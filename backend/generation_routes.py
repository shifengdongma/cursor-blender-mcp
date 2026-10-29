# -*- coding: utf-8 -*-
"""Real image/video generation API."""
from __future__ import absolute_import

import logging
import os
from datetime import datetime, timezone

from flask import g, request, send_file

from .access import require_asset, require_task
from .asset_service import get_asset_service
from .auth_middleware import admin_required, is_admin
from .database import get_database
from .generation_models import list_models
from .http_utils import ApiError, parse_json_body, parse_pagination
from .models import GenerationTask
from .task_service import get_task_service
from .task_serializer import public_task_dict
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
        parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ApiError("invalid_params", "日期格式应为 YYYY-MM-DD", status_code=400)
    timestamp = int(parsed.timestamp())
    return timestamp + 86399 if end_of_day else timestamp


def _client_request_id(payload):
    return (request.headers.get("Idempotency-Key") or payload.get("client_request_id") or "")[:128] or None


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
        result = task_service.list_tasks(
            creative_project_id=project_id,
            task_type=task_type,
            task_types=(GenerationTask.TYPE_IMAGE, GenerationTask.TYPE_VIDEO),
            status=status,
            created_by=created_by,
            limit=pagination.limit,
            offset=pagination.offset,
            created_after=_parse_date(request.args.get("date_from")),
            created_before=_parse_date(request.args.get("date_to"), end_of_day=True),
            model_id=request.args.get("model_id"),
        )
        asset_service = get_asset_service(cfg.DATA_DIR)
        result["items"] = [
            _serialize_task(task_service.get_task(item.get("id")), asset_service)
            for item in result.get("items", [])
        ]
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

    @app.route("/api/generation/assets/<asset_id>/download", methods=["GET"])
    def generation_asset_download(asset_id):
        asset = require_asset(asset_id, write=False, demo_mode=cfg.DEMO_MODE)
        asset_service = get_asset_service(cfg.DATA_DIR)
        path = asset_service.get_file_path_for_asset(asset)
        if not path or not os.path.isfile(path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)
        return send_file(path, as_attachment=True, download_name=os.path.basename(path))


def _audit(cfg, action, task_id):
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=g.current_user.get("id"),
            tenant_id=g.current_user.get("tenant_id"),
            project_id=None,
            action=action,
            target_type="generation_task",
            target_id=task_id,
            result="success",
            request_id=getattr(g, "request_id", None),
        )
    except Exception:
        pass
