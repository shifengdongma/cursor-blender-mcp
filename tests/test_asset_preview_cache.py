# -*- coding: utf-8 -*-
"""Task 6: GLB magic validation, preview flags and asset-file cache headers."""
from __future__ import absolute_import

import glob
import io
import os

from tests import support

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
GLB = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 76
OBJ = b"# test mesh\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def _upload(client, token, filename, content):
    return client.post(
        "/api/assets/upload",
        data={
            "file": (io.BytesIO(content), filename),
            "name": filename,
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )


def _stored_model_files(client):
    data_dir = client.application.config["AIGV_CONFIG"].DATA_DIR
    return glob.glob(os.path.join(data_dir, "assets", "models", "*", "*.glb"))


def test_glb_magic_validation_and_previewable(client):
    _, token = support.register_and_login(client, "glbuser")

    response = _upload(client, token, "model.glb", GLB)
    assert response.status_code == 201, response.get_json()
    asset = response.get_json()["data"]
    assert asset["previewable"] is True
    assert asset["preview_reason"] is None
    assert asset["file_ext"] == "glb"
    assert asset["checksum_sha256"]
    assert "?v=" in asset["file_url"]
    assert asset["file_url"].endswith(asset["checksum_sha256"][:12])
    assert len(_stored_model_files(client)) == 1

    fake = _upload(client, token, "fake.glb", b"XXXX" + b"\x00" * 76)
    assert fake.status_code == 400
    assert fake.get_json()["error"] == "invalid_upload"

    listing = client.get("/api/assets").get_json()["data"]
    assert listing["total"] == 1
    assert len(_stored_model_files(client)) == 1


def test_obj_is_download_only(client):
    _, token = support.register_and_login(client, "objuser")

    response = _upload(client, token, "model.obj", OBJ)
    assert response.status_code == 201, response.get_json()
    asset = response.get_json()["data"]
    assert asset["previewable"] is False
    assert asset["preview_reason"]
    assert "在线预览" in asset["preview_reason"]
    assert asset["file_ext"] == "obj"
    assert asset["file_url"]


def test_asset_file_cache_header(client):
    _, token = support.register_and_login(client, "cacheuser")
    response = _upload(client, token, "cache.png", PNG)
    assert response.status_code == 201, response.get_json()
    asset = response.get_json()["data"]

    served = client.get(asset["file_url"])
    assert served.status_code == 200
    cache_control = served.headers.get("Cache-Control", "")
    assert "private" in cache_control
    assert "max-age=86400" in cache_control
    assert served.headers.get("ETag")

    downloaded = client.get(asset["download_url"])
    assert downloaded.status_code == 200
    download_cache = downloaded.headers.get("Cache-Control", "")
    assert "private" in download_cache
    assert "max-age=86400" in download_cache

    listing = client.get("/api/assets")
    assert listing.status_code == 200
    assert listing.headers.get("Cache-Control") == "no-store"
