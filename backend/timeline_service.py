# -*- coding: utf-8 -*-
"""Timeline persistence, auto-initialization and FFmpeg-ready validation."""
from __future__ import absolute_import

import json
import logging
import math
import os
import time

from .access import can_read_asset
from .asset_service import get_asset_service
from .database import get_database
from .http_utils import ApiError
from .media_service import get_media_service, probe_media_file
from .models import (
    CreativeProject, ShotMediaVersion, StoryboardShot, TimelineClip, TimelineTrack,
)
from .storyboard_service import get_storyboard_service

logger = logging.getLogger(__name__)

MAX_TRACKS = 20
MAX_CLIPS = 2000
MAX_START_S = 86400.0
MAX_CLIP_DURATION_S = 3600.0
MAX_SUBTITLE_CHARS = 2000


def _now():
    return int(time.time())


def _finite(value, field, minimum=None, maximum=None, default=None):
    if value is None:
        value = default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(
            "invalid_timeline", "{0} 必须是数字".format(field), status_code=400
        )
    if not math.isfinite(number):
        raise ApiError("invalid_timeline", "{0} 必须是有限数字".format(field), status_code=400)
    if minimum is not None and number < minimum:
        raise ApiError(
            "invalid_timeline",
            "{0} 不能小于 {1}".format(field, minimum),
            status_code=400,
        )
    if maximum is not None and number > maximum:
        raise ApiError(
            "invalid_timeline",
            "{0} 不能大于 {1}".format(field, maximum),
            status_code=400,
        )
    return number


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ApiError("invalid_timeline", "布尔字段类型错误", status_code=400)


