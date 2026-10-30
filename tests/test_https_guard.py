# -*- coding: utf-8 -*-
"""Credential HTTPS guard is opt-in; the current HTTP deployment stays usable."""
from __future__ import absolute_import

from tests import support


def _put(client, token, provider="llm", **payload):
    return client.put(
        "/api/user/provider-credentials/{0}".format(provider),
        json=payload,
        headers=support.auth_headers(token),
    )


def _test(client, token, provider="llm"):
    return client.post(
        "/api/user/provider-credentials/{0}/test".format(provider),
        headers=support.auth_headers(token),
    )


def test_http_credentials_allowed_by_default(client):
    _user, token = support.register_and_login(client, "httpsdefault")
    response = _put(client, token, api_key="sk-http-default-1234")
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["has_key"] is True


def test_enforced_guard_rejects_http_mutations(tmp_path):
    app = support.make_app(tmp_path, CREDENTIAL_REQUIRE_HTTPS=True)
    client = app.test_client()
    _user, token = support.register_and_login(client, "httpsenforced")

    put_response = _put(client, token, api_key="sk-http-enforced-1234")
    assert put_response.status_code == 403, put_response.get_json()
    assert put_response.get_json()["error"] == "https_required"

    test_response = _test(client, token)
    assert test_response.status_code == 403, test_response.get_json()
    assert test_response.get_json()["error"] == "https_required"

    delete_response = client.delete(
        "/api/user/provider-credentials/llm", headers=support.auth_headers(token)
    )
    assert delete_response.status_code == 403
    assert delete_response.get_json()["error"] == "https_required"

    generation_response = client.post(
        "/api/user/provider-credentials/llm/test-generation",
        json={"model_key": "openai_gpt_image_1", "confirm_billing": True},
        headers=support.auth_headers(token),
    )
    assert generation_response.status_code == 403
    assert generation_response.get_json()["error"] == "https_required"


def test_enforced_guard_allows_direct_https(tmp_path):
    app = support.make_app(tmp_path, CREDENTIAL_REQUIRE_HTTPS=True)
    client = app.test_client()
    _user, token = support.register_and_login(client, "httpsdirect")
    response = client.put(
        "/api/user/provider-credentials/llm",
        json={"api_key": "sk-https-direct-1234"},
        headers=support.auth_headers(token),
        base_url="https://localhost",
    )
    assert response.status_code == 200, response.get_json()


def test_enforced_guard_allows_trusted_proxy_header(tmp_path):
    app = support.make_app(
        tmp_path, CREDENTIAL_REQUIRE_HTTPS=True, TRUST_PROXY=True
    )
    client = app.test_client()
    _user, token = support.register_and_login(client, "httpsproxy")
    headers = support.auth_headers(token)
    headers["X-Forwarded-Proto"] = "https"
    response = client.put(
        "/api/user/provider-credentials/llm",
        json={"api_key": "sk-https-proxy-1234"},
        headers=headers,
    )
    assert response.status_code == 200, response.get_json()
