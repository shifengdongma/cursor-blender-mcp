# -*- coding: utf-8 -*-
"""Additive media-workflow schema and model contracts."""
from __future__ import absolute_import

from backend.database import get_database
from backend.models import ShotMediaVersion, TimelineClip


def _columns(db, table):
    return {row["name"] for row in db.fetch_all("PRAGMA table_info({0})".format(table))}


def test_media_workflow_columns_exist(test_db):
    assets = _columns(test_db, "assets")
    assert {"duration_s", "audio_role", "media_info"} <= assets

    shots = _columns(test_db, "storyboard_shots")
    assert {
        "subtitle_asset_id", "audio_options", "audio_duration_s",
        "selected_video_asset_id", "refined_video_asset_id",
        "video_selection_source",
    } <= shots

    projects = _columns(test_db, "creative_projects")
    assert {
        "timeline_version", "final_video_asset_id",
        "final_compose_task_id", "final_timeline_version",
    } <= projects

    clips = _columns(test_db, "timeline_clips")
    assert {
        "volume", "muted", "source_audio_enabled",
        "fade_in", "fade_out", "subtitle_text",
    } <= clips
    assert "role" in _columns(test_db, "timeline_tracks")

    tasks = _columns(test_db, "generation_tasks")
    assert {
        "timeline_version", "timeline_snapshot",
        "provider_request_started_at", "provider_request_finished_at",
        "download_started_at", "download_finished_at",
        "persist_started_at", "persist_finished_at",
        "created_at_ms", "claimed_at_ms", "completed_at_ms", "timing_json",
    } <= tasks
    assert {"asset_id", "timeline_version"} <= _columns(test_db, "export_packages")

    tables = {
        row["name"]
        for row in test_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "shot_media_versions" in tables
    versions = {
        row["version"]
        for row in test_db.fetch_all("SELECT version FROM schema_migrations")
    }
    assert {1, 2, 3, 4, 5} <= versions


def test_schema_migration_is_idempotent(test_db):
    path = test_db.db_path
    test_db.close()
    again = get_database(path)
    try:
        columns = _columns(again, "timeline_clips")
        assert "volume" in columns
        versions = {
            row["version"]
            for row in again.fetch_all("SELECT version FROM schema_migrations")
        }
        assert {1, 2, 3, 4, 5} <= versions
    finally:
        again.close()


def test_new_models_roundtrip(test_db):
    clip = TimelineClip(
        track_id="track-1",
        creative_project_id="project-1",
        shot_id=None,
        asset_id=None,
        name="clip",
        start_time=1.5,
        duration_s=2.5,
        trim_in=0.25,
        trim_out=2.75,
        volume=0.8,
        muted=True,
        source_audio_enabled=False,
        fade_in=0.1,
        fade_out=0.2,
        subtitle_text="字幕",
    )
    assert clip.to_dict()["volume"] == 0.8
    assert clip.to_dict()["muted"] is True

    version = ShotMediaVersion(
        creative_project_id="project-1",
        shot_id="shot-1",
        media_kind="audio",
        asset_id="asset-1",
        source="tts",
        label="华言女声",
        metadata={"voice_id": "piper:test"},
        is_selected=True,
    )
    assert version.to_dict()["media_kind"] == "audio"
    assert version.to_dict()["metadata"]["voice_id"] == "piper:test"
