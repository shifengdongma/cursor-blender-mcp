# -*- coding: utf-8 -*-
"""
Task service for managing generation_tasks and task_artifacts.
"""
from __future__ import absolute_import

import logging
import time

from .database import get_database
from .http_utils import ApiError
from .models import GenerationTask, TaskArtifact

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class TaskService(object):
    """Service for managing async generation tasks."""

    def __init__(self, data_dir=None):
        self.db = get_database()

    def create_task(self, creative_project_id, task_type, cursor=None, **kwargs):
        """Create a new generation task.

        Pass ``cursor`` to insert inside an existing ``db.transaction()`` block
        (used to make quota checks and inserts atomic).
        """
        provided_created_at = kwargs.get("created_at")
        provided_created_at_ms = kwargs.get("created_at_ms")
        task = GenerationTask(
            creative_project_id=creative_project_id,
            task_type=task_type,
            **kwargs
        )
        if provided_created_at is None:
            task.created_at = _now()
        if provided_created_at_ms is None:
            task.created_at_ms = float(time.time())
        if not task.updated_at:
            task.updated_at = _now()

        params = task.to_insert_params()
        if cursor is None:
            self.db.insert("generation_tasks", params)
        else:
            columns = list(params.keys())
            cursor.execute(
                "INSERT INTO generation_tasks ({0}) VALUES ({1})".format(
                    ", ".join(columns), ", ".join("?" for _ in columns)
                ),
                tuple(params[column] for column in columns),
            )
        return task

    def get_task(self, task_id):
        """Get a single task by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM generation_tasks WHERE id = ?",
            (task_id,),
        )
        return GenerationTask.from_row(row)

    def get_tasks_by_ids(self, task_ids):
        """Fetch many task rows in one query, preserving input order."""
        ids = [task_id for task_id in (task_ids or []) if task_id]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.fetch_all(
            "SELECT * FROM generation_tasks WHERE id IN ({0})".format(placeholders),
            tuple(ids),
        )
        return {row["id"]: GenerationTask.from_row(row) for row in rows}

    # Fixed ORDER BY fragments; raw client input never reaches the SQL string.
    SORT_ORDERS = {
        "newest": "created_at DESC",
        "oldest": "created_at ASC",
    }

    def list_tasks(self, creative_project_id=None, task_type=None, task_types=None,
                   status=None, created_by=None, limit=50, offset=0,
                   created_after=None, created_before=None, model_id=None,
                   sort="newest"):
        """List tasks, optionally filtered."""
        order_clause = self.SORT_ORDERS.get(sort or "newest")
        if order_clause is None:
            raise ApiError("invalid_params", "不支持的排序方式", status_code=400)
        conditions = []
        params = []

        if creative_project_id:
            conditions.append("creative_project_id = ?")
            params.append(creative_project_id)
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        if task_types:
            placeholders = ",".join("?" for _ in task_types)
            conditions.append("task_type IN ({0})".format(placeholders))
            params.extend(task_types)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if created_by:
            conditions.append("created_by = ?")
            params.append(created_by)
        if created_after is not None:
            conditions.append("created_at >= ?")
            params.append(int(created_after))
        if created_before is not None:
            conditions.append("created_at <= ?")
            params.append(int(created_before))
        if model_id:
            conditions.append("model_id = ?")
            params.append(model_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.db.fetch_all(
            "SELECT * FROM generation_tasks WHERE {0} ORDER BY {1} LIMIT ? OFFSET ?".format(
                where, order_clause
            ),
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

    def find_idempotent_task(self, created_by, client_request_id):
        if not created_by or not client_request_id:
            return None
        row = self.db.fetch_one(
            "SELECT * FROM generation_tasks WHERE created_by = ? AND client_request_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (created_by, client_request_id),
        )
        return GenerationTask.from_row(row)

    def claim_next_task(self, task_types=None):
        """Atomically claim the next queued legacy task."""
        conditions = ["status = ?"]
        params = [GenerationTask.STATUS_QUEUED]
        if task_types:
            placeholders = ",".join("?" for _ in task_types)
            conditions.append("task_type IN ({0})".format(placeholders))
            params.extend(task_types)
        row = self.db.fetch_one(
            "SELECT id FROM generation_tasks WHERE {0} ORDER BY created_at ASC LIMIT 1".format(
                " AND ".join(conditions)
            ),
            tuple(params),
        )
        if not row:
            return None

        task_id = row["id"]
        now = _now()
        affected = self.db.update(
            "generation_tasks",
            {
                "status": GenerationTask.STATUS_RUNNING,
                "claimed_at": now,
                "claimed_at_ms": time.time(),
                "updated_at": now,
            },
            "id = ? AND status = ?",
            (task_id, GenerationTask.STATUS_QUEUED),
        )
        if affected == 0:
            return None
        return self.get_task(task_id)

    # ── Resumable generation queue ──

    def claim_generation_submission(self, lease_owner, lease_seconds=300):
        now = _now()
        task_id = None
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT id FROM generation_tasks "
                "WHERE task_type IN ('image','video') AND status = 'queued' "
                "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
                "ORDER BY created_at ASC LIMIT 1",
                (now,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            task_id = row["id"]
            cursor.execute(
                "UPDATE generation_tasks SET status = 'submitting', lease_owner = ?, "
                "lease_expires_at = ?, attempt_count = COALESCE(attempt_count, 0) + 1, "
                "submission_uncertain = 1, submission_started_at = ?, updated_at = ?, "
                "claimed_at = ?, claimed_at_ms = COALESCE(claimed_at_ms, ?), "
                "created_at_ms = COALESCE(created_at_ms, ?) "
                "WHERE id = ? AND status = 'queued'",
                (
                    lease_owner, now + lease_seconds, now, now, now,
                    time.time(), time.time(), task_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_task(task_id)

    def claim_generation_poll(self, lease_owner, lease_seconds=300):
        now = _now()
        task_id = None
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT id FROM generation_tasks "
                "WHERE task_type IN ('image','video') AND status = 'running' "
                "AND provider_job_id IS NOT NULL AND provider_job_id <> '' "
                "AND (next_retry_at IS NULL OR next_retry_at <= ?) "
                "AND (lease_expires_at IS NULL OR lease_expires_at < ?) "
                "ORDER BY COALESCE(next_retry_at, 0) ASC, created_at ASC LIMIT 1",
                (now, now),
            )
            row = cursor.fetchone()
            if not row:
                return None
            task_id = row["id"]
            cursor.execute(
                "UPDATE generation_tasks SET lease_owner = ?, lease_expires_at = ?, updated_at = ? "
                "WHERE id = ? AND status = 'running' "
                "AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
                (lease_owner, now + lease_seconds, now, task_id, now),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_task(task_id)

    def release_generation_lease(self, task_id, lease_owner, cursor=None, **fields):
        update = {"lease_owner": None, "lease_expires_at": None, "updated_at": _now()}
        for key, value in fields.items():
            if key in (
                "status", "stage", "progress", "provider_status", "provider_job_id",
                "provider_request_id", "next_retry_at", "poll_error_count", "last_polled_at",
                "submission_uncertain", "error_code", "error_message",
                "completed_at", "completed_at_ms", "result_payload",
                "output_asset_id", "cancel_requested",
                "provider_request_started_at", "provider_request_finished_at",
                "provider_job_created_at", "provider_finished_at",
                "download_started_at", "download_finished_at",
                "persist_started_at", "persist_finished_at",
                "claimed_at_ms", "created_at_ms", "timing_json",
            ):
                if key == "result_payload":
                    update[key] = __import__("json").dumps(value, ensure_ascii=False)
                else:
                    update[key] = value
        set_clause = ", ".join("{0} = ?".format(key) for key in update)
        query = "UPDATE generation_tasks SET {0} WHERE id = ? AND lease_owner = ?".format(set_clause)
        params = tuple(update.values()) + (task_id, lease_owner)
        if cursor is not None:
            cursor.execute(query, params)
            return cursor.rowcount
        return self.db.execute(query, params)

    def recover_stale_generation_leases(self):
        now = _now()
        with self.db.transaction() as cursor:
            cursor.execute(
                "UPDATE generation_tasks SET status = 'needs_review', lease_owner = NULL, "
                "lease_expires_at = NULL, error_code = 'submission_uncertain', "
                "error_message = '提交结果不确定，需人工确认是否已在服务商侧创建任务', updated_at = ? "
                "WHERE task_type IN ('image','video') AND status = 'submitting' "
                "AND (provider_job_id IS NULL OR provider_job_id = '') "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (now, now),
            )
            cursor.execute(
                "UPDATE generation_tasks SET lease_owner = NULL, lease_expires_at = NULL, "
                "next_retry_at = ?, updated_at = ? "
                "WHERE task_type IN ('image','video') AND status = 'running' "
                "AND provider_job_id IS NOT NULL AND provider_job_id <> '' "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                (now, now, now),
            )

    def count_active_tasks(self, created_by, task_types=None):
        where = "created_by = ? AND status IN ('queued','submitting','running')"
        params = [created_by]
        if task_types:
            placeholders = ",".join("?" for _ in task_types)
            where += " AND task_type IN ({0})".format(placeholders)
            params.extend(task_types)
        return self.db.count("generation_tasks", where, tuple(params))

    def count_active_project_tasks(self, creative_project_id, task_types=None):
        where = (
            "creative_project_id = ? "
            "AND status IN ('queued','submitting','running')"
        )
        params = [creative_project_id]
        if task_types:
            placeholders = ",".join("?" for _ in task_types)
            where += " AND task_type IN ({0})".format(placeholders)
            params.extend(task_types)
        return self.db.count("generation_tasks", where, tuple(params))

    def count_tasks_since(self, created_by, since, task_type=None):
        where = "created_by = ? AND created_at >= ?"
        params = [created_by, since]
        if task_type:
            where += " AND task_type = ?"
            params.append(task_type)
        return self.db.count("generation_tasks", where, tuple(params))

    def update_task(self, task_id, **kwargs):
        """Update task fields."""
        existing = self.get_task(task_id)
        if not existing:
            return None

        updatable = [
            "status", "stage", "progress", "params", "result_payload",
            "error_code", "error_message", "completed_at", "provider",
            "model_id", "provider_job_id", "provider_request_id", "provider_status", "attempt_count",
            "max_attempts", "next_retry_at", "lease_expires_at", "lease_owner",
            "submission_uncertain", "submission_started_at", "poll_error_count",
            "last_polled_at", "output_asset_id", "client_request_id",
            "cost_estimate", "currency", "cancel_requested",
            "timeline_version", "timeline_snapshot",
            "created_at_ms", "claimed_at_ms",
            "provider_request_started_at", "provider_request_finished_at",
            "provider_job_created_at", "provider_finished_at",
            "download_started_at", "download_finished_at",
            "persist_started_at", "persist_finished_at", "completed_at_ms",
            "timing_json",
        ]
        update_data = {}
        for key in updatable:
            if key in kwargs:
                setattr(existing, key, kwargs[key])
                if key in ("result_payload", "params", "timeline_snapshot", "timing_json"):
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
        """Cancel a task if it's queued, or request cancellation when running."""
        task = self.get_task(task_id)
        if not task:
            return False

        if task.task_type in (GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO):
            if task.status == GenerationTask.STATUS_QUEUED:
                affected = self.db.update(
                    "generation_tasks",
                    {
                        "status": GenerationTask.STATUS_CANCELLED,
                        "completed_at": _now(),
                        "completed_at_ms": time.time(),
                        "updated_at": _now(),
                    },
                    "id = ? AND status = 'queued'",
                    (task_id,),
                )
                if affected:
                    return True
                # Lost the race to a worker claim; fall through and request
                # cancellation of the now-active task instead of lying.
                task = self.get_task(task_id)
                if not task:
                    return False
            if task.status in (
                GenerationTask.STATUS_QUEUED,
                GenerationTask.STATUS_SUBMITTING,
                GenerationTask.STATUS_RUNNING,
            ):
                self.db.update(
                    "generation_tasks",
                    {"cancel_requested": 1, "updated_at": _now()},
                    "id = ? AND status IN ('queued','submitting','running')",
                    (task_id,),
                )
                return True
            return task.status == GenerationTask.STATUS_CANCELLED

        if task.status in (GenerationTask.STATUS_QUEUED, GenerationTask.STATUS_RUNNING):
            affected = self.db.update(
                "generation_tasks",
                {
                    "status": GenerationTask.STATUS_CANCELLED,
                    "completed_at": _now(),
                    "completed_at_ms": time.time(),
                    "updated_at": _now(),
                },
                "id = ? AND status IN ('queued','running')",
                (task_id,),
            )
            return affected > 0

        return False

    def delete_terminal_task(self, task_id):
        """Delete a failed/cancelled task and its child rows atomically.

        Tasks with any output asset are intentionally rejected so deleting a
        history record never destroys a usable asset.
        """
        with self.db.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM generation_tasks WHERE id = ?", (task_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ApiError("task_not_found", "任务不存在", status_code=404)
            task = GenerationTask.from_row(dict(row))
            if task.task_type not in (
                GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO
            ):
                raise ApiError("invalid_task", "不是可删除的生成任务", status_code=400)
            if task.status not in (
                GenerationTask.STATUS_FAILED, GenerationTask.STATUS_CANCELLED
            ):
                raise ApiError(
                    "task_not_deletable",
                    "只有失败或已取消的任务可以删除记录",
                    status_code=409,
                )
            result_payload = task.result_payload or {}
            if task.output_asset_id or (result_payload.get("asset_ids") or []):
                raise ApiError(
                    "task_has_assets",
                    "该任务已有生成作品，请先在素材库删除作品",
                    status_code=409,
                )
            cursor.execute(
                "SELECT id, asset_id FROM task_artifacts WHERE task_id = ?",
                (task_id,),
            )
            artifacts = [dict(item) for item in cursor.fetchall()]
            if any(item.get("asset_id") for item in artifacts):
                raise ApiError(
                    "task_has_assets",
                    "该任务已有生成作品，请先在素材库删除作品",
                    status_code=409,
                )
            # Delete children before the parent; SQLite foreign keys are on.
            cursor.execute("DELETE FROM export_packages WHERE task_id = ?", (task_id,))
            cursor.execute("DELETE FROM task_artifacts WHERE task_id = ?", (task_id,))
            cursor.execute(
                "DELETE FROM generation_tasks WHERE id = ? "
                "AND status IN ('failed','cancelled') "
                "AND output_asset_id IS NULL",
                (task_id,),
            )
            if cursor.rowcount != 1:
                raise ApiError(
                    "task_not_deletable",
                    "任务状态已变化，请刷新后重试",
                    status_code=409,
                )
        return {"task": task, "artifacts": artifacts}

    def add_artifact(self, task_id, creative_project_id, name, artifact_type,
                     file_path=None, file_size=0, asset_id=None, metadata=None,
                     cursor=None):
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
        if cursor is None:
            self.db.insert("task_artifacts", params)
        else:
            columns = list(params.keys())
            cursor.execute(
                "INSERT INTO task_artifacts ({0}) VALUES ({1})".format(
                    ", ".join(columns), ", ".join("?" for _ in columns)
                ),
                tuple(params[column] for column in columns),
            )
        return artifact

    def list_artifacts_for_tasks(self, task_ids):
        """Fetch artifacts for many tasks in one query, grouped by task_id."""
        ids = [task_id for task_id in (task_ids or []) if task_id]
        grouped = {task_id: [] for task_id in ids}
        if not ids:
            return grouped
        placeholders = ",".join("?" for _ in ids)
        rows = self.db.fetch_all(
            "SELECT * FROM task_artifacts WHERE task_id IN ({0}) "
            "ORDER BY created_at DESC".format(placeholders),
            tuple(ids),
        )
        for row in rows:
            artifact = TaskArtifact.from_row(row)
            grouped.setdefault(artifact.task_id, []).append(artifact)
        return grouped

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
