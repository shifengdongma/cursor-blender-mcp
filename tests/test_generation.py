# -*- coding: utf-8 -*-
"""Stage C: generation API, resumable worker and mock providers."""
from __future__ import absolute_import

import os
import time

import pytest

from backend import generation_service
from backend.asset_service import get_asset_service
from backend.generation_worker import GenerationWorker
from backend.providers.mock_provider import MockImageProvider, MockVideoProvider
from backend.task_service import get_task_service
from tests import support


@pytest.fixture
def gen_app(tmp_path):
    from tests.support import make_app, reset_globals
    app = make_app(tmp_path, ARK_API_KEY="test-ark-key", DAILY_IMAGE_LIMIT=100, DAILY_VIDEO_LIMIT=100)
    yield app
    reset_globals()


def _auth(client, username):
    return support.register_and_login(client, username)


def test_models_list_only_configured_and_image_task(gen_app, monkeypatch):
    client = gen_app.test_client()
    support.register_and_login(client, "genimg")
    models = client.get("/api/generation/models?task_type=image").get_json()["data"]["items"]
    keys = {m["key"] for m in models}
    assert "ark_seedream_pro" in keys
    # Unconfigured models are returned with an explanation instead of hidden.
    comfy = next(m for m in models if m["key"] == "comfyui_default")
    assert comfy["available"] is False
    assert comfy["unavailable_reason"]
    assert all(m["available"] for m in models if m["key"].startswith("ark_"))

    available_only = client.get(
        "/api/generation/models?task_type=image&available_only=1"
    ).get_json()["data"]["items"]
    assert "comfyui_default" not in {m["key"] for m in available_only}

    provider = MockImageProvider()
    monkeypatch.setattr(generation_service, "_provider_for_task", lambda cfg, task: provider)
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "a quiet gallery", "size": "2K"},
        headers=support.auth_headers(client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]),
    )
    assert response.status_code == 202, response.get_json()
    task = response.get_json()["data"]
    assert task["status"] == "queued"
    assert task["task_type"] == "image"

    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    worker = GenerationWorker(task_service, cfg)
    assert worker.run_once() is True
    task = task_service.get_task(task["id"])
    assert task.status == "succeeded"
    assert task.output_asset_id
    asset = get_asset_service(cfg.DATA_DIR).get_asset(task.output_asset_id)
    assert asset is not None
    path = get_asset_service(cfg.DATA_DIR).get_file_path_for_asset(asset)
    assert path and os.path.isfile(path)
    assert client.get("/api/assets/{0}/file".format(asset.id)).status_code == 200


def test_video_submission_poll_and_worker_restart(gen_app, monkeypatch, tmp_path):
    client = gen_app.test_client()
    support.register_and_login(client, "genvid")
    token = client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    provider = MockVideoProvider()
    monkeypatch.setattr(generation_service, "_provider_for_task", lambda cfg, task: provider)

    def fake_download(cfg, url, dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, "mock.mp4")
        with open(path, "wb") as handle:
            handle.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
        return path

    monkeypatch.setattr(generation_service, "_download_video", fake_download)

    response = client.post(
        "/api/generation/videos",
        json={
            "model_key": "ark_seedance_25",
            "prompt": "slow camera move",
            "ratio": "16:9",
            "duration_s": 5,
            "resolution": "720p",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["id"]
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)

    worker = GenerationWorker(task_service, cfg, name="worker-one")
    assert worker.run_once() is True
    task = task_service.get_task(task_id)
    assert task.status == "running"
    assert task.provider_job_id == "mock-video-task-1"

    # Simulate a worker restart before polling.
    task_service.update_task(task_id, next_retry_at=0, lease_owner=None, lease_expires_at=None)
    worker_two = GenerationWorker(task_service, cfg, name="worker-two")
    assert worker_two.run_once() is True
    task = task_service.get_task(task_id)
    assert task.status == "succeeded"
    assert task.output_asset_id
    assert provider.create_calls == 1
    assert provider.poll_calls == 1


def test_uncertain_submission_needs_review_and_is_not_resubmitted(gen_app, monkeypatch):
    client = gen_app.test_client()
    support.register_and_login(client, "genuncertain")
    token = client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    provider = MockImageProvider(fail_uncertain=True)
    monkeypatch.setattr(generation_service, "_provider_for_task", lambda cfg, task: provider)

    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "uncertain"},
        headers=support.auth_headers(token),
    )
    task_id = response.get_json()["data"]["id"]
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    worker = GenerationWorker(task_service, cfg)
    assert worker.run_once() is True
    task = task_service.get_task(task_id)
    assert task.status == "needs_review"
    assert provider.calls == 1
    assert worker.run_once() is False
    assert provider.calls == 1


def test_idempotency_and_ownership(gen_app, monkeypatch):
    client_a = gen_app.test_client()
    support.register_and_login(client_a, "idema")
    token = client_a.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    payload = {
        "model_key": "ark_seedream_pro",
        "prompt": "same request",
        "client_request_id": "idem-1",
    }
    first = client_a.post("/api/generation/images", json=payload, headers=support.auth_headers(token))
    second = client_a.post("/api/generation/images", json=payload, headers=support.auth_headers(token))
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.get_json()["data"]["id"] == second.get_json()["data"]["id"]

    other = gen_app.test_client()
    support.register_and_login(other, "idemb")
    task_id = first.get_json()["data"]["id"]
    assert other.get("/api/generation/tasks/{0}".format(task_id)).status_code == 403
    assert other.post(
        "/api/generation/tasks/{0}/cancel".format(task_id),
        headers=support.auth_headers(other.get("/api/auth/csrf").get_json()["data"]["csrf_token"]),
    ).status_code == 403


def test_cancel_queued_image_task(gen_app):
    client = gen_app.test_client()
    support.register_and_login(client, "canceler")
    token = client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "cancel me"},
        headers=support.auth_headers(token),
    )
    task_id = response.get_json()["data"]["id"]
    response = client.post(
        "/api/generation/tasks/{0}/cancel".format(task_id),
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "cancelled"
    cfg = gen_app.config["AIGV_CONFIG"]
    worker = GenerationWorker(get_task_service(cfg.DATA_DIR), cfg)
    assert worker.run_once() is False
