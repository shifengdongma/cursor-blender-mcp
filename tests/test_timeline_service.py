# -*- coding: utf-8 -*-
"""Transactional, ownership-aware timeline initialization and saving."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

from backend import storyboard_service
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.http_utils import ApiError
from backend.timeline_service import get_timeline_service
from tests import support

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg required")


def _make_video(path, color="red", duration=1.0):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "color=c={0}:s=320x180:r=24:d={1}".format(color, duration),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


def _make_audio(path, duration=0.8):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=440:duration={0}".format(duration),
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _setup(tmp_path, username="timeline", shot_count=3, admin=True):
    app = support.make_app(
        tmp_path,
        FFMPEG_BIN=FFMPEG,
        FFPROBE_BIN=FFPROBE,
    )
    cfg = app.config["AIGV_CONFIG"]
    if admin:
        user = support.create_admin(
            cfg.DATA_DIR, username=username, email="{0}@example.com".format(username)
        )
    else:
        from backend.auth_service import AuthService
        user = AuthService(cfg.DATA_DIR).create_user(
            username=username,
            password="Password12345",
            email="{0}@example.com".format(username),
            nickname=username,
            role="user",
        )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="Timeline project",
        tenant_id=user.get("tenant_id"),
        user_id=user["id"],
    )
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    asset_service = get_asset_service(cfg.DATA_DIR)
    shots = []
    for index in range(shot_count):
        shot = shot_service.create_shot(
            project.id,
            scene_title="镜头{0}".format(index + 1),
            dialogue="旁白{0}".format(index + 1),
            duration_s=1.0,
        )
        video_path = os.path.join(
            asset_service.assets_dir, "videos", "{0}_shot{1}.mp4".format(username, index)
        )
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        _make_video(video_path, color=["red", "green", "blue"][index % 3])
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
            shot.id,
            video_asset_id=video.id,
            selected_video_asset_id=video.id,
        )
        if index < 2:
            audio_path = os.path.join(
                asset_service.assets_dir, "audio", "{0}_shot{1}.wav".format(username, index)
            )
            _make_audio(audio_path)
            audio = asset_service.create_asset(
                name="配音{0}".format(index),
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
    return app, cfg, user, project, shots, asset_service


def test_auto_init_uses_real_durations_and_is_idempotent(tmp_path):
    app, cfg, user, project, shots, _assets = _setup(tmp_path)
    service = get_timeline_service(cfg)
    result = service.get_timeline(project.id, ensure=True, user=user)
    assert result["initialized"] is True
    assert result["timeline_version"] == 1
    video_track = next(t for t in result["tracks"] if t["track"]["role"] == "video")
    assert len(video_track["clips"]) == 3
    assert result["duration_s"] == pytest.approx(3.0, abs=0.2)
    starts = [clip["start_time"] for clip in video_track["clips"]]
    assert starts == pytest.approx([0.0, 1.0, 2.0], abs=0.2)
    assert all(clip["duration_s"] > 0.5 for clip in video_track["clips"])
    narration = next(t for t in result["tracks"] if t["track"]["role"] == "narration")
    assert len(narration["clips"]) == 2
    subtitles = next(t for t in result["tracks"] if t["track"]["role"] == "subtitle")
    assert len(subtitles["clips"]) == 3
    assert subtitles["clips"][0]["subtitle_text"] == "旁白1"

    again = service.get_timeline(project.id, ensure=True, user=user)
    assert again["initialized"] is False
    assert again["timeline_version"] == 1
    assert len(again["tracks"]) == len(result["tracks"])


def test_save_timeline_validates_version_and_persists_fields(tmp_path):
    app, cfg, user, project, shots, _assets = _setup(tmp_path)
    service = get_timeline_service(cfg)
    initial = service.get_timeline(project.id, ensure=True, user=user)
    video_track = next(t for t in initial["tracks"] if t["track"]["role"] == "video")
    payload = {
        "timeline_version": initial["timeline_version"],
        "tracks": [{
            "name": video_track["track"]["name"],
            "track_type": "video",
            "role": "video",
            "sequence_no": 0,
            "clips": [{
                "shot_id": video_track["clips"][0]["shot_id"],
                "asset_id": video_track["clips"][0]["asset_id"],
                "name": "主镜头",
                "start_time": 0.0,
                "duration_s": 0.9,
                "trim_in": 0.05,
                "trim_out": 0.95,
                "volume": 0.5,
                "muted": True,
                "source_audio_enabled": False,
                "fade_in": 0.1,
                "fade_out": 0.1,
            }],
        }],
    }
    saved = service.save_timeline(project.id, payload, user=user)
    assert saved["timeline_version"] == initial["timeline_version"] + 1
    clip = saved["tracks"][0]["clips"][0]
    assert clip["volume"] == 0.5
    assert clip["muted"] is True
    assert clip["trim_in"] == pytest.approx(0.05)

    with pytest.raises(ApiError) as excinfo:
        service.save_timeline(project.id, payload, user=user)
    assert excinfo.value.code == "timeline_conflict"


def test_save_rejects_other_users_asset_and_bad_shot(tmp_path):
    app, cfg, user, project, shots, _assets = _setup(tmp_path, admin=False)
    service = get_timeline_service(cfg)
    initial = service.get_timeline(project.id, ensure=True, user=user)
    video_track = next(t for t in initial["tracks"] if t["track"]["role"] == "video")
    other = support.create_admin(
        cfg.DATA_DIR, username="other", email="other@example.com"
    )
    other_asset = get_asset_service(cfg.DATA_DIR).create_asset(
        name="other video",
        asset_type="video",
        file_path=video_track["clips"][0]["asset_id"] + ".mp4",
        owner_user_id=other["id"],
        visibility="private",
    )
    payload = {
        "timeline_version": initial["timeline_version"],
        "tracks": [{
            "track_type": "video", "role": "video", "sequence_no": 0,
            "clips": [{
                "shot_id": shots[0].id,
                "asset_id": other_asset.id,
                "start_time": 0, "duration_s": 1.0,
            }],
        }],
    }
    with pytest.raises(ApiError) as excinfo:
        service.save_timeline(project.id, payload, user=user)
    assert excinfo.value.status_code == 403

    payload["tracks"][0]["clips"][0]["asset_id"] = video_track["clips"][0]["asset_id"]
    payload["tracks"][0]["clips"][0]["shot_id"] = "not-a-shot"
    with pytest.raises(ApiError) as excinfo:
        service.save_timeline(project.id, payload, user=user)
    assert excinfo.value.code == "invalid_timeline"


def test_failed_save_keeps_previous_timeline(tmp_path, monkeypatch):
    app, cfg, user, project, shots, _assets = _setup(tmp_path)
    service = get_timeline_service(cfg)
    initial = service.get_timeline(project.id, ensure=True, user=user)
    video_track = next(t for t in initial["tracks"] if t["track"]["role"] == "video")
    payload = {
        "timeline_version": initial["timeline_version"],
        "tracks": [{
            "track_type": "video", "role": "video", "sequence_no": 0,
            "clips": [{
                "shot_id": video_track["clips"][0]["shot_id"],
                "asset_id": video_track["clips"][0]["asset_id"],
                "start_time": 0, "duration_s": 1.0,
            }],
        }],
    }

    original = service._insert_timeline

    def explode(cursor, project_id, tracks, now):
        original(cursor, project_id, tracks[:1], now)
        raise RuntimeError("simulated insert failure")

    monkeypatch.setattr(service, "_insert_timeline", explode)
    with pytest.raises(RuntimeError):
        service.save_timeline(project.id, payload, user=user)
    monkeypatch.setattr(service, "_insert_timeline", original)

    after = service.get_timeline(project.id, user=user)
    assert after["timeline_version"] == initial["timeline_version"]
    assert len(after["tracks"]) == len(initial["tracks"])
    assert len([
        c for t in after["tracks"] if t["track"]["role"] == "video"
        for c in t["clips"]
    ]) == 3


def test_save_rejects_inconsistent_trim_out_and_duration(tmp_path):
    app, cfg, user, project, shots, _assets = _setup(tmp_path)
    service = get_timeline_service(cfg)
    initial = service.get_timeline(project.id, ensure=True, user=user)
    video_track = next(t for t in initial["tracks"] if t["track"]["role"] == "video")
    payload = {
        "timeline_version": initial["timeline_version"],
        "tracks": [{
            "track_type": "video", "role": "video", "sequence_no": 0,
            "clips": [{
                "shot_id": video_track["clips"][0]["shot_id"],
                "asset_id": video_track["clips"][0]["asset_id"],
                "start_time": 0, "duration_s": 2.0,
                "trim_in": 0, "trim_out": 1.0,
            }],
        }],
    }
    with pytest.raises(ApiError) as excinfo:
        service.save_timeline(project.id, payload, user=user)
    assert excinfo.value.code == "invalid_timeline"


def test_build_srt_skips_muted_subtitle_clips():
    from backend.timeline_service import TimelineService
    timeline = {"tracks": [{
        "track": {"role": "subtitle", "track_type": "subtitle"},
        "clips": [
            {"start_time": 0, "duration_s": 1, "subtitle_text": "保留", "muted": False},
            {"start_time": 1, "duration_s": 1, "subtitle_text": "静音", "muted": True},
        ],
    }]}
    srt = TimelineService.build_srt_from_timeline(timeline)
    assert "保留" in srt
    assert "静音" not in srt
