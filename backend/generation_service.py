# -*- coding: utf-8 -*-
"""Business orchestration for real image/video generation tasks."""
from __future__ import absolute_import

import base64
import hashlib
import logging
import os
import shutil
import sqlite3
import time

from . import generation_models
from .access import can_read_asset
from .asset_service import get_asset_service
from .auth_middleware import is_admin
from .credential_service import CredentialError, CredentialService
from .database import get_database
from .http_utils import ApiError
from .media_fetcher import MediaFetchError, download_url
from .models import GenerationTask, ShotMediaVersion, StoryboardShot

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def _now_ms():
    return time.time()


def _task_dir(cfg, task):
    base = os.path.realpath(os.path.join(cfg.DATA_DIR, "assets", "generated"))
    path = os.path.realpath(
        os.path.join(base, str(task.created_by or "unknown"), str(task.id))
    )
    if path != base and not path.startswith(base + os.sep):
        raise ApiError("invalid_task_path", "任务存储路径无效", status_code=500)
    os.makedirs(path, exist_ok=True)
    return path


def _tenant_for_user(user_id):
    row = get_database().fetch_one(
        "SELECT tenant_id FROM auth_users WHERE id = ?", (user_id,)
    )
    return row["tenant_id"] if row else None


def _project_owned_by(user, project_id):
    if not project_id:
        return None
    row = get_database().fetch_one(
        "SELECT * FROM creative_projects WHERE id = ?", (project_id,)
    )
    if not row:
        raise ApiError("project_not_found", "项目不存在", status_code=404)
    if not is_admin(user) and row.get("user_id") != user.get("id"):
        raise ApiError("forbidden", "无权在该项目下创建任务", status_code=403)
    return row


def _shot_owned_by(user, shot_id, project_id):
    if not shot_id:
        return None
    row = get_database().fetch_one(
        "SELECT * FROM storyboard_shots WHERE id = ?", (shot_id,)
    )
    if not row:
        raise ApiError("shot_not_found", "分镜不存在", status_code=404)
    shot = StoryboardShot.from_row(row)
    if project_id and shot.creative_project_id != project_id:
        raise ApiError("invalid_params", "分镜不属于指定项目", status_code=400)
    _project_owned_by(user, shot.creative_project_id)
    return shot


def _validate_prompt(cfg, prompt):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ApiError("invalid_params", "Prompt 不能为空", status_code=400)
    if len(prompt) > cfg.MAX_PROMPT_LENGTH:
        raise ApiError(
            "invalid_params",
            "Prompt 不能超过 {0} 个字符".format(cfg.MAX_PROMPT_LENGTH),
            status_code=400,
        )
    return prompt


def _check_quota(cfg, task_service, user, task_type):
    if task_service.count_active_tasks(user.get("id")) >= cfg.MAX_CONCURRENT_TASKS_PER_USER:
        raise ApiError(
            "quota_exceeded",
            "当前运行中的任务过多，请等待完成后再提交",
            status_code=429,
        )
    since = _now() - 86400
    if task_type == GenerationTask.TYPE_IMAGE:
        limit = cfg.DAILY_IMAGE_LIMIT
    elif task_type == GenerationTask.TYPE_VIDEO:
        limit = cfg.DAILY_VIDEO_LIMIT
    else:
        limit = 0
    if limit and task_service.count_tasks_since(user.get("id"), since, task_type) >= limit:
        raise ApiError(
            "quota_exceeded",
            "今日该类型任务已达到上限（{0}）".format(limit),
            status_code=429,
        )


def _parse_ratio(ratio):
    ratio = str(ratio or "1:1").strip().lower()
    if ratio in ("adaptive", "custom", ""):
        return 1.0, 1.0
    if ":" not in ratio:
        raise ApiError("invalid_params", "比例格式应为 宽:高", status_code=400)
    try:
        width_ratio, height_ratio = [float(part) for part in ratio.split(":", 1)]
    except (TypeError, ValueError):
        raise ApiError("invalid_params", "比例格式应为 宽:高", status_code=400)
    if width_ratio <= 0 or height_ratio <= 0:
        raise ApiError("invalid_params", "比例必须为正数", status_code=400)
    return width_ratio, height_ratio


def _round_to_multiple(value, multiple=8):
    return max(multiple, int(round(value / float(multiple))) * multiple)