def srt_timestamp(seconds):
    millis = int(round(max(0.0, float(seconds)) * 1000))
    hours, remainder = divmod(millis, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole_seconds, millis = divmod(remainder, 1000)
    return "{0:02d}:{1:02d}:{2:02d},{3:03d}".format(
        hours, minutes, whole_seconds, millis
    )


class TimelineService(object):
    """Read/save the one editable timeline belonging to a creative project."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.data_dir = cfg.DATA_DIR
        self.db = get_database()
        self.asset_service = get_asset_service(cfg.DATA_DIR)
        self.storyboard_service = get_storyboard_service(cfg.DATA_DIR)
        self.media_service = get_media_service(cfg.FFMPEG_BIN, cfg.FFPROBE_BIN)

    # ── Reading ──

    def _raw_tracks(self, project_id):
        rows = self.db.fetch_all(
            "SELECT * FROM timeline_tracks WHERE creative_project_id = ? "
            "ORDER BY sequence_no ASC, created_at ASC",
            (project_id,),
        )
        tracks = []
        for row in rows:
            track = TimelineTrack.from_row(row)
            clip_rows = self.db.fetch_all(
                "SELECT * FROM timeline_clips WHERE track_id = ? "
                "ORDER BY start_time ASC, created_at ASC",
                (track.id,),
            )
            tracks.append({
                "track": track.to_dict(),
                "clips": [TimelineClip.from_row(clip).to_dict() for clip in clip_rows],
            })
        return tracks

    def _format(self, project_id, tracks, initialized=False, warnings=None):
        project = self._project(project_id)
        duration = 0.0
        for item in tracks:
            for clip in item["clips"]:
                duration = max(
                    duration,
                    float(clip.get("start_time") or 0)
                    + float(clip.get("duration_s") or 0),
                )
        return {
            "timeline_version": int(project.timeline_version or 0) if project else 0,
            "initialized": initialized,
            "updated_at": project.updated_at if project else None,
            "tracks": tracks,
            "duration_s": round(duration, 3),
            "warnings": warnings or [],
        }

    def get_timeline(self, project_id, ensure=False, user=None):
        tracks = self._raw_tracks(project_id)
        if tracks or not ensure:
            return self._format(project_id, tracks)
        return self.auto_init(project_id, user=user)

    def _project(self, project_id):
        row = self.db.fetch_one(
            "SELECT * FROM creative_projects WHERE id = ?", (project_id,)
        )
        return CreativeProject.from_row(row)

    def timeline_ready(self, project_id):
        video_clips = [
            clip for clip in self._video_clips(project_id)
            if not clip.get("muted")
        ]
        if not video_clips:
            return False
        for clip in video_clips:
            asset = self.asset_service.get_asset(clip.get("asset_id"))
            if not asset or asset.asset_type != "video":
                return False
            if not self.asset_service.get_file_path_for_asset(asset):
                return False
        return True

    def _video_clips(self, project_id):
        rows = self.db.fetch_all(
            "SELECT c.* FROM timeline_clips c "
            "JOIN timeline_tracks t ON t.id = c.track_id "
            "WHERE c.creative_project_id = ? "
            "AND (t.role = 'video' OR t.track_type = 'video') "
            "ORDER BY c.start_time ASC",
            (project_id,),
        )
        return [TimelineClip.from_row(row).to_dict() for row in rows]

    # ── Probing ──

    def _asset_duration(self, asset, user):
        if asset.duration_s and asset.duration_s > 0:
            return float(asset.duration_s)
        path = self.asset_service.get_file_path_for_asset(asset)
        if not path:
            raise ApiError(
                "invalid_timeline", "素材文件不存在", status_code=400,
                details={"asset_id": asset.id},
            )
        try:
            info = probe_media_file(self.cfg.FFPROBE_BIN, path)
        except Exception as exc:
            raise ApiError(
                "invalid_timeline",
                "素材无法探测：{0}".format(str(exc)),
                status_code=400,
                details={"asset_id": asset.id},
            )
        return float(info.get("duration_s") or 0.0)

    def _checked_asset(self, asset_id, expected_type, user):
        asset = self.asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError(
                "asset_not_found", "素材不存在", status_code=404,
                details={"asset_id": asset_id},
            )
        if user is not None and not can_read_asset(
            asset, user, demo_mode=getattr(self.cfg, "DEMO_MODE", False)
        ):
            raise ApiError(
                "forbidden", "无权使用该素材", status_code=403,
                details={"asset_id": asset_id},
            )
        if asset.asset_type != expected_type:
            raise ApiError(
                "invalid_timeline",
                "素材类型与轨道不匹配（需要 {0}）".format(expected_type),
                status_code=400,
                details={"asset_id": asset.id},
            )
        return asset

    # ── Auto initialization ──

    def auto_init(self, project_id, user=None):
        if self._raw_tracks(project_id):
            return self._format(project_id, self._raw_tracks(project_id))
        project = self._project(project_id)
        if not project:
            raise ApiError("project_not_found", "项目不存在", status_code=404)
        shots = self.storyboard_service.list_shots(project_id)
        warnings = []
        video_track_clips = []
        narration_clips = []
        subtitle_clips = []
        cursor_time = 0.0

        for shot in shots:
            video_asset_id = shot.selected_video_asset_id or shot.video_asset_id
            video_duration = None
            video_start = cursor_time
            if video_asset_id:
                asset = self.asset_service.get_asset(video_asset_id)
                if not asset or asset.asset_type != "video":
                    warnings.append("分镜 {0} 的视频素材不存在".format(shot.sequence_no))
                elif user is not None and not can_read_asset(
                    asset, user, demo_mode=getattr(self.cfg, "DEMO_MODE", False)
                ):
                    warnings.append("分镜 {0} 的视频素材无权访问".format(shot.sequence_no))
                else:
                    path = self.asset_service.get_file_path_for_asset(asset)
                    if not path:
                        warnings.append("分镜 {0} 的视频文件缺失".format(shot.sequence_no))
                    else:
                        try:
                            info = probe_media_file(self.cfg.FFPROBE_BIN, path)
                            video_duration = float(info.get("duration_s") or 0.0)
                        except Exception as exc:
                            warnings.append(
                                "分镜 {0} 的视频无法探测：{1}".format(
                                    shot.sequence_no, str(exc)
                                )
                            )
            if video_duration and video_duration > 0 and video_asset_id:
                has_narration = bool(shot.audio_asset_id)
                video_track_clips.append({
                    "shot_id": shot.id,
                    "asset_id": video_asset_id,
                    "name": shot.scene_title or "镜头{0}".format(shot.sequence_no),
                    "start_time": round(cursor_time, 3),
                    "duration_s": round(video_duration, 3),
                    "trim_in": 0.0,
                    "trim_out": round(video_duration, 3),
                    "volume": 1.0,
                    "muted": False,
                    "source_audio_enabled": not has_narration,
                    "fade_in": 0.0,
                    "fade_out": 0.0,
                    "properties": {"auto_initialized": True},
                })
                cursor_time += video_duration

            audio_duration = None
            if shot.audio_asset_id:
                audio = self.asset_service.get_asset(shot.audio_asset_id)
                if audio and audio.asset_type == "audio":
                    try:
                        audio_duration = self._asset_duration(audio, user)
                    except ApiError:
                        audio_duration = shot.audio_duration_s
                if audio_duration and audio_duration > 0:
                    narration_clips.append({
                        "shot_id": shot.id,
                        "asset_id": shot.audio_asset_id,
                        "name": "{0} 配音".format(shot.scene_title or shot.sequence_no),
                        "start_time": round(video_start, 3),
                        "duration_s": round(audio_duration, 3),
                        "trim_in": 0.0,
                        "trim_out": round(audio_duration, 3),
                        "volume": 1.0,
                        "muted": False,
                        "source_audio_enabled": True,
                        "fade_in": 0.0,
                        "fade_out": 0.0,
                        "properties": {"auto_initialized": True},
                    })

            if (shot.dialogue or "").strip():
                subtitle_duration = audio_duration or video_duration or float(
                    shot.duration_s or 0
                )
                if subtitle_duration and subtitle_duration > 0:
                    subtitle_clips.append({
                        "shot_id": shot.id,
                        "asset_id": None,
                        "name": "{0} 字幕".format(shot.scene_title or shot.sequence_no),
                        "start_time": round(video_start, 3),
                        "duration_s": round(float(subtitle_duration), 3),
                        "trim_in": 0.0,
                        "trim_out": round(float(subtitle_duration), 3),
                        "volume": 1.0,
                        "muted": False,
                        "source_audio_enabled": True,
                        "fade_in": 0.0,
                        "fade_out": 0.0,
                        "subtitle_text": shot.dialogue.strip(),
                        "properties": {
                            "auto_initialized": True,
                            "timing_method": "audio_duration" if audio_duration else "estimated",
                        },
                    })

        if not video_track_clips:
            warnings.append("项目还没有可用的分镜视频，时间线尚未初始化")
            return self._format(project_id, [], initialized=False, warnings=warnings)

        tracks = [
            self._track_payload("主视频轨", "video", "video", 0, video_track_clips),
            self._track_payload("配音轨", "audio", "narration", 1, narration_clips),
            self._track_payload("音乐轨", "audio", "music", 2, []),
            self._track_payload("音效轨", "audio", "sfx", 3, []),
            self._track_payload("字幕轨", "subtitle", "subtitle", 4, subtitle_clips),
        ]
        now = _now()
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM timeline_tracks WHERE creative_project_id = ?",
                (project_id,),
            )
            if cursor.fetchone()["count"]:
                raced = True
            else:
                raced = False
                self._insert_timeline(cursor, project_id, tracks, now)
                cursor.execute(
                    "UPDATE creative_projects SET timeline_version = 1, updated_at = ? "
                    "WHERE id = ? AND COALESCE(timeline_version, 0) = 0",
                    (now, project_id),
                )
        if raced:
            return self._format(project_id, self._raw_tracks(project_id))
        return self._format(
            project_id, self._raw_tracks(project_id),
            initialized=True, warnings=warnings,
        )

    def _track_payload(self, name, track_type, role, sequence_no, clips):
        return {
            "name": name,
            "track_type": track_type,
            "role": role,
            "sequence_no": sequence_no,
            "settings": {},
            "clips": clips,
        }

    # ── Saving ──

    def save_timeline(self, project_id, payload, user=None):
        tracks_data = payload.get("tracks")
        if not isinstance(tracks_data, list):
            raise ApiError("invalid_timeline", "tracks 必须是数组", status_code=400)
        if len(tracks_data) > MAX_TRACKS:
            raise ApiError("invalid_timeline", "轨道数量超过限制", status_code=400)
        # Accept the GET shape ({track: ..., clips: ...}) as well as the flat
        # save shape so a load-modify-save round trip is always valid.
        normalised_tracks = []
        for raw_track in tracks_data:
            if isinstance(raw_track, dict) and isinstance(raw_track.get("track"), dict):
                flat = dict(raw_track["track"])
                flat["clips"] = raw_track.get("clips") or []
                normalised_tracks.append(flat)
            else:
                normalised_tracks.append(raw_track)
        tracks_data = normalised_tracks
        expected_version = payload.get("timeline_version")
        project = self._project(project_id)
        if not project:
            raise ApiError("project_not_found", "项目不存在", status_code=404)
        current_version = int(project.timeline_version or 0)
        if expected_version is not None:
            try:
                expected_version = int(expected_version)
            except (TypeError, ValueError):
                raise ApiError("invalid_timeline", "timeline_version 必须是整数", status_code=400)
            if expected_version != current_version:
                raise ApiError(
                    "timeline_conflict",
                    "时间线已被其他编辑修改，请刷新后再保存",
                    status_code=409,
                    details={"current_timeline_version": current_version},
                )

        validated = self._validate_tracks(project_id, tracks_data, user)
        now = _now()
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT COALESCE(timeline_version, 0) AS version "
                "FROM creative_projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ApiError("project_not_found", "项目不存在", status_code=404)
            current = int(row["version"] or 0)
            if expected_version is not None and current != expected_version:
                raise ApiError(
                    "timeline_conflict",
                    "时间线已被其他编辑修改，请刷新后再保存",
                    status_code=409,
                    details={"current_timeline_version": current},
                )
            self._insert_timeline(cursor, project_id, validated, now)
            new_version = current + 1
            cursor.execute(
                "UPDATE creative_projects SET timeline_version = ?, updated_at = ? "
                "WHERE id = ?",
                (new_version, now, project_id),
            )
        result = self._format(project_id, self._raw_tracks(project_id))
        result["saved"] = True
        return result

    def _validate_tracks(self, project_id, tracks_data, user):
        shots = {shot.id: shot for shot in self.storyboard_service.list_shots(project_id)}
        validated = []
        total_clips = 0
        video_tracks = 0
        for track_index, raw_track in enumerate(tracks_data):
            if not isinstance(raw_track, dict):
                raise ApiError("invalid_timeline", "轨道格式错误", status_code=400)
            track_type = raw_track.get("track_type")
            role = raw_track.get("role")
            if track_type not in ("video", "audio", "subtitle", "effect"):
                raise ApiError("invalid_timeline", "不支持的轨道类型", status_code=400)
            if role not in ("video", "narration", "music", "sfx", "subtitle"):
                raise ApiError("invalid_timeline", "不支持的轨道角色", status_code=400)
            if track_type == "video" and role != "video":
                raise ApiError("invalid_timeline", "视频轨角色必须为 video", status_code=400)
            if role == "video":
                video_tracks += 1
                if video_tracks > 1:
                    raise ApiError("invalid_timeline", "只支持一条主视频轨", status_code=400)
            if track_type == "audio" and role not in ("narration", "music", "sfx"):
                raise ApiError("invalid_timeline", "音频轨角色无效", status_code=400)
            if track_type == "subtitle" and role != "subtitle":
                raise ApiError("invalid_timeline", "字幕轨角色无效", status_code=400)
            raw_clips = raw_track.get("clips") or []
            if not isinstance(raw_clips, list):
                raise ApiError("invalid_timeline", "clips 必须是数组", status_code=400)
            total_clips += len(raw_clips)
            if total_clips > MAX_CLIPS:
                raise ApiError("invalid_timeline", "片段数量超过限制", status_code=400)
            clips = [
                self._validate_clip(project_id, role, raw_clip, shots, user)
                for raw_clip in raw_clips
            ]
            if role == "video":
                ordered = sorted(clips, key=lambda item: item["start_time"])
                for first, second in zip(ordered, ordered[1:]):
                    if first["start_time"] + first["duration_s"] > second["start_time"] + 0.01:
                        raise ApiError(
                            "invalid_timeline", "视频轨片段不能重叠", status_code=400
                        )
            validated.append({
                "name": str(raw_track.get("name") or role)[:120],
                "track_type": track_type,
                "role": role,
                "sequence_no": int(raw_track.get("sequence_no", track_index)),
                "settings": raw_track.get("settings") if isinstance(
                    raw_track.get("settings"), dict
                ) else {},
                "clips": clips,
            })
        return validated

    def _validate_clip(self, project_id, role, raw_clip, shots, user):
        if not isinstance(raw_clip, dict):
            raise ApiError("invalid_timeline", "片段格式错误", status_code=400)
        start_time = _finite(raw_clip.get("start_time"), "start_time", 0, MAX_START_S)
        duration_s = _finite(
            raw_clip.get("duration_s"), "duration_s", 0.01, MAX_CLIP_DURATION_S
        )
        trim_in = _finite(raw_clip.get("trim_in"), "trim_in", 0, MAX_CLIP_DURATION_S, 0.0)
        trim_out = raw_clip.get("trim_out")
        if trim_out is not None:
            trim_out = _finite(trim_out, "trim_out", 0, MAX_CLIP_DURATION_S)
            if trim_out <= trim_in:
                raise ApiError("invalid_timeline", "trim_out 必须大于 trim_in", status_code=400)
        volume = _finite(raw_clip.get("volume"), "volume", 0, 2.0, 1.0)
        fade_in = _finite(raw_clip.get("fade_in"), "fade_in", 0, 30.0, 0.0)
        fade_out = _finite(raw_clip.get("fade_out"), "fade_out", 0, 30.0, 0.0)
        muted = _bool(raw_clip.get("muted"), False)
        source_audio_enabled = _bool(raw_clip.get("source_audio_enabled"), True)
        subtitle_text = raw_clip.get("subtitle_text")
        if subtitle_text is not None:
            if not isinstance(subtitle_text, str):
                raise ApiError("invalid_timeline", "字幕文本必须是字符串", status_code=400)
            if len(subtitle_text) > MAX_SUBTITLE_CHARS:
                raise ApiError("invalid_timeline", "字幕文本过长", status_code=400)
            subtitle_text = subtitle_text.strip() or None

        shot_id = raw_clip.get("shot_id")
        shot = None
        if shot_id:
            shot = shots.get(shot_id)
            if not shot:
                raise ApiError("invalid_timeline", "分镜不属于当前项目", status_code=400)

        asset_id = raw_clip.get("asset_id")
        asset = None
        if role != "subtitle" and not asset_id:
            raise ApiError("invalid_timeline", "该轨道片段必须引用素材", status_code=400)
        if asset_id:
            expected = "video" if role == "video" else (
                "subtitle" if role == "subtitle" else "audio"
            )
            asset = self._checked_asset(asset_id, expected, user)
            if role != "subtitle":
                source_duration = self._asset_duration(asset, user)
                if trim_in > source_duration + 0.05:
                    raise ApiError("invalid_timeline", "trim_in 超过素材时长", status_code=400)
                effective = (trim_out - trim_in) if trim_out is not None else duration_s
                is_looped_music = (
                    role == "music" and bool((raw_clip.get("properties") or {}).get("loop"))
                )
                if not is_looped_music and effective > source_duration + 0.05:
                    raise ApiError("invalid_timeline", "片段超出素材实际时长", status_code=400)
                if (
                    trim_out is not None and not is_looped_music
                    and abs((trim_out - trim_in) - duration_s) > 0.05
                ):
                    raise ApiError(
                        "invalid_timeline",
                        "duration_s 必须等于 trim_out - trim_in",
                        status_code=400,
                    )
            if role == "narration":
                if not shot:
                    raise ApiError("invalid_timeline", "配音片段必须绑定分镜", status_code=400)
                version = self.db.fetch_one(
                    "SELECT id FROM shot_media_versions WHERE shot_id = ? "
                    "AND media_kind = 'audio' AND asset_id = ?",
                    (shot.id, asset.id),
                )
                if not version and shot.audio_asset_id != asset.id:
                    raise ApiError(
                        "invalid_timeline", "配音素材不是该分镜的配音版本", status_code=400
                    )
            if role in ("music", "sfx"):
                if asset.audio_role and asset.audio_role != role:
                    raise ApiError(
                        "invalid_timeline", "音频角色与轨道不匹配", status_code=400
                    )
        if role == "subtitle" and not subtitle_text:
            raise ApiError("invalid_timeline", "字幕片段必须有文本", status_code=400)

        return {
            "shot_id": shot_id,
            "asset_id": asset_id,
            "name": str(raw_clip.get("name") or "")[:120],
            "start_time": start_time,
            "duration_s": duration_s,
            "trim_in": trim_in,
            "trim_out": trim_out,
            "volume": volume,
            "muted": muted,
            "source_audio_enabled": source_audio_enabled,
            "fade_in": fade_in,
            "fade_out": fade_out,
            "subtitle_text": subtitle_text,
            "properties": raw_clip.get("properties") if isinstance(
                raw_clip.get("properties"), dict
            ) else {},
        }

    # ── Persistence primitives ──

    @staticmethod
    def _insert_row(cursor, table, params):
        columns = list(params.keys())
        cursor.execute(
            "INSERT INTO {0} ({1}) VALUES ({2})".format(
                table,
                ", ".join(columns),
                ", ".join("?" for _ in columns),
            ),
            tuple(params[column] for column in columns),
        )

    def _insert_timeline(self, cursor, project_id, tracks, now):
        cursor.execute(
            "DELETE FROM timeline_clips WHERE creative_project_id = ?", (project_id,)
        )
        cursor.execute(
            "DELETE FROM timeline_tracks WHERE creative_project_id = ?", (project_id,)
        )
        for track_data in tracks:
            track = TimelineTrack(
                creative_project_id=project_id,
                name=track_data["name"],
                track_type=track_data["track_type"],
                role=track_data["role"],
                sequence_no=track_data["sequence_no"],
                settings=track_data.get("settings") or {},
                created_at=now,
                updated_at=now,
            )
            self._insert_row(cursor, "timeline_tracks", track.to_insert_params())
            for clip_data in track_data["clips"]:
                clip = TimelineClip(
                    track_id=track.id,
                    creative_project_id=project_id,
                    shot_id=clip_data.get("shot_id"),
                    asset_id=clip_data.get("asset_id"),
                    name=clip_data.get("name") or "",
                    start_time=clip_data["start_time"],
                    duration_s=clip_data["duration_s"],
                    trim_in=clip_data["trim_in"],
                    trim_out=clip_data.get("trim_out"),
                    volume=clip_data["volume"],
                    muted=clip_data["muted"],
                    source_audio_enabled=clip_data["source_audio_enabled"],
                    fade_in=clip_data["fade_in"],
                    fade_out=clip_data["fade_out"],
                    subtitle_text=clip_data.get("subtitle_text"),
                    properties=clip_data.get("properties") or {},
                    created_at=now,
                    updated_at=now,
                )
                self._insert_row(cursor, "timeline_clips", clip.to_insert_params())

    def sync_shot_media(self, project_id, shot_id, audio_asset_id=None,
                        audio_duration_s=None, audio_options=None,
                        subtitle_text=None, subtitle_duration_s=None):
        """Update narration/subtitle clips after TTS or audio selection.

        Only the matching shot's clips are touched; user edits to other clips
        remain intact.  Returns ``(updated, timeline_version)``.
        """
        tracks = self._raw_tracks(project_id)
        if not tracks:
            return False, None
        video_track = None
        narration_track = None
        subtitle_track = None
        for item in tracks:
            role = (item.get("track") or {}).get("role")
            if role == "video":
                video_track = item["track"]
            elif role == "narration":
                narration_track = item["track"]
            elif role == "subtitle":
                subtitle_track = item["track"]
        if not narration_track and not subtitle_track:
            return False, None
        video_clip = None
        if video_track:
            for clip in self._video_clips(project_id):
                if clip.get("shot_id") == shot_id:
                    video_clip = clip
                    break
        start_time = float(video_clip.get("start_time") or 0) if video_clip else 0.0
        video_duration = float(video_clip.get("duration_s") or 0) if video_clip else 0.0
        duration = float(audio_duration_s or 0) or video_duration or 1.0
        now = _now()
        changed = False
        with self.db.transaction() as cursor:
            if narration_track:
                cursor.execute(
                    "SELECT id FROM timeline_clips WHERE track_id = ? AND shot_id = ?",
                    (narration_track["id"], shot_id),
                )
                row = cursor.fetchone()
                if audio_asset_id:
                    if row:
                        cursor.execute(
                            "UPDATE timeline_clips SET asset_id = ?, start_time = ?, "
                            "duration_s = ?, trim_in = 0, trim_out = ?, "
                            "updated_at = ? WHERE id = ?",
                            (audio_asset_id, start_time, duration, duration, now, row["id"]),
                        )
                    else:
                        clip = TimelineClip(
                            track_id=narration_track["id"],
                            creative_project_id=project_id,
                            shot_id=shot_id,
                            asset_id=audio_asset_id,
                            name="配音",
                            start_time=start_time,
                            duration_s=duration,
                            trim_in=0,
                            trim_out=duration,
                            volume=1.0,
                            muted=False,
                            source_audio_enabled=True,
                            fade_in=0,
                            fade_out=0,
                            properties={"auto_synced": True},
                            created_at=now,
                            updated_at=now,
                        )
                        self._insert_row(
                            cursor, "timeline_clips", clip.to_insert_params()
                        )
                    changed = True
                elif row:
                    cursor.execute(
                        "DELETE FROM timeline_clips WHERE id = ?", (row["id"],)
                    )
                    changed = True
            text = (subtitle_text or "").strip()
            if subtitle_track and text:
                subtitle_duration = float(subtitle_duration_s or 0) or duration
                cursor.execute(
                    "SELECT id FROM timeline_clips WHERE track_id = ? AND shot_id = ?",
                    (subtitle_track["id"], shot_id),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        "UPDATE timeline_clips SET subtitle_text = ?, start_time = ?, "
                        "duration_s = ?, updated_at = ? WHERE id = ?",
                        (text, start_time, subtitle_duration, now, row["id"]),
                    )
                else:
                    clip = TimelineClip(
                        track_id=subtitle_track["id"],
                        creative_project_id=project_id,
                        shot_id=shot_id,
                        asset_id=None,
                        name="字幕",
                        start_time=start_time,
                        duration_s=subtitle_duration,
                        trim_in=0,
                        trim_out=subtitle_duration,
                        volume=1.0,
                        muted=False,
                        source_audio_enabled=True,
                        fade_in=0,
                        fade_out=0,
                        subtitle_text=text,
                        properties={"auto_synced": True},
                        created_at=now,
                        updated_at=now,
                    )
                    self._insert_row(
                        cursor, "timeline_clips", clip.to_insert_params()
                    )
                changed = True
            if changed:
                cursor.execute(
                    "UPDATE creative_projects SET timeline_version = "
                    "COALESCE(timeline_version, 0) + 1, updated_at = ? WHERE id = ?",
                    (now, project_id),
                )
                cursor.execute(
                    "SELECT timeline_version FROM creative_projects WHERE id = ?",
                    (project_id,),
                )
                version = cursor.fetchone()["timeline_version"]
            else:
                row = cursor.execute(
                    "SELECT COALESCE(timeline_version, 0) AS version "
                    "FROM creative_projects WHERE id = ?",
                    (project_id,),
                ).fetchone()
                version = row["version"] if row else None
        return changed, version

    def sync_from_shots(self, project_id, user=None):
        """Synchronise video clips with each shot's selected video.

        Existing clips keep their timeline start; their source asset and trim
        are refreshed.  New shots are appended at the end of the video track.
        Music/SFX clips and other tracks are untouched.
        """
        tracks = self._raw_tracks(project_id)
        if not tracks:
            return self.auto_init(project_id, user=user)
        video_track = None
        for item in tracks:
            track = item.get("track") or {}
            if track.get("role") == "video" or track.get("track_type") == "video":
                video_track = track
                break
        if not video_track:
            return self._format(project_id, tracks, warnings=["没有主视频轨"])
        shots = self.storyboard_service.list_shots(project_id)
        existing = {}
        if video_track:
            for row in self.db.fetch_all(
                "SELECT * FROM timeline_clips WHERE track_id = ? "
                "ORDER BY start_time ASC",
                (video_track["id"],),
            ):
                clip = TimelineClip.from_row(row)
                if clip.shot_id:
                    existing[clip.shot_id] = clip
        prepared = []
        end_time = 0.0
        for clip in existing.values():
            end_time = max(end_time, float(clip.start_time) + float(clip.duration_s))
        for shot in shots:
            asset_id = shot.selected_video_asset_id or shot.video_asset_id
            if not asset_id:
                continue
            asset = self.asset_service.get_asset(asset_id)
            if not asset or asset.asset_type != "video":
                continue
            if user is not None and not can_read_asset(
                asset, user, demo_mode=getattr(self.cfg, "DEMO_MODE", False)
            ):
                continue
            try:
                duration = self._asset_duration(asset, user)
            except ApiError:
                continue
            if duration <= 0:
                continue
            current = existing.get(shot.id)
            if current:
                prepared.append(("update", current, asset_id, duration))
            else:
                prepared.append(("insert", shot, asset_id, duration, end_time))
                end_time += duration
        if not prepared:
            return self._format(project_id, tracks)
        now = _now()
        with self.db.transaction() as cursor:
            for item in prepared:
                if item[0] == "update":
                    _kind, clip, asset_id, duration = item
                    cursor.execute(
                        "UPDATE timeline_clips SET asset_id = ?, trim_in = 0, "
                        "duration_s = ?, trim_out = ?, updated_at = ? WHERE id = ?",
                        (asset_id, duration, duration, now, clip.id),
                    )
                else:
                    _kind, shot, asset_id, duration, start_time = item
                    clip = TimelineClip(
                        track_id=video_track["id"],
                        creative_project_id=project_id,
                        shot_id=shot.id,
                        asset_id=asset_id,
                        name=shot.scene_title or "镜头",
                        start_time=start_time,
                        duration_s=duration,
                        trim_in=0,
                        trim_out=duration,
                        volume=1.0,
                        muted=False,
                        source_audio_enabled=not bool(shot.audio_asset_id),
                        fade_in=0,
                        fade_out=0,
                        properties={"auto_synced": True},
                        created_at=now,
                        updated_at=now,
                    )
                    self._insert_row(
                        cursor, "timeline_clips", clip.to_insert_params()
                    )
            cursor.execute(
                "UPDATE creative_projects SET timeline_version = "
                "COALESCE(timeline_version, 0) + 1, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            cursor.execute(
                "SELECT timeline_version FROM creative_projects WHERE id = ?",
                (project_id,),
            )
            version = cursor.fetchone()["timeline_version"]
        result = self._format(project_id, self._raw_tracks(project_id))
        result["synced"] = True
        result["timeline_version"] = version
        return result

    # ── Subtitles ──

    @staticmethod
    def build_srt_from_timeline(timeline):
        entries = []
        for item in timeline.get("tracks") or []:
            track = item.get("track") or {}
            role = track.get("role")
            if role is None and track.get("track_type") == "subtitle":
                role = "subtitle"
            if role != "subtitle":
                continue
            for clip in item.get("clips") or []:
                if clip.get("muted"):
                    continue
                text = (clip.get("subtitle_text") or "").strip()
                if not text:
                    continue
                entries.append((float(clip.get("start_time") or 0), clip, text))
        entries.sort(key=lambda item: item[0])
        lines = []
        for index, (_start, clip, text) in enumerate(entries, start=1):
            lines.append(
                "{0}\n{1} --> {2}\n{3}\n".format(
                    index,
                    srt_timestamp(float(clip.get("start_time") or 0)),
                    srt_timestamp(
                        float(clip.get("start_time") or 0)
                        + float(clip.get("duration_s") or 0)
                    ),
                    text,
                )
            )
        return "\n".join(lines)

    @staticmethod
    def timeline_end(timeline):
        end = 0.0
        for item in timeline.get("tracks") or []:
            track = item.get("track") or {}
            if track.get("role") != "video" and track.get("track_type") != "video":
                continue
            for clip in item.get("clips") or []:
                end = max(
                    end,
                    float(clip.get("start_time") or 0)
                    + float(clip.get("duration_s") or 0),
                )
        return end

    def build_srt(self, project_id):
        return self.build_srt_from_timeline(
            self._format(project_id, self._raw_tracks(project_id))
        )


_timeline_service = None


def get_timeline_service(cfg):
    global _timeline_service
    if _timeline_service is None or getattr(_timeline_service, "data_dir", None) != cfg.DATA_DIR:
        _timeline_service = TimelineService(cfg)
    return _timeline_service
