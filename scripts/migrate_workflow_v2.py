#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Idempotent, additive media-workflow migration with a pre-migration backup.

Run with the web/worker processes stopped, or at least with the existing
gunicorn process idle.  The migration never drops tables or user data.
"""
from __future__ import absolute_import

import argparse
import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.database import Database  # noqa: E402

REQUIRED_COLUMNS = {
    "assets": {"duration_s", "audio_role", "media_info"},
    "storyboard_shots": {
        "subtitle_asset_id", "audio_options", "audio_duration_s",
        "selected_video_asset_id", "refined_video_asset_id",
        "video_selection_source",
    },
    "creative_projects": {
        "timeline_version", "final_video_asset_id",
        "final_compose_task_id", "final_timeline_version",
    },
    "timeline_tracks": {"role"},
    "timeline_clips": {
        "volume", "muted", "source_audio_enabled",
        "fade_in", "fade_out", "subtitle_text",
    },
    "generation_tasks": {
        "timeline_version", "timeline_snapshot", "created_at_ms",
        "claimed_at_ms", "provider_request_started_at",
        "provider_request_finished_at", "provider_job_created_at",
        "provider_finished_at", "download_started_at",
        "download_finished_at", "persist_started_at",
        "persist_finished_at", "completed_at_ms", "timing_json",
    },
    "export_packages": {"asset_id", "timeline_version"},
}


def _backup(db_path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    target = os.path.join(
        backup_dir, "aigv-{0}.db".format(time.strftime("%Y%m%d-%H%M%S"))
    )
    source = sqlite3.connect(db_path)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def _columns(conn, table):
    return {
        row[1] for row in conn.execute("PRAGMA table_info({0})".format(table))
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--backup", action="store_true", default=True)
    parser.add_argument("--no-backup", dest="backup", action="store_false")
    args = parser.parse_args()
    db_path = os.path.abspath(os.path.join(args.data_dir, "aigv.db"))
    if not os.path.isfile(db_path):
        raise SystemExit("database not found: {0}".format(db_path))

    backup_path = None
    if args.backup:
        backup_path = _backup(
            db_path, os.path.join(os.path.abspath(args.data_dir), "backups")
        )
        print("backup: {0}".format(backup_path))

    before = sqlite3.connect(db_path)
    try:
        bad_srt = before.execute(
            "SELECT COUNT(*) FROM storyboard_shots "
            "WHERE srt_path IS NOT NULL AND lower(srt_path) LIKE '%.wav'"
        ).fetchone()[0]
    finally:
        before.close()

    Database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        missing = {}
        for table, columns in REQUIRED_COLUMNS.items():
            present = _columns(conn, table)
            absent = sorted(columns - present)
            if absent:
                missing[table] = absent
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        versions = [
            row[0] for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        counts = {
            table: conn.execute(
                "SELECT COUNT(*) FROM {0}".format(table)
            ).fetchone()[0]
            for table in (
                "creative_projects", "storyboard_shots", "generation_tasks",
                "timeline_tracks", "timeline_clips", "shot_media_versions",
            )
        }
    finally:
        conn.close()

    if missing or "shot_media_versions" not in tables:
        print(json.dumps({
            "ok": False,
            "missing": missing,
            "has_shot_media_versions": "shot_media_versions" in tables,
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(json.dumps({
        "ok": True,
        "database": db_path,
        "backup": backup_path,
        "schema_versions": versions,
        "wav_srt_pointers_cleared": bad_srt,
        "counts": counts,
        "note": "WAV files themselves were not deleted; only incorrect srt_path pointers were cleared.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