def _image_dimensions(size, ratio, caps):
    """Resolve a size preset/custom value and ratio into concrete pixels."""
    if not isinstance(size, str) or not size.strip():
        size = caps.get("default_size") or "2K"
    size = size.strip()
    ratio_value = ratio or caps.get("default_ratio") or "1:1"
    if ratio_value not in caps.get("ratios", []):
        raise ApiError("invalid_params", "不支持的比例", status_code=400)
    ratio_w, ratio_h = _parse_ratio(ratio_value)
    pixel_range = caps.get("pixel_range") or None

    if "x" in size.lower():
        if not caps.get("supports_custom_size", False):
            raise ApiError("invalid_params", "该模型不支持自定义尺寸", status_code=400)
        try:
            width, height = [int(part) for part in size.lower().split("x", 1)]
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "自定义尺寸格式应为 宽x高", status_code=400)
        if width < 256 or height < 256 or width > 8192 or height > 8192:
            raise ApiError("invalid_params", "图片宽高需在 256-8192 之间", status_code=400)
        if pixel_range and not (pixel_range[0] <= width * height <= pixel_range[1]):
            raise ApiError(
                "invalid_params",
                "图片像素总量超出模型支持范围（{0}-{1}）".format(*pixel_range),
                status_code=400,
            )
        return width, height

    if size not in caps.get("sizes", []):
        raise ApiError("invalid_params", "不支持的图片尺寸", status_code=400)
    preset_pixels = {
        "1K": 1024 * 1024,
        "1.5K": 1536 * 1536,
        "2K": 2048 * 2048,
        "3K": 3072 * 3072,
        "4K": 4096 * 4096,
    }
    target = preset_pixels.get(size)
    if target is None:
        raise ApiError("invalid_params", "不支持的图片尺寸", status_code=400)
    width = (target * ratio_w / ratio_h) ** 0.5
    height = target / width
    if pixel_range:
        pixels = width * height
        if pixels < pixel_range[0]:
            scale = (float(pixel_range[0]) / pixels) ** 0.5
        elif pixels > pixel_range[1]:
            scale = (float(pixel_range[1]) / pixels) ** 0.5
        else:
            scale = 1.0
        width *= scale
        height *= scale
    width = _round_to_multiple(width)
    height = _round_to_multiple(height)
    if pixel_range and not (pixel_range[0] <= width * height <= pixel_range[1]):
        raise ApiError(
            "invalid_params",
            "图片像素总量超出模型支持范围（{0}-{1}）".format(*pixel_range),
            status_code=400,
        )
    return width, height


def create_generation_task(cfg, task_service, user, task_type, model_key, payload,
                           project_id=None, shot_id=None, client_request_id=None):
    model = generation_models.get_model(
        cfg, model_key, include_unavailable=True, user=user
    )
    if not model:
        raise ApiError("invalid_model", "未知的生成模型", status_code=400)
    if model["task_type"] != task_type:
        raise ApiError("invalid_model", "模型类型与任务不匹配", status_code=400)
    if not model["available"]:
        raise ApiError(
            "provider_not_configured",
            model.get("unavailable_reason") or "生成模型未配置",
            status_code=400,
            details={"configure_url": "/api-settings"},
        )

    prompt = _validate_prompt(cfg, payload.get("prompt"))
    caps = model["capabilities"]

    if project_id:
        _project_owned_by(user, project_id)
    if shot_id:
        shot = _shot_owned_by(user, shot_id, project_id)
        if not project_id:
            project_id = shot.creative_project_id

    reference_asset_ids = []
    raw_reference_ids = payload.get("reference_asset_ids")
    if raw_reference_ids is not None:
        if not isinstance(raw_reference_ids, (list, tuple)):
            raise ApiError("invalid_params", "reference_asset_ids 必须是数组", status_code=400)
        for value in raw_reference_ids:
            if isinstance(value, str) and value.strip() and value.strip() not in reference_asset_ids:
                reference_asset_ids.append(value.strip())
    single_reference_id = payload.get("reference_asset_id")
    if isinstance(single_reference_id, str) and single_reference_id.strip():
        single_reference_id = single_reference_id.strip()
        if single_reference_id not in reference_asset_ids:
            reference_asset_ids.insert(0, single_reference_id)

    max_reference_images = int(caps.get("max_reference_images") or 0)
    if reference_asset_ids and not caps.get("supports_reference_image"):
        raise ApiError("invalid_params", "该模型不支持参考图片", status_code=400)
    if len(reference_asset_ids) > max_reference_images:
        raise ApiError(
            "invalid_params",
            "该模型最多支持 {0} 张参考图片，当前提交 {1} 张".format(
                max_reference_images, len(reference_asset_ids)
            ),
            status_code=400,
        )
    if reference_asset_ids:
        asset_service = get_asset_service(cfg.DATA_DIR)
        for reference_asset_id in reference_asset_ids:
            asset = asset_service.get_asset(reference_asset_id)
            if not asset:
                raise ApiError("asset_not_found", "参考图片不存在", status_code=404)
            if not can_read_asset(asset, user, demo_mode=cfg.DEMO_MODE):
                raise ApiError("forbidden", "无权使用该参考图片", status_code=403)
            if asset.asset_type != "image":
                raise ApiError("invalid_params", "参考素材必须是图片", status_code=400)
    reference_asset_id = reference_asset_ids[0] if reference_asset_ids else None

    seed = payload.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "seed 必须是整数", status_code=400)
        if not caps.get("supports_seed"):
            raise ApiError("invalid_params", "该模型不支持随机种子", status_code=400)

    negative_prompt = payload.get("negative_prompt") or None
    if negative_prompt and not caps.get("supports_negative_prompt"):
        # Shot defaults may supply a negative prompt; never send it to a model
        # that would reject the field.
        negative_prompt = None

    watermark = bool(payload.get("watermark", False))
    if watermark and not caps.get("supports_watermark"):
        raise ApiError("invalid_params", "该模型不支持水印参数", status_code=400)

    params = {
        "model_key": model_key,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "reference_asset_id": reference_asset_id,
        "reference_asset_ids": list(reference_asset_ids),
        "watermark": watermark,
        # Snapshot which credential source this task was created with so the
        # worker never silently switches accounts while queued/running.
        "credential_source": model.get("credential_source"),
    }
    if task_type == GenerationTask.TYPE_IMAGE:
        size = payload.get("size") or caps.get("default_size") or "2K"
        ratio = (
            payload.get("ratio")
            or payload.get("aspect_ratio")
            or caps.get("default_ratio")
            or "1:1"
        )
        width, height = _image_dimensions(size, ratio, caps)
        params.update(
            {
                "size": size,
                "ratio": ratio,
                "width": width,
                "height": height,
            }
        )
    else:
        ratio = payload.get("ratio") or payload.get("aspect_ratio") or "16:9"
        try:
            duration = int(payload.get("duration_s") or payload.get("duration") or 5)
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "视频时长必须是整数秒", status_code=400)
        resolution = payload.get("resolution") or "720p"
        if ratio not in caps.get("ratios", []):
            raise ApiError("invalid_params", "不支持的比例", status_code=400)
        duration_range = caps.get("duration_range")
        if duration_range:
            if duration < int(duration_range[0]) or duration > int(duration_range[1]):
                raise ApiError(
                    "invalid_params",
                    "该模型支持的视频时长为 {0}-{1} 秒".format(
                        duration_range[0], duration_range[1]
                    ),
                    status_code=400,
                )
        elif duration not in caps.get("durations", []):
            raise ApiError("invalid_params", "不支持的视频时长", status_code=400)
        if resolution not in caps.get("resolutions", []):
            raise ApiError("invalid_params", "不支持的分辨率", status_code=400)
        requested_audio = payload.get("generate_audio")
        generate_audio = (
            bool(caps.get("default_audio", False))
            if requested_audio is None
            else bool(requested_audio)
        )
        if generate_audio and not caps.get("supports_audio"):
            raise ApiError("invalid_params", "该模型不支持音频生成", status_code=400)
        params.update(
            {
                "ratio": ratio,
                "duration_s": duration,
                "resolution": resolution,
                "generate_audio": generate_audio,
            }
        )

    existing = task_service.find_idempotent_task(user.get("id"), client_request_id)
    if existing:
        return existing

    try:
        # Quota check + insert share one IMMEDIATE transaction so concurrent
        # submissions cannot both pass the limit.
        with task_service.db.transaction() as cursor:
            _check_quota(cfg, task_service, user, task_type)
            task = task_service.create_task(
                creative_project_id=project_id,
                task_type=task_type,
                target_shot_id=shot_id,
                target_asset_id=reference_asset_id,
                created_by=user.get("id"),
                provider=model["provider"],
                model_id=model["model_id"],
                params=params,
                client_request_id=client_request_id,
                max_attempts=cfg.GENERATION_MAX_ATTEMPTS,
                status=GenerationTask.STATUS_QUEUED,
                cursor=cursor,
            )
    except sqlite3.IntegrityError:
        # Another request with the same idempotency key won the race.
        existing = task_service.find_idempotent_task(user.get("id"), client_request_id)
        if existing:
            return existing
        raise ApiError("duplicate_request", "重复的生成请求", status_code=409)

    _audit(cfg, "generation_submit", user, task.id, {"task_type": task_type, "model": model_key})
    return task


