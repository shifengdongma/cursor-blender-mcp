# -*- coding: utf-8 -*-
"""Owner-scoped generation timing and admin aggregates."""
from __future__ import absolute_import

import time

import os

from backend import generation_service, storyboard_service
from backend.creative_project_service import get_creative_project_service
from backend.database import get_database
from backend.generation_worker import GenerationWorker
from backend.models import GenerationTask
from backend.task_service import get_task_service
from tests import support


def _make_task(cfg, user, **overrides):
    task_service = get_task_service(cfg.DATA_DIR)
    now = time.time()
    values = dict(
        creative_project_id=None,
        task_type=GenerationTask.TYPE_VIDEO,
        created_by=user["id"],
        provider="ark_seedance",
        model_id="model-x",
        status=GenerationTask.STATUS_SUCCEEDED,
        created_at=int(now - 20),
        created_at_ms=now - 20,
        claimed_at=int(now - 19),
        claimed_at_ms=now - 19,
        provider_request_started_at=now - 18.9,
        provider_request_finished_at=now - 18.5,
        provider_job_created_at=now - 18.5,
        provider_finished_at=now - 5.0,
        download_started_at=now - 4.9,
        download_finished_at=now - 3.0,
        persist_started_at=now - 2.9,
        persist_finished_at=now - 2.0,
        completed_at=int(now - 2),
        completed_at_ms=now - 2.0,
        params={"prompt": "timing", "duration_s": 5},
    )
    values.update(overrides)
    return task_service.create_task(**values)


def test_timing_endpoint_is_owner_scoped_and_computes_phases(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    owner = support.create_admin(
        cfg.DATA_DIR, username="timing_owner", email="timing_owner@example.com"
    )
    task = _make_task(cfg, owner)
    client = app.test_client()
    support.login_and_token(client, "timing_owner", password="AdminPass12345")

    response = client.get("/api/generation/tasks/{0}/timing".format(task.id))
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["task_id"] == task.id
    assert data["timestamps"]["provider_request_started_at"]
    assert data["durations_ms"]["queue_wait_ms"] == 1000
    assert data["durations_ms"]["download_ms"] == 1900
    assert data["durations_ms"]["persist_ms"] == 900
    assert data["durations_ms"]["total_ms"] >= 17000
    assert any("不等于纯推理" in note for note in data["notes"])

    other = app.test_client()
    support.register_and_login(other, "timing_other")
    forbidden = other.get("/api/generation/tasks/{0}/timing".format(task.id))
    assert forbidden.status_code == 403


def test_public_task_hides_timing_and_snapshot(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    owner = support.create_admin(
        cfg.DATA_DIR, username="timing_hide", email="timing_hide@example.com"
    )
    task = _make_task(
        cfg, owner, timeline_snapshot={"tracks": []}, timing_json={"x": 1}
    )
    client = app.test_client()
    support.login_and_token(client, "timing_hide", password="AdminPass12345")
    response = client.get("/api/generation/tasks/{0}".format(task.id))
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert "timeline_snapshot" not in data
    assert "timing_json" not in data
    assert "provider_request_started_at" not in data


def test_admin_timing_summary(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    admin = support.create_admin(
        cfg.DATA_DIR, username="timing_admin", email="timing_admin@example.com"
    )
    _make_task(cfg, admin)
    _make_task(
        cfg, admin, status=GenerationTask.STATUS_FAILED,
        completed_at_ms=time.time(), error_code="provider_failed",
    )
    client = app.test_client()
    support.login_and_token(client, "timing_admin", password="AdminPass12345")
    response = client.get("/api/generation/timing/summary?task_type=video")
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["count"] >= 2
    assert 0.0 <= data["success_rate"] <= 1.0
    assert data["durations_ms"]["total_ms"]["median"] is not None
    assert data["durations_ms"]["total_ms"]["p95"] is not None


def test_worker_alternates_poll_and_submission(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    worker = GenerationWorker(get_task_service(cfg.DATA_DIR), cfg, name="fair-worker")
    worker._last_action = "poll"
    calls = []

    def submit():
        calls.append("submit")
        return True

    def poll():
        calls.append("poll")
        return True

    worker._submit_once = submit
    worker._poll_once = poll
    assert worker.run_once() is True
    assert calls == ["submit"]
    worker._last_action = "submit"
    calls[:] = []
    assert worker.run_once() is True
    assert calls == ["poll"]


def test_finalize_records_timing_and_video_version(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="timing_finalize", email="timing_finalize@example.com"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="Timing project", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).create_shot(
        project.id, scene_title="镜头", duration_s=2
    )
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_VIDEO,
        created_by=user["id"],
        provider="ark_seedance",
        model_id="model-x",
        params={"prompt": "timing"},
        status=GenerationTask.STATUS_RUNNING,
        target_shot_id=shot.id,
        lease_owner="lease-1",
        provider_job_id="job-1",
    )
    path = os.path.join(
        cfg.DATA_DIR, "assets", "generated", user["id"], task.id, "out.mp4"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64)
    generation_service.finalize_task(
        cfg, task_service, task, "lease-1", [path], "video"
    )
    refreshed = task_service.get_task(task.id)
    assert refreshed.status == GenerationTask.STATUS_SUCCEEDED
    assert refreshed.persist_started_at is not None
    assert refreshed.persist_finished_at is not None
    assert refreshed.completed_at_ms is not None
    assert refreshed.output_asset_id
    version = get_database().fetch_one(
        "SELECT * FROM shot_media_versions WHERE shot_id = ? AND media_kind = 'video'",
        (shot.id,),
    )
    assert version and version["asset_id"] == refreshed.output_asset_id
    assert version["source"] == "generation"
    shot_after = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shot.id)
    assert shot_after.selected_video_asset_id == refreshed.output_asset_id
    assert shot_after.video_selection_source == "original"
