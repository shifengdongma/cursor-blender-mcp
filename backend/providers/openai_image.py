# -*- coding: utf-8 -*-
"""OpenAI Images generation provider (synchronous API)."""
from __future__ import absolute_import

import logging

import requests

from .base import (
    ProviderAuthError,
    ProviderError,
    ProviderRejected,
    ProviderUncertain,
    scrub_secret,
)
from .errors import extract_request_id, provider_http_error

logger = logging.getLogger(__name__)

# OpenAI gpt-image-1 only accepts these three sizes.
_SQUARE = "1024x1024"
_LANDSCAPE = "1536x1024"
_PORTRAIT = "1024x1536"


def normalize_size(size):
    """Map any ``WxH`` request to an OpenAI-supported size by orientation.

    Unparseable values fall back to the square size so the adapter never
    forwards an unsupported dimension to the API.
    """
    try:
        width, height = [
            int(part) for part in str(size or "").strip().lower().split("x", 1)
        ]
    except (TypeError, ValueError):
        return _SQUARE
    if width <= 0 or height <= 0:
        return _SQUARE
    if width > height:
        return _LANDSCAPE
    if height > width:
        return _PORTRAIT
    return _SQUARE


class OpenAIImageProvider(object):
    def __init__(self, api_key, base_url, model_id, timeout_s=180):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.model_id = model_id
        self.timeout_s = timeout_s

    def _headers(self):
        return {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

    def _safe_error(self, response):
        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}
        error = payload.get("error") or {}
        if isinstance(error, dict):
            message = error.get("message")
        else:
            message = None
        message = message or payload.get("message") or response.text or ""
        # Defence in depth: never echo the bearer token even if a provider
        # mirrors request headers into its error body.
        return scrub_secret(str(message)[:500], self.api_key)

    def generate(self, prompt, negative_prompt=None, size="1024x1024", seed=None,
                 reference_image_urls=None, watermark=False, response_format="b64_json"):
        if not self.api_key:
            raise ProviderAuthError(
                "OPENAI_API_KEY 未配置", error_type="missing_api_key"
            )
        if not prompt:
            raise ProviderRejected("图片提示词不能为空", error_type="invalid_prompt")
        if reference_image_urls:
            # gpt-image-1 edit/reference flows are out of scope; the model
            # capabilities already forbid this, so reject defensively.
            raise ProviderRejected(
                "OpenAI 图片模型暂不支持参考图片", error_type="unsupported_reference_image"
            )

        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "size": normalize_size(size),
            "n": 1,
        }
        # gpt-image-* always returns b64_json and rejects ``response_format``
        # with HTTP 400; only older DALL·E models accept the field.
        if not str(self.model_id or "").startswith("gpt-image-"):
            payload["response_format"] = response_format or "b64_json"

        url = self.base_url + "/images/generations"
        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout_s,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderUncertain(
                "OpenAI 图片请求超时，生成结果不确定",
                error_type="image_submission_uncertain",
            )
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUncertain(
                "OpenAI 图片连接失败: {0}".format(str(exc)[:200]),
                error_type="image_submission_uncertain",
            )

        mapped = provider_http_error(
            response, self.api_key, "OpenAI 图片", model_id=self.model_id,
            uncertain_error_type="image_submission_uncertain",
        )
        if mapped is not None:
            raise mapped

        try:
            data = response.json() or {}
        except ValueError:
            raise ProviderError(
                "OpenAI 图片返回非 JSON", error_type="provider_invalid_response"
            )

        images = []
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                images.append({"url": item["url"]})
            elif item.get("b64_json"):
                images.append({"b64_json": item["b64_json"]})
        if not images:
            raise ProviderError(
                "OpenAI 图片响应没有图片", error_type="provider_invalid_response"
            )
        return {
            "images": images,
            "created": data.get("created"),
            "request_id": extract_request_id(response, data),
        }
