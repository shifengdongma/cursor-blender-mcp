# -*- coding: utf-8 -*-
"""Prompt document write permissions and update whitelist."""
from __future__ import absolute_import

from tests import support


def _admin_client(client, tmp_path):
    support.create_admin(tmp_path)
    admin_client = client.application.test_client()
    _user, token = support.login_and_token(
        admin_client, "rootadmin", "AdminPass12345"
    )
    return admin_client, token


def _create(admin_client, token, title="Prompt 文档"):
    response = admin_client.post(
        "/api/prompts/documents",
        json={
            "title": title,
            "category": "venue",
            "content": "初始内容",
            "keywords": "场馆, 光影",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_non_admin_cannot_write_prompt_documents(client):
    _user, token = support.register_and_login(client, "prompt_normal")
    for method, path in (
        ("post", "/api/prompts/documents"),
        ("put", "/api/prompts/documents/missing"),
        ("delete", "/api/prompts/documents/missing"),
    ):
        response = getattr(client, method)(
            path,
            json={"title": "x"} if method != "delete" else None,
            headers=support.auth_headers(token),
        )
        assert response.status_code == 403, (method, response.get_json())


def test_admin_can_create_update_and_delete_prompt_documents(client, tmp_path):
    admin_client, token = _admin_client(client, tmp_path)
    doc = _create(admin_client, token)
    original_created_at = doc["created_at"]

    response = admin_client.put(
        "/api/prompts/documents/{0}".format(doc["id"]),
        json={
            "title": "更新后的标题",
            "category": "shot",
            "content": "更新后的内容",
            "keywords": ["镜头", "运镜"],
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200, response.get_json()
    updated = response.get_json()["data"]
    assert updated["id"] == doc["id"]
    assert updated["title"] == "更新后的标题"
    assert updated["category"] == "shot"
    assert updated["content"] == "更新后的内容"
    assert updated["keywords"] == "镜头, 运镜"
    assert updated["created_at"] == original_created_at

    response = admin_client.delete(
        "/api/prompts/documents/{0}".format(doc["id"]),
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200, response.get_json()
    assert admin_client.get(
        "/api/prompts/documents/{0}".format(doc["id"])
    ).status_code == 404


def test_prompt_document_update_rejects_unknown_or_invalid_fields(client, tmp_path):
    admin_client, token = _admin_client(client, tmp_path)
    doc = _create(admin_client, token)
    url = "/api/prompts/documents/{0}".format(doc["id"])

    invalid_payloads = [
        {"id": "hijacked"},
        {"created_at": 1},
        {"source_file": "hijacked.json"},
        {"title": "   "},
        {"title": "x" * 201},
        {"category": "not-a-category"},
        {"content": ["not", "text"]},
        {"keywords": {"bad": "shape"}},
    ]
    for payload in invalid_payloads:
        response = admin_client.put(
            url,
            json=payload,
            headers=support.auth_headers(token),
        )
        assert response.status_code == 400, (payload, response.get_json())

    unchanged = admin_client.get(url).get_json()["data"]
    assert unchanged["id"] == doc["id"]
    assert unchanged["title"] == "Prompt 文档"


def test_prompt_document_list_remains_readable_for_normal_users(client, tmp_path):
    admin_client, token = _admin_client(client, tmp_path)
    _create(admin_client, token, title="普通用户可读")

    normal = client.application.test_client()
    support.register_and_login(normal, "prompt_reader")
    response = normal.get("/api/prompts/documents")
    assert response.status_code == 200, response.get_json()
    items = response.get_json()["data"]["items"]
    assert any(item["title"] == "普通用户可读" for item in items)
