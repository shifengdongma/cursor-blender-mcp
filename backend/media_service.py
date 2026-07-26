# -*- coding: utf-8 -*-
"""
Media service: FFmpeg wrapper for video composition, transcoding, and filtering.
"""
from __future__ import absolute_import

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile

logger = logging.getLogger(__name__)


class MediaServiceError(RuntimeError):
    """Custom error for media service operations."""
    pass


def _safe_param(value):
    """Convert a value to a safe string parameter for FFmpeg."""
    return str(value)


def _safe_path(base_dir, user_path):
    """
    Ensure a user-supplied path is within the allowed base directory.
    Prevents path traversal attacks.
    """
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(os.path.join(base_dir, user_path))
    if not real_path.startswith(real_base + os.sep) and real_path != real_base:
        raise MediaServiceError("Path traversal detected: {0}".format(user_path))
    return real_path


class MediaService(object):
    """FFmpeg-based media processing service."""

    def __init__(self, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe", work_dir=None):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="aigv_media_")

    def _run_ffmpeg(self, args, timeout_s=300):
        """
        Run FFmpeg with given arguments.
        Uses parameter arrays (not shell strings) for safety.

        Args:
            args: List of string arguments (first being ffmpeg binary)
            timeout_s: Timeout in seconds

        Returns:
            dict: {returncode, stdout, stderr}
        """
        cmd = [self.ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error"] + args

        logger.info("Running ffmpeg: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate(timeout=timeout_s)

            if proc.returncode != 0:
                stderr_text = (stderr or b"").decode("utf-8", errors="replace")
                raise MediaServiceError(
                    "FFmpeg exited with code {0}: {1}".format(
                        proc.returncode, stderr_text[:500]
                    )
                )

            return {
                "returncode": proc.returncode,
                "stdout": (stdout or b"").decode("utf-8", errors="replace"),
                "stderr": (stderr or b"").decode("utf-8", errors="replace"),
            }
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise MediaServiceError("FFmpeg timed out after {0}s".format(timeout_s))
        except MediaServiceError:
            raise
        except Exception as e:
            raise MediaServiceError("FFmpeg execution error: {0}".format(str(e)))

    def _run_ffprobe(self, file_path, timeout_s=30):
        """Run ffprobe to get media info."""
        cmd = [
            self.ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = proc.communicate(timeout=timeout_s)

            if proc.returncode != 0:
                return {}

            return json.loads(stdout.decode("utf-8", errors="replace")) if stdout else {}
        except Exception as e:
            logger.warning("ffprobe failed: %s", str(e))
            return {}

    def get_media_info(self, file_path):
        """Get media file information."""
        if not os.path.exists(file_path):
            raise MediaServiceError("File not found: {0}".format(file_path))
        return self._run_ffprobe(file_path)

    def transcode(self, input_path, output_path, video_codec="libx264",
                  audio_codec="aac", crf=23, preset="medium",
                  width=None, height=None, fps=None, bitrate=None):
        """
        Transcode a video file.

        Args:
            input_path: Source video path
            output_path: Destination path
            video_codec: Video codec (default: libx264)
            audio_codec: Audio codec (default: aac)
            crf: Quality (0-51, lower=better, default: 23)
            preset: Encoding speed preset
            width: Optional output width
            height: Optional output height
            fps: Optional output frame rate
            bitrate: Optional video bitrate (e.g., "2M")
        """
        args = ["-i", input_path]

        if video_codec:
            args.extend(["-c:v", _safe_param(video_codec)])
        if audio_codec:
            args.extend(["-c:a", _safe_param(audio_codec)])
        if crf is not None:
            args.extend(["-crf", str(int(crf))])
        if preset:
            args.extend(["-preset", _safe_param(preset)])
        if width and height:
            args.extend(["-vf", "scale={0}:{1}".format(int(width), int(height))])
        if fps:
            args.extend(["-r", str(int(fps))])
        if bitrate:
            args.extend(["-b:v", _safe_param(bitrate)])

        args.append(output_path)
        self._run_ffmpeg(args)

    def compose_video(self, clip_specs, output_path, width=1920, height=1080, fps=24):
        """
        Compose multiple video clips into a single video.

        clip_specs: list of dicts with {file_path, duration_s, trim_in}.
        """
        if not clip_specs:
            raise MediaServiceError("No clips provided for composition")

        # Write concat file
        concat_file = os.path.join(self.work_dir, "{0}_concat.txt".format(str(uuid.uuid4())[:8]))
        with open(concat_file, "w") as f:
            for spec in clip_specs:
                f.write("file '{0}'\n".format(spec["file_path"]))

        args = [
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-vf", "scale={0}:{1},fps={2}".format(int(width), int(height), int(fps)),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-crf", "23",
            "-preset", "medium",
            output_path,
        ]

        self._run_ffmpeg(args)

        # Clean up concat file
        try:
            os.remove(concat_file)
        except OSError:
            pass

    def mix_audio(self, audio_files, output_path, mix_mode="concat"):
        """
        Mix or concatenate audio files.

        audio_files: list of audio file paths
        mix_mode: "concat" or "mix" (overlay)
        """
        if not audio_files:
            raise MediaServiceError("No audio files provided")

        if mix_mode == "concat":
            concat_file = os.path.join(self.work_dir, "{0}_audio.txt".format(str(uuid.uuid4())[:8]))
            with open(concat_file, "w") as f:
                for af in audio_files:
                    f.write("file '{0}'\n".format(af))

            args = [
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c:a", "aac",
                "-b:a", "192k",
                output_path,
            ]
            self._run_ffmpeg(args)

            try:
                os.remove(concat_file)
            except OSError:
                pass
        else:
            # Mix (overlay) all audio streams
            args = []
            for af in audio_files:
                args.extend(["-i", af])

            filter_str = ""
            for i in range(len(audio_files)):
                if i == 0:
                    filter_str += "[{0}:a]".format(i)
                else:
                    filter_str += "[{0}:a]".format(i)

            filter_str += "amix=inputs={0}:duration=longest[outa]".format(len(audio_files))
            args.extend(["-filter_complex", filter_str, "-map", "[outa]"])

            args.append(output_path)
            self._run_ffmpeg(args)

    def burn_subtitles(self, video_path, srt_path, output_path):
        """Burn subtitles from SRT file into video."""
        # Escape special characters in SRT path for FFmpeg
        escaped_srt = srt_path.replace("\\", "\\\\").replace(":", "\\:")

        args = [
            "-i", video_path,
            "-vf", "subtitles={0}".format(escaped_srt),
            "-c:v", "libx264",
            "-c:a", "copy",
            "-crf", "23",
            output_path,
        ]
        self._run_ffmpeg(args)

    def generate_thumbnail(self, video_path, output_path, time_offset=0.0, width=320, height=180):
        """Generate a thumbnail image from video."""
        args = [
            "-ss", str(float(time_offset)),
            "-i", video_path,
            "-vframes", "1",
            "-vf", "scale={0}:{1}".format(int(width), int(height)),
            output_path,
        ]
        self._run_ffmpeg(args)

    def apply_filter_chain(self, input_path, output_path, filters):
        """
        Apply a chain of video filters.

        filters: dict with filter parameters:
            - brightness: float (-1.0 to 1.0)
            - contrast: float (-2.0 to 2.0)
            - saturation: float (0.0 to 3.0)
            - gamma: float (0.1 to 10.0)
            - sharpen: float (0.0 to 5.0)
            - denoise: str ("weak", "medium", "strong")
            - crop: tuple (w, h, x, y)
            - scale: tuple (w, h)
            - fps: int
        """
        vf_parts = []

        # Color adjustments
        eq_parts = []
        if "brightness" in filters and filters["brightness"] is not None:
            eq_parts.append("brightness={0}".format(float(filters["brightness"])))
        if "contrast" in filters and filters["contrast"] is not None:
            eq_parts.append("contrast={0}".format(float(filters["contrast"])))
        if "saturation" in filters and filters["saturation"] is not None:
            eq_parts.append("saturation={0}".format(float(filters["saturation"])))
        if "gamma" in filters and filters["gamma"] is not None:
            eq_parts.append("gamma={0}".format(float(filters["gamma"])))
        if eq_parts:
            vf_parts.append("eq={0}".format(":".join(eq_parts)))

        # Sharpen
        if "sharpen" in filters and filters["sharpen"] is not None:
            sharpen_val = float(filters["sharpen"])
            if sharpen_val > 0:
                vf_parts.append("unsharp=5:5:{0}:5:5:0".format(sharpen_val))

        # Denoise
        if "denoise" in filters and filters["denoise"] is not None:
            denoise_map = {"weak": "hqdn3d=2:2:3:3", "medium": "hqdn3d=4:4:5:5", "strong": "hqdn3d=6:6:7:7"}
            denoise_filter = denoise_map.get(filters["denoise"])
            if denoise_filter:
                vf_parts.append(denoise_filter)

        # Crop
        if "crop" in filters and filters["crop"] is not None:
            c = filters["crop"]
            if isinstance(c, (list, tuple)) and len(c) == 4:
                vf_parts.append("crop={0}:{1}:{2}:{3}".format(int(c[0]), int(c[1]), int(c[2]), int(c[3])))

        # Scale
        if "scale" in filters and filters["scale"] is not None:
            s = filters["scale"]
            if isinstance(s, (list, tuple)) and len(s) == 2:
                vf_parts.append("scale={0}:{1}".format(int(s[0]), int(s[1])))

        # FPS
        if "fps" in filters and filters["fps"] is not None:
            vf_parts.append("fps={0}".format(int(filters["fps"])))

        if vf_parts:
            args = [
                "-i", input_path,
                "-vf", ",".join(vf_parts),
                "-c:v", "libx264",
                "-c:a", "copy",
                "-crf", "23",
                output_path,
            ]
            self._run_ffmpeg(args)
        else:
            # No filters, just copy
            shutil.copy2(input_path, output_path)

    def create_zip_package(self, files, output_path, manifest=None):
        """
        Create a ZIP package containing the specified files.

        Args:
            files: list of (file_path, arcname) tuples
            output_path: Path for the output ZIP
            manifest: Optional manifest dict to include as manifest.json
        """
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path, arcname in files:
                if os.path.exists(file_path):
                    zf.write(file_path, arcname)

            if manifest:
                manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
                zf.writestr("manifest.json", manifest_json)


# Singleton
_media_service = None


def get_media_service(ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe"):
    global _media_service
    if _media_service is None:
        _media_service = MediaService(ffmpeg_bin=ffmpeg_bin, ffprobe_bin=ffprobe_bin)
    return _media_service