# Generation provider -> per-user credential provider.
_CREDENTIAL_PROVIDER_BY_TASK_PROVIDER = {
    "ark_seedream": "ark",
    "ark_seedance": "ark",
    "openai_image": "openai_image",
    "atlas_seedance": "atlas_seedance",
    "luma": "luma",
}


def _provider_for_task(cfg, task):
    params = task.params or {}
    provider_name = task.provider
    if not provider_name:
        model = generation_models.get_model(
            cfg, params.get("model_key") or "", include_unavailable=True
        )
        provider_name = (model or {}).get("provider")
    if provider_name == "comfyui":
        # ComfyUI stays platform-configured only (no user-level endpoints).
        from .providers.image_provider import ComfyUIProvider
        return ComfyUIProvider(
            base_url=cfg.COMFYUI_BASE_URL,
            workflow_file=cfg.COMFYUI_WORKFLOW_FILE,
        )

    cred_provider = _CREDENTIAL_PROVIDER_BY_TASK_PROVIDER.get(provider_name)
    if not cred_provider:
        raise ApiError("invalid_model", "无法创建 Provider 客户端", status_code=400)

    credential_service = CredentialService(cfg.DATA_DIR, cfg)
    try:
        effective = credential_service.effective(
            task.created_by,
            cred_provider,
            cfg,
            prefer_source=params.get("credential_source"),
        )
    except CredentialError as exc:
        raise ApiError(
            "provider_credential_missing",
            exc.message or "Provider 凭据不可用",
            status_code=400,
            details={"configure_url": "/api-settings"},
        )
    if not effective.get("api_key") or not effective.get("source"):
        raise ApiError(
            "provider_credential_missing",
            "任务使用的 {0} 凭据已不可用，请在 API 配置页重新配置".format(cred_provider),
            status_code=400,
            details={"configure_url": "/api-settings"},
        )
    if effective.get("source") == "user":
        # Re-resolve immediately before the outbound request: save-time
        # validation is not enough with DNS rebinding.  Fail closed rather
        # than calling a host that now points at the private network.
        try:
            effective["base_url"] = credential_service.validate_base_url(
                effective.get("base_url"), cfg
            )
        except CredentialError:
            raise ApiError(
                "provider_credential_missing",
                "任务使用的 Base URL 未通过安全校验，请在 API 配置页重新配置",
                status_code=400,
                details={"configure_url": "/api-settings"},
            )

    api_key = effective["api_key"]
    base_url = effective["base_url"]
    model_id = task.model_id
    if not model_id:
        model = generation_models.get_model(
            cfg, params.get("model_key") or "", include_unavailable=True
        )
        model_id = (model or {}).get("model_id") or effective.get("model")

    from .provider_factory import create_provider
    return create_provider(
        cfg, provider_name, api_key, base_url,
        model_id or effective.get("model"),
    )


