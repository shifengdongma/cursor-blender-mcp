# -*- coding: utf-8 -*-
"""Workbench quick-generation contract: prompt flag and real task persistence."""
from __future__ import absolute_import

import os

from backend import generation_service
from backend.providers.mock_provider import MockVideoProvider
from backend.task_service import get_task_service
from tests import support


def _token(client):
    return client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]


def test_prompt_preview_can_omit_engine_context(app):
    client = app.test_client()
    support.register_and_login(client, "workbenchprompt")
    token = _token(client)
    base = {
        "venue_type": "theater",
        "shot_type": "orbit",
        "ai_model": "ark_seedance_25",
        "duration_s": 4,
        "asset_id": "text_only",
        "workflow_mode": "text_to_video",
    }
    with_context = client.post(
        "/api/prompt/preview",
        json=dict(base),
        headers=support.auth_headers(token),
    )
    assert with_context.status_code == 200, with_context.get_json()
    prompt_with = with_context.get_json()["data"]["prompt_bundle"]["prompt"]
    assert "engine target" in prompt_with
    assert "render mode" in prompt_with

    without_context = client.post(
        "/api/prompt/preview",
        json=dict(base, include_engine_context=False),
        headers=support.auth_headers(token),
    )
    assert without_context.status_code == 200, without_context.get_json()
    prompt_without = without_context.get_json()["data"]["prompt_bundle"]["prompt"]
    assert "engine target" not in prompt_without
    assert "render mode" not in prompt_without


def test_workbench_video_payload_persists_asset(tmp_path, monkeypatch):
    app = support.make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_VIDEO_LIMIT=100,
    )
    client = app.test_client()
    user, token = support.register_and_login(client, "workbenchvideo")
    provider = MockVideoProvider()
    monkeypatch.setattr(
        generation_service, "_provider_for_task", lambda cfg, task: provider
    )

    def fake_download(cfg, url, dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, "workbench.mp4")
        with open(path, "wb") as handle:
            handle.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
        return path

    monkeypatch.setattr(generation_service, "_download_video", fake_download)

    response = client.post(
        "/api/generation/videos",
        json={
            "model_key": "ark_seedance_20",
            "prompt": "slow camera move through a theater",
            "ratio": "16:9",
            "duration_s": 4,
            "resolution": "480p",
            "generate_audio": False,
            "client_request_id": "workbench-contract-1",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["id"]

    cfg = app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    from backend.generation_worker import GenerationWorker
    worker = GenerationWorker(task_service, cfg)
    assert worker.run_once() is True
    task_service.update_task(
        task_id, next_retry_at=0, lease_owner=None, lease_expires_at=None
    )
    worker_two = GenerationWorker(task_service, cfg, name="worker-two")
    assert worker_two.run_once() is True

    task = task_service.get_task(task_id)
    assert task.status == "succeeded"
    assert task.output_asset_id
    assert task.created_by == user["id"]

    detail = client.get("/api/generation/tasks/{0}".format(task_id))
    assert detail.status_code == 200, detail.get_json()
    data = detail.get_json()["data"]
    assert data["output_asset"]
    assert data["output_asset"]["id"] == task.output_asset_id
    assert data["status"] == "succeeded"

    file_response = client.get(
        "/api/assets/{0}/file".format(task.output_asset_id)
    )
    assert file_response.status_code == 200
    assert file_response.data[:4] == b"\x00\x00\x00\x18"
