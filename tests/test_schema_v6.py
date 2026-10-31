# -*- coding: utf-8 -*-
"""Schema v6: AI usage / Volcengine snapshot tables are additive and idempotent."""
from __future__ import absolute_import

from backend.database import get_database


def _columns(db, table):
    return {row['name'] for row in db.fetch_all('PRAGMA table_info({0})'.format(table))}


def test_v6_tables_columns_and_version(test_db):
    tables = {
        row['name']
        for row in test_db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        'ai_model_usage_records', 'volcengine_usage_snapshots',
        'volcengine_bill_snapshots', 'volcengine_balance_snapshots',
        'volcengine_sync_status',
    } <= tables
    assert 'provider_request_id' in _columns(test_db, 'generation_tasks')
    assert 'usage_source' in _columns(test_db, 'ai_model_usage_records')
    assert 'api_key_id' in _columns(test_db, 'volcengine_usage_snapshots')
    assert 'payable_amount' in _columns(test_db, 'volcengine_bill_snapshots')
    assert 'available_balance' in _columns(test_db, 'volcengine_balance_snapshots')
    versions = {
        row['version'] for row in test_db.fetch_all('SELECT version FROM schema_migrations')
    }
    assert {1, 2, 3, 4, 5, 6} <= versions
    statuses = {
        row['sync_key']: row['status']
        for row in test_db.fetch_all('SELECT sync_key, status FROM volcengine_sync_status')
    }
    assert statuses == {
        'ark_usage': 'never_run',
        'ark_billing': 'never_run',
        'ark_balance': 'never_run',
    }


def test_v6_schema_reopen_is_idempotent(test_db):
    path = test_db.db_path
    test_db.close()
    again = get_database(path)
    try:
        versions = {
            row['version'] for row in again.fetch_all('SELECT version FROM schema_migrations')
        }
        assert 6 in versions
        assert again.count('volcengine_sync_status') == 3
    finally:
        again.close()
