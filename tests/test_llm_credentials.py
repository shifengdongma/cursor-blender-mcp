# -*- coding: utf-8 -*-
"""LLM analysis runs with per-user credentials, and the storyboard worker is wired."""
from __future__ import absolute_import

import pytest

from backend import task_worker
from backend.creative_project_service import get_creative_project_service
from backend.credential_service import CredentialService
from backend.database import get_database
from backend.models import CreativeProject, GenerationTask
from backend.providers.base import ProviderError
from backend.task_service import get_task_service
from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"
USER_KEY = "sk-user-llm-1234"
USER_MODEL = "gpt-4o-mini"


def _setup(app, username):
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username=username, email="{0}@example.com".format(username)
    )
    return CredentialService(cfg.DATA_DIR, cfg), cfg, user


def _save_user_llm(svc, user):
    svc.upsert(
        user["id"],
        user.get("tenant_id"),
        "llm",
        api_key=USER_KEY,
        base_url=PUBLIC_BASE_URL,
        model=USER_MODEL,
    )


def _create_project(cfg, user):
    return get_creative_project_service(cfg.DATA_DIR).create_project(
        name="LLM 分析项目",
        tenant_id=user.get("tenant_id"),
        user_id=user["id"],
        status=CreativeProject.STATUS_DRAFT,
    )


def _create_storyboard_task(cfg, project, user):
    return get_task_service(cfg.DATA_DIR).create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_STORYBOARD,
        created_by=user["id"],
        params={"project_id": project.id, "credential_source": "user"},
    )


def _login(app, username):
    client = app.test_client()
    _user, token = support.login_and_token(client, username, password="AdminPass12345")
    return client, token


def _analyze(client, token, project_id):
    return client.post(
        "/api/creative/projects/{0}/analyze".format(project_id),
        headers=support.auth_headers(token),
    )


def test_analyze_accepts_user_llm_credential(app):
    svc, cfg, user = _setup(app, "llm_analyze_user")
    _save_user_llm(svc, user)
    project = _create_project(cfg, user)
    client, token = _login(app, "llm_analyze_user")

    response = _analyze(client, token, project.id)
    assert response.status_code in (201, 202), response.get_json()

    task_id = response.get_json()["data"]["id"]
    stored = get_task_service(cfg.DATA_DIR).get_task(task_id)
    assert stored.params["credential_source"] == "user"
    assert stored.params["project_id"] == project.id
    assert stored.created_by == user["id"]


def test_analyze_returns_configure_url_without_llm(app):
    _svc, cfg, user = _setup(app, "llm_analyze_missing")
    project = _create_project(cfg, user)
    client, token = _login(app, "llm_analyze_missing")

    response = _analyze(client, token, project.id)
    assert response.status_code == 400, response.get_json()
    payload = response.get_json()
    assert payload["error"] == "provider_not_configured"
    assert payload["details"]["configure_url"] == "/api-settings"


def test_storyboard_executor_uses_user_llm_and_imports_creative_project(app, monkeypatch):
    svc, cfg, user = _setup(app, "llm_executor_user")
    _save_user_llm(svc, user)
    project = _create_project(cfg, user)
    task = _create_storyboard_task(cfg, project, user)

    captured = {}

    class FakeLLMProvider(object):
        def __init__(self, api_key, base_url, model_name="gpt-4o"):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["model_name"] = model_name

        def generate_structured(self, system_prompt, user_prompt, schema):
            return {"shots": []}

    monkeypatch.setattr(task_worker, "LLMProvider", FakeLLMProvider)

    result = task_worker._execute_storyboard(task, cfg, get_database())

    assert captured == {
        "api_key": USER_KEY,
        "base_url": PUBLIC_BASE_URL,
        "model_name": USER_MODEL,
    }
    assert result == {"shots_count": 0}
    refreshed = get_creative_project_service(cfg.DATA_DIR).get_project(project.id)
    assert refreshed.status == CreativeProject.STATUS_READY


def test_storyboard_executor_fails_when_pinned_user_credential_missing(app):
    svc, cfg, user = _setup(app, "llm_executor_missing")
    _save_user_llm(svc, user)
    project = _create_project(cfg, user)
    task = _create_storyboard_task(cfg, project, user)
    svc.delete(user["id"], "llm")

    with pytest.raises(ProviderError) as exc:
        task_worker._execute_storyboard(task, cfg, get_database())
    assert exc.value.error_type == "llm_missing_key"