def _reference_data_urls(cfg, asset_ids, user):
    if not asset_ids:
        return []
    asset_service = get_asset_service(cfg.DATA_DIR)
    total_limit_mb = int(getattr(cfg, "MAX_REFERENCE_IMAGES_TOTAL_MB", 40) or 0)
    total_limit = total_limit_mb * 1024 * 1024
    urls = []
    total_size = 0
    for asset_id in asset_ids:
        asset = asset_service.get_asset(asset_id)
        if not asset or not can_read_asset(asset, user, demo_mode=cfg.DEMO_MODE):
            raise ApiError("forbidden", "无权使用参考图片", status_code=403)
        path = asset_service.get_file_path_for_asset(asset)
        if not path:
            raise ApiError("file_not_found", "参考图片文件不存在", status_code=404)
        size = os.path.getsize(path)
        if size > cfg.MAX_REFERENCE_IMAGE_MB * 1024 * 1024:
            raise ApiError("invalid_params", "参考图片超过大小限制", status_code=400)
        total_size += size
        if total_limit and total_size > total_limit:
            raise ApiError(
                "invalid_params",
                "参考图片总大小超过限制（{0} MB）".format(total_limit_mb),
                status_code=400,
            )
        with open(path, "rb") as handle:
            raw = handle.read()
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }.get(ext)
        if not mime:
            raise ApiError("invalid_params", "参考图片格式不支持", status_code=400)
        urls.append("data:{0};base64,{1}".format(
            mime, base64.b64encode(raw).decode("ascii")
        ))
    return urls


def _reference_data_url(cfg, asset_id, user):
    urls = _reference_data_urls(cfg, [asset_id] if asset_id else [], user)
    return urls[0] if urls else None


def _user_dict(user_id):
    row = get_database().fetch_one("SELECT * FROM auth_users WHERE id = ?", (user_id,))
    if not row:
        return None
    return {
        "id": row["id"],
        "tenant_id": row.get("tenant_id"),
        "role": row.get("role") or "user",
        "status": row.get("status") or "active",
    }


def _decode_b64_image(b64, dest_dir, max_bytes):
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise MediaFetchError("Provider 返回的 Base64 图片无效", "invalid_base64")
    if not raw or len(raw) > max_bytes:
        raise MediaFetchError("Provider 图片为空或超过大小限制", "file_too_large")
    if not (
        raw.startswith(b"\x89PNG\r\n\x1a\n")
        or raw.startswith(b"\xff\xd8\xff")
        or (len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    ):
        raise MediaFetchError("Provider 图片格式校验失败", "invalid_file_magic")
    ext = ".png" if raw.startswith(b"\x89PNG") else ".jpg" if raw.startswith(b"\xff\xd8\xff") else ".webp"
    path = os.path.join(dest_dir, hashlib.sha256(raw).hexdigest()[:32] + ext)
    with open(path, "wb") as handle:
        handle.write(raw)
    return path


def _download_image_items(cfg, items, dest_dir):
    files = []
    max_bytes = cfg.MAX_GENERATION_DOWNLOAD_MB * 1024 * 1024
    for item in items or []:
        if item.get("url"):
            files.append(download_url(
                item["url"], dest_dir, kind="image", max_bytes=max_bytes,
                timeout_s=cfg.GENERATION_DOWNLOAD_TIMEOUT_S,
            ))
        elif item.get("b64_json"):
            files.append(_decode_b64_image(item["b64_json"], dest_dir, max_bytes))
    return files


def _download_video(cfg, url, dest_dir):
    return download_url(
        url, dest_dir, kind="video",
        max_bytes=cfg.MAX_GENERATION_DOWNLOAD_MB * 1024 * 1024,
        timeout_s=cfg.GENERATION_DOWNLOAD_TIMEOUT_S,
    )


def _audit(cfg, action, user, task_id, metadata=None, result="success"):
    if not getattr(cfg, "AUDIT_ENABLED", True):
        return None
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=(user or {}).get("id"),
            tenant_id=(user or {}).get("tenant_id"),
            project_id=None,
            action=action,
            target_type="generation_task",
            target_id=task_id,
            result=result,
            metadata=metadata,
        )
    except Exception:
        pass


def _audit_task_failure(cfg, task, error_code=None, error_message=None):
    """Record a final task failure without exposing prompts or provider bodies."""
    metadata = {
        "task_type": getattr(task, "task_type", None),
        "provider": getattr(task, "provider", None),
        "model_id": getattr(task, "model_id", None),
    }
    if error_code:
        metadata["error_code"] = str(error_code)[:120]
    if error_message:
        metadata["error_message"] = str(error_message)[:500]
    return _audit(
        cfg, "generation_failed", _user_dict(task.created_by), task.id,
        metadata=metadata, result="failed",
    )


