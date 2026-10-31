# -*- coding: utf-8 -*-
"""Platform administrator API: user management, stats and audit logs."""
from __future__ import absolute_import

import os
from datetime import datetime, timedelta, timezone

from flask import g, request, send_file, send_from_directory

from .audit_presenter import (
    actor_filter_clause,
    fetch_event,
    filter_options,
    present_event_detail,
    present_events,
)
from .auth_middleware import admin_required
from .auth_service import AuthError
from .database import get_database
from .http_utils import ApiError, parse_json_body, parse_pagination
from .models import GenerationTask

_BEIJING_TZ = timezone(timedelta(hours=8))
_RESULT_ALIASES = {
    'succeeded': 'success',
    'failure': 'failed',
    'canceled': 'cancelled',
    'completed': 'success',
}


def _parse_audit_day(value, field):
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=_BEIJING_TZ)
    except (TypeError, ValueError):
        raise ApiError(
            'invalid_date',
            '日期格式应为 YYYY-MM-DD',
            status_code=400,
            details={'field': field},
        )
    return int(parsed.timestamp())


def _audit(cfg, action, actor, target_id=None, result="success", metadata=None):
    if not getattr(cfg, "AUDIT_ENABLED", True):
        return None
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=(actor or {}).get("id"),
            tenant_id=(actor or {}).get("tenant_id"),
            project_id=None,
            action=action,
            target_type="user" if target_id else None,
            target_id=target_id,
            result=result,
            metadata=metadata,
            request_id=getattr(g, "request_id", None),
        )
    except Exception:
        pass


def _avatar_path(cfg, rel_path):
    if not rel_path:
        return None
    root = os.path.realpath(os.path.join(cfg.DATA_DIR, "profile_avatars"))
    candidate = os.path.realpath(os.path.join(cfg.DATA_DIR, rel_path))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate


def _with_avatar(user):
    if not user:
        return user
    item = dict(user)
    if item.get("has_avatar"):
        item["avatar_url"] = "/api/admin/users/{0}/avatar?t={1}".format(
            item.get("id"), item.get("updated_at") or 0
        )
    else:
        item["avatar_url"] = None
    return item


def _user_stats(user_id):
    db = get_database()
    tasks = db.count("generation_tasks", "created_by = ?", (user_id,))
    projects = db.count("creative_projects", "user_id = ?", (user_id,))
    assets = db.count("assets", "owner_user_id = ?", (user_id,))
    rows = db.fetch_all(
        "SELECT * FROM generation_tasks WHERE created_by = ? ORDER BY created_at DESC LIMIT 5",
        (user_id,),
    )
    recent = []
    for row in rows:
        task = GenerationTask.from_row(row)
        recent.append(
            {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "error_code": task.error_code,
            }
        )
    return {
        "tasks": tasks,
        "projects": projects,
        "assets": assets,
        "recent_tasks": recent,
    }


