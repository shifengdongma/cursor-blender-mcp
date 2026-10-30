#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local generation/media benchmark without paid provider calls.

It exercises the real GenerationService submit/finalize path with a fake
provider, plus the batched task serializer and timeline composition.  Run from
the repository root:

    .venv/bin/python scripts/benchmark_generation.py --tasks 30
"""
from __future__ import absolute_import

import argparse
import base64
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend import generation_service  # noqa: E402
from backend.asset_service import get_asset_service  # noqa: E402
from backend.auth_service import AuthService  # noqa: E402
from backend.database import get_database, reset_database  # noqa: E402
from backend.media_service import MediaService  # noqa: E402
from backend.models import Asset, GenerationTask, TaskArtifact  # noqa: E402
from backend.task_serializer import public_task_dict, public_task_dicts  # noqa: E402
from backend.task_service import get_task_service  # noqa: E402

PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 256
).decode("ascii")


class FakeProvider(object):
    def __init__(self, delay):
        self.delay = delay

    def generate(self, **kwargs):
        time.sleep(self.delay)
        return {"images": [{"b64_json": PNG}]}


def _config(data_dir, delay):
    return types.SimpleNamespace(
        DATA_DIR=data_dir,
        DEMO_MODE=False,
        MAX_GENERATION_DOWNLOAD_MB=50,
        MAX_PROMPT_LENGTH=4000,
        GENERATION_POLL_INTERVAL_S=1,
        GENERATION_POLL_MAX_ERRORS=8,
        GENERATION_IMAGE_DEADLINE_S=1800,
        GENERATION_VIDEO_DEADLINE_S=7200,
        PROVIDER_CONNECT_TIMEOUT_S=10,
        FFMPEG_BIN=shutil.which("ffmpeg") or "ffmpeg",
        FFPROBE_BIN=shutil.which("ffprobe") or "ffprobe",
        FAKE_PROVIDER_DELAY=delay,
    )


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * p / 100.0
    low = int(index)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def _stats(values):
    values = [value for value in values if value is not None]
    return {
        "count": len(values),
        "avg_ms": round(statistics.mean(values), 2) if values else None,
        "median_ms": round(statistics.median(values), 2) if values else None,
        "p95_ms": round(_percentile(values, 95), 2) if values else None,
    }


def _make_video(path, color):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c={0}:s=640x360:r=24:d=1".format(color),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ], check=True)


FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def run(args):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg/ffprobe required")
    data_dir = tempfile.mkdtemp(prefix="aigv_bench_")
    reset_database()
    db = get_database(os.path.join(data_dir, "aigv.db"))
    cfg = _config(data_dir, args.provider_delay)
    user = AuthService(data_dir).create_user(
        username="bench_user",
        password="BenchPass12345",
        email="bench@example.com",
        role="user",
    )
    task_service = get_task_service(data_dir)
    generation_service._provider_for_task = lambda cfg, task: FakeProvider(
        cfg.FAKE_PROVIDER_DELAY
    )
    durations = []
    timings = []
    for index in range(args.tasks):
        created = task_service.create_task(
            creative_project_id=None,
            task_type=GenerationTask.TYPE_IMAGE,
            created_by=user["id"],
            provider="fake",
            model_id="fake-image",
            params={"prompt": "benchmark", "model_key": "fake"},
            status=GenerationTask.STATUS_QUEUED,
        )
        lease_owner = "bench-{0}".format(index)
        claimed = task_service.claim_generation_submission(
            lease_owner, lease_seconds=900
        )
        if claimed is None or claimed.id != created.id:
            raise SystemExit("could not claim benchmark task")
        start = time.perf_counter()
        generation_service.submit_task(cfg, task_service, claimed, lease_owner)
        durations.append((time.perf_counter() - start) * 1000)
        refreshed = task_service.get_task(created.id)
        timings.append({
            "queue_wait_ms": (
                (refreshed.claimed_at_ms or 0) - (refreshed.created_at_ms or 0)
            ) * 1000 if refreshed.claimed_at_ms and refreshed.created_at_ms else None,
            "submission_ms": (
                (refreshed.provider_request_finished_at or 0)
                - (refreshed.provider_request_started_at or 0)
            ) * 1000 if refreshed.provider_request_finished_at else None,
            "persist_ms": (
                (refreshed.persist_finished_at or 0)
                - (refreshed.persist_started_at or 0)
            ) * 1000 if refreshed.persist_finished_at else None,
        })

    # Batch serializer vs the old per-task shape (same result set).
    asset_service = get_asset_service(data_dir)
    listed = task_service.list_tasks(created_by=user["id"], limit=args.tasks)["items"]
    tasks = [task_service.get_task(item["id"]) for item in listed]
    tasks = [task for task in tasks if task]
    start = time.perf_counter()
    batch = public_task_dicts(tasks, asset_service, task_service)
    batch_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    naive = [public_task_dict(task, asset_service, task_service) for task in tasks]
    naive_ms = (time.perf_counter() - start) * 1000

    # Three-clip composition with narration, music and subtitles.
    media = MediaService(FFMPEG, shutil.which("ffprobe"))
    compose_tmp = os.path.join(data_dir, "compose")
    os.makedirs(compose_tmp, exist_ok=True)
    clips = []
    for index, color in enumerate(("red", "green", "blue")):
        path = os.path.join(compose_tmp, "clip{0}.mp4".format(index))
        _make_video(path, color)
        clips.append(path)
    tracks = [{"track": {"role": "video", "track_type": "video"}, "clips": []}]
    for index, path in enumerate(clips):
        tracks[0]["clips"].append({
            "asset_id": "v{0}".format(index), "shot_id": "s{0}".format(index),
            "start_time": float(index), "duration_s": 1.0, "trim_in": 0.0,
            "trim_out": 1.0, "volume": 1.0, "muted": False,
            "source_audio_enabled": False, "fade_in": 0, "fade_out": 0,
        })
    inputs = {
        "v{0}".format(index): {"path": path, "has_audio": False, "duration_s": 1.0}
        for index, path in enumerate(clips)
    }
    timeline = {"timeline_version": 1, "tracks": tracks}
    start = time.perf_counter()
    result = media.compose_timeline(
        timeline, os.path.join(compose_tmp, "final.mp4"),
        {"width": 1280, "height": 720, "fps": 24, "crf": 26,
         "subtitle_mode": "none", "keep_source_audio": False,
         "loudness_normalize": False},
        inputs=inputs,
    )
    compose_ms = (time.perf_counter() - start) * 1000

    output = {
        "tasks": args.tasks,
        "provider_delay_s": args.provider_delay,
        "submit_total_ms": _stats(durations),
        "queue_wait_ms": _stats([item["queue_wait_ms"] for item in timings]),
        "provider_request_ms": _stats([item["submission_ms"] for item in timings]),
        "persist_ms": _stats([item["persist_ms"] for item in timings]),
        "task_list": {
            "batch_ms": round(batch_ms, 2),
            "naive_ms": round(naive_ms, 2),
            "items": len(batch),
            "same_result": len(batch) == len(naive),
        },
        "compose_3_clips_ms": round(compose_ms, 2),
        "compose_duration_s": result["duration_s"],
        "note": "Fake provider; queue/provider/persist numbers measure local code, not real model inference.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    shutil.rmtree(data_dir, ignore_errors=True)
    reset_database()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=20)
    parser.add_argument("--provider-delay", type=float, default=0.02)
    run(parser.parse_args())
