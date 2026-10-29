# -*- coding: utf-8 -*-
"""
Background task worker for creative production pipeline.
Daemon thread pattern: claim → execute → update status.
"""
from __future__ import absolute_import

import json
import logging
import os
import subprocess
import threading
import time

from .asset_service import get_asset_service
from .config import Config
from .creative_project_service import get_creative_project_service
from .credential_service import CredentialError, CredentialService
from .media_service import get_media_service, MediaServiceError
from .models import CreativeProject, GenerationTask, StoryboardShot, TaskArtifact, Asset, ExportPackage
from .providers.base import ProviderError
from .providers.llm_provider import LLMProvider
from .providers.image_provider import ComfyUIProvider
from .providers.tts_provider import PiperTTSProvider
from .provider_router import ProviderRouter
from .storyboard_service import get_storyboard_service
from .task_service import get_task_service

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


def _execute_tts(task, cfg, db):
    """Execute TTS narration generation via Piper."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)

    task_service.update_task(task.id, stage="generating", progress=10)

    # Get all shots with dialogue
    shots = storyboard_service.list_shots(task.creative_project_id)

    tts_provider = PiperTTSProvider(
        piper_bin=cfg.PIPER_BIN,
        piper_model_path=cfg.PIPER_MODEL_PATH,
        ffprobe_bin=cfg.FFPROBE_BIN,
    )

    task_service.update_task(task.id, progress=20)

    output_dir = os.path.join(cfg.DATA_DIR, "assets", "audio", "generated")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    audio_assets = []
    total_duration = 0.0

    for i, shot in enumerate(shots):
        if not shot.dialogue:
            continue

        voice_id = shot.voice_id or cfg.PIPER_MODEL_PATH
        output_path = os.path.join(output_dir, "shot_{0}.wav".format(shot.id))

        result = tts_provider.synthesize(shot.dialogue, voice_id, output_path)

        # Create asset record
        asset = asset_service.create_asset(
            name="{0}_narration".format(shot.scene_title or "shot_{0}".format(i)),
            asset_type="audio",
            file_path=output_path,
            file_size=os.path.getsize(output_path),
            **_owned_asset_fields(task, db)
        )

        storyboard_service.update_shot(shot.id, audio_asset_id=asset.id, srt_path=output_path)

        audio_assets.append({"shot_id": shot.id, "asset_id": asset.id, "duration_s": result["duration_s"]})
        total_duration += result["duration_s"]

        progress = 20 + int((i + 1) / max(len(shots), 1) * 70)
        task_service.update_task(task.id, progress=progress)

    task_service.update_task(task.id, progress=100)
    return {"audio_assets": audio_assets, "total_duration_s": total_duration}


def _execute_compose(task, cfg, db):
    """Execute video composition via MediaService."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()

    task_service.update_task(task.id, stage="composing", progress=10)

    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)

    output_dir = os.path.join(cfg.DATA_DIR, "assets", "videos", "composed")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, "{0}_composed.mp4".format(task.creative_project_id))

    params = task.params or {}
    width = params.get("width", 1920)
    height = params.get("height", 1080)
    fps = params.get("fps", 24)

    # Collect local clips/assets from shots. Remote URLs are never passed to FFmpeg.
    shots = storyboard_service.list_shots(task.creative_project_id)
    clip_specs = []
    audio_files = []
    asset_service = get_asset_service(cfg.DATA_DIR)

    for shot in shots:
        video_path = None
        if shot.video_asset_id:
            asset = asset_service.get_asset(shot.video_asset_id)
            video_path = asset_service.get_file_path_for_asset(asset) if asset else None
        if video_path:
            clip_specs.append({
                "file_path": video_path,
                "duration_s": shot.duration_s or 4,
            })
        if shot.audio_asset_id:
            audio_asset = asset_service.get_asset(shot.audio_asset_id)
            audio_path = asset_service.get_file_path_for_asset(audio_asset) if audio_asset else None
            if audio_path:
                audio_files.append(audio_path)

    task_service.update_task(task.id, progress=40)

    # Compose video
    media_service.compose_video(clip_specs, output_path, width=width, height=height, fps=fps)

    task_service.update_task(task.id, progress=70)

    # Mix audio if available
    audio_output = os.path.join(output_dir, "{0}_audio.aac".format(task.creative_project_id))
    if audio_files:
        media_service.mix_audio(audio_files, audio_output)

    task_service.update_task(task.id, progress=90)

    # Create asset record
    asset_service = get_asset_service(cfg.DATA_DIR)
    if os.path.exists(output_path):
        asset = asset_service.create_asset(
            name="composed_video",
            asset_type="video",
            file_path=output_path,
            file_size=os.path.getsize(output_path),
            **_owned_asset_fields(task, db)
        )

        task_service.update_task(task.id, progress=100)
        return {"video_asset_id": asset.id, "output_path": output_path}

    task_service.update_task(task.id, progress=100)
    return {"output_path": output_path}


