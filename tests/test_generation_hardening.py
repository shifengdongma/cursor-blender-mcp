# -*- coding: utf-8 -*-
"""Stage C hardening: capabilities, ComfyUI async, races, finalize, references."""
from __future__ import absolute_import

import base64
import os
import time

import pytest

from backend import generation_models, generation_service
from backend.asset_service import get_asset_service
from backend.database import get_database
from backend.generation_worker import GenerationWorker
from backend.models import GenerationTask
from backend.providers.mock_provider import MockImageProvider, MockVideoProvider
from backend.task_service import get_task_service
from tests import support

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture
def gen_app(tmp_path):
    from tests.support import make_app, reset_globals
    app = make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=100,
        DAILY_VIDEO_LIMIT=100,
    )
    yield app
    reset_globals()


@pytest.fixture
def comfy_app(tmp_path, monkeypatch):
    from tests.support import make_app, reset_globals
    app = make_app(
        tmp_path,
        COMFYUI_ENABLED=True,
        COMFYUI_BASE_URL="http://comfy.test",
        DAILY_IMAGE_LIMIT=100,
    )
    monkeypatch.setattr(
        generation_models, "_comfyui_status", lambda cfg: (True, None)
    )
    yield app
    reset_globals()


def _auth(client, username):
    return support.register_and_login(client, username)


def _post_token(client):
    return client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]


