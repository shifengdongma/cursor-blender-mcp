# -*- coding: utf-8 -*-
"""
Audit Service: User action audit trail for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import logging
import os

from .database import get_database
from .ops_service import (
    OpsService,
    EVENT_LOGIN, EVENT_LOGOUT, EVENT_LOGIN_FAILED, EVENT_PASSWORD_CHANGE,
    EVENT_PROJECT_CREATE, EVENT_PROJECT_DELETE,
    EVENT_STORYBOARD_GENERATE, EVENT_IMAGE_SUBMIT, EVENT_VIDEO_SUBMIT,
    EVENT_RENDER_SUBMIT, EVENT_TASK_CANCEL, EVENT_TASK_RETRY,
    EVENT_RESOURCE_ALLOCATE, EVENT_RESOURCE_REASSIGN,
    EVENT_ALERT_ACKNOWLEDGE, EVENT_ALERT_CLOSE,
    EVENT_PERMISSION_CHANGE, EVENT_PERMISSION_GRANT, EVENT_PERMISSION_REVOKE,
    EVENT_CLOUD_SYNC, EVENT_EXPORT_DOWNLOAD,
    SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR,
)

logger = logging.getLogger(__name__)

# Sensitive field patterns to never log
_SENSITIVE_PATTERNS = (
    'password', 'secret', 'api_key', 'token', 'credential',
    'access_key', 'private_key',
)


class AuditService(object):
    """Audit trail service wrapping OpsService with sensitive data filtering."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.ops = OpsService(self.data_dir)

    def _sanitize_metadata(self, metadata):
        """Remove sensitive fields from metadata."""
        if not metadata:
            return None
        sanitized = {}
        for key, val in metadata.items():
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in _SENSITIVE_PATTERNS):
                sanitized[key] = '[REDACTED]'
            elif isinstance(val, dict):
                sanitized[key] = self._sanitize_metadata(val)
            else:
                sanitized[key] = val
        return sanitized

    def record_audit(self, user_id, tenant_id, project_id, action,
                     target_type=None, target_id=None, result='success',
                     metadata=None, request_id=None, severity=None):
        """Record an audit trail event."""
        audit_metadata = self._sanitize_metadata(metadata) or {}
        if request_id:
            audit_metadata['request_id'] = request_id
        # Keep a safe identity clue for future deleted/changed users.  The
        # snapshot is display-only and never contains credentials or email.
        try:
            from .audit_presenter import build_actor_snapshot
            actor_display = build_actor_snapshot(self.ops.db, user_id)
            if actor_display:
                audit_metadata['actor_display'] = actor_display
        except Exception:
            pass

        return self.ops.record_event(
            tenant_id=tenant_id,
            project_id=project_id,
            job_id=None,
            event_type=action,
            severity=severity or SEVERITY_INFO,
            message=result,
            metadata={
                'user_id': user_id,
                'target_type': target_type,
                'target_id': target_id,
                'request_id': request_id,
                'details': audit_metadata,
            },
            actor_user_id=user_id,
            request_id=request_id,
        )

    def record_login(self, user_id, tenant_id, success=True, metadata=None, request_id=None):
        action = EVENT_LOGIN if success else EVENT_LOGIN_FAILED
        return self.record_audit(
            user_id=user_id, tenant_id=tenant_id, project_id=None,
            action=action, result='success' if success else 'failed',
            metadata=metadata, request_id=request_id,
            severity=SEVERITY_INFO if success else SEVERITY_WARNING,
        )

    def record_logout(self, user_id, tenant_id, request_id=None):
        return self.record_audit(
            user_id=user_id, tenant_id=tenant_id, project_id=None,
            action=EVENT_LOGOUT, result='success', request_id=request_id,
        )

    def record_password_change(self, user_id, tenant_id, success=True, request_id=None):
        return self.record_audit(
            user_id=user_id, tenant_id=tenant_id, project_id=None,
            action=EVENT_PASSWORD_CHANGE, result='success' if success else 'failed',
            request_id=request_id,
        )

    def record_permission_change(self, user_id, tenant_id, project_id, change_type,
                                  target_user_id, details=None, request_id=None):
        return self.record_audit(
            user_id=user_id, tenant_id=tenant_id, project_id=project_id,
            action=change_type, target_type='user', target_id=target_user_id,
            metadata=details, request_id=request_id,
        )

    def list_audit_events(self, project_id=None, user_id=None, action=None, limit=100):
        """List audit events with optional filters."""
        conditions = []
        params = []

        if project_id:
            conditions.append('project_id = ?')
            params.append(project_id)
        if action:
            conditions.append('event_type = ?')
            params.append(action)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        query = 'SELECT * FROM ops_events WHERE {0} ORDER BY created_at DESC LIMIT ?'.format(where_clause)
        params.append(limit)

        rows = self.ops.db.fetch_all(query, tuple(params))
        from .models import OpsEvent
        results = []
        for row in rows:
            event = OpsEvent.from_row(row).to_dict()
            # Filter by user_id if provided
            if user_id:
                meta = event.get('metadata') or {}
                if isinstance(meta, dict) and meta.get('user_id') != user_id:
                    continue
            results.append(event)
        return results


def get_audit_service(data_dir=None):
    return AuditService(data_dir)
