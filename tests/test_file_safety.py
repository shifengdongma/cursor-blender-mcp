# -*- coding: utf-8 -*-
"""Stage A: asset ownership, safe paths and upload validation."""
from __future__ import absolute_import

import io

import pytest

from backend.asset_service import AssetService, AssetServiceError
from tests import support

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80


def _upload(client, token, filename="pic.png", content=PNG, **form):
    data = {
        "file": (io.BytesIO(content), filename),
        "name": form.pop("name", "Picture"),
    }
    data.update(form)
    return client.post(
        "/api/assets/upload",
        data=data,
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )


def test_asset_ownership_and_validated_download(client):
    user_a, token_a = support.register_and_login(client, "assetuser_a")
    response = _upload(client, token_a)
    assert response.status_code == 201, response.get_json()
    asset = response.get_json()["data"]
    assert asset["visibility"] == "private"
    assert "file_path" not in asset
    assert asset["file_url"].startswith("/api/assets/{0}/file?v=".format(asset["id"]))
    assert asset["file_url"].endswith(asset["checksum_sha256"][:12])

    assert client.get(asset["file_url"]).status_code == 200
    assert client.get(asset["download_url"]).status_code == 200

    other = client.application.test_client()
    support.register_and_login(other, "assetuser_b")
    assert other.get("/api/assets").get_json()["data"]["total"] == 0
    assert other.get("/api/assets/{0}".format(asset["id"])).status_code == 403
    assert other.get(asset["file_url"]).status_code == 403


def test_upload_rejects_fake_image_and_bad_venue(client):
    _, token = support.register_and_login(client, "uploaduser")
    response = _upload(client, token, filename="fake.png", content=b"<html>not an image</html>")
    assert response.status_code == 400

    response = _upload(client, token, venue_type="../../outside")
    assert response.status_code == 400

    response = _upload(client, token, filename="bad.exe", content=b"MZ")
    assert response.status_code == 400


def test_asset_update_cannot_change_owner_or_path(client, tmp_path):
    user, token = support.register_and_login(client, "assetupdate")
    response = _upload(client, token)
    asset = response.get_json()["data"]

    response = client.put(
        "/api/assets/{0}".format(asset["id"]),
        json={"name": "Renamed", "file_path": "../aigv.db", "owner_user_id": "someone-else"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Renamed"

    service = AssetService(str(tmp_path))
    stored = service.get_asset(asset["id"])
    assert stored.file_path != "../aigv.db"
    assert stored.owner_user_id == user["id"]


def test_safe_path_and_traversal_endpoints(client, tmp_path):
    _, token = support.register_and_login(client, "pathuser")
    service = AssetService(str(tmp_path))
    owner = service.db.fetch_one("SELECT id FROM auth_users WHERE username = ?", ("pathuser",))["id"]
    malicious = service.create_asset(
        name="Bad path",
        asset_type="image",
        file_path="../aigv.db",
        owner_user_id=owner,
    )
    assert service.get_file_path_for_asset(malicious) is None
    assert client.get("/api/assets/{0}/file".format(malicious.id)).status_code == 404
    assert client.get("/api/assets/{0}/download".format(malicious.id)).status_code == 404

    response = client.get("/data/assets/../aigv.db")
    assert response.status_code in (401, 404)
    assert b"SQLite format" not in response.data


def test_referenced_asset_cannot_be_deleted(client):
    _, token = support.register_and_login(client, "refasset")
    response = _upload(client, token)
    asset = response.get_json()["data"]

    project_resp = client.post(
        "/api/creative/projects",
        json={"name": "引用项目"},
        headers=support.auth_headers(token),
    )
    project_id = project_resp.get_json()["data"]["id"]
    shot_resp = client.post(
        "/api/creative/projects/{0}/shots".format(project_id),
        json={"scene_title": "镜头"},
        headers=support.auth_headers(token),
    )
    shot_id = shot_resp.get_json()["data"]["id"]
    update_resp = client.put(
        "/api/creative/shots/{0}".format(shot_id),
        json={"primary_image_asset_id": asset["id"]},
        headers=support.auth_headers(token),
    )
    assert update_resp.status_code == 200

    response = client.delete(
        "/api/assets/{0}".format(asset["id"]),
        headers=support.auth_headers(token),
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "asset_in_use"


def test_asset_service_containment(tmp_path):
    service = AssetService(str(tmp_path))
    assert service._safe_asset_path("../aigv.db") is None
    assert service._safe_asset_path("/etc/passwd") is None
    with pytest.raises(AssetServiceError):
        service._validate_venue("../../evil")
