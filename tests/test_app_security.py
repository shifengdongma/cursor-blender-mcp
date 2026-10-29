# -*- coding: utf-8 -*-
"""Stage A: authentication, CSRF, session revocation and route protection."""
from __future__ import absolute_import

import pytest

from backend.auth_service import AuthService
from backend.web_security import safe_redirect_target
from tests import support


def test_pages_redirect_and_apis_return_401(client):
    response = client.get("/creative-studio")
    assert response.status_code == 302
    assert "/login?next=/creative-studio" in response.headers["Location"]

    response = client.get("/api/creative/projects")
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"

    response = client.get("/api/assets")
    assert response.status_code == 401


def test_register_login_logout_flow(client):
    user, token = support.register_and_login(client, "flowuser")
    assert user["role"] == "user"
    assert user["tenant_id"] == "tenant_platform"

    response = client.get("/api/auth/status")
    assert response.get_json()["data"]["logged_in"] is True

    response = client.get("/api/creative/projects")
    assert response.status_code == 200

    response = client.post("/api/auth/logout", headers=support.auth_headers(token))
    assert response.status_code == 200
    assert client.get("/api/creative/projects").status_code == 401


def test_registration_validation_and_duplicate_case_insensitive(client):
    token = support.csrf(client)
    response = client.post(
        "/api/auth/register",
        json={"username": "weak", "password": "short", "confirm_password": "short",
              "nickname": "Weak", "terms_accepted": True},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "weak_password"

    token = support.csrf(client)
    response = client.post(
        "/api/auth/register",
        json={"username": "noterms", "password": "password123", "confirm_password": "password123",
              "nickname": "NoTerms"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "terms_required"

    response = support.register(client, "CaseUser", email="case@example.com")
    assert response.status_code == 201

    response = support.register(client, "caseuser", email="other@example.com")
    assert response.status_code == 409
    assert response.get_json()["error"] == "username_taken"

    response = support.register(client, "otheruser", email="CASE@example.com")
    assert response.status_code == 409
    assert response.get_json()["error"] == "email_taken"


def test_registration_cannot_self_assign_admin(client):
    token = support.csrf(client)
    response = client.post(
        "/api/auth/register",
        json={"username": "roleuser", "password": "password123", "confirm_password": "password123",
              "nickname": "Role", "terms_accepted": True, "role": "admin"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["user"]["role"] == "user"


def test_csrf_is_required_and_rotated(client):
    response = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_invalid"

    old_token = support.csrf(client)
    response = client.post(
        "/api/auth/register",
        json={"username": "csrfuser", "password": "password123", "confirm_password": "password123",
              "nickname": "CSRF", "terms_accepted": True},
        headers=support.auth_headers("wrong-token"),
    )
    assert response.status_code == 403

    response = client.post(
        "/api/auth/register",
        json={"username": "csrfuser", "password": "password123", "confirm_password": "password123",
              "nickname": "CSRF", "terms_accepted": True},
        headers=support.auth_headers(old_token),
    )
    assert response.status_code == 201
    new_token = response.get_json()["data"]["csrf_token"]
    assert new_token != old_token

    # The pre-login token is rotated out.
    response = client.post("/api/auth/logout", headers=support.auth_headers(old_token))
    assert response.status_code == 403
    response = client.post("/api/auth/logout", headers=support.auth_headers(new_token))
    assert response.status_code == 200


def test_password_change_invalidates_old_session(client):
    user, token = support.register_and_login(client, "pwuser")
    response = client.put(
        "/api/user/password",
        json={"current_password": "password123", "new_password": "newpassword123",
              "confirm_password": "newpassword123"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    assert client.get("/api/user/profile").status_code == 401

    response = support.login(client, "pwuser", "password123")
    assert response.status_code == 401
    response = support.login(client, "pwuser", "newpassword123")
    assert response.status_code == 200


def test_session_version_revocation_and_disabled_login(client, tmp_path):
    user, token = support.register_and_login(client, "revokeuser")
    service = AuthService(str(tmp_path))
    service.revoke_sessions(user["id"])
    assert client.get("/api/user/profile").status_code == 401

    other = support.register(client, "disableduser")
    assert other.status_code == 201
    target = other.get_json()["data"]["user"]
    service.admin_update_status(target["id"], "disabled", actor_id="operator")
    response = support.login(client, "disableduser")
    assert response.status_code == 403
    assert response.get_json()["error"] == "account_disabled"


def test_role_change_revokes_existing_session_and_admin_api_forbidden(client, tmp_path):
    normal, normal_token = support.register_and_login(client, "normaluser")
    support.create_admin(tmp_path)
    admin_client = client.application.test_client()
    admin, admin_token = support.login_and_token(admin_client, "rootadmin", "AdminPass12345")

    response = client.get("/api/admin/users")
    assert response.status_code == 403

    response = admin_client.patch(
        "/api/admin/users/{0}/role".format(normal["id"]),
        json={"role": "admin"},
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == "admin"

    # The original session was issued with the previous session_version.
    assert client.get("/api/user/profile").status_code == 401
    relogin = support.login_and_token(client, "normaluser", "password123")
    assert relogin[0]["role"] == "admin"


def test_open_redirect_target_is_rejected():
    assert safe_redirect_target("/creative-studio?x=1") == "/creative-studio?x=1"
    assert safe_redirect_target("//evil.example") == "/"
    assert safe_redirect_target("https://evil.example") == "/"
    assert safe_redirect_target("\\\\evil.example") == "/"
    assert safe_redirect_target("/api/creative/projects") == "/"


def test_static_html_bypass_and_health_disclosure(client):
    assert client.get("/web/creative-studio.html").status_code == 404
    assert client.get("/web/api-client.js").status_code == 200

    response = client.get("/api/health")
    assert response.status_code == 200
    assert set(response.get_json()["data"].keys()) == {"status"}

    assert client.get("/api/health/dependencies").status_code == 401
    support.register_and_login(client, "healthuser")
    assert client.get("/api/health/dependencies").status_code == 403
