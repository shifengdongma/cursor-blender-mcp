# -*- coding: utf-8 -*-
"""Explicit, user-triggered real provider generation tests.

These calls are billable.  The HTTP route requires ``confirm_billing: true``
before this module is invoked.  Image tests generate one minimal image; video
tests create the shortest supported task and immediately attempt cancellation.
Nothing is written to the asset library or task tables.
"""
from __future__ import absolute_import

import logging

from . import generation_models
from .credential_service import CredentialError, CredentialService
from .http_utils import ApiError
from .provider_factory import create_provider
from .providers.base import ProviderError

logger = logging.getLogger(__name__)

TEST_IMAGE_PROMPT = "A simple gray cube on a white background, minimal product photo."
TEST_VIDEO_PROMPT = "A slow, steady camera pan across an empty gray studio."

_CREDENTIAL_PROVIDER_BY_MODEL_PROVIDER = {
    "ark_seedream": "ark",
    "ark_seedance": "ark",
    "openai_image": "openai_image",
    "atlas_seedance": "atlas_seedance",
    "luma": "luma",
}
_SUPPORTED_PROVIDERS = {"ark", "openai_image", "atlas_seedance", "luma"}


def _resolve_model(cfg, user, provider, model_key):
    model = generation_models.get_model(
        cfg, model_key, include_unavailable=True, user=user
    )
    if not model:
        raise ApiError("invalid_model", "未知的生成模型", status_code=400)
    mapped = _CREDENTIAL_PROVIDER_BY_MODEL_PROVIDER.get(model.get("provider"))
    if mapped != provider:
        raise ApiError(
            "invalid_model",
            "模型 {0} 不属于 Provider {1}".format(model_key, provider),
            status_code=400,
        )
    if model.get("task_type") not in ("image", "video"):
        raise ApiError("invalid_model", "该模型不支持图片/视频生成测试", status_code=400)
    if not model.get("model_id"):
        raise ApiError("invalid_model", "模型 ID 为空，请检查模型配置", status_code=400)
    return model


def _base_result(model, provider, task_type):
    return {
        "status": "failed",
        "task_type": task_type,
        "provider": provider,
        "model_key": model["key"],
        "model_id": model.get("model_id"),
        "model_id_source": model.get("model_id_source"),
        "error_code": None,
        "provider_code": None,
        "provider_request_id": None,
        "message": "",
    }


def _image_test(cfg, client, model, provider):
    caps = model.get("capabilities") or {}
    sizes = caps.get("sizes") or ["1K"]
    size = sizes[0] if sizes else "1K"
    result = _base_result(model, provider, "image")
    generated = client.generate(
        prompt=TEST_IMAGE_PROMPT,
        size=size,
        watermark=False,
    )
    images = generated.get("images") or []
    if not images:
        result["error_code"] = "provider_invalid_response"
        result["message"] = "模型未返回图片，无法确认生成成功"
        return result
    first = images[0]
    result.update({
        "status": "succeeded",
        "size": size,
        "image_count": len(images),
        "image_url": first.get("url") if isinstance(first, dict) else None,
        "image_b64_present": bool(isinstance(first, dict) and first.get("b64_json")),
        "provider_request_id": generated.get("request_id"),
        "message": "真实图片生成成功（已实际调用模型并返回图片）。",
    })
    return result


