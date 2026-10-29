# -*- coding: utf-8 -*-
"""Unit tests for Ark adapters and SSRF-safe URL validation."""
from __future__ import absolute_import

import socket

import pytest
import requests

from backend.media_fetcher import MediaFetchError, validate_url
from backend.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
)
from backend.providers.luma import LumaProvider
from backend.providers.seedance import SeedanceProvider
from backend.providers.volcengine_image import VolcengineImageProvider
from backend.providers.volcengine_video import VolcengineVideoProvider


class FakeResponse(object):
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_ark_image_request_and_parse(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update({"url": url, "headers": headers, "json": json})
        captured.update(kwargs)
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

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update({"url": url, "json": json})
        captured.update(kwargs)
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

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update(json)
        captured.update(kwargs)
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

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured.update(json)
        captured.update(kwargs)
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


# ── Redirects are rejected, never followed (C2) ──


def test_ark_image_rejects_redirect_without_following(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(307, text="redirect", headers={})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = VolcengineImageProvider("secret-key-1", "https://ark.example/api/v3", "model")
    with pytest.raises(ProviderRejected) as exc:
        provider.generate("prompt")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False


def test_ark_video_rejects_redirects_for_submit_and_poll(monkeypatch):
    provider = VolcengineVideoProvider("secret-key-2", "https://ark.example/api/v3", "model")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(302, text="redirect")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(308, text="redirect")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(ProviderError) as exc:
        provider.get_generation("task-1")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False


def test_seedance_rejects_redirects_for_submit_and_poll(monkeypatch):
    provider = SeedanceProvider("secret-key-3", "https://atlas.example/api/v1", "model")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(302, text="redirect")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False

    monkeypatch.setattr(requests, "get", lambda url, **kw: (captured.update(kw), FakeResponse(307))[1])
    with pytest.raises(ProviderError) as exc:
        provider.get_generation("pred-1")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False


def test_luma_rejects_redirects_for_submit_and_poll(monkeypatch):
    provider = LumaProvider("secret-key-4", "https://luma.example", model_name="ray-2")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(302, text="redirect")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False

    monkeypatch.setattr(requests, "get", lambda url, **kw: (captured.update(kw), FakeResponse(307))[1])
    with pytest.raises(ProviderError) as exc:
        provider.get_generation("gen-1")
    assert exc.value.error_type == "provider_redirect_rejected"
    assert captured["allow_redirects"] is False


# ── Error bodies never leak the bearer key (I8) ──


def test_ark_image_error_body_secret_is_scrubbed(monkeypatch):
    key = "ark-secret-abc-987"
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResponse(
            400, {"error": {"message": "bad bearer {0}".format(key)}}
        ),
    )
    provider = VolcengineImageProvider(key, "https://ark.example/api/v3", "model")
    with pytest.raises(ProviderRejected) as exc:
        provider.generate("prompt")
    assert key not in str(exc.value)
    assert "***" in str(exc.value)


def test_ark_video_error_body_secret_is_scrubbed(monkeypatch):
    key = "ark-video-secret-654"
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResponse(
            400, {"error": {"message": "rejected {0}".format(key)}}
        ),
    )
    provider = VolcengineVideoProvider(key, "https://ark.example/api/v3", "model")
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert key not in str(exc.value)
    assert "***" in str(exc.value)


def test_seedance_error_body_secret_is_scrubbed(monkeypatch):
    key = "seedance-secret-321"
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResponse(400, text="bad key {0}".format(key)),
    )
    provider = SeedanceProvider(key, "https://atlas.example/api/v1", "model")
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert key not in str(exc.value)
    assert "***" in str(exc.value)


def test_luma_error_body_secret_is_scrubbed(monkeypatch):
    key = "luma-secret-159"
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResponse(400, text="bad key {0}".format(key)),
    )
    provider = LumaProvider(key, "https://luma.example", model_name="ray-2")
    with pytest.raises(ProviderRejected) as exc:
        provider.create_generation("prompt")
    assert key not in str(exc.value)
    assert "***" in str(exc.value)
