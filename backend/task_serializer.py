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
)


def public_task_dict(task, asset_service=None, task_service=None):
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
    if asset_service is not None and task.output_asset_id:
        output_asset = asset_service.get_asset(task.output_asset_id)
        data["output_asset"] = (
            asset_service.public_dict(output_asset) if output_asset else None
        )
    else:
        data["output_asset"] = None

    artifacts = []
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
