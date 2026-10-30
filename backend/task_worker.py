# -*- coding: utf-8 -*-
"""
Background task worker for creative production pipeline.
Daemon thread pattern: claim → execute → update status.
"""
from __future__ import absolute_import

import hashlib
import json
import logging
import os
import subprocess
import threading
import time

from .access import can_read_asset
from .asset_service import get_asset_service
from .config import Config
from .creative_project_service import get_creative_project_service
from .credential_service import CredentialError, CredentialService
from .media_service import get_media_service, probe_media_file, MediaServiceError
from .models import (
    Asset, CreativeProject, ExportPackage, GenerationTask, ShotMediaVersion,
    StoryboardShot, TaskArtifact,
)
from .providers.base import ProviderError
from .providers.llm_provider import LLMProvider
from .providers.image_provider import ComfyUIProvider
from .providers.tts_provider import PiperTTSProvider
from .provider_router import ProviderRouter
from .storyboard_service import get_storyboard_service
from .task_service import get_task_service
from .timeline_service import TimelineService, get_timeline_service
from .tts_service import TTSVoiceRegistry

logger = logging.getLogger(__name__)

# Schema for LLM storyboard generation
STORYBOARD_SCHEMA = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_title": {"type": "string"},
                    "scene_description": {"type": "string"},
                    "shot_type": {"type": "string"},
                    "duration_s": {"type": "number"},
                    "dialogue": {"type": "string"},
                    "camera_movement": {"type": "string"},
                    "lighting_mood": {"type": "string"},
                    "environment_detail": {"type": "string"},
                    "character_action": {"type": "string"},
                    "visual_style": {"type": "string"},
                    "prompt_cn": {"type": "string"},
                    "prompt_en": {"type": "string"},
                },
                "required": ["scene_title", "scene_description", "shot_type", "duration_s"]
            }
        }
    },
    "required": ["shots"],
}


def _build_storyboard_prompt(project):
    """Build prompts for LLM storyboard generation."""
    concept = project.concept or ""
    genre = project.genre or "promotional"
    requirements = project.requirements or {}
    creative_brief = project.creative_brief or {}

    system_prompt = (
        "You are an expert storyboard artist and video director. "
        "Generate a detailed storyboard in valid JSON format based on the project description. "
        "Each shot must include: scene_title, scene_description, shot_type (close_up/medium/wide/establishing/detail/tracking), "
        "duration_s (2-10 seconds), dialogue (narration text if any), camera_movement, lighting_mood, "
        "environment_detail, character_action, visual_style, prompt_cn (Chinese video prompt), "
        "and prompt_en (English video prompt). "
        "Output ONLY valid JSON, no markdown."
    )

    user_prompt = (
        "Create a storyboard for the following project:\n"
        "Genre: {genre}\n"
        "Concept: {concept}\n"
        "Requirements: {requirements}\n"
        "Creative Brief: {brief}\n"
        "\nGenerate 5-10 sequential shots that tell a compelling story."
    ).format(
        genre=genre,
        concept=concept,
        requirements=json.dumps(requirements, ensure_ascii=False),
        brief=json.dumps(creative_brief, ensure_ascii=False),
    )

    return system_prompt, user_prompt


# ── Executors ──


def _owned_asset_fields(task, db):
    """Assets created by a legacy executor belong to the task creator.

    Without this, ``create_asset`` produced ownerless rows that every user
    could read (the legacy "shared library" semantics), leaking composed
    videos and narrations across tenants.
    """
    row = db.fetch_one(
        "SELECT tenant_id FROM auth_users WHERE id = ?", (task.created_by,)
    ) if task.created_by else None
    return {
        "owner_user_id": task.created_by,
        "tenant_id": row["tenant_id"] if row else None,
        "visibility": "private",
    }


def _project_asset_fields(db, task):
    """Project-scoped outputs belong to the project owner, not the admin who
    happened to click the button.  Falls back to the task creator."""
    project = db.fetch_one(
        "SELECT user_id, tenant_id FROM creative_projects WHERE id = ?",
        (task.creative_project_id,),
    )
    if project and project.get("user_id"):
        return {
            "owner_user_id": project["user_id"],
            "tenant_id": project.get("tenant_id"),
            "visibility": "private",
        }
    return _owned_asset_fields(task, db)


def _raise_if_cancelled(task_service, task_id):
    fresh = task_service.get_task(task_id)
    if not fresh or fresh.status == GenerationTask.STATUS_CANCELLED or fresh.cancel_requested:
        raise ProviderError("任务已取消", error_type="task_cancelled")


def _task_user(db, task):
    if not task.created_by:
        return {}
    row = db.fetch_one("SELECT * FROM auth_users WHERE id = ?", (task.created_by,))
    if not row:
        return {}
    return {
        "id": row["id"],
        "tenant_id": row.get("tenant_id"),
        "role": row.get("role") or "user",
        "status": row.get("status") or "active",
    }


def _insert_row(cursor, table, params):
    columns = list(params.keys())
    cursor.execute(
        "INSERT INTO {0} ({1}) VALUES ({2})".format(
            table,
            ", ".join(columns),
            ", ".join("?" for _ in columns),
        ),
        tuple(params[column] for column in columns),
    )


