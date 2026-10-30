# -*- coding: utf-8 -*-
"""TTS voices, per-shot audio history/selection and audio uploads."""
from __future__ import absolute_import

import io
import json
import os
import stat
import wave

from backend import storyboard_service
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.database import get_database
from backend.models import ShotMediaVersion, TimelineClip, TimelineTrack
from tests import support

FAKE_PIPER = """#!/bin/sh
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--output_file" ]; then out="$arg"; fi
  prev="$arg"
done
python3 - "$out" <<'PY'
import sys, wave
with wave.open(sys.argv[1], 'wb') as h:
    h.setnchannels(1); h.setsampwidth(2); h.setframerate(16000)
    h.writeframes(b'\\x00\\x00' * 16000)
PY
"""


def _app_with_voice(tmp_path):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "voice.onnx").write_bytes(b"onnx")
    (model_dir / "voice.onnx.json").write_text("{}")
    piper = tmp_path / "piper"
    piper.write_text(FAKE_PIPER)
    piper.chmod(piper.stat().st_mode | stat.S_IXUSR)
    voices = {
        "version": 1,
        "voices": [{
            "id": "piper:voice",
            "provider": "piper",
            "label": "测试中文音色",
            "language": "zh-CN",
            "model_path": "voice.onnx",
            "config_path": "voice.onnx.json",
        }],
    }
    voices_file = tmp_path / "voices.json"
    voices_file.write_text(json.dumps(voices), encoding="utf-8")
    return support.make_app(
        tmp_path,
        PIPER_BIN=str(piper),
        PIPER_MODEL_PATH=str(model_dir / "voice.onnx"),
        TTS_MODEL_DIR=str(model_dir),
        TTS_VOICES_FILE=str(voices_file),
        TTS_DEFAULT_VOICE_ID="piper:voice",
        FFMPEG_BIN="/usr/bin/ffmpeg",
        FFPROBE_BIN="/usr/bin/ffprobe",
    )


def _project_and_shot(app, username):
    cfg = app.config["AIGV_CONFIG"]
    client = app.test_client()
    user, token = support.register_and_login(client, username)
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="Audio API project",
        tenant_id=user.get("tenant_id"),
        user_id=user["id"],
    )
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).create_shot(
        project.id, scene_title="镜头一", dialogue="原始旁白", duration_s=4
    )
    return client, user, token, project, shot


def test_voices_endpoint_lists_real_available_voice(tmp_path):
    app = _app_with_voice(tmp_path)
    client, _user, _token, _project, _shot = _project_and_shot(app, "voices_api")
    response = client.get("/api/creative/tts/voices")
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["default_voice_id"] == "piper:voice"
    assert data["items"][0]["available"] is True
    assert "model_path" not in data["items"][0]


