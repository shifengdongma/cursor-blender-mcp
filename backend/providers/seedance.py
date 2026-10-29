# -*- coding: utf-8 -*-
"""Atlas Cloud Seedance provider (legacy compatibility channel).

This is NOT the Volcengine Ark direct API.  Keep the two adapters separate.
The adapter only sends fields that the caller explicitly requests.
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


class SeedanceError(ProviderError):
    """Backwards-compatible alias for older callers."""


class SeedanceProvider(object):
    def __init__(self, api_key, base_url, model_name=None):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name or "bytedance/seedance-v1.5-pro/text-to-video"

    def _headers(self):
        return {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

    def create_generation(self, prompt, negative_prompt=None, keyframe_urls=None,
                          aspect_ratio="16:9", duration_s=8, resolution="720p",
                          generate_audio=None, seed=None):
        if not self.api_key:
            raise ProviderAuthError("SEEDANCE_API_KEY 未配置", error_type="missing_api_key")
        if not prompt:
            raise ProviderRejected("视频提示词不能为空", error_type="invalid_prompt")

        payload = {
            "model": self.model_name,
            "aspect_ratio": aspect_ratio,
            "duration": int(duration_s),
            "prompt": prompt,
            "resolution": resolution,
        }
        if generate_audio is not None:
            payload["generate_audio"] = bool(generate_audio)
        if seed is not None:
            payload["seed"] = int(seed)

        url = self.base_url + "/model/generateVideo"
        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=120,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderUncertain("Seedance 提交超时，任务是否创建不确定", error_type="submission_uncertain")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUncertain(
                "Seedance 连接失败: {0}".format(str(exc)[:200]),
                error_type="submission_uncertain",
            )

        if is_redirect(response.status_code):
            raise ProviderRejected(
                "Seedance 返回重定向（HTTP {0}），已拒绝跟随".format(response.status_code),
                error_type="provider_redirect_rejected",
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError("Seedance 鉴权失败: HTTP {0}".format(response.status_code))
        if response.status_code == 429:
            raise ProviderRateLimited("Seedance 请求过于频繁")
        if 400 <= response.status_code < 500:
            raise ProviderRejected(
                "Seedance 拒绝请求: {0}".format(
                    scrub_secret(response.text[:500], self.api_key)
                ),
                error_type="provider_rejected",
            )
        if response.status_code >= 500:
            raise ProviderUncertain(
                "Seedance 服务异常: HTTP {0}".format(response.status_code),
                error_type="submission_uncertain",
            )
        try:
            data = response.json() or {}
        except ValueError:
            raise ProviderError("Seedance 返回非 JSON", error_type="provider_invalid_response")
        prediction_id = (data.get("data") or {}).get("id")
        if not prediction_id:
            raise ProviderError("Seedance 返回缺少 data.id 字段", error_type="provider_invalid_response")
        return data

    def get_generation(self, prediction_id):
        if not self.api_key:
            raise ProviderAuthError("SEEDANCE_API_KEY 未配置", error_type="missing_api_key")
        url = self.base_url + "/model/prediction/{0}".format(prediction_id)
        try:
            response = requests.get(
                url,
                headers={"Authorization": "Bearer {0}".format(self.api_key)},
                timeout=60,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ProviderPollError("Seedance 查询超时", error_type="provider_poll_timeout")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderPollError(
                "Seedance 查询连接失败: {0}".format(str(exc)[:160]),
                error_type="provider_poll_error",
            )
        if is_redirect(response.status_code):
            raise ProviderPollError(
                "Seedance 查询返回重定向（HTTP {0}），已拒绝跟随".format(response.status_code),
                error_type="provider_redirect_rejected",
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError("Seedance 查询鉴权失败")
        if response.status_code == 429:
            raise ProviderRateLimited("Seedance 查询过于频繁")
        if response.status_code >= 400:
            raise ProviderPollError(
                "Seedance 查询失败: HTTP {0}".format(response.status_code),
                error_type="provider_poll_error",
            )
        try:
            return response.json() or {}
        except ValueError:
            raise ProviderPollError("Seedance 查询返回非 JSON", error_type="provider_invalid_response")

    @staticmethod
    def extract_status(pred_json):
        data = (pred_json or {}).get("data") or {}
        return data.get("status") or "unknown"

    @staticmethod
    def extract_video_url(pred_json):
        data = (pred_json or {}).get("data") or {}
        outputs = data.get("outputs") or []
        if isinstance(outputs, list) and outputs:
            return outputs[0]
        return None

    @staticmethod
    def extract_error(pred_json):
        data = (pred_json or {}).get("data") or {}
        error = data.get("error") or (pred_json or {}).get("error") or {}
        if isinstance(error, dict):
            return {
                "code": error.get("code") or "provider_failed",
                "message": (error.get("message") or "视频生成失败")[:500],
            }
        return {"code": "provider_failed", "message": "视频生成失败"}

    def wait_until_done(self, prediction_id, timeout_s=900, poll_interval_s=5):
        start = time.time()
        last = None
        while time.time() - start < timeout_s:
            last = self.get_generation(prediction_id)
            status = str(self.extract_status(last) or "").lower()
            if status in ("completed", "succeeded", "success", "done") and self.extract_video_url(last):
                return last
            if status in ("failed", "error", "canceled", "cancelled"):
                return last
            time.sleep(poll_interval_s)
        if last is None:
            raise ProviderPollError("Seedance 轮询超时且无有效响应")
        last["_timeout"] = True
        return last
