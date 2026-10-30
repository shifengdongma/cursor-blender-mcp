# -*- coding: utf-8 -*-
"""Real image/video generation API."""
from __future__ import absolute_import

import logging
import os
import statistics
import time
from datetime import datetime

from flask import g, request, send_file

from .access import require_asset, require_task
from .asset_service import get_asset_service
from .auth_middleware import admin_required, is_admin
from .database import get_database
from .generation_models import list_models
from .http_utils import ApiError, parse_json_body, parse_pagination
from .models import GenerationTask
from .task_service import get_task_service
from .task_serializer import public_task_dict, public_task_dicts
from . import generation_service

logger = logging.getLogger(__name__)


def _serialize_task(task, asset_service):
    return public_task_dict(task, asset_service=asset_service)


def _parse_date(value, end_of_day=False):
    if value is None or str(value).strip() == "":
        return None
    value = str(value).strip()
    try:
        return int(value)
    except ValueError:
        pass
    try:
        # No tzinfo: dates are interpreted in the server's local timezone.
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ApiError("invalid_params", "日期格式应为 YYYY-MM-DD", status_code=400)
    timestamp = int(parsed.timestamp())
    return timestamp + 86399 if end_of_day else timestamp


def _client_request_id(payload):
    return (request.headers.get("Idempotency-Key") or payload.get("client_request_id") or "")[:128] or None


def _epoch_ms(task, name, integer_name=None):
    value = getattr(task, name, None)
    if value is not None:
        try:
            return float(value) * 1000.0
        except (TypeError, ValueError):
            return None
    if integer_name:
        value = getattr(task, integer_name, None)
        if value is not None:
            try:
                return float(value) * 1000.0
            except (TypeError, ValueError):
                return None
    return None


def _safe_delta(end, start):
    if end is None or start is None:
        return None
    value = float(end) - float(start)
    return round(value, 1) if value >= 0 else None


