# -*- coding: utf-8 -*-
"""Shot-scoped refinement, version history and original/refined selection."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

from backend import storyboard_service, task_worker
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.models import GenerationTask
from backend.task_service import get_task_service
from backend.timeline_service import get_timeline_service
from tests import support

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg required")


def _make_video(path, color):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c={0}:s=320x180:r=24:d=0.6".format(color),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


def _setup(tmp_path):
    app = support.make_app(tmp_path, FFMPEG_BIN=FFMPEG, FFPROBE_BIN=FFPROBE)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="refine_user", email="refine@example.com"
    )
    client = app.test_client()
    _user, token = support.login_and_token(
        client, "refine_user", password="AdminPass12345"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="精修项目", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    assets = []
    shots = []
    for index, color in enumerate(("red", "blue")):
        shot = shot_service.create_shot(
            project.id, scene_title="镜头{0}".format(index + 1),
            dialogue="旁白{0}".format(index + 1), duration_s=0.6,
        )
        path = os.path.join(
            asset_service.assets_dir, "videos", "refine_{0}.mp4".format(index)
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _make_video(path, color)
        asset = asset_service.create_asset(
            name="视频{0}".format(index),
            asset_type="video",
            file_path=os.path.relpath(path, asset_service.assets_dir),
            file_size=os.path.getsize(path),
            owner_user_id=user["id"],
            tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        shot_service.update_shot(
            shot.id, video_asset_id=asset.id, selected_video_asset_id=asset.id
        )
        assets.append(asset)
        shots.append(shot_service.get_shot(shot.id))
    return app, cfg, user, project, shots, assets, client, token


def test_refine_creates_version_and_selection_updates_timeline(tmp_path):
    app, cfg, user, project, shots, assets, client, token = _setup(tmp_path)
    headers = support.auth_headers(token)
    timeline = get_timeline_service(cfg).get_timeline(project.id, ensure=True, user=user)
    assert timeline["timeline_version"] == 1

    response = client.post(
        "/api/creative/projects/{0}/refine".format(project.id),
        json={
            "shot_id": shots[0].id,
            "input_asset_id": assets[0].id,
            "filters": {"brightness": 0.1, "saturation": 1.2, "hue": 10},
            "client_request_id": "refine-1",
        },
        headers=headers,
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["id"]
    task = get_task_service(cfg.DATA_DIR).claim_next_task(
        task_types=(GenerationTask.TYPE_REFINE,)
    )
    assert task and task.id == task_id
    task_worker._process_task(get_task_service(cfg.DATA_DIR), cfg, get_task_service(cfg.DATA_DIR).db, task)

    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shots[0].id)
    assert shot.refined_video_asset_id
    assert shot.video_asset_id == assets[0].id  # original preserved
    refined = get_asset_service(cfg.DATA_DIR).get_asset(shot.refined_video_asset_id)
    assert refined.asset_type == "video"
    assert refined.metadata["filters"]["hue"] == 10
    versions = get_task_service(cfg.DATA_DIR).db.fetch_all(
        "SELECT * FROM shot_media_versions WHERE shot_id = ? AND media_kind = 'video'",
        (shots[0].id,),
    )
    assert len(versions) == 1
    assert versions[0]["source"] == "refine"
    assert versions[0]["is_selected"] == 0

    listing = client.get("/api/creative/shots/{0}/videos".format(shots[0].id))
    assert listing.status_code == 200, listing.get_json()
    items = listing.get_json()["data"]["items"]
    assert len(items) == 2
    assert any(item["is_refined"] for item in items)

    selected = client.post(
        "/api/creative/shots/{0}/video-selection".format(shots[0].id),
        json={"asset_id": refined.id},
        headers=headers,
    )
    assert selected.status_code == 200, selected.get_json()
    result = selected.get_json()["data"]
    assert result["selection_source"] == "refined"
    assert result["timeline_updated"] is True
    assert result["timeline_version"] == 2
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shots[0].id)
    assert shot.selected_video_asset_id == refined.id
    clip = get_task_service(cfg.DATA_DIR).db.fetch_one(
        "SELECT * FROM timeline_clips WHERE shot_id = ?", (shots[0].id,)
    )
    assert clip["asset_id"] == refined.id

    restored = client.post(
        "/api/creative/shots/{0}/video-selection".format(shots[0].id),
        json={"asset_id": assets[0].id},
        headers=headers,
    )
    assert restored.status_code == 200, restored.get_json()
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shots[0].id)
    assert shot.selected_video_asset_id == assets[0].id
    assert shot.video_selection_source == "original"


def test_refine_rejects_other_shot_video_and_unknown_filter(tmp_path):
    app, cfg, user, project, shots, assets, client, token = _setup(tmp_path)
    headers = support.auth_headers(token)
    bad_input = client.post(
        "/api/creative/projects/{0}/refine".format(project.id),
        json={
            "shot_id": shots[0].id,
            "input_asset_id": assets[1].id,
            "filters": {"brightness": 0.1},
        },
        headers=headers,
    )
    assert bad_input.status_code == 400
    assert bad_input.get_json()["error"] == "asset_not_linked_to_shot"

    bad_filter = client.post(
        "/api/creative/projects/{0}/refine".format(project.id),
        json={
            "shot_id": shots[0].id,
            "input_asset_id": assets[0].id,
            "filters": {"shell": "rm -rf /"},
        },
        headers=headers,
    )
    assert bad_filter.status_code == 400
    assert bad_filter.get_json()["error"] == "unsupported_filter"