def _video_test(cfg, client, model, provider):
    caps = model.get("capabilities") or {}
    duration_range = caps.get("duration_range")
    if duration_range:
        duration = int(duration_range[0])
    else:
        durations = caps.get("durations") or [5]
        duration = int(min(durations))
    resolutions = caps.get("resolutions") or ["720p"]
    resolution = "480p" if "480p" in resolutions else resolutions[0]
    ratios = caps.get("ratios") or ["16:9"]
    ratio = "16:9" if "16:9" in ratios else ratios[0]
    generate_audio = False if caps.get("supports_audio") else None

    result = _base_result(model, provider, "video")
    provider_name = model.get("provider")
    if provider_name == "ark_seedance":
        created = client.create_generation(
            prompt=TEST_VIDEO_PROMPT,
            aspect_ratio=ratio,
            duration_s=duration,
            resolution=resolution,
            generate_audio=generate_audio,
            watermark=False,
        )
        provider_job_id = created.get("id") or (created.get("data") or {}).get("id")
    elif provider_name == "atlas_seedance":
        created = client.create_generation(
            prompt=TEST_VIDEO_PROMPT,
            aspect_ratio=ratio,
            duration_s=duration,
            resolution=resolution,
        )
        provider_job_id = (created.get("data") or {}).get("id")
    elif provider_name == "luma":
        created = client.create_generation(
            prompt=TEST_VIDEO_PROMPT,
            aspect_ratio=ratio,
            duration_s=duration,
            resolution=resolution,
        )
        provider_job_id = created.get("id") or created.get("generation_id")
    else:
        result["error_code"] = "unsupported_provider"
        result["message"] = "该模型不支持视频创建测试"
        return result

    if not provider_job_id:
        result["error_code"] = "provider_invalid_response"
        result["message"] = "服务商未返回任务 ID，无法确认任务已创建"
        return result

    cancel_attempted = hasattr(client, "cancel_generation")
    cancel_accepted = False
    if cancel_attempted:
        try:
            cancel_accepted = bool(client.cancel_generation(provider_job_id))
        except Exception:
            cancel_accepted = False

    if cancel_attempted and cancel_accepted:
        cancel_message = "已立即请求取消。"
    elif cancel_attempted:
        cancel_message = "已请求取消，但取消未被服务商确认，任务仍可能继续产生费用。"
    else:
        cancel_message = "该服务商不支持取消，任务将继续运行并可能产生费用。"

    result.update({
        "status": "accepted",
        "provider_job_id": provider_job_id,
        "duration_s": duration,
        "resolution": resolution,
        "ratio": ratio,
        "generate_audio": generate_audio,
        "cancel_attempted": cancel_attempted,
        "cancel_accepted": cancel_accepted,
        "provider_request_id": created.get("_request_id") or created.get("request_id"),
        "message": (
            "视频任务已真实创建（不等于生成完成）。{0}"
            "请到服务商控制台核对任务与费用。".format(cancel_message)
        ),
    })
    return result


def run_generation_test(cfg, user, provider, model_key, credential_service=None):
    provider = (provider or "").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise ApiError(
            "test_not_supported",
            "该 Provider 不支持真实图片/视频生成测试；请使用“测试连接”或配置生成模型",
            status_code=400,
        )
    service = credential_service or CredentialService(cfg.DATA_DIR, cfg)
    try:
        effective = service.effective(user.get("id"), provider, cfg)
    except CredentialError as exc:
        raise ApiError(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
    if not effective.get("api_key") or not effective.get("source"):
        raise ApiError(
            "provider_not_configured",
            "该 Provider 尚未配置 API Key，无法发起真实调用",
            status_code=400,
            details={"configure_url": "/api-settings"},
        )
    base_url = effective.get("base_url")
    if effective.get("source") == "user":
        try:
            base_url = service.validate_base_url(base_url, cfg)
        except CredentialError as exc:
            raise ApiError(exc.code, exc.message, status_code=exc.status_code, details=exc.details)

    model = _resolve_model(cfg, user, provider, model_key)
    client = create_provider(
        cfg, model.get("provider"), effective.get("api_key"), base_url,
        model.get("model_id"),
    )
    task_type = model.get("task_type")
    try:
        if task_type == "image":
            result = _image_test(cfg, client, model, provider)
        else:
            result = _video_test(cfg, client, model, provider)
    except ProviderError as exc:
        result = _base_result(model, provider, task_type)
        result.update({
            "error_code": exc.error_type,
            "provider_code": exc.provider_code,
            "provider_request_id": exc.request_id,
            "provider_status_code": exc.status_code,
            "retry_after_s": exc.retry_after_s,
            "message": str(exc),
        })
    except Exception:
        logger.exception(
            "Real provider test failed for %s/%s", provider, model.get("key")
        )
        result = _base_result(model, provider, task_type)
        result.update({
            "error_code": "provider_test_failed",
            "message": "真实调用测试失败，请稍后重试；如持续失败请检查 Base URL 与模型配置",
        })

    if result.get("status") in ("succeeded", "accepted"):
        timestamp = service.record_verification(
            user.get("id"),
            provider,
            model.get("key"),
            model.get("model_id"),
            result.get("status"),
            request_id=result.get("provider_request_id"),
        )
    else:
        row = service.get_record(user.get("id"), provider)
        timestamp = row.get("last_verified_at") if row else None
    result["last_verified_at"] = timestamp
    return result
