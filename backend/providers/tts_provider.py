# -*- coding: utf-8 -*-
"""Piper TTS provider with verified audio post-processing."""
from __future__ import absolute_import

import json
import logging
import math
import os
import shutil
import subprocess

from .base import BaseTTSProvider, ProviderError

logger = logging.getLogger(__name__)


def atempo_chain(rate):
    """Split a playback rate into FFmpeg ``atempo`` factors (0.5–2.0 each)."""
    try:
        value = float(rate)
    except (TypeError, ValueError):
        raise ProviderError("语速必须是数字", error_type="unsupported_tts_option")
    if not math.isfinite(value) or value <= 0:
        raise ProviderError("语速必须大于 0", error_type="unsupported_tts_option")
    if abs(value - 1.0) < 1e-9:
        return [1.0]
    factors = []
    while value > 2.0 + 1e-9:
        factors.append(2.0)
        value /= 2.0
    while value < 0.5 - 1e-9:
        factors.append(0.5)
        value /= 0.5
    factors.append(round(value, 6))
    return factors


def _normalise_options(options):
    options = options or {}
    if not isinstance(options, dict):
        raise ProviderError("TTS 选项必须是对象", error_type="unsupported_tts_option")
    unknown = set(options) - {"speech_rate", "volume"}
    if unknown:
        raise ProviderError(
            "不支持的 TTS 参数：{0}".format(", ".join(sorted(unknown))),
            error_type="unsupported_tts_option",
        )
    try:
        rate = float(options.get("speech_rate", 1.0))
        volume = float(options.get("volume", 1.0))
    except (TypeError, ValueError):
        raise ProviderError("语速/音量必须是数字", error_type="unsupported_tts_option")
    if not math.isfinite(rate) or not 0.5 <= rate <= 2.0:
        raise ProviderError("语速需在 0.5–2.0 之间", error_type="unsupported_tts_option")
    if not math.isfinite(volume) or not 0.0 <= volume <= 2.0:
        raise ProviderError("音量需在 0.0–2.0 之间", error_type="unsupported_tts_option")
    return {"speech_rate": rate, "volume": volume}


