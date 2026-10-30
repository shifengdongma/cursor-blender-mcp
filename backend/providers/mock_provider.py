# -*- coding: utf-8 -*-
"""Deterministic mock providers for automated tests.

Never registered or selected in production.  Tests monkeypatch the provider
factory to return these objects.
"""
from __future__ import absolute_import

from .base import ProviderUncertain

# 1x1 transparent PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Wl2Z9sAAAAASUVORK5CYII="
)


class MockImageProvider(object):
    def __init__(self, fail_uncertain=False):
        self.calls = 0
        self.fail_uncertain = fail_uncertain

    def generate(self, prompt, negative_prompt=None, size="2K", seed=None,
                 reference_image_urls=None, watermark=False, response_format="url"):
        self.calls += 1
        if self.fail_uncertain:
            raise ProviderUncertain("simulated timeout", error_type="submission_uncertain")
        return {"images": [{"b64_json": _PNG_B64}], "created": 0, "raw": {}}


class MockVideoProvider(object):
    def __init__(self):
        self.create_calls = 0
        self.poll_calls = 0

    def create_generation(self, prompt, negative_prompt=None, reference_image_urls=None,
                          reference_image_roles=None, aspect_ratio="16:9",
                          duration_s=5, resolution="720p",
                          generate_audio=False, watermark=False, seed=None,
                          camera_fixed=False):
        self.create_calls += 1
        return {"id": "mock-video-task-1"}

    def get_generation(self, task_id):
        self.poll_calls += 1
        return {
            "id": task_id,
            "status": "succeeded",
            "content": {"video_url": "https://provider.invalid/mock.mp4"},
        }

    def cancel_generation(self, task_id):
        return True

    @staticmethod
    def extract_status(data):
        return data.get("status", "unknown")

    @staticmethod
    def extract_video_url(data):
        return (data.get("content") or {}).get("video_url")

    @staticmethod
    def extract_error(data):
        return {"code": "mock_failed", "message": "mock failure"}
