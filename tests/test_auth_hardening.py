# -*- coding: utf-8 -*-
"""Stage A hardening: guard ordering, lockout recovery, next sanitising, RBAC."""
from __future__ import absolute_import

import json
import os

import pytest

from backend.auth_service import AuthService
from backend.config import _resolve_secret_key
from backend.database import get_database
from backend.tenant_service import TenantService
from tests import support


def test_anonymous_unsafe_api_without_csrf_returns_401(client):
    response = client.post("/api/creative/projects", json={"name": "x"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_public_login_without_csrf_still_returns_403(client):
    response = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_invalid"


def test_login_next_is_sanitized(client):
    support.register_and_login(client, "nextuser")
    token = client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    client.post("/api/auth/logout", headers=support.auth_headers(token))

    cases = [
        ("/creative-studio?x=1", "/creative-studio?x=1"),
        ("//evil.example", "/"),
        ("https://evil.example", "/"),
        ("\\\\evil.example", "/"),
        ("/api/creative/projects", "/"),
        ("", "/"),
    ]
    for target, expected in cases:
        token = support.csrf(client)
        response = client.post(
            "/api/auth/login",
            json={"username": "nextuser", "password": "password123", "next": target},
            headers=support.auth_headers(token),
        )
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["data"]["redirect_to"] == expected
        new_token = response.get_json()["data"]["csrf_token"]
        client.post("/api/auth/logout", headers=support.auth_headers(new_token))


def test_reenable_clears_lockout(client, tmp_path):
    support.register(client, "lockeduser")
    anon = client.application.test_client()
    for _ in range(3):
        response = support.login(anon, "lockeduser", "wrong-password")
        assert response.status_code == 401
    # The third failure arms the lockout; the next attempt is rejected as locked.
    assert support.login(anon, "lockeduser", "wrong-password").status_code == 423

    support.create_admin(tmp_path)
    admin_client = client.application.test_client()
    _, admin_token = support.login_and_token(admin_client, "rootadmin", "AdminPass12345")
    target = AuthService(str(tmp_path)).get_user_by_username("lockeduser")
    assert target["failed_login_count"] >= 3

    response = admin_client.patch(
        "/api/admin/users/{0}/status".format(target["id"]),
        json={"status": "active"},
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200, response.get_json()
    fresh = AuthService(str(tmp_path)).get_user(target["id"])
    assert fresh["failed_login_count"] == 0
    assert fresh["locked_until"] is None
    assert support.login(anon, "lockeduser", "password123").status_code == 200


def test_capabilities_are_server_derived(client, tmp_path):
    support.register_and_login(client, "capuser")
    data = client.get("/api/auth/status").get_json()["data"]
    assert data["capabilities"] == {"is_admin": False, "view_compute": False}

    support.create_admin(tmp_path, username="capadmin")
    admin_client = client.application.test_client()
    support.login_and_token(admin_client, "capadmin", "AdminPass12345")
    data = admin_client.get("/api/auth/status").get_json()["data"]
    assert data["capabilities"] == {"is_admin": True, "view_compute": True}


def test_registration_can_be_closed(client):
    cfg = client.application.config["AIGV_CONFIG"]
    previous = cfg.ALLOW_REGISTRATION
    cfg.ALLOW_REGISTRATION = False
    try:
        response = support.register(client, "closeduser")
        assert response.status_code == 403
        assert response.get_json()["error"] == "registration_closed"
    finally:
        cfg.ALLOW_REGISTRATION = previous


def test_users_json_is_never_an_authentication_source(client, tmp_path):
    legacy_path = os.path.join(str(tmp_path), "users.json")
    with open(legacy_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "legacy": {
                    "username": "legacy",
                    "password_hash": "pbkdf2:sha256:injected",
                    "role": "admin",
                }
            },
            handle,
        )
    response = support.login(client, "legacy", "password123")
    assert response.status_code == 401


def test_audit_flag_disables_writes(tmp_path):
    from tests.support import make_app, reset_globals

    reset_globals()
    try:
        app = make_app(tmp_path, AUDIT_ENABLED=False)
        client = app.test_client()
        support.register_and_login(client, "noaudit")
        assert get_database().count("ops_events") == 0
    finally:
        reset_globals()


def test_production_requires_explicit_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _resolve_secret_key(str(tmp_path), "production")


def test_production_rejects_short_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "short-secret")
    with pytest.raises(RuntimeError):
        _resolve_secret_key(str(tmp_path), "production")


def test_session_cookie_flags(client):
    config = client.application.config
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert config["SESSION_COOKIE_NAME"] == "aigv_session"


def test_project_owner_is_not_a_platform_admin(client, tmp_path):
    user, _token = support.register_and_login(client, "ownertest")
    db = get_database()
    membership = db.fetch_one(
        "SELECT * FROM project_memberships WHERE user_id = ?", (user["id"],)
    )
    assert membership is not None
    assert membership["role"] == "owner"
    # Owning a project does not grant compute/cloud permissions implicitly.
    assert TenantService(str(tmp_path)).check_permission(
        user["tenant_id"], user["id"], membership["project_id"], "view_compute"
    ) is False
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/compute-platform").status_code == 403
