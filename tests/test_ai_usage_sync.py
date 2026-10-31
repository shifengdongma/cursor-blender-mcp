# -*- coding: utf-8 -*-
"""Tests for official usage sync, idempotency, cache and local statistics."""
from __future__ import absolute_import

import os
import time
from types import SimpleNamespace

import pytest

from backend.billing_service import BillingService
from backend.database import get_database
from backend.usage_records import record_usage
from backend.volcengine.client import VolcengineAPIError
from backend.volcengine.store import get_sync_status
from backend.volcengine.usage_service import VolcengineUsageService


def _cfg():
    return SimpleNamespace(
        VOLCENGINE_USAGE_ENABLED=True,
        VOLCENGINE_BILLING_ENABLED=False,
        VOLCENGINE_ACCESS_KEY_ID='AK',
        VOLCENGINE_SECRET_ACCESS_KEY='SK',
        VOLCENGINE_ARK_REGION='cn-beijing',
        VOLCENGINE_ARK_PROJECT='default',
        VOLCENGINE_USAGE_SYNC_INTERVAL_S=1800,
        VOLCENGINE_USAGE_LOOKBACK_DAYS=31,
        AUDIT_ENABLED=False,
        DATA_DIR='.',
        GPU_PRICE_MAP='',
        GPU_UNIT_PRICE_CNY=120,
        ENGINE_UNIT_PRICE_CNY=80,
        STREAM_UNIT_PRICE_CNY=40,
    )


def _usage_row(day='2026-10-31', input_tokens=10, output_tokens=20,
               total_tokens=30, req_cnt=1, image_count=1,
               model='doubao-seedream', key='key-1'):
    return {
        'AccountID': '2100',
        'ApikeyID': key,
        'ModelName': model,
        'ModelVersion': 'v1',
        'ModelEndpoint': 'ep-1',
        'BillingStatus': 'normal',
        'ProjectName': 'default',
        'Day': day,
        'InputTokens': str(input_tokens),
        'OutputTokens': str(output_tokens),
        'TotalTokens': str(total_tokens),
        'ReqCnt': str(req_cnt),
        'ImageCount': str(image_count),
    }


class FakeUsageClient(object):
    def __init__(self, rows=None, error=None, fail_dimensions_once=False,
                 task_usage=None):
        self.rows = list(rows or [])
        self.error = error
        self.fail_dimensions_once = fail_dimensions_once
        self.task_usage = task_usage or {}
        self.calls = []

    @staticmethod
    def dimension_filters():
        return [{'Key': 'ApikeyID', 'Values': []}, {'Key': 'ModelName', 'Values': []}]

    def get_inference_usage(self, start_date, end_date, query_interval='Day',
                            filters=None, **kwargs):
        self.calls.append({'start': start_date, 'end': end_date, 'filters': filters})
        if self.error:
            raise self.error
        if self.fail_dimensions_once and filters:
            self.fail_dimensions_once = False
            raise VolcengineAPIError('invalid_param', 'empty filters rejected')
        return {
            'rows': list(self.rows),
            'fields': [],
            'fields_json': '[]',
            'query_interval': query_interval,
            'query_start': start_date,
            'query_end': end_date,
            'data_count': len(self.rows),
        }

    def get_inference_task_usage(self, task_id):
        return self.task_usage


def _service(test_db, client):
    return VolcengineUsageService(_cfg(), db=test_db, client=client)


def test_sync_upserts_snapshots_and_is_idempotent(test_db):
    client = FakeUsageClient([
        _usage_row(),
        _usage_row(input_tokens=1, output_tokens=2, total_tokens=3, req_cnt=1, image_count=0),
    ])
    service = _service(test_db, client)
    result = service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    assert result['status'] == 'success'
    assert result['rows'] == 1
    rows = test_db.fetch_all('SELECT * FROM volcengine_usage_snapshots')
    assert len(rows) == 1
    row = rows[0]
    assert row['input_tokens'] == 11
    assert row['output_tokens'] == 22
    assert row['total_tokens'] == 33
    assert row['req_cnt'] == 2
    assert row['image_count'] == 1
    status = get_sync_status(test_db, 'ark_usage')
    assert status['status'] == 'success'
    assert status['last_success_at']
    last_success = status['last_success_at']

    client.rows = [_usage_row(input_tokens=100, output_tokens=200, total_tokens=300,
                              req_cnt=5, image_count=2)]
    service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    rows = test_db.fetch_all('SELECT * FROM volcengine_usage_snapshots')
    assert len(rows) == 1
    assert rows[0]['total_tokens'] == 300
    assert rows[0]['req_cnt'] == 5


def test_sync_failure_keeps_last_snapshot_and_success_time(test_db):
    client = FakeUsageClient([_usage_row()])
    service = _service(test_db, client)
    service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    before = get_sync_status(test_db, 'ark_usage')
    before_count = test_db.count('volcengine_usage_snapshots')
    client.error = VolcengineAPIError('network', 'network down')
    with pytest.raises(VolcengineAPIError):
        service.sync_official_usage(
            start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
        )
    after = get_sync_status(test_db, 'ark_usage')
    assert after['status'] == 'failed'
    assert after['error_category'] == 'network'
    assert after['last_success_at'] == before['last_success_at']
    assert test_db.count('volcengine_usage_snapshots') == before_count


