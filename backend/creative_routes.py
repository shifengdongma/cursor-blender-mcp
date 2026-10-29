# -*- coding: utf-8 -*-
"""
Creative Production API routes for AIGV Studio.
"""
from __future__ import absolute_import

import os

from flask import g, request, send_file

from .access import current_user, require_project, require_shot, require_task
from .asset_service import get_asset_service
from .auth_middleware import is_admin
from .creative_project_service import get_creative_project_service
from .credential_service import CredentialService
from .generation_models import list_models
from .generation_service import create_generation_task
from .http_utils import ApiError, parse_json_body, parse_pagination, require_fields
from .models import CreativeProject, GenerationTask, ExportPackage, TimelineTrack, TimelineClip
from .storyboard_service import get_storyboard_service
from .task_service import get_task_service
from .task_serializer import public_task_dict


def register_creative_routes(app, cfg, json_success, json_error):
    """Register all creative production API routes."""

    project_service = get_creative_project_service(cfg.DATA_DIR)
    storyboard_service = get_storyboard_service(cfg.DATA_DIR)
    task_service = get_task_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)

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
        data = parse_json_body(request)
        shot = storyboard_service.create_shot(project_id, **data)
        return json_success(shot.to_dict(), message="分镜已添加", status_code=201)

    @app.route("/api/creative/shots/<shot_id>", methods=["PUT"])
    def update_storyboard_shot(shot_id):
        require_shot(shot_id, write=True, demo_mode=cfg.DEMO_MODE)
        data = parse_json_body(request)
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
                "size": data.get("size") or data.get("resolution") or "2K",
                "seed": data.get("seed"),
                "negative_prompt": data.get("negative_prompt") or shot.negative_prompt,
                "reference_asset_id": data.get("reference_asset_id"),
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
                "generate_audio": data.get("generate_audio", False),
                "watermark": data.get("watermark", False),
                "seed": data.get("seed"),
                "reference_asset_id": reference_asset_id,
                "client_request_id": data.get("client_request_id"),
            },
            project_id=shot.creative_project_id,
            shot_id=shot_id,
            client_request_id=data.get("client_request_id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="视频生成任务已创建", status_code=201)

    @app.route("/api/creative/projects/<project_id>/tts", methods=["POST"])
    def generate_project_tts(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)

        user = current_user()
        capacity_error = _legacy_capacity_error(user)
        if capacity_error:
            return capacity_error
        if not cfg.has_piper_configured():
            return json_error("provider_not_configured", "TTS 语音合成服务未配置", status_code=400)

        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_TTS,
            created_by=user.get("id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="TTS 生成任务已创建", status_code=201)

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
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_COMPOSE,
            params={
                "width": data.get("width", 1920),
                "height": data.get("height", 1080),
                "fps": data.get("fps", 24),
            },
            created_by=user.get("id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="视频合成任务已创建", status_code=201)

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
        # Stage A: do not accept arbitrary server paths.  Stage C wires an owned
        # input_asset_id; keep the legacy field rejected explicitly.
        if data.get("input_path"):
            return json_error("invalid_params", "不再接受服务器文件路径，请使用 input_asset_id", status_code=400)
        require_fields(data, ["input_asset_id"])
        from .access import require_asset

        asset = require_asset(data["input_asset_id"], write=False, demo_mode=cfg.DEMO_MODE)
        task = task_service.create_task(
            creative_project_id=project_id,
            task_type=GenerationTask.TYPE_REFINE,
            params={"input_asset_id": asset.id, "filters": data.get("filters") or {}},
            created_by=user.get("id"),
        )

        return json_success(public_task_dict(task, asset_service, task_service), message="视频精修任务已创建", status_code=201)

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

    # ── Timeline ──

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["GET"])
    def get_project_timeline(project_id):
        require_project(project_id, demo_mode=cfg.DEMO_MODE)
        from .database import get_database
        db = get_database()

        tracks = db.fetch_all(
            "SELECT * FROM timeline_tracks WHERE creative_project_id = ? ORDER BY sequence_no ASC",
            (project_id,),
        )

        result = []
        for track_row in tracks:
            track = TimelineTrack.from_row(track_row)
            clips = db.fetch_all(
                "SELECT * FROM timeline_clips WHERE track_id = ? ORDER BY start_time ASC",
                (track.id,),
            )
            result.append({
                "track": track.to_dict(),
                "clips": [TimelineClip.from_row(c).to_dict() for c in clips],
            })

        return json_success(result)

    @app.route("/api/creative/projects/<project_id>/timeline", methods=["PUT"])
    def save_project_timeline(project_id):
        require_project(project_id, write=True, demo_mode=cfg.DEMO_MODE)
        from .database import get_database
        db = get_database()
        data = parse_json_body(request)
        tracks_data = data.get("tracks") or []

        # Delete existing tracks/clips for this project
        db.delete("timeline_clips", "creative_project_id = ?", (project_id,))
        db.delete("timeline_tracks", "creative_project_id = ?", (project_id,))

        for track_data in tracks_data:
            track = TimelineTrack(
                creative_project_id=project_id,
                name=track_data.get("name", "Track"),
                track_type=track_data.get("track_type", "video"),
                sequence_no=track_data.get("sequence_no", 0),
                settings=track_data.get("settings"),
            )
            db.insert("timeline_tracks", track.to_insert_params())

            clips_data = track_data.get("clips") or []
            for clip_data in clips_data:
                clip = TimelineClip(
                    track_id=track.id,
                    creative_project_id=project_id,
                    shot_id=clip_data.get("shot_id"),
                    asset_id=clip_data.get("asset_id"),
                    name=clip_data.get("name", "Clip"),
                    start_time=clip_data.get("start_time", 0),
                    duration_s=clip_data.get("duration_s", 0),
                    trim_in=clip_data.get("trim_in", 0),
                    trim_out=clip_data.get("trim_out"),
                    properties=clip_data.get("properties"),
                )
                db.insert("timeline_clips", clip.to_insert_params())

        return json_success({"saved": True}, message="时间线已保存")
