# -*- coding: utf-8 -*-
"""
Permission enforcement middleware for AIGV Studio.
Provides decorators for route-level authentication and authorization.
"""
from __future__ import absolute_import

import functools
import logging

from flask import jsonify, session

from .http_utils import api_error
from .tenant_service import get_tenant_service

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


def login_required(f):
    """Decorator that requires a valid user session.

    Returns 401 if no user is logged in.
    """

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = session.get('user')
        if not user:
            payload, status_code = api_error('unauthorized', '请先登录', 401)
            return jsonify(payload), status_code
        return f(*args, **kwargs)

    return decorated


def permission_required(permission):
    """Decorator that checks a specific permission.

    Must be used together with @login_required (applied first).
    Assumes session['user'] is set and contains 'id' and 'tenant_id'.
    The request must have 'project_id' available via request.args or request.view_args.

    Returns 403 if permission is denied. admin/owner roles bypass.
    """

    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            from flask import request

            user = session.get('user')
            if not user:
                payload, status_code = api_error('unauthorized', '请先登录', 401)
                return jsonify(payload), status_code

            # Allow admins and owners to bypass permission check
            user_role = user.get('role', '')
            if user_role in ('owner', 'admin'):
                return f(*args, **kwargs)

            tenant_id = user.get('tenant_id') or user.get('id', '').split('_')[0] if '_' in user.get('id', '') else 'tenant_museum_group'
            user_id = user.get('id', '')

            # Get project_id from request (args, view_args, or JSON body)
            project_id = (
                request.args.get('project_id') or
                request.args.get('projectId') or
                (request.view_args or {}).get('project_id') or
                request.args.get('demo_project_id', 'project_mid_demo')
            )

            ts = get_tenant_service()
            if not ts.check_permission(tenant_id, user_id, project_id, permission):
                payload, status_code = api_error(
                    'forbidden',
                    '您没有执行此操作的权限 ({0})'.format(permission),
                    403,
                    details={'required_permission': permission, 'project_id': project_id}
                )
                return jsonify(payload), status_code

            return f(*args, **kwargs)

        return decorated

    return decorator
