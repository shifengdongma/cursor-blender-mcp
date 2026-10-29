# -*- coding: utf-8 -*-
"""Business identity provisioning for platform users.

The platform deliberately uses one shared tenant for registered accounts.  The
business ``users`` row shares the auth account UUID, which keeps existing
project/task foreign keys usable without inventing a second ID namespace.
Project membership is a *project* role and never grants the platform admin role.
"""
from __future__ import absolute_import

import json
import os
import time


DEFAULT_PLATFORM_TENANT_ID = "tenant_platform"
DEFAULT_MEMBERSHIP_PERMISSIONS = [
    "submit_job",
    "generate_media",
    "manage_own_projects",
]


def _now():
    return int(time.time())


def platform_tenant_id():
    return os.environ.get("PLATFORM_TENANT_ID", DEFAULT_PLATFORM_TENANT_ID)


def ensure_platform_tenant(cursor, tenant_id=None):
    """Create the shared platform tenant if needed and return its ID."""
    tenant_id = tenant_id or platform_tenant_id()
    cursor.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
    if cursor.fetchone() is None:
        now = _now()
        cursor.execute(
            "INSERT INTO tenants (id, name, code, tier, status, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                "AIGV Studio 平台用户",
                "platform",
                "standard",
                "active",
                json.dumps({"platform": True}, ensure_ascii=False),
                now,
                now,
            ),
        )
    return tenant_id


def provision_business_identity(cursor, auth_user_id, username, nickname=None, tenant_id=None):
    """Create/link the business user, default project and owner membership.

    Must be called inside a Database.transaction() block.
    """
    tenant_id = tenant_id or ensure_platform_tenant(cursor)
    now = _now()
    display_name = (nickname or username or "").strip() or username or auth_user_id

    cursor.execute("SELECT id, tenant_id FROM users WHERE id = ?", (auth_user_id,))
    existing_user = cursor.fetchone()
    if existing_user is None:
        cursor.execute(
            "INSERT INTO users (id, tenant_id, name, role, title, status, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                auth_user_id,
                tenant_id,
                display_name,
                "member",
                None,
                "active",
                json.dumps({"auth_user": True}, ensure_ascii=False),
                now,
                now,
            ),
        )
    else:
        cursor.execute(
            "UPDATE users SET tenant_id = ?, name = ?, status = 'active', updated_at = ? WHERE id = ?",
            (tenant_id, display_name, now, auth_user_id),
        )

    project_id = "workspace_{0}".format(auth_user_id)
    cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO projects (id, tenant_id, name, code, status, render_mode, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                tenant_id,
                "个人工作区",
                "workspace-{0}".format(str(auth_user_id)[:8]),
                "active",
                "cinematic",
                json.dumps({"personal_workspace": True}, ensure_ascii=False),
                now,
                now,
            ),
        )

    membership_id = "membership_workspace_{0}".format(auth_user_id)
    cursor.execute("SELECT id FROM project_memberships WHERE id = ?", (membership_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO project_memberships "
            "(id, project_id, user_id, tenant_id, role, permissions, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                membership_id,
                project_id,
                auth_user_id,
                tenant_id,
                "owner",
                json.dumps(DEFAULT_MEMBERSHIP_PERMISSIONS, ensure_ascii=False),
                now,
                now,
            ),
        )

    return {"tenant_id": tenant_id, "project_id": project_id, "membership_id": membership_id}
