# -*- coding: utf-8 -*-
"""Real provider-call tests: cost gate, image generation, video create+cancel."""
from __future__ import absolute_import

import requests

from backend.database import get_database
from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"
ARK_KEY = "ark-real-test-secret-4321"
FLASH_ID = "doubao-seedream-5-0-flash-260915"
SEEDANCE_20_ID = "doubao-seedance-2-0-260128"


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


def _put(client, token, provider, **payload):
    return client.put(
        "/api/user/provider-credentials/{0}".format(provider),
        json=payload,
        headers=support.auth_headers(token),
    )


def _post_test(client, token, provider, **payload):
    return client.post(
        "/api/user/provider-credentials/{0}/test-generation".format(provider),
        json=payload,
        headers=support.auth_headers(token),
    )


def _ark_user(client, username, overrides=None):
    user, token = support.register_and_login(client, username)
    response = _put(
        client, token, "ark",
        api_key=ARK_KEY,
        base_url=PUBLIC_BASE_URL,
        model_overrides=overrides or {},
    )
    assert response.status_code == 200, response.get_json()
    return user, token


def _task_count(app, user_id):
    cfg = app.config["AIGV_CONFIG"]
    db = get_database(cfg.DATA_DIR + "/aigv.db")
    row = db.fetch_one(
        "SELECT COUNT(*) AS total FROM generation_tasks WHERE created_by = ?",
        (user_id,),
    )
    return int(row["total"])


def test_real_test_requires_explicit_billing_confirmation(client, monkeypatch):
    _user, token = _ark_user(client, "realgate")

    def fail(*args, **kwargs):
        raise AssertionError("must not call provider before confirmation")

    monkeypatch.setattr(requests, "post", fail)
    response = _post_test(
        client, token, "ark", model_key="ark_seedream_flash"
    )
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "billing_confirmation_required"


def test_real_image_test_uses_flash_id_and_returns_safe_result(client, app, monkeypatch):
    user, token = _ark_user(client, "realimage")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update({"url": url, "json": json, "headers": headers})
        return FakeResponse(
            200,
            {"created": 1, "data": [{"url": "https://ark-result.example/test.png"}]},
            headers={"x-request-id": "req-img-1"},
        )

    monkeypatch.setattr(requests, "post", fake_post)
    response = _post_test(
        client, token, "ark",
        model_key="ark_seedream_flash", confirm_billing=True,
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "succeeded"
    assert data["model_id"] == FLASH_ID
    assert data["image_count"] == 1
    assert data["provider_request_id"] == "req-img-1"
    assert captured["json"]["model"] == FLASH_ID
    assert captured["json"]["size"] == "1K"
    assert captured["json"]["prompt"]
    assert captured["json"]["watermark"] is False
    assert captured["headers"]["Authorization"] == "Bearer {0}".format(ARK_KEY)
    assert ARK_KEY not in response.get_data(as_text=True)
    assert _task_count(app, user["id"]) == 0

    listing = client.get("/api/user/provider-credentials", headers=support.auth_headers(token))
    item = [entry for entry in listing.get_json()["data"]["items"]
            if entry["provider"] == "ark"][0]
    assert item["last_verified_at"] is not None
    assert item["last_verification"]["ark_seedream_flash"]["status"] == "succeeded"
    assert item["last_verification"]["ark_seedream_flash"]["model_id"] == FLASH_ID


def test_real_video_test_creates_minimal_task_and_attempts_cancel(client, app, monkeypatch):
    user, token = _ark_user(client, "realvideo")
    captured = {}
    deleted = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update({"url": url, "json": json})
        return FakeResponse(
            200, {"id": "task-123"},
            headers={"x-request-id": "req-video-1"},
        )

    def fake_delete(url, **kwargs):
        deleted["url"] = url
        return FakeResponse(204)

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "delete", fake_delete)
    response = _post_test(
        client, token, "ark",
        model_key="ark_seedance_20", confirm_billing=True,
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "accepted"
    assert data["model_id"] == SEEDANCE_20_ID
    assert data["provider_job_id"] == "task-123"
    assert data["cancel_attempted"] is True
    assert data["cancel_accepted"] is True
    assert data["provider_request_id"] == "req-video-1"
    assert captured["json"]["model"] == SEEDANCE_20_ID
    assert captured["json"]["duration"] == 4
    assert captured["json"]["resolution"] == "480p"
    assert captured["json"]["generate_audio"] is False
    assert deleted["url"].endswith("/contents/generations/tasks/task-123")
    assert "费用" in data["message"]
    assert _task_count(app, user["id"]) == 0


def test_real_test_reports_model_not_activated_with_request_id(client, monkeypatch):
    _user, token = _ark_user(client, "realactivation")
    request_id = "02179335784499824e994d08a876ec3f4dc3077f2522"
    payload = {
        "error": {
            "code": "ModelNotOpen",
            "message": (
                "Your account 2121252570 has not activated the model {0}. "
                "Please activate the model service in the Ark Console. "
                "Request id: {1}".format(FLASH_ID, request_id)
            ),
        }
    }
    monkeypatch.setattr(
        requests, "post", lambda *a, **k: FakeResponse(400, payload)
    )
    response = _post_test(
        client, token, "ark",
        model_key="ark_seedream_flash", confirm_billing=True,
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "model_not_activated"
    assert data["provider_code"] == "ModelNotOpen"
    assert data["provider_request_id"] == request_id
    assert "未开通" in data["message"]
    assert ARK_KEY not in response.get_data(as_text=True)


def test_real_test_rejects_model_from_another_provider(client):
    _user, token = _ark_user(client, "realmismatch")
    response = _post_test(
        client, token, "ark",
        model_key="openai_gpt_image_1", confirm_billing=True,
    )
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_model"


def test_llm_does_not_support_generation_test(client):
    _user, token = support.register_and_login(client, "realllm")
    created = _put(
        client, token, "llm",
        api_key="sk-llm-real-test-8765",
        base_url=PUBLIC_BASE_URL,
        model="deepseek-chat",
    )
    assert created.status_code == 200, created.get_json()
    response = _post_test(
        client, token, "llm",
        model_key="openai_gpt_image_1", confirm_billing=True,
    )
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "test_not_supported"


def test_video_cancel_failure_is_reported(client, monkeypatch):
    _user, token = _ark_user(client, "realcancel")
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: FakeResponse(200, {"id": "task-cancel-fail"}),
    )
    monkeypatch.setattr(
        requests, "delete", lambda *a, **k: FakeResponse(500, {"error": {"message": "nope"}})
    )
    data = _post_test(
        client, token, "ark",
        model_key="ark_seedance_20", confirm_billing=True,
    ).get_json()["data"]
    assert data["status"] == "accepted"
    assert data["cancel_attempted"] is True
    assert data["cancel_accepted"] is False
    assert "费用" in data["message"]


def test_user_model_override_is_used_by_real_test(client, monkeypatch):
    _user, token = _ark_user(
        client, "realoverride",
        overrides={"ark_seedream_flash": "custom-flash-endpoint-id"},
    )
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update(json)
        return FakeResponse(
            200, {"data": [{"url": "https://ark-result.example/custom.png"}]}
        )

    monkeypatch.setattr(requests, "post", fake_post)
    data = _post_test(
        client, token, "ark",
        model_key="ark_seedream_flash", confirm_billing=True,
    ).get_json()["data"]
    assert data["status"] == "succeeded"
    assert data["model_id"] == "custom-flash-endpoint-id"
    assert captured["model"] == "custom-flash-endpoint-id"