def _deadline_seconds(cfg, task):
    if task.task_type == GenerationTask.TYPE_IMAGE:
        return int(getattr(cfg, "GENERATION_IMAGE_DEADLINE_S", 1800) or 0)
    return int(getattr(cfg, "GENERATION_VIDEO_DEADLINE_S", 7200) or 0)


def _task_expired(cfg, task):
    deadline = _deadline_seconds(cfg, task)
    if not deadline or not task.created_at:
        return False
    return (_now() - int(task.created_at)) > deadline


def _fail_if_expired(cfg, task_service, task, lease_owner, stage="running"):
    if not _task_expired(cfg, task):
        return False
    task_service.release_generation_lease(
        task.id, lease_owner, status="failed", stage="failed",
        error_code="task_timeout",
        error_message="任务超过最长等待时间；第三方任务 ID 已保留，管理员可恢复轮询",
        completed_at=_now(), completed_at_ms=_now_ms(),
    )
    _audit_task_failure(
        cfg, task, "task_timeout",
        "任务超过最长等待时间；第三方任务 ID 已保留，管理员可恢复轮询",
    )
    return True


def submit_task(cfg, task_service, task, lease_owner):
    """One submission step for an image/video task."""
    user = _user_dict(task.created_by)
    if not user:
        task_service.release_generation_lease(
            task.id, lease_owner, status="failed", error_code="user_missing",
            error_message="任务创建者不存在", completed_at=_now(),
        )
        return
    if _fail_if_expired(cfg, task_service, task, lease_owner, stage="queued"):
        return
    if task.cancel_requested:
        task_service.release_generation_lease(
            task.id, lease_owner, status="cancelled", completed_at=_now(),
            completed_at_ms=_now_ms(), stage="cancelled",
        )
        return

    task_service.update_task(task.id, provider_request_started_at=_now_ms())
    provider = _provider_for_task(cfg, task)
    model = generation_models.get_model(
        cfg, (task.params or {}).get("model_key") or "", include_unavailable=True,
        user=user,
    )
    caps = (model or {}).get("capabilities") or {}
    params = task.params or {}
    reference_ids = params.get("reference_asset_ids") or []
    if not reference_ids and params.get("reference_asset_id"):
        reference_ids = [params.get("reference_asset_id")]
    references = _reference_data_urls(cfg, reference_ids, user)

    try:
        if task.task_type == GenerationTask.TYPE_IMAGE:
            if task.provider == "comfyui":
                prompt_id = provider.submit_generation(
                    prompt=params.get("prompt"),
                    negative_prompt=params.get("negative_prompt"),
                    seed=params.get("seed") if params.get("seed") is not None else -1,
                    width=int(params.get("width") or 1024),
                    height=int(params.get("height") or 1024),
                    quantity=1,
                )
                if not prompt_id:
                    raise MediaFetchError("ComfyUI 未返回任务 ID", "provider_invalid_response")
                task_service.release_generation_lease(
                    task.id, lease_owner, status="running", stage="provider_running",
                    provider_job_id=str(prompt_id), provider_status="queued",
                    submission_uncertain=0,
                    next_retry_at=_now() + cfg.GENERATION_POLL_INTERVAL_S,
                    last_polled_at=_now(), error_code=None, error_message=None,
                    provider_request_finished_at=_now_ms(),
                    provider_job_created_at=_now_ms(),
                )
                return
            size = "{0}x{1}".format(
                int(params.get("width") or 1024), int(params.get("height") or 1024)
            )
            result = provider.generate(
                prompt=params.get("prompt"),
                negative_prompt=params.get("negative_prompt"),
                size=size,
                seed=params.get("seed") if caps.get("supports_seed") else None,
                reference_image_urls=references,
                watermark=bool(params.get("watermark")),
            )
            task_service.update_task(
                task.id,
                provider_request_finished_at=_now_ms(),
                provider_job_created_at=_now_ms(),
                download_started_at=_now_ms(),
            )
            files = _download_image_items(cfg, result.get("images"), _task_dir(cfg, task))
            task_service.update_task(task.id, download_finished_at=_now_ms())
            if not files:
                raise MediaFetchError("Provider 没有返回图片", "empty_output")
            finalize_task(cfg, task_service, task, lease_owner, files, "image")
            return

        # Video submission
        ratio = params.get("ratio") or "16:9"
        duration = int(params.get("duration_s") or 5)
        resolution = params.get("resolution") or "720p"
        if task.provider == "ark_seedance":
            roles = generation_models.reference_image_roles(caps, len(references))
            if roles is None:
                raise ApiError(
                    "invalid_params",
                    "该模型仅支持首帧/尾帧参考，最多 2 张图片",
                    status_code=400,
                )
            generate_audio = (
                bool(params.get("generate_audio"))
                if caps.get("supports_audio") else None
            )
            created = provider.create_generation(
                prompt=params.get("prompt"),
                reference_image_urls=references,
                reference_image_roles=roles,
                aspect_ratio=ratio,
                duration_s=duration,
                resolution=resolution,
                generate_audio=generate_audio,
                watermark=bool(params.get("watermark")),
                seed=params.get("seed") if caps.get("supports_seed") else None,
            )
            provider_job_id = created.get("id") or (created.get("data") or {}).get("id")
        elif task.provider == "atlas_seedance":
            created = provider.create_generation(
                prompt=params.get("prompt"),
                aspect_ratio=ratio,
                duration_s=duration,
                resolution=resolution,
            )
            provider_job_id = (created.get("data") or {}).get("id")
        elif task.provider == "luma":
            keyframes = references if caps.get("supports_reference_image") else []
            created = provider.create_generation(
                prompt=params.get("prompt"),
                aspect_ratio=ratio,
                duration_s=duration,
                resolution=resolution,
                keyframe_urls=keyframes,
            )
            provider_job_id = created.get("id") or created.get("generation_id")
        else:
            raise ApiError("invalid_model", "视频 Provider 不支持", status_code=400)

        if not provider_job_id:
            raise MediaFetchError("Provider 未返回任务 ID", "provider_invalid_response")
        task_service.release_generation_lease(
            task.id, lease_owner, status="running", stage="provider_running",
            provider_job_id=str(provider_job_id), provider_status="queued",
            submission_uncertain=0, next_retry_at=_now() + cfg.GENERATION_POLL_INTERVAL_S,
            last_polled_at=_now(), error_code=None, error_message=None,
            provider_request_finished_at=_now_ms(),
            provider_job_created_at=_now_ms(),
        )
    except ApiError:
        raise
    except Exception as exc:
        _handle_submission_error(cfg, task_service, task, lease_owner, exc)