def _resolve_compose_inputs(cfg, db, task, snapshot):
    """Resolve snapshot asset IDs to safe local paths and stream metadata."""
    asset_service = get_asset_service(cfg.DATA_DIR)
    user = _task_user(db, task)
    resolved = {}
    for item in snapshot.get("tracks") or []:
        track = item.get("track") or {}
        role = track.get("role")
        if not role:
            if track.get("track_type") == "video":
                role = "video"
            elif track.get("track_type") == "subtitle":
                role = "subtitle"
        if role == "subtitle":
            continue
        expected_type = "video" if role == "video" else "audio"
        for clip in item.get("clips") or []:
            asset_id = clip.get("asset_id")
            if not asset_id or asset_id in resolved:
                continue
            asset = asset_service.get_asset(asset_id)
            if not asset:
                raise ProviderError(
                    "时间线引用的素材不存在：{0}".format(asset_id),
                    error_type="compose_asset_missing",
                )
            if user and not can_read_asset(
                asset, user, demo_mode=getattr(cfg, "DEMO_MODE", False)
            ):
                raise ProviderError(
                    "无权使用时间线引用的素材",
                    error_type="compose_asset_forbidden",
                )
            if asset.asset_type != expected_type:
                raise ProviderError(
                    "素材类型与轨道不匹配：{0}".format(asset_id),
                    error_type="compose_asset_type_mismatch",
                )
            path = asset_service.get_file_path_for_asset(asset)
            if not path:
                raise ProviderError(
                    "素材文件缺失：{0}".format(asset_id),
                    error_type="compose_asset_file_missing",
                )
            try:
                info = probe_media_file(cfg.FFPROBE_BIN, path)
            except MediaServiceError as exc:
                raise ProviderError(
                    "素材无法探测：{0}".format(str(exc)),
                    error_type="compose_asset_probe_failed",
                )
            resolved[asset_id] = {
                "path": path,
                "has_audio": bool(info.get("has_audio")),
                "duration_s": float(info.get("duration_s") or 0.0),
            }
    return resolved, user


def _execute_storyboard(task, cfg, db):
    """Execute storyboard generation via LLM."""
    task_service = get_task_service()
    project_service = get_creative_project_service()
    storyboard_service = get_storyboard_service()

    task_service.update_task(task.id, stage="generating", progress=10)

    project = project_service.get_project(task.creative_project_id)
    if not project:
        raise ProviderError("Project not found: {0}".format(task.creative_project_id), error_type="project_not_found")

    # Resolve the credentials pinned when the task was created (user first,
    # platform fallback) *before* marking the project as analyzing, so a
    # missing/invalid credential can never strand the project in that state.
    credential_service = CredentialService(cfg.DATA_DIR, cfg)
    eff = credential_service.effective(
        task.created_by,
        "llm",
        cfg,
        prefer_source=(task.params or {}).get("credential_source"),
    )
    if not eff.get("source") or not eff.get("api_key"):
        raise ProviderError(
            "LLM 凭据不可用，请在 API 配置页重新配置",
            error_type="llm_missing_key",
        )

    base_url = eff.get("base_url") or cfg.LLM_BASE_URL
    if eff.get("source") == "user":
        # Re-resolve right before the request (DNS rebinding defence).
        try:
            base_url = credential_service.validate_base_url(base_url, cfg)
        except CredentialError:
            raise ProviderError(
                "LLM Base URL 未通过安全校验，请在 API 配置页重新配置",
                error_type="llm_missing_key",
            )

    llm = LLMProvider(
        api_key=eff["api_key"],
        base_url=base_url,
        model_name=eff.get("model") or cfg.LLM_MODEL_NAME,
    )

    # Credentials and endpoint are known-good: now the project is analyzing.
    project_service.update_project(task.creative_project_id, status=CreativeProject.STATUS_ANALYZING)

    task_service.update_task(task.id, progress=30)

    system_prompt, user_prompt = _build_storyboard_prompt(project)

    result = llm.generate_structured(system_prompt, user_prompt, STORYBOARD_SCHEMA)
    shots_data = result.get("shots") or []

    task_service.update_task(task.id, progress=60)

    # Insert shots into database
    for shot_data in shots_data:
        storyboard_service.create_shot(task.creative_project_id, **shot_data)

    task_service.update_task(task.id, progress=90)

    # Update project status
    project_service.update_project(task.creative_project_id, status=CreativeProject.STATUS_READY)

    task_service.update_task(task.id, progress=100)
    return {"shots_count": len(shots_data)}


def _execute_image(task, cfg, db):
    """Execute concept image generation via ComfyUI."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)

    task_service.update_task(task.id, stage="generating", progress=10)

    shot_id = task.target_shot_id
    if not shot_id:
        shot = storyboard_service.get_shot(task.target_shot_id)
    else:
        shot = storyboard_service.get_shot(shot_id)

    if not shot:
        raise ProviderError("Shot not found", error_type="shot_not_found")

    provider = ComfyUIProvider(
        base_url=cfg.COMFYUI_BASE_URL,
        workflow_file=cfg.COMFYUI_WORKFLOW_FILE,
    )

    task_service.update_task(task.id, progress=20)

    prompt = shot.prompt_en or shot.prompt_cn or shot.scene_description or ""
    negative = shot.negative_prompt or ""

    params = task.params or {}
    width = params.get("width", 1024)
    height = params.get("height", 576)
    seed = params.get("seed", -1)

    prompt_id = provider.submit_generation(prompt=prompt, negative_prompt=negative, seed=seed, width=width, height=height, quantity=1)

    task_service.update_task(task.id, progress=40)

    # Download results
    output_dir = os.path.join(cfg.DATA_DIR, "assets", "images", "generated")
    file_paths = provider.download_results(prompt_id, output_dir)

    task_service.update_task(task.id, progress=80)

    if file_paths:
        file_path = file_paths[0]
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        # Create asset record
        asset = asset_service.create_asset(
            name="{0}_concept".format(shot.scene_title or "shot"),
            asset_type="image",
            file_path=file_path,
            file_size=file_size,
            **_owned_asset_fields(task, db)
        )

        # Update shot with image reference
        storyboard_service.update_shot(shot.id, primary_image_asset_id=asset.id, status=StoryboardShot.STATUS_READY)

        task_service.update_task(task.id, progress=100)

        return {"asset_id": asset.id, "file_path": file_path}
    else:
        raise ProviderError("No images generated", error_type="comfyui_empty_output")


def _execute_video(task, cfg, db):
    """Execute video generation via existing ProviderRouter (Seedance/Luma)."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()

    task_service.update_task(task.id, stage="generating", progress=10)

    shot = storyboard_service.get_shot(task.target_shot_id) if task.target_shot_id else None

    task_service.update_task(task.id, progress=20)

    prompt = ""
    if shot:
        prompt = shot.prompt_en or shot.prompt_cn or shot.scene_description or ""
    else:
        prompt = (task.params or {}).get("prompt") or "Cinematic scene, high quality"

    router = ProviderRouter(cfg)

    # Build a minimal prompt bundle
    prompt_bundle = {"prompt": prompt, "negative_prompt": shot.negative_prompt if shot else None}
    duration_s = int(shot.duration_s) if shot and shot.duration_s else 4
    execution_provider = (task.params or {}).get("execution_provider") or "seedance"
    if not cfg.SEEDANCE_API_KEY and not cfg.LUMA_API_KEY:
        execution_provider = "seedance"

    task_service.update_task(task.id, progress=40)

    try:
        provider, created, provider_job_id = router.submit_generation(
            execution_provider=execution_provider,
            prompt_bundle=prompt_bundle,
            duration_s=duration_s,
        )
    except Exception as e:
        raise ProviderError("Video submission failed: {0}".format(str(e)), error_type="video_submission_failed")

    task_service.update_task(task.id, progress=60)

    try:
        done = router.wait_until_done(
            execution_provider=execution_provider,
            provider=provider,
            provider_job_id=provider_job_id,
        )
    except Exception as e:
        raise ProviderError("Video generation failed: {0}".format(str(e)), error_type="video_generation_failed")

    video_url = provider.extract_video_url(done)

    task_service.update_task(task.id, progress=90)

    if video_url:
        if shot:
            storyboard_service.update_shot(shot.id, video_url=video_url, status=StoryboardShot.STATUS_READY)

        task_service.update_task(task.id, progress=100)
        return {"video_url": video_url, "provider_job_id": provider_job_id}
    else:
        raise ProviderError("No video URL in response", error_type="video_empty_output")


