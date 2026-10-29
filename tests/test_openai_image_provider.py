# -*- coding: utf-8 -*-
"""Unit tests for the OpenAI Images provider adapter (no real network)."""
from __future__ import absolute_import

import pytest
import requests

from backend.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
)
from backend.providers.openai_image import OpenAIImageProvider


class FakeResponse(object):
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _provider():
    return OpenAIImageProvider(
        api_key="sk-test-secret",
        base_url="https://api.openai.example/v1",
        model_id="gpt-image-1",
    )


def _capture(monkeypatch, payload=None, status_code=200):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return FakeResponse(status_code, payload or {"data": [{"b64_json": "aW1n"}]})

    monkeypatch.setattr(requests, "post", fake_post)
    return captured


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("1024x1024", "1024x1024"),
        ("2048x2048", "1024x1024"),
        ("1792x1024", "1536x1024"),
        ("1200x800", "1536x1024"),
        ("1024x1792", "1024x1536"),
        ("800x1200", "1024x1536"),
        ("not-a-size", "1024x1024"),
        ("", "1024x1024"),
    ],
)
def test_size_mapping_follows_orientation(monkeypatch, requested, expected):
    captured = _capture(monkeypatch)
    _provider().generate("a hall", size=requested)
    assert captured["json"]["size"] == expected


def test_request_shape_and_b64_and_url_parsing(monkeypatch):
    captured = _capture(
        monkeypatch,
        {
            "created": 1,
            "data": [
                {"b64_json": "QUJD"},
                {"url": "https://cdn.example/out.png"},
            ],
        },
    )
    result = _provider().generate(
        "a hall",
        negative_prompt="blurry",
        seed=7,
        reference_image_urls=None,
        watermark=True,
    )
    assert captured["url"] == "https://api.openai.example/v1/images/generations"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-secret"
    body = captured["json"]
    assert body["model"] == "gpt-image-1"
    assert body["prompt"] == "a hall"
    assert body["n"] == 1
    assert body["response_format"] == "b64_json"
    assert "negative_prompt" not in body
    assert "seed" not in body
    assert "watermark" not in body
    assert result["images"] == [
        {"b64_json": "QUJD"},
        {"url": "https://cdn.example/out.png"},
    ]


def test_reference_images_are_rejected_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network must not be used")

    monkeypatch.setattr(requests, "post", no_network)
    with pytest.raises(ProviderRejected):
        _provider().generate(
            "a hall", reference_image_urls=["data:image/png;base64,xx"]
        )


def test_missing_api_key_raises_auth_error_without_network(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("network must not be used")

    monkeypatch.setattr(requests, "post", no_network)
    provider = OpenAIImageProvider("", "https://api.openai.example/v1", "gpt-image-1")
    with pytest.raises(ProviderAuthError):
        provider.generate("a hall")


@pytest.mark.parametrize(
    "status,error_type",
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (429, ProviderRateLimited),
        (400, ProviderRejected),
        (404, ProviderRejected),
        (500, ProviderUncertain),
        (503, ProviderUncertain),
    ],
)
def test_error_mapping(monkeypatch, status, error_type):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: FakeResponse(status, {"error": {"message": "bad request"}}),
    )
    with pytest.raises(error_type) as exc:
        _provider().generate("a hall")
    assert "sk-test-secret" not in str(exc.value)


def test_timeout_and_connection_errors_are_uncertain(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "post", timeout)
    with pytest.raises(ProviderUncertain):
        _provider().generate("a hall")

    def connection(*args, **kwargs):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", connection)
    with pytest.raises(ProviderUncertain):
        _provider().generate("a hall")


def test_empty_or_invalid_response_is_provider_error(monkeypatch):
    _capture(monkeypatch, {"data": []})
    with pytest.raises(ProviderError) as exc:
        _provider().generate("a hall")
    assert exc.value.error_type == "provider_invalid_response"

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, None))
    with pytest.raises(ProviderError):
        _provider().generate("a hall")
