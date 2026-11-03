# -*- coding: utf-8 -*-
"""Unified document library: summary counts, permissions and server pagination."""
from __future__ import absolute_import

import io
import time

from backend.database import get_database
from tests import support

TXT = b"hello unified document library"


def _upload_document(client, token, name="Document asset", filename="notes.txt",
                     content=TXT):
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


def _admin_client(app, tmp_path):
    support.create_admin(tmp_path)
    client = app.test_client()
    user, token = support.login_and_token(
        client, "rootadmin", "AdminPass12345"
    )
    return client, user, token


def _create_prompt_doc(client, token, title, content="prompt content",
                       category="venue", keywords="museum, stage"):
    response = client.post(
        "/api/prompts/documents",
        json={
            "title": title,
            "category": category,
            "content": content,
            "keywords": keywords,
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def _documents(client, **params):
    query = "&".join(
        "{0}={1}".format(key, value) for key, value in params.items()
    )
    url = "/api/assets/documents" + ("?" + query if query else "")
    response = client.get(url)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def test_summary_merges_asset_and_prompt_documents(client, tmp_path):
    user, token = support.register_and_login(client, "docs_summary")
    asset_id = _upload_document(client, token, "普通文档")
    admin_client, _admin, admin_token = _admin_client(
        client.application, tmp_path
    )
    prompt_id = _create_prompt_doc(admin_client, admin_token, "场馆 Prompt")

    summary = client.get("/api/assets/summary").get_json()["data"]
    assert summary["documents"] == 1
    assert summary["prompt_documents"] == 1
    assert summary["document_total"] == 2
    assert summary["venue_presets"] == 0
    assert summary["storage"]["used_bytes"] == len(TXT)
    assert summary["storage"]["actual_used_bytes"] == len(TXT)
    assert summary["storage"]["quota_bytes"] == 2000000000000
    assert summary["storage"]["source"] == "actual"
    assert summary["storage"]["unit"] == "TB"
    assert summary["storage"]["bytes_per_tb"] == 1000000000000

    listing = _documents(client, limit=20, offset=0)
    assert listing["total"] == 2
    assert listing["counts"] == {
        "asset": 1, "prompt_document": 1, "total": 2
    }
    assert {item["source_type"] for item in listing["items"]} == {
        "asset", "prompt_document"
    }
    assert {item["id"] for item in listing["items"]} == {asset_id, prompt_id}


def test_private_asset_documents_respect_scope_but_prompt_docs_are_global(
        client, tmp_path):
    _user_a, token_a = support.register_and_login(client, "docs_private_a")
    _upload_document(client, token_a, "A 私有文档")
    admin_client, _admin, admin_token = _admin_client(
        client.application, tmp_path
    )
    _create_prompt_doc(admin_client, admin_token, "全局 Prompt")

    other = client.application.test_client()
    _user_b, _token_b = support.register_and_login(other, "docs_private_b")
    summary = other.get("/api/assets/summary").get_json()["data"]
    assert summary["documents"] == 0
    assert summary["prompt_documents"] == 1
    assert summary["document_total"] == 1

    listing = _documents(other, limit=20, offset=0)
    assert listing["total"] == 1
    assert listing["items"][0]["source_type"] == "prompt_document"

    admin_summary = admin_client.get("/api/assets/summary").get_json()["data"]
    assert admin_summary["documents"] == 1
    assert admin_summary["document_total"] == 2


def test_unified_documents_pagination_sort_search_and_source_type(client, tmp_path):
    _user, _token = support.register_and_login(client, "docs_page")
    admin_client, _admin, admin_token = _admin_client(
        client.application, tmp_path
    )
    ids = []
    for index, title in enumerate(["Alpha 场馆", "Beta 镜头", "Gamma 光影"]):
        ids.append(_create_prompt_doc(
            admin_client,
            admin_token,
            title,
            content="content {0} keyword{0}".format(index),
            category=["venue", "shot", "lighting"][index],
        ))
    asset_id = _upload_document(admin_client, admin_token, "Delta 文档")

    # Make the timestamps deterministic: asset oldest, then prompt docs.
    now = int(time.time())
    db = get_database()
    db.update("assets", {"created_at": now - 100}, "id = ?", (asset_id,))
    for offset, doc_id in enumerate(ids):
        db.update(
            "prompt_documents",
            {"created_at": now - 30 + offset},
            "id = ?",
            (doc_id,),
        )

    first = _documents(admin_client, limit=2, offset=0, sort="newest")
    second = _documents(admin_client, limit=2, offset=2, sort="newest")
    assert first["total"] == 4
    assert len(first["items"]) == 2 and len(second["items"]) == 2
    page_ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(set(page_ids)) == 4

    oldest = _documents(admin_client, limit=4, offset=0, sort="oldest")
    assert oldest["items"][0]["id"] == asset_id
    by_name = _documents(admin_client, limit=4, offset=0, sort="name")
    assert by_name["items"][0]["name"].startswith("Alpha")

    searched = _documents(admin_client, limit=20, offset=0, q="keyword1")
    assert searched["total"] == 1
    assert searched["items"][0]["source_type"] == "prompt_document"
    assert "keyword1" in searched["items"][0]["content"]

    asset_only = _documents(admin_client, limit=20, offset=0, source_type="asset")
    assert asset_only["total"] == 1
    assert asset_only["counts"]["prompt_document"] == 0
    prompt_only = _documents(
        admin_client, limit=20, offset=0, source_type="prompt_document"
    )
    assert prompt_only["total"] == 3
    assert prompt_only["counts"]["asset"] == 0


def test_same_title_in_both_tables_counts_twice(client, tmp_path):
    _user, token = support.register_and_login(client, "docs_dupe")
    asset_id = _upload_document(client, token, "相同标题")
    admin_client, _admin, admin_token = _admin_client(
        client.application, tmp_path
    )
    prompt_id = _create_prompt_doc(admin_client, admin_token, "相同标题")

    listing = _documents(client, limit=20, offset=0)
    assert listing["total"] == 2
    assert {item["id"] for item in listing["items"]} == {asset_id, prompt_id}
    assert {item["source_type"] for item in listing["items"]} == {
        "asset", "prompt_document"
    }


def test_unified_document_permissions_flags(client, tmp_path):
    _user, token = support.register_and_login(client, "docs_permissions")
    _upload_document(client, token, "普通用户文档")
    admin_client, _admin, admin_token = _admin_client(
        client.application, tmp_path
    )
    _create_prompt_doc(admin_client, admin_token, "管理员 Prompt")

    user_listing = _documents(client, limit=20, offset=0)
    asset_item = next(
        item for item in user_listing["items"] if item["source_type"] == "asset"
    )
    prompt_item = next(
        item for item in user_listing["items"]
        if item["source_type"] == "prompt_document"
    )
    assert asset_item["can_edit"] is True
    assert asset_item["can_delete"] is True
    assert prompt_item["can_edit"] is False
    assert prompt_item["can_delete"] is False

    admin_listing = _documents(admin_client, limit=20, offset=0)
    admin_prompt = next(
        item for item in admin_listing["items"]
        if item["source_type"] == "prompt_document"
    )
    assert admin_prompt["can_edit"] is True
    assert admin_prompt["can_delete"] is True


def test_unified_route_does_not_collide_with_asset_detail(client):
    support.register_and_login(client, "docs_route")
    response = client.get("/api/assets/documents")
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["items"] == []
    assert payload["total"] == 0
