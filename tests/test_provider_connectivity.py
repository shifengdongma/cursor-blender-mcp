# -*- coding: utf-8 -*-
"""Three-state credential connectivity: network, key, model."""
from __future__ import absolute_import

import requests

from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"
ARK_MODEL_ID = "doubao-seedream-5-0-flash-260915"


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

    def close(self):
        pass


def _put(client, token, provider, **payload):
    return client.put(
        "/api/user/provider-credentials/{0}".format(provider),
        json=payload,
        headers=support.auth_headers(token),
    )


def _test(client, token, provider):
    return client.post(
        "/api/user/provider-credentials/{0}/test".format(provider),
        headers=support.auth_headers(token),
    )


def _ark_client(client):
    _user, token = support.register_and_login(client, "connark")
    response = _put(
        client, token, "ark",
        api_key="ark-connectivity-secret-1234",
        base_url=PUBLIC_BASE_URL,
    )
    assert response.status_code == 200, response.get_json()
    return token


def _forbid_head(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("connectivity test must not use HEAD")

    monkeypatch.setattr(requests, "head", fail)


def test_ark_models_200_verifies_key_and_lists_model(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["headers"] = kwargs.get("headers") or {}
        return FakeResponse(
            200,
            {"data": [{"id": ARK_MODEL_ID}, {"id": "doubao-seedance-2-5-260628"}]},
            headers={"x-request-id": "req-list-1"},
        )

    monkeypatch.setattr(requests, "get", fake_get)

    response = _test(client, token, "ark")
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["network"]["status_code"] == 200
    assert data["key"]["status"] == "verified"
    assert data["key"]["provider_request_id"] == "req-list-1"
    assert data["model"]["status"] == "listed"
    assert data["model"]["model_id"] == ARK_MODEL_ID
    assert data["reachable"] is True
    assert data["verified"] is True
    assert calls["url"] == PUBLIC_BASE_URL + "/models"
    assert calls["headers"]["Authorization"] == "Bearer ark-connectivity-secret-1234"
    body = response.get_data(as_text=True)
    assert "ark-connectivity-secret-1234" not in body
    assert "不代表模型可调用" in data["message"] or "真实调用" in data["message"]

    listing = client.get("/api/user/provider-credentials", headers=support.auth_headers(token))
    item = [entry for entry in listing.get_json()["data"]["items"]
            if entry["provider"] == "ark"][0]
    assert item["last_verified_at"] is not None


def test_ark_404_is_reachable_but_not_verified(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(404, {"error": {"message": "not found"}}),
    )

    data = _test(client, token, "ark").get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["network"]["status_code"] == 404
    assert data["key"]["status"] == "unsupported"
    assert data["verified"] is False
    assert "无法通过此方式验证" in data["message"]
    assert "验证通过" not in data["message"]


def test_ark_401_marks_key_rejected_without_leaking_key(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(
            401,
            {"error": {"code": "AuthenticationError",
                       "message": "bad key ark-connectivity-secret-1234"}},
            headers={"x-request-id": "req-401"},
        ),
    )

    response = _test(client, token, "ark")
    data = response.get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["key"]["status"] == "rejected"
    assert data["verified"] is False
    assert "无效" in data["key"]["message"]
    assert data["key"]["provider_request_id"] == "req-401"
    body = response.get_data(as_text=True)
    assert "ark-connectivity-secret-1234" not in body

    listing = client.get("/api/user/provider-credentials", headers=support.auth_headers(token))
    item = [entry for entry in listing.get_json()["data"]["items"]
            if entry["provider"] == "ark"][0]
    assert item["last_verified_at"] is None


def test_ark_429_is_inconclusive(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(
            429, {"error": {"message": "slow down"}}, headers={"Retry-After": "30"}
        ),
    )

    data = _test(client, token, "ark").get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["key"]["status"] == "unknown"
    assert data["key"]["retry_after_s"] == 30
    assert data["verified"] is False
    assert "限流" in data["key"]["message"]


def test_ark_200_without_model_list_is_not_verified(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)
    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(200, {"message": "ok"}, text="<html>ok</html>"),
    )

    data = _test(client, token, "ark").get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["key"]["status"] == "unknown"
    assert data["verified"] is False
    assert "无法通过此方式验证" in data["message"]


def test_network_error_marks_unreachable(client, monkeypatch):
    token = _ark_client(client)
    _forbid_head(monkeypatch)

    def fail(*args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(requests, "get", fail)
    data = _test(client, token, "ark").get_json()["data"]
    assert data["network"]["reachable"] is False
    assert data["key"]["status"] == "unknown"
    assert data["verified"] is False


def test_atlas_and_luma_are_network_probes_without_authorization(client, monkeypatch):
    _user, token = support.register_and_login(client, "conntext")
    response = _put(
        client, token, "luma",
        api_key="luma-secret-9999",
        base_url=PUBLIC_BASE_URL,
    )
    assert response.status_code == 200, response.get_json()

    _forbid_head(monkeypatch)
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["headers"] = kwargs.get("headers") or {}
        return FakeResponse(404, {"message": "not found"})

    monkeypatch.setattr(requests, "get", fake_get)
    data = _test(client, token, "luma").get_json()["data"]
    assert data["network"]["reachable"] is True
    assert data["key"]["status"] == "unsupported"
    assert data["verified"] is False
    assert "无法通过此方式验证" in data["message"]
    assert "Authorization" not in calls["headers"]
    assert calls["url"] == PUBLIC_BASE_URL


def test_deepseek_compatible_models_endpoint_verifies_key(client, monkeypatch):
    _user, token = support.register_and_login(client, "conndeepseek")
    response = _put(
        client, token, "llm",
        api_key="sk-deepseek-test-4321",
        base_url=PUBLIC_BASE_URL,
        model="deepseek-chat",
    )
    assert response.status_code == 200, response.get_json()
    _forbid_head(monkeypatch)

    monkeypatch.setattr(
        requests, "get",
        lambda *a, **k: FakeResponse(
            200, {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}
        ),
    )
    data = _test(client, token, "llm").get_json()["data"]
    assert data["key"]["status"] == "verified"
    assert data["verified"] is True
    assert data["model"]["status"] == "listed"
    assert data["model"]["model_id"] == "deepseek-chat"


def test_llm_404_says_cannot_verify(client, monkeypatch):
    _user, token = support.register_and_login(client, "connllm404")
    response = _put(
        client, token, "llm",
        api_key="sk-test-llm-9876",
        base_url=PUBLIC_BASE_URL,
    )
    assert response.status_code == 200, response.get_json()
    _forbid_head(monkeypatch)
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse(404, text="not found")
    )
    data = _test(client, token, "llm").get_json()["data"]
    assert data["key"]["status"] == "unsupported"
    assert data["verified"] is False
    assert "无法通过此方式验证" in data["message"]
