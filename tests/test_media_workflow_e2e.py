# -*- coding: utf-8 -*-
"""Real Piper + FFmpeg E2E: TTS, timeline, MP4 compose and ZIP export."""
from __future__ import absolute_import

import io
import json
import os
import shutil
import subprocess
import zipfile

import pytest

from backend import storyboard_service, task_worker
from backend.media_service import probe_media_file
from backend.models import GenerationTask
from backend.task_service import get_task_service
from tests import support

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER = shutil.which("piper") or "/usr/local/bin/piper"
MODEL = os.path.join(ROOT, "data", "tts_models", "zh_CN-huayan-medium.onnx")
VOICES = os.path.join(ROOT, "data", "tts_voices.json")
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

pytestmark = pytest.mark.skipif(
    not (FFMPEG and FFPROBE and os.path.isfile(PIPER) and os.path.isfile(MODEL)
         and os.path.isfile(VOICES)),
    reason="real Piper voice, ffmpeg and ffprobe required",
)


def _video(path, color):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c={0}:s=640x360:r=24:d=1".format(color),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


def _audio(path, frequency, duration):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency={0}:duration={1}".format(frequency, duration),
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _upload(client, token, path, asset_type, name, audio_role=None):
    data = {
        "file": (open(path, "rb"), os.path.basename(path)),
        "asset_type": asset_type,
        "name": name,
    }
    if audio_role:
        data["audio_role"] = audio_role
    response = client.post(
        "/api/assets/upload", data=data,
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_real_media_workflow(tmp_path):
    app = support.make_app(
        tmp_path,
        PIPER_BIN=PIPER,
        PIPER_MODEL_PATH=MODEL,
        TTS_MODEL_DIR=os.path.join(ROOT, "data", "tts_models"),
        TTS_VOICES_FILE=VOICES,
        TTS_DEFAULT_VOICE_ID="piper:zh_CN-huayan-medium",
        FFMPEG_BIN=FFMPEG,
        FFPROBE_BIN=FFPROBE,
    )
    cfg = app.config["AIGV_CONFIG"]
    client = app.test_client()
    user, token = support.register_and_login(client, "e2e_media")
    headers = support.auth_headers(token)

    project_resp = client.post(
        "/api/creative/projects", json={"name": "真实媒体验收"}, headers=headers
    )
    assert project_resp.status_code == 201, project_resp.get_json()
    project_id = project_resp.get_json()["data"]["id"]
    shot_service = storyboard_service.get_storyboard_service(cfg.DATA_DIR)
    shots = []
    for index, color in enumerate(("red", "blue")):
        shot = shot_service.create_shot(
            project_id,
            scene_title="验收镜头{0}".format(index + 1),
            dialogue="你好" if index == 0 else "",
            duration_s=1.0,
        )
        video_path = str(tmp_path / "source_{0}.mp4".format(index))
        _video(video_path, color)
        video_asset = _upload(client, token, video_path, "video", "源视频{0}".format(index))
        # Test setup uses the trusted service path for media pointers; the
        # public API intentionally rejects arbitrary pointer writes.
        shot_service.update_shot(
            shot.id,
            video_asset_id=video_asset["id"],
            selected_video_asset_id=video_asset["id"],
            status="confirmed",
        )
        shots.append(shot_service.get_shot(shot.id))

    # Real local Piper TTS through the API task/worker path.
    tts_resp = client.post(
        "/api/creative/shots/{0}/tts".format(shots[0].id),
        json={
            "provider": "piper",
            "voice_id": "piper:zh_CN-huayan-medium",
            "text": "你好",
            "speech_rate": 1.0,
            "volume": 1.0,
            "client_request_id": "e2e-tts-1",
        },
        headers=headers,
    )
    assert tts_resp.status_code == 201, tts_resp.get_json()
    task_service = get_task_service(cfg.DATA_DIR)
    tts_task = task_service.claim_next_task(task_types=(GenerationTask.TYPE_TTS,))
    assert tts_task and tts_task.id == tts_resp.get_json()["data"]["id"]
    task_worker._process_task(task_service, cfg, task_service.db, tts_task)
    tts_done = task_service.get_task(tts_task.id)
    assert tts_done.status == GenerationTask.STATUS_SUCCEEDED, tts_done.error_message
    shot = shot_service.get_shot(shots[0].id)
    assert shot.audio_asset_id
    assert shot.audio_duration_s > 0
    assert shot.srt_path.endswith(".srt") and os.path.isfile(shot.srt_path)
    audio_resp = client.get("/api/creative/shots/{0}/audio".format(shot.id))
    assert audio_resp.status_code == 200
    assert audio_resp.get_json()["data"]["items"][0]["asset"]["file_url"]

    # Upload real music and SFX.
    music_path = str(tmp_path / "music.wav")
    sfx_path = str(tmp_path / "sfx.wav")
    _audio(music_path, 220, 1.0)
    _audio(sfx_path, 880, 0.3)
    music = _upload(client, token, music_path, "audio", "验收音乐", "music")
    sfx = _upload(client, token, sfx_path, "audio", "验收音效", "sfx")

    timeline_resp = client.get(
        "/api/creative/projects/{0}/timeline?ensure=1".format(project_id)
    )
    assert timeline_resp.status_code == 200, timeline_resp.get_json()
    timeline = timeline_resp.get_json()["data"]
    assert timeline["initialized"] is True
    tracks = timeline["tracks"]
    for item in tracks:
        role = (item.get("track") or {}).get("role")
        if role == "music":
            item["clips"] = [{
                "shot_id": None, "asset_id": music["id"], "name": "验收音乐",
                "start_time": 0.0, "duration_s": 2.0, "trim_in": 0.0,
                "trim_out": 1.0, "volume": 0.3, "muted": False,
                "source_audio_enabled": True, "fade_in": 0.1, "fade_out": 0.1,
                "subtitle_text": None, "properties": {"loop": True},
            }]
        if role == "sfx":
            item["clips"] = [{
                "shot_id": None, "asset_id": sfx["id"], "name": "验收音效",
                "start_time": 0.4, "duration_s": 0.3, "trim_in": 0.0,
                "trim_out": 0.3, "volume": 0.8, "muted": False,
                "source_audio_enabled": True, "fade_in": 0.0, "fade_out": 0.0,
                "subtitle_text": None, "properties": {},
            }]
    saved = client.put(
        "/api/creative/projects/{0}/timeline".format(project_id),
        json={"timeline_version": timeline["timeline_version"], "tracks": tracks},
        headers=headers,
    )
    assert saved.status_code == 200, saved.get_json()
    saved_timeline = saved.get_json()["data"]

    compose = client.post(
        "/api/creative/projects/{0}/compose".format(project_id),
        json={
            "resolution": "720p", "fps": 24, "crf": 28,
            "subtitle_mode": "burn", "keep_source_audio": False,
            "loudness_normalize": False,
            "timeline_version": saved_timeline["timeline_version"],
            "client_request_id": "e2e-compose-1",
        },
        headers=headers,
    )
    assert compose.status_code == 202, compose.get_json()
    compose_task = task_service.claim_next_task(
        task_types=(GenerationTask.TYPE_COMPOSE,)
    )
    assert compose_task and compose_task.id == compose.get_json()["data"]["id"]
    task_worker._process_task(task_service, cfg, task_service.db, compose_task)
    compose_done = task_service.get_task(compose_task.id)
    assert compose_done.status == GenerationTask.STATUS_SUCCEEDED, compose_done.error_message

    final = client.get(
        "/api/creative/projects/{0}/final-video".format(project_id)
    )
    assert final.status_code == 200, final.get_json()
    final_data = final.get_json()["data"]
    final_path = os.path.join(
        cfg.DATA_DIR, "assets", "videos", "composed", compose_task.id, "final_video.mp4"
    )
    assert os.path.isfile(final_path)
    info = probe_media_file(FFPROBE, final_path)
    assert info["has_video"] and info["has_audio"]
    assert info["video"]["width"] == 1280
    assert info["video"]["height"] == 720
    assert final_data["asset"]["id"] == compose_done.output_asset_id
    assert final_data["up_to_date"] is True
    assert final_data["subtitle_asset_id"]

    export = client.post(
        "/api/creative/projects/{0}/exports".format(project_id),
        json={"client_request_id": "e2e-export-1"}, headers=headers,
    )
    assert export.status_code == 201, export.get_json()
    export_task = task_service.claim_next_task(
        task_types=(GenerationTask.TYPE_EXPORT,)
    )
    task_worker._process_task(task_service, cfg, task_service.db, export_task)
    download = client.get(
        "/api/creative/tasks/{0}/export/download".format(export_task.id)
    )
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
        names = set(archive.namelist())
        assert "final/final_video.mp4" in names
        assert "subtitles/subtitles.srt" in names
        assert "manifest.json" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["final_video"]["asset_id"] == compose_done.output_asset_id

    # Re-login and confirm the finished video is still visible.
    client2 = app.test_client()
    support.login_and_token(client2, "e2e_media", password="password123")
    again = client2.get(
        "/api/creative/projects/{0}/final-video".format(project_id)
    )
    assert again.status_code == 200
    assert again.get_json()["data"]["asset"]["id"] == compose_done.output_asset_id