def _sha256_file(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _srt_timestamp(seconds):
    seconds = max(0.0, float(seconds))
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole_seconds, millis = divmod(remainder, 1000)
    return "{0:02d}:{1:02d}:{2:02d},{3:03d}".format(
        hours, minutes, whole_seconds, millis
    )


def _write_shot_srt(path, text, duration_s):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = (
        "1\n{0} --> {1}\n{2}\n\n".format(
            _srt_timestamp(0), _srt_timestamp(duration_s), text.strip()
        )
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return content


def _record_media_version(db, task, shot, kind, asset, source, label,
                          metadata, selected=True, clear_selection=True):
    if clear_selection:
        db.update(
            "shot_media_versions",
            {"is_selected": 0, "updated_at": int(time.time())},
            "shot_id = ? AND media_kind = ?",
            (shot.id, kind),
        )
    version = ShotMediaVersion(
        creative_project_id=task.creative_project_id,
        shot_id=shot.id,
        media_kind=kind,
        asset_id=asset.id,
        task_id=task.id,
        source=source,
        label=label,
        metadata=metadata,
        is_selected=1 if selected else 0,
    )
    db.insert("shot_media_versions", version.to_insert_params())
    return version


def _execute_tts(task, cfg, db):
    """Generate real per-shot narration with history, metadata and SRT."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)

    task_service.update_task(task.id, stage="generating", progress=10)
    _raise_if_cancelled(task_service, task.id)

    params = task.params or {}
    shots = storyboard_service.list_shots(task.creative_project_id)
    requested_ids = params.get("shot_ids") or []
    if requested_ids:
        by_id = {shot.id: shot for shot in shots}
        missing = [shot_id for shot_id in requested_ids if shot_id not in by_id]
        if missing:
            raise ProviderError(
                "分镜不属于当前项目：{0}".format(", ".join(missing)),
                error_type="tts_shot_not_found",
            )
        targets = [by_id[shot_id] for shot_id in requested_ids]
    else:
        targets = shots

    mode = params.get("mode") or "all"
    if mode not in ("all", "missing"):
        raise ProviderError("不支持的 TTS 模式", error_type="invalid_tts_mode")
    if mode == "missing":
        targets = [shot for shot in targets if not shot.audio_asset_id]

    explicit_text = (params.get("text") or "").strip()
    if explicit_text and len(targets) != 1:
        raise ProviderError(
            "为单个分镜指定文案时只能选择一个分镜",
            error_type="invalid_tts_params",
        )

    registry = TTSVoiceRegistry(cfg)
    voice = None
    requested_voice_id = params.get("voice_id")
    try:
        voices = registry.list_voices()
        if voices:
            voice = registry.resolve_voice(requested_voice_id)
    except ProviderError:
        if requested_voice_id:
            raise
    voice_id = voice["id"] if voice else requested_voice_id
    voice_label = voice["label"] if voice else None

    tts_provider = PiperTTSProvider(
        piper_bin=cfg.PIPER_BIN,
        piper_model_path=cfg.PIPER_MODEL_PATH,
        ffprobe_bin=cfg.FFPROBE_BIN,
        ffmpeg_bin=cfg.FFMPEG_BIN,
        registry=registry,
    )
    options = {
        "speech_rate": params.get("speech_rate", 1.0),
        "volume": params.get("volume", 1.0),
    }

    audio_root = os.path.join(
        cfg.DATA_DIR, "assets", "audio", "generated", str(task.id)
    )
    subtitle_root = os.path.join(
        cfg.DATA_DIR, "assets", "subtitles", "generated", str(task.id)
    )
    os.makedirs(audio_root, exist_ok=True)
    os.makedirs(subtitle_root, exist_ok=True)

    audio_assets = []
    total_duration = 0.0
    skipped = 0
    asset_fields = _project_asset_fields(db, task)

    for index, shot in enumerate(targets):
        _raise_if_cancelled(task_service, task.id)
        text = explicit_text or (shot.dialogue or "").strip()
        if not text:
            skipped += 1
            continue

        output_path = os.path.join(audio_root, "shot_{0}.wav".format(shot.id))
        result = tts_provider.synthesize(
            text, voice_id, output_path, options=options
        )
        duration_s = float(result.get("duration_s") or 0.0)
        if duration_s <= 0:
            raise ProviderError(
                "TTS 没有返回有效音频时长", error_type="tts_invalid_audio"
            )

        metadata = {
            "source": "tts",
            "task_id": task.id,
            "project_id": task.creative_project_id,
            "shot_id": shot.id,
            "provider": result.get("provider") or "piper",
            "voice_id": result.get("voice_id") or voice_id,
            "voice_label": result.get("voice_label") or voice_label,
            "text": text,
            "speech_rate": result.get("speech_rate", options["speech_rate"]),
            "volume": result.get("volume", options["volume"]),
            "duration_s": duration_s,
            "media_info": result.get("media_info"),
        }
        asset = asset_service.create_asset(
            name="{0}_narration".format(shot.scene_title or "shot_{0}".format(index + 1)),
            asset_type="audio",
            file_path=asset_service.relative_path_for(output_path),
            file_size=os.path.getsize(output_path),
            description=text[:500],
            metadata=metadata,
            duration_s=duration_s,
            audio_role="narration",
            media_info=result.get("media_info"),
            checksum_sha256=_sha256_file(output_path),
            **asset_fields
        )

        srt_path = os.path.join(
            subtitle_root, "shot_{0}.srt".format(shot.id)
        )
        _write_shot_srt(srt_path, text, duration_s)
        subtitle_asset = asset_service.create_asset(
            name="{0}_subtitle".format(shot.scene_title or "shot_{0}".format(index + 1)),
            asset_type="subtitle",
            file_path=asset_service.relative_path_for(srt_path),
            file_size=os.path.getsize(srt_path),
            description=text[:500],
            metadata={
                "source": "tts",
                "task_id": task.id,
                "project_id": task.creative_project_id,
                "shot_id": shot.id,
                "timing_method": "audio_duration",
                "duration_s": duration_s,
            },
            checksum_sha256=_sha256_file(srt_path),
            **asset_fields
        )

        audio_options = {
            "provider": result.get("provider") or "piper",
            "voice_id": result.get("voice_id") or voice_id,
            "voice_label": result.get("voice_label") or voice_label,
            "speech_rate": result.get("speech_rate", options["speech_rate"]),
            "volume": result.get("volume", options["volume"]),
            "text": text,
            "duration_s": duration_s,
            "task_id": task.id,
            "subtitle_asset_id": subtitle_asset.id,
        }
        storyboard_service.update_shot(
            shot.id,
            audio_asset_id=asset.id,
            subtitle_asset_id=subtitle_asset.id,
            audio_options=audio_options,
            audio_duration_s=duration_s,
            srt_path=srt_path,
            voice_id=audio_options["voice_id"],
        )
        _record_media_version(
            db, task, shot, "audio", asset, "tts",
            audio_options.get("voice_label") or "TTS 配音",
            audio_options,
        )
        _record_media_version(
            db, task, shot, "subtitle", subtitle_asset, "tts",
            "分镜字幕",
            {"task_id": task.id, "timing_method": "audio_duration"},
        )
        try:
            get_timeline_service(cfg).sync_shot_media(
                task.creative_project_id,
                shot.id,
                audio_asset_id=asset.id,
                audio_duration_s=duration_s,
                audio_options=audio_options,
                subtitle_text=text,
                subtitle_duration_s=duration_s,
            )
        except Exception:
            logger.warning(
                "Could not sync TTS result into timeline for shot %s",
                shot.id, exc_info=True,
            )

        task_service.add_artifact(
            task_id=task.id,
            creative_project_id=task.creative_project_id,
            name=os.path.basename(output_path),
            artifact_type=TaskArtifact.TYPE_AUDIO,
            file_path=os.path.relpath(output_path, cfg.DATA_DIR),
            file_size=os.path.getsize(output_path),
            asset_id=asset.id,
            metadata={
                "shot_id": shot.id,
                "voice_id": audio_options["voice_id"],
                "duration_s": duration_s,
            },
        )
        task_service.add_artifact(
            task_id=task.id,
            creative_project_id=task.creative_project_id,
            name=os.path.basename(srt_path),
            artifact_type="subtitle",
            file_path=os.path.relpath(srt_path, cfg.DATA_DIR),
            file_size=os.path.getsize(srt_path),
            asset_id=subtitle_asset.id,
            metadata={"shot_id": shot.id, "timing_method": "audio_duration"},
        )

        audio_assets.append({
            "shot_id": shot.id,
            "asset_id": asset.id,
            "subtitle_asset_id": subtitle_asset.id,
            "duration_s": duration_s,
            "voice_id": audio_options["voice_id"],
        })
        total_duration += duration_s

        progress = 20 + int((index + 1) / max(len(targets), 1) * 70)
        task_service.update_task(task.id, progress=progress)

    first_asset_id = audio_assets[0]["asset_id"] if audio_assets else None
    task_service.update_task(
        task.id, progress=100, output_asset_id=first_asset_id
    )
    return {
        "audio_assets": audio_assets,
        "total_duration_s": total_duration,
        "skipped": skipped,
        "voice_id": voice_id,
    }


def _execute_compose(task, cfg, db):
    """Compose the task's saved timeline snapshot into a verified MP4."""
    task_service = get_task_service()
    project_service = get_creative_project_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)

    task_service.update_task(task.id, stage="composing", progress=5)
    _raise_if_cancelled(task_service, task.id)
    snapshot = task.timeline_snapshot
    if not snapshot or not snapshot.get("tracks"):
        raise ProviderError(
            "合成任务缺少时间线快照", error_type="compose_no_timeline"
        )
    project = project_service.get_project(task.creative_project_id)
    if not project:
        raise ProviderError("项目不存在", error_type="project_not_found")

    inputs, user = _resolve_compose_inputs(cfg, db, task, snapshot)
    settings = dict((task.params or {}).get("export_settings") or {})
    settings["subtitle_mode"] = settings.get("subtitle_mode") or "none"
    settings["subtitle_font_name"] = settings.get(
        "subtitle_font_name", getattr(cfg, "SUBTITLE_FONT_NAME", "Noto Sans CJK SC")
    )
    settings["subtitle_font_size"] = settings.get(
        "subtitle_font_size", getattr(cfg, "SUBTITLE_FONT_SIZE", 24)
    )
    timeline_end = TimelineService.timeline_end(snapshot)
    if timeline_end <= 0:
        raise ProviderError("时间线没有视频内容", error_type="timeline_has_no_video")
    max_duration = int(getattr(cfg, "MAX_COMPOSE_DURATION_S", 900))
    if timeline_end > max_duration:
        raise ProviderError(
            "时间线超过最长合成时长（{0} 秒）".format(max_duration),
            error_type="timeline_too_long",
        )

    output_dir = os.path.join(
        cfg.DATA_DIR, "assets", "videos", "composed", str(task.id)
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "final_video.mp4")

    subtitle_asset_path = None
    subtitle_srt = None
    if settings["subtitle_mode"] in ("burn", "mov_text"):
        subtitle_srt = TimelineService.build_srt_from_timeline(snapshot)
        if not subtitle_srt.strip():
            # A requested subtitle mode with no text silently produces no
            # subtitle asset; never claim subtitles exist when they do not.
            settings["subtitle_mode"] = "none"
        else:
            subtitle_dir = os.path.join(
                cfg.DATA_DIR, "assets", "subtitles", "generated", str(task.id)
            )
            os.makedirs(subtitle_dir, exist_ok=True)
            subtitle_asset_path = os.path.join(subtitle_dir, "subtitles.srt")
            with open(subtitle_asset_path, "w", encoding="utf-8") as handle:
                handle.write(subtitle_srt)
            settings["subtitle_path"] = subtitle_asset_path

    def progress(value):
        task_service.update_task(
            task.id, stage="composing", progress=max(5, min(95, int(value)))
        )

    result = media_service.compose_timeline(
        snapshot, output_path, settings, inputs=inputs, progress_cb=progress
    )
    _raise_if_cancelled(task_service, task.id)
    task_service.update_task(task.id, progress=96)

    owner_user_id = project.user_id or task.created_by
    tenant_id = project.tenant_id or (user or {}).get("tenant_id")
    stored_settings = dict(settings)
    stored_settings.pop("subtitle_path", None)
    now = int(time.time())
    subtitle_asset = None
    try:
        with task_service.db.transaction() as cursor:
            asset = asset_service.create_asset(
                name="{0} 成片".format(project.name or "AIGV"),
                asset_type="video",
                file_path=asset_service.relative_path_for(output_path),
                file_size=os.path.getsize(output_path),
                description="时间线合成成片",
                metadata={
                    "source": "compose",
                    "task_id": task.id,
                    "project_id": project.id,
                    "timeline_version": snapshot.get("timeline_version"),
                    "export_settings": stored_settings,
                    "width": result["width"],
                    "height": result["height"],
                    "fps": result["fps"],
                    "duration_s": result["duration_s"],
                    "subtitle_mode": settings["subtitle_mode"],
                },
                owner_user_id=owner_user_id,
                tenant_id=tenant_id,
                visibility="private",
                checksum_sha256=_sha256_file(output_path),
                duration_s=result["duration_s"],
                media_info=result["media_info"],
                cursor=cursor,
            )
            task_service.add_artifact(
                task_id=task.id,
                creative_project_id=project.id,
                name=os.path.basename(output_path),
                artifact_type=TaskArtifact.TYPE_VIDEO,
                file_path=os.path.relpath(output_path, cfg.DATA_DIR),
                file_size=os.path.getsize(output_path),
                asset_id=asset.id,
                metadata={
                    "timeline_version": snapshot.get("timeline_version"),
                    "width": result["width"],
                    "height": result["height"],
                    "fps": result["fps"],
                    "duration_s": result["duration_s"],
                },
                cursor=cursor,
            )
            subtitle_asset = None
            if subtitle_asset_path and settings["subtitle_mode"] != "none":
                subtitle_asset = asset_service.create_asset(
                    name="{0} 字幕".format(project.name or "AIGV"),
                    asset_type="subtitle",
                    file_path=asset_service.relative_path_for(subtitle_asset_path),
                    file_size=os.path.getsize(subtitle_asset_path),
                    description="最终成片字幕",
                    metadata={
                        "source": "compose",
                        "task_id": task.id,
                        "project_id": project.id,
                        "timeline_version": snapshot.get("timeline_version"),
                        "subtitle_mode": settings["subtitle_mode"],
                    },
                    owner_user_id=owner_user_id,
                    tenant_id=tenant_id,
                    visibility="private",
                    checksum_sha256=_sha256_file(subtitle_asset_path),
                    cursor=cursor,
                )
                task_service.add_artifact(
                    task_id=task.id,
                    creative_project_id=project.id,
                    name=os.path.basename(subtitle_asset_path),
                    artifact_type="subtitle",
                    file_path=os.path.relpath(subtitle_asset_path, cfg.DATA_DIR),
                    file_size=os.path.getsize(subtitle_asset_path),
                    asset_id=subtitle_asset.id,
                    metadata={"timeline_version": snapshot.get("timeline_version")},
                    cursor=cursor,
                )
            result_payload = {
                "video_asset_id": asset.id,
                "subtitle_asset_id": subtitle_asset.id if subtitle_asset else None,
                "duration_s": result["duration_s"],
                "timeline_version": snapshot.get("timeline_version"),
                "width": result["width"],
                "height": result["height"],
                "fps": result["fps"],
            }
            cursor.execute(
                "UPDATE generation_tasks SET output_asset_id = ?, result_payload = ?, "
                "progress = 100, stage = 'composing', updated_at = ? WHERE id = ?",
                (
                    asset.id,
                    json.dumps(result_payload, ensure_ascii=False),
                    now,
                    task.id,
                ),
            )
            cursor.execute(
                "UPDATE creative_projects SET final_video_asset_id = ?, "
                "final_compose_task_id = ?, final_timeline_version = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    asset.id,
                    task.id,
                    snapshot.get("timeline_version"),
                    now,
                    project.id,
                ),
            )
            export_package = ExportPackage(
                id="{0}_mp4".format(task.id),
                creative_project_id=project.id,
                task_id=task.id,
                format=ExportPackage.FORMAT_MP4,
                file_path=output_path,
                file_size=os.path.getsize(output_path),
                status=ExportPackage.STATUS_COMPLETED,
                manifest={
                    "timeline_version": snapshot.get("timeline_version"),
                    "export_settings": stored_settings,
                    "duration_s": result["duration_s"],
                },
                download_url="/api/assets/{0}/download".format(asset.id),
                asset_id=asset.id,
                timeline_version=snapshot.get("timeline_version"),
                created_at=now,
                updated_at=now,
                created_by=task.created_by,
            )
            _insert_row(cursor, "export_packages", export_package.to_insert_params())
    except Exception:
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
        except OSError:
            pass
        raise

    logger.info("Composed timeline for project %s -> %s", project.id, output_path)
    return result_payload


