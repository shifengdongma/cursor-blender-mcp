# -*- coding: utf-8 -*-
"""Deterministic FFmpeg filter validation and application."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

from backend.http_utils import ApiError
from backend.media_filters import validate_filters
from backend.media_service import MediaService, MediaServiceError, probe_media_file

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg required")


def test_filter_validation_rejects_empty_and_unknown():
    with pytest.raises(ApiError) as excinfo:
        validate_filters({})
    assert excinfo.value.code == "empty_filters"
    with pytest.raises(ApiError) as excinfo:
        validate_filters({"brightness": 0.1, "shell": "-vf evil"})
    assert excinfo.value.code == "unsupported_filter"
    with pytest.raises(ApiError):
        validate_filters({"contrast": 99})


def test_filter_validation_normalises_supported_values():
    result = validate_filters({
        "brightness": 0.1,
        "contrast": 1.1,
        "saturation": 1.2,
        "hue": 15,
        "blur": 2,
        "sharpen": 1,
        "exposure": 0.2,
        "crop": {"w": 320, "h": 180, "x": 0, "y": 0},
        "scale": {"width": 640, "height": 360},
        "fps": 30,
    })
    assert result["brightness"] == 0.1
    assert result["crop"] == (320, 180, 0, 0)
    assert result["scale"] == (640, 360)
    assert result["fps"] == 30


def test_apply_filter_chain_rejects_empty_filters(tmp_path):
    service = MediaService(FFMPEG, FFPROBE)
    video = str(tmp_path / "in.mp4")
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=640x360:r=24:d=0.5",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", video,
    ], check=True)
    with pytest.raises(MediaServiceError):
        service.apply_filter_chain(video, str(tmp_path / "out.mp4"), {})
    assert not os.path.exists(str(tmp_path / "out.mp4"))


def test_apply_filter_chain_outputs_real_filtered_video(tmp_path):
    service = MediaService(FFMPEG, FFPROBE)
    video = str(tmp_path / "in.mp4")
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=640x360:r=24:d=0.5",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", video,
    ], check=True)
    output = str(tmp_path / "out.mp4")
    service.apply_filter_chain(input_path=video, output_path=output, filters={
        "brightness": 0.05,
        "contrast": 1.1,
        "saturation": 1.1,
        "hue": 10,
        "blur": 1,
        "sharpen": 0.5,
        "scale": (320, 180),
        "fps": 24,
    })
    assert os.path.getsize(output) > 1000
    info = probe_media_file(FFPROBE, output)
    assert info["has_video"] is True
    assert info["video"]["width"] == 320
    assert info["video"]["height"] == 180


def test_filter_validation_rejects_malformed_crop_and_scale():
    for filters in (
        {"scale": [1280, 720, 0, 0]},
        {"crop": [100, 100]},
        {"crop": {"w": 100}},
    ):
        with pytest.raises(ApiError) as excinfo:
            validate_filters(filters)
        assert excinfo.value.code == "invalid_filters"
