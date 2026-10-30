# -*- coding: utf-8 -*-
"""Ark/provider HTTP errors keep safe codes, request IDs and Chinese messages."""
from __future__ import absolute_import

import pytest
import requests

from backend.providers import base
from backend.providers.volcengine_image import VolcengineImageProvider
from backend.providers.volcengine_video import VolcengineVideoProvider

MODEL_ID = "doubao-seedream-5-0-flash-260915"
REQUEST_ID = "02179335784499824e994d08a876ec3f4dc3077f2522"


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


def _activation_payload():
    return {
        "error": {
            "code": "ModelNotOpen",
            "message": (
                "Your account 2121252570 has not activated the model "
                "{0}. Please activate the model service in the Ark Console. "
                "Request id: {1}".format(MODEL_ID, REQUEST_ID)
            ),
            "type": "BadRequest",
        }
    }


def test_ark_image_model_not_activated_error_is_actionable(monkeypatch):
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: FakeResponse(400, _activation_payload())
    )
    provider = VolcengineImageProvider("ark-secret-key", "https://ark.example/api/v3", MODEL_ID)
    with pytest.raises(base.ProviderRejected) as exc:
        provider.generate("prompt")

    error = exc.value
    assert error.error_type == "model_not_activated"
    assert error.status_code == 400
    assert error.provider_code == "ModelNotOpen"
    assert error.request_id == REQUEST_ID
    assert error.model_id == MODEL_ID
    assert "未开通" in str(error)
    assert MODEL_ID in str(error)
    assert REQUEST_ID in str(error)
    assert "ark-secret-key" not in str(error)


def test_ark_404_model_not_open_is_activation_error(monkeypatch):
    payload = {
        "error": {
            "code": "ModelNotOpen",
            "message": "The model service is not activated. Request id: 0217933607196221cb6d3ad1bdd7a7436196dd041d7fa42e7e12b",
        }
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(404, payload))
    provider = VolcengineImageProvider("ark-secret-key", "https://ark.example/api/v3", MODEL_ID)
    with pytest.raises(base.ProviderRejected) as exc:
        provider.generate("prompt")
    assert exc.value.error_type == "model_not_activated"
    assert exc.value.status_code == 404
    assert exc.value.provider_code == "ModelNotOpen"
    assert "未开通" in str(exc.value)
    assert "接口路径不存在" not in str(exc.value)


def test_ark_video_model_not_found_error_is_actionable(monkeypatch):
    payload = {
        "error": {
            "code": "InvalidEndpointOrModel.NotFound",
            "message": "The model does not exist or you do not have access to it.",
            "request_id": "req-model-404",
        }
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(400, payload))
    provider = VolcengineVideoProvider("ark-secret-key", "https://ark.example/api/v3", "wrong-model")
    with pytest.raises(base.ProviderRejected) as exc:
        provider.create_generation("prompt")

    error = exc.value
    assert error.error_type == "model_not_found"
    assert error.request_id == "req-model-404"
    assert error.provider_code == "InvalidEndpointOrModel.NotFound"
    assert "模型 ID" in str(error)


def test_ark_image_auth_permission_endpoint_and_rate_limit_mapping(monkeypatch):
    provider = VolcengineImageProvider("ark-secret-key", "https://ark.example/api/v3", MODEL_ID)

    cases = [
        (401, {"error": {"code": "AuthenticationError", "message": "bad key"}}, None),
        (403, {"error": {"code": "AccessDenied", "message": "denied"}},
         {"x-request-id": "req-403"}),
        (404, {"error": {"message": "not found"}}, {"X-Request-Id": "req-404"}),
        (429, {"error": {"message": "slow down"}}, {"Retry-After": "30"}),
        (500, {"error": {"message": "boom"}}, {"x-ark-request-id": "req-500"}),
    ]
    for status, payload, headers in cases:
        monkeypatch.setattr(
            requests, "post",
            lambda *a, **k: FakeResponse(status, payload, headers=headers),
        )
        with pytest.raises(base.ProviderError) as exc:
            provider.generate("prompt")
        error = exc.value
        assert error.status_code == status
        if status == 401:
            assert isinstance(error, base.ProviderAuthError)
            assert error.error_type == "provider_auth_error"
            assert "API Key" in str(error)
        elif status == 403:
            assert isinstance(error, base.ProviderAuthError)
            assert error.error_type == "provider_permission_denied"
            assert "权限" in str(error)
            assert error.request_id == "req-403"
        elif status == 404:
            assert error.error_type == "provider_endpoint_not_found"
            assert "Base URL" in str(error)
            assert error.request_id == "req-404"
        elif status == 429:
            assert isinstance(error, base.ProviderRateLimited)
            assert error.retry_after_s == 30
            assert "频繁" in str(error)
        else:
            assert isinstance(error, base.ProviderUncertain)
            assert error.error_type == "image_submission_uncertain"
            assert "服务" in str(error)
            assert error.request_id == "req-500"


def test_video_poll_error_reads_nested_data_error():
    data = {
        "status": "failed",
        "data": {
            "error": {
                "code": "InvalidParameter",
                "message": "bad duration",
                "request_id": "req-poll-1",
            }
        },
    }
    error = VolcengineVideoProvider.extract_error(data)
    assert error["code"] == "InvalidParameter"
    assert error["message"] == "bad duration"
    assert error["request_id"] == "req-poll-1"


def test_video_submit_5xx_is_uncertain_with_request_id(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: FakeResponse(
            503, {"error": {"message": "unavailable"}},
            headers={"x-request-id": "req-503"},
        ),
    )
    provider = VolcengineVideoProvider("ark-secret-key", "https://ark.example/api/v3", "model")
    with pytest.raises(base.ProviderUncertain) as exc:
        provider.create_generation("prompt")
    assert exc.value.error_type == "submission_uncertain"
    assert exc.value.request_id == "req-503"
    assert "服务" in str(exc.value)


def test_error_body_secret_is_scrubbed_and_request_id_safe(monkeypatch):
    key = "ark-secret-abc-987"
    payload = {
        "error": {
            "code": "AuthenticationError",
            "message": "bad bearer {0} request id: bad/id with spaces".format(key),
        }
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(401, payload))
    provider = VolcengineImageProvider(key, "https://ark.example/api/v3", MODEL_ID)
    with pytest.raises(base.ProviderAuthError) as exc:
        provider.generate("prompt")
    assert key not in str(exc.value)
    assert "***" in str(exc.value)
    assert exc.value.request_id in (None, "")