def _execute_refine(task, cfg, db):
    """Apply a real FFmpeg refinement to one shot and keep both versions."""
    task_service = get_task_service()
    project_service = get_creative_project_service(cfg.DATA_DIR)
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)
    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)

    task_service.update_task(task.id, stage="refining", progress=10)
    _raise_if_cancelled(task_service, task.id)
    params = task.params or {}
    shot_id = params.get("shot_id")
    if not shot_id:
        raise ProviderError("精修任务缺少 shot_id", error_type="refine_no_shot")
    shot = storyboard_service.get_shot(shot_id)
    if not shot or shot.creative_project_id != task.creative_project_id:
        raise ProviderError("精修分镜不属于当前项目", error_type="refine_shot_not_found")
    input_asset_id = params.get("input_asset_id") or shot.selected_video_asset_id or shot.video_asset_id
    input_asset = asset_service.get_asset(input_asset_id) if input_asset_id else None
    if not input_asset or input_asset.asset_type != "video":
        raise ProviderError("精修输入必须是视频素材", error_type="refine_no_input")
    user = _task_user(db, task)
    if user and not can_read_asset(
        input_asset, user, demo_mode=getattr(cfg, "DEMO_MODE", False)
    ):
        raise ProviderError("无权使用精修输入素材", error_type="refine_asset_forbidden")
    input_path = asset_service.get_file_path_for_asset(input_asset)
    if not input_path:
        raise ProviderError("精修输入文件不存在", error_type="refine_no_input")

    filters = params.get("filters") or {}
    if not filters:
        raise ProviderError("精修参数不能为空", error_type="empty_filters")
    output_dir = os.path.join(
        cfg.DATA_DIR, "assets", "videos", "refined", str(task.id)
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "refined.mp4")

    task_service.update_task(task.id, progress=35)
    try:
        media_service.apply_filter_chain(input_path, output_path, filters)
    except MediaServiceError as exc:
        raise ProviderError(str(exc), error_type="refine_failed")

    _raise_if_cancelled(task_service, task.id)
    task_service.update_task(task.id, progress=85)
    try:
        info = probe_media_file(cfg.FFPROBE_BIN, output_path)
    except MediaServiceError as exc:
        raise ProviderError(
            "精修输出无法验证：{0}".format(str(exc)),
            error_type="refine_invalid_output",
        )
    if not info.get("has_video") or float(info.get("duration_s") or 0) <= 0:
        raise ProviderError("精修输出没有有效视频轨", error_type="refine_invalid_output")
    duration_s = float(info.get("duration_s") or 0)

    project = project_service.get_project(task.creative_project_id)
    owner_user_id = (project.user_id if project else None) or task.created_by
    tenant_id = (project.tenant_id if project else None) or (user or {}).get("tenant_id")
    asset = asset_service.create_asset(
        name="{0} 精修版".format(shot.scene_title or "镜头"),
        asset_type="video",
        file_path=asset_service.relative_path_for(output_path),
        file_size=os.path.getsize(output_path),
        description="FFmpeg 单镜头精修",
        metadata={
            "source": "refine",
            "task_id": task.id,
            "project_id": task.creative_project_id,
            "shot_id": shot.id,
            "input_asset_id": input_asset.id,
            "filters": filters,
            "duration_s": duration_s,
            "media_info": info,
        },
        owner_user_id=owner_user_id,
        tenant_id=tenant_id,
        visibility="private",
        checksum_sha256=_sha256_file(output_path),
        duration_s=duration_s,
        media_info=info,
    )
    storyboard_service.set_media_pointers(
        shot.id, refined_video_asset_id=asset.id
    )
    _record_media_version(
        db, task, shot, "video", asset, "refine",
        "FFmpeg 精修版",
        {"filters": filters, "input_asset_id": input_asset.id},
        selected=False,
        clear_selection=False,
    )
    task_service.add_artifact(
        task_id=task.id,
        creative_project_id=task.creative_project_id,
        name=os.path.basename(output_path),
        artifact_type=TaskArtifact.TYPE_VIDEO,
        file_path=os.path.relpath(output_path, cfg.DATA_DIR),
        file_size=os.path.getsize(output_path),
        asset_id=asset.id,
        metadata={
            "shot_id": shot.id,
            "filters": filters,
            "input_asset_id": input_asset.id,
            "duration_s": duration_s,
        },
    )
    task_service.update_task(
        task.id, progress=100, output_asset_id=asset.id
    )
    return {
        "video_asset_id": asset.id,
        "shot_id": shot.id,
        "input_asset_id": input_asset.id,
        "filters": filters,
        "duration_s": duration_s,
        "output_path": output_path,
    }


