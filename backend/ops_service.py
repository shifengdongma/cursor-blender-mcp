from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import OpsEvent

# ── Event Type Constants ──

EVENT_NODE_ONLINE = 'node_online'
EVENT_NODE_OFFLINE = 'node_offline'
EVENT_NODE_ERROR = 'node_error'
EVENT_NODE_MAINTENANCE = 'node_maintenance'
EVENT_RENDER_STARTED = 'render_started'
EVENT_RENDER_PROGRESS = 'render_progress'
EVENT_RENDER_SUCCEEDED = 'render_succeeded'
EVENT_RENDER_FAILED = 'render_failed'
EVENT_RENDER_CANCELLED = 'render_cancelled'
EVENT_HEALTH_CHECK = 'health_check'
EVENT_SCHEDULE_ALLOCATION = 'schedule_allocation'
EVENT_PROVIDER_SYNC = 'provider_sync'

# ── Audit Trail Events ──
EVENT_LOGIN = 'login'
EVENT_LOGOUT = 'logout'
EVENT_LOGIN_FAILED = 'login_failed'
EVENT_PASSWORD_CHANGE = 'password_change'
EVENT_PROJECT_CREATE = 'project_create'
EVENT_PROJECT_DELETE = 'project_delete'
EVENT_STORYBOARD_GENERATE = 'storyboard_generate'
EVENT_IMAGE_SUBMIT = 'image_submit'
EVENT_VIDEO_SUBMIT = 'video_submit'
EVENT_RENDER_SUBMIT = 'render_submit'
EVENT_TASK_CANCEL = 'task_cancel'
EVENT_TASK_RETRY = 'task_retry'
EVENT_RESOURCE_ALLOCATE = 'resource_allocate'
EVENT_RESOURCE_REASSIGN = 'resource_reassign'
EVENT_ALERT_ACKNOWLEDGE = 'alert_acknowledge'
EVENT_ALERT_CLOSE = 'alert_close'
EVENT_PERMISSION_CHANGE = 'permission_change'
EVENT_PERMISSION_GRANT = 'permission_grant'
EVENT_PERMISSION_REVOKE = 'permission_revoke'
EVENT_CLOUD_SYNC = 'cloud_sync'
EVENT_EXPORT_DOWNLOAD = 'export_download'
EVENT_SCHEDULE_RESCHEDULE = 'schedule_reschedule'

# ── Severity Constants ──

SEVERITY_INFO = 'info'
SEVERITY_WARNING = 'warning'
SEVERITY_ERROR = 'error'


class OpsService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def record_event(self, tenant_id, project_id, job_id, event_type, severity, message,
                     metadata=None, actor_user_id=None, request_id=None):
        event = OpsEvent(
            tenant_id=tenant_id,
            project_id=project_id,
            job_id=job_id,
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata or {},
            actor_user_id=actor_user_id,
            request_id=request_id,
        )
        self.db.insert(OpsEvent.TABLE_NAME, event.to_insert_params())
        return event.to_dict()

    def list_events(self, project_id=None, limit=50):
        if project_id:
            rows = self.db.fetch_all(
                'SELECT * FROM ops_events WHERE project_id = ? ORDER BY created_at DESC LIMIT ?',
                (project_id, limit)
            )
        else:
            rows = self.db.fetch_all('SELECT * FROM ops_events ORDER BY created_at DESC LIMIT ?', (limit,))
        return [OpsEvent.from_row(row).to_dict() for row in rows]

    def record_audit(self, user_id, tenant_id, project_id, action,
                     target_type=None, target_id=None, result='success',
                     metadata=None, request_id=None):
        """Record an audit trail event with user context."""
        audit_metadata = metadata or {}
        if request_id:
            audit_metadata['request_id'] = request_id

        # Sanitize: never log passwords, API keys, secrets
        sanitized = {}
        for key, val in audit_metadata.items():
            if any(secret in key.lower() for secret in ('password', 'secret', 'api_key', 'token')):
                continue
            sanitized[key] = val

        return self.record_event(
            tenant_id=tenant_id,
            project_id=project_id,
            job_id=None,
            event_type=action,
            severity=SEVERITY_INFO,
            message=result,
            metadata={
                'user_id': user_id,
                'target_type': target_type,
                'target_id': target_id,
                'details': sanitized,
            },
            actor_user_id=user_id,
            request_id=request_id,
        )


def get_ops_service(data_dir=None):
    return OpsService(data_dir)
