# -*- coding: utf-8 -*-
"""
Creative Production API routes for AIGV Studio.
"""
from __future__ import absolute_import

import json
import math
import os
import shutil
import subprocess
import time

from flask import g, request, send_file

from .access import (
    can_read_asset, current_user, require_asset, require_project, require_shot,
    require_task,
)
from .asset_service import get_asset_service
from .auth_middleware import is_admin
from .creative_project_service import get_creative_project_service
from .credential_service import CredentialService
from .generation_models import list_models
from .generation_service import create_generation_task
from .http_utils import ApiError, parse_json_body, parse_pagination, require_fields
from .media_filters import validate_filters
from .media_service import probe_media_file
from .models import (
    CreativeProject, ExportPackage, GenerationTask, ShotMediaVersion,
    TimelineClip, TimelineTrack,
)
from .providers.base import ProviderError
from .storyboard_service import get_storyboard_service
from .task_service import get_task_service
from .task_serializer import public_task_dict, public_task_dicts
from .timeline_service import get_timeline_service
from .tts_service import TTSVoiceRegistry


def register_creative_routes(app, cfg, json_success, json_error):
    """Register all creative production API routes."""

    project_service = get_creative_project_service(cfg.DATA_DIR)
    storyboard_service = get_storyboard_service(cfg.DATA_DIR)
    task_service = get_task_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    timeline_service = get_timeline_service(cfg)

    def _legacy_capacity_error(user, project_id=None, storyboard=False):
        """Reject abusive legacy-task creation (one shared worker thread)."""
        from .task_worker import LEGACY_TASK_TYPES

        limit = getattr(cfg, "MAX_ACTIVE_LEGACY_TASKS_PER_USER", 3)
        if limit and task_service.count_active_tasks(
            user.get("id"), task_types=LEGACY_TASK_TYPES
        ) >= limit:
            return json_error(
                "quota_exceeded",
                "同时进行的创作任务过多，请等待完成后再提交",
                status_code=429,
            )
        if storyboard and project_id and task_service.count_active_project_tasks(
            project_id, task_types=(GenerationTask.TYPE_STORYBOARD,)
        ):
            return json_error(
                "task_in_progress",
                "该项目已有分镜分析任务正在进行，请等待完成或取消",
                status_code=409,
            )
        return None

    def _bounded_float(data, key, default, minimum, maximum):
        value = data.get(key, default)
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "{0} 必须是数字".format(key), status_code=400)
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise ApiError(
                "invalid_params",
                "{0} 需在 {1}–{2} 之间".format(key, minimum, maximum),
                status_code=400,
            )
        return value

    def _idempotent_task(user, task_type, client_request_id, project_id=None):
        if not client_request_id:
            return None
        existing = task_service.find_idempotent_task(user.get("id"), client_request_id)
        if existing and existing.task_type == task_type:
            if project_id and existing.creative_project_id != project_id:
                raise ApiError(
                    "idempotency_key_conflict",
                    "该请求标识已用于其他项目",
                    status_code=409,
                )
            return existing
        return None

    def _resolve_tts_params(data, voice_id=None, default_text=None):
        registry = TTSVoiceRegistry(cfg)
        requested = voice_id or data.get("voice_id")
        provider = (data.get("provider") or "piper").strip()
        try:
            voice = registry.resolve_voice(requested)
        except ProviderError as exc:
            raise ApiError(exc.error_type, str(exc), status_code=400)
        if provider != voice["provider"]:
            raise ApiError(
                "tts_provider_mismatch",
                "所选音色不属于该 TTS Provider",
                status_code=400,
            )
        text = data.get("text")
        if text is None:
            text = default_text
        text = (text or "").strip()
        if not text:
            raise ApiError("empty_text", "配音文案不能为空", status_code=400)
        max_len = int(getattr(cfg, "MAX_TTS_TEXT_LENGTH", 2000))
        if len(text) > max_len:
            raise ApiError(
                "invalid_params",
                "配音文案不能超过 {0} 个字符".format(max_len),
                status_code=400,
            )
        rate = _bounded_float(data, "speech_rate", 1.0, 0.5, 2.0)
        volume = _bounded_float(data, "volume", 1.0, 0.0, 2.0)
        capabilities = voice.get("capabilities") or {}
        if not (capabilities.get("speech_rate") or {}).get("supported") and rate != 1.0:
            raise ApiError(
                "unsupported_tts_option", "当前 TTS 不支持语速调节", status_code=400
            )
        if not (capabilities.get("volume") or {}).get("supported") and volume != 1.0:
            raise ApiError(
                "unsupported_tts_option", "当前 TTS 不支持音量调节", status_code=400
            )
        return {
            "provider": voice["provider"],
            "voice_id": voice["id"],
            "voice_label": voice.get("label"),
            "text": text,
            "speech_rate": rate,
            "volume": volume,
        }

    _EDITABLE_SHOT_FIELDS = {
        "scene_title", "scene_description", "shot_type", "duration_s",
        "dialogue", "camera_movement", "lighting_mood", "environment_detail",
        "character_action", "visual_style", "prompt_cn", "prompt_en",
        "negative_prompt", "status", "sequence_no", "metadata",
        "keyframe_asset_id", "primary_image_asset_id",
    }

    def _sanitize_shot_payload(data, project_id=None):
        """Only expose editorial shot fields; media pointers are set by
        validated endpoints/workers, never by arbitrary client JSON."""
        unknown = sorted(set(data) - _EDITABLE_SHOT_FIELDS)
        if unknown:
            raise ApiError(
                "invalid_shot_field",
                "不允许直接修改这些分镜字段：{0}".format(", ".join(unknown)),
                status_code=400,
            )
        payload = dict(data)
        if "duration_s" in payload:
            try:
                duration = float(payload["duration_s"])
            except (TypeError, ValueError):
                raise ApiError("invalid_params", "duration_s 必须是数字", status_code=400)
            if not math.isfinite(duration) or duration <= 0 or duration > 600:
                raise ApiError("invalid_params", "duration_s 需在 0–600 秒之间", status_code=400)
            payload["duration_s"] = duration
        if "sequence_no" in payload:
            try:
                payload["sequence_no"] = int(payload["sequence_no"])
            except (TypeError, ValueError):
                raise ApiError("invalid_params", "sequence_no 必须是整数", status_code=400)
        if "metadata" in payload and payload["metadata"] is not None:
            if not isinstance(payload["metadata"], dict):
                raise ApiError("invalid_params", "metadata 必须是对象", status_code=400)
        if "status" in payload and payload["status"] not in (
            "draft", "pending", "generating_image", "generating_video",
            "ready", "confirmed", "failed",
        ):
            raise ApiError("invalid_params", "不支持的分镜状态", status_code=400)
        for key in ("keyframe_asset_id", "primary_image_asset_id"):
            asset_id = payload.get(key)
            if not asset_id:
                continue
            asset = require_asset(asset_id, write=False, demo_mode=cfg.DEMO_MODE)
            if asset.asset_type != "image":
                raise ApiError(
                    "invalid_asset", "{0} 必须是图片素材".format(key), status_code=400
                )
        return payload

    def _shot_audio_versions(shot_id):
        rows = project_service.db.fetch_all(
            "SELECT * FROM shot_media_versions WHERE shot_id = ? "
            "AND media_kind = 'audio' "
            "ORDER BY is_selected DESC, created_at DESC, rowid DESC",
            (shot_id,),
        )
        return [ShotMediaVersion.from_row(row) for row in rows]

    def _compose_settings(data):
        resolution = str(data.get("resolution") or "").strip().lower()
        if resolution in ("720p", "1280x720"):
            width, height = 1280, 720
        elif resolution in ("1080p", "1920x1080"):
            width, height = 1920, 1080
        else:
            try:
                width = int(data.get("width") or 1920)
                height = int(data.get("height") or 1080)
            except (TypeError, ValueError):
                raise ApiError("invalid_params", "输出分辨率无效", status_code=400)
        if (width, height) not in ((1280, 720), (1920, 1080)):
            raise ApiError(
                "invalid_params", "只支持 720p 或 1080p 输出", status_code=400
            )
        try:
            fps = int(data.get("fps") or 30)
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "fps 必须是整数", status_code=400)
        if fps not in (24, 25, 30):
            raise ApiError("invalid_params", "只支持 24/25/30 FPS", status_code=400)
        try:
            crf = int(data.get("crf", 20))
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "crf 必须是整数", status_code=400)
        if not 16 <= crf <= 28:
            raise ApiError("invalid_params", "crf 需在 16–28 之间", status_code=400)
        audio_bitrate = str(data.get("audio_bitrate") or "192k")
        if audio_bitrate not in ("128k", "192k", "256k", "320k"):
            raise ApiError("invalid_params", "不支持的音频码率", status_code=400)
        subtitle_mode = str(data.get("subtitle_mode") or "none")
        if subtitle_mode not in ("none", "mov_text", "burn"):
            raise ApiError("invalid_params", "不支持的字幕模式", status_code=400)
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "crf": crf,
            "audio_bitrate": audio_bitrate,
            "subtitle_mode": subtitle_mode,
            "keep_source_audio": bool(data.get("keep_source_audio", False)),
            "music_ducking": bool(data.get("music_ducking", False)),
            "loudness_normalize": bool(data.get("loudness_normalize", True)),
            "subtitle_font_name": getattr(cfg, "SUBTITLE_FONT_NAME", "Noto Sans CJK SC"),
            "subtitle_font_size": int(getattr(cfg, "SUBTITLE_FONT_SIZE", 24)),
            "timeout_s": int(getattr(cfg, "FFMPEG_TIMEOUT_S", 1800)),
            "min_output_bytes": int(getattr(cfg, "MIN_OUTPUT_BYTES", 4096)),
            "max_inputs": int(getattr(cfg, "MAX_COMPOSE_INPUTS", 200)),
            "max_output_mb": int(getattr(cfg, "MAX_COMPOSE_OUTPUT_MB", 1500)),
        }

    def _check_subtitle_burn_support():
        ffmpeg_bin = getattr(cfg, "FFMPEG_BIN", "ffmpeg")
        if not shutil.which(ffmpeg_bin) and not os.path.isfile(ffmpeg_bin):
            return False, "FFmpeg 不可用"
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-hide_banner", "-filters"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
            )
            text = (proc.stdout or b"").decode("utf-8", errors="replace")
            if " subtitles " not in text:
                return False, "当前 FFmpeg 未启用 libass/subtitles 滤镜"
        except Exception:
            return False, "无法检查 FFmpeg 字幕能力"
        font = getattr(cfg, "SUBTITLE_FONT_NAME", "Noto Sans CJK SC")
        try:
            proc = subprocess.run(
                ["fc-match", "-f", "%{family}", font],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            matched = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
            has_cjk = (
                font.lower() in matched.lower()
                or "cjk" in matched.lower()
                or "noto" in matched.lower() and "sc" in matched.lower()
            )
            if not has_cjk:
                cjk_proc = subprocess.run(
                    ["fc-list", ":lang=zh"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                )
                has_cjk = bool((cjk_proc.stdout or b"").strip())
            if not matched or not has_cjk:
                return False, "未找到可用的中文字体：{0}".format(font)
        except Exception:
            return False, "fontconfig 不可用，无法烧录字幕"
        return True, None

    # ── Project CRUD ──

    @app.route("/api/creative/projects", methods=["GET"])
    def list_creative_projects():
        user = current_user()
        pagination = parse_pagination(request)
        tenant_id = request.args.get("tenant_id") if is_admin(user) else user.get("tenant_id")
        user_id = None if is_admin(user) else user.get("id")
        result = project_service.list_projects(
            tenant_id=tenant_id,
            user_id=user_id,
            include_unowned=bool(cfg.DEMO_MODE),
            limit=pagination.limit,
            offset=pagination.offset,
        )
        return json_success(result)

    @app.route("/api/creative/projects", methods=["POST"])
    def create_creative_project():
        data = parse_json_body(request)
        require_fields(data, ["name"])
        user = current_user()
        workspace = project_service.db.fetch_one(
            "SELECT id FROM projects WHERE id = ?",
            ("workspace_{0}".format(user.get("id")),),
        )
        project = project_service.create_project(
            name=data.get("name"),
            description=data.get("description"),
            genre=data.get("genre"),
            concept=data.get("concept"),
            requirements=data.get("requirements"),
            creative_brief=data.get("creative_brief"),
            settings=data.get("settings"),
            tenant_id=user.get("tenant_id"),
            project_id=workspace["id"] if workspace else None,
            user_id=user.get("id"),
            status=CreativeProject.STATUS_DRAFT,
        )
        return json_success(project.to_dict(), message="项目已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>", methods=["GET"])
    def get_creative_project(project_id):
        project = require_project(project_id, demo_mode=cfg.DEMO_MODE)
        return json_success(project.to_dict())

    @app.route("/api/creative/projects/<project_id>", methods=["PUT"])
    def update_creative_project(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        project = project_service.update_project(project_id, **data)
        if not project:
            return json_error("project_not_found", "项目不存在", status_code=404)
        return json_success(project.to_dict(), message="项目已更新")

    @app.route("/api/creative/projects/<project_id>", methods=["DELETE"])
    def delete_creative_project(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        success = project_service.delete_project(project_id)
        if not success:
            return json_error("project_not_found", "项目不存在", status_code=404)
        return json_success({"deleted": True}, message="项目已删除")

    # ── Storyboard Analysis ──

    @app.route("/api/creative/projects/<project_id>/analyze", methods=["POST"])
    def analyze_creative_project(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user, project_id, storyboard=True)
        if capacity_error:
            return capacity_error

        credential_service = CredentialService(cfg.DATA_DIR, cfg)
        available, _reason = credential_service.has_llm(user.get("id"), cfg)
        if not available:
            return json_error(
                "provider_not_configured",
                "LLM 服务未配置",
                status_code=400,
                details={"configure_url": "/api-settings"},
            )

        source = credential_service.effective(user.get("id"), "llm", cfg).get("source")
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_STORYBOARD,
            params={"project_id": project_id, "credential_source": source},
            created_by=user.get("id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="分析任务已创建", status_code=201)

    # ── Storyboard Shots CRUD ──

    @app.route("/api/creative/projects/<project_id>/shots", methods=["GET"])
    def list_storyboard_shots(project_id):
        require_project(project_id, demo_mode=cfg.DEMO_MODE)
        shots = storyboard_service.list_shots(project_id)
        return json_success([s.to_dict() for s in shots])

    @app.route("/api/creative/projects/<project_id>/shots", methods=["POST"])
    def create_storyboard_shot(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = _sanitize_shot_payload(parse_json_body(request), project_id)
        shot = storyboard_service.create_shot(project_id, **data)
        return json_success(shot.to_dict(), message="分镜已添加", status_code=201)

    @app.route("/api/creative/shots/<shot_id>", methods=["PUT"])
    def update_storyboard_shot(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = _sanitize_shot_payload(parse_json_body(request), shot.creative_project_id)
        shot = storyboard_service.update_shot(shot_id, **data)
        if not shot:
            return json_error("shot_not_found", "分镜不存在", status_code=404)
        return json_success(shot.to_dict(), message="分镜已更新")

    @app.route("/api/creative/shots/<shot_id>", methods=["DELETE"])
    def delete_storyboard_shot(shot_id):
        require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        success = storyboard_service.delete_shot(shot_id)
        if not success:
            return json_error("shot_not_found", "分镜不存在", status_code=404)
        return json_success({"deleted": True}, message="分镜已删除")

    @app.route("/api/creative/shots/reorder", methods=["POST"])
    def reorder_storyboard_shots():
        data = parse_json_body(request)
        require_fields(data, ["project_id", "ordered_ids"])
        require_project(data["project_id"], write=True, demo_mode=cfg.DEMO_MODE)

        storyboard_service.reorder_shots(data["project_id"], data["ordered_ids"])
        return json_success({"reordered": True}, message="顺序已更新")

    # ── Generation Tasks ──

    @app.route("/api/creative/shots/<shot_id>/images", methods=["POST"])
    def generate_shot_images(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        user = current_user()
        model_key = data.get("model_key")
        if not model_key:
            available = [
                m
                for m in list_models(cfg, task_type="image", user=user)
                if m["available"]
            ]
            if not available:
                return json_error("provider_not_configured", "图片生成模型未配置", status_code=400)
            model_key = available[0]["key"]

        prompt = data.get("prompt") or shot.prompt_en or shot.prompt_cn or shot.scene_description or ""
        task = create_generation_task(
            cfg,
            task_service,
            user,
            GenerationTask.TYPE_IMAGE,
            model_key,
            {
                "prompt": prompt,
                # Let create_generation_task apply the selected model's default.
                "size": data.get("size") or data.get("resolution"),
                "ratio": data.get("ratio") or data.get("aspect_ratio"),
                "seed": data.get("seed"),
                "negative_prompt": data.get("negative_prompt") or shot.negative_prompt,
                "reference_asset_id": data.get("reference_asset_id"),
                "reference_asset_ids": data.get("reference_asset_ids"),
                "watermark": data.get("watermark", False),
                "client_request_id": data.get("client_request_id"),
            },
            project_id=shot.creative_project_id,
            shot_id=shot_id,
            client_request_id=data.get("client_request_id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="图片生成任务已创建", status_code=201)

    @app.route("/api/creative/shots/<shot_id>/videos", methods=["POST"])
    def generate_shot_video(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        user = current_user()
        model_key = data.get("model_key")
        if not model_key:
            available = [
                m
                for m in list_models(cfg, task_type="video", user=user)
                if m["available"]
            ]
            if not available:
                return json_error("provider_not_configured", "视频生成模型未配置", status_code=400)
            model_key = available[0]["key"]

        prompt = data.get("prompt") or shot.prompt_en or shot.prompt_cn or shot.scene_description or ""
        reference_asset_id = (
            data.get("reference_asset_id")
            or shot.keyframe_asset_id
            or shot.primary_image_asset_id
        )
        task = create_generation_task(
            cfg,
            task_service,
            user,
            GenerationTask.TYPE_VIDEO,
            model_key,
            {
                "prompt": prompt,
                "ratio": data.get("ratio") or data.get("aspect_ratio") or "16:9",
                "duration_s": data.get("duration_s") or data.get("duration") or int(shot.duration_s or 5),
                "resolution": data.get("resolution") or "720p",
                # None lets create_generation_task use the model's default
                # (Seedance 2.5 defaults to audio on).
                "generate_audio": data.get("generate_audio"),
                "watermark": data.get("watermark", False),
                "seed": data.get("seed"),
                "reference_asset_id": reference_asset_id,
                "reference_asset_ids": data.get("reference_asset_ids"),
                "client_request_id": data.get("client_request_id"),
            },
            project_id=shot.creative_project_id,
            shot_id=shot_id,
            client_request_id=data.get("client_request_id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="视频生成任务已创建", status_code=201)

    @app.route("/api/creative/tts/voices", methods=["GET"])
    def list_tts_voices():
        current_user()
        registry = TTSVoiceRegistry(cfg)
        return json_success({
            "items": registry.list_voices(),
            "providers": registry.providers(),
            "default_voice_id": registry.default_voice_id(),
        })

    @app.route("/api/creative/shots/<shot_id>/tts", methods=["POST"])
    def generate_shot_tts(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error

        params = _resolve_tts_params(data, default_text=shot.dialogue)
        client_request_id = (data.get("client_request_id") or "").strip() or None
        existing = _idempotent_task(
            user, GenerationTask.TYPE_TTS, client_request_id,
            project_id=shot.creative_project_id,
        )
        if existing:
            return json_success(
                public_task_dict(existing, asset_service, task_service),
                message="配音任务已存在",
            )

        storyboard_service.update_shot(shot.id, dialogue=params["text"])
        task = task_service.create_task(
            creative_project_id=shot.creative_project_id,
            task_type=GenerationTask.TYPE_TTS,
            params={
                "shot_ids": [shot.id],
                "mode": "all",
                "provider": params["provider"],
                "voice_id": params["voice_id"],
                "voice_label": params["voice_label"],
                "text": params["text"],
                "speech_rate": params["speech_rate"],
                "volume": params["volume"],
                "client_request_id": client_request_id,
            },
            target_shot_id=shot.id,
            created_by=user.get("id"),
            client_request_id=client_request_id,
        )
        return json_success(
            public_task_dict(task, asset_service, task_service),
            message="配音任务已创建",
            status_code=201,
        )

    @app.route("/api/creative/shots/<shot_id>/audio", methods=["GET"])
    def get_shot_audio(shot_id):
        shot, _project = require_shot(shot_id, demo_mode=cfg.DEMO_MODE)
        versions = _shot_audio_versions(shot_id)
        items = []
        for version in versions:
            asset = asset_service.get_asset(version.asset_id) if version.asset_id else None
            if not asset:
                continue
            if not can_read_asset(
                asset, current_user(), demo_mode=cfg.DEMO_MODE
            ):
                continue
            metadata = version.metadata or {}
            items.append({
                "id": version.id,
                "asset": asset_service.public_dict(asset, viewer=current_user()),
                "source": version.source,
                "provider": metadata.get("provider"),
                "voice_id": metadata.get("voice_id"),
                "voice_label": metadata.get("voice_label") or version.label,
                "speech_rate": metadata.get("speech_rate"),
                "volume": metadata.get("volume"),
                "duration_s": asset.duration_s or metadata.get("duration_s"),
                "is_selected": bool(version.is_selected),
                "task_id": version.task_id,
                "created_at": version.created_at,
            })
        subtitle = (
            asset_service.get_asset(shot.subtitle_asset_id)
            if shot.subtitle_asset_id else None
        )
        if subtitle and not can_read_asset(
            subtitle, current_user(), demo_mode=cfg.DEMO_MODE
        ):
            subtitle = None
        return json_success({
            "shot_id": shot.id,
            "dialogue": shot.dialogue,
            "current_audio_asset_id": shot.audio_asset_id,
            "audio_options": shot.audio_options,
            "audio_duration_s": shot.audio_duration_s,
            "subtitle_asset_id": shot.subtitle_asset_id,
            "subtitle": asset_service.public_dict(subtitle, viewer=current_user()) if subtitle else None,
            "items": items,
        })

    @app.route("/api/creative/shots/<shot_id>/audio/selection", methods=["POST"])
    def select_shot_audio(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        asset_id = data.get("asset_id")
        metadata = {}
        subtitle_asset = None
        subtitle_path = None
        if asset_id:
            asset = require_asset(asset_id, write=False, demo_mode=cfg.DEMO_MODE)
            version = next(
                (item for item in _shot_audio_versions(shot_id)
                 if item.asset_id == asset.id),
                None,
            )
            if not version:
                raise ApiError(
                    "asset_not_linked_to_shot",
                    "该音频不是此分镜的配音版本",
                    status_code=400,
                )
            if asset.asset_type != "audio":
                raise ApiError("invalid_asset", "所选素材不是音频", status_code=400)
            metadata = version.metadata or {}
            subtitle_asset_id = metadata.get("subtitle_asset_id")
            if subtitle_asset_id:
                subtitle_asset = asset_service.get_asset(subtitle_asset_id)
                if subtitle_asset and not can_read_asset(
                    subtitle_asset, current_user(), demo_mode=cfg.DEMO_MODE
                ):
                    subtitle_asset = None
            if not subtitle_asset:
                subtitle_row = project_service.db.fetch_one(
                    "SELECT asset_id FROM shot_media_versions WHERE shot_id = ? "
                    "AND media_kind = 'subtitle' AND task_id = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (shot.id, version.task_id),
                )
                if subtitle_row and subtitle_row["asset_id"]:
                    subtitle_asset = asset_service.get_asset(subtitle_row["asset_id"])
            if subtitle_asset:
                subtitle_path = asset_service.get_file_path_for_asset(subtitle_asset)
            options = dict(metadata)
            options["subtitle_asset_id"] = subtitle_asset.id if subtitle_asset else None
            storyboard_service.set_media_pointers(
                shot.id,
                audio_asset_id=asset.id,
                audio_options=options,
                audio_duration_s=asset.duration_s or metadata.get("duration_s"),
                subtitle_asset_id=subtitle_asset.id if subtitle_asset else None,
                srt_path=subtitle_path,
            )
        else:
            version = None
            storyboard_service.set_media_pointers(
                shot.id,
                audio_asset_id=None,
                audio_options=None,
                audio_duration_s=None,
                subtitle_asset_id=None,
                srt_path=None,
            )
        now = int(time.time())
        project_service.db.execute(
            "UPDATE shot_media_versions SET is_selected = CASE WHEN asset_id = ? THEN 1 ELSE 0 END, "
            "updated_at = ? WHERE shot_id = ? AND media_kind = 'audio'",
            (asset_id or "", now, shot.id),
        )
        timeline_updated, timeline_version = timeline_service.sync_shot_media(
            shot.creative_project_id,
            shot.id,
            audio_asset_id=asset_id or None,
            audio_duration_s=(asset.duration_s if asset_id else None) or metadata.get("duration_s"),
            audio_options=metadata,
            subtitle_text=shot.dialogue,
            subtitle_duration_s=(
                (asset.duration_s if asset_id else None) or metadata.get("duration_s")
                or shot.audio_duration_s
            ),
        )
        return json_success({
            "selected_asset_id": asset_id or None,
            "version_id": version.id if version else None,
            "timeline_updated": timeline_updated,
            "timeline_version": timeline_version,
            "requires_recompose": timeline_updated,
        }, message="配音选择已更新")

    @app.route("/api/creative/projects/<project_id>/tts", methods=["POST"])
    def generate_project_tts(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error

        data = parse_json_body(request)
        mode = (data.get("mode") or "all").strip()
        if mode not in ("all", "missing"):
            raise ApiError("invalid_params", "mode 只能是 all 或 missing", status_code=400)
        shots = storyboard_service.list_shots(project_id)
        by_id = {shot.id: shot for shot in shots}
        shot_ids = data.get("shot_ids") or []
        if shot_ids:
            unknown = [shot_id for shot_id in shot_ids if shot_id not in by_id]
            if unknown:
                raise ApiError(
                    "shot_not_found", "存在不属于该项目的分镜", status_code=400
                )
            target_shot = by_id[shot_ids[0]]
            default_text = target_shot.dialogue if len(shot_ids) == 1 else None
        else:
            target_shot = None
            default_text = None
        voice_id = data.get("voice_id")
        if target_shot is None and data.get("text"):
            raise ApiError(
                "invalid_params", "批量配音不能指定单个分镜的文案", status_code=400
            )
        if data.get("text") and len(shot_ids) != 1:
            raise ApiError(
                "invalid_params", "指定文案时只能选择一个分镜", status_code=400
            )
        params = _resolve_tts_params(data, voice_id=voice_id, default_text=default_text)
        client_request_id = (data.get("client_request_id") or "").strip() or None
        existing = _idempotent_task(
            user, GenerationTask.TYPE_TTS, client_request_id, project_id=project_id
        )
        if existing:
            return json_success(
                public_task_dict(existing, asset_service, task_service),
                message="配音任务已存在",
            )
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_TTS,
            params={
                "shot_ids": shot_ids,
                "mode": mode,
                "provider": params["provider"],
                "voice_id": params["voice_id"],
                "voice_label": params["voice_label"],
                "text": data.get("text") if len(shot_ids) == 1 else None,
                "speech_rate": params["speech_rate"],
                "volume": params["volume"],
                "client_request_id": client_request_id,
            },
            target_shot_id=target_shot.id if target_shot else None,
            created_by=user.get("id"),
            client_request_id=client_request_id,
        )

        return json_success(
            public_task_dict(task, asset_service, task_service),
            message="TTS 生成任务已创建",
            status_code=201,
        )

    @app.route("/api/creative/projects/<project_id>/compose", methods=["POST"])
    def compose_project_video(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error
        if not cfg.has_ffmpeg_configured():
            return json_error("provider_not_configured", "FFmpeg 视频合成服务未配置", status_code=400)

        data = parse_json_body(request)
        settings = _compose_settings(data)
        timeline = timeline_service.get_timeline(
            project_id, ensure=True, user=user
        )
        video_clips = [
            clip
            for item in timeline.get("tracks") or []
            if (item.get("track") or {}).get("role") == "video"
            or (item.get("track") or {}).get("track_type") == "video"
            for clip in item.get("clips") or []
            if not clip.get("muted")
        ]
        if not video_clips:
            return json_error(
                "timeline_has_no_video",
                "时间线没有可合成的视频片段，请先完成第 03 步并保存时间线",
                status_code=400,
            )
        current_version = int(timeline.get("timeline_version") or 0)
        if data.get("timeline_version") is not None:
            try:
                requested_version = int(data.get("timeline_version"))
            except (TypeError, ValueError):
                raise ApiError("invalid_params", "timeline_version 必须是整数", status_code=400)
            if requested_version != current_version:
                return json_error(
                    "timeline_conflict",
                    "时间线已修改，请刷新后再合成",
                    status_code=409,
                    details={"current_timeline_version": current_version},
                )
        timeline_end = timeline_service.timeline_end(timeline)
        if timeline_end <= 0:
            return json_error("timeline_has_no_video", "时间线时长无效", status_code=400)
        max_duration = int(getattr(cfg, "MAX_COMPOSE_DURATION_S", 900))
        if timeline_end > max_duration:
            return json_error(
                "timeline_too_long",
                "时间线超过最长合成时长（{0} 秒）".format(max_duration),
                status_code=400,
            )
        for item in timeline.get("tracks") or []:
            if (item.get("track") or {}).get("role") != "narration":
                continue
            for clip in item.get("clips") or []:
                if float(clip.get("start_time") or 0) + float(
                    clip.get("duration_s") or 0
                ) > timeline_end + 0.05:
                    return json_error(
                        "narration_exceeds_timeline",
                        "配音片段超出视频总时长，请调整语速、裁切或延长镜头",
                        status_code=400,
                        details={"clip_id": clip.get("id")},
                    )
        if settings["subtitle_mode"] == "burn":
            supported, reason = _check_subtitle_burn_support()
            if not supported:
                return json_error(
                    "missing_font_dependency", reason, status_code=400
                )
        try:
            free = shutil.disk_usage(cfg.DATA_DIR).free
            if free < 256 * 1024 * 1024:
                return json_error(
                    "insufficient_storage", "磁盘剩余空间不足", status_code=400
                )
        except OSError:
            pass

        client_request_id = (data.get("client_request_id") or "").strip() or None
        existing = _idempotent_task(
            user, GenerationTask.TYPE_COMPOSE, client_request_id, project_id=project_id
        )
        if existing:
            return json_success(
                public_task_dict(existing, asset_service, task_service),
                message="合成任务已存在",
            )

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_COMPOSE,
            params={"export_settings": settings},
            timeline_version=current_version,
            timeline_snapshot=timeline,
            created_by=user.get("id"),
            client_request_id=client_request_id,
        )

        return json_success(
            public_task_dict(task, asset_service, task_service),
            message="视频合成任务已创建",
            status_code=202,
        )

    @app.route("/api/creative/projects/<project_id>/refine", methods=["POST"])
    def refine_project_video(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error
        if not cfg.has_ffmpeg_configured():
            return json_error("provider_not_configured", "FFmpeg 视频精修服务未配置", status_code=400)

        data = parse_json_body(request)
        if data.get("input_path"):
            return json_error("invalid_params", "不接受服务器文件路径，请使用 input_asset_id", status_code=400)
        require_fields(data, ["shot_id"])
        shot, _shot_project = require_shot(
            data["shot_id"], write=True, demo_mode=cfg.DEMO_MODE
        )
        if shot.creative_project_id != project_id:
            raise ApiError("invalid_params", "分镜不属于当前项目", status_code=400)
        input_asset_id = (
            data.get("input_asset_id")
            or shot.selected_video_asset_id
            or shot.video_asset_id
        )
        if not input_asset_id:
            raise ApiError("refine_no_input", "该分镜还没有可精修的视频", status_code=400)
        asset = require_asset(input_asset_id, write=False, demo_mode=cfg.DEMO_MODE)
        if asset.asset_type != "video":
            raise ApiError("refine_no_input", "精修输入必须是视频素材", status_code=400)
        linked = project_service.db.fetch_one(
            "SELECT id FROM shot_media_versions WHERE shot_id = ? "
            "AND media_kind = 'video' AND asset_id = ?",
            (shot.id, asset.id),
        )
        if not linked and asset.id not in (
            shot.video_asset_id, shot.selected_video_asset_id,
            shot.refined_video_asset_id,
        ):
            raise ApiError(
                "asset_not_linked_to_shot",
                "所选视频不是该分镜的版本",
                status_code=400,
            )
        try:
            filters = validate_filters(data.get("filters") or {})
        except ApiError as exc:
            raise ApiError(exc.code, exc.message, status_code=400, details=exc.details)
        client_request_id = (data.get("client_request_id") or "").strip() or None
        existing = _idempotent_task(
            user, GenerationTask.TYPE_REFINE, client_request_id, project_id=project_id
        )
        if existing:
            return json_success(
                public_task_dict(existing, asset_service, task_service),
                message="精修任务已存在",
            )
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_REFINE,
            params={
                "shot_id": shot.id,
                "input_asset_id": asset.id,
                "filters": filters,
                "client_request_id": client_request_id,
            },
            target_shot_id=shot.id,
            target_asset_id=asset.id,
            created_by=user.get("id"),
            client_request_id=client_request_id,
        )
        return json_success(
            public_task_dict(task, asset_service, task_service),
            message="视频精修任务已创建",
            status_code=202,
        )

    def _video_versions(shot_id):
        rows = project_service.db.fetch_all(
            "SELECT * FROM shot_media_versions WHERE shot_id = ? "
            "AND media_kind = 'video' "
            "ORDER BY is_selected DESC, created_at DESC, rowid DESC",
            (shot_id,),
        )
        return [ShotMediaVersion.from_row(row) for row in rows]

    @app.route("/api/creative/shots/<shot_id>/videos", methods=["GET"])
    def list_shot_videos(shot_id):
        shot, _project = require_shot(shot_id, demo_mode=cfg.DEMO_MODE)
        versions = _video_versions(shot_id)
        items = []
        seen = set()
        for version in versions:
            if not version.asset_id or version.asset_id in seen:
                continue
            asset = asset_service.get_asset(version.asset_id)
            if not asset:
                continue
            if not can_read_asset(
                asset, current_user(), demo_mode=cfg.DEMO_MODE
            ):
                continue
            seen.add(asset.id)
            metadata = version.metadata or {}
            items.append({
                "id": version.id,
                "asset": asset_service.public_dict(asset, viewer=current_user()),
                "source": version.source,
                "label": version.label,
                "filters": metadata.get("filters"),
                "duration_s": asset.duration_s,
                "is_selected": asset.id == (shot.selected_video_asset_id or shot.video_asset_id),
                "is_refined": asset.id == shot.refined_video_asset_id,
                "task_id": version.task_id,
                "created_at": version.created_at,
            })
        if shot.video_asset_id and shot.video_asset_id not in seen:
            asset = asset_service.get_asset(shot.video_asset_id)
            if asset and can_read_asset(
                asset, current_user(), demo_mode=cfg.DEMO_MODE
            ):
                items.append({
                    "id": "legacy-video-{0}".format(shot.id),
                    "asset": asset_service.public_dict(asset, viewer=current_user()),
                    "source": "legacy",
                    "label": "AI 生成视频",
                    "filters": None,
                    "duration_s": asset.duration_s,
                    "is_selected": asset.id == (shot.selected_video_asset_id or shot.video_asset_id),
                    "is_refined": False,
                    "task_id": None,
                    "created_at": asset.created_at,
                })
        return json_success({
            "shot_id": shot.id,
            "selected_video_asset_id": shot.selected_video_asset_id or shot.video_asset_id,
            "original_video_asset_id": shot.video_asset_id,
            "refined_video_asset_id": shot.refined_video_asset_id,
            "selection_source": shot.video_selection_source,
            "items": items,
        })

    @app.route("/api/creative/shots/<shot_id>/video-selection", methods=["POST"])
    def select_shot_video(shot_id):
        shot, _project = require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        asset_id = data.get("asset_id")
        if not asset_id:
            raise ApiError("invalid_params", "请选择视频版本", status_code=400)
        asset = require_asset(asset_id, write=False, demo_mode=cfg.DEMO_MODE)
        if asset.asset_type != "video":
            raise ApiError("invalid_asset", "所选素材不是视频", status_code=400)
        version = next(
            (item for item in _video_versions(shot_id) if item.asset_id == asset.id),
            None,
        )
        allowed = {
            shot.video_asset_id, shot.refined_video_asset_id,
            shot.selected_video_asset_id,
        }
        if not version and asset.id not in allowed:
            raise ApiError(
                "asset_not_linked_to_shot",
                "所选视频不是该分镜的版本",
                status_code=400,
            )
        source = (
            "refined" if version and version.source == "refine"
            else "original"
        )
        storyboard_service.set_media_pointers(
            shot.id,
            selected_video_asset_id=asset.id,
            video_selection_source=source,
        )
        now = int(time.time())
        project_service.db.execute(
            "UPDATE shot_media_versions SET is_selected = CASE WHEN asset_id = ? "
            "THEN 1 ELSE 0 END, updated_at = ? WHERE shot_id = ? AND media_kind = 'video'",
            (asset.id, now, shot.id),
        )
        timeline_updated = False
        timeline_version = None
        try:
            info = probe_media_file(cfg.FFPROBE_BIN, asset_service.get_file_path_for_asset(asset))
            asset_duration = float(info.get("duration_s") or 0)
        except Exception:
            asset_duration = 0.0
        clip_rows = project_service.db.fetch_all(
            "SELECT c.* FROM timeline_clips c "
            "JOIN timeline_tracks t ON t.id = c.track_id "
            "WHERE c.creative_project_id = ? AND c.shot_id = ? "
            "AND (t.role = 'video' OR t.track_type = 'video')",
            (shot.creative_project_id, shot.id),
        )
        video_track = project_service.db.fetch_one(
            "SELECT * FROM timeline_tracks WHERE creative_project_id = ? "
            "AND (role = 'video' OR track_type = 'video') "
            "ORDER BY sequence_no ASC LIMIT 1",
            (shot.creative_project_id,),
        )
        if clip_rows or video_track:
            with project_service.db.transaction() as cursor:
                if clip_rows:
                    for row in clip_rows:
                        old_duration = float(row["duration_s"] or 0)
                        new_duration = old_duration
                        if asset_duration > 0:
                            new_duration = min(old_duration, asset_duration)
                        if new_duration <= 0:
                            new_duration = asset_duration or float(shot.duration_s or 1)
                        # Selecting a different source resets the source trim;
                        # leaving the old trim_in would make trim_out < trim_in.
                        cursor.execute(
                            "UPDATE timeline_clips SET asset_id = ?, trim_in = 0, "
                            "duration_s = ?, trim_out = ?, updated_at = ? WHERE id = ?",
                            (asset.id, new_duration, new_duration, now, row["id"]),
                        )
                elif video_track:
                    cursor.execute(
                        "SELECT COALESCE(MAX(start_time + duration_s), 0) AS end_time "
                        "FROM timeline_clips WHERE track_id = ?",
                        (video_track["id"],),
                    )
                    end_time = float(cursor.fetchone()["end_time"] or 0)
                    duration = asset_duration or float(shot.duration_s or 1)
                    from .models import TimelineClip
                    clip = TimelineClip(
                        track_id=video_track["id"],
                        creative_project_id=shot.creative_project_id,
                        shot_id=shot.id,
                        asset_id=asset.id,
                        name=shot.scene_title or "镜头",
                        start_time=end_time,
                        duration_s=duration,
                        trim_in=0,
                        trim_out=duration,
                        volume=1.0,
                        muted=False,
                        source_audio_enabled=not bool(shot.audio_asset_id),
                        fade_in=0,
                        fade_out=0,
                        properties={"added_by_version_selection": True},
                        created_at=now,
                        updated_at=now,
                    )
                    params = clip.to_insert_params()
                    columns = list(params.keys())
                    cursor.execute(
                        "INSERT INTO timeline_clips ({0}) VALUES ({1})".format(
                            ", ".join(columns), ", ".join("?" for _ in columns)
                        ),
                        tuple(params[column] for column in columns),
                    )
                cursor.execute(
                    "UPDATE creative_projects SET timeline_version = "
                    "COALESCE(timeline_version, 0) + 1, updated_at = ? WHERE id = ?",
                    (now, shot.creative_project_id),
                )
                cursor.execute(
                    "SELECT timeline_version FROM creative_projects WHERE id = ?",
                    (shot.creative_project_id,),
                )
                timeline_version = cursor.fetchone()["timeline_version"]
            timeline_updated = True
        return json_success({
            "selected_asset_id": asset.id,
            "selection_source": source,
            "timeline_updated": timeline_updated,
            "timeline_version": timeline_version,
            "requires_recompose": timeline_updated,
        }, message="视频版本已选择")

    @app.route("/api/creative/projects/<project_id>/exports", methods=["POST"])
    def export_project(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_EXPORT,
            created_by=user.get("id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="导出任务已创建", status_code=201)

    # ── Task Management ──

    @app.route("/api/creative/tasks/<task_id>", methods=["GET"])
    def get_creative_task(task_id):
        task = require_task(task_id, demo_mode=cfg.DEMO_MODE)
        return json_success(public_task_dict(task, asset_service, task_service))

    @app.route("/api/creative/tasks/<task_id>/cancel", methods=["POST"])
    def cancel_creative_task(task_id):
        require_task(task_id, write=True, demo_mode=cfg.DEMO_MODE)
        success = task_service.cancel_task(task_id)
        if not success:
            return json_error("cancel_failed", "取消失败，任务不存在或已完成", status_code=400)
        return json_success({"cancelled": True}, message="任务已取消")

    # ── Artifacts ──

    @app.route("/api/creative/projects/<project_id>/artifacts", methods=["GET"])
    def list_project_artifacts(project_id):
        require_project(project_id, demo_mode=cfg.DEMO_MODE)
        artifacts = task_service.list_artifacts(creative_project_id=project_id)
        items = []
        for artifact in artifacts:
            item = artifact.to_dict()
            item.pop("file_path", None)
            if artifact.asset_id:
                item["file_url"] = "/api/assets/{0}/file".format(artifact.asset_id)
                item["download_url"] = "/api/assets/{0}/download".format(artifact.asset_id)
            elif artifact.metadata and artifact.metadata.get("download_url"):
                item["download_url"] = artifact.metadata.get("download_url")
            items.append(item)
        return json_success(items)

    @app.route("/api/creative/tasks/<task_id>/export/download", methods=["GET"])
    def download_export_package(task_id):
        require_task(task_id, demo_mode=cfg.DEMO_MODE)
        from .database import get_database
        row = get_database().fetch_one(
            "SELECT * FROM export_packages WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        if not row:
            raise ApiError("export_not_found", "导出包不存在", status_code=404)
        path = os.path.realpath(row.get("file_path") or "")
        base = os.path.realpath(os.path.join(cfg.DATA_DIR, "exports"))
        if not path.startswith(base + os.sep) or not os.path.isfile(path):
            raise ApiError("export_not_found", "导出文件不存在", status_code=404)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    # ── Workflow / final output ──

    def _final_video_summary(project):
        if not project.final_video_asset_id:
            return None
        asset = asset_service.get_asset(project.final_video_asset_id)
        if not asset:
            return None
        path = asset_service.get_file_path_for_asset(asset)
        if not path:
            return None
        metadata = asset.metadata or {}

        def _safe_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        task = task_service.get_task(project.final_compose_task_id) if project.final_compose_task_id else None
        subtitle_asset_id = None
        if task:
            subtitle_row = project_service.db.fetch_one(
                "SELECT asset_id FROM task_artifacts WHERE task_id = ? "
                "AND artifact_type = 'subtitle' ORDER BY created_at DESC LIMIT 1",
                (task.id,),
            )
            subtitle_asset_id = subtitle_row["asset_id"] if subtitle_row else None
        return {
            "asset": asset_service.public_dict(asset, viewer=current_user()),
            "task_id": task.id if task else None,
            "timeline_version": project.final_timeline_version,
            "current_timeline_version": project.timeline_version,
            "up_to_date": (
                int(project.final_timeline_version or -1)
                == int(project.timeline_version or 0)
            ),
            "duration_s": asset.duration_s or metadata.get("duration_s"),
            "width": _safe_int(metadata.get("width")),
            "height": _safe_int(metadata.get("height")),
            "fps": _safe_int(metadata.get("fps")),
            "file_size": asset.file_size,
            "subtitle_asset_id": subtitle_asset_id,
            "download_url": asset_service.public_dict(
                asset, viewer=current_user()
            ).get("download_url"),
            "created_at": asset.created_at,
        }

    @app.route("/api/creative/projects/<project_id>/final-video", methods=["GET"])
    def get_final_video(project_id):
        project = require_project(project_id, demo_mode=cfg.DEMO_MODE)
        summary = _final_video_summary(project)
        if not summary:
            raise ApiError("final_video_not_found", "项目还没有最终成片", status_code=404)
        return json_success(summary)

    @app.route("/api/creative/projects/<project_id>/workflow", methods=["GET"])
    def get_project_workflow(project_id):
        project = require_project(project_id, demo_mode=cfg.DEMO_MODE)
        shots = storyboard_service.list_shots(project_id)
        timeline = timeline_service.get_timeline(
            project_id, ensure=False, user=current_user()
        )
        video_clips = []
        for item in timeline.get("tracks") or []:
            track = item.get("track") or {}
            if track.get("role") == "video" or track.get("track_type") == "video":
                video_clips.extend([
                    clip for clip in (item.get("clips") or [])
                    if not clip.get("muted")
                ])
        with_image = [shot for shot in shots if shot.primary_image_asset_id]
        with_video = [
            shot for shot in shots
            if shot.selected_video_asset_id or shot.video_asset_id
        ]
        with_refined = [
            shot for shot in shots if shot.refined_video_asset_id
        ]
        final_summary = _final_video_summary(project)
        steps = [
            {
                "step": 1,
                "complete": bool(shots or (project.concept or "").strip()),
                "details": {"shots": len(shots)},
            },
            {
                "step": 2,
                "complete": bool(shots) and len(with_image) == len(shots),
                "details": {"with_image": len(with_image), "shots": len(shots)},
            },
            {
                "step": 3,
                "complete": bool(shots) and len(with_video) == len(shots),
                "details": {"with_video": len(with_video), "shots": len(shots)},
            },
            {
                "step": 4,
                "complete": bool(video_clips) and timeline_service.timeline_ready(project_id),
                "details": {
                    "timeline_version": timeline.get("timeline_version"),
                    "video_clips": len(video_clips),
                    "ready": timeline_service.timeline_ready(project_id),
                },
            },
            {
                "step": 5,
                "optional": True,
                "complete": bool(with_refined),
                "details": {"refined_versions": len(with_refined)},
            },
            {
                "step": 6,
                "complete": bool(final_summary),
                "details": {
                    "final_video_asset_id": project.final_video_asset_id,
                    "up_to_date": final_summary.get("up_to_date") if final_summary else False,
                },
            },
        ]
        next_step = None
        for item in steps[:4]:
            if not item["complete"]:
                next_step = item["step"]
                break
        if next_step is None:
            next_step = 6 if not (final_summary and final_summary["up_to_date"]) else 6

        active_rows = project_service.db.fetch_all(
            "SELECT id, task_type, status, stage, progress, created_at, updated_at "
            "FROM generation_tasks WHERE creative_project_id = ? "
            "AND status IN ('queued','submitting','running') "
            "ORDER BY created_at ASC LIMIT 20",
            (project_id,),
        )
        registry = TTSVoiceRegistry(cfg)
        voices = registry.list_voices()
        return json_success({
            "steps": steps,
            "next_step": next_step,
            "active_tasks": [dict(row) for row in active_rows],
            "timeline": {
                "exists": bool(timeline.get("tracks")),
                "version": timeline.get("timeline_version"),
                "duration_s": timeline.get("duration_s"),
            },
            "final_video": final_summary,
            "capabilities": {
                "ffmpeg": cfg.has_ffmpeg_configured(),
                "ffprobe": bool(shutil.which(getattr(cfg, "FFPROBE_BIN", "ffprobe"))),
                "piper": any(voice.get("available") for voice in voices),
                "tts_voices": len([v for v in voices if v.get("available")]),
                "subtitle_burn": bool(shutil.which("fc-match")) and bool(
                    cfg.has_ffmpeg_configured()
                ),
            },
        })

    @app.route("/api/creative/projects/<project_id>/tasks", methods=["GET"])
    def list_project_creative_tasks(project_id):
        require_project(project_id, demo_mode=cfg.DEMO_MODE)
        task_type = request.args.get("task_type")
        status = request.args.get("status")
        active = request.args.get("active") in ("1", "true", "yes")
        try:
            limit = min(100, max(1, int(request.args.get("limit") or 50)))
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "limit 必须是整数", status_code=400)
        conditions = ["creative_project_id = ?"]
        params = [project_id]
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if active:
            conditions.append("status IN ('queued','submitting','running')")
        rows = project_service.db.fetch_all(
            "SELECT * FROM generation_tasks WHERE {0} "
            "ORDER BY created_at DESC LIMIT ?".format(" AND ".join(conditions)),
            tuple(params) + (limit,),
        )
        return json_success(public_task_dicts(
            [GenerationTask.from_row(row) for row in rows],
            asset_service, task_service,
        ))

    @app.route("/api/creative/audio/presets", methods=["GET"])
    def list_audio_presets():
        current_user()
        role = request.args.get("role", "music")
        if role not in ("music", "sfx"):
            raise ApiError("invalid_params", "role 必须是 music 或 sfx", status_code=400)
        manifest_path = getattr(cfg, "PRESET_AUDIO_MANIFEST", "")
        if not manifest_path or not os.path.isfile(manifest_path):
            return json_success({"items": [], "source": "preset"})
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            raise ApiError("invalid_preset_manifest", "预设音频清单无效", status_code=500)
        items = []
        for entry in data.get("items") or []:
            if entry.get("role") != role:
                continue
            asset_id = entry.get("asset_id")
            if not asset_id:
                continue
            asset = asset_service.get_asset(asset_id)
            if not asset or asset.asset_type != "audio":
                continue
            if not asset_service.get_file_path_for_asset(asset):
                continue
            items.append({
                "id": asset.id,
                "name": entry.get("name") or asset.name,
                "license": entry.get("license"),
                "asset": asset_service.public_dict(asset, viewer=current_user()),
            })
        return json_success({"items": items, "source": "preset"})

    @app.route("/api/creative/capabilities", methods=["GET"])
    def get_creative_capabilities():
        current_user()
        registry = TTSVoiceRegistry(cfg)
        voices = registry.list_voices()
        return json_success({
            "ffmpeg": cfg.has_ffmpeg_configured(),
            "ffprobe": bool(shutil.which(getattr(cfg, "FFPROBE_BIN", "ffprobe"))),
            "piper": any(voice.get("available") for voice in voices),
            "tts_voice_count": len([v for v in voices if v.get("available")]),
            "subtitle_burn": bool(shutil.which("fc-match")) and bool(
                cfg.has_ffmpeg_configured()
            ),
        })

    # ── Timeline ──

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["GET"])
    def get_project_timeline(project_id):
        ensure = request.args.get("ensure") in ("1", "true", "yes")
        if ensure:
            require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        else:
            require_project(project_id, demo_mode=cfg.DEMO_MODE)
        return json_success(
            timeline_service.get_timeline(
                project_id, ensure=ensure, user=current_user()
            )
        )

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["PUT"])
    def save_project_timeline(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
        result = timeline_service.save_timeline(
            project_id, data, user=current_user()
        )
        return json_success(result, message="时间线已保存")

    @app.route("/api/creative/projects/<project_id>/timeline/sync", methods=["POST"])
    def sync_project_timeline(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        result = timeline_service.sync_from_shots(project_id, user=current_user())
        return json_success(result, message="时间线已同步分镜视频")

    @app.route("/api/creative/projects/<project_id>/subtitles", methods=["GET"])
    def download_project_subtitles(project_id):
        require_project(project_id, demo_mode=cfg.DEMO_MODE)
        timeline = timeline_service.get_timeline(
            project_id, ensure=False, user=current_user()
        )
        content = timeline_service.build_srt_from_timeline(timeline)
        if request.args.get("download") in ("1", "true", "yes"):
            from flask import Response
            return Response(
                content,
                mimetype="application/x-subrip",
                headers={"Content-Disposition": "attachment; filename=subtitles.srt"},
            )
        return json_success({
            "srt": content,
            "timeline_version": timeline.get("timeline_version"),
        })