def _task_timing(task):
    created = _epoch_ms(task, "created_at_ms", "created_at")
    claimed = _epoch_ms(task, "claimed_at_ms", "claimed_at")
    request_started = _epoch_ms(task, "provider_request_started_at")
    request_finished = _epoch_ms(task, "provider_request_finished_at")
    job_created = _epoch_ms(task, "provider_job_created_at")
    provider_finished = _epoch_ms(task, "provider_finished_at")
    download_started = _epoch_ms(task, "download_started_at")
    download_finished = _epoch_ms(task, "download_finished_at")
    persist_started = _epoch_ms(task, "persist_started_at")
    persist_finished = _epoch_ms(task, "persist_finished_at")
    completed = _epoch_ms(task, "completed_at_ms", "completed_at")
    durations = {
        "queue_wait_ms": _safe_delta(claimed, created),
        "submission_ms": _safe_delta(request_finished, request_started),
        "provider_elapsed_ms": _safe_delta(provider_finished, job_created),
        "download_ms": _safe_delta(download_finished, download_started),
        "persist_ms": _safe_delta(persist_finished, persist_started),
        "total_ms": _safe_delta(completed, created),
    }
    return {
        "task_id": task.id,
        "task_type": task.task_type,
        "provider": task.provider,
        "model_id": task.model_id,
        "status": task.status,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
        "timestamps": {
            "created_at_ms": created,
            "claimed_at_ms": claimed,
            "provider_request_started_at": request_started,
            "provider_request_finished_at": request_finished,
            "provider_job_created_at": job_created,
            "provider_finished_at": provider_finished,
            "download_started_at": download_started,
            "download_finished_at": download_finished,
            "persist_started_at": persist_started,
            "persist_finished_at": persist_finished,
            "completed_at_ms": completed,
        },
        "durations_ms": durations,
        "notes": [
            "provider_elapsed 包含服务商排队与运行时间，不等于纯推理时间",
            "queue_wait 为创建到 Worker 领取的本地排队时间",
            "total 为创建到任务完成的端到端时间",
        ],
    }


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile / 100.0
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def register_generation_routes(app, cfg, json_success, json_error):
    task_service = get_task_service(cfg.DATA_DIR)

    @app.route("/api/generation/models", methods=["GET"])
    def generation_models():
        task_type = request.args.get("task_type")
        # Default: return every model with an availability flag so the UI can
        # explain why a provider is unusable.  ``available_only=1`` keeps the
        # old "configured only" behaviour for programmatic callers.
        available_only = (
            request.args.get("available_only") in ("1", "true", "yes")
            or request.args.get("include_unavailable") in ("0", "false", "no")
        )
        models = list_models(
            cfg,
            task_type=task_type,
            include_unavailable=not available_only,
            user=g.current_user,
        )
        return json_success(
            {
                "items": models,
                "available_count": len([m for m in models if m.get("available")]),
            }
        )

    @app.route("/api/generation/images", methods=["POST"])
    def generation_images():
        payload = parse_json_body(request)
        model_key = payload.get("model_key") or payload.get("model")
        if not model_key:
            raise ApiError("invalid_model", "缺少 model_key", status_code=400)
        task = generation_service.create_generation_task(
            cfg,
            task_service,
            g.current_user,
            GenerationTask.TYPE_IMAGE,
            model_key,
            payload,
            project_id=payload.get("project_id") or payload.get("creative_project_id"),
            shot_id=payload.get("shot_id") or payload.get("target_shot_id"),
            client_request_id=_client_request_id(payload),
        )
        asset_service = get_asset_service(cfg.DATA_DIR)
        return json_success(_serialize_task(task, asset_service), message="图片生成任务已创建", status_code=202)

    @app.route("/api/generation/videos", methods=["POST"])
    def generation_videos():
        payload = parse_json_body(request)
        model_key = payload.get("model_key") or payload.get("model")
        if not model_key:
            raise ApiError("invalid_model", "缺少 model_key", status_code=400)
        task = generation_service.create_generation_task(
            cfg,
            task_service,
            g.current_user,
            GenerationTask.TYPE_VIDEO,
            model_key,
            payload,
            project_id=payload.get("project_id") or payload.get("creative_project_id"),
            shot_id=payload.get("shot_id") or payload.get("target_shot_id"),
            client_request_id=_client_request_id(payload),
        )
        asset_service = get_asset_service(cfg.DATA_DIR)
        return json_success(_serialize_task(task, asset_service), message="视频生成任务已创建", status_code=202)

    @app.route("/api/generation/tasks", methods=["GET"])
    def generation_task_list():
        pagination = parse_pagination(request, default_limit=20, max_limit=100)
        task_type = request.args.get("task_type")
        status = request.args.get("status")
        project_id = request.args.get("project_id")
        scope = request.args.get("scope") or "mine"
        created_by = None if (scope == "all" and is_admin(g.current_user)) else g.current_user.get("id")
        created_after = _parse_date(request.args.get("date_from"))
        created_before = _parse_date(request.args.get("date_to"), end_of_day=True)
        if (created_after is not None and created_before is not None
                and created_after > created_before):
            raise ApiError("invalid_params", "开始时间不能晚于结束时间", status_code=400)
        sort = request.args.get("sort") or "newest"
        if sort not in ("newest", "oldest"):
            raise ApiError("invalid_params", "不支持的排序方式", status_code=400)
        result = task_service.list_tasks(
            creative_project_id=project_id,
            task_type=task_type,
            task_types=(GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO),
            status=status,
            created_by=created_by,
            limit=pagination.limit,
            offset=pagination.offset,
            created_after=created_after,
            created_before=created_before,
            model_id=request.args.get("model_id"),
            sort=sort,
        )
        asset_service = get_asset_service(cfg.DATA_DIR)
        ids = [item.get("id") for item in result.get("items", []) if item.get("id")]
        task_map = task_service.get_tasks_by_ids(ids)
        ordered = [task_map[task_id] for task_id in ids if task_id in task_map]
        result["items"] = public_task_dicts(ordered, asset_service, task_service)
        if scope == "all" and is_admin(g.current_user):
            creator_ids = sorted({
                item.get("created_by") for item in result["items"] if item.get("created_by")
            })
            creators = {}
            if creator_ids:
                placeholders = ",".join("?" for _ in creator_ids)
                for row in get_database().fetch_all(
                    "SELECT id, username, nickname FROM auth_users "
                    "WHERE id IN ({0})".format(placeholders),
                    tuple(creator_ids),
                ):
                    creators[row["id"]] = {
                        "id": row["id"],
                        "username": row["username"],
                        "nickname": row.get("nickname") or row["username"],
                    }
            for item in result["items"]:
                item["creator"] = creators.get(item.get("created_by"))
        return json_success(result)

    @app.route("/api/generation/tasks/<task_id>", methods=["GET"])
    def generation_task_detail(task_id):
        task = require_task(task_id, demo_mode=cfg.DEMO_MODE)
        return json_success(_serialize_task(task, get_asset_service(cfg.DATA_DIR)))

    @app.route("/api/generation/tasks/<task_id>/cancel", methods=["POST"])
    def generation_task_cancel(task_id):
        require_task(task_id, write=True, demo_mode=cfg.DEMO_MODE)
        task = task_service.get_task(task_id)
        if not task or task.task_type not in (GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO):
            raise ApiError("invalid_task", "不是可取消的生成任务", status_code=400)
        if not task_service.cancel_task(task_id):
            raise ApiError("cancel_failed", "当前状态不能取消", status_code=400)
        task = task_service.get_task(task_id)
        _audit(cfg, "generation_cancel", task_id)
        return json_success(_serialize_task(task, get_asset_service(cfg.DATA_DIR)), message="取消请求已记录")

    @app.route("/api/generation/tasks/<task_id>", methods=["DELETE"])
    def generation_task_delete(task_id):
        task = require_task(
            task_id, write=True, demo_mode=cfg.DEMO_MODE, creator_only=True
        )
        if task.task_type not in (GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO):
            raise ApiError("invalid_task", "不是可删除的生成任务", status_code=400)
        deleted = task_service.delete_terminal_task(task_id)
        deleted_task = deleted["task"]
        provider_cancel = {"attempted": False, "succeeded": False}
        if (deleted_task.status == GenerationTask.STATUS_FAILED
                and deleted_task.provider_job_id):
            provider_cancel = generation_service.cancel_provider_job(cfg, deleted_task)
        generation_service.remove_task_directory(cfg, deleted_task)
        _audit(
            cfg, "generation_delete", task_id,
            metadata={
                "task_type": deleted_task.task_type,
                "status_at_delete": deleted_task.status,
                "provider": deleted_task.provider,
                "model_id": deleted_task.model_id,
                "had_provider_job": bool(deleted_task.provider_job_id),
                "provider_cancel_succeeded": provider_cancel.get("succeeded"),
                "artifact_count": len(deleted.get("artifacts") or []),
            },
        )
        return json_success({"deleted": True}, message="生成记录已删除")

    @app.route("/api/generation/tasks/<task_id>/retry", methods=["POST"])
    @admin_required
    def generation_task_retry(task_id):
        task = task_service.get_task(task_id)
        if not task or task.task_type not in (GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO):
            raise ApiError("invalid_task", "不是可重试的生成任务", status_code=400)
        if task.status not in (GenerationTask.STATUS_FAILED, GenerationTask.STATUS_NEEDS_REVIEW):
            raise ApiError("invalid_task_state", "只有失败或待确认任务可以重试", status_code=400)
        payload = request.get_json(silent=True) or {}
        if task.provider_job_id:
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_RUNNING,
                next_retry_at=0,
                lease_owner=None,
                lease_expires_at=None,
                error_code=None,
                error_message=None,
                submission_uncertain=0,
                poll_error_count=0,
            )
            message = "已恢复轮询，不会重新提交付费任务"
        else:
            if not payload.get("confirm_duplicate"):
                raise ApiError(
                    "duplicate_risk",
                    "该任务没有第三方任务 ID，重试可能重复扣费；请确认后携带 confirm_duplicate=true",
                    status_code=409,
                )
            task_service.update_task(
                task.id,
                status=GenerationTask.STATUS_QUEUED,
                next_retry_at=None,
                lease_owner=None,
                lease_expires_at=None,
                error_code=None,
                error_message=None,
                submission_uncertain=0,
                attempt_count=0,
                completed_at=None,
                cancel_requested=0,
            )
            message = "已重新排队；第三方是否已扣费需人工核对"
        _audit(cfg, "generation_retry", task_id)
        return json_success(_serialize_task(task_service.get_task(task_id), get_asset_service(cfg.DATA_DIR)),
                            message=message)

    @app.route("/api/generation/tasks/<task_id>/timing", methods=["GET"])
    def generation_task_timing(task_id):
        task = require_task(task_id, demo_mode=cfg.DEMO_MODE)
        return json_success(_task_timing(task))

    @app.route("/api/generation/timing/summary", methods=["GET"])
    @admin_required
    def generation_timing_summary():
        task_type = request.args.get("task_type")
        if task_type and task_type not in (GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO):
            raise ApiError("invalid_params", "task_type 只能是 image 或 video", status_code=400)
        try:
            hours = int(request.args.get("hours", 168))
        except (TypeError, ValueError):
            raise ApiError("invalid_params", "hours 必须是整数", status_code=400)
        if hours < 0:
            raise ApiError("invalid_params", "hours 不能为负", status_code=400)
        conditions = []
        params = []
        if task_type:
            conditions.append("task_type = ?")
            params.append(task_type)
        else:
            conditions.append("task_type IN ('image','video')")
        if request.args.get("provider"):
            conditions.append("provider = ?")
            params.append(request.args["provider"])
        if request.args.get("model_id"):
            conditions.append("model_id = ?")
            params.append(request.args["model_id"])
        if request.args.get("status"):
            conditions.append("status = ?")
            params.append(request.args["status"])
        if hours:
            conditions.append("created_at >= ?")
            params.append(int(time.time()) - hours * 3600)
        rows = task_service.db.fetch_all(
            "SELECT * FROM generation_tasks WHERE {0} ORDER BY created_at DESC".format(
                " AND ".join(conditions)
            ),
            tuple(params),
        )
        tasks = [GenerationTask.from_row(row) for row in rows]
        has_reference = request.args.get("has_reference")
        if has_reference in ("1", "0", "true", "false", "yes", "no"):
            wants = has_reference in ("1", "true", "yes")
            filtered = []
            for task in tasks:
                task_params = task.params or {}
                has_ref = bool(
                    task_params.get("reference_asset_id")
                    or task_params.get("reference_asset_ids")
                )
                if has_ref == wants:
                    filtered.append(task)
            tasks = filtered
        timings = [_task_timing(task) for task in tasks]
        metrics = {}
        for key in (
            "queue_wait_ms", "submission_ms", "provider_elapsed_ms",
            "download_ms", "persist_ms", "total_ms",
        ):
            values = [
                item["durations_ms"].get(key)
                for item in timings
                if item["durations_ms"].get(key) is not None
            ]
            metrics[key] = {
                "count": len(values),
                "avg": round(statistics.mean(values), 1) if values else None,
                "median": round(statistics.median(values), 1) if values else None,
                "p95": round(_percentile(values, 95), 1) if values else None,
            }
        success = len([
            task for task in tasks
            if task.status == GenerationTask.STATUS_SUCCEEDED
        ])
        return json_success({
            "count": len(tasks),
            "success_rate": round(success / len(tasks), 4) if tasks else None,
            "filters": {
                "task_type": task_type or "image,video",
                "hours": hours,
                "provider": request.args.get("provider"),
                "model_id": request.args.get("model_id"),
                "status": request.args.get("status"),
                "has_reference": has_reference,
            },
            "durations_ms": metrics,
            "notes": [
                "provider_elapsed_ms 包含服务商排队与运行时间，不等于纯模型推理时间",
                "统计基于 generation_tasks 中已记录的真实阶段时间戳",
            ],
        })

    @app.route("/api/generation/assets/<asset_id>/download", methods=["GET"])
    def generation_asset_download(asset_id):
        asset = require_asset(asset_id, write=False, demo_mode=cfg.DEMO_MODE)
        asset_service = get_asset_service(cfg.DATA_DIR)
        path = asset_service.get_file_path_for_asset(asset)
        if not path or not os.path.isfile(path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))


def _audit(cfg, action, task_id, metadata=None, result="success"):
    if not getattr(cfg, "AUDIT_ENABLED", True):
        return None
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=g.current_user.get("id"),
            tenant_id=g.current_user.get("tenant_id"),
            project_id=None,
            action=action,
            target_type="generation_task",
            target_id=task_id,
            result=result,
            metadata=metadata,
            request_id=getattr(g, "request_id", None),
        )
    except Exception:
        pass
