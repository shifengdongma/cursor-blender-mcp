# -*- coding: utf-8 -*-
"""End-to-end backend compose: timeline snapshot -> verified MP4 asset."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

from backend import storyboard_service, task_worker
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.database import get_database
from backend.media_service import probe_media_file
from backend.models import GenerationTask
from backend.task_service import get_task_service
from backend.timeline_service import get_timeline_service
from tests import support

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg required")


def _make_video(path, color, duration=1.0):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "color=c={0}:s=640x360:r=24:d={1}".format(color, duration),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


def _make_audio(path, frequency, duration):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "sine=frequency={0}:duration={1}".format(frequency, duration),
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _setup(tmp_path):
    app = support.make_app(tmp_path, FFMPEG_BIN=FFMPEG, FFPROBE_BIN=FFPROBE)
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username="compose_e2e", email="compose_e2e@example.com"
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="成片项目", tenant_id=user.get("tenant_id"), user_id=user["id"]
    )
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    shots = []
    for index, color in enumerate(("red", "green")):
        shot = shot_service.create_shot(
            project.id,
            scene_title="镜头{0}".format(index + 1),
            dialogue="旁白{0}".format(index + 1),
            duration_s=1.0,
        )
        video_path = os.path.join(
            asset_service.assets_dir, "videos", "compose_{0}.mp4".format(index)
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
        audio_path = os.path.join(
            asset_service.assets_dir, "audio", "narration_{0}.wav".format(index)
        )
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        _make_audio(audio_path, 440, 0.8)
        audio = asset_service.create_asset(
            name="旁白{0}".format(index),
            asset_type="audio",
            file_path=os.path.relpath(audio_path, asset_service.assets_dir),
            file_size=os.path.getsize(audio_path),
            duration_s=0.8,
            audio_role="narration",
            owner_user_id=user["id"],
            tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        shot_service.update_shot(
            shot.id, audio_asset_id=audio.id, audio_duration_s=0.8
        )
        shots.append(shot_service.get_shot(shot.id))

    music_path = os.path.join(asset_service.assets_dir, "audio", "music.wav")
    _make_audio(music_path, 220, 0.5)
    music = asset_service.create_asset(
        name="背景音乐",
        asset_type="audio",
        file_path=os.path.relpath(music_path, asset_service.assets_dir),
        file_size=os.path.getsize(music_path),
        duration_s=0.5,
        audio_role="music",
        owner_user_id=user["id"],
        tenant_id=user.get("tenant_id"),
        visibility="private",
    )
    return app, cfg, user, project, shots, music


def test_compose_worker_writes_final_video_and_mixes_tracks(tmp_path):
    app, cfg, user, project, shots, music = _setup(tmp_path)
    timeline_service = get_timeline_service(cfg)
    timeline = timeline_service.get_timeline(project.id, ensure=True, user=user)
    assert timeline["timeline_version"] == 1
    tracks = timeline["tracks"]
    music_track = next(t for t in tracks if t["track"]["role"] == "music")
    music_track["clips"] = [{
        "shot_id": None,
        "asset_id": music.id,
        "name": "背景音乐",
        "start_time": 0.0,
        "duration_s": 2.0,
        "trim_in": 0.0,
        "trim_out": 0.5,
        "volume": 0.3,
        "muted": False,
        "source_audio_enabled": True,
        "fade_in": 0.1,
        "fade_out": 0.1,
        "subtitle_text": None,
        "properties": {"loop": True},
    }]
    saved = timeline_service.save_timeline(
        project.id,
        {"timeline_version": timeline["timeline_version"], "tracks": tracks},
        user=user,
    )
    settings = {
        "width": 1280,
        "height": 720,
        "fps": 24,
        "crf": 28,
        "audio_bitrate": "128k",
        "subtitle_mode": "burn",
        "subtitle_font_name": "Noto Sans CJK SC",
        "subtitle_font_size": 18,
        "keep_source_audio": False,
        "music_ducking": False,
        "loudness_normalize": False,
        "timeout_s": 300,
    }
    task = get_task_service(cfg.DATA_DIR).create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_COMPOSE,
        params={"export_settings": settings},
        timeline_version=saved["timeline_version"],
        timeline_snapshot=saved,
        created_by=user["id"],
    )

    result = task_worker._execute_compose(task, cfg, get_database())

    assert result["video_asset_id"]
    assert result["subtitle_asset_id"]
    asset_service = get_asset_service(cfg.DATA_DIR)
    video_asset = asset_service.get_asset(result["video_asset_id"])
    assert video_asset.asset_type == "video"
    assert video_asset.duration_s == pytest.approx(2.0, abs=0.3)
    video_path = asset_service.get_file_path_for_asset(video_asset)
    info = probe_media_file(FFPROBE, video_path)
    assert info["has_video"] and info["has_audio"]
    assert info["video"]["width"] == 1280
    assert info["video"]["height"] == 720
    subtitle_asset = asset_service.get_asset(result["subtitle_asset_id"])
    assert subtitle_asset.asset_type == "subtitle"
    subtitle_path = asset_service.get_file_path_for_asset(subtitle_asset)
    with open(subtitle_path, "r", encoding="utf-8") as handle:
        srt = handle.read()
    assert "旁白1" in srt and "旁白2" in srt

    project_after = get_creative_project_service(cfg.DATA_DIR).get_project(project.id)
    assert project_after.final_video_asset_id == video_asset.id
    assert project_after.final_compose_task_id == task.id
    assert project_after.final_timeline_version == saved["timeline_version"]
    export_row = get_database().fetch_one(
        "SELECT * FROM export_packages WHERE task_id = ? AND format = 'mp4'",
        (task.id,),
    )
    assert export_row and export_row["asset_id"] == video_asset.id
    task_after = get_task_service(cfg.DATA_DIR).get_task(task.id)
    assert task_after.output_asset_id == video_asset.id
    assert task_after.result_payload["subtitle_asset_id"] == subtitle_asset.id
