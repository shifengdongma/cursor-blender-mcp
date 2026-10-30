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

from .http_utils import ApiError
from .media_filters import build_filter_parts

logger = logging.getLogger(__name__)


class MediaServiceError(RuntimeError):
    """Custom error for media service operations."""
    pass


def probe_media_file(ffprobe_bin, file_path, timeout_s=30):
    """Probe a local file and return normalised stream/format information.

    Raises MediaServiceError when ffprobe is unavailable or the file cannot be
    decoded, so callers never treat an unverified upload as valid media.
    """
    if not ffprobe_bin:
        raise MediaServiceError("FFprobe 未配置")
    if not os.path.isfile(file_path):
        raise MediaServiceError("文件不存在")
    cmd = [
        ffprobe_bin, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", file_path,
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except FileNotFoundError:
        raise MediaServiceError("FFprobe 不可用")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise MediaServiceError("媒体探测超时")
    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", errors="replace")[:500]
        raise MediaServiceError("媒体文件无法解码: {0}".format(detail))
    try:
        info = json.loads(stdout.decode("utf-8", errors="replace")) if stdout else {}
    except ValueError:
        raise MediaServiceError("FFprobe 返回了无效结果")
    streams = info.get("streams") or []
    audio = next(
        (item for item in streams if item.get("codec_type") == "audio"), None
    )
    video = next(
        (item for item in streams if item.get("codec_type") == "video"), None
    )
    fmt = info.get("format") or {}
    try:
        duration_s = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration_s = 0.0
    if not audio and not video:
        raise MediaServiceError("文件不包含可识别的音频或视频流")
    return {
        "duration_s": duration_s,
        "format_name": fmt.get("format_name"),
        "size": int(fmt.get("size") or 0),
        "bit_rate": fmt.get("bit_rate"),
        "has_audio": bool(audio),
        "has_video": bool(video),
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
            "channel_layout": audio.get("channel_layout"),
            "bit_rate": audio.get("bit_rate"),
        } if audio else None,
        "video": {
            "codec": video.get("codec_name"),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "fps": video.get("r_frame_rate"),
        } if video else None,
    }


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

    # ── Timeline composition ──

    @staticmethod
    def _escape_filter_path(path):
        value = str(path)
        for char in ("\\", ":", "'", "[", "]", ",", ";"):
            value = value.replace(char, "\\" + char)
        return value

    @staticmethod
    def _clips_by_role(timeline, role):
        found = []
        for item in timeline.get("tracks") or []:
            track = item.get("track") or {}
            item_role = track.get("role")
            if not item_role:
                if track.get("track_type") == "video":
                    item_role = "video"
                elif track.get("track_type") == "subtitle":
                    item_role = "subtitle"
            if item_role != role:
                continue
            for clip in item.get("clips") or []:
                if clip.get("muted"):
                    continue
                found.append(clip)
        return sorted(found, key=lambda clip: float(clip.get("start_time") or 0))

    def probe(self, file_path):
        info = probe_media_file(self.ffprobe_bin, file_path)
        return info

    def verify_output(self, output_path, expected, require_audio=True,
                      min_bytes=4096, timeout_s=300):
        if not os.path.isfile(output_path):
            raise MediaServiceError("合成输出文件不存在")
        size = os.path.getsize(output_path)
        if size < int(min_bytes):
            raise MediaServiceError("合成输出文件过小：{0} 字节".format(size))
        info = probe_media_file(self.ffprobe_bin, output_path)
        if not info.get("has_video"):
            raise MediaServiceError("合成输出缺少视频轨")
        if require_audio and not info.get("has_audio"):
            raise MediaServiceError("合成输出缺少音频轨")
        video = info.get("video") or {}
        if int(video.get("width") or 0) != int(expected.get("width")):
            raise MediaServiceError(
                "输出宽度不正确：{0}".format(video.get("width"))
            )
        if int(video.get("height") or 0) != int(expected.get("height")):
            raise MediaServiceError(
                "输出高度不正确：{0}".format(video.get("height"))
            )
        if expected.get("fps"):
            try:
                numerator, denominator = str(video.get("fps") or "0/1").split("/")
                actual_fps = float(numerator) / float(denominator or 1)
            except (TypeError, ValueError, ZeroDivisionError):
                actual_fps = 0.0
            if abs(actual_fps - float(expected["fps"])) > 0.1:
                raise MediaServiceError(
                    "输出帧率不正确：{0}".format(video.get("fps"))
                )
        expected_duration = float(expected.get("duration_s") or 0)
        if expected_duration and abs(float(info.get("duration_s") or 0) - expected_duration) > 0.75:
            raise MediaServiceError(
                "输出时长不正确：{0:.2f}s（期望 {1:.2f}s）".format(
                    float(info.get("duration_s") or 0), expected_duration
                )
            )
        # A successful container probe is not enough: decode every frame.
        cmd = [
            self.ffmpeg_bin, "-v", "error", "-xerror",
            "-i", output_path, "-f", "null", "-",
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            _stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise MediaServiceError("合成结果解码校验超时")
        if proc.returncode != 0:
            detail = (stderr or b"").decode("utf-8", errors="replace")[:500]
            raise MediaServiceError("合成结果无法完整解码：{0}".format(detail))
        return info

    def compose_timeline(self, timeline, output_path, export_settings=None,
                         inputs=None, progress_cb=None):
        """Compose a validated timeline into one MP4 with real audio/subtitles.

        ``inputs`` maps asset_id to ``{path, has_audio, duration_s}``.  The
        worker resolves those paths through AssetService, so this service never
        receives user-controlled paths directly.
        """
        settings = dict(export_settings or {})
        width = int(settings.get("width") or 1920)
        height = int(settings.get("height") or 1080)
        fps = int(settings.get("fps") or 24)
        if width not in (1280, 1920) or height not in (720, 1080):
            raise MediaServiceError("只支持 720p/1080p 输出")
        if fps not in (24, 25, 30):
            raise MediaServiceError("只支持 24/25/30 FPS 输出")
        if width * height not in (1280 * 720, 1920 * 1080):
            raise MediaServiceError("输出分辨率组合无效")
        if (width, height) not in ((1280, 720), (1920, 1080)):
            raise MediaServiceError("输出分辨率组合无效")
        crf = int(settings.get("crf") or 20)
        if not 16 <= crf <= 28:
            raise MediaServiceError("CRF 需在 16–28 之间")
        audio_bitrate = str(settings.get("audio_bitrate") or "192k")
        if audio_bitrate not in ("128k", "192k", "256k", "320k"):
            raise MediaServiceError("不支持的音频码率")
        subtitle_mode = settings.get("subtitle_mode") or "none"
        if subtitle_mode not in ("none", "mov_text", "burn"):
            raise MediaServiceError("不支持的字幕模式")
        keep_source_audio = bool(settings.get("keep_source_audio", False))
        music_ducking = bool(settings.get("music_ducking", False))
        loudness_normalize = bool(settings.get("loudness_normalize", True))
        subtitle_path = settings.get("subtitle_path")
        if subtitle_mode in ("burn", "mov_text") and not subtitle_path:
            raise MediaServiceError("字幕模式需要字幕文件")
        if subtitle_mode == "burn" and not os.path.isfile(subtitle_path):
            raise MediaServiceError("字幕文件不存在")

        inputs = inputs or {}
        input_args = []
        filter_parts = []
        video_labels = []
        audio_labels = []
        narration_labels = []
        music_labels = []
        other_audio_labels = []
        source_inputs = []  # (input_index, clip, path_info)
        audio_inputs = []   # (input_index, clip, role, path_info)
        subtitle_input_index = None
        total_video_duration = 0.0

        def add_file_input(path, loop=False):
            index = sum(1 for arg in input_args if arg == "-i")
            if loop:
                input_args.extend(["-stream_loop", "-1", "-i", path])
            else:
                input_args.extend(["-i", path])
            return index

        def add_lavfi_input(source, duration=None):
            index = sum(1 for arg in input_args if arg == "-i")
            args = ["-f", "lavfi"]
            if duration is not None:
                args.extend(["-t", "{0:.4f}".format(duration)])
            args.extend(["-i", source])
            input_args.extend(args)
            return index

        video_clips = self._clips_by_role(timeline, "video")
        if not video_clips:
            raise MediaServiceError("时间线没有视频片段")
        if len(video_clips) + sum(
            len(self._clips_by_role(timeline, role))
            for role in ("narration", "music", "sfx")
        ) > int(settings.get("max_inputs") or 200):
            raise MediaServiceError("时间线输入片段超过限制")

        cursor_time = 0.0
        segment_index = 0
        for clip in video_clips:
            start = float(clip.get("start_time") or 0)
            duration = float(clip.get("duration_s") or 0)
            if duration <= 0:
                raise MediaServiceError("视频片段时长无效")
            if start < cursor_time - 0.01:
                raise MediaServiceError("视频片段重叠")
            asset_id = clip.get("asset_id")
            info = inputs.get(asset_id)
            if not info or not os.path.isfile(str(info.get("path") or "")):
                raise MediaServiceError("视频素材缺失：{0}".format(asset_id))
            if start > cursor_time + 0.001:
                gap = start - cursor_time
                gap_index = add_lavfi_input(
                    "color=c=black:s={0}x{1}:r={2}".format(width, height, fps),
                    duration=gap,
                )
                filter_parts.append(
                    "[{0}:v]setsar=1,fps={2},format=yuv420p[v{1}]".format(
                        gap_index, segment_index, fps
                    )
                )
                video_labels.append("[v{0}]".format(segment_index))
                segment_index += 1
            index = add_file_input(info["path"])
            trim_in = float(clip.get("trim_in") or 0)
            filter_parts.append(
                "[{0}:v]trim=start={1:.4f}:duration={2:.4f},"
                "setpts=PTS-STARTPTS,"
                "scale={3}:{4}:force_original_aspect_ratio=decrease,"
                "pad={3}:{4}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={5},"
                "format=yuv420p[v{6}]".format(
                    index, trim_in, duration, width, height, fps, segment_index
                )
            )
            video_labels.append("[v{0}]".format(segment_index))
            segment_index += 1
            if keep_source_audio and clip.get("source_audio_enabled", True) and info.get("has_audio"):
                source_inputs.append((index, clip, info))
            total_video_duration = start + duration
            cursor_time = total_video_duration

        if not video_labels:
            raise MediaServiceError("时间线没有可合成的视频片段")
        if len(video_labels) == 1:
            filter_parts.append("{}null[vcat]".format(video_labels[0]))
        else:
            filter_parts.append(
                "{}concat=n={}:v=1:a=0[vcat]".format(
                    "".join(video_labels), len(video_labels)
                )
            )

        if subtitle_mode == "burn":
            font_name = str(settings.get("subtitle_font_name") or "Noto Sans CJK SC")
            font_size = int(settings.get("subtitle_font_size") or 24)
            escaped = self._escape_filter_path(subtitle_path)
            filter_parts.append(
                "[vcat]subtitles=filename='{0}':force_style='FontName={1},FontSize={2}'[vout]".format(
                    escaped, font_name.replace("'", ""), font_size
                )
            )
        else:
            filter_parts.append("[vcat]null[vout]")

        for input_index, clip, info in source_inputs:
            label = "src{0}".format(len(audio_labels))
            start = float(clip.get("start_time") or 0)
            duration = float(clip.get("duration_s") or 0)
            trim_in = float(clip.get("trim_in") or 0)
            volume = float(clip.get("volume") if clip.get("volume") is not None else 1.0)
            filter_parts.append(
                "[{0}:a]atrim=start={1:.4f}:duration={2:.4f},"
                "asetpts=PTS-STARTPTS,aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                "volume={3:.4f},adelay={4}|{4}[{5}]".format(
                    input_index, trim_in, duration, volume,
                    int(round(start * 1000)), label
                )
            )
            audio_labels.append(label)
            other_audio_labels.append(label)

        for role in ("narration", "music", "sfx"):
            for clip in self._clips_by_role(timeline, role):
                asset_id = clip.get("asset_id")
                info = inputs.get(asset_id)
                if not info or not os.path.isfile(str(info.get("path") or "")):
                    raise MediaServiceError(
                        "{0} 音频素材缺失：{1}".format(role, asset_id)
                    )
                if not info.get("has_audio"):
                    raise MediaServiceError("音频素材没有音频流：{0}".format(asset_id))
                loop = role == "music" and bool((clip.get("properties") or {}).get("loop"))
                input_index = add_file_input(info["path"], loop=loop)
                label = "af{0}".format(len(audio_labels))
                start = float(clip.get("start_time") or 0)
                duration = float(clip.get("duration_s") or 0)
                trim_in = float(clip.get("trim_in") or 0)
                volume = float(clip.get("volume") if clip.get("volume") is not None else 1.0)
                fade_in = float(clip.get("fade_in") or 0)
                fade_out = float(clip.get("fade_out") or 0)
                parts = [
                    "[{0}:a]atrim=start={1:.4f}:duration={2:.4f}".format(
                        input_index, trim_in, duration
                    ),
                    "asetpts=PTS-STARTPTS",
                    "aresample=48000",
                    "aformat=sample_fmts=fltp:channel_layouts=stereo",
                    "volume={0:.4f}".format(volume),
                ]
                if fade_in > 0:
                    parts.append("afade=t=in:st=0:d={0:.4f}".format(min(fade_in, duration)))
                if fade_out > 0:
                    parts.append(
                        "afade=t=out:st={0:.4f}:d={1:.4f}".format(
                            max(0.0, duration - fade_out), min(fade_out, duration)
                        )
                    )
                parts.append("adelay={0}|{0}[{1}]".format(int(round(start * 1000)), label))
                filter_parts.append(",".join(parts))
                audio_labels.append(label)
                if role == "narration":
                    narration_labels.append(label)
                elif role == "music":
                    music_labels.append(label)
                else:
                    other_audio_labels.append(label)

        if not audio_labels:
            silence_index = add_lavfi_input(
                "anullsrc=r=48000:cl=stereo", duration=total_video_duration
            )
            filter_parts.append("[{0}:a]anull[asilence]".format(silence_index))
            audio_labels = ["asilence"]
            other_audio_labels = ["asilence"]

        def mix_labels(labels, output_label):
            if len(labels) == 1:
                filter_parts.append("[{0}]anull[{1}]".format(labels[0], output_label))
            else:
                filter_parts.append(
                    "{0}amix=inputs={1}:duration=longest:normalize=0[{2}]".format(
                        "".join("[{0}]".format(label) for label in labels),
                        len(labels), output_label,
                    )
                )
            return "[{0}]".format(output_label)

        if music_ducking and narration_labels and music_labels:
            narration_mix = mix_labels(narration_labels, "narrmix")
            music_mix = mix_labels(music_labels, "musicmix")
            # The sidechain input is not audible by itself.  Split narration so
            # one copy controls the compressor and the other stays in the mix.
            filter_parts.append("{0}asplit=2[narrside][narrmixout]".format(narration_mix))
            filter_parts.append(
                "{0}[narrside]sidechaincompress=threshold=0.05:ratio=4:attack=20:release=300[musicduck]".format(
                    music_mix
                )
            )
            final_labels = other_audio_labels + ["narrmixout", "musicduck"]
        else:
            final_labels = audio_labels

        if len(final_labels) == 1:
            filter_parts.append("[{0}]anull[amix]".format(final_labels[0]))
        else:
            filter_parts.append(
                "{0}amix=inputs={1}:duration=longest:normalize=0[amix]".format(
                    "".join("[{0}]".format(label) for label in final_labels),
                    len(final_labels),
                )
            )
        post_filters = []
        if loudness_normalize:
            post_filters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
        post_filters.append("alimiter=limit=0.95")
        filter_parts.append(
            "[amix]{0}[aout]".format(",".join(post_filters))
        )

        if subtitle_mode == "mov_text":
            subtitle_input_index = add_file_input(subtitle_path)

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        part_path = output_path + ".part.mp4"
        if os.path.exists(part_path):
            os.remove(part_path)

        args = list(input_args)
        args.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[vout]", "-map", "[aout]",
        ])
        if subtitle_mode == "mov_text":
            args.extend([
                "-map", "{0}:s".format(subtitle_input_index),
                "-c:s", "mov_text",
            ])
        args.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            "-t", "{0:.4f}".format(total_video_duration),
            part_path,
        ])
        if progress_cb:
            progress_cb(10)
        try:
            self._run_ffmpeg(args, timeout_s=int(settings.get("timeout_s") or 1800))
        except Exception:
            if os.path.exists(part_path):
                os.remove(part_path)
            raise
        os.replace(part_path, output_path)
        if progress_cb:
            progress_cb(85)
        max_output_bytes = int(settings.get("max_output_mb") or 1500) * 1024 * 1024
        if os.path.getsize(output_path) > max_output_bytes:
            raise MediaServiceError("合成输出超过大小限制")
        media_info = self.verify_output(
            output_path,
            {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_s": total_video_duration,
            },
            require_audio=True,
            min_bytes=int(settings.get("min_output_bytes") or 4096),
            timeout_s=int(settings.get("verify_timeout_s") or 600),
        )
        if progress_cb:
            progress_cb(100)
        return {
            "output_path": output_path,
            "duration_s": float(media_info.get("duration_s") or total_video_duration),
            "media_info": media_info,
            "timeline_version": timeline.get("timeline_version"),
            "width": width,
            "height": height,
            "fps": fps,
            "subtitle_mode": subtitle_mode,
        }

    def compose_video(self, clip_specs, output_path, width=1920, height=1080, fps=24):
        """
        Compose multiple video clips into a single video.

        clip_specs: list of dicts with {file_path, duration_s, trim_in}.
        """
        if not clip_specs:
            raise MediaServiceError("No clips provided for composition")

        # Write concat file. Reject paths that could break the concat syntax.
        concat_file = os.path.join(self.work_dir, "{0}_concat.txt".format(str(uuid.uuid4())[:8]))
        with open(concat_file, "w") as f:
            for spec in clip_specs:
                raw_path = str(spec["file_path"])
                if "://" in raw_path or raw_path.startswith("data:"):
                    raise MediaServiceError("Remote media URLs are not allowed in composition")
                path = os.path.abspath(raw_path)
                if any(ch in path for ch in ("'", "\n", "\r")):
                    raise MediaServiceError("Unsafe media path in composition")
                f.write("file '{0}'\n".format(path))

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
                    raw_path = str(af)
                    if "://" in raw_path or raw_path.startswith("data:"):
                        raise MediaServiceError("Remote audio URLs are not allowed")
                    path = os.path.abspath(raw_path)
                    if any(ch in path for ch in ("'", "\n", "\r")):
                        raise MediaServiceError("Unsafe audio path")
                    f.write("file '{0}'\n".format(path))

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
        """Apply a whitelisted, range-checked filter chain to a real video."""
        try:
            vf_parts = build_filter_parts(filters)
        except ApiError as exc:
            raise MediaServiceError(exc.message)
        if not vf_parts:
            raise MediaServiceError("没有可应用的有效滤镜")
        if not os.path.isfile(input_path):
            raise MediaServiceError("精修输入文件不存在")
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        part_path = output_path + ".part.mp4"
        if os.path.exists(part_path):
            os.remove(part_path)
        args = [
            "-i", input_path,
            "-vf", ",".join(vf_parts),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            "-movflags", "+faststart",
            part_path,
        ]
        try:
            self._run_ffmpeg(args)
        except Exception:
            if os.path.exists(part_path):
                os.remove(part_path)
            raise
        os.replace(part_path, output_path)

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
