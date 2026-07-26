# -*- coding: utf-8 -*-
"""Tests for MediaService (with mocked subprocess)."""
from __future__ import absolute_import

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from backend.media_service import MediaService, MediaServiceError


class TestMediaService(object):

    def make_svc(self):
        return MediaService(ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe")

    def test_get_media_info(self):
        svc = self.make_svc()
        with patch.object(svc, "_run_ffprobe") as mock_probe, \
             patch("os.path.exists", return_value=True):
            mock_probe.return_value = {
                "format": {"duration": "10.5", "bit_rate": "1000000"},
                "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
            }
            info = svc.get_media_info("/path/to/video.mp4")
            assert info["format"]["duration"] == "10.5"

    def test_get_media_info_file_not_found(self):
        svc = self.make_svc()
        with pytest.raises(MediaServiceError):
            svc.get_media_info("/nonexistent/file.mp4")

    def test_transcode(self):
        svc = self.make_svc()
        with patch.object(svc, "_run_ffmpeg") as mock_run:
            svc.transcode("input.mp4", "output.mp4", crf=18, width=1280, height=720)
            args = mock_run.call_args[0][0]
            # Check key args are present
            arg_str = " ".join(args)
            assert "-i" in arg_str
            assert "1280" in arg_str
            assert "720" in arg_str

    def test_compose_video(self):
        svc = self.make_svc()
        with patch.object(svc, "_run_ffmpeg") as mock_run:
            clips = [
                {"file_path": "/tmp/clip1.mp4", "duration_s": 5},
                {"file_path": "/tmp/clip2.mp4", "duration_s": 8},
            ]
            svc.compose_video(clips, "output.mp4", width=1920, height=1080, fps=24)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "-f" in args and "concat" in args

    def test_compose_no_clips(self):
        svc = self.make_svc()
        with pytest.raises(MediaServiceError):
            svc.compose_video([], "output.mp4")

    def test_mix_audio_concat(self):
        svc = self.make_svc()
        with patch.object(svc, "_run_ffmpeg") as mock_run:
            svc.mix_audio(["/tmp/a1.wav", "/tmp/a2.wav"], "output.wav", mix_mode="concat")
            mock_run.assert_called_once()

    def test_mix_audio_no_files(self):
        svc = self.make_svc()
        with pytest.raises(MediaServiceError):
            svc.mix_audio([], "output.wav")

    def test_apply_filter_chain_color(self):
        svc = self.make_svc()
        with patch.object(svc, "_run_ffmpeg") as mock_run:
            svc.apply_filter_chain("input.mp4", "output.mp4", {
                "brightness": 0.1,
                "contrast": 0.2,
                "saturation": 1.2,
            })
            args = mock_run.call_args[0][0]
            arg_str = " ".join(args)
            assert "-vf" in arg_str
            assert "eq=" in arg_str

    def test_apply_filter_chain_no_filters(self):
        svc = self.make_svc()
        with patch("backend.media_service.shutil.copy2") as mock_copy:
            svc.apply_filter_chain("input.mp4", "output.mp4", {})
            mock_copy.assert_called_once()

    def test_create_zip_package(self):
        svc = self.make_svc()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            tmp_file = f.name

        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as zip_f:
                zip_path = zip_f.name

            svc.create_zip_package(
                [(tmp_file, "data.txt")],
                zip_path,
                manifest={"project": "test"},
            )

            assert os.path.exists(zip_path)
            assert os.path.getsize(zip_path) > 0

            os.unlink(zip_path)
        finally:
            if os.path.exists(tmp_file):
                os.unlink(tmp_file)

    def test_path_traversal_prevention(self):
        from backend.media_service import _safe_path
        base = "/safe/dir"

        # Normal path
        assert _safe_path(base, "file.txt") == os.path.realpath("/safe/dir/file.txt")

        # Path traversal attempt
        with pytest.raises(MediaServiceError):
            _safe_path(base, "../../etc/passwd")

    def test_subprocess_ffmpeg(self):
        svc = self.make_svc()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("subprocess.Popen", return_value=mock_proc):
            result = svc._run_ffmpeg(["-i", "test.mp4", "test_out.mp4"])
            assert result["returncode"] == 0

    def test_subprocess_ffmpeg_error(self):
        svc = self.make_svc()
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"Error occurred")

        with patch("subprocess.Popen", return_value=mock_proc):
            with pytest.raises(MediaServiceError):
                svc._run_ffmpeg(["-i", "test.mp4", "test_out.mp4"])
