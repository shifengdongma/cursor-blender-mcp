# -*- coding: utf-8 -*-
"""
Creative project service for AIGV Studio.
"""
from __future__ import absolute_import

import logging
import time

from .database import get_database
from .models import CreativeProject

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class CreativeProjectService(object):
    """Service for managing creative production projects."""

    def __init__(self, data_dir=None):
        self.db = get_database()

    def list_projects(self, tenant_id=None, limit=100, offset=0):
        """List creative projects, optionally filtered by tenant."""
        if tenant_id:
            rows = self.db.fetch_all(
                "SELECT * FROM creative_projects WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (tenant_id, limit, offset),
            )
            total = self.db.count("creative_projects", "tenant_id = ?", (tenant_id,))
        else:
            rows = self.db.fetch_all(
                "SELECT * FROM creative_projects ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            total = self.db.count("creative_projects")

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
        update_data = {}
        for key in updatable:
            if key in kwargs and kwargs[key] is not None:
                setattr(existing, key, kwargs[key])
                update_data[key] = kwargs[key]

        if not update_data:
            return existing

        existing.updated_at = _now()
        update_data["updated_at"] = existing.updated_at

        self.db.update("creative_projects", update_data, "id = ?", (project_id,))
        return self.get_project(project_id)

    def delete_project(self, project_id):
        """Delete a creative project and related data."""
        # Delete storyboard shots
        self.db.delete("storyboard_shots", "creative_project_id = ?", (project_id,))
        # Delete timeline clips
        self.db.delete("timeline_clips", "creative_project_id = ?", (project_id,))
        # Delete timeline tracks
        self.db.delete("timeline_tracks", "creative_project_id = ?", (project_id,))
        # Delete task artifacts
        self.db.delete("task_artifacts", "creative_project_id = ?", (project_id,))
        # Delete generation tasks
        self.db.delete("generation_tasks", "creative_project_id = ?", (project_id,))
        # Delete export packages
        self.db.delete("export_packages", "creative_project_id = ?", (project_id,))
        # Delete the project
        deleted = self.db.delete("creative_projects", "id = ?", (project_id,))
        return deleted > 0


# Singleton
_creative_project_service = None


def get_creative_project_service(data_dir=None):
    global _creative_project_service
    if _creative_project_service is None:
        _creative_project_service = CreativeProjectService(data_dir)
    return _creative_project_service