def register_admin_routes(app, cfg, auth_service, web_root, json_success, json_error):
    @app.route("/admin/users", methods=["GET"])
    def admin_users_page():
        return send_from_directory(web_root, "admin-users.html")

    @app.route("/api/admin/users", methods=["GET"])
    @admin_required
    def admin_list_users():
        pagination = parse_pagination(request, default_limit=20, max_limit=200)
        q = request.args.get("q")
        role = request.args.get("role")
        status = request.args.get("status")
        result = auth_service.list_users(
            q=q, role=role, status=status,
            limit=pagination.limit, offset=pagination.offset,
        )
        result["items"] = [_with_avatar(item) for item in result["items"]]
        return json_success(result)

    @app.route("/api/admin/users/<user_id>", methods=["GET"])
    @admin_required
    def admin_get_user(user_id):
        user = auth_service.get_user(user_id)
        if not user:
            raise ApiError("user_not_found", "用户不存在", status_code=404)
        payload = _with_avatar(auth_service.public_user(user))
        payload["bio"] = user.get("bio") or ""
        payload["stats"] = _user_stats(user_id)
        return json_success(payload)

    @app.route("/api/admin/users/<user_id>", methods=["PATCH"])
    @admin_required
    def admin_update_user(user_id):
        data = parse_json_body(request)
        updates = {key: data.get(key) for key in ("nickname", "email", "bio") if key in data}
        try:
            user = auth_service.admin_update_profile(user_id, **updates)
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(cfg, "admin_user_update", g.current_user, target_id=user_id, metadata={"fields": sorted(updates)})
        return json_success(_with_avatar(auth_service.public_user(user)), message="用户资料已更新")

    @app.route("/api/admin/users/<user_id>/role", methods=["PATCH"])
    @admin_required
    def admin_update_role(user_id):
        data = parse_json_body(request)
        role = data.get("role")
        before = auth_service.get_user(user_id)
        if not before:
            raise ApiError("user_not_found", "用户不存在", status_code=404)
        try:
            user = auth_service.admin_update_role(user_id, role, g.current_user.get("id"))
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(
            cfg, "admin_role_change", g.current_user, target_id=user_id,
            metadata={"before": before.get("role"), "after": role},
        )
        return json_success(_with_avatar(auth_service.public_user(user)), message="用户角色已更新")

    @app.route("/api/admin/users/<user_id>/status", methods=["PATCH"])
    @admin_required
    def admin_update_status(user_id):
        data = parse_json_body(request)
        status = data.get("status")
        before = auth_service.get_user(user_id)
        if not before:
            raise ApiError("user_not_found", "用户不存在", status_code=404)
        try:
            user = auth_service.admin_update_status(user_id, status, g.current_user.get("id"))
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(
            cfg, "admin_status_change", g.current_user, target_id=user_id,
            metadata={"before": before.get("status"), "after": status},
        )
        return json_success(_with_avatar(auth_service.public_user(user)), message="用户状态已更新")

    @app.route("/api/admin/users/<user_id>/sessions/revoke", methods=["POST"])
    @admin_required
    def admin_revoke_sessions(user_id):
        try:
            auth_service.revoke_sessions(user_id)
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code)
        _audit(cfg, "admin_revoke_sessions", g.current_user, target_id=user_id)
        return json_success({"revoked": True}, message="该用户的所有会话已失效")

    @app.route("/api/admin/users/<user_id>/avatar", methods=["GET"])
    @admin_required
    def admin_get_avatar(user_id):
        user = auth_service.get_user(user_id)
        if not user:
            raise ApiError("user_not_found", "用户不存在", status_code=404)
        path = _avatar_path(cfg, user.get("avatar_path"))
        if not path or not os.path.isfile(path):
            raise ApiError("avatar_not_found", "未设置头像", status_code=404)
        response = send_file(path, conditional=True)
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    @app.route("/api/admin/stats", methods=["GET"])
    @admin_required
    def admin_stats():
        stats = auth_service.admin_stats()
        stats["recent_users"] = [_with_avatar(item) for item in stats.get("recent_users", [])]
        stats["generated_at"] = int(__import__("time").time())
        return json_success(stats)

    @app.route("/api/admin/audit-logs", methods=["GET"])
    @admin_required
    def admin_audit_logs():
        pagination = parse_pagination(request, default_limit=50, max_limit=200)
        # Keep the old ``action`` alias; ``event_type`` is the new preferred
        # name.  ``actor_user_id`` is also kept for existing clients.
        event_type = request.args.get("event_type") or request.args.get("action")
        result = request.args.get("result")
        actor = request.args.get("actor") or request.args.get("actor_user_id")
        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()

        conditions = []
        params = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if result:
            normalized_result = _RESULT_ALIASES.get(result, result)
            conditions.append("message = ?")
            params.append(normalized_result)
        if actor:
            clause, _ = actor_filter_clause()
            conditions.append(clause)
            params.extend([actor, actor, actor])

        start_ts = _parse_audit_day(start_date, "start_date") if start_date else None
        if end_date:
            end_ts = _parse_audit_day(end_date, "end_date") + 86400
        else:
            end_ts = None
        if start_ts is not None and end_ts is not None and start_ts >= end_ts:
            raise ApiError(
                "invalid_date_range",
                "开始日期不能晚于结束日期",
                status_code=400,
            )
        if start_ts is not None:
            conditions.append("created_at >= ?")
            params.append(start_ts)
        if end_ts is not None:
            conditions.append("created_at < ?")
            params.append(end_ts)

        where = " AND ".join(conditions) if conditions else "1=1"
        db = get_database()
        rows = db.fetch_all(
            "SELECT * FROM ops_events WHERE {0} "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?".format(where),
            tuple(params) + (pagination.limit, pagination.offset),
        )
        total = db.count("ops_events", where, tuple(params) if params else None)
        items = present_events(db, rows)
        return json_success(
            {
                "items": items,
                "total": total,
                "limit": pagination.limit,
                "offset": pagination.offset,
                "filters": {
                    "event_type": event_type or None,
                    "result": result or None,
                    "actor": actor or None,
                    "start_date": start_date or None,
                    "end_date": end_date or None,
                },
                "filter_options": filter_options(),
                "source": "ops_events",
                "source_label": "平台审计日志（只读）",
            }
        )

    @app.route("/api/admin/audit-logs/<event_id>", methods=["GET"])
    @admin_required
    def admin_audit_log_detail(event_id):
        db = get_database()
        event = fetch_event(db, event_id)
        if not event:
            raise ApiError("audit_event_not_found", "审计事件不存在", status_code=404)
        return json_success(present_event_detail(db, event))
