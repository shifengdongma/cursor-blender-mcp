# -*- coding: utf-8 -*-
"""Asset library capacity summary: scoped bytes, dedup and showcase mode."""
from __future__ import absolute_import

import io

from backend.asset_service import AssetService
from tests import support

TXT = b"0123456789" * 10


def _upload_document(client, token, name, filename="capacity.txt", content=TXT):
    response = client.post(
        "/api/assets/upload",
        data={
            "file": (io.BytesIO(content), filename),
            "name": name,
            "asset_type": "document",
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def test_actual_storage_sums_uploaded_bytes(client):
    _user, token = support.register_and_login(client, "storage_bytes")
    _upload_document(client, token, "十份文档", content=TXT)

    summary = client.get("/api/assets/summary").get_json()["data"]
    storage = summary["storage"]
    assert storage["source"] == "actual"
    assert storage["used_bytes"] == len(TXT)
    assert storage["actual_used_bytes"] == len(TXT)
    assert storage["quota_bytes"] == 2000000000000


def test_storage_deduplicates_same_file_path(client, tmp_path):
    user, _token = support.register_and_login(client, "storage_dedup")
    service = AssetService(str(tmp_path))
    owner = user.get("id")
    tenant_id = user.get("tenant_id")
    for index in range(2):
        service.create_asset(
            name="重复引用 {0}".format(index),
            asset_type="document",
            file_path="documents/same-file.txt",
            file_size=1234,
            owner_user_id=owner,
            tenant_id=tenant_id,
            visibility="private",
        )

    summary = client.get("/api/assets/summary").get_json()["data"]
    assert summary["storage"]["actual_used_bytes"] == 1234
    assert summary["storage"]["used_bytes"] == 1234


def test_storage_is_scoped_for_non_admin(client, tmp_path):
    _user_a, token_a = support.register_and_login(client, "storage_scope_a")
    _upload_document(client, token_a, "A 的文档", content=b"a" * 100)

    other = client.application.test_client()
    _user_b, _token_b = support.register_and_login(other, "storage_scope_b")
    summary = other.get("/api/assets/summary").get_json()["data"]
    assert summary["storage"]["actual_used_bytes"] == 0
    assert summary["storage"]["used_bytes"] == 0

    admin_app = client.application
    support.create_admin(tmp_path)
    admin_client = admin_app.test_client()
    support.login_and_token(admin_client, "rootadmin", "AdminPass12345")
    admin_summary = admin_client.get("/api/assets/summary").get_json()["data"]
    assert admin_summary["storage"]["actual_used_bytes"] == 100


def test_showcase_storage_values_are_display_only(tmp_path):
    app = support.make_app(
        tmp_path,
        ASSET_STORAGE_SHOWCASE_MODE=True,
        ASSET_STORAGE_SHOWCASE_USED_TB=1.94,
        ASSET_STORAGE_QUOTA_TB=2.0,
    )
    client = app.test_client()
    _user, _token = support.register_and_login(client, "storage_showcase")
    summary = client.get("/api/assets/summary").get_json()["data"]
    storage = summary["storage"]
    assert storage["source"] == "showcase"
    assert storage["used_bytes"] == 1940000000000
    assert storage["quota_bytes"] == 2000000000000
    assert storage["actual_used_bytes"] == 0
    assert storage["actual_quota_bytes"] == 2000000000000


def test_empty_library_reports_zero_storage(client):
    support.register_and_login(client, "storage_empty")
    summary = client.get("/api/assets/summary").get_json()["data"]
    assert summary["documents"] == 0
    assert summary["prompt_documents"] == 0
    assert summary["document_total"] == 0
    assert summary["storage"]["used_bytes"] == 0
    assert summary["storage"]["actual_used_bytes"] == 0