def test_per_shot_tts_route_validates_and_persists_params(tmp_path):
    app = _app_with_voice(tmp_path)
    client, _user, _token, _project, shot = _project_and_shot(app, "shot_tts_api")
    token = support.csrf(client)
    response = client.post(
        "/api/creative/shots/{0}/tts".format(shot.id),
        json={
            "provider": "piper",
            "voice_id": "piper:voice",
            "text": "新的旁白",
            "speech_rate": 1.3,
            "volume": 0.7,
            "client_request_id": "shot-tts-1",
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201, response.get_json()
    task = response.get_json()["data"]
    assert task["task_type"] == "tts"
    assert task["params"]["shot_ids"] == [shot.id]
    assert task["params"]["voice_id"] == "piper:voice"
    assert task["params"]["speech_rate"] == 1.3
    assert storyboard_service.get_storyboard_service(
        app.config["AIGV_CONFIG"].DATA_DIR
    ).get_shot(shot.id).dialogue == "新的旁白"

    bad = client.post(
        "/api/creative/shots/{0}/tts".format(shot.id),
        json={"voice_id": "vp-001", "text": "x"},
        headers=support.auth_headers(token),
    )
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "tts_voice_not_found"


def test_shot_audio_history_and_selection(tmp_path):
    app = _app_with_voice(tmp_path)
    client, user, _token, project, shot = _project_and_shot(app, "audio_select")
    cfg = app.config["AIGV_CONFIG"]
    asset_service = get_asset_service(cfg.DATA_DIR)
    paths = []
    assets = []
    for index in range(2):
        path = os.path.join(asset_service.assets_dir, "audio", "take{0}.wav".format(index))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"RIFFtake")
        asset = asset_service.create_asset(
            name="take{0}".format(index),
            asset_type="audio",
            file_path=os.path.relpath(path, asset_service.assets_dir),
            file_size=8,
            audio_role="narration",
            duration_s=1.0 + index,
            owner_user_id=user["id"],
            tenant_id=user.get("tenant_id"),
            visibility="private",
        )
        version = ShotMediaVersion(
            creative_project_id=project.id,
            shot_id=shot.id,
            media_kind="audio",
            asset_id=asset.id,
            source="tts",
            label="take{0}".format(index),
            metadata={"voice_id": "piper:voice", "duration_s": 1.0 + index},
            is_selected=index == 0,
        )
        get_database().insert("shot_media_versions", version.to_insert_params())
        paths.append(path)
        assets.append(asset)
    storyboard_service.get_storyboard_service(cfg.DATA_DIR).update_shot(
        shot.id, audio_asset_id=assets[0].id
    )
    narration_track = TimelineTrack(
        creative_project_id=project.id, name="配音轨",
        track_type="audio", role="narration", sequence_no=1,
    )
    get_database().insert("timeline_tracks", narration_track.to_insert_params())
    narration_clip = TimelineClip(
        track_id=narration_track.id,
        creative_project_id=project.id,
        shot_id=shot.id,
        asset_id=assets[0].id,
        name="旧配音",
        start_time=0,
        duration_s=1.0,
        trim_in=0,
        trim_out=1.0,
    )
    get_database().insert("timeline_clips", narration_clip.to_insert_params())

    response = client.get("/api/creative/shots/{0}/audio".format(shot.id))
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["current_audio_asset_id"] == assets[0].id
    assert len(data["items"]) == 2
    assert data["items"][0]["asset"]["file_url"]
    assert data["items"][0]["is_selected"] is True

    token = support.csrf(client)
    selected = client.post(
        "/api/creative/shots/{0}/audio/selection".format(shot.id),
        json={"asset_id": assets[1].id},
        headers=support.auth_headers(token),
    )
    assert selected.status_code == 200, selected.get_json()
    selected_data = selected.get_json()["data"]
    assert selected_data["timeline_updated"] is True
    shot_after = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(
        shot.id
    )
    assert shot_after.audio_asset_id == assets[1].id
    assert shot_after.audio_duration_s == 2.0
    clip_after = get_database().fetch_one(
        "SELECT * FROM timeline_clips WHERE id = ?", (narration_clip.id,)
    )
    assert clip_after["asset_id"] == assets[1].id
    assert clip_after["duration_s"] == 2.0

    cleared = client.post(
        "/api/creative/shots/{0}/audio/selection".format(shot.id),
        json={"asset_id": None},
        headers=support.auth_headers(token),
    )
    assert cleared.status_code == 200, cleared.get_json()
    assert storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(
        shot.id
    ).audio_asset_id is None


def test_audio_upload_probes_and_rejects_invalid(tmp_path):
    app = _app_with_voice(tmp_path)
    client, user, _token, _project, _shot = _project_and_shot(app, "audio_upload")
    token = support.csrf(client)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)
    buffer.seek(0)
    ok = client.post(
        "/api/assets/upload",
        data={
            "file": (buffer, "music.wav"),
            "asset_type": "audio",
            "audio_role": "music",
            "name": "测试音乐",
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert ok.status_code == 201, ok.get_json()
    uploaded = ok.get_json()["data"]
    assert uploaded["audio_role"] == "music"
    assert uploaded["duration_s"] == 1.0

    listing = client.get("/api/assets?asset_type=audio&audio_role=music")
    assert listing.status_code == 200
    assert any(item["id"] == uploaded["id"] for item in listing.get_json()["data"]["items"])

    bad = client.post(
        "/api/assets/upload",
        data={
            "file": (io.BytesIO(b"not audio at all"), "broken.mp3"),
            "asset_type": "audio",
            "audio_role": "sfx",
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "invalid_audio"