def _execute_refine(task, cfg, db):
    """Execute video refinement via MediaService filter chain."""
    task_service = get_task_service()

    task_service.update_task(task.id, stage="refining", progress=10)

    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)
    params = task.params or {}

    input_asset_id = params.get("input_asset_id")
    asset_service = get_asset_service(cfg.DATA_DIR)
    input_asset = asset_service.get_asset(input_asset_id) if input_asset_id else None
    if not input_asset or input_asset.asset_type != "video":
        raise ProviderError("Refine input must be an owned video asset", error_type="refine_no_input")
    input_path = asset_service.get_file_path_for_asset(input_asset)
    if not input_path:
        raise ProviderError("Refine input file not found", error_type="refine_no_input")

    output_dir = os.path.join(cfg.DATA_DIR, "assets", "videos", "refined")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, "{0}_refined.mp4".format(task.creative_project_id))

    raw_filters = params.get("filters") or {}
    filters = {
        "brightness": raw_filters.get("brightness", params.get("brightness")),
        "contrast": raw_filters.get("contrast", params.get("contrast")),
        "saturation": raw_filters.get("saturation", params.get("saturation")),
        "gamma": raw_filters.get("gamma", params.get("gamma")),
        "sharpen": raw_filters.get("sharpen", params.get("sharpen")),
        "denoise": raw_filters.get("denoise", params.get("denoise")),
        "crop": raw_filters.get("crop", params.get("crop")),
        "scale": raw_filters.get("scale", params.get("scale")),
        "fps": raw_filters.get("fps", params.get("fps")),
    }

    task_service.update_task(task.id, progress=40)

    media_service.apply_filter_chain(input_path, output_path, filters)

    task_service.update_task(task.id, progress=90)

    asset_service = get_asset_service(cfg.DATA_DIR)
    if os.path.exists(output_path):
        asset = asset_service.create_asset(
            name="refined_video",
            asset_type="video",
            file_path=output_path,
            file_size=os.path.getsize(output_path),
            **_owned_asset_fields(task, db)
        )

        task_service.update_task(task.id, progress=100)
        return {"video_asset_id": asset.id, "output_path": output_path}

    task_service.update_task(task.id, progress=100)
    return {"output_path": output_path}