def _safe_arc_name(value, fallback="file"):
    import re as _re
    text = _re.sub(r"[^0-9A-Za-z一-龥._-]+", "_", str(value or ""))
    return text.strip("._") or fallback


def _execute_export(task, cfg, db):
    """Export a task-scoped ZIP containing the real project media and final MP4."""
    task_service = get_task_service()
    project_service = get_creative_project_service(cfg.DATA_DIR)
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)
    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)
    timeline_service = get_timeline_service(cfg)

    task_service.update_task(task.id, stage="exporting", progress=10)
    _raise_if_cancelled(task_service, task.id)
    project = project_service.get_project(task.creative_project_id)
    if not project:
        raise ProviderError("项目不存在", error_type="project_not_found")
    user = _task_user(db, task)
    shots = storyboard_service.list_shots(task.creative_project_id)
    timeline = timeline_service.get_timeline(
        task.creative_project_id, ensure=False, user=user
    )

    output_dir = os.path.join(cfg.DATA_DIR, "exports", str(task.id))
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, "project_package.zip")
    manifest = {
        "project_id": project.id,
        "project_name": project.name,
        "timeline_version": project.timeline_version,
        "exported_timeline_version": timeline.get("timeline_version"),
        "final_video": None,
        "shots": [],
        "audio": [],
        "subtitles": None,
        "generated_at": int(time.time()),
    }
    files = []
    seen_arcnames = set()

    def add_asset(asset_id, arcname, category=None):
        if not asset_id or not arcname or arcname in seen_arcnames:
            return None
        asset = asset_service.get_asset(asset_id)
        if not asset:
            return None
        if user and not can_read_asset(
            asset, user, demo_mode=getattr(cfg, "DEMO_MODE", False)
        ):
            return None
        path = asset_service.get_file_path_for_asset(asset)
        if not path:
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext:
            base, requested_ext = os.path.splitext(arcname)
            if requested_ext.lower() != ext:
                arcname = base + ext
        seen_arcnames.add(arcname)
        files.append((path, arcname))
        return {"asset_id": asset.id, "arcname": arcname, "category": category,
                "file_size": asset.file_size, "metadata": asset.metadata}

    final_asset_id = project.final_video_asset_id
    final_video = add_asset(final_asset_id, "final/final_video.mp4", "final")
    manifest["final_video"] = final_video

    for shot in shots:
        shot_manifest = {
            "shot_id": shot.id,
            "sequence_no": shot.sequence_no,
            "scene_title": shot.scene_title,
            "dialogue": shot.dialogue,
        }
        video_id = shot.selected_video_asset_id or shot.video_asset_id
        entry = add_asset(
            video_id, "videos/shot_{0:03d}_video.mp4".format(shot.sequence_no), "video"
        )
        if entry:
            shot_manifest["video"] = entry
        image_entry = add_asset(
            shot.primary_image_asset_id,
            "images/shot_{0:03d}_image.png".format(shot.sequence_no), "image",
        )
        if image_entry:
            shot_manifest["image"] = image_entry
        narration_entry = add_asset(
            shot.audio_asset_id,
            "audio/narration/shot_{0:03d}_narration.wav".format(shot.sequence_no),
            "narration",
        )
        if narration_entry:
            shot_manifest["narration"] = narration_entry
        manifest["shots"].append(shot_manifest)

    for item in timeline.get("tracks") or []:
        track = item.get("track") or {}
        role = track.get("role")
        if role not in ("music", "sfx"):
            continue
        for clip in item.get("clips") or []:
            if clip.get("muted"):
                continue
            asset_id = clip.get("asset_id")
            if not asset_id:
                continue
            asset = asset_service.get_asset(asset_id)
            name = _safe_arc_name((asset.name if asset else "audio"), "audio")
            folder = "music" if role == "music" else "effects"
            entry = add_asset(
                asset_id,
                "audio/{0}/{1}.wav".format(folder, name),
                role,
            )
            if entry:
                manifest["audio"].append(entry)

    srt_content = TimelineService.build_srt_from_timeline(timeline)
    if not srt_content:
        # Do not read arbitrary shot.srt_path values.  Rebuild safe cue text
        # from validated shot metadata when no timeline subtitle clip exists.
        cumulative = 0.0
        cues = []
        for shot in shots:
            text = (shot.dialogue or "").strip()
            duration = float(shot.audio_duration_s or shot.duration_s or 4.0)
            if text:
                cues.append((
                    cumulative, cumulative + max(0.1, duration), text
                ))
            cumulative += max(0.1, duration)
        for index, (start, end, text) in enumerate(cues, start=1):
            srt_content += "{0}\n{1} --> {2}\n{3}\n\n".format(
                index, _srt_timestamp(start), _srt_timestamp(end), text
            )
    if srt_content.strip():
        srt_path = os.path.join(output_dir, "subtitles.srt")
        with open(srt_path, "w", encoding="utf-8") as handle:
            handle.write(srt_content)
        files.append((srt_path, "subtitles/subtitles.srt"))
        manifest["subtitles"] = "subtitles/subtitles.srt"

    project_json_path = os.path.join(output_dir, "project.json")
    with open(project_json_path, "w", encoding="utf-8") as handle:
        json.dump(project.to_dict(), handle, ensure_ascii=False, indent=2)
    files.append((project_json_path, "project.json"))

    _raise_if_cancelled(task_service, task.id)
    task_service.update_task(task.id, progress=55)
    media_service.create_zip_package(files, zip_path, manifest)
    _raise_if_cancelled(task_service, task.id)
    task_service.update_task(task.id, progress=95)

    now = int(time.time())
    download_url = "/api/creative/tasks/{0}/export/download".format(task.id)
    export_package = ExportPackage(
        id="{0}_export".format(task.id),
        creative_project_id=task.creative_project_id,
        task_id=task.id,
        format=ExportPackage.FORMAT_ZIP,
        file_path=zip_path,
        file_size=os.path.getsize(zip_path),
        status=ExportPackage.STATUS_COMPLETED,
        manifest=manifest,
        download_url=download_url,
        timeline_version=project.timeline_version,
        created_at=now,
        updated_at=now,
        created_by=task.created_by,
    )
    db.insert("export_packages", export_package.to_insert_params())
    task_service.add_artifact(
        task_id=task.id,
        creative_project_id=task.creative_project_id,
        name=os.path.basename(zip_path),
        artifact_type="archive",
        file_path=os.path.relpath(zip_path, cfg.DATA_DIR),
        file_size=os.path.getsize(zip_path),
        metadata={"download_url": download_url, "manifest": manifest},
    )
    task_service.update_task(task.id, progress=100)
    return {
        "zip_path": zip_path,
        "zip_size": os.path.getsize(zip_path),
        "manifest": manifest,
        "download_url": download_url,
    }


