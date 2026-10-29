# -*- coding: utf-8 -*-
"""Unit tests for Ark adapters and SSRF-safe URL validation."""
from __future__ import absolute_import

import socket

import pytest
import requests

from backend.media_fetcher import MediaFetchError, validate_url
from backend.providers.base import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
)
from backend.providers.luma import LumaProvider
from backend.providers.seedance import SeedanceProvider
from backend.providers.volcengine_image import VolcengineImageProvider
from backend.providers.volcengine_video import VolcengineVideoProvider


class FakeResponse(object):
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_ark_image_request_and_parse(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update({"url": url, "headers": headers, "json": json})
        return FakeResponse(200, {"created": 1, "data": [
            {"url": "https://ark-result.example/a.png"},
            {"b64_json": "abc"},
        ]})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = VolcengineImageProvider(
        api_key="secret", base_url="https://ark.example/api/v3",
        model_id="doubao-seedream-5-0-pro-260628",
    )
    result = provider.generate("prompt", size="2K", reference_image_urls=["data:image/png;base64,xx"])
    assert captured["url"] == "https://ark.example/api/v3/images/generations"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "doubao-seedream-5-0-pro-260628"
    assert captured["json"]["image"] == ["data:image/png;base64,xx"]
    assert result["images"][0]["url"].startswith("https://")
    assert result["images"][1]["b64_json"] == "abc"


@pytest.mark.parametrize("status,error_type", [
    (401, ProviderAuthError),
    (429, ProviderRateLimited),
    (400, ProviderRejected),
    (500, ProviderUncertain),
])
def test_ark_image_error_mapping(monkeypatch, status, error_type):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(status, {"error": {"message": "bad"}}))
    provider = VolcengineImageProvider("secret", "https://ark.example/api/v3", "model")
    with pytest.raises(error_type):
        provider.generate("prompt")


def test_ark_image_timeout_is_uncertain(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "post", timeout)
    provider = VolcengineImageProvider("secret", "https://ark.example/api/v3", "model")
    with pytest.raises(ProviderUncertain):
        provider.generate("prompt")


def test_ark_video_request_and_parse(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update({"url": url, "json": json})
        return FakeResponse(200, {"id": "task-123"})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = VolcengineVideoProvider("secret", "https://ark.example/api/v3", "doubao-seedance-2-5-260628")
    created = provider.create_generation(
        "camera moves",
        reference_image_urls=["data:image/png;base64,xx"],
        aspect_ratio="16:9",
        duration_s=5,
        resolution="720p",
        generate_audio=True,
    )
    assert created["id"] == "task-123"
    assert captured["url"].endswith("/contents/generations/tasks")
    assert captured["json"]["content"][0]["type"] == "text"
    assert captured["json"]["content"][1]["role"] == "first_frame"
    assert captured["json"]["duration"] == 5

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(
        200, {"status": "succeeded", "content": {"video_url": "https://ark-result.example/v.mp4"}}
    ))
    data = provider.get_generation("task-123")
    assert provider.extract_status(data) == "succeeded"
    assert provider.extract_video_url(data).endswith("v.mp4")


def test_seedance_omits_optional_fields_and_typed_timeout(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(json)
        return FakeResponse(200, {"data": {"id": "pred-1"}})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = SeedanceProvider("key", "https://atlas.example/api/v1", "model")
    provider.create_generation("prompt", aspect_ratio="16:9", duration_s=5, resolution="720p")
    assert "generate_audio" not in captured
    assert "seed" not in captured

    def timeout(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "post", timeout)
    with pytest.raises(ProviderUncertain):
        provider.create_generation("prompt")


def test_luma_payload_and_typed_timeout(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(json)
        return FakeResponse(200, {"id": "luma-1"})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = LumaProvider("key", "https://luma.example", model_name="ray-2")
    provider.create_generation(
        "prompt",
        aspect_ratio="9:16",
        duration_s=5,
        resolution="720p",
    )
    assert captured["model"] == "ray-2"
    assert captured["duration"] == "5s"
    assert captured["resolution"] == "720p"

    def timeout(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "post", timeout)
    with pytest.raises(ProviderUncertain):
        provider.create_generation("prompt")


def test_validate_url_blocks_private_and_http(monkeypatch):
    real_getaddrinfo = socket.getaddrinfo

    def private(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", private)
    with pytest.raises(MediaFetchError):
        validate_url("https://example.com/a.png")

    def public(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", public)
    assert validate_url("https://example.com/a.png").hostname == "example.com"
    with pytest.raises(MediaFetchError):
        validate_url("http://example.com/a.png")
    with pytest.raises(MediaFetchError):
        validate_url("https://user:pass@example.com/a.png")
    monkeypatch.setattr(socket, "getaddrinfo", real_getaddrinfo)
