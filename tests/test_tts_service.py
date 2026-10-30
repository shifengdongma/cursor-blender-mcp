# -*- coding: utf-8 -*-
"""Voice registry, post-processing and failure contracts for real TTS."""
from __future__ import absolute_import

import json
import os
import shutil
import stat
import sys
import wave
from types import SimpleNamespace

import pytest

from backend.providers.base import ProviderError
from backend.providers.tts_provider import PiperTTSProvider, atempo_chain
from backend.tts_service import TTSVoiceRegistry


FAKE_PIPER = r'''#!/usr/bin/env python3
import sys, wave
args = sys.argv[1:]
output = args[args.index("--output_file") + 1]
text = sys.stdin.buffer.read().decode("utf-8")
if not text.strip():
    sys.exit(2)
seconds = 1.0
with wave.open(output, "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(16000)
    handle.writeframes(b"\x00\x00" * int(16000 * seconds))
'''


def _executable(path, content):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _cfg(tmp_path, **overrides):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    model = model_dir / "voice.onnx"
    model.write_bytes(b"onnx")
    (model_dir / "voice.onnx.json").write_text("{}", encoding="utf-8")
    piper = _executable(str(tmp_path / "piper"), FAKE_PIPER)
    fake_tool = _executable(str(tmp_path / "tool"), "#!/bin/sh\nexit 0\n")
    voices = {
        "version": 1,
        "providers": {"piper": {"enabled": True, "model_dir": str(model_dir)}},
        "voices": [{
            "id": "piper:voice",
            "provider": "piper",
            "label": "测试音色",
            "description": "unit test",
            "language": "zh-CN",
            "model_path": "voice.onnx",
            "config_path": "voice.onnx.json",
            "enabled": True,
        }],
    }
    voices_file = tmp_path / "voices.json"
    voices_file.write_text(json.dumps(voices), encoding="utf-8")
    values = dict(
        DATA_DIR=str(tmp_path),
        PIPER_BIN=piper,
        PIPER_MODEL_PATH=str(model),
        FFMPEG_BIN=fake_tool,
        FFPROBE_BIN=fake_tool,
        TTS_VOICES_FILE=str(voices_file),
        TTS_MODEL_DIR=str(model_dir),
        TTS_DEFAULT_VOICE_ID="piper:voice",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_registry_lists_only_available_real_voices(tmp_path):
    cfg = _cfg(tmp_path)
    registry = TTSVoiceRegistry(cfg)
    voices = registry.list_voices()
    assert len(voices) == 1
    voice = voices[0]
    assert voice["id"] == "piper:voice"
    assert voice["available"] is True
    assert voice["capabilities"]["speech_rate"]["postprocess"] == "ffmpeg-atempo"
    assert "model_path" not in voice

    os.remove(str(tmp_path / "models" / "voice.onnx"))
    registry = TTSVoiceRegistry(cfg)
    voice = registry.list_voices()[0]
    assert voice["available"] is False
    assert "模型" in voice["unavailable_reason"] or "model" in voice["unavailable_reason"].lower()


def test_registry_rejects_model_paths_outside_model_dir(tmp_path):
    cfg = _cfg(tmp_path)
    outside = tmp_path / "outside.onnx"
    outside.write_bytes(b"onnx")
    data = json.loads(open(cfg.TTS_VOICES_FILE).read())
    data["voices"][0]["model_path"] = "../outside.onnx"
    with open(cfg.TTS_VOICES_FILE, "w") as handle:
        json.dump(data, handle)
    voice = TTSVoiceRegistry(cfg).list_voices()[0]
    assert voice["available"] is False
    assert "目录" in voice["unavailable_reason"] or "outside" in voice["unavailable_reason"]
    with pytest.raises(ProviderError):
        TTSVoiceRegistry(cfg).resolve_voice("piper:voice")


def test_registry_resolves_default_and_rejects_unknown(tmp_path):
    registry = TTSVoiceRegistry(_cfg(tmp_path))
    resolved = registry.resolve_voice(None)
    assert resolved["id"] == "piper:voice"
    with pytest.raises(ProviderError) as excinfo:
        registry.resolve_voice("vp-001")
    assert excinfo.value.error_type == "tts_voice_not_found"


def test_atempo_chain_stays_in_supported_range():
    for rate in (0.25, 0.5, 0.9, 1.0, 1.4, 2.0, 3.0, 4.0):
        factors = atempo_chain(rate)
        assert factors
        product = 1.0
        for factor in factors:
            assert 0.5 <= factor <= 2.0
            product *= factor
        assert abs(product - rate) < 1e-6


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg/ffprobe required")
def test_piper_provider_applies_rate_and_volume_to_real_wav(tmp_path):
    cfg = _cfg(tmp_path, FFMPEG_BIN=shutil.which("ffmpeg"),
               FFPROBE_BIN=shutil.which("ffprobe"))
    provider = PiperTTSProvider(
        piper_bin=cfg.PIPER_BIN,
        piper_model_path=cfg.PIPER_MODEL_PATH,
        ffprobe_bin=cfg.FFPROBE_BIN,
        ffmpeg_bin=cfg.FFMPEG_BIN,
        registry=TTSVoiceRegistry(cfg),
    )
    output = str(tmp_path / "out.wav")
    result = provider.synthesize(
        "中文测试", "piper:voice", output,
        options={"speech_rate": 2.0, "volume": 0.8},
    )
    assert os.path.isfile(output)
    assert result["duration_s"] == pytest.approx(0.5, abs=0.15)
    assert result["voice_id"] == "piper:voice"
    assert result["speech_rate"] == 2.0
    with wave.open(output, "rb") as handle:
        assert handle.getframerate() == 48000
        assert handle.getnchannels() == 1


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg/ffprobe required")
def test_piper_provider_failure_keeps_no_fake_output(tmp_path):
    cfg = _cfg(tmp_path, FFMPEG_BIN=shutil.which("ffmpeg"),
               FFPROBE_BIN=shutil.which("ffprobe"))
    failing = _executable(str(tmp_path / "piper-fail"), "#!/bin/sh\nexit 9\n")
    cfg.PIPER_BIN = failing
    provider = PiperTTSProvider(
        piper_bin=failing,
        piper_model_path=cfg.PIPER_MODEL_PATH,
        ffprobe_bin=cfg.FFPROBE_BIN,
        ffmpeg_bin=cfg.FFMPEG_BIN,
        registry=TTSVoiceRegistry(cfg),
    )
    output = str(tmp_path / "failed.wav")
    with pytest.raises(ProviderError):
        provider.synthesize("中文测试", "piper:voice", output)
    assert not os.path.exists(output)
