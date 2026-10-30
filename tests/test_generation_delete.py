# -*- coding: utf-8 -*-
"""Delete failed/cancelled generation history records."""
from __future__ import absolute_import

import os
import time

import pytest

from backend import generation_service
from backend.database import get_database
from backend.ops_service import get_ops_service
from backend.task_service import get_task_service
from tests import support


@pytest.fixture
def app_with_generation(tmp_path):
    from tests.support import make_app, reset_globals
    application = make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=100,
        DAILY_VIDEO_LIMIT=100,
        AUDIT_ENABLED=True,
    )
    yield application
    reset_globals()


def _token(client):
    return client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]


def _create_image_task(client, token, prompt="delete-test"):
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": prompt},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    return response.get_json()["data"]["id"]


def _set_status(app, task_id, status, **extra):
    cfg = app.config["AIGV_CONFIG"]
    service = get_task_service(cfg.DATA_DIR)
    fields = {
        "status": status,
        "stage": status,
        "completed_at": int(time.time()),
    }
    fields.update(extra)
    task = service.update_task(task_id, **fields)
    assert task is not None
    return service


def _delete(client, token, task_id):
    return client.delete(
        "/api/generation/tasks/{0}".format(task_id),
        headers=support.auth_headers(token),
    )


def test_delete_failed_task_removes_record_and_directory(app_with_generation):
    client = app_with_generation.test_client()
    user, token = support.register_and_login(client, "deletedfailed")
    task_id = _create_image_task(client, token)
    service = _set_status(
        app_with_generation, task_id, "failed",
        error_code="provider_rejected", error_message="test failure",
    )
    cfg = app_with_generation.config["AIGV_CONFIG"]
    task_dir = os.path.join(
        cfg.DATA_DIR, "assets", "generated", user["id"], task_id
    )
    os.makedirs(task_dir, exist_ok=True)
    with open(os.path.join(task_dir, "partial.bin"), "wb") as handle:
        handle.write(b"partial")

    response = _delete(client, token, task_id)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["deleted"] is True
    assert service.get_task(task_id) is None
    assert not os.path.exists(task_dir)
    assert _delete(client, token, task_id).status_code == 404


def test_delete_rejects_active_and_succeeded_tasks(app_with_generation):
    client = app_with_generation.test_client()
    _user, token = support.register_and_login(client, "deletedactive")
    task_id = _create_image_task(client, token)

    response = _delete(client, token, task_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "task_not_deletable"

    service = _set_status(app_with_generation, task_id, "succeeded")
    response = _delete(client, token, task_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "task_not_deletable"
    assert service.get_task(task_id) is not None


def test_delete_rejects_task_with_output_or_artifact_assets(app_with_generation):
    client = app_with_generation.test_client()
    _user, token = support.register_and_login(client, "deletedassets")
    task_id = _create_image_task(client, token)
    service = _set_status(app_with_generation, task_id, "failed")
    service.update_task(task_id, output_asset_id="dummy-output-asset")
    response = _delete(client, token, task_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "task_has_assets"

    service.update_task(task_id, output_asset_id=None)
    service.add_artifact(
        task_id=task_id,
        creative_project_id=None,
        name="artifact.png",
        artifact_type="image",
        asset_id="dummy-artifact-asset",
    )
    response = _delete(client, token, task_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "task_has_assets"
    assert service.get_task(task_id) is not None


def test_delete_requires_creator_or_admin(app_with_generation):
    client = app_with_generation.test_client()
    _user, token = support.register_and_login(client, "deleteowner")
    task_id = _create_image_task(client, token)
    _set_status(app_with_generation, task_id, "failed")

    other = app_with_generation.test_client()
    support.register_and_login(other, "deleteother")
    other_token = _token(other)
    response = _delete(other, other_token, task_id)
    assert response.status_code == 403, response.get_json()

    cfg = app_with_generation.config["AIGV_CONFIG"]
    support.create_admin(cfg.DATA_DIR, username="deleteadmin")
    admin_client = app_with_generation.test_client()
    _admin, admin_token = support.login_and_token(
        admin_client, "deleteadmin", password="AdminPass12345"
    )
    response = _delete(admin_client, admin_token, task_id)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["deleted"] is True


def test_delete_cancelled_task_is_allowed(app_with_generation):
    client = app_with_generation.test_client()
    _user, token = support.register_and_login(client, "deletecancelled")
    task_id = _create_image_task(client, token)
    _set_status(app_with_generation, task_id, "cancelled")
    response = _delete(client, token, task_id)
    assert response.status_code == 200, response.get_json()


def test_delete_needs_review_is_blocked(app_with_generation):
    client = app_with_generation.test_client()
    _user, token = support.register_and_login(client, "deletereview")
    task_id = _create_image_task(client, token)
    _set_status(app_with_generation, task_id, "needs_review")
    response = _delete(client, token, task_id)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "task_not_deletable"


def test_delete_failed_task_attempts_provider_cancel_and_audits(
    app_with_generation, monkeypatch,
):
    client = app_with_generation.test_client()
    user, token = support.register_and_login(client, "deletecancel")
    task_id = _create_image_task(client, token)
    _set_status(
        app_with_generation, task_id, "failed",
        provider_job_id="provider-job-1",
    )
    calls = {}

    class FakeProvider(object):
        def cancel_generation(self, provider_job_id):
            calls["provider_job_id"] = provider_job_id
            return True

    monkeypatch.setattr(
        generation_service,
        "_provider_for_task",
        lambda cfg, task: FakeProvider(),
    )
    response = _delete(client, token, task_id)
    assert response.status_code == 200, response.get_json()
    assert calls["provider_job_id"] == "provider-job-1"

    cfg = app_with_generation.config["AIGV_CONFIG"]
    events = get_ops_service(cfg.DATA_DIR).list_events(limit=50)
    delete_events = [e for e in events if e.get("event_type") == "generation_delete"]
    assert delete_events
    metadata = delete_events[0].get("metadata") or {}
    details = metadata.get("details") or {}
    assert details.get("had_provider_job") is True
    assert details.get("provider_cancel_succeeded") is True
    assert metadata.get("user_id") == user["id"]


def test_delete_audit_disabled_writes_no_event(tmp_path):
    from tests.support import make_app, reset_globals
    app = make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=100,
        AUDIT_ENABLED=False,
    )
    try:
        client = app.test_client()
        _user, token = support.register_and_login(client, "deleteauditoff")
        task_id = _create_image_task(client, token)
        _set_status(app, task_id, "failed")
        assert _delete(client, token, task_id).status_code == 200
        cfg = app.config["AIGV_CONFIG"]
        events = get_ops_service(cfg.DATA_DIR).list_events(limit=20)
        assert not [e for e in events if e.get("event_type") == "generation_delete"]
    finally:
        reset_globals()
