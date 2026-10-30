# -*- coding: utf-8 -*-
"""Workflow derivation, compose API, final-video and task recovery endpoints."""
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


def _make_audio(path):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _setup(tmp_path):
    app = support.make_app(tmp_path, FFMPEG_BIN=FFMPEG, FFPROBE_BIN=FFPROBE)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="workflow_user", email="workflow@example.com"
    )
    client = app.test_client()
    _user, token = support.login_and_token(
        client, "workflow_user", password="AdminPass12345"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="工作流项目", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    for index, color in enumerate(("red", "blue")):
        shot = shot_service.create_shot(
            project.id,
            scene_title="镜头{0}".format(index + 1),
            dialogue="旁白{0}".format(index + 1),
            duration_s=0.6,
        )
        video_path = os.path.join(
            asset_service.assets_dir, "videos", "workflow_{0}.mp4".format(index)
        )
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        _make_video(video_path, color)
        video = asset_service.create_asset(
            name="视频{0}".format(index),
            asset_type="video",
            file_path=os.path.relpath(video_path, asset_service.assets_dir),
            file_size=os.path.getsize(video_path),
            owner_user_id=user["id"],
            tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        shot_service.update_shot(
            shot.id, video_asset_id=video.id, selected_video_asset_id=video.id
        )
        if index == 0:
            audio_path = os.path.join(asset_service.assets_dir, "audio", "workflow.wav")
            _make_audio(audio_path)
            audio = asset_service.create_asset(
                name="旁白",
                asset_type="audio",
                file_path=os.path.relpath(audio_path, asset_service.assets_dir),
                file_size=os.path.getsize(audio_path),
                duration_s=0.5,
                audio_role="narration",
                owner_user_id=user["id"],
                tenant_id=user.get("tenant_id"),
                visibility="private",
            )
            shot_service.update_shot(shot.id, audio_asset_id=audio.id, audio_duration_s=0.5)
    return app, cfg, user, project, client, token


def test_workflow_and_compose_final_video(tmp_path):
    app, cfg, user, project, client, token = _setup(tmp_path)
    headers = support.auth_headers(token)

    workflow = client.get(
        "/api/creative/projects/{0}/workflow".format(project.id)
    )
    assert workflow.status_code == 200, workflow.get_json()
    steps = workflow.get_json()["data"]["steps"]
    assert steps[0]["complete"] is True
    assert steps[2]["complete"] is True
    assert steps[3]["complete"] is False

    timeline = client.get(
        "/api/creative/projects/{0}/timeline?ensure=1".format(project.id)
    )
    assert timeline.status_code == 200, timeline.get_json()
    timeline_data = timeline.get_json()["data"]
    assert timeline_data["initialized"] is True
    assert timeline_data["timeline_version"] == 1

    workflow = client.get(
        "/api/creative/projects/{0}/workflow".format(project.id)
    ).get_json()["data"]
    assert workflow["steps"][3]["complete"] is True
    assert workflow["timeline"]["version"] == 1

    compose = client.post(
        "/api/creative/projects/{0}/compose".format(project.id),
        json={
            "resolution": "720p",
            "fps": 24,
            "subtitle_mode": "none",
            "timeline_version": timeline_data["timeline_version"],
        },
        headers=headers,
    )
    assert compose.status_code == 202, compose.get_json()
    task_id = compose.get_json()["data"]["id"]
    task = get_task_service(cfg.DATA_DIR).claim_next_task(
        task_types=(GenerationTask.TYPE_COMPOSE,)
    )
    assert task is not None and task.id == task_id
    task_worker._process_task(
        get_task_service(cfg.DATA_DIR), cfg,
        get_task_service(cfg.DATA_DIR).db, task,
    )

    final = client.get(
        "/api/creative/projects/{0}/final-video".format(project.id)
    )
    assert final.status_code == 200, final.get_json()
    final_data = final.get_json()["data"]
    assert final_data["asset"]["asset_type"] == "video"
    assert final_data["up_to_date"] is True
    assert final_data["download_url"]

    workflow = client.get(
        "/api/creative/projects/{0}/workflow".format(project.id)
    ).get_json()["data"]
    assert workflow["steps"][5]["complete"] is True
    assert workflow["final_video"]["up_to_date"] is True

    subtitles = client.get(
        "/api/creative/projects/{0}/subtitles".format(project.id)
    )
    assert subtitles.status_code == 200
    srt = subtitles.get_json()["data"]["srt"]
    assert "旁白1" in srt and "旁白2" in srt

    tasks = client.get(
        "/api/creative/projects/{0}/tasks?task_type=compose".format(project.id)
    )
    assert tasks.status_code == 200
    assert tasks.get_json()["data"][0]["id"] == task_id

    # Another user must not see the project's final video.
    client2 = app.test_client()
    support.register_and_login(client2, "workflow_other")
    forbidden = client2.get(
        "/api/creative/projects/{0}/final-video".format(project.id)
    )
    assert forbidden.status_code in (403, 404)

    # Deleting the project must remove version/timeline/task children before
    # their FK parents (foreign_keys=ON).
    deleted = client.delete(
        "/api/creative/projects/{0}".format(project.id), headers=headers
    )
    assert deleted.status_code == 200, deleted.get_json()
    assert get_creative_project_service(cfg.DATA_DIR).get_project(project.id) is None