# Executor map. Image/video are handled by the resumable GenerationWorker.
EXECUTOR_MAP = {
    GenerationTask.TYPE_STORYBOARD: _execute_storyboard,
    GenerationTask.TYPE_TTS: _execute_tts,
    GenerationTask.TYPE_COMPOSE: _execute_compose,
    GenerationTask.TYPE_REFINE: _execute_refine,
    GenerationTask.TYPE_EXPORT: _execute_export,
}
LEGACY_TASK_TYPES = tuple(EXECUTOR_MAP.keys())


def recover_orphaned_legacy_tasks(task_service):
    """Fail tasks left ``running`` by a previous process and unstick projects.

    Legacy executors run in daemon threads without a lease: a crash or restart
    leaves the task ``running`` forever, which also blocks credential edits
    (``has_active_tasks``) and keeps the project in ``analyzing``.
    """
    now = int(time.time())
    placeholders = ",".join("?" for _ in LEGACY_TASK_TYPES)
    with task_service.db.transaction() as cursor:
        cursor.execute(
            "UPDATE generation_tasks SET status = ?, error_code = ?, error_message = ?, "
            "completed_at = ?, updated_at = ? "
            "WHERE task_type IN ({0}) AND status IN ('running', 'submitting')".format(
                placeholders
            ),
            (
                GenerationTask.STATUS_FAILED,
                "worker_restarted",
                "Worker 重启时任务尚未完成，已标记失败；请重新提交",
                now,
                now,
            ) + LEGACY_TASK_TYPES,
        )
        recovered_tasks = cursor.rowcount
        cursor.execute(
            "UPDATE creative_projects SET status = CASE "
            "WHEN EXISTS (SELECT 1 FROM storyboard_shots s "
            "WHERE s.creative_project_id = creative_projects.id) "
            "THEN ? ELSE ? END, updated_at = ? "
            "WHERE status = ? AND NOT EXISTS ("
            "SELECT 1 FROM generation_tasks t "
            "WHERE t.creative_project_id = creative_projects.id "
            "AND t.status IN ('queued', 'submitting', 'running'))",
            (
                CreativeProject.STATUS_READY,
                CreativeProject.STATUS_DRAFT,
                now,
                CreativeProject.STATUS_ANALYZING,
            ),
        )
        reset_projects = cursor.rowcount
    if recovered_tasks or reset_projects:
        logger.warning(
            "Recovered %s orphaned legacy task(s) and reset %s analyzing project(s)",
            recovered_tasks, reset_projects,
        )
    return {"tasks": recovered_tasks, "projects": reset_projects}