def _handle_submission_error(cfg, task_service, task, lease_owner, exc):
    error_type = getattr(exc, "error_type", "submission_failed")
    message = str(exc)[:500]
    if error_type in ("submission_uncertain", "image_submission_uncertain", "provider_poll_timeout"):
        task_service.release_generation_lease(
            task.id, lease_owner, status="needs_review", stage="needs_review",
            submission_uncertain=1, error_code="submission_uncertain",
            error_message="提交结果不确定，需人工确认是否已在服务商侧创建任务",
            completed_at=_now(), completed_at_ms=_now_ms(),
            provider_request_finished_at=_now_ms(),
        )
        return
    if error_type == "provider_rate_limited" and (task.attempt_count or 0) < (task.max_attempts or 3):
        task_service.release_generation_lease(
            task.id, lease_owner, status="queued", stage="queued",
            next_retry_at=_now() + 60, error_code=error_type, error_message=message,
            submission_uncertain=0, provider_request_finished_at=_now_ms(),
        )
        return
    task_service.release_generation_lease(
        task.id, lease_owner, status="failed", stage="failed",
        error_code=error_type, error_message=message, completed_at=_now(),
        completed_at_ms=_now_ms(), provider_request_finished_at=_now_ms(),
    )
    _audit_task_failure(cfg, task, error_type, message)


def poll_task(cfg, task_service, task, lease_owner):
    if _fail_if_expired(cfg, task_service, task, lease_owner):
        return
    provider = _provider_for_task(cfg, task)
    if task.cancel_requested:
        cancelled = False
        try:
            if hasattr(provider, "cancel_generation"):
                cancelled = bool(provider.cancel_generation(task.provider_job_id))
        except Exception:
            cancelled = False
        message = None if cancelled else "服务商不支持取消运行中任务，任务可能仍产生费用"
        task_service.release_generation_lease(
            task.id, lease_owner, status="cancelled", stage="cancelled",
            completed_at=_now(), completed_at_ms=_now_ms(),
            error_code=None if cancelled else "cancel_not_guaranteed",
            error_message=message,
        )
        return

    try:
        if task.provider == "comfyui":
            history = provider.poll_generation(task.provider_job_id)
            entry = (history or {}).get(task.provider_job_id)
            if not entry:
                task_service.release_generation_lease(
                    task.id, lease_owner, status="running", stage="provider_running",
                    provider_status="running",
                    next_retry_at=_now() + cfg.GENERATION_POLL_INTERVAL_S,
                    last_polled_at=_now(),
                )
                return
            task_service.update_task(
                task.id,
                provider_finished_at=_now_ms(),
                download_started_at=_now_ms(),
            )
            files = provider.download_results_from_history(
                entry,
                _task_dir(cfg, task),
                max_bytes=cfg.MAX_GENERATION_DOWNLOAD_MB * 1024 * 1024,
            )
            task_service.update_task(task.id, download_finished_at=_now_ms())
            if not files:
                raise MediaFetchError("ComfyUI 没有返回图片", "empty_output")
            finalize_task(cfg, task_service, task, lease_owner, files, "image")
            return

        if task.provider == "ark_seedance":
            data = provider.get_generation(task.provider_job_id)
            status = provider.extract_status(data)
        elif task.provider == "atlas_seedance":
            data = provider.get_generation(task.provider_job_id)
            status = str(provider.extract_status(data) or "unknown").lower()
        elif task.provider == "luma":
            data = provider.get_generation(task.provider_job_id)
            status = str(provider.extract_status(data) or "unknown").lower()
        else:
            raise MediaFetchError("未知视频 Provider", "unsupported_provider")

        if status in ("queued", "pending", "running", "processing", "dreaming", "generating"):
            task_service.release_generation_lease(
                task.id, lease_owner, status="running", stage="provider_running",
                provider_status=status, next_retry_at=_now() + cfg.GENERATION_POLL_INTERVAL_S,
                last_polled_at=_now(),
            )
            return

        if status in ("succeeded", "success", "completed", "done"):
            if task.provider == "ark_seedance":
                video_url = provider.extract_video_url(data)
            elif task.provider == "atlas_seedance":
                video_url = provider.extract_video_url(data)
            else:
                video_url = provider.extract_video_url(data)
            if not video_url:
                raise MediaFetchError("Provider 成功响应缺少视频地址", "provider_invalid_response")
            task_service.update_task(
                task.id,
                provider_finished_at=_now_ms(),
                download_started_at=_now_ms(),
            )
            path = _download_video(cfg, video_url, _task_dir(cfg, task))
            task_service.update_task(task.id, download_finished_at=_now_ms())
            finalize_task(cfg, task_service, task, lease_owner, [path], "video")
            return

        if status in ("failed", "error", "expired", "cancelled", "canceled"):
            if status in ("cancelled", "canceled"):
                task_service.release_generation_lease(
                    task.id, lease_owner, status="cancelled", stage="cancelled",
                    completed_at=_now(), completed_at_ms=_now_ms(),
                    provider_finished_at=_now_ms(),
                )
            else:
                error = {"code": "provider_failed", "message": "视频生成失败"}
                if hasattr(provider, "extract_error"):
                    error = provider.extract_error(data)
                error_message = str(error.get("message") or "视频生成失败")
                if error.get("request_id"):
                    error_message = "{0}（请求 ID: {1}）".format(
                        error_message, error.get("request_id")
                    )
                error_code = str(error.get("code") or "provider_failed")[:80]
                task_service.release_generation_lease(
                    task.id, lease_owner, status="failed", stage="failed",
                    error_code=error_code,
                    error_message=error_message[:500],
                    completed_at=_now(), completed_at_ms=_now_ms(),
                    provider_finished_at=_now_ms(),
                )
                _audit_task_failure(cfg, task, error_code, error_message)
            return

        raise MediaFetchError("未知的 Provider 状态: {0}".format(status), "provider_unknown_status")
    except Exception as exc:
        _handle_poll_error(cfg, task_service, task, lease_owner, exc)


