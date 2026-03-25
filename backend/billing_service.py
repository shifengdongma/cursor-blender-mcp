from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import BillingUsageRecord, BillingAccount


class BillingService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def build_job_billing(self, job_id, payload, schedule_result, stream_session):
        gpu_hours = round(float(payload.get('duration_s') or 6) / 3600.0, 4)
        engine_hours = round(gpu_hours * 1.15, 4)
        stream_hours = round(gpu_hours * 1.25, 4)
        amount = round(gpu_hours * 120 + engine_hours * 80 + stream_hours * 40, 2)
        snapshot = {
            'job_id': job_id,
            'tenant_id': payload.get('tenant_id'),
            'project_id': payload.get('project_id'),
            'currency': 'CNY',
            'gpu_hours': gpu_hours,
            'engine_hours': engine_hours,
            'stream_hours': stream_hours,
            'amount': amount,
            'line_items': [
                {'name': 'GPU 调度', 'units': gpu_hours, 'unit_price': 120, 'subtotal': round(gpu_hours * 120, 2)},
                {'name': '引擎会话', 'units': engine_hours, 'unit_price': 80, 'subtotal': round(engine_hours * 80, 2)},
                {'name': '编码推流', 'units': stream_hours, 'unit_price': 40, 'subtotal': round(stream_hours * 40, 2)},
            ],
            'resource_node': ((schedule_result or {}).get('node') or {}).get('node_name'),
            'stream_profile': (stream_session or {}).get('profile'),
            'recorded_at': int(time.time()),
        }
        record = BillingUsageRecord(
            job_id=job_id,
            tenant_id=payload.get('tenant_id'),
            project_id=payload.get('project_id'),
            amount=amount,
            currency='CNY',
            usage_type='job_run',
            usage_units=gpu_hours,
            metadata=snapshot,
        )
        self.db.insert(BillingUsageRecord.TABLE_NAME, record.to_insert_params())
        return snapshot

    def get_job_billing(self, job_id):
        row = self.db.fetch_one('SELECT * FROM billing_usage_records WHERE job_id = ? ORDER BY created_at DESC LIMIT 1', (job_id,))
        item = BillingUsageRecord.from_row(row)
        return item.to_dict() if item else None

    def get_billing_summary(self):
        rows = self.db.fetch_all('SELECT * FROM billing_accounts ORDER BY created_at ASC')
        accounts = [BillingAccount.from_row(row).to_dict() for row in rows]
        usage_rows = self.db.fetch_all('SELECT * FROM billing_usage_records ORDER BY created_at DESC LIMIT 20')
        usage = [BillingUsageRecord.from_row(row).to_dict() for row in usage_rows]
        total_amount = round(sum(float(item.get('amount') or 0.0) for item in usage), 2)
        return {
            'accounts': accounts,
            'recent_usage': usage,
            'total_amount': total_amount,
            'currency': 'CNY',
        }

    def get_project_usage(self, project_id):
        rows = self.db.fetch_all('SELECT * FROM billing_usage_records WHERE project_id = ? ORDER BY created_at DESC', (project_id,))
        items = [BillingUsageRecord.from_row(row).to_dict() for row in rows]
        total_amount = round(sum(float(item.get('amount') or 0.0) for item in items), 2)
        return {
            'project_id': project_id,
            'records': items,
            'total_amount': total_amount,
            'currency': 'CNY',
        }


def get_billing_service(data_dir=None):
    return BillingService(data_dir)
