# -*- coding: utf-8 -*-
"""Persistence helpers for official usage, bills, balances and sync status."""
from __future__ import absolute_import

import hashlib
import json
import time

USAGE_SYNC_KEY = 'ark_usage'
BILLING_SYNC_KEY = 'ark_billing'
BALANCE_SYNC_KEY = 'ark_balance'


def now():
    return int(time.time())


def _stable_id(key):
    return hashlib.sha256(str(key).encode('utf-8')).hexdigest()


def _json_text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _row_dict(row):
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def upsert_by_key(db, table, key_column, values):
    """INSERT ... ON CONFLICT(key) DO UPDATE for snapshot tables."""
    if not values or not values.get(key_column):
        return None
    data = dict(values)
    if not data.get('id'):
        data['id'] = _stable_id(data[key_column])
    columns = list(data.keys())
    placeholders = ', '.join('?' for _ in columns)
    updates = [
        '{0} = excluded.{0}'.format(column)
        for column in columns
        if column not in ('id', key_column, 'created_at')
    ]
    query = (
        'INSERT INTO {0} ({1}) VALUES ({2}) '
        'ON CONFLICT({3}) DO UPDATE SET {4}'
    ).format(
        table, ', '.join(columns), placeholders, key_column,
        ', '.join(updates),
    )
    db.execute(query, tuple(data[column] for column in columns))
    return data['id']


def ensure_status_row(db, sync_key):
    db.execute(
        "INSERT OR IGNORE INTO volcengine_sync_status "
        "(sync_key, status, updated_at) VALUES (?, 'never_run', ?)",
        (sync_key, now()),
    )


def claim_sync(db, sync_key, stale_seconds=1800):
    ensure_status_row(db, sync_key)
    current = now()
    stale_before = current - max(60, int(stale_seconds or 1800))
    affected = db.execute(
        "UPDATE volcengine_sync_status SET status = 'running', "
        "running_since = ?, last_attempt_at = ?, updated_at = ? "
        "WHERE sync_key = ? AND (status <> 'running' OR running_since IS NULL "
        "OR running_since < ?)",
        (current, current, current, sync_key, stale_before),
    )
    return affected == 1


def finish_sync(db, sync_key, status, error_category=None, error_code=None,
                error_message=None, records_processed=0, last_period=None,
                metadata=None, success=False):
    ensure_status_row(db, sync_key)
    current = now()
    fields = {
        'status': status,
        'error_category': error_category,
        'last_error_code': (str(error_code)[:120] if error_code else None),
        'last_error_message': (str(error_message)[:500] if error_message else None),
        'last_attempt_at': current,
        'running_since': None,
        'records_processed': int(records_processed or 0),
        'last_period': last_period,
        'metadata': _json_text(metadata),
        'updated_at': current,
    }
    if success:
        fields['last_success_at'] = current
        fields['last_error_code'] = None
        fields['last_error_message'] = None
        fields['error_category'] = None
    set_clause = ', '.join('{0} = ?'.format(key) for key in fields.keys())
    params = tuple(fields.values()) + (sync_key,)
    db.execute(
        'UPDATE volcengine_sync_status SET {0} WHERE sync_key = ?'.format(set_clause),
        params,
    )


def get_sync_status(db, sync_key):
    ensure_status_row(db, sync_key)
    row = db.fetch_one(
        'SELECT * FROM volcengine_sync_status WHERE sync_key = ?', (sync_key,)
    )
    return _row_dict(row)


def get_all_sync_statuses(db):
    rows = db.fetch_all(
        'SELECT * FROM volcengine_sync_status ORDER BY sync_key'
    )
    return [_row_dict(row) for row in rows]


def upsert_usage_snapshot(db, snapshot):
    return upsert_by_key(
        db, 'volcengine_usage_snapshots', 'snapshot_key', snapshot
    )


def upsert_bill_snapshot(db, snapshot):
    return upsert_by_key(
        db, 'volcengine_bill_snapshots', 'snapshot_key', snapshot
    )


def insert_balance_snapshot(db, snapshot):
    data = dict(snapshot or {})
    if not data:
        return None
    data['id'] = data.get('id') or _stable_id(
        'balance:{0}:{1}'.format(data.get('provider_account_ref') or '', data.get('synced_at') or now())
    )
    data.setdefault('synced_at', now())
    data.setdefault('updated_at', now())
    columns = list(data.keys())
    placeholders = ', '.join('?' for _ in columns)
    db.execute(
        'INSERT OR IGNORE INTO volcengine_balance_snapshots ({0}) VALUES ({1})'.format(
            ', '.join(columns), placeholders
        ),
        tuple(data[column] for column in columns),
    )
    return data['id']


def latest_balance(db):
    row = db.fetch_one(
        'SELECT * FROM volcengine_balance_snapshots ORDER BY synced_at DESC, id DESC LIMIT 1'
    )
    return _row_dict(row)


def rows_since(db, table, since):
    return db.fetch_all(
        'SELECT * FROM {0} WHERE period_start_at >= ? ORDER BY period_start_at ASC'.format(table),
        (since,),
    )
