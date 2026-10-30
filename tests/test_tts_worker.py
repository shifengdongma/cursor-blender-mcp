# -*- coding: utf-8 -*-
"""Per-shot TTS execution: history, metadata, real SRT, no overwrite."""
from __future__ import absolute_import

import os

from backend import storyboard_service, task_worker
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.database import get_database
from backend.models import GenerationTask, ShotMediaVersion
from backend.task_service import get_task_service
from tests import support


def _setup(app, username):
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username=username, email="{0}@example.com".format(username)
    )
    project = get_creative_project_service(cfg.DATA_DIR).create_project(
        name="TTS project",
        tenant_id=user.get("tenant_id"),
        user_id=user["id"],
    )
    shot = storyboard_service.get_storyboard_service(cfg.DATA_DIR).create_shot(
        project.id,
        scene_title="第一镜",
        dialogue="这是第一段旁白",
        duration_s=4,
    )
    return cfg, user, project, shot


class FakeTTS(object):
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def synthesize(self, text, voice_id, output_path, options=None):
        FakeTTS.calls.append({
            "text": text,
            "voice_id": voice_id,
            "output_path": output_path,
            "options": options,
        })
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as handle:
            handle.write(b"RIFF" + text.encode("utf-8") * 10)
        return {
            "output_path": output_path,
            "duration_s": 2.5,
            "format": "wav",
            "provider": "piper",
            "voice_id": voice_id,
            "voice_label": "测试音色",
            "speech_rate": (options or {}).get("speech_rate", 1.0),
            "volume": (options or {}).get("volume", 1.0),
            "media_info": {"codec": "pcm_s16le", "sample_rate": 48000, "channels": 1},
        }


def _task(cfg, user, project, params):
    return get_task_service(cfg.DATA_DIR).create_task(
        creative_project_id=project.id,
        task_type=GenerationTask.TYPE_TTS,
        created_by=user["id"],
        params=params,
    )


def test_per_shot_tts_creates_history_srt_and_keeps_old_audio(app, monkeypatch):
    cfg, user, project, shot = _setup(app, "tts_shot")
    monkeypatch.setattr(task_worker, "PiperTTSProvider", FakeTTS)
    FakeTTS.calls = []

    task = _task(cfg, user, project, {
        "shot_ids": [shot.id],
        "provider": "piper",
        "voice_id": "piper:test",
        "text": "这是第一段旁白",
        "speech_rate": 1.2,
        "volume": 0.8,
    })
    first = task_worker._execute_tts(task, cfg, get_database())

    asset_service = get_asset_service(cfg.DATA_DIR)
    shot_row = storyboard_service.get_storyboard_service(cfg.DATA_DIR).get_shot(shot.id)
    first_asset = asset_service.get_asset(first["audio_assets"][0]["asset_id"])
    assert first_asset.asset_type == "audio"
    assert first_asset.audio_role == "narration"
    assert first_asset.duration_s == 2.5
    assert first_asset.owner_user_id == user["id"]
    assert first_asset.metadata["voice_id"] == "piper:test"
    assert first_asset.metadata["speech_rate"] == 1.2
    assert shot_row.audio_asset_id == first_asset.id
    assert shot_row.audio_duration_s == 2.5
    assert shot_row.srt_path.endswith(".srt")
    assert os.path.isfile(shot_row.srt_path)
    assert not shot_row.srt_path.endswith(".wav")
    with open(shot_row.srt_path, "r", encoding="utf-8") as handle:
        srt = handle.read()
    assert "这是第一段旁白" in srt
    assert "00:00:00,000 --> 00:00:02,500" in srt
    subtitle = asset_service.get_asset(shot_row.subtitle_asset_id)
    assert subtitle is not None and subtitle.asset_type == "subtitle"
    assert first["audio_assets"][0]["subtitle_asset_id"] == subtitle.id
    versions = get_database().fetch_all(
        "SELECT * FROM shot_media_versions WHERE shot_id = ? AND media_kind = 'audio'",
        (shot.id,),
    )
    assert len(versions) == 1
    assert ShotMediaVersion.from_row(versions[0]).metadata["voice_id"] == "piper:test"

    # Regenerating creates a new file and version; the old file survives.
    task2 = _task(cfg, user, project, {
        "shot_ids": [shot.id],
        "voice_id": "piper:test",
        "speech_rate": 0.9,
        "volume": 1.0,
    })
    second = task_worker._execute_tts(task2, cfg, get_database())
    second_asset = asset_service.get_asset(second["audio_assets"][0]["asset_id"])
    assert second_asset.id != first_asset.id
    assert second_asset.file_path != first_asset.file_path
    assert os.path.isfile(asset_service.get_file_path_for_asset(first_asset))
    assert len(asset_service.db.fetch_all(
        "SELECT * FROM shot_media_versions WHERE shot_id = ? AND media_kind = 'audio'",
        (shot.id,),
    )) == 2


def test_tts_with_no_text_does_not_create_fake_audio(app, monkeypatch):
    cfg, user, project, shot = _setup(app, "tts_empty")
    storyboard_service.get_storyboard_service(cfg.DATA_DIR).update_shot(
        shot.id, dialogue=""
    )
    monkeypatch.setattr(task_worker, "PiperTTSProvider", FakeTTS)
    task = _task(cfg, user, project, {"shot_ids": [shot.id]})
    result = task_worker._execute_tts(task, cfg, get_database())
    assert result["audio_assets"] == []
    assert result["skipped"] == 1
