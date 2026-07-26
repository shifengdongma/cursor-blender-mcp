# -*- coding: utf-8 -*-
"""
Piper TTS provider via subprocess.
"""
from __future__ import absolute_import

import json
import logging
import os
import subprocess
import tempfile
import time

from .base import BaseTTSProvider, ProviderError

logger = logging.getLogger(__name__)


class PiperTTSProvider(BaseTTSProvider):
    """Piper TTS voice synthesis via subprocess pipe."""

    def __init__(self, piper_bin="piper", piper_model_path=None, ffprobe_bin="ffprobe"):
        self.piper_bin = piper_bin
        self.piper_model_path = piper_model_path
        self.ffprobe_bin = ffprobe_bin

    def _get_duration_ffprobe(self, file_path):
        """Get audio duration using ffprobe."""
        try:
            cmd = [
                self.ffprobe_bin, "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                file_path,
            ]
            result = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = result.communicate(timeout=30)
            if result.returncode != 0:
                return 0.0

            info = json.loads(stdout.decode("utf-8", errors="replace")) if stdout else {}
            duration = float(info.get("format", {}).get("duration", 0))
            return duration
        except Exception:
            return 0.0

    def synthesize(self, text, voice_id, output_path):
        """
        Synthesize text to speech using Piper TTS.

        Args:
            text: Text to synthesize
            voice_id: Voice/model identifier (used as model path override)
            output_path: Path to save the WAV file

        Returns:
            dict: {output_path, duration_s, format}
        """
        if not self.piper_bin:
            raise ProviderError("Piper binary path not configured", error_type="piper_not_configured")

        if not text or not text.strip():
            raise ProviderError("TTS input text is empty", error_type="piper_empty_text")

        model_path = voice_id or self.piper_model_path
        if not model_path:
            raise ProviderError("Piper model path not configured", error_type="piper_missing_model")

        if not os.path.exists(model_path):
            raise ProviderError(
                "Piper model not found: {0}".format(model_path),
                error_type="piper_model_not_found",
            )

        # Ensure output directory exists
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)

        cmd = [
            self.piper_bin,
            "--model", model_path,
            "--output_file", output_path,
        ]

        logger.info("Running Piper TTS: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate(
                input=text.encode("utf-8"),
                timeout=300,
            )

            if proc.returncode != 0:
                stderr_text = (stderr or b"").decode("utf-8", errors="replace")
                raise ProviderError(
                    "Piper TTS failed (exit {0}): {1}".format(proc.returncode, stderr_text[:500]),
                    error_type="piper_execution_error",
                )

        except subprocess.TimeoutExpired:
            proc.kill()
            raise ProviderError("Piper TTS timed out after 300s", error_type="piper_timeout")
        except FileNotFoundError:
            raise ProviderError(
                "Piper binary not found: {0}".format(self.piper_bin),
                error_type="piper_not_found",
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("Piper TTS error: {0}".format(str(e)), error_type="piper_unknown_error")

        duration_s = self._get_duration_ffprobe(output_path) if self.ffprobe_bin else 0.0

        return {
            "output_path": output_path,
            "duration_s": duration_s,
            "format": "wav",
        }