def test_sync_lock_rejects_concurrent_run(test_db):
    client = FakeUsageClient([_usage_row()])
    service = _service(test_db, client)
    service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    test_db.execute(
        "UPDATE volcengine_sync_status SET status='running', running_since=? "
        "WHERE sync_key='ark_usage'",
        (int(time.time()),),
    )
    result = service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    assert result['claimed'] is False
    assert len(client.calls) == 1


def test_sync_falls_back_when_empty_filters_are_rejected(test_db):
    client = FakeUsageClient([_usage_row()], fail_dimensions_once=True)
    service = _service(test_db, client)
    result = service.sync_official_usage(
        start_date='2026-10-31', end_date='2026-10-31', enrich_tasks=False,
    )
    assert result['dimension_filters_supported'] is False
    assert len(client.calls) == 2
    assert client.calls[0]['filters']
    assert client.calls[1]['filters'] is None


def test_enrich_task_usage_writes_official_api_record(test_db):
    now = int(time.time())
    test_db.insert('generation_tasks', {
        'id': 'video-1', 'task_type': 'video', 'status': 'succeeded',
        'provider': 'ark_seedance', 'model_id': 'doubao-seedance-2-0',
        'provider_job_id': 'cgt-official', 'created_by': 'user-1',
        'created_at': now, 'completed_at': now, 'updated_at': now,
    })
    client = FakeUsageClient(task_usage={
        'TaskID': 'cgt-official', 'APIKeyID': 'key-official',
        'ModelName': 'doubao-seedance-2-0', 'BillingStatus': 'normal',
        'OutputTokens': 123, 'Resolution': '720p',
    })
    service = _service(test_db, client)
    result = service.enrich_task_usage(limit=5)
    assert result['records'] == 1
    rows = test_db.fetch_all(
        "SELECT * FROM ai_model_usage_records WHERE task_id='video-1'"
    )
    assert len(rows) == 1
    row = rows[0]
    assert row['usage_source'] == 'official_api'
    assert row['output_tokens'] == 123
    assert row['api_key_resource_id'] == 'key-official'
    assert row['provider_job_id'] == 'cgt-official'
    again = service.enrich_task_usage(limit=5)
    assert again['tasks_checked'] == 0


def test_local_summary_users_tasks_and_performance(test_db):
    now = int(time.time())
    test_db.insert('auth_users', {
        'id': 'user-local', 'username': 'alice', 'nickname': '爱丽丝',
        'password_hash': 'x', 'role': 'user', 'status': 'active',
        'created_at': now, 'updated_at': now,
    })
    base = now
    for index, task_type in enumerate(('image', 'video', 'storyboard', 'tts')):
        test_db.insert('generation_tasks', {
            'id': 'task-local-{0}'.format(index),
            'task_type': task_type, 'status': 'succeeded',
            'provider': 'ark_seedream' if task_type == 'image' else None,
            'model_id': 'model-image' if task_type == 'image' else None,
            'created_by': 'user-local',
            'created_at': base, 'completed_at': base + 10, 'updated_at': base,
            'created_at_ms': float(base), 'claimed_at_ms': float(base + 1),
            'completed_at_ms': float(base + 10),
        })
    record_usage({
        'dedupe_key': 'local-usage-1',
        'task_id': 'task-local-0', 'user_id': 'user-local',
        'provider': 'ark_seedream', 'model_id': 'model-image',
        'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30,
        'image_count': 1, 'usage_source': 'response',
    })
    service = _service(test_db, FakeUsageClient())
    summary = service.local_summary(days=1)
    assert summary['model_calls'] == 3
    assert summary['images'] == 1
    assert summary['videos'] == 1
    assert summary['llm_tasks'] == 1
    assert summary['succeeded'] == 3
    assert summary['source'] == 'aigv_local'
    users = service.local_users(days=1)
    assert users['items'][0]['display'] == '爱丽丝（alice）'
    assert users['items'][0]['total_tokens'] == 30
    tasks = service.local_tasks(days=1, limit=10, offset=0)
    assert tasks['total'] == 4
    image_task = [item for item in tasks['items'] if item['id'] == 'task-local-0'][0]
    assert image_task['creator_display'] == '爱丽丝（alice）'
    assert image_task['usage']['total_tokens'] == 30
    models = service.local_models(days=1)
    assert models['items'][0]['model_id'] == 'model-image'


def test_billing_summary_uses_all_records_not_only_recent_20(test_db):
    now = int(time.time())
    for index in range(25):
        test_db.insert('billing_usage_records', {
            'id': 'bill-{0}'.format(index), 'amount': 1.5, 'currency': 'CNY',
            'usage_type': 'job_run', 'created_at': now + index,
            'updated_at': now + index,
        })
    service = BillingService(data_dir=os.path.dirname(test_db.db_path), cfg=_cfg())
    service.db = test_db
    summary = service.get_billing_summary()
    assert summary['usage_record_count'] == 25
    assert summary['total_amount'] == 37.5
    assert len(summary['recent_usage']) == 20
    assert summary['total_amount_scope'] == 'all_time'
    assert summary['source'] == 'internal_estimate'
    assert summary['is_estimated'] is True
