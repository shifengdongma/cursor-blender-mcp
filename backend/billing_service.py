"""Billing service with real time-based calculation and balance deduction."""
from __future__ import absolute_import

import logging
import os
import time

from .config import Config
from .database import get_database
from .models import BillingUsageRecord, BillingAccount, RenderJob

logger = logging.getLogger(__name__)


def _parse_gpu_price_map(raw):
    """Parse GPU_PRICE_MAP env var: 'A100:150,A10:80,L40:120' → dict."""
    mapping = {}
    if raw:
        for pair in raw.split(','):
            parts = pair.strip().split(':')
            if len(parts) == 2:
                try:
                    mapping[parts[0].strip()] = float(parts[1].strip())
                except ValueError:
                    pass
    return mapping


class BillingService(object):
    def __init__(self, data_dir=None, cfg=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.cfg = cfg or Config()
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._gpu_prices = _parse_gpu_price_map(self.cfg.GPU_PRICE_MAP)

    def build_job_billing(self, job_id, payload, schedule_result, stream_session):
        """Build billing for a job.

        If a render_job record exists with started_at/finished_at, use real
        timestamps. Otherwise, fall back to the duration_s from the payload.
        """
        # Try to find a render_job record for real timestamps
        render_job_row = self.db.fetch_one(
            'SELECT * FROM render_jobs WHERE id = ?',
            (job_id,)
        )

        gpu_hours = 0.0
        usage_seconds = None
        unit_price = None
        node_id = None
        provider = None

        if render_job_row:
            rj = RenderJob.from_row(render_job_row)
            render_dict = rj.to_dict()
            started_at = render_dict.get('started_at')
            finished_at = render_dict.get('finished_at')

            if started_at and finished_at and finished_at > started_at:
                usage_seconds = finished_at - started_at
                gpu_hours = round(float(usage_seconds) / 3600.0, 4)

                # Get node details for GPU type and pricing
                node_id = render_dict.get('node_id')
                if node_id:
                    node_row = self.db.fetch_one(
                        'SELECT gpu_type, provider_type FROM compute_nodes WHERE id = ?',
                        (node_id,)
                    )
                    if node_row:
                        gpu_type = node_row.get('gpu_type') or ''
                        unit_price = self._gpu_prices.get(gpu_type, self.cfg.GPU_UNIT_PRICE_CNY)
                        provider = node_row.get('provider_type')

        # Fallback: use payload-based calculation
        if not usage_seconds:
            gpu_hours = round(float(payload.get('duration_s') or 6) / 3600.0, 4)
            unit_price = self.cfg.GPU_UNIT_PRICE_CNY

        engine_hours = round(gpu_hours * 1.15, 4)
        stream_hours = round(gpu_hours * 1.25, 4)
        amount = round(gpu_hours * (unit_price or 120) + engine_hours * self.cfg.ENGINE_UNIT_PRICE_CNY + stream_hours * self.cfg.STREAM_UNIT_PRICE_CNY, 2)

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
                {'name': 'GPU 调度', 'units': gpu_hours, 'unit_price': unit_price or self.cfg.GPU_UNIT_PRICE_CNY, 'subtotal': round(gpu_hours * (unit_price or self.cfg.GPU_UNIT_PRICE_CNY), 2)},
                {'name': '引擎会话', 'units': engine_hours, 'unit_price': self.cfg.ENGINE_UNIT_PRICE_CNY, 'subtotal': round(engine_hours * self.cfg.ENGINE_UNIT_PRICE_CNY, 2)},
                {'name': '编码推流', 'units': stream_hours, 'unit_price': self.cfg.STREAM_UNIT_PRICE_CNY, 'subtotal': round(stream_hours * self.cfg.STREAM_UNIT_PRICE_CNY, 2)},
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
            render_job_id=job_id if render_job_row else None,
            node_id=node_id,
            provider=provider,
            usage_seconds=usage_seconds,
            unit_price=unit_price,
            metadata=snapshot,
        )
        self.db.insert(BillingUsageRecord.TABLE_NAME, record.to_insert_params())
        return snapshot

    def finalize_billing(self, job_id):
        """Finalize billing: insert record and deduct from billing_accounts.balance."""
        # Re-build billing with the latest data
        render_row = self.db.fetch_one('SELECT * FROM render_jobs WHERE id = ?', (job_id,))
        if not render_row:
            raise ValueError('No render_job found for billing: {0}'.format(job_id))

        rj = RenderJob.from_row(render_row)
        rj_dict = rj.to_dict()

        usage_seconds = None
        if rj_dict.get('started_at') and rj_dict.get('finished_at'):
            usage_seconds = rj_dict['finished_at'] - rj_dict['started_at']

        gpu_hours = round(float(usage_seconds or 0) / 3600.0, 4)
        node_id = rj_dict.get('node_id')
        unit_price = self.cfg.GPU_UNIT_PRICE_CNY

        if node_id:
            node_row = self.db.fetch_one('SELECT gpu_type FROM compute_nodes WHERE id = ?', (node_id,))
            if node_row and node_row.get('gpu_type'):
                unit_price = self._gpu_prices.get(node_row.get('gpu_type'), self.cfg.GPU_UNIT_PRICE_CNY)

        amount = round(gpu_hours * unit_price, 2)

        # Insert record
        record = BillingUsageRecord(
            job_id=job_id,
            tenant_id=rj_dict.get('tenant_id'),
            project_id=rj_dict.get('project_id'),
            amount=amount,
            currency='CNY',
            usage_type='render_job',
            usage_units=gpu_hours,
            render_job_id=job_id,
            node_id=node_id,
            usage_seconds=usage_seconds,
            unit_price=unit_price,
            metadata={
                'job_id': job_id,
                'gpu_hours': gpu_hours,
                'usage_seconds': usage_seconds,
                'unit_price': unit_price,
                'finalized_at': int(time.time()),
            },
        )
        self.db.insert(BillingUsageRecord.TABLE_NAME, record.to_insert_params())

        # Deduct from billing account
        project_id = rj_dict.get('project_id')
        if project_id:
            account_rows = self.db.fetch_all(
                'SELECT * FROM billing_accounts WHERE project_id = ? ORDER BY created_at ASC',
                (project_id,)
            )
            for acct_row in account_rows:
                acct = BillingAccount.from_row(acct_row)
                new_balance = max(0.0, (acct.balance or 0.0) - amount)
                self.db.update(
                    BillingAccount.TABLE_NAME,
                    {'balance': new_balance, 'updated_at': int(time.time())},
                    'id = ?',
                    (acct.id,)
                )
                logger.info('Billing finalized: job=%s amount=%s balance=%s->%s',
                            job_id, amount, acct.balance, new_balance)

        return record.to_dict()

    def get_job_billing(self, job_id):
        row = self.db.fetch_one(
            'SELECT * FROM billing_usage_records WHERE job_id = ? ORDER BY created_at DESC LIMIT 1',
            (job_id,)
        )
        item = BillingUsageRecord.from_row(row)
        return item.to_dict() if item else None

    def get_billing_summary(self):
        rows = self.db.fetch_all('SELECT * FROM billing_accounts ORDER BY created_at ASC')
        accounts = [BillingAccount.from_row(row).to_dict() for row in rows]

        usage_rows = self.db.fetch_all(
            'SELECT * FROM billing_usage_records ORDER BY created_at DESC LIMIT 20'
        )
        usage = [BillingUsageRecord.from_row(row).to_dict() for row in usage_rows]
        total_amount = round(sum(float(item.get('amount') or 0.0) for item in usage), 2)

        # Render job stats
        render_count = self.db.count('render_jobs')
        render_running = self.db.count('render_jobs', "status = 'rendering'")

        return {
            'accounts': accounts,
            'recent_usage': usage,
            'total_amount': total_amount,
            'currency': 'CNY',
            'render_stats': {
                'total_render_jobs': render_count,
                'active_render_jobs': render_running,
            },
        }

    def get_project_usage(self, project_id):
        rows = self.db.fetch_all(
            'SELECT * FROM billing_usage_records WHERE project_id = ? ORDER BY created_at DESC',
            (project_id,)
        )
        items = [BillingUsageRecord.from_row(row).to_dict() for row in rows]
        total_amount = round(sum(float(item.get('amount') or 0.0) for item in items), 2)
        return {
            'project_id': project_id,
            'records': items,
            'total_amount': total_amount,
            'currency': 'CNY',
        }


def get_billing_service(data_dir=None, cfg=None):
    return BillingService(data_dir, cfg)
