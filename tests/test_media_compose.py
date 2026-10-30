# -*- coding: utf-8 -*-
"""Timeline-driven FFmpeg composition with real audio and subtitles."""
from __future__ import absolute_import

import os
import shutil
import subprocess

import pytest

from backend.media_service import MediaService, MediaServiceError

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg required")


def _video(path, color, duration=1.0, with_audio=True):
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "color=c={0}:s=320x180:r=24:d={1}".format(color, duration),
    ]
    if with_audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=330:duration={0}".format(duration)]
        args += ["-c:a", "aac", "-shortest"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    subprocess.run(args, check=True)


def _audio(path, frequency=440, duration=0.8):
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "sine=frequency={0}:duration={1}".format(frequency, duration),
        "-c:a", "pcm_s16le", path,
    ], check=True)


def _timeline(video_a, video_b, narration, music, sfx):
    return {
        "timeline_version": 3,
        "duration_s": 2.0,
        "tracks": [
            {"track": {"role": "video", "track_type": "video"}, "clips": [
                {
                    "id": "v1", "shot_id": "s1", "asset_id": "vid-a",
                    "name": "红色镜头", "start_time": 0.0, "duration_s": 1.0,
                    "trim_in": 0.0, "trim_out": 1.0, "volume": 1.0,
                    "muted": False, "source_audio_enabled": False,
                    "fade_in": 0.0, "fade_out": 0.0, "subtitle_text": None,
                },
                {
                    "id": "v2", "shot_id": "s2", "asset_id": "vid-b",
                    "name": "绿色镜头", "start_time": 1.0, "duration_s": 1.0,
                    "trim_in": 0.0, "trim_out": 1.0, "volume": 1.0,
                    "muted": False, "source_audio_enabled": False,
                    "fade_in": 0.0, "fade_out": 0.0, "subtitle_text": None,
                },
            ]},
            {"track": {"role": "narration", "track_type": "audio"}, "clips": [{
                "id": "n1", "shot_id": "s1", "asset_id": "narration",
                "name": "旁白", "start_time": 0.1, "duration_s": 0.8,
                "trim_in": 0.0, "trim_out": 0.8, "volume": 1.0,
                "muted": False, "source_audio_enabled": True,
                "fade_in": 0.0, "fade_out": 0.0, "subtitle_text": None,
            }]},
            {"track": {"role": "music", "track_type": "audio"}, "clips": [{
                "id": "m1", "shot_id": None, "asset_id": "music",
                "name": "音乐", "start_time": 0.0, "duration_s": 2.0,
                "trim_in": 0.0, "trim_out": 2.0, "volume": 0.25,
                "muted": False, "source_audio_enabled": True,
                "fade_in": 0.2, "fade_out": 0.3, "subtitle_text": None,
                "properties": {"loop": True},
            }]},
            {"track": {"role": "sfx", "track_type": "audio"}, "clips": [{
                "id": "e1", "shot_id": None, "asset_id": "sfx",
                "name": "音效", "start_time": 1.2, "duration_s": 0.4,
                "trim_in": 0.0, "trim_out": 0.4, "volume": 0.8,
                "muted": False, "source_audio_enabled": True,
                "fade_in": 0.0, "fade_out": 0.0, "subtitle_text": None,
            }]},
            {"track": {"role": "subtitle", "track_type": "subtitle"}, "clips": [
                {
                    "id": "sub1", "shot_id": "s1", "asset_id": None,
                    "name": "字幕1", "start_time": 0.1, "duration_s": 0.8,
                    "trim_in": 0, "trim_out": None, "volume": 1,
                    "muted": False, "source_audio_enabled": True,
                    "fade_in": 0, "fade_out": 0,
                    "subtitle_text": "第一段旁白",
                },
                {
                    "id": "sub2", "shot_id": "s2", "asset_id": None,
                    "name": "字幕2", "start_time": 1.0, "duration_s": 0.9,
                    "trim_in": 0, "trim_out": None, "volume": 1,
                    "muted": False, "source_audio_enabled": True,
                    "fade_in": 0, "fade_out": 0,
                    "subtitle_text": "第二段旁白",
                },
            ]},
        ],
    }


def test_compose_timeline_produces_verified_video_with_audio(tmp_path):
    video_a = str(tmp_path / "a.mp4")
    video_b = str(tmp_path / "b.mp4")
    narration = str(tmp_path / "narration.wav")
    music = str(tmp_path / "music.wav")
    sfx = str(tmp_path / "sfx.wav")
    _video(video_a, "red")
    _video(video_b, "green")
    _audio(narration, 440, 0.8)
    _audio(music, 220, 0.5)
    _audio(sfx, 880, 0.4)
    srt = str(tmp_path / "subtitles.srt")
    with open(srt, "w", encoding="utf-8") as handle:
        handle.write(
            "1\n00:00:00,100 --> 00:00:00,900\n第一段旁白\n\n"
            "2\n00:00:01,000 --> 00:00:01,900\n第二段旁白\n"
        )
    output = str(tmp_path / "final.mp4")
    service = MediaService(FFMPEG, FFPROBE)
    result = service.compose_timeline(
        _timeline(video_a, video_b, narration, music, sfx),
        output,
        {
            "width": 1280, "height": 720, "fps": 24, "crf": 23,
            "audio_bitrate": "128k", "subtitle_mode": "burn",
            "subtitle_path": srt, "subtitle_font_name": "Noto Sans CJK SC",
            "subtitle_font_size": 18, "keep_source_audio": False,
            "music_ducking": True, "loudness_normalize": False,
        },
        inputs={
            "vid-a": {"path": video_a, "has_audio": True, "duration_s": 1.0},
            "vid-b": {"path": video_b, "has_audio": True, "duration_s": 1.0},
            "narration": {"path": narration, "has_audio": True, "duration_s": 0.8},
            "music": {"path": music, "has_audio": True, "duration_s": 0.5},
            "sfx": {"path": sfx, "has_audio": True, "duration_s": 0.4},
        },
    )
    assert os.path.isfile(output)
    assert os.path.getsize(output) > 10000
    info = result["media_info"]
    assert info["has_video"] is True
    assert info["has_audio"] is True
    assert info["video"]["width"] == 1280
    assert info["video"]["height"] == 720
    assert result["duration_s"] == pytest.approx(2.0, abs=0.25)
    assert result["timeline_version"] == 3
    # The decode check must actually read every frame.
    subprocess.run(
        [FFMPEG, "-v", "error", "-xerror", "-i", output, "-f", "null", "-"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_compose_rejects_missing_video_input(tmp_path):
    service = MediaService(FFMPEG, FFPROBE)
    output = str(tmp_path / "out.mp4")
    with pytest.raises(MediaServiceError):
        service.compose_timeline(
            _timeline("missing", "missing", "missing", "missing", "missing"),
            output,
            {
                "width": 1280, "height": 720, "fps": 24,
                "subtitle_mode": "none",
            },
            inputs={},
        )
    assert not os.path.exists(output)
