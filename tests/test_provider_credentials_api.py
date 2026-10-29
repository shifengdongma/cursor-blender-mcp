# -*- coding: utf-8 -*-
"""HTTP API for per-user provider credentials (masking, SSRF, task lock)."""
from __future__ import absolute_import

import os
import time

import requests

from backend.database import get_database
from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"


def _headers(token):
    return support.auth_headers(token)


def _put(client, token, provider, **payload):
    return client.put(
        "/api/user/provider-credentials/{0}".format(provider),
        json=payload,
        headers=_headers(token),
    )


def test_put_get_delete_credential_masks_key(client):
    user, token = support.register_and_login(client, "credapi1")

    response = _put(
        client,
        token,
        "llm",
        api_key="sk-test-secret-9876",
        base_url=PUBLIC_BASE_URL,
        model="gpt-4o-mini",
    )
    assert response.status_code == 200, response.get_json()
    record = response.get_json()["data"]
    assert record["provider"] == "llm"
    assert record["has_key"] is True
    assert record["key_last4"] == "9876"
    assert record["base_url"] == PUBLIC_BASE_URL
    assert record["model"] == "gpt-4o-mini"
    assert record["source"] == "user"
    assert "api_key" not in record
    assert "api_key_ciphertext" not in record
    assert "sk-test-secret-9876" not in response.get_data(as_text=True)

    listing = client.get("/api/user/provider-credentials", headers=_headers(token))
    assert listing.status_code == 200
    payload = listing.get_json()["data"]
    assert payload["catalog"]
    assert {item["provider"] for item in payload["catalog"]} >= {"llm", "ark", "openai_image"}
    item = [entry for entry in payload["items"] if entry["provider"] == "llm"][0]
    assert item["has_key"] is True
    assert item["key_last4"] == "9876"
    assert "api_key" not in item
    assert "sk-test-secret-9876" not in listing.get_data(as_text=True)

    deleted = client.delete(
        "/api/user/provider-credentials/llm", headers=_headers(token)
    )
    assert deleted.status_code == 200, deleted.get_json()
    assert deleted.get_json()["data"]["deleted"] is True

    after = client.get("/api/user/provider-credentials", headers=_headers(token))
    assert after.get_json()["data"]["items"] == []


def test_custom_base_url_requires_user_key_via_api(client):
    _user, token = support.register_and_login(client, "credapi2")

    response = _put(client, token, "llm", base_url=PUBLIC_BASE_URL)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "user_key_required"


def test_reject_private_and_http_base_url(client):
    _user, token = support.register_and_login(client, "credapi3")

    private = _put(
        client, token, "llm", api_key="sk-test-secret-0001",
        base_url="https://127.0.0.1/v1",
    )
    assert private.status_code == 400, private.get_json()
    assert private.get_json()["error"] == "invalid_base_url"

    insecure = _put(
        client, token, "llm", api_key="sk-test-secret-0002",
        base_url="http://93.184.216.34",
    )
    assert insecure.status_code == 400, insecure.get_json()
    assert insecure.get_json()["error"] == "invalid_base_url"


def test_credential_locked_by_active_task(client, app):
    user, token = support.register_and_login(client, "credapi4")

    created = _put(client, token, "luma", api_key="luma-secret-4321", model="ray-2")
    assert created.status_code == 200, created.get_json()

    data_dir = app.config["AIGV_CONFIG"].DATA_DIR
    db = get_database(os.path.join(data_dir, "aigv.db"))
    now = int(time.time())
    db.insert(
        "generation_tasks",
        {
            "id": "task-locked-0001",
            "task_type": "video",
            "status": "queued",
            "provider": "luma",
            "created_by": user["id"],
            "created_at": now,
            "updated_at": now,
        },
    )

    update = _put(client, token, "luma", model="ray-3")
    assert update.status_code == 409, update.get_json()
    assert update.get_json()["error"] == "active_tasks"

    deleted = client.delete(
        "/api/user/provider-credentials/luma", headers=_headers(token)
    )
    assert deleted.status_code == 409, deleted.get_json()
    assert deleted.get_json()["error"] == "active_tasks"

    listing = client.get("/api/user/provider-credentials", headers=_headers(token))
    assert [entry["provider"] for entry in listing.get_json()["data"]["items"]] == ["luma"]


def test_other_user_cannot_see_credential(app):
    client_a = app.test_client()
    _user_a, token_a = support.register_and_login(client_a, "credapiusera")
    created = _put(client_a, token_a, "llm", api_key="sk-user-a-1111")
    assert created.status_code == 200, created.get_json()

    client_b = app.test_client()
    _user_b, _token_b = support.register_and_login(client_b, "credapiuserb")

    listing = client_b.get("/api/user/provider-credentials")
    assert listing.status_code == 200
    assert listing.get_json()["data"]["items"] == []
    assert "sk-user-a-1111" not in listing.get_data(as_text=True)


class _FakeResponse(object):
    def __init__(self, status_code):
        self.status_code = status_code

    def close(self):
        pass


def test_llm_connection_test_uses_models_endpoint_without_leaking_key(client, monkeypatch):
    _user, token = support.register_and_login(client, "credapi5")
    created = _put(
        client, token, "llm",
        api_key="sk-test-secret-5555", base_url=PUBLIC_BASE_URL,
    )
    assert created.status_code == 200, created.get_json()

    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["headers"] = kwargs.get("headers") or {}
        return _FakeResponse(200)

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.post(
        "/api/user/provider-credentials/llm/test", headers=_headers(token)
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["reachable"] is True
    assert payload["verified"] is True
    assert calls["url"] == PUBLIC_BASE_URL + "/models"
    assert calls["headers"]["Authorization"] == "Bearer sk-test-secret-5555"
    assert "sk-test-secret-5555" not in response.get_data(as_text=True)


def test_connection_test_maps_network_error_without_leaking_key(client, monkeypatch):
    _user, token = support.register_and_login(client, "credapi6")
    created = _put(client, token, "luma", api_key="luma-secret-6666")
    assert created.status_code == 200, created.get_json()

    def fake_head(url, **kwargs):
        raise requests.ConnectionError("Authorization: Bearer luma-secret-6666")

    monkeypatch.setattr(requests, "head", fake_head)

    response = client.post(
        "/api/user/provider-credentials/luma/test", headers=_headers(token)
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["reachable"] is False
    assert payload["verified"] is False
    body = response.get_data(as_text=True)
    assert "luma-secret-6666" not in body
    assert "Authorization" not in body


def test_connection_test_requires_configured_key(client):
    _user, token = support.register_and_login(client, "credapi7")

    response = client.post(
        "/api/user/provider-credentials/llm/test", headers=_headers(token)
    )
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "provider_not_configured"
