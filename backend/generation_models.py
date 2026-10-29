# -*- coding: utf-8 -*-
"""Server-side model registry and availability for generation UI/APIs.

Model IDs are based on the Volcengine Ark documentation and can be overridden
with ``ARK_IMAGE_MODEL`` / ``ARK_VIDEO_MODEL`` style environment variables.
``verified`` stays false until a real call has been performed against the
configured account; availability only means "credentials are configured".
"""
from __future__ import absolute_import

import logging
import time

from .credential_service import CredentialError, CredentialService

logger = logging.getLogger(__name__)

_COMFYUI_CACHE = {"checked_at": 0, "available": None, "reason": None}

_VERIFICATION_NOTE = (
    "未进行真实 API 调用验证；请以火山方舟控制台实际开通的模型 ID 为准"
)
_OPENAI_VERIFICATION_NOTE = (
    "未进行真实 API 调用验证；模型 ID 以 OpenAI 账户可用的图片模型为准"
)
_SETTINGS_HINT = "（请前往 /api-settings 配置）"

_COMMON_RATIOS = ["1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]
_VIDEO_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"]
_MAX30_DURATIONS = [4, 5, 6, 8, 10, 12, 15, 20, 30]


def _model(key, provider, model_id, display_name, task_type, capabilities,
           env_key=None, default=False, verification_note=_VERIFICATION_NOTE):
    return {
        "key": key,
        "provider": provider,
        "model_id": model_id,
        "display_name": display_name,
        "task_type": task_type,
        "capabilities": capabilities,
        "env_key": env_key,
        "default": default,
        "verification_note": verification_note,
    }


def _image_caps(sizes, max_reference_images, pixel_range, default_size):
    return {
        "sizes": list(sizes),
        "ratios": list(_COMMON_RATIOS),
        "supports_reference_image": max_reference_images > 0,
        "max_reference_images": int(max_reference_images),
        "supports_negative_prompt": False,
        "supports_watermark": True,
        "supports_seed": False,
        "supports_custom_size": True,
        "max_images": 1,
        "pixel_range": list(pixel_range) if pixel_range else None,
        "default_size": default_size,
        "default_ratio": "1:1",
    }


def _video_caps(durations, resolutions, max_reference_images, supports_audio,
                supports_seed, supports_cancel, default_audio=False):
    return {
        "ratios": list(_VIDEO_RATIOS),
        "durations": list(durations),
        "resolutions": list(resolutions),
        "supports_reference_image": max_reference_images > 0,
        "max_reference_images": int(max_reference_images),
        "supports_negative_prompt": False,
        "supports_audio": bool(supports_audio),
        "default_audio": bool(default_audio),
        "supports_seed": bool(supports_seed),
        "supports_watermark": True,
        "supports_cancel": bool(supports_cancel),
        "cancel_note": "仅排队中任务可取消；运行中任务可能仍产生费用" if supports_cancel else "该服务商不支持取消",
    }


MODELS = [
    _model(
        "ark_seedream_pro", "ark_seedream", "doubao-seedream-5-0-pro-260628",
        "Seedream 5.0 Pro（火山方舟）", "image",
        _image_caps(["1K", "1.5K", "2K"], 10, (921600, 4624220), "2K"),
        env_key="ARK_API_KEY", default=True,
    ),
    _model(
        "ark_seedream_lite", "ark_seedream", "doubao-seedream-5-0-lite-260128",
        "Seedream 5.0 Lite（火山方舟）", "image",
        _image_caps(["2K", "3K", "4K"], 14, (3686400, 16777216), "2K"),
        env_key="ARK_API_KEY",
    ),
    _model(
        "comfyui_default", "comfyui", "default",
        "ComfyUI 本地工作流", "image", {
            "sizes": ["1K", "2K", "4K"],
            "ratios": list(_COMMON_RATIOS),
            "supports_reference_image": False,
            "max_reference_images": 0,
            "supports_negative_prompt": True,
            "supports_watermark": False,
            "supports_seed": True,
            "supports_custom_size": True,
            "max_images": 1,
            "pixel_range": None,
            "default_size": "1K",
            "default_ratio": "1:1",
        }, env_key="COMFYUI_BASE_URL",
    ),
    _model(
        "openai_gpt_image_1", "openai_image", "gpt-image-1",
        "GPT Image 1（OpenAI）", "image", {
            "sizes": ["1K", "1.5K"],
            "default_size": "1K",
            "default_ratio": "1:1",
            "supports_custom_size": True,
            "supports_reference_image": False,
            "max_reference_images": 0,
            "supports_negative_prompt": False,
            "supports_watermark": False,
            "supports_seed": False,
            "max_images": 1,
            "ratios": list(_COMMON_RATIOS),
            "pixel_range": None,
        }, env_key="OPENAI_API_KEY",
        verification_note=_OPENAI_VERIFICATION_NOTE,
    ),
    _model(
        "ark_seedance_25", "ark_seedance", "doubao-seedance-2-5-260628",
        "Seedance 2.5（火山方舟）", "video",
        _video_caps(_MAX30_DURATIONS, ["480p", "720p", "1080p"], 30,
                    supports_audio=True, supports_seed=True,
                    supports_cancel=True, default_audio=True),
        env_key="ARK_API_KEY", default=True,
    ),
    _model(
        "ark_seedance_20", "ark_seedance", "doubao-seedance-2-0-260128",
        "Seedance 2.0（火山方舟）", "video",
        _video_caps([4, 5, 8, 10, 12], ["480p", "720p", "1080p"], 1,
                    supports_audio=False, supports_seed=True, supports_cancel=True),
        env_key="ARK_API_KEY",
    ),
    _model(
        "ark_seedance_10_pro", "ark_seedance", "doubao-seedance-1-0-pro-250528",
        "Seedance 1.0 Pro（火山方舟）", "video",
        _video_caps([5, 10], ["480p", "720p", "1080p"], 1,
                    supports_audio=False, supports_seed=True, supports_cancel=True),
        env_key="ARK_API_KEY",
    ),
    _model(
        "atlas_seedance_default", "atlas_seedance", "atlas-default",
        "Atlas Cloud Seedance（兼容通道）", "video",
        _video_caps([4, 5, 8], ["720p"], 0,
                    supports_audio=False, supports_seed=False, supports_cancel=False),
        env_key="SEEDANCE_API_KEY",
        verification_note="旧版 Atlas Cloud 兼容适配，未进行真实调用验证",
    ),
    _model(
        "luma_default", "luma", "luma-default",
        "Luma Dream Machine", "video",
        _video_caps([5, 9], ["720p"], 0,
                    supports_audio=False, supports_seed=False, supports_cancel=False),
        env_key="LUMA_API_KEY",
        verification_note="Luma 适配未进行真实调用验证；不支持参考图片",
    ),
]


# UI model key -> Config attribute holding the real Ark model ID.
_CONFIG_MODEL_OVERRIDES = {
    "ark_seedream_pro": "ARK_IMAGE_MODEL",
    "ark_seedream_lite": "ARK_IMAGE_MODEL_LITE",
    "ark_seedance_25": "ARK_VIDEO_MODEL",
    "ark_seedance_20": "ARK_VIDEO_MODEL_20",
    "ark_seedance_10_pro": "ARK_VIDEO_MODEL_10_PRO",
    "atlas_seedance_default": "SEEDANCE_MODEL_NAME",
    "luma_default": "LUMA_MODEL_NAME",
    "openai_gpt_image_1": "OPENAI_IMAGE_MODEL",
}

# Registry provider -> per-user credential provider.
_CREDENTIAL_PROVIDER_BY_MODEL_PROVIDER = {
    "ark_seedream": "ark",
    "ark_seedance": "ark",
    "openai_image": "openai_image",
    "atlas_seedance": "atlas_seedance",
    "luma": "luma",
}


def _user_id(user):
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _credential_provider(model):
    return _CREDENTIAL_PROVIDER_BY_MODEL_PROVIDER.get(model.get("provider"))


def _effective_credentials(cfg, model, user):
    """Resolve the user's effective credentials, never raising."""
    provider = _credential_provider(model)
    if not provider or not user:
        return None
    try:
        return CredentialService(cfg.DATA_DIR, cfg).effective(
            _user_id(user), provider, cfg
        )
    except CredentialError:
        # Availability explains the problem; model resolution keeps going.
        return None


def _with_config(cfg, model, user=None):
    item = dict(model)
    item["capabilities"] = dict(model.get("capabilities") or {})
    attr = _CONFIG_MODEL_OVERRIDES.get(model["key"])
    configured = getattr(cfg, attr, None) if attr else None
    if configured:
        item["model_id"] = configured
    effective = _effective_credentials(cfg, model, user)
    if effective:
        if model["provider"] in ("ark_seedream", "ark_seedance"):
            override = (effective.get("model_overrides") or {}).get(model["key"])
        else:
            override = effective.get("model")
        if override:
            item["model_id"] = override
    return item


def _comfyui_status(cfg):
    if not getattr(cfg, "COMFYUI_ENABLED", False) or not getattr(cfg, "COMFYUI_BASE_URL", ""):
        return False, "ComfyUI 未启用或未配置地址"
    now = time.time()
    if _COMFYUI_CACHE["available"] is not None and now - _COMFYUI_CACHE["checked_at"] < 30:
        return _COMFYUI_CACHE["available"], _COMFYUI_CACHE["reason"]
    try:
        import requests
        response = requests.get(
            "{0}/system_stats".format(cfg.COMFYUI_BASE_URL.rstrip("/")),
            timeout=2,
        )
        available = response.status_code < 400
        reason = None if available else "ComfyUI 返回 HTTP {0}".format(response.status_code)
    except Exception as exc:
        available = False
        reason = "ComfyUI 不可达: {0}".format(str(exc)[:160])
    _COMFYUI_CACHE.update({"checked_at": now, "available": available, "reason": reason})
    return available, reason


def _availability(cfg, model, user=None):
    provider = model["provider"]
    if provider == "comfyui":
        return _comfyui_status(cfg)
    cred_provider = _credential_provider(model)
    if user and cred_provider:
        available, reason = CredentialService(cfg.DATA_DIR, cfg).has_provider(
            _user_id(user), cred_provider, cfg
        )
        if not available:
            reason = "{0}{1}".format(reason or "Provider 凭据不可用", _SETTINGS_HINT)
        return available, reason
    env_key = model.get("env_key")
    if env_key and getattr(cfg, env_key, ""):
        return True, None
    return False, "未配置 {0}{1}".format(env_key or "Provider 凭据", _SETTINGS_HINT)


def _credential_source(cfg, model, user):
    provider = _credential_provider(model)
    if not provider:
        return None
    try:
        effective = CredentialService(cfg.DATA_DIR, cfg).effective(
            _user_id(user), provider, cfg
        )
    except CredentialError:
        return None
    return effective.get("source")


def get_model(cfg, key, include_unavailable=True, user=None):
    for model in MODELS:
        if model["key"] == key:
            item = _with_config(cfg, model, user=user)
            available, reason = _availability(cfg, model, user=user)
            item["available"] = available
            item["unavailable_reason"] = reason
            item["credential_source"] = _credential_source(cfg, model, user)
            item["verified"] = False
            if not available:
                item["configure_url"] = "/api-settings"
            if not available and not include_unavailable:
                return None
            return item
    return None


def list_models(cfg, task_type=None, include_unavailable=True, user=None):
    items = []
    for model in MODELS:
        if task_type and model["task_type"] != task_type:
            continue
        item = get_model(cfg, model["key"], include_unavailable=True, user=user)
        if not item:
            continue
        if not item["available"] and not include_unavailable:
            continue
        items.append(item)
    # Pick a default per type from the available models.
    for wanted_type in ("image", "video"):
        available = [m for m in items if m["task_type"] == wanted_type and m["available"]]
        for model in items:
            if model["task_type"] == wanted_type:
                model["default"] = bool(available and model["key"] == available[0]["key"])
    return items