def _reset_project_after_failure(task_service, task):
    """Leave a project in a usable state when its analyzing task fails."""
    if not task.creative_project_id:
        return
    db = task_service.db
    try:
        project = db.fetch_one(
            "SELECT status FROM creative_projects WHERE id = ?",
            (task.creative_project_id,),
        )
        if not project or project.get("status") != CreativeProject.STATUS_ANALYZING:
            return
        active = db.fetch_one(
            "SELECT COUNT(*) AS total FROM generation_tasks "
            "WHERE creative_project_id = ? AND id <> ? "
            "AND status IN ('queued', 'submitting', 'running')",
            (task.creative_project_id, task.id),
        )
        if active and int(active.get("total") or 0) > 0:
            return
        shots = db.fetch_one(
            "SELECT COUNT(*) AS total FROM storyboard_shots WHERE creative_project_id = ?",
            (task.creative_project_id,),
        )
        status = (
            CreativeProject.STATUS_READY
            if shots and int(shots.get("total") or 0) > 0
            else CreativeProject.STATUS_DRAFT
        )
        db.update(
            "creative_projects",
            {"status": status, "updated_at": int(time.time())},
            "id = ? AND status = ?",
            (task.creative_project_id, CreativeProject.STATUS_ANALYZING),
        )
    except Exception:
        logger.exception(
            "Failed to reset project %s after task %s failure",
            task.creative_project_id, task.id,
        )


