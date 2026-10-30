# -*- coding: utf-8 -*-
"""Shared HTTP serialisation for generation tasks.

All task responses go through this helper so internal leasing/idempotency
fields never leak through one route while being stripped by another.
"""
from __future__ import absolute_import

from .task_service import get_task_service

_SENSITIVE_TASK_FIELDS = (
    "lease_owner",
    "lease_expires_at",
    "submission_started_at",
    "provider_job_id",
    "idempotency_key",
    "client_request_id",
    "timeline_snapshot",
    "timing_json",
    "created_at_ms",
    "claimed_at_ms",
    "provider_request_started_at",
    "provider_request_finished_at",
    "provider_job_created_at",
    "provider_finished_at",
    "download_started_at",
    "download_finished_at",
    "persist_started_at",
    "persist_finished_at",
    "completed_at_ms",
)


def public_task_dict(task, asset_service=None, task_service=None, _skip_queries=False):
    if not task:
        return None
    data = task.to_dict()
    for field in _SENSITIVE_TASK_FIELDS:
        data.pop(field, None)

    result = task.result_payload or {}
    data["result_payload"] = {
        "provider": result.get("provider"),
        "model_id": result.get("model_id"),
        "asset_ids": result.get("asset_ids") or [],
        "output_asset_id": result.get("output_asset_id"),
    }
    data["cancel_requested"] = bool(task.cancel_requested)

    output_asset = None
    if not _skip_queries and asset_service is not None and task.output_asset_id:
        output_asset = asset_service.get_asset(task.output_asset_id)
        data["output_asset"] = (
            asset_service.public_dict(output_asset) if output_asset else None
        )
    else:
        data["output_asset"] = None

    artifacts = []
    if not _skip_queries:
        if task_service is None:
            try:
                task_service = get_task_service()
            except Exception:
                task_service = None
        if task_service is not None:
            artifacts = [
                {
                    "id": artifact.id,
                    "name": artifact.name,
                    "artifact_type": artifact.artifact_type,
                    "file_size": artifact.file_size,
                    "asset_id": artifact.asset_id,
                    "created_at": artifact.created_at,
                }
                for artifact in task_service.list_artifacts(task_id=task.id)
            ]
    data["artifacts"] = artifacts
    return data


def public_task_dicts(tasks, asset_service, task_service):
    """Serialise many tasks with batched asset/artifact lookups."""
    tasks = [task for task in (tasks or []) if task]
    asset_ids = [task.output_asset_id for task in tasks if task.output_asset_id]
    assets = asset_service.get_assets_by_ids(asset_ids) if asset_service else {}
    artifacts = task_service.list_artifacts_for_tasks([task.id for task in tasks])
    items = []
    for task in tasks:
        data = public_task_dict(task, _skip_queries=True)
        asset = assets.get(task.output_asset_id) if task.output_asset_id else None
        data["output_asset"] = (
            asset_service.public_dict(asset) if asset and asset_service else None
        )
        data["artifacts"] = [
            {
                "id": artifact.id,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "file_size": artifact.file_size,
                "asset_id": artifact.asset_id,
                "created_at": artifact.created_at,
            }
            for artifact in artifacts.get(task.id, [])
        ]
        items.append(data)
    return items
