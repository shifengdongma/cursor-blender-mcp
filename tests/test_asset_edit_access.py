# -*- coding: utf-8 -*-
"""Task 5: shared asset visibility semantics, editable metadata and can_edit."""
from __future__ import absolute_import

import io
import time

from backend.database import get_database
from tests import support

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80


def _upload(client, token, filename="shared.png", content=PNG, name="Shared asset"):
    return client.post(
        "/api/assets/upload",
        data={"file": (io.BytesIO(content), filename), "name": name},
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )


def _set_tenant(username, tenant_id):
    """Move an auth user to another tenant; sessions reload users per request."""
    get_database().update(
        "auth_users",
        {"tenant_id": tenant_id, "updated_at": int(time.time())},
        "username = ? COLLATE NOCASE",
        (username,),
    )


def _upload_id(response):
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def _share(client, token, asset_id):
    response = client.put(
        "/api/assets/{0}".format(asset_id),
        json={"visibility": "shared"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["visibility"] == "shared", data
    return data


def test_shared_asset_readable_within_tenant(client):
    _, token_a = support.register_and_login(client, "share_a")
    _set_tenant("share_a", "tenant_shared")
    asset_id = _upload_id(_upload(client, token_a))
    _share(client, token_a, asset_id)

    other = client.application.test_client()
    _, token_b = support.register_and_login(other, "share_b")
    _set_tenant("share_b", "tenant_shared")

    listing = other.get("/api/assets").get_json()["data"]
    item = next((entry for entry in listing["items"] if entry["id"] == asset_id), None)
    assert item is not None
    assert item["can_edit"] is False
    assert listing["total"] >= 1

    detail = other.get("/api/assets/{0}".format(asset_id))
    assert detail.status_code == 200, detail.get_json()
    assert detail.get_json()["data"]["can_edit"] is False

    assert other.get("/api/assets/{0}/file".format(asset_id)).status_code == 200
    assert other.get("/api/assets/{0}/download".format(asset_id)).status_code == 200

    forbidden = other.put(
        "/api/assets/{0}".format(asset_id),
        json={"name": "Hijacked"},
        headers=support.auth_headers(token_b),
    )
    assert forbidden.status_code == 403


def test_shared_asset_not_readable_across_tenants(client):
    _, token_a = support.register_and_login(client, "cross_a")
    _set_tenant("cross_a", "tenant_alpha")
    asset_id = _upload_id(_upload(client, token_a))
    _share(client, token_a, asset_id)

    other = client.application.test_client()
    _, _token_b = support.register_and_login(other, "cross_b")
    _set_tenant("cross_b", "tenant_other")

    listing = other.get("/api/assets").get_json()["data"]
    assert listing["total"] == 0
    assert all(entry["id"] != asset_id for entry in listing["items"])

    summary = other.get("/api/assets/summary").get_json()["data"]
    assert summary["images"] == 0
    assert summary["total"] == 0

    assert other.get("/api/assets/{0}".format(asset_id)).status_code == 403
    assert other.get("/api/assets/{0}/file".format(asset_id)).status_code == 403
    assert other.get("/api/assets/{0}/download".format(asset_id)).status_code == 403


def test_edit_metadata_and_validation(client):
    _, token = support.register_and_login(client, "edituser")
    asset_id = _upload_id(_upload(client, token))

    response = client.put(
        "/api/assets/{0}".format(asset_id),
        json={
            "name": "  新名称  ",
            "description": "新的描述",
            "venue_type": "modern_gallery",
            "visibility": "shared",
            "metadata": {"source": "test"},
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["name"] == "新名称"
    assert data["description"] == "新的描述"
    assert data["venue_type"] == "modern_gallery"
    assert data["visibility"] == "shared"
    assert data["metadata"] == {"source": "test"}
    assert data["can_edit"] is True

    for payload in (
        {"name": "   "},
        {"name": "x" * 121},
        {"name": 123},
        {"description": "x" * 2001},
        {"venue_type": "moon_base"},
        {"visibility": "public"},
        {"metadata": ["not", "a", "dict"]},
    ):
        response = client.put(
            "/api/assets/{0}".format(asset_id),
            json=payload,
            headers=support.auth_headers(token),
        )
        assert response.status_code == 400, (payload, response.get_json())
        assert response.get_json()["error"] == "invalid_asset_update"

    response = client.put(
        "/api/assets/{0}".format(asset_id),
        json={"unknown_field": "ignored", "name": "Renamed"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["name"] == "Renamed"
    assert "unknown_field" not in response.get_json()["data"]


def test_can_edit_flag(client, tmp_path):
    _, token_a = support.register_and_login(client, "canedit_a")
    _set_tenant("canedit_a", "tenant_canedit")
    asset_id = _upload_id(_upload(client, token_a))
    _share(client, token_a, asset_id)

    owner_listing = client.get("/api/assets").get_json()["data"]["items"]
    owner_item = next(entry for entry in owner_listing if entry["id"] == asset_id)
    assert owner_item["can_edit"] is True
    assert client.get("/api/assets/{0}".format(asset_id)).get_json()["data"]["can_edit"] is True

    other = client.application.test_client()
    support.register_and_login(other, "canedit_b")
    _set_tenant("canedit_b", "tenant_canedit")
    viewer_listing = other.get("/api/assets").get_json()["data"]["items"]
    viewer_item = next(entry for entry in viewer_listing if entry["id"] == asset_id)
    assert viewer_item["can_edit"] is False
    assert other.get("/api/assets/{0}".format(asset_id)).get_json()["data"]["can_edit"] is False

    support.create_admin(tmp_path)
    admin_client = client.application.test_client()
    support.login_and_token(admin_client, "rootadmin", "AdminPass12345")
    admin_item = next(
        entry
        for entry in admin_client.get("/api/assets").get_json()["data"]["items"]
        if entry["id"] == asset_id
    )
    assert admin_item["can_edit"] is True
    assert admin_item["owner_user_id"]
    admin_detail = admin_client.get("/api/assets/{0}".format(asset_id)).get_json()["data"]
    assert admin_detail["can_edit"] is True
