# -*- coding: utf-8 -*-
"""Server-side TTS voice registry and capability reporting.

The browser only ever sees stable voice IDs and capabilities.  Real model
paths stay on the server and are confined to ``TTS_MODEL_DIR``.
"""
from __future__ import absolute_import

import json
import logging
import os
import shutil
import time

from .providers.base import ProviderError

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 10.0


def _binary_available(value):
    if not value:
        return False
    if os.path.sep in str(value):
        return os.path.isfile(value) and os.access(value, os.X_OK)
    return bool(shutil.which(str(value)))


def _real_path_inside(base_dir, candidate):
    base = os.path.realpath(base_dir)
    path = candidate
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    real = os.path.realpath(path)
    if real != base and not real.startswith(base + os.sep):
        return None
    return real


class TTSVoiceRegistry(object):
    """Load, validate and expose available TTS voices."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._cache = None
        self._cache_at = 0.0

    # ── Loading ──

    def _voices_file(self):
        explicit = getattr(self.cfg, "TTS_VOICES_FILE", None)
        if explicit:
            return explicit
        return os.path.join(self.cfg.DATA_DIR, "tts_voices.json")

    def _model_dir(self):
        explicit = getattr(self.cfg, "TTS_MODEL_DIR", None)
        if explicit:
            return explicit
        return os.path.join(self.cfg.DATA_DIR, "tts_models")

    def _load_entries(self):
        path = self._voices_file()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                entries = data.get("voices") if isinstance(data, dict) else None
                if isinstance(entries, list):
                    return entries
                logger.warning("TTS voice registry has no voices list: %s", path)
            except (OSError, ValueError) as exc:
                logger.warning("Could not read TTS voice registry %s: %s", path, exc)

        # Backwards-compatible fallback: a configured Piper model is a real,
        # installed voice even before an explicit registry file exists.
        legacy = getattr(self.cfg, "PIPER_MODEL_PATH", None)
        if legacy and os.path.isfile(legacy):
            name = os.path.splitext(os.path.basename(legacy))[0]
            return [{
                "id": "piper:{0}".format(name),
                "provider": "piper",
                "label": name,
                "description": "已配置的本地 Piper 音色",
                "language": "zh-CN",
                "model_path": os.path.abspath(legacy),
                "config_path": legacy + ".json" if os.path.isfile(legacy + ".json") else None,
                "enabled": True,
                "_legacy_voice": True,
            }]
        return []

    # ── Availability ──

    def _availability(self):
        piper_ok = _binary_available(getattr(self.cfg, "PIPER_BIN", "piper"))
        ffmpeg_ok = _binary_available(getattr(self.cfg, "FFMPEG_BIN", "ffmpeg"))
        ffprobe_ok = _binary_available(getattr(self.cfg, "FFPROBE_BIN", "ffprobe"))
        return piper_ok, ffmpeg_ok, ffprobe_ok

    def _evaluate(self, entry):
        if not isinstance(entry, dict):
            return None
        voice_id = str(entry.get("id") or "").strip()
        if not voice_id:
            return None
        provider = str(entry.get("provider") or "piper").strip()
        enabled = entry.get("enabled", True) is not False
        reasons = []
        if not enabled:
            reasons.append("音色已禁用")
        if provider != "piper":
            reasons.append("暂不支持该 TTS Provider")

        raw_model = entry.get("model_path")
        if entry.get("_legacy_voice") and raw_model:
            model_dir = os.path.dirname(os.path.abspath(str(raw_model)))
        else:
            model_dir = self._model_dir()
        model_path = None
        if not raw_model:
            reasons.append("未配置模型文件")
        else:
            model_path = _real_path_inside(model_dir, str(raw_model))
            if not model_path:
                reasons.append("模型路径不在允许的音色目录内")
            elif not os.path.isfile(model_path):
                reasons.append("模型文件不存在")

        config_path = None
        raw_config = entry.get("config_path")
        if raw_config:
            config_path = _real_path_inside(model_dir, str(raw_config))
            if not config_path:
                reasons.append("模型配置路径不在允许的音色目录内")
            elif not os.path.isfile(config_path):
                reasons.append("模型配置文件不存在")

        piper_ok, ffmpeg_ok, ffprobe_ok = self._availability()
        if not piper_ok:
            reasons.append("Piper 可执行文件不可用")
        if not ffprobe_ok:
            reasons.append("FFprobe 不可用，无法验证真实音频")
        if not ffmpeg_ok:
            reasons.append("FFmpeg 不可用，无法应用语速/音量后处理")

        available = not reasons
        return {
            "id": voice_id,
            "provider": provider,
            "label": entry.get("label") or voice_id,
            "description": entry.get("description") or "",
            "language": entry.get("language") or "zh-CN",
            "gender": entry.get("gender"),
            "quality": entry.get("quality"),
            "license": entry.get("license"),
            "available": available,
            "unavailable_reason": None if available else "；".join(reasons),
            "capabilities": {
                "speech_rate": {
                    "supported": ffmpeg_ok,
                    "native": False,
                    "postprocess": "ffmpeg-atempo" if ffmpeg_ok else None,
                    "min": 0.5,
                    "max": 2.0,
                },
                "volume": {
                    "supported": ffmpeg_ok,
                    "native": False,
                    "postprocess": "ffmpeg-volume" if ffmpeg_ok else None,
                    "min": 0.0,
                    "max": 2.0,
                },
                "text_max_length": int(getattr(self.cfg, "MAX_TTS_TEXT_LENGTH", 2000)),
                "output_format": "wav",
            },
            "_model_path": model_path,
            "_config_path": config_path,
        }

    def _entries(self):
        now = time.time()
        if self._cache is not None and now - self._cache_at < _CACHE_TTL_S:
            return self._cache
        evaluated = []
        seen = set()
        for entry in self._load_entries():
            voice = self._evaluate(entry)
            if not voice or voice["id"] in seen:
                continue
            seen.add(voice["id"])
            evaluated.append(voice)
        self._cache = evaluated
        self._cache_at = now
        return evaluated

    # ── Public API ──

    def list_voices(self):
        items = []
        for voice in self._entries():
            public = dict(voice)
            public.pop("_model_path", None)
            public.pop("_config_path", None)
            public.pop("_legacy_voice", None)
            items.append(public)
        return items

    def providers(self):
        piper_ok, _ffmpeg_ok, _ffprobe_ok = self._availability()
        return [{
            "id": "piper",
            "available": piper_ok,
            "configured": bool(getattr(self.cfg, "PIPER_MODEL_PATH", "")),
        }]

    def default_voice_id(self):
        configured = getattr(self.cfg, "TTS_DEFAULT_VOICE_ID", None)
        voices = self._entries()
        by_id = {voice["id"]: voice for voice in voices}
        if configured and configured in by_id and by_id[configured]["available"]:
            return configured
        for voice in voices:
            if voice["available"]:
                return voice["id"]
        return voices[0]["id"] if voices else None

    def resolve_voice(self, voice_id, require_available=True):
        voice_id = voice_id or self.default_voice_id()
        if not voice_id:
            raise ProviderError(
                "没有可用的 TTS 音色，请先安装 Piper 模型并配置音色注册表",
                error_type="tts_not_configured",
            )
        for voice in self._entries():
            if voice["id"] != voice_id:
                continue
            if require_available and not voice["available"]:
                raise ProviderError(
                    "音色不可用：{0}".format(voice["unavailable_reason"]),
                    error_type="tts_voice_unavailable",
                )
            return voice
        raise ProviderError(
            "未知的 TTS 音色：{0}".format(voice_id),
            error_type="tts_voice_not_found",
        )

    def capabilities(self, voice_id=None):
        voice = self.resolve_voice(voice_id, require_available=False)
        return voice["capabilities"]