def test_image_dimensions_and_unsupported_parameters(gen_app):
    client = gen_app.test_client()
    _auth(client, "dims")
    token = _post_token(client)

    response = client.post(
        "/api/generation/images",
        json={
            "model_key": "ark_seedream_pro",
            "prompt": "gallery",
            "size": "2K",
            "ratio": "16:9",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    task = get_database().fetch_one(
        "SELECT * FROM generation_tasks WHERE id = ?", (response.get_json()["data"]["id"],)
    )
    import json
    params = json.loads(task["params"])
    assert params["width"] > params["height"]
    assert 921600 <= params["width"] * params["height"] <= 4624220

    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "seed", "seed": 42},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"

    response = client.post(
        "/api/generation/videos",
        json={
            "model_key": "ark_seedance_10_pro",
            "prompt": "audio",
            "generate_audio": True,
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 400
    assert "音频" in response.get_json()["message"]


def test_comfyui_async_submit_and_poll(comfy_app, monkeypatch):
    client = comfy_app.test_client()
    _auth(client, "comfyuser")
    token = _post_token(client)

    class FakeComfy(object):
        def __init__(self):
            self.polls = 0

        def submit_generation(self, **kwargs):
            return "comfy-prompt-1"

        def poll_generation(self, prompt_id):
            self.polls += 1
            if self.polls == 1:
                return {}
            return {
                prompt_id: {
                    "outputs": {
                        "9": {
                            "images": [
                                {"filename": "../../evil.png", "subfolder": "", "type": "output"}
                            ]
                        }
                    }
                }
            }

        def download_results_from_history(self, entry, output_dir, max_bytes=None):
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, "comfy.png")
            with open(path, "wb") as handle:
                handle.write(PNG)
            return [path]

    provider = FakeComfy()
    monkeypatch.setattr(
        generation_service, "_provider_for_task", lambda cfg, task: provider
    )

    response = client.post(
        "/api/generation/images",
        json={"model_key": "comfyui_default", "prompt": "local", "size": "1K"},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["id"]
    cfg = comfy_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    worker = GenerationWorker(task_service, cfg, name="comfy-worker")

    assert worker.run_once() is True
    task = task_service.get_task(task_id)
    assert task.status == "running"
    assert task.provider_job_id == "comfy-prompt-1"
    assert provider.polls == 0  # submission must not block on generation

    task_service.update_task(task_id, next_retry_at=0)
    assert worker.run_once() is True
    assert task_service.get_task(task_id).status == "running"

    task_service.update_task(task_id, next_retry_at=0)
    assert worker.run_once() is True
    task = task_service.get_task(task_id)
    assert task.status == "succeeded"
    assert task.output_asset_id


def test_finalize_lease_loss_rolls_back(gen_app, tmp_path):
    client = gen_app.test_client()
    user, _token = _auth(client, "leaseuser")
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_IMAGE,
        created_by=user["id"],
        provider="ark_seedream",
        model_id="doubao-seedream-5-0-pro-260628",
        params={"prompt": "rollback"},
        status=GenerationTask.STATUS_RUNNING,
        lease_owner="real-owner",
        provider_job_id="job-1",
    )
    path = os.path.join(
        cfg.DATA_DIR, "assets", "generated", user["id"], task.id, "out.png"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(PNG)

    generation_service.finalize_task(
        cfg, task_service, task, "wrong-owner", [path], "image"
    )

    assert not os.path.exists(path)
    assert get_database().count(
        "task_artifacts", "task_id = ?", (task.id,)
    ) == 0
    assert get_database().count(
        "assets", "owner_user_id = ?", (user["id"],)
    ) == 0
    assert task_service.get_task(task.id).status == "running"


def test_expired_queued_task_fails_without_calling_provider(gen_app):
    client = gen_app.test_client()
    user, _token = _auth(client, "timeoutuser")
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_IMAGE,
        created_by=user["id"],
        provider="ark_seedream",
        model_id="doubao-seedream-5-0-pro-260628",
        params={"prompt": "late"},
        status=GenerationTask.STATUS_QUEUED,
    )
    task_service.db.update(
        "generation_tasks",
        {"created_at": int(time.time()) - cfg.GENERATION_IMAGE_DEADLINE_S - 10},
        "id = ?",
        (task.id,),
    )
    worker = GenerationWorker(task_service, cfg, name="timeout-worker")
    assert worker.run_once() is True
    task = task_service.get_task(task.id)
    assert task.status == "failed"
    assert task.error_code == "task_timeout"


def test_cancel_race_does_not_report_false_success(gen_app):
    client = gen_app.test_client()
    user, _token = _auth(client, "cancelrace")
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_VIDEO,
        created_by=user["id"],
        provider="ark_seedance",
        model_id="doubao-seedance-2-5-260628",
        params={"prompt": "race"},
        status=GenerationTask.STATUS_QUEUED,
    )
    # Simulate the worker claiming the task between the UI read and cancel.
    task_service.update_task(task.id, status=GenerationTask.STATUS_SUBMITTING)
    assert task_service.cancel_task(task.id) is True
    fresh = task_service.get_task(task.id)
    assert fresh.status == GenerationTask.STATUS_SUBMITTING
    assert fresh.cancel_requested == 1


def test_idempotency_integrity_error_returns_existing(gen_app, monkeypatch):
    client = gen_app.test_client()
    user, _token = _auth(client, "idemrace")
    token = _post_token(client)
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    existing = task_service.create_task(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_IMAGE,
        created_by=user["id"],
        provider="ark_seedream",
        model_id="doubao-seedream-5-0-pro-260628",
        params={"prompt": "existing"},
        status=GenerationTask.STATUS_QUEUED,
        client_request_id="race-key",
    )
    original = task_service.find_idempotent_task
    calls = {"n": 0}

    def flaky(created_by, client_request_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return original(created_by, client_request_id)

    monkeypatch.setattr(task_service, "find_idempotent_task", flaky)
    response = client.post(
        "/api/generation/images",
        json={
            "model_key": "ark_seedream_pro",
            "prompt": "existing",
            "client_request_id": "race-key",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    assert response.get_json()["data"]["id"] == existing.id


def test_task_responses_hide_internal_fields(gen_app, monkeypatch):
    client = gen_app.test_client()
    _auth(client, "serialize")
    token = _post_token(client)
    monkeypatch.setattr(
        generation_service, "_provider_for_task", lambda cfg, task: MockImageProvider()
    )
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "serialize"},
        headers=support.auth_headers(token),
    )
    task_id = response.get_json()["data"]["id"]
    data = client.get("/api/generation/tasks/{0}".format(task_id)).get_json()["data"]
    for field in (
        "provider_job_id", "lease_owner", "lease_expires_at",
        "submission_started_at", "client_request_id",
    ):
        assert field not in data
    assert data["params"]["prompt"] == "serialize"


def test_active_reference_asset_cannot_be_deleted(gen_app):
    client = gen_app.test_client()
    user, _token = _auth(client, "refowner")
    token = _post_token(client)
    cfg = gen_app.config["AIGV_CONFIG"]
    asset_service = get_asset_service(cfg.DATA_DIR)
    asset = asset_service.create_asset(
        name="reference",
        asset_type="image",
        owner_user_id=user["id"],
        tenant_id=user["tenant_id"],
        metadata={"source": "upload"},
    )
    response = client.post(
        "/api/generation/images",
        json={
            "model_key": "ark_seedream_pro",
            "prompt": "with reference",
            "reference_asset_id": asset.id,
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    response = client.delete(
        "/api/assets/{0}".format(asset.id), headers=support.auth_headers(token)
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "asset_in_use"


def test_generated_asset_can_be_deleted_and_detached(gen_app, monkeypatch):
    client = gen_app.test_client()
    _auth(client, "deletegen")
    token = _post_token(client)
    cfg = gen_app.config["AIGV_CONFIG"]
    monkeypatch.setattr(
        generation_service, "_provider_for_task", lambda cfg, task: MockImageProvider()
    )
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": "delete me"},
        headers=support.auth_headers(token),
    )
    task_id = response.get_json()["data"]["id"]
    worker = GenerationWorker(get_task_service(cfg.DATA_DIR), cfg)
    assert worker.run_once() is True

    detail = client.get("/api/generation/tasks/{0}".format(task_id)).get_json()["data"]
    asset_id = detail["output_asset_id"]
    assert asset_id

    response = client.delete(
        "/api/assets/{0}".format(asset_id), headers=support.auth_headers(token)
    )
    assert response.status_code == 200, response.get_json()
    detail = client.get("/api/generation/tasks/{0}".format(task_id)).get_json()["data"]
    assert detail["output_asset"] is None
    assert detail["artifacts"] == []
    assert detail["result_payload"]["asset_ids"] == []


def test_luma_dreaming_keeps_task_running(gen_app, monkeypatch):
    client = gen_app.test_client()
    user, _token = _auth(client, "luma")
    cfg = gen_app.config["AIGV_CONFIG"]
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_VIDEO,
        created_by=user["id"],
        provider="luma",
        model_id="ray-2",
        params={"prompt": "dream", "ratio": "16:9", "duration_s": 5, "resolution": "720p"},
        status=GenerationTask.STATUS_RUNNING,
        lease_owner="luma-owner",
        provider_job_id="luma-1",
    )

    class FakeLuma(object):
        @staticmethod
        def get_generation(task_id):
            return {"state": "dreaming"}

        @staticmethod
        def extract_status(data):
            return data.get("state", "unknown")

        @staticmethod
        def extract_video_url(data):
            return None

    monkeypatch.setattr(
        generation_service, "_provider_for_task", lambda cfg, task: FakeLuma()
    )
    generation_service.poll_task(cfg, task_service, task, "luma-owner")
    fresh = task_service.get_task(task.id)
    assert fresh.status == "running"
    assert fresh.provider_status == "dreaming"


def test_project_deletion_removes_unreferenced_generated_assets(gen_app):
    client = gen_app.test_client()
    user, _token = _auth(client, "projectclean")
    token = _post_token(client)
    cfg = gen_app.config["AIGV_CONFIG"]
    project = client.post(
        "/api/creative/projects",
        json={"name": "cleanup"},
        headers=support.auth_headers(token),
    ).get_json()["data"]
    task_service = get_task_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    asset = asset_service.create_asset(
        name="generated",
        asset_type="image",
        owner_user_id=user["id"],
        tenant_id=user["tenant_id"],
        metadata={"source": "generation"},
    )
    task = task_service.create_task(
        creative_project_id=project["id"],
        task_type=GenerationTask.TYPE_IMAGE,
        created_by=user["id"],
        provider="ark_seedream",
        model_id="doubao-seedream-5-0-pro-260628",
        params={"prompt": "generated"},
        status=GenerationTask.STATUS_SUCCEEDED,
        output_asset_id=asset.id,
    )
    task_service.add_artifact(
        task_id=task.id,
        creative_project_id=project["id"],
        name="generated.png",
        artifact_type="image",
        asset_id=asset.id,
    )
    response = client.delete(
        "/api/creative/projects/{0}".format(project["id"]),
        headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    assert asset_service.get_asset(asset.id) is None
