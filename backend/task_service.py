# -*- coding: utf-8 -*-
"""
Task service for managing generation_tasks and task_artifacts.
"""
from __future__ import absolute_import

import logging
import time

from .database import get_database
from .models import GenerationTask, TaskArtifact

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class TaskService(object):
    """Service for managing async generation tasks."""

    def __init__(self, data_dir=None):
        self.db = get_database()

    def create_task(self, creative_project_id, task_type, **kwargs):
        """Create a new generation task."""
        task = GenerationTask(
            creative_project_id=creative_project_id,
            task_type=task_type,
            **kwargs
        )
        task.created_at = _now()
        task.updated_at = _now()

        params = task.to_insert_params()
        self.db.insert("generation_tasks", params)
        return task

    def get_task(self, task_id):
        """Get a single task by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM generation_tasks WHERE id = ?",
            (task_id,),
        )
        return GenerationTask.from_row(row)

    def list_tasks(self, creative_project_id=None, task_type=None, limit=50, offset=0):
        """List tasks, optionally filtered."""
        conditions = []
        params = []

        if creative_project_id:
            conditions.append("creative_project_id = ?")
            params.append(creative_project_id)
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.db.fetch_all(
            "SELECT * FROM generation_tasks WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?".format(where),
            tuple(params) + (limit, offset),
        )
        total = self.db.count("generation_tasks", where, tuple(params))

        tasks = [GenerationTask.from_row(r) for r in rows]
        return {
            "items": [t.to_dict() for t in tasks],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def claim_next_task(self):
        """
        Atomically claim the next queued task.
        Uses UPDATE ... WHERE id IN (SELECT ...) for atomicity.

        Returns:
            GenerationTask or None
        """
        # First find the next queued task
        row = self.db.fetch_one(
            "SELECT id FROM generation_tasks WHERE status = ? ORDER BY created_at ASC LIMIT 1",
            (GenerationTask.STATUS_QUEUED,),
        )
        if not row:
            return None

        task_id = row["id"]
        now = _now()

        # Atomically claim it
        affected = self.db.update(
            "generation_tasks",
            {"status": GenerationTask.STATUS_RUNNING, "claimed_at": now, "updated_at": now},
            "id = ? AND status = ?",
            (task_id, GenerationTask.STATUS_QUEUED),
        )

        if affected == 0:
            # Someone else claimed it
            return None

        return self.get_task(task_id)

    def update_task(self, task_id, **kwargs):
        """Update task fields."""
        existing = self.get_task(task_id)
        if not existing:
            return None

        updatable = [
            "status", "stage", "progress", "result_payload",
            "error_code", "error_message", "completed_at",
        ]
        update_data = {}
        for key in updatable:
            if key in kwargs and kwargs[key] is not None:
                setattr(existing, key, kwargs[key])
                if key in ("result_payload",):
                    # Serialize JSON-typed fields
                    update_data[key] = __import__("json").dumps(kwargs[key], ensure_ascii=False)
                else:
                    update_data[key] = kwargs[key]

        if not update_data:
            return existing

        existing.updated_at = _now()
        update_data["updated_at"] = existing.updated_at

        self.db.update("generation_tasks", update_data, "id = ?", (task_id,))
        return self.get_task(task_id)

    def cancel_task(self, task_id):
        """Cancel a task if it's queued or running."""
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status in (GenerationTask.STATUS_QUEUED, GenerationTask.STATUS_RUNNING):
            self.db.update(
                "generation_tasks",
                {
                    "status": GenerationTask.STATUS_CANCELLED,
                    "completed_at": _now(),
                    "updated_at": _now(),
                },
                "id = ?",
                (task_id,),
            )
            return True

        return False

    def add_artifact(self, task_id, creative_project_id, name, artifact_type,
                     file_path=None, file_size=0, asset_id=None, metadata=None):
        """Add an artifact record for a task."""
        artifact = TaskArtifact(
            task_id=task_id,
            creative_project_id=creative_project_id,
            name=name,
            artifact_type=artifact_type,
            file_path=file_path,
            file_size=file_size,
            asset_id=asset_id,
            metadata=metadata,
        )
        artifact.created_at = _now()
        artifact.updated_at = _now()

        params = artifact.to_insert_params()
        self.db.insert("task_artifacts", params)
        return artifact

    def list_artifacts(self, creative_project_id=None, task_id=None):
        """List artifacts, optionally filtered."""
        if task_id:
            rows = self.db.fetch_all(
                "SELECT * FROM task_artifacts WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            )
        elif creative_project_id:
            rows = self.db.fetch_all(
                "SELECT * FROM task_artifacts WHERE creative_project_id = ? ORDER BY created_at DESC",
                (creative_project_id,),
            )
        else:
            rows = self.db.fetch_all("SELECT * FROM task_artifacts ORDER BY created_at DESC")

        return [TaskArtifact.from_row(r) for r in rows]


# Singleton
_task_service = None


def get_task_service(data_dir=None):
    global _task_service
    if _task_service is None:
        _task_service = TaskService(data_dir)
    return _task_service
