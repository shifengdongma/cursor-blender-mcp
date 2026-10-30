# -*- coding: utf-8 -*-
"""Task-scoped ZIP export with final MP4, media, subtitles and manifest."""
from __future__ import absolute_import

import io
import json
import os
import shutil
import subprocess
import zipfile

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


def _video(path, color):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c={0}:s=320x180:r=24:d=0.6".format(color),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


def _audio(path, frequency, duration):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency={0}:duration={1}".format(frequency, duration),
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _setup(tmp_path):
    app = support.make_app(tmp_path, FFMPEG_BIN=FFMPEG, FFPROBE_BIN=FFPROBE)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="export_user", email="export@example.com"
    )
    client = app.test_client()
    _user, token = support.login_and_token(
        client, "export_user", password="AdminPass12345"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="导出项目", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    for index, color in enumerate(("red", "blue")):
        shot = shot_service.create_shot(
            project.id, scene_title="镜头{0}".format(index + 1),
            dialogue="字幕旁白{0}".format(index + 1), duration_s=0.6,
        )
        video_path = os.path.join(
            asset_service.assets_dir, "videos", "export_{0}.mp4".format(index)
        )
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        _video(video_path, color)
        video = asset_service.create_asset(
            name="视频{0}".format(index), asset_type="video",
            file_path=os.path.relpath(video_path, asset_service.assets_dir),
            file_size=os.path.getsize(video_path),
            owner_user_id=user["id"], tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        shot_service.update_shot(
            shot.id, video_asset_id=video.id, selected_video_asset_id=video.id
        )
        audio_path = os.path.join(
            asset_service.assets_dir, "audio", "export_narration_{0}.wav".format(index)
        )
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        _audio(audio_path, 440, 0.5)
        audio = asset_service.create_asset(
            name="旁白{0}".format(index), asset_type="audio",
            file_path=os.path.relpath(audio_path, asset_service.assets_dir),
            file_size=os.path.getsize(audio_path), duration_s=0.5,
            audio_role="narration",
            owner_user_id=user["id"], tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        shot_service.update_shot(
            shot.id, audio_asset_id=audio.id, audio_duration_s=0.5
        )
    music_path = os.path.join(asset_service.assets_dir, "audio", "export_music.wav")
    _audio(music_path, 220, 0.5)
    music = asset_service.create_asset(
        name="背景音乐", asset_type="audio",
        file_path=os.path.relpath(music_path, asset_service.assets_dir),
        file_size=os.path.getsize(music_path), duration_s=0.5,
        audio_role="music",
        owner_user_id=user["id"], tenant_id=user.get("tenant_id"),
        visibility="private",
    )
    return app, cfg, user, project, music, client, token


def test_export_zip_contains_final_media_and_manifest(tmp_path):
    app, cfg, user, project, music, client, token = _setup(tmp_path)
    timeline_service = get_timeline_service(cfg)
    timeline = timeline_service.get_timeline(project.id, ensure=True, user=user)
    music_track = next(t for t in timeline["tracks"] if t["track"]["role"] == "music")
    music_track["clips"] = [{
        "shot_id": None, "asset_id": music.id, "name": "背景音乐",
        "start_time": 0.0, "duration_s": 1.2, "trim_in": 0.0, "trim_out": 0.5,
        "volume": 0.3, "muted": False, "source_audio_enabled": True,
        "fade_in": 0.1, "fade_out": 0.1, "subtitle_text": None,
        "properties": {"loop": True},
    }]
    timeline = timeline_service.save_timeline(
        project.id,
        {"timeline_version": timeline["timeline_version"], "tracks": timeline["tracks"]},
        user=user,
    )

    compose_settings = {
        "width": 1280, "height": 720, "fps": 24, "crf": 28,
        "audio_bitrate": "128k", "subtitle_mode": "none",
        "keep_source_audio": False, "loudness_normalize": False,
    }
    compose_task = get_task_service(cfg.DATA_DIR).create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_COMPOSE,
        params={"export_settings": compose_settings},
        timeline_version=timeline["timeline_version"],
        timeline_snapshot=timeline,
        created_by=user["id"],
    )
    claimed = get_task_service(cfg.DATA_DIR).claim_next_task(
        task_types=(GenerationTask.TYPE_COMPOSE,)
    )
    task_worker._process_task(
        get_task_service(cfg.DATA_DIR), cfg, get_task_service(cfg.DATA_DIR).db, claimed
    )
    final_project = get_creative_project_service(cfg.DATA_DIR).get_project(project.id)
    assert final_project.final_video_asset_id

    headers = support.auth_headers(token)
    response = client.post(
        "/api/creative/projects/{0}/exports".format(project.id),
        json={}, headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    export_task_id = response.get_json()["data"]["id"]
    export_task = get_task_service(cfg.DATA_DIR).claim_next_task(
        task_types=(GenerationTask.TYPE_EXPORT,)
    )
    assert export_task and export_task.id == export_task_id
    task_worker._process_task(
        get_task_service(cfg.DATA_DIR), cfg, get_task_service(cfg.DATA_DIR).db,
        export_task,
    )

    zip_path = os.path.join(
        cfg.DATA_DIR, "exports", export_task_id, "project_package.zip"
    )
    assert os.path.isfile(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert "final/final_video.mp4" in names
        assert any(name.startswith("videos/shot_001_video") for name in names)
        assert any(name.startswith("audio/narration/shot_001_narration") for name in names)
        assert any(name.startswith("audio/music/") for name in names)
        assert "subtitles/subtitles.srt" in names
        assert "manifest.json" in names
        assert "project.json" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["final_video"]["asset_id"]
        assert manifest["timeline_version"] == timeline["timeline_version"]
        assert all(not str(value).startswith("/") for value in
                   [manifest["final_video"]["arcname"]])
        project_json = json.loads(archive.read("project.json").decode("utf-8"))
        assert project_json["name"] == "导出项目"

    download = client.get(
        "/api/creative/tasks/{0}/export/download".format(export_task_id)
    )
    assert download.status_code == 200
    assert download.data[:2] == b"PK"

    other = app.test_client()
    support.register_and_login(other, "export_other")
    forbidden = other.get(
        "/api/creative/tasks/{0}/export/download".format(export_task_id)
    )
    assert forbidden.status_code in (403, 404)