def _execute_export(task, cfg, db):
    """Execute export package creation."""
    task_service = get_task_service()
    storyboard_service = get_storyboard_service()
    asset_service = get_asset_service(cfg.DATA_DIR)

    task_service.update_task(task.id, stage="exporting", progress=10)

    media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)

    shots = storyboard_service.list_shots(task.creative_project_id)

    output_dir = os.path.join(cfg.DATA_DIR, "exports", task.creative_project_id)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    zip_path = os.path.join(output_dir, "{0}_package.zip".format(task.creative_project_id))

    files_to_zip = []
    manifest = {"project_id": task.creative_project_id, "shots": []}

    task_service.update_task(task.id, progress=30)

    # Collect all assets
    for shot in shots:
        shot_manifest = {
            "shot_id": shot.id,
            "sequence_no": shot.sequence_no,
            "scene_title": shot.scene_title,
            "dialogue": shot.dialogue,
        }

        if shot.video_asset_id:
            video_asset = asset_service.get_asset(shot.video_asset_id)
            video_path = asset_service.get_file_path_for_asset(video_asset) if video_asset else None
            if video_path and os.path.exists(video_path):
                arcname = "video/{0:03d}_video.mp4".format(shot.sequence_no)
                files_to_zip.append((video_path, arcname))
                shot_manifest["video_file"] = arcname
                shot_manifest["video_asset_id"] = shot.video_asset_id

        if shot.primary_image_asset_id:
            asset = asset_service.get_asset(shot.primary_image_asset_id)
            if asset and asset.file_path and os.path.exists(asset.file_path):
                arcname = "shots/{0:03d}_image.png".format(shot.sequence_no)
                files_to_zip.append((asset.file_path, arcname))
                shot_manifest["image_file"] = arcname

        if shot.audio_asset_id:
            asset = asset_service.get_asset(shot.audio_asset_id)
            if asset and asset.file_path and os.path.exists(asset.file_path):
                arcname = "audio/{0:03d}_narration.wav".format(shot.sequence_no)
                files_to_zip.append((asset.file_path, arcname))
                shot_manifest["audio_file"] = arcname

        manifest["shots"].append(shot_manifest)

    task_service.update_task(task.id, progress=60)

    # Generate SRT if dialogues exist
    srt_content = ""
    cumulative_time = 0.0
    for shot in shots:
        if shot.dialogue:
            start_sec = cumulative_time
            end_sec = cumulative_time + (shot.duration_s or 4)
            cumulative_time = end_sec

            start_str = "{0:02d}:{1:02d}:{2:06.3f}".format(
                int(start_sec // 3600), int((start_sec % 3600) // 60), start_sec % 60
            ).replace(".", ",")
            end_str = "{0:02d}:{1:02d}:{2:06.3f}".format(
                int(end_sec // 3600), int((end_sec % 3600) // 60), end_sec % 60
            ).replace(".", ",")

            srt_content += "{0}\n{1} --> {2}\n{3}\n\n".format(
                shot.sequence_no, start_str, end_str, shot.dialogue
            )

    srt_path = os.path.join(output_dir, "subtitles.srt")
    with open(srt_path, "w") as f:
        f.write(srt_content)
    files_to_zip.append((srt_path, "subtitles.srt"))

    # Generate cover thumbnail from the first locally stored video asset.
    cover_path = os.path.join(output_dir, "cover.png")
    first_video_path = None
    if shots and shots[0].video_asset_id:
        first_video_asset = asset_service.get_asset(shots[0].video_asset_id)
        first_video_path = asset_service.get_file_path_for_asset(first_video_asset) if first_video_asset else None
    if first_video_path:
        try:
            media_service.generate_thumbnail(first_video_path, cover_path, width=640, height=360)
            files_to_zip.append((cover_path, "cover.png"))
        except Exception as e:
            logger.warning("Failed to generate cover: %s", str(e))

    task_service.update_task(task.id, progress=80)

    # Create ZIP
    media_service.create_zip_package(files_to_zip, zip_path, manifest)

    task_service.update_task(task.id, progress=95)

    # Create export package record
    now = int(time.time())
    download_url = "/api/creative/tasks/{0}/export/download".format(task.id)
    db.insert("export_packages", {
        "id": str(task.id) + "_export",
        "creative_project_id": task.creative_project_id,
        "task_id": task.id,
        "format": "zip",
        "file_path": zip_path,
        "file_size": os.path.getsize(zip_path) if os.path.exists(zip_path) else 0,
        "status": "completed",
        "manifest": json.dumps(manifest, ensure_ascii=False),
        "download_url": download_url,
        "created_by": task.created_by,
        "created_at": now,
        "updated_at": now,
    })
    task_service.add_artifact(
        task_id=task.id,
        creative_project_id=task.creative_project_id,
        name=os.path.basename(zip_path),
        artifact_type="archive",
        file_path=os.path.relpath(zip_path, cfg.DATA_DIR),
        file_size=os.path.getsize(zip_path) if os.path.exists(zip_path) else 0,
        metadata={"download_url": download_url},
    )

    task_service.update_task(task.id, progress=100)
    return {"zip_path": zip_path, "manifest": manifest, "download_url": download_url}


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
                result_payload=result,
                progress=100,
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
                error_code=e.error_type or "provider_error",
                error_message=str(e),
            )
        _reset_project_after_failure(task_service, task)
        logger.error("Task %s failed (provider): %s", task.id, str(e))
    except Exception as e:
        current = task_service.get_task(task.id)
        if not current or current.status != GenerationTask.STATUS_CANCELLED:
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_FAILED,
                error_message=str(e),
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
