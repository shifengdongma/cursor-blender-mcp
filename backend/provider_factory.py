# -*- coding: utf-8 -*-
"""Construct provider clients from already-resolved credentials."""
from __future__ import absolute_import

from .http_utils import ApiError


def create_provider(cfg, provider_name, api_key, base_url, model_id=None):
    """Build a provider client without resolving credentials itself."""
    provider_name = (provider_name or "").strip().lower()
    if provider_name == "openai_image":
        from .providers.openai_image import OpenAIImageProvider
        return OpenAIImageProvider(
            api_key=api_key,
            base_url=base_url,
            model_id=model_id or getattr(cfg, "OPENAI_IMAGE_MODEL", "gpt-image-1"),
        )
    if provider_name == "ark_seedream":
        from .providers.volcengine_image import VolcengineImageProvider
        return VolcengineImageProvider(
            api_key=api_key,
            base_url=base_url,
            model_id=model_id,
            timeout_s=getattr(cfg, "ARK_REQUEST_TIMEOUT_S", 180),
        )
    if provider_name == "ark_seedance":
        from .providers.volcengine_video import VolcengineVideoProvider
        return VolcengineVideoProvider(
            api_key=api_key,
            base_url=base_url,
            model_id=model_id,
            timeout_s=getattr(cfg, "ARK_REQUEST_TIMEOUT_S", 180),
        )
    if provider_name == "atlas_seedance":
        from .providers.seedance import SeedanceProvider
        return SeedanceProvider(
            api_key=api_key,
            base_url=base_url,
            model_name=model_id or getattr(cfg, "SEEDANCE_MODEL_NAME", None),
        )
    if provider_name == "luma":
        from .providers.luma import LumaProvider
        return LumaProvider(
            api_key=api_key,
            base_url=base_url,
            model_name=model_id or getattr(cfg, "LUMA_MODEL_NAME", "ray-2"),
        )
    if provider_name == "comfyui":
        from .providers.image_provider import ComfyUIProvider
        return ComfyUIProvider(
            base_url=cfg.COMFYUI_BASE_URL,
            workflow_file=cfg.COMFYUI_WORKFLOW_FILE,
        )
    raise ApiError("invalid_model", "无法创建 Provider 客户端", status_code=400)