class PiperTTSProvider(BaseTTSProvider):
    """Piper TTS voice synthesis via subprocess pipe."""

    provider_id = "piper"

    def __init__(self, piper_bin="piper", piper_model_path=None,
                 ffprobe_bin="ffprobe", ffmpeg_bin="ffmpeg", registry=None):
        self.piper_bin = piper_bin
        self.piper_model_path = piper_model_path
        self.ffprobe_bin = ffprobe_bin
        self.ffmpeg_bin = ffmpeg_bin
        self.registry = registry

    # ── Capabilities ──

    def list_voices(self):
        if self.registry is None:
            return []
        return self.registry.list_voices()

    def get_capabilities(self, voice_id=None):
        if self.registry is not None:
            return self.registry.capabilities(voice_id)
        return {
            "speech_rate": {
                "supported": bool(self.ffmpeg_bin),
                "native": False,
                "postprocess": "ffmpeg-atempo" if self.ffmpeg_bin else None,
                "min": 0.5,
                "max": 2.0,
            },
            "volume": {
                "supported": bool(self.ffmpeg_bin),
                "native": False,
                "postprocess": "ffmpeg-volume" if self.ffmpeg_bin else None,
                "min": 0.0,
                "max": 2.0,
            },
        }

    # ── Voice/model resolution ──

    def _resolve_model(self, voice_id):
        if self.registry is not None:
            voice = self.registry.resolve_voice(voice_id)
            return voice.get("_model_path"), voice
        if not self.piper_model_path:
            raise ProviderError(
                "Piper model path not configured", error_type="piper_missing_model"
            )
        if voice_id and voice_id != self.piper_model_path:
            raise ProviderError(
                "未知的 TTS 音色：{0}".format(voice_id),
                error_type="tts_voice_not_found",
            )
        return self.piper_model_path, {"id": None, "label": None}

    # ── Probing ──

    def _probe(self, file_path):
        if not self.ffprobe_bin:
            return {}
        cmd = [
            self.ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path,
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, _stderr = proc.communicate(timeout=30)
            if proc.returncode != 0:
                return {}
            return json.loads(stdout.decode("utf-8", errors="replace")) if stdout else {}
        except Exception as exc:
            logger.warning("ffprobe failed for %s: %s", file_path, exc)
            return {}

    def _audio_info(self, file_path):
        if not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
            raise ProviderError(
                "Piper 未生成音频文件", error_type="tts_empty_output"
            )
        info = self._probe(file_path)
        streams = info.get("streams") or []
        audio = next(
            (item for item in streams if item.get("codec_type") == "audio"), None
        )
        if not audio:
            raise ProviderError(
                "TTS 输出没有音频流", error_type="tts_invalid_audio"
            )
        try:
            duration = float((info.get("format") or {}).get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0:
            raise ProviderError(
                "TTS 输出音频时长无效", error_type="tts_invalid_audio"
            )
        return {
            "duration_s": duration,
            "codec": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
        }

    # ── Synthesis ──

    def synthesize(self, text, voice_id, output_path, options=None):
        """Synthesize text and post-process it into a verified WAV file."""
        if not self.piper_bin:
            raise ProviderError(
                "Piper binary path not configured",
                error_type="piper_not_configured",
            )
        if not text or not text.strip():
            raise ProviderError("TTS input text is empty", error_type="piper_empty_text")
        options = _normalise_options(options)

        model_path, voice = self._resolve_model(voice_id)
        if not model_path or not os.path.isfile(model_path):
            raise ProviderError(
                "Piper 模型文件不存在", error_type="piper_model_not_found"
            )

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        raw_path = output_path + ".raw.wav"
        for path in (raw_path, output_path):
            if os.path.exists(path):
                os.remove(path)

        cmd = [
            self.piper_bin,
            "--model", model_path,
            "--output_file", raw_path,
        ]
        logger.info("Running Piper TTS with voice %s", voice.get("id"))
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _stdout, stderr = proc.communicate(input=text.encode("utf-8"), timeout=300)
            if proc.returncode != 0:
                stderr_text = (stderr or b"").decode("utf-8", errors="replace")
                raise ProviderError(
                    "Piper TTS failed (exit {0}): {1}".format(
                        proc.returncode, stderr_text[:500]
                    ),
                    error_type="piper_execution_error",
                )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise ProviderError("Piper TTS timed out after 300s", error_type="piper_timeout")
        except FileNotFoundError:
            raise ProviderError(
                "Piper binary not found", error_type="piper_not_found"
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Piper TTS error: {0}".format(str(exc)),
                error_type="piper_unknown_error",
            )

        try:
            raw_info = self._audio_info(raw_path)
            rate = options["speech_rate"]
            volume = options["volume"]
            ffmpeg_ok = bool(self.ffmpeg_bin and shutil.which(self.ffmpeg_bin))
            if not ffmpeg_ok:
                if abs(rate - 1.0) > 1e-9 or abs(volume - 1.0) > 1e-9:
                    raise ProviderError(
                        "FFmpeg 不可用，无法应用语速或音量设置",
                        error_type="tts_postprocess_unavailable",
                    )
                os.replace(raw_path, output_path)
            else:
                filters = []
                for factor in atempo_chain(rate):
                    filters.append("atempo={0:.6f}".format(factor))
                if abs(volume - 1.0) > 1e-9:
                    filters.append("volume={0:.4f}".format(volume))
                args = [
                    self.ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", raw_path,
                ]
                if filters:
                    args.extend(["-af", ",".join(filters)])
                args.extend([
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                    output_path,
                ])
                result = subprocess.run(
                    args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300
                )
                if result.returncode != 0:
                    stderr_text = (result.stderr or b"").decode(
                        "utf-8", errors="replace"
                    )
                    raise ProviderError(
                        "TTS 音频后处理失败: {0}".format(stderr_text[:500]),
                        error_type="tts_postprocess_failed",
                    )
                os.remove(raw_path)
            info = self._audio_info(output_path)
            duration = info["duration_s"]
            if not (duration > 0):
                raise ProviderError(
                    "TTS 输出音频时长无效", error_type="tts_invalid_audio"
                )
            return {
                "output_path": output_path,
                "duration_s": duration,
                "format": "wav",
                "provider": "piper",
                "voice_id": voice.get("id"),
                "voice_label": voice.get("label"),
                "speech_rate": rate,
                "volume": volume,
                "media_info": info,
                "raw_duration_s": raw_info["duration_s"],
            }
        except Exception:
            for path in (raw_path, output_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            raise
