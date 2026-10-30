# -*- coding: utf-8 -*-
"""
Storyboard service for managing storyboard_shots.
"""
from __future__ import absolute_import

import json
import logging
import time

from .database import get_database
from .models import StoryboardShot

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class StoryboardService(object):
    """Service for managing storyboard shots."""

    def __init__(self, data_dir=None):
        self.db = get_database()

    def list_shots(self, creative_project_id):
        """List all shots for a creative project, ordered by sequence_no."""
        rows = self.db.fetch_all(
            "SELECT * FROM storyboard_shots WHERE creative_project_id = ? ORDER BY sequence_no ASC",
            (creative_project_id,),
        )
        return [StoryboardShot.from_row(r) for r in rows]

    def get_shot(self, shot_id):
        """Get a single shot by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM storyboard_shots WHERE id = ?",
            (shot_id,),
        )
        return StoryboardShot.from_row(row)

    def create_shot(self, creative_project_id, **kwargs):
        """Create a new shot with auto-assigned sequence_no."""
        # Get next sequence number
        existing = self.list_shots(creative_project_id)
        next_seq = 1
        if existing:
            next_seq = max(s.sequence_no for s in existing) + 1

        shot = StoryboardShot(
            creative_project_id=creative_project_id,
            sequence_no=kwargs.pop("sequence_no", next_seq),
            **kwargs
        )
        shot.created_at = _now()
        shot.updated_at = _now()

        params = shot.to_insert_params()
        self.db.insert("storyboard_shots", params)
        return shot

    def update_shot(self, shot_id, cursor=None, **kwargs):
        """Update a storyboard shot.

        Pass ``cursor`` when called inside ``db.transaction()`` so the update
        joins the surrounding transaction instead of taking the DB write lock.
        """
        existing = self.get_shot(shot_id)
        if not existing:
            return None

        updatable = [
            "sequence_no", "scene_title", "scene_description", "shot_type",
            "duration_s", "dialogue", "voice_id", "camera_movement",
            "lighting_mood", "environment_detail", "character_action",
            "visual_style", "prompt_cn", "prompt_en", "negative_prompt",
            "primary_image_asset_id", "keyframe_asset_id", "video_asset_id", "audio_asset_id",
            "selected_video_asset_id", "refined_video_asset_id", "video_selection_source",
            "subtitle_asset_id", "audio_options", "audio_duration_s",
            "srt_path", "video_url", "status", "metadata",
        ]
        update_data = {}
        for key in updatable:
            if key in kwargs and kwargs[key] is not None:
                setattr(existing, key, kwargs[key])
                if key in ("metadata", "audio_options"):
                    update_data[key] = json.dumps(kwargs[key], ensure_ascii=False)
                else:
                    update_data[key] = kwargs[key]

        if not update_data:
            return existing

        existing.updated_at = _now()
        update_data["updated_at"] = existing.updated_at

        if cursor is None:
            self.db.update("storyboard_shots", update_data, "id = ?", (shot_id,))
        else:
            columns = list(update_data.keys())
            cursor.execute(
                "UPDATE storyboard_shots SET {0} WHERE id = ?".format(
                    ", ".join("{0} = ?".format(column) for column in columns)
                ),
                tuple(update_data[column] for column in columns) + (shot_id,),
            )
        return self.get_shot(shot_id)

    def set_media_pointers(self, shot_id, **fields):
        """Explicitly set pointer fields, including clearing them with None."""
        allowed = {
            "audio_asset_id", "subtitle_asset_id", "srt_path",
            "selected_video_asset_id", "refined_video_asset_id",
            "video_selection_source", "audio_options", "audio_duration_s",
        }
        update_data = {}
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "audio_options" and value is not None:
                update_data[key] = json.dumps(value, ensure_ascii=False)
            else:
                update_data[key] = value
        if not update_data:
            return self.get_shot(shot_id)
        update_data["updated_at"] = _now()
        columns = list(update_data.keys())
        self.db.execute(
            "UPDATE storyboard_shots SET {0} WHERE id = ?".format(
                ", ".join("{0} = ?".format(column) for column in columns)
            ),
            tuple(update_data[column] for column in columns) + (shot_id,),
        )
        return self.get_shot(shot_id)

    def delete_shot(self, shot_id):
        """Delete a shot and its dependent timeline/version/task references."""
        shot = self.get_shot(shot_id)
        if not shot:
            return False
        now = _now()
        with self.db.transaction() as cursor:
            cursor.execute(
                "DELETE FROM shot_media_versions WHERE shot_id = ?", (shot_id,)
            )
            cursor.execute(
                "DELETE FROM timeline_clips WHERE shot_id = ?", (shot_id,)
            )
            removed_clips = cursor.rowcount
            cursor.execute(
                "UPDATE generation_tasks SET target_shot_id = NULL WHERE target_shot_id = ?",
                (shot_id,),
            )
            cursor.execute("DELETE FROM storyboard_shots WHERE id = ?", (shot_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("shot delete lost race")
            if removed_clips:
                cursor.execute(
                    "UPDATE creative_projects SET timeline_version = "
                    "COALESCE(timeline_version, 0) + 1, updated_at = ? WHERE id = ?",
                    (now, shot.creative_project_id),
                )
        return True

    def reorder_shots(self, creative_project_id, ordered_ids):
        """
        Reorder shots by updating sequence_no atomically.
        ordered_ids: list of shot IDs in desired order.
        """
        if not ordered_ids:
            return

        # Verify all IDs belong to this project
        placeholders = ",".join(["?" for _ in ordered_ids])
        rows = self.db.fetch_all(
            "SELECT id FROM storyboard_shots WHERE creative_project_id = ? AND id IN ({0})".format(placeholders),
            (creative_project_id,) + tuple(ordered_ids),
        )
        valid_ids = set(r["id"] for r in rows)

        now = _now()
        for i, shot_id in enumerate(ordered_ids, start=1):
            if shot_id in valid_ids:
                self.db.update(
                    "storyboard_shots",
                    {"sequence_no": i, "updated_at": now},
                    "id = ?",
                    (shot_id,),
                )

    def bulk_create_shots(self, creative_project_id, shots_data):
        """Create multiple shots from a list of dicts."""
        created = []
        for data in shots_data:
            shot = self.create_shot(creative_project_id, **data)
            created.append(shot)
        return created


# Singleton
_storyboard_service = None


def get_storyboard_service(data_dir=None):
    global _storyboard_service
    if _storyboard_service is None:
        _storyboard_service = StoryboardService(data_dir)
    return _storyboard_service
