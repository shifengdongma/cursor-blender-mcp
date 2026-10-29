# -*- coding: utf-8 -*-
"""Luma Dream Machine provider (legacy, unverified).

The adapter maps Luma's asynchronous generation API onto the same create/poll
contract used by the Ark provider.  Timeouts are surfaced as *uncertain* so the
worker never automatically resubmits a task that may already be running.
"""
from __future__ import absolute_import

import time

import requests

from .base import (
    ProviderAuthError,
    ProviderError,
    ProviderPollError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
    is_redirect,
    scrub_secret,
)


class LumaError(ProviderError):
    """Backwards-compatible alias for older callers."""


class LumaProvider(object):
    def __init__(self, api_key, base_url, model_name="ray-2"):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name or "ray-2"

    def _headers(self):
        return {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

    def create_generation(self, prompt, negative_prompt=None, keyframe_urls=None,
                          aspect_ratio="16:9", duration_s=5, resolution="720p"):
        if not self.api_key:
            raise ProviderAuthError("LUMA_API_KEY 未配置", error_type="missing_api_key")
        if not prompt:
            raise ProviderRejected("视频提示词不能为空", error_type="invalid_prompt")

        payload = {
            "prompt": prompt,
            "model": self.model_name,
            "aspect_ratio": aspect_ratio,
        }
        if duration_s is not None:
            payload["duration"] = "{0}s".format(int(duration_s))
        if resolution:
            payload["resolution"] = resolution
        if keyframe_urls:
            payload["keyframes"] = {
                "frame0": {"type": "image", "url": keyframe_urls[0]},
            }

        url = self.base_url + "/generations"
        try:
            response = requests.post(
                url, json=payload, headers=self._headers(), timeout=60,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderUncertain("Luma 提交超时，任务是否创建不确定", error_type="submission_uncertain")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUncertain(
                "Luma 连接失败: {0}".format(str(exc)[:200]),
                error_type="submission_uncertain",
            )

        if is_redirect(response.status_code):
            raise ProviderRejected(
                "Luma 返回重定向（HTTP {0}），已拒绝跟随".format(response.status_code),
                error_type="provider_redirect_rejected",
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError("Luma 鉴权失败: HTTP {0}".format(response.status_code))
        if response.status_code == 429:
            raise ProviderRateLimited("Luma 请求过于频繁")
        if 400 <= response.status_code < 500:
            raise ProviderRejected(
                "Luma 拒绝请求: {0}".format(
                    scrub_secret(response.text[:500], self.api_key)
                ),
                error_type="provider_rejected",
            )
        if response.status_code >= 500:
            raise ProviderUncertain(
                "Luma 服务异常: HTTP {0}".format(response.status_code),
                error_type="submission_uncertain",
            )
        try:
            data = response.json() or {}
        except ValueError:
            raise ProviderError("Luma 返回非 JSON", error_type="provider_invalid_response")
        generation_id = data.get("id") or data.get("generation_id")
        if not generation_id:
            raise ProviderError("Luma 返回缺少 id 字段", error_type="provider_invalid_response")
        return data

    def get_generation(self, generation_id):
        if not self.api_key:
            raise ProviderAuthError("LUMA_API_KEY 未配置", error_type="missing_api_key")
        url = self.base_url + "/generations/{0}".format(generation_id)
        try:
            response = requests.get(
                url,
                headers={"Authorization": "Bearer {0}".format(self.api_key)},
                timeout=60,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderPollError("Luma 查询超时", error_type="provider_poll_timeout")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderPollError(
                "Luma 查询连接失败: {0}".format(str(exc)[:160]),
                error_type="provider_poll_error",
            )
        if is_redirect(response.status_code):
            raise ProviderPollError(
                "Luma 查询返回重定向（HTTP {0}），已拒绝跟随".format(response.status_code),
                error_type="provider_redirect_rejected",
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError("Luma 查询鉴权失败")
        if response.status_code == 429:
            raise ProviderRateLimited("Luma 查询过于频繁")
        if response.status_code >= 400:
            raise ProviderPollError(
                "Luma 查询失败: HTTP {0}".format(response.status_code),
                error_type="provider_poll_error",
            )
        try:
            return response.json() or {}
        except ValueError:
            raise ProviderPollError("Luma 查询返回非 JSON", error_type="provider_invalid_response")

    @staticmethod
    def extract_status(gen_json):
        for key in ("state", "status"):
            value = (gen_json or {}).get(key)
            if value:
                return value
        return "unknown"

    @staticmethod
    def extract_video_url(gen_json):
        assets = (gen_json or {}).get("assets") or {}
        if isinstance(assets, dict):
            if assets.get("video"):
                return assets.get("video")
            if assets.get("video_url"):
                return assets.get("video_url")
        output = (gen_json or {}).get("output") or {}
        if isinstance(output, dict) and output.get("video_url"):
            return output.get("video_url")
        return None

    @staticmethod
    def extract_error(gen_json):
        error = (gen_json or {}).get("error") or {}
        if isinstance(error, dict):
            return {
                "code": error.get("code") or "provider_failed",
                "message": (error.get("message") or "视频生成失败")[:500],
            }
        return {"code": "provider_failed", "message": "视频生成失败"}

    def wait_until_done(self, generation_id, timeout_s=900, poll_interval_s=5):
        """Legacy synchronous helper; the worker uses get_generation instead."""
        start = time.time()
        last = None
        while time.time() - start < timeout_s:
            last = self.get_generation(generation_id)
            status = str(self.extract_status(last) or "").lower()
            if status in ("completed", "succeeded", "success", "done") and self.extract_video_url(last):
                return last
            if status in ("failed", "error", "canceled", "cancelled"):
                return last
            time.sleep(poll_interval_s)
        if last is None:
            raise ProviderPollError("Luma 轮询超时且无有效响应")
        last["_timeout"] = True
        return last
