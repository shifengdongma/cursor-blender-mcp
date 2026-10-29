# -*- coding: utf-8 -*-
"""Stage B: profile, admin user management, last-admin guard and audit."""
from __future__ import absolute_import

import base64
import io
import time

import pytest

from backend.auth_service import AuthError, AuthService
from backend.database import get_database
from backend.models import GenerationTask
from tests import support

# 1x1 transparent PNG (valid IHDR/IDAT/IEND, used to exercise avatar storage).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def test_profile_update_whitelist_and_stats(client):
    user, token = support.register_and_login(client, "profileuser", email="profile@example.com")

    response = client.get("/api/user/profile")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["stats"]["tasks_total"] == 0
    assert data["stats"]["images_completed"] == 0

    response = client.patch(
        "/api/user/profile",
        json={"nickname": "新昵称", "bio": "简介", "role": "admin", "status": "disabled"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["nickname"] == "新昵称"
    assert data["role"] == "user"
    assert data["status"] == "active"

    db = get_database()
    db.insert("generation_tasks", GenerationTask(
        creative_project_id=None,
        task_type="image",
        status="succeeded",
        created_by=user["id"],
        output_asset_id=None,
    ).to_insert_params())

    data = client.get("/api/user/profile").get_json()["data"]
    assert data["stats"]["tasks_total"] == 1
    assert data["stats"]["images_completed"] == 1


def test_profile_email_uniqueness(client):
    support.register_and_login(client, "emaila", email="same@example.com")
    other = client.application.test_client()
    _, token = support.register_and_login(other, "emailb", email="other@example.com")
    response = other.patch(
        "/api/user/profile",
        json={"email": "SAME@example.com"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "email_taken"


def test_avatar_validation_and_access(client, tmp_path):
    user_a, token_a = support.register_and_login(client, "avatar_a")
    response = client.post(
        "/api/user/avatar",
        data={"file": (io.BytesIO(PNG), "a.png")},
        headers=support.auth_headers(token_a),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["has_avatar"] is True
    assert client.get("/api/user/avatar").status_code == 200

    response = client.post(
        "/api/user/avatar",
        data={"file": (io.BytesIO(b"<html>fake</html>"), "a.png")},
        headers=support.auth_headers(token_a),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400

    # A valid magic header followed by garbage must not be accepted.
    truncated = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    response = client.post(
        "/api/user/avatar",
        data={"file": (io.BytesIO(truncated), "broken.png")},
        headers=support.auth_headers(token_a),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400

    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    response = client.post(
        "/api/user/avatar",
        data={"file": (io.BytesIO(huge), "big.png")},
        headers=support.auth_headers(token_a),
        content_type="multipart/form-data",
    )
    assert response.status_code == 413

    other = client.application.test_client()
    support.register_and_login(other, "avatar_b")
    assert other.get("/api/user/avatar").status_code == 404


def test_admin_management_and_audit(client, tmp_path):
    normal, normal_token = support.register_and_login(client, "manageduser")
    admin = support.create_admin(tmp_path)
    admin_client = client.application.test_client()
    _, admin_token = support.login_and_token(admin_client, "rootadmin", "AdminPass12345")

    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert admin_client.get("/admin/users").status_code == 200

    response = admin_client.get("/api/admin/users?q=managed&role=user&status=active")
    assert response.status_code == 200
    assert response.get_json()["data"]["total"] == 1

    response = admin_client.patch(
        "/api/admin/users/{0}".format(normal["id"]),
        json={"nickname": "Managed New", "email": "managed@example.com"},
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["nickname"] == "Managed New"

    response = admin_client.patch(
        "/api/admin/users/{0}/role".format(normal["id"]),
        json={"role": "admin"},
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == "admin"

    response = admin_client.patch(
        "/api/admin/users/{0}/status".format(normal["id"]),
        json={"status": "disabled"},
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "disabled"

    # The target's old session is invalid and disabled login is rejected.
    assert client.get("/api/user/profile").status_code == 401
    assert support.login(client, "manageduser").status_code == 403

    response = admin_client.post(
        "/api/admin/users/{0}/sessions/revoke".format(normal["id"]),
        headers=support.auth_headers(admin_token),
    )
    assert response.status_code == 200

    stats = admin_client.get("/api/admin/stats").get_json()["data"]
    assert stats["users"]["total"] == 2
    assert stats["users"]["admins"] == 1

    logs = admin_client.get("/api/admin/audit-logs?action=admin_role_change").get_json()["data"]
    assert logs["total"] >= 1
    assert logs["items"][0]["actor_user_id"] == admin["id"]


def test_self_role_and_status_changes_are_rejected(client, tmp_path):
    support.create_admin(tmp_path, username="admin_one")
    admin_client = client.application.test_client()
    admin, token = support.login_and_token(admin_client, "admin_one", "AdminPass12345")

    response = admin_client.patch(
        "/api/admin/users/{0}/role".format(admin["id"]),
        json={"role": "user"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "self_role_change"

    response = admin_client.patch(
        "/api/admin/users/{0}/status".format(admin["id"]),
        json={"status": "disabled"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "self_status_change"


def test_last_active_admin_guard(tmp_path):
    admin = support.create_admin(tmp_path, username="last_admin")
    service = AuthService(str(tmp_path))
    with pytest.raises(AuthError) as exc:
        service.admin_update_role(admin["id"], "user", actor_id="another-operator")
    assert exc.value.code == "last_admin"

    with pytest.raises(AuthError) as exc:
        service.admin_update_status(admin["id"], "disabled", actor_id="another-operator")
    assert exc.value.code == "last_admin"


def test_password_change_then_new_login(client):
    support.register_and_login(client, "pwchange", password="password123")
    token = client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    response = client.put(
        "/api/user/password",
        json={"current_password": "password123", "new_password": "newpassword123",
              "confirm_password": "newpassword123"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    assert client.get("/api/user/profile").status_code == 401
    assert support.login(client, "pwchange", "password123").status_code == 401
    assert support.login(client, "pwchange", "newpassword123").status_code == 200
