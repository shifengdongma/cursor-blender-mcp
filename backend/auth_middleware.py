# -*- coding: utf-8 -*-
"""Authentication and authorization helpers.

Role resolution and permission checks always use the database-backed user in
``g.current_user`` (installed by backend.web_security).  Client-supplied
user_id/tenant_id/project_id values are never trusted as identity.
"""
from __future__ import absolute_import

import functools
import json
import logging

from flask import g, jsonify, request

from .database import get_database
from .http_utils import api_error

logger = logging.getLogger(__name__)

# ── Permission Constants ──

PERM_VIEW_COMPUTE = 'view_compute'
PERM_MANAGE_COMPUTE = 'manage_compute'
PERM_SUBMIT_RENDER_JOB = 'submit_render_job'
PERM_MANAGE_CLOUD_ACCOUNTS = 'manage_cloud_accounts'
PERM_VIEW_BILLING = 'view_billing'
PERM_VIEW_MONITOR = 'view_monitor'

ALL_COMPUTE_PERMISSIONS = [
    PERM_VIEW_COMPUTE,
    PERM_MANAGE_COMPUTE,
    PERM_SUBMIT_RENDER_JOB,
    PERM_MANAGE_CLOUD_ACCOUNTS,
    PERM_VIEW_BILLING,
    PERM_VIEW_MONITOR,
]


def current_user():
    return getattr(g, 'current_user', None)


def is_admin(user=None):
    user = user or current_user()
    return bool(user and user.get('role') == 'admin' and user.get('status') == 'active')


def _membership_permissions(user, project_id=None):
    if not user:
        return []
    db = get_database()
    if project_id:
        rows = db.fetch_all(
            "SELECT role, permissions FROM project_memberships "
            "WHERE tenant_id = ? AND user_id = ? AND project_id = ?",
            (user.get('tenant_id'), user.get('id'), project_id),
        )
    else:
        rows = db.fetch_all(
            "SELECT role, permissions FROM project_memberships "
            "WHERE tenant_id = ? AND user_id = ?",
            (user.get('tenant_id'), user.get('id')),
        )
    permissions = set()
    for row in rows:
        try:
            values = json.loads(row.get('permissions') or '[]')
        except (TypeError, ValueError):
            values = []
        if isinstance(values, list):
            permissions.update(str(value) for value in values)
    return permissions


def has_permission(permission, user=None, project_id=None):
    user = user or current_user()
    if not user:
        return False
    if is_admin(user):
        return True
    return permission in _membership_permissions(user, project_id=project_id)


def login_required(f):
    """Decorator that requires a valid, DB-revalidated session."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            payload, status_code = api_error('unauthorized', '请先登录', 401)
            return jsonify(payload), status_code
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Require the platform admin role (never a project owner role)."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user:
            payload, status_code = api_error('unauthorized', '请先登录', 401)
            return jsonify(payload), status_code
        if not is_admin(user):
            payload, status_code = api_error('forbidden', '需要平台管理员权限', 403)
            return jsonify(payload), status_code
        return f(*args, **kwargs)

    return decorated


def permission_required(permission):
    """Require an explicit membership permission or platform admin.

    For project-scoped routes the project_id comes from the route's view_args.
    For global compute routes, holding the permission in any membership is
    sufficient.  Project owner/editor roles alone do not bypass the permission
    list, so a personal workspace owner does not gain cloud-admin powers.
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = current_user()
            if not user:
                payload, status_code = api_error('unauthorized', '请先登录', 401)
                return jsonify(payload), status_code
            if is_admin(user):
                return f(*args, **kwargs)

            project_id = (request.view_args or {}).get('project_id')
            if not has_permission(permission, user=user, project_id=project_id):
                payload, status_code = api_error(
                    'forbidden',
                    '您没有执行此操作的权限 ({0})'.format(permission),
                    403,
                    details={'required_permission': permission},
                )
                return jsonify(payload), status_code

            return f(*args, **kwargs)

        return decorated

    return decorator
