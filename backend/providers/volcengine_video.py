# -*- coding: utf-8 -*-
"""Volcengine Ark Seedance video generation provider (asynchronous tasks)."""
from __future__ import absolute_import

import logging

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

logger = logging.getLogger(__name__)


class VolcengineVideoProvider(object):
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

    def _error_text(self, response):
        try:
            payload = response.json() or {}
        except ValueError:
            payload = {}
        error = payload.get("error") or {}
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or str(payload)
        else:
            message = payload.get("message") or response.text or ""
        return scrub_secret(str(message)[:500], self.api_key)

    def create_generation(self, prompt, negative_prompt=None, reference_image_urls=None,
                          aspect_ratio="16:9", duration_s=5, resolution="720p",
                          generate_audio=False, watermark=False, seed=None,
                          camera_fixed=False):
        if not self.api_key:
            raise ProviderAuthError("ARK_API_KEY 未配置", error_type="missing_api_key")
        if not prompt:
            raise ProviderRejected("视频提示词不能为空", error_type="invalid_prompt")

        content = [{"type": "text", "text": prompt}]
        for index, image in enumerate(reference_image_urls or []):
            if not image:
                continue
            item = {
                "type": "image_url",
                "image_url": {"url": image},
                "role": "first_frame" if index == 0 else "reference_image",
            }
            content.append(item)

        payload = {
            "model": self.model_id,
            "content": content,
            "ratio": aspect_ratio or "16:9",
            "duration": int(duration_s or 5),
            "resolution": resolution or "720p",
            "generate_audio": bool(generate_audio),
            "watermark": bool(watermark),
        }
        if seed is not None:
            payload["seed"] = int(seed)
        if camera_fixed:
            payload["camera_fixed"] = True

        url = self.base_url + "/contents/generations/tasks"
        try:
            response = requests.post(
                url, headers=self._headers(), json=payload, timeout=self.timeout_s,
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
                "Seedance 拒绝请求: {0}".format(self._error_text(response)),
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
        task_id = data.get("id") or (data.get("data") or {}).get("id")
        if not task_id:
            raise ProviderError("Seedance 响应缺少任务 ID", error_type="provider_invalid_response")
        return data

    def get_generation(self, task_id):
        if not self.api_key:
            raise ProviderAuthError("ARK_API_KEY 未配置")
        url = self.base_url + "/contents/generations/tasks/{0}".format(task_id)
        try:
            response = requests.get(
                url, headers=self._headers(), timeout=60, allow_redirects=False
            )
        except requests.exceptions.Timeout:
            raise ProviderPollError("Seedance 查询超时", error_type="provider_poll_timeout")
        except requests.exceptions.ConnectionError as exc:
            raise ProviderPollError("Seedance 查询连接失败: {0}".format(str(exc)[:160]))
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

    def cancel_generation(self, task_id):
        """Delete/cancel a queued provider task. Returns True when accepted."""
        url = self.base_url + "/contents/generations/tasks/{0}".format(task_id)
        try:
            response = requests.delete(
                url, headers=self._headers(), timeout=30, allow_redirects=False
            )
        except requests.exceptions.RequestException:
            return False
        if is_redirect(response.status_code):
            return False
        return response.status_code in (200, 202, 204)

    def wait_until_done(self, task_id, timeout_s=900, poll_interval_s=5):
        """Legacy synchronous compatibility helper for the workbench pipeline."""
        import time
        start = time.time()
        last = None
        while time.time() - start < timeout_s:
            last = self.get_generation(task_id)
            status = self.extract_status(last)
            if status in ("succeeded", "success", "completed", "done"):
                return last
            if status in ("failed", "error", "expired", "cancelled", "canceled"):
                return last
            time.sleep(poll_interval_s)
        if last is None:
            raise ProviderPollError("Seedance 轮询超时且无有效响应")
        last["_timeout"] = True
        return last

    @staticmethod
    def extract_status(data):
        status = (data or {}).get("status")
        if not status:
            data_obj = (data or {}).get("data") or {}
            status = data_obj.get("status")
        return str(status or "unknown").lower()

    @staticmethod
    def extract_video_url(data):
        content = (data or {}).get("content")
        if isinstance(content, dict) and content.get("video_url"):
            return content.get("video_url")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("video_url"):
                    return item.get("video_url")
        data_obj = (data or {}).get("data") or {}
        content = data_obj.get("content")
        if isinstance(content, dict):
            return content.get("video_url")
        return None

    @staticmethod
    def extract_error(data):
        error = (data or {}).get("error") or {}
        if isinstance(error, dict):
            return {
                "code": error.get("code") or "provider_failed",
                "message": (error.get("message") or "视频生成失败")[:500],
            }
        return {"code": "provider_failed", "message": "视频生成失败"}
