# -*- coding: utf-8 -*-
"""Regression tests for media-path/pointer injection and FK-safe deletion."""
from __future__ import absolute_import

import os

from backend import storyboard_service
from backend.creative_project_service import get_creative_project_service
from backend.database import get_database
from backend.models import GenerationTask, ShotMediaVersion, TimelineClip, TimelineTrack
from tests import support


def _setup(tmp_path):
    app = support.make_app(tmp_path)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="security_user", email="security@example.com"
    )
    client = app.test_client()
    _user, token = support.login_and_token(
        client, "security_user", password="AdminPass12345"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="安全测试", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).create_shot(
        project.id, scene_title="镜头", dialogue="你好", duration_s=2
    )
    return app, cfg, user, project, shot, client, token


def test_shot_update_rejects_paths_and_pointer_injection(tmp_path):
    app, cfg, user, project, shot, client, token = _setup(tmp_path)
    headers = support.auth_headers(token)
    for payload in (
        {"srt_path": "/etc/hostname"},
        {"video_asset_id": "someone-elses-asset"},
        {"audio_asset_id": "someone-elses-asset"},
        {"selected_video_asset_id": "someone-elses-asset"},
        {"subtitle_asset_id": "someone-elses-asset"},
        {"video_selection_source": "refined"},
    ):
        response = client.put(
            "/api/creative/shots/{0}".format(shot.id),
            json=payload, headers=headers,
        )
        assert response.status_code == 400, payload
        assert response.get_json()["error"] == "invalid_shot_field"


def test_delete_shot_cleans_timeline_versions_and_task_reference(tmp_path):
    app, cfg, user, project, shot, client, token = _setup(tmp_path)
    headers = support.auth_headers(token)
    db = get_database()
    track = TimelineTrack(
        creative_project_id=project.id, name="视频轨",
        track_type="video", role="video", sequence_no=0,
    )
    db.insert("timeline_tracks", track.to_insert_params())
    clip = TimelineClip(
        track_id=track.id, creative_project_id=project.id, shot_id=shot.id,
        asset_id=None, name="片段", start_time=0, duration_s=2,
        trim_in=0, trim_out=2,
    )
    db.insert("timeline_clips", clip.to_insert_params())
    version = ShotMediaVersion(
        creative_project_id=project.id, shot_id=shot.id, media_kind="video",
        asset_id=None, source="legacy", label="旧版本",
    )
    db.insert("shot_media_versions", version.to_insert_params())
    task = GenerationTask(
        creative_project_id=project.id, task_type=GenerationTask.TYPE_VIDEO,
        created_by=user["id"], target_shot_id=shot.id,
    )
    db.insert("generation_tasks", task.to_insert_params())

    response = client.delete(
        "/api/creative/shots/{0}".format(shot.id), headers=headers
    )
    assert response.status_code == 200, response.get_json()
    assert storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shot.id) is None
    assert db.count("timeline_clips", "shot_id = ?", (shot.id,)) == 0
    assert db.count("shot_media_versions", "shot_id = ?", (shot.id,)) == 0
    assert db.fetch_one(
        "SELECT target_shot_id FROM generation_tasks WHERE id = ?", (task.id,)
    )["target_shot_id"] is None


def test_export_does_not_read_arbitrary_srt_path(tmp_path):
    import zipfile
    from backend import task_worker
    from backend.task_service import get_task_service

    app, cfg, user, project, shot, client, token = _setup(tmp_path)
    storyboard_service.get_storyboard_service(cfg.DATA_DIR).update_shot(
        shot.id, srt_path="/etc/hostname"
    )
    task = get_task_service(cfg.DATA_DIR).create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_EXPORT,
        created_by=user["id"],
    )
    claimed = get_task_service(cfg.DATA_DIR).claim_next_task(
        task_types=(GenerationTask.TYPE_EXPORT,)
    )
    task_worker._process_task(
        get_task_service(cfg.DATA_DIR), cfg,
        get_task_service(cfg.DATA_DIR).db, claimed,
    )
    result = get_task_service(cfg.DATA_DIR).get_task(claimed.id)
    assert result.status == GenerationTask.STATUS_SUCCEEDED
    row = get_task_service(cfg.DATA_DIR).db.fetch_one(
        "SELECT file_path FROM export_packages WHERE task_id = ?", (claimed.id,)
    )
    with zipfile.ZipFile(row["file_path"]) as archive:
        srt = archive.read("subtitles/subtitles.srt").decode("utf-8")
    assert "你好" in srt
    with open("/etc/hostname", "r", encoding="utf-8") as handle:
        hostname = handle.read().strip()
    assert hostname and hostname not in srt
