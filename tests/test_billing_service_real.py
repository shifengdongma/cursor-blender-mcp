# -*- coding: utf-8 -*-
"""Tests for the real billing service with time-based calculation."""
from __future__ import absolute_import

import os
import tempfile
import time

import pytest


@pytest.fixture
def cfg():
    from backend.config import Config
    cfg = Config()
    cfg.GPU_PRICE_MAP = "A100:150,A10:80,L40:120"
    cfg.GPU_UNIT_PRICE_CNY = 100
    return cfg


@pytest.fixture
def fresh_env():
    """Provide a fresh DATA_DIR per test."""
    tmp = tempfile.mkdtemp(prefix="aigv_billing_")
    old = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tmp
    yield tmp
    os.environ["DATA_DIR"] = old or "./data"


@pytest.fixture
def svc(cfg, fresh_env):
    from backend.database import get_database, reset_database
    from backend.models import Tenant, Project
    from backend.billing_service import BillingService

    reset_database()
    db = get_database()

    t = Tenant(id='tenant-bill', name='Billing Test', code='bt', tier='premium', status='active')
    db.insert(Tenant.TABLE_NAME, t.to_insert_params())
    p = Project(id='proj-bill', tenant_id='tenant-bill', name='Test Project', status='active')
    db.insert(Project.TABLE_NAME, p.to_insert_params())

    yield BillingService(cfg=cfg)

    reset_database()


# ── Tests ──

class TestBillingService:

    def test_gpu_price_map_parsing(self):
        from backend.billing_service import _parse_gpu_price_map
        mapping = _parse_gpu_price_map("A100:150,A10:80,L40:120")
        assert mapping == {'A100': 150.0, 'A10': 80.0, 'L40': 120.0}

    def test_gpu_price_map_empty(self):
        from backend.billing_service import _parse_gpu_price_map
        assert _parse_gpu_price_map("") == {}

    def test_gpu_price_map_malformed(self):
        from backend.billing_service import _parse_gpu_price_map
        mapping = _parse_gpu_price_map("A100:abc,invalid,B:100")
        assert mapping == {'B': 100.0}

    def test_build_job_billing_fallback(self, svc):
        payload = {'duration_s': 60, 'tenant_id': 'tenant-bill', 'project_id': 'proj-bill'}
        result = svc.build_job_billing('no-render-job', payload, None, None)
        assert result['gpu_hours'] > 0
        assert result['amount'] > 0
        assert result['currency'] == 'CNY'
        assert round(result['gpu_hours'], 4) == round(60 / 3600.0, 4)

    def test_finalize_billing_with_render_job(self, svc):
        from backend.database import get_database
        from backend.models import RenderJob

        now = int(time.time())
        rj = RenderJob(
            id='test-rj-1', tenant_id='tenant-bill', project_id='proj-bill',
            status='succeeded', progress=100,
            started_at=now - 7200, finished_at=now,
        )
        get_database().insert(RenderJob.TABLE_NAME, rj.to_insert_params())

        result = svc.finalize_billing('test-rj-1')
        assert result['usage_type'] == 'render_job'
        assert result['usage_seconds'] == 7200

    def test_finalize_billing_deducts_balance(self, svc):
        from backend.database import get_database
        from backend.models import RenderJob, BillingAccount

        # Create billing account
        ba = BillingAccount(id='ba-t1', tenant_id='tenant-bill', project_id='proj-bill',
                            plan_name='T', balance=1000.0, currency='CNY', status='active')
        get_database().insert(BillingAccount.TABLE_NAME, ba.to_insert_params())

        now = int(time.time())
        rj = RenderJob(id='test-rj-2', tenant_id='tenant-bill', project_id='proj-bill',
                       status='succeeded', progress=100,
                       started_at=now - 3600, finished_at=now)
        get_database().insert(RenderJob.TABLE_NAME, rj.to_insert_params())

        result = svc.finalize_billing('test-rj-2')
        amount = result['amount']

        row = get_database().fetch_one("SELECT balance FROM billing_accounts WHERE id = ?", ('ba-t1',))
        assert row['balance'] == round(1000.0 - amount, 2)

    def test_finalize_billing_with_gpu_node(self, svc):
        from backend.database import get_database
        from backend.models import RenderJob, BillingAccount, ComputeNode

        ba = BillingAccount(id='ba-t2', tenant_id='tenant-bill', project_id='proj-bill',
                            plan_name='T', balance=2000.0, currency='CNY', status='active')
        get_database().insert(BillingAccount.TABLE_NAME, ba.to_insert_params())

        cn = ComputeNode(id='cn-a100', tenant_id='tenant-bill', provider_type='aliyun',
                         node_name='n1', gpu_type='A100', gpu_count=4, status='online', schedulable=1)
        get_database().insert(ComputeNode.TABLE_NAME, cn.to_insert_params())

        now = int(time.time())
        rj = RenderJob(id='test-rj-3', tenant_id='tenant-bill', project_id='proj-bill',
                       node_id='cn-a100', status='succeeded', progress=100,
                       started_at=now - 3600, finished_at=now)
        get_database().insert(RenderJob.TABLE_NAME, rj.to_insert_params())

        result = svc.finalize_billing('test-rj-3')
        assert result['unit_price'] == 150.0  # A100 from price map
        assert result['amount'] == round(1.0 * 150, 2)

    def test_finalize_missing_render_job_raises(self, svc):
        with pytest.raises(ValueError, match='No render_job found'):
            svc.finalize_billing('nonexistent')

    def test_get_billing_summary_includes_render_stats(self, svc):
        from backend.database import get_database
        from backend.models import RenderJob

        summary = svc.get_billing_summary()
        assert summary['render_stats']['total_render_jobs'] == 0

        rj = RenderJob(id='test-rj-4', tenant_id='tenant-bill', project_id='proj-bill',
                       status='pending', progress=0)
        get_database().insert(RenderJob.TABLE_NAME, rj.to_insert_params())

        summary = svc.get_billing_summary()
        assert summary['render_stats']['total_render_jobs'] == 1

    def test_get_job_billing_returns_none_for_unknown(self, svc):
        assert svc.get_job_billing('unknown') is None

    def test_get_project_usage(self, svc):
        from backend.database import get_database
        from backend.models import RenderJob, BillingAccount

        ba = BillingAccount(id='ba-t3', tenant_id='tenant-bill', project_id='proj-bill',
                            plan_name='T', balance=500.0, currency='CNY', status='active')
        get_database().insert(BillingAccount.TABLE_NAME, ba.to_insert_params())

        now = int(time.time())
        rj = RenderJob(id='test-rj-5', tenant_id='tenant-bill', project_id='proj-bill',
                       status='succeeded', progress=100,
                       started_at=now - 1800, finished_at=now)
        get_database().insert(RenderJob.TABLE_NAME, rj.to_insert_params())
        svc.finalize_billing('test-rj-5')

        usage = svc.get_project_usage('proj-bill')
        assert usage['project_id'] == 'proj-bill'
        assert len(usage['records']) >= 1
        assert usage['total_amount'] > 0