def _process_task(task_service, cfg, db, task):
    """Run one claimed legacy task, honouring cancellation and failures."""
    fresh = task_service.get_task(task.id)
    if not fresh:
        return
    if (
        fresh.status == GenerationTask.STATUS_CANCELLED
        or fresh.cancel_requested
    ):
        logger.info("Task %s was cancelled before execution; skipping", task.id)
        return

    executor = EXECUTOR_MAP.get(task.task_type)
    if not executor:
        task_service.update_task(
            task.id,
            status=GenerationTask.STATUS_FAILED,
            error_code="unknown_task_type",
            error_message="Unknown task type: {0}".format(task.task_type),
        )
        return

    logger.info("Executing task %s (type=%s)", task.id, task.task_type)

    try:
        result = executor(task, cfg, db)
        current = task_service.get_task(task.id)
        if current and current.status == GenerationTask.STATUS_RUNNING:
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_SUCCEEDED,
                stage="succeeded",
                result_payload=result,
                progress=100,
                completed_at=int(time.time()),
                completed_at_ms=time.time(),
            )
            logger.info("Task %s succeeded", task.id)
        else:
            logger.info(
                "Task %s finished after cancellation (status=%s)",
                task.id, current.status if current else "missing",
            )
    except ProviderError as e:
        current = task_service.get_task(task.id)
        if not current or current.status != GenerationTask.STATUS_CANCELLED:
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_FAILED,
                stage="failed",
                error_code=e.error_type or "provider_error",
                error_message=str(e),
                completed_at=int(time.time()),
                completed_at_ms=time.time(),
            )
        _reset_project_after_failure(task_service, task)
        logger.error("Task %s failed (provider): %s", task.id, str(e))
    except Exception as e:
        current = task_service.get_task(task.id)
        if not current or current.status != GenerationTask.STATUS_CANCELLED:
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_FAILED,
                stage="failed",
                error_message=str(e),
                completed_at=int(time.time()),
                completed_at_ms=time.time(),
            )
        _reset_project_after_failure(task_service, task)
        logger.exception("Task %s failed with exception", task.id)


def start_task_worker(task_service, cfg):
    """Start a daemon thread that processes creative production tasks."""

    def _run():
        # Import Database for db operations
        from .database import get_database

        db = get_database()
        stop_event = threading.Event()

        try:
            recover_orphaned_legacy_tasks(task_service)
        except Exception:
            logger.exception("Failed to recover orphaned legacy tasks")

        logger.info("Creative task worker started")
        while not stop_event.is_set():
            try:
                task = task_service.claim_next_task(task_types=LEGACY_TASK_TYPES)
                if task is None:
                    time.sleep(2)
                    continue

                _process_task(task_service, cfg, db, task)

            except Exception as e:
                logger.exception("Task worker loop error: %s", str(e))
                time.sleep(5)

    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
    return t