def _handle_poll_error(cfg, task_service, task, lease_owner, exc):
    attempt = int(task.poll_error_count or 0) + 1
    message = str(exc)[:500]
    if attempt < cfg.GENERATION_POLL_MAX_ERRORS:
        task_service.release_generation_lease(
            task.id, lease_owner, status="running", stage="provider_running",
            poll_error_count=attempt, next_retry_at=_now() + min(600, 10 * (2 ** attempt)),
            error_code=getattr(exc, "code", None) or getattr(exc, "error_type", "poll_error"),
            error_message=message, last_polled_at=_now(),
        )
        return
    error_code = getattr(exc, "code", None) or getattr(exc, "error_type", "poll_error")
    task_service.release_generation_lease(
        task.id, lease_owner, status="failed", stage="failed",
        poll_error_count=attempt, error_code=error_code,
        error_message=message, completed_at=_now(), completed_at_ms=_now_ms(),
    )
    _audit_task_failure(cfg, task, error_code, message)


class _LeaseLost(Exception):
    """Raised inside a finalize transaction when the worker lease is gone."""


def _prepare_output_file(asset_service, path):
    rel_path = os.path.relpath(path, asset_service.assets_dir)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    digest = None
    if os.path.exists(path):
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    return {"path": path, "rel_path": rel_path, "size": size, "digest": digest}


