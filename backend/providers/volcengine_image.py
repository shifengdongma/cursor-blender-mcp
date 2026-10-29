# -*- coding: utf-8 -*-
"""Volcengine Ark Seedream image generation provider (synchronous API)."""
from __future__ import absolute_import

import logging

import requests

from .base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
    is_redirect,
    scrub_secret,
)

logger = logging.getLogger(__name__)


class VolcengineImageProvider(object):
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
        message = error.get("message") if isinstance(error, dict) else None
        return scrub_secret(
            (message or str(payload.get("message") or response.text or ""))[:500],
            self.api_key,
        )

    def generate(self, prompt, negative_prompt=None, size="2K", seed=None,
                 reference_image_urls=None, watermark=False, response_format="url"):
        if not self.api_key:
            raise ProviderAuthError("ARK_API_KEY 未配置", error_type="missing_api_key")
        if not prompt:
            raise ProviderRejected("图片提示词不能为空", error_type="invalid_prompt")

        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "size": size or "2K",
            "response_format": response_format or "url",
            "watermark": bool(watermark),
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if reference_image_urls:
            payload["image"] = list(reference_image_urls)

        url = self.base_url + "/images/generations"
        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout_s,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderUncertain("Seedream 请求超时，生成结果不确定", error_type="image_submission_uncertain")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUncertain(
                "Seedream 连接失败: {0}".format(str(exc)[:200]),
                error_type="image_submission_uncertain",
            )

        if is_redirect(response.status_code):
            raise ProviderRejected(
                "Seedream 返回重定向（HTTP {0}），已拒绝跟随".format(response.status_code),
                error_type="provider_redirect_rejected",
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                "Seedream 鉴权失败: HTTP {0}".format(response.status_code),
                error_type="provider_auth_error",
            )
        if response.status_code == 429:
            raise ProviderRateLimited("Seedream 请求过于频繁", error_type="provider_rate_limited")
        if 400 <= response.status_code < 500:
            raise ProviderRejected(
                "Seedream 拒绝请求: {0}".format(self._safe_error(response)),
                error_type="provider_rejected",
            )
        if response.status_code >= 500:
            raise ProviderUncertain(
                "Seedream 服务异常: HTTP {0}".format(response.status_code),
                error_type="image_submission_uncertain",
            )

        try:
            data = response.json() or {}
        except ValueError:
            raise ProviderError("Seedream 返回非 JSON", error_type="provider_invalid_response")

        images = []
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                images.append({"url": item["url"]})
            elif item.get("b64_json"):
                images.append({"b64_json": item["b64_json"]})
        if not images:
            raise ProviderError("Seedream 响应没有图片", error_type="provider_invalid_response")
        return {"images": images, "created": data.get("created"), "raw": data}
