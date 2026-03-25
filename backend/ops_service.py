from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import OpsEvent


class OpsService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def record_event(self, tenant_id, project_id, job_id, event_type, severity, message, metadata=None):
        event = OpsEvent(
            tenant_id=tenant_id,
            project_id=project_id,
            job_id=job_id,
            event_type=event_type,
            severity=severity,
            message=message,
            metadata=metadata or {},
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


def get_ops_service(data_dir=None):
    return OpsService(data_dir)
