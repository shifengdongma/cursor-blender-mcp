# -*- coding: utf-8 -*-
"""Legacy workbench /api/jobs must use per-user credentials and the selected model."""
from __future__ import absolute_import

import json
import os

import pytest

from backend import generation_models
from backend.credential_service import CredentialService
from backend.provider_router import ProviderRouter, ProviderRoutingError
from backend.providers.base import ProviderRejected
from backend.task_service import get_task_service
from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"
ARK_KEY = "ark-legacy-secret-7788"


def _cfg(app):
    return app.config["AIGV_CONFIG"]


def _ark_user(cfg, username="legacyuser", overrides=None):
    user = support.create_admin(cfg.DATA_DIR, username=username)
    service = CredentialService(cfg.DATA_DIR, cfg)
    service.upsert(
        user["id"],
        user.get("tenant_id"),
        "ark",
        api_key=ARK_KEY,
        base_url=PUBLIC_BASE_URL,
        model_overrides=overrides or {},
    )
    return user


def test_router_uses_user_key_and_selected_seedance_20_model(app):
    cfg = _cfg(app)
    user = _ark_user(
        cfg, "legacyrouter",
        overrides={"ark_seedance_20": "custom-seedance-20-endpoint"},
    )
    router = ProviderRouter(
        cfg, user_id=user["id"], model_key="ark_seedance_20",
        credential_source="user",
    )
    provider = router.create_provider("ark_seedance")
    assert provider.api_key == ARK_KEY
    assert provider.base_url == PUBLIC_BASE_URL
    assert provider.model_id == "custom-seedance-20-endpoint"


def test_router_missing_user_credential_uses_unified_message(app):
    cfg = _cfg(app)
    user = support.create_admin(cfg.DATA_DIR, username="legacymissing")
    router = ProviderRouter(
        cfg, user_id=user["id"], model_key="ark_seedance_20",
        credential_source="user",
    )
    with pytest.raises(ProviderRoutingError) as exc:
        router.create_provider("ark_seedance")
    assert exc.value.error_type == "provider_credential_missing"
    assert "API 配置" in str(exc.value)
    assert "未配置 Ark API Key" not in str(exc.value)


def test_ark_submit_does_not_pass_keyframe_urls(app, monkeypatch):
    cfg = _cfg(app)
    user = _ark_user(cfg, "legacykwarg")
    router = ProviderRouter(
        cfg, user_id=user["id"], model_key="ark_seedance_20",
        credential_source="user",
        request_payload={"duration_s": 6, "ratio": "16:9", "resolution": "720p"},
    )
    captured = {}

    class FakeProvider(object):
        def create_generation(self, **kwargs):
            captured.update(kwargs)
            return {"id": "legacy-task-1"}

    monkeypatch.setattr(router, "create_provider", lambda name: FakeProvider())
    provider, created, task_id = router.submit_generation(
        "ark_seedance", {"prompt": "stage", "negative_prompt": ""}, 6
    )
    assert created["id"] == "legacy-task-1"
    assert task_id == "legacy-task-1"
    assert "reference_image_urls" in captured
    assert "keyframe_urls" not in captured
    assert captured["duration_s"] == 6
    assert captured["aspect_ratio"] == "16:9"
    assert captured["resolution"] == "720p"


def test_ark_submit_preserves_provider_error_fields(app, monkeypatch):
    cfg = _cfg(app)
    user = _ark_user(cfg, "legacyerror")
    router = ProviderRouter(
        cfg, user_id=user["id"], model_key="ark_seedance_20",
        credential_source="user",
    )

    class FailingProvider(object):
        def create_generation(self, **kwargs):
            raise ProviderRejected(
                "火山方舟账户未开通模型（请求 ID: req-legacy-1）",
                error_type="model_not_activated",
                status_code=400,
                provider_code="ModelNotOpen",
                request_id="req-legacy-1",
                model_id="doubao-seedance-2-0-260128",
            )

    monkeypatch.setattr(router, "create_provider", lambda name: FailingProvider())
    with pytest.raises(ProviderRoutingError) as exc:
        router.submit_generation("ark_seedance", {"prompt": "stage"}, 6)
    assert exc.value.error_type == "model_not_activated"
    assert exc.value.provider_code == "ModelNotOpen"
    assert exc.value.request_id == "req-legacy-1"


def test_legacy_request_clamps_duration_and_omits_unsupported_audio(app):
    cfg = _cfg(app)
    user = _ark_user(cfg, "legacyclamp")
    router = ProviderRouter(
        cfg, user_id=user["id"], model_key="ark_seedance_10_pro",
        credential_source="user",
        request_payload={
            "duration_s": 1, "resolution": "4k", "ratio": "16:9",
            "generate_audio": True,
        },
    )
    caps = generation_models.get_model(
        cfg, "ark_seedance_10_pro", user=user
    )["capabilities"]
    data = router._build_generation_request(
        "ark_seedance", {"prompt": "stage"}, 1,
        payload=router.request_payload, caps=caps,
    )
    assert data["duration_s"] == 2
    assert data["resolution"] == "720p"
    assert data["generate_audio"] is None


def test_create_job_snapshots_selected_model_and_credential_source(app, monkeypatch):
    cfg = _cfg(app)
    captured = {}

    def fake_start(job_store, job_id, cfg_arg, orchestrator):
        captured["job_id"] = job_id

    monkeypatch.setattr("app.start_job_worker", fake_start)

    client = app.test_client()
    _user, token = support.register_and_login(client, "legacyjob")
    service = CredentialService(cfg.DATA_DIR, cfg)
    user = service.db.fetch_one(
        "SELECT * FROM auth_users WHERE username = ?", ("legacyjob",)
    )
    service.upsert(
        user["id"], user.get("tenant_id"), "ark",
        api_key=ARK_KEY,
        base_url=PUBLIC_BASE_URL,
        model_overrides={"ark_seedance_20": "job-seedance-20-endpoint"},
    )

    response = client.post(
        "/api/jobs",
        json={
            "ai_model": "ark_seedance_20",
            "duration_s": 6,
            "venue_type": "theater",
            "shot_type": "orbit",
            "title": "legacy job",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201, response.get_json()
    job_id = response.get_json()["data"]["id"]
    assert captured["job_id"] == job_id

    job_path = os.path.join(cfg.JOBS_DIR, job_id, "job.json")
    with open(job_path, "r") as handle:
        job = json.load(handle)
    payload = job["payload"]
    assert payload["model_key"] == "ark_seedance_20"
    assert payload["model_id"] == "job-seedance-20-endpoint"
    assert payload["provider"] == "ark_seedance"
    assert payload["credential_source"] == "user"
    assert ARK_KEY not in json.dumps(job, ensure_ascii=False)
    assert os.path.exists(job_path)