def finalize_task(cfg, task_service, task, lease_owner, files, kind):
    """Persist generated files, task result, artifacts and shot linkage atomically.

    The lease-guarded task update and every DB insert share one transaction.  A
    lost lease rolls the whole DB change back and removes the downloaded files,
    so no orphan asset/artifact rows survive.
    """
    asset_service = get_asset_service(cfg.DATA_DIR)
    tenant_id = _tenant_for_user(task.created_by)
    owner_user_id = task.created_by
    if task.creative_project_id:
        project_row = get_database().fetch_one(
            "SELECT user_id, tenant_id FROM creative_projects WHERE id = ?",
            (task.creative_project_id,),
        )
        if project_row and project_row.get("user_id"):
            owner_user_id = project_row["user_id"]
            tenant_id = project_row.get("tenant_id") or tenant_id
    persist_started_at = _now_ms()
    prepared = []
    for path in files:
        if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise MediaFetchError(
                "生成文件缺失或为空，未写入素材库", "empty_output"
            )
        prepared.append(_prepare_output_file(asset_service, path))
    prompt = (task.params or {}).get("prompt") or "Generated result"
    generation_params = dict(task.params or {})
    created_assets = []
    created_paths = [item["path"] for item in prepared]

    try:
        with task_service.db.transaction() as cursor:
            # Confirm we still own the lease before doing any work.
            cursor.execute(
                "UPDATE generation_tasks SET updated_at = ? WHERE id = ? AND lease_owner = ?",
                (_now(), task.id, lease_owner),
            )
            if cursor.rowcount != 1:
                raise _LeaseLost()

            for item in prepared:
                asset = asset_service.create_asset(
                    name="{0} {1}".format(
                        "图片" if kind == "image" else "视频",
                        prompt[:60],
                    ),
                    asset_type=kind,
                    file_path=item["rel_path"],
                    file_size=item["size"],
                    description=prompt[:500],
                    metadata={
                        "source": "generation",
                        "task_id": task.id,
                        "provider": task.provider,
                        "model_id": task.model_id,
                        "generation_params": generation_params,
                    },
                    owner_user_id=owner_user_id,
                    tenant_id=tenant_id,
                    visibility="private",
                    checksum_sha256=item["digest"],
                    cursor=cursor,
                )
                created_assets.append(asset)
                task_service.add_artifact(
                    task_id=task.id,
                    creative_project_id=task.creative_project_id,
                    name=os.path.basename(item["path"]),
                    artifact_type=kind,
                    file_path=os.path.relpath(item["path"], cfg.DATA_DIR),
                    file_size=item["size"],
                    asset_id=asset.id,
                    metadata={"provider": task.provider, "model_id": task.model_id},
                    cursor=cursor,
                )

            output_asset_id = created_assets[0].id if created_assets else None
            result_payload = {
                "provider": task.provider,
                "model_id": task.model_id,
                "provider_job_id": task.provider_job_id,
                "asset_ids": [asset.id for asset in created_assets],
                "output_asset_id": output_asset_id,
            }
            affected = task_service.release_generation_lease(
                task.id, lease_owner, cursor=cursor,
                status="succeeded", stage="succeeded",
                progress=100, result_payload=result_payload,
                output_asset_id=output_asset_id,
                completed_at=_now(), completed_at_ms=_now_ms(),
                persist_started_at=persist_started_at,
                persist_finished_at=_now_ms(),
                error_code=None, error_message=None,
                submission_uncertain=0,
            )
            if not affected:
                raise _LeaseLost()

            if task.target_shot_id:
                cursor.execute(
                    "SELECT * FROM storyboard_shots WHERE id = ?", (task.target_shot_id,)
                )
                row = cursor.fetchone()
                shot = StoryboardShot.from_row(dict(row)) if row else None
                if shot:
                    # Preserve an explicit user confirmation; a generated asset
                    # otherwise makes the shot ready for the next step.
                    next_status = (
                        StoryboardShot.STATUS_CONFIRMED
                        if shot.status == StoryboardShot.STATUS_CONFIRMED
                        else StoryboardShot.STATUS_READY
                    )
                    if kind == "image":
                        get_storyboard_service().update_shot(
                            shot.id, cursor=cursor,
                            primary_image_asset_id=output_asset_id,
                            status=next_status,
                        )
                    else:
                        get_storyboard_service().update_shot(
                            shot.id, cursor=cursor,
                            video_asset_id=output_asset_id,
                            selected_video_asset_id=output_asset_id,
                            video_selection_source="original",
                            video_url=(
                                "/api/assets/{0}/file".format(output_asset_id)
                                if output_asset_id else None
                            ),
                            status=next_status,
                        )
                        cursor.execute(
                            "UPDATE shot_media_versions SET is_selected = 0, updated_at = ? "
                            "WHERE shot_id = ? AND media_kind = 'video'",
                            (_now(), shot.id),
                        )
                        version = ShotMediaVersion(
                            creative_project_id=shot.creative_project_id,
                            shot_id=shot.id,
                            media_kind="video",
                            asset_id=output_asset_id,
                            task_id=task.id,
                            source="generation",
                            label="AI 生成视频",
                            metadata={
                                "provider": task.provider,
                                "model_id": task.model_id,
                                "generation_params": generation_params,
                            },
                            is_selected=1,
                            created_at=_now(),
                            updated_at=_now(),
                        )
                        columns = list(version.to_insert_params().keys())
                        params = version.to_insert_params()
                        cursor.execute(
                            "INSERT INTO shot_media_versions ({0}) VALUES ({1})".format(
                                ", ".join(columns), ", ".join("?" for _ in columns)
                            ),
                            tuple(params[column] for column in columns),
                        )
    except _LeaseLost:
        for path in created_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        logger.warning("Lease lost while finalizing task %s; rolled back output", task.id)
        return
    except Exception:
        for path in created_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise

    _audit(cfg, "generation_succeeded", _user_dict(task.created_by), task.id, result_payload)


def cancel_provider_job(cfg, task):
    """Best-effort cancellation of a failed task's provider job."""
    if not task or not task.provider_job_id:
        return {"attempted": False, "succeeded": False}
    try:
        provider = _provider_for_task(cfg, task)
    except Exception:
        logger.warning(
            "Could not build provider for task %s while deleting; provider job left untouched",
            task.id,
        )
        return {"attempted": False, "succeeded": False}
    if not hasattr(provider, "cancel_generation"):
        return {"attempted": False, "succeeded": False}
    try:
        succeeded = bool(provider.cancel_generation(task.provider_job_id))
    except Exception:
        logger.warning(
            "Provider cancellation failed for task %s", task.id, exc_info=True
        )
        succeeded = False
    return {"attempted": True, "succeeded": succeeded}


def remove_task_directory(cfg, task):
    """Remove a generation task's downloaded files without recreating paths."""
    if not task:
        return False
    base = os.path.realpath(os.path.join(cfg.DATA_DIR, "assets", "generated"))
    path = os.path.realpath(
        os.path.join(base, str(task.created_by or "unknown"), str(task.id))
    )
    if path == base or not path.startswith(base + os.sep):
        logger.warning("Refusing to remove out-of-tree task directory: %s", path)
        return False
    if not os.path.isdir(path):
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def get_storyboard_service():
    from .storyboard_service import get_storyboard_service as _get
    return _get()
