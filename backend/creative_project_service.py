# -*- coding: utf-8 -*-
"""
Creative project service for AIGV Studio.
"""
from __future__ import absolute_import

import logging
import os
import time

from .database import get_database
from .models import CreativeProject, _json_dumps

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class CreativeProjectService(object):
    """Service for managing creative production projects."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database()

    def list_projects(self, tenant_id=None, user_id=None, include_unowned=False, limit=100, offset=0):
        """List creative projects with optional tenant/user scoping."""
        conditions = []
        params = []
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if user_id:
            if include_unowned:
                conditions.append("(user_id = ? OR user_id IS NULL)")
                params.append(user_id)
            else:
                conditions.append("user_id = ?")
                params.append(user_id)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.db.fetch_all(
            "SELECT * FROM creative_projects WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?".format(where),
            tuple(params) + (limit, offset),
        )
        total = self.db.count("creative_projects", where, tuple(params))

        projects = [CreativeProject.from_row(r) for r in rows]
        return {
            "items": [p.to_dict() for p in projects],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_project(self, project_id):
        """Get a single creative project by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM creative_projects WHERE id = ?",
            (project_id,),
        )
        return CreativeProject.from_row(row)

    def create_project(self, **kwargs):
        """Create a new creative project."""
        project = CreativeProject(**kwargs)
        project.created_at = _now()
        project.updated_at = _now()
        params = project.to_insert_params()
        self.db.insert("creative_projects", params)
        return project

    def update_project(self, project_id, **kwargs):
        """Update an existing creative project."""
        existing = self.get_project(project_id)
        if not existing:
            return None

        updatable = [
            "name", "description", "status", "genre", "target_duration",
            "concept", "requirements", "creative_brief", "settings",
        ]
        json_fields = ("requirements", "creative_brief", "settings")
        update_data = {}
        for key in updatable:
            if key in kwargs and kwargs[key] is not None:
                value = kwargs[key]
                setattr(existing, key, value)
                update_data[key] = _json_dumps(value) if key in json_fields else value

        if not update_data:
            return existing

        existing.updated_at = _now()
        update_data["updated_at"] = existing.updated_at

        self.db.update("creative_projects", update_data, "id = ?", (project_id,))
        return self.get_project(project_id)

    def delete_project(self, project_id):
        """Delete a creative project and related data.

        Generated assets are removed only after the project rows are gone and
        only when no other shot/timeline/task still references them.
        """
        asset_ids = set()
        for row in self.db.fetch_all(
            "SELECT output_asset_id FROM generation_tasks "
            "WHERE creative_project_id = ? AND output_asset_id IS NOT NULL",
            (project_id,),
        ):
            asset_ids.add(row["output_asset_id"])
        for row in self.db.fetch_all(
            "SELECT DISTINCT asset_id FROM task_artifacts "
            "WHERE creative_project_id = ? AND asset_id IS NOT NULL",
            (project_id,),
        ):
            asset_ids.add(row["asset_id"])
        for row in self.db.fetch_all(
            "SELECT DISTINCT asset_id FROM shot_media_versions "
            "WHERE creative_project_id = ? AND asset_id IS NOT NULL",
            (project_id,),
        ):
            asset_ids.add(row["asset_id"])
        final_row = self.db.fetch_one(
            "SELECT final_video_asset_id FROM creative_projects WHERE id = ?",
            (project_id,),
        )
        if final_row and final_row["final_video_asset_id"]:
            asset_ids.add(final_row["final_video_asset_id"])

        export_task_ids = [
            row["id"] for row in self.db.fetch_all(
                "SELECT id FROM generation_tasks WHERE creative_project_id = ? "
                "AND task_type = 'export'",
                (project_id,),
            )
        ]
        # Delete child rows before their FK parents in one transaction. media
        # versions reference both shots and tasks; export_packages reference
        # tasks.
        with self.db.transaction() as cursor:
            cursor.execute(
                "DELETE FROM shot_media_versions WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM timeline_clips WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM timeline_tracks WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM task_artifacts WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM export_packages WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM generation_tasks WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute(
                "DELETE FROM storyboard_shots WHERE creative_project_id = ?",
                (project_id,),
            )
            cursor.execute("DELETE FROM creative_projects WHERE id = ?", (project_id,))
            deleted = cursor.rowcount

        if deleted:
            import shutil
            exports_root = os.path.realpath(os.path.join(self.data_dir, "exports"))
            for task_id in export_task_ids:
                path = os.path.realpath(os.path.join(exports_root, str(task_id)))
                if path.startswith(exports_root + os.sep) and os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)

        if deleted and asset_ids:
            from .asset_service import get_asset_service
            asset_service = get_asset_service(self.data_dir)
            for asset_id in asset_ids:
                if sum(asset_service.asset_reference_breakdown(asset_id).values()):
                    continue
                asset = asset_service.get_asset(asset_id)
                source = (asset.metadata or {}).get("source") if asset else None
                if asset and source in ("generation", "tts", "compose", "refine"):
                    asset_service.delete_asset(asset_id)
        return deleted > 0


# Singleton
_creative_project_service = None


def get_creative_project_service(data_dir=None):
    global _creative_project_service
    if _creative_project_service is None:
        _creative_project_service = CreativeProjectService(data_dir)
    return _creative_project_service
