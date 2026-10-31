# -*- coding: utf-8 -*-
"""Tests for the enhanced admin audit-log endpoint."""
from __future__ import absolute_import

import json
import time
import uuid
from datetime import datetime, timedelta, timezone

from backend.audit_service import AuditService
from backend.database import get_database
from backend.models import OpsEvent
from tests import support


def _now():
    return int(time.time())


def _insert_targets(alice_id):
    db = get_database()
    db.insert('creative_projects', {
        'id': 'project-audit', 'name': '审计项目',
        'created_at': _now(), 'updated_at': _now(),
    })
    db.insert('generation_tasks', {
        'id': 'task-audit', 'task_type': 'video', 'status': 'succeeded',
        'provider': 'ark_seedance', 'model_id': 'doubao-seedance-2-0-260128',
        'creative_project_id': 'project-audit', 'created_by': alice_id,
        'created_at': _now(), 'updated_at': _now(),
    })
    db.insert('assets', {
        'id': 'asset-audit', 'name': '展厅参考图', 'asset_type': 'image',
        'created_at': _now(), 'updated_at': _now(),
    })


def _record(svc, actor_id, action, result='success', target_type=None,
           target_id=None, details=None):
    return svc.record_audit(
        actor_id, None, None, action,
        target_type=target_type, target_id=target_id, result=result,
        metadata=details or {},
    )


def _raw_event(event_type, message='success', actor_user_id=None,
               target_type=None, target_id=None, details=None,
               created_at=None, severity='info'):
    return OpsEvent(
        id=str(uuid.uuid4()),
        event_type=event_type,
        message=message,
        severity=severity,
        actor_user_id=actor_user_id,
        created_at=created_at or _now(),
        updated_at=created_at or _now(),
        metadata={
            'user_id': actor_user_id,
            'target_type': target_type,
            'target_id': target_id,
            'details': details or {},
        },
    )


def _admin_client(app, tmp_path, username='rootadmin'):
    support.create_admin(tmp_path, username=username)
    client = app.test_client()
    _, token = support.login_and_token(client, username, 'AdminPass12345')
    return client, token


def test_audit_api_readable_fields_filters_and_detail(app, client, tmp_path):
    alice, _ = support.register_and_login(client, 'alice', nickname='爱丽丝')
    _insert_targets(alice['id'])
    admin_client, _ = _admin_client(app, tmp_path)

    svc = AuditService(str(tmp_path))
    success_event = _record(
        svc, alice['id'], 'generation_succeeded',
        target_type='generation_task', target_id='task-audit',
        details={'result_payload': {'provider': 'ark_seedance'}},
    )
    failed_event = _record(
        svc, alice['id'], 'generation_failed', result='failed',
        target_type='generation_task', target_id='task-audit',
        details={'error_code': 'provider_failed', 'error_message': '生成失败'},
    )
    _record(svc, None, 'login_failed', result='failed',
            details={'username': 'ghost'})
    _record(svc, alice['id'], 'asset_update',
            target_type='asset', target_id='asset-audit')

    response = admin_client.get('/api/admin/audit-logs?limit=10')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['total'] >= 4
    assert data['filter_options']['event_types']
    assert data['filter_options']['results']
    item = [entry for entry in data['items']
            if entry['id'] == success_event['id']][0]
    assert item['event_label'] == 'AI 生成任务完成'
    assert item['result_label'] == '成功'
    assert item['actor_display'] == '爱丽丝（alice）'
    assert 'AI 视频生成任务' in item['target_display']
    assert '审计项目' in item['target_display']
    # Legacy fields remain available.
    assert item['message'] == 'success'
    assert item['actor_user_id'] == alice['id']
    assert item['metadata']['target_type'] == 'generation_task'

    # New and legacy event-type filters.
    filtered = admin_client.get(
        '/api/admin/audit-logs?event_type=generation_succeeded'
    ).get_json()['data']
    assert filtered['total'] == 1
    assert filtered['items'][0]['id'] == success_event['id']
    legacy = admin_client.get(
        '/api/admin/audit-logs?action=generation_failed'
    ).get_json()['data']
    assert legacy['total'] == 1
    assert legacy['items'][0]['id'] == failed_event['id']

    # Result and actor filters.
    failed = admin_client.get(
        '/api/admin/audit-logs?result=failed'
    ).get_json()['data']
    assert {entry['id'] for entry in failed['items']} >= {
        failed_event['id'],
    }
    assert all(entry['result'] == 'failed' for entry in failed['items'])
    by_username = admin_client.get(
        '/api/admin/audit-logs?actor=alice'
    ).get_json()['data']
    assert all(entry['actor_user_id'] == alice['id']
               for entry in by_username['items'])
    by_id = admin_client.get(
        '/api/admin/audit-logs?actor=' + alice['id']
    ).get_json()['data']
    assert by_id['total'] == by_username['total']

    # Detail endpoint.
    detail = admin_client.get(
        '/api/admin/audit-logs/{0}'.format(success_event['id'])
    )
    assert detail.status_code == 200
    detail_data = detail.get_json()['data']
    assert detail_data['detail']['event_raw_code'] == 'generation_succeeded'
    assert detail_data['detail']['raw_ids']['event_id'] == success_event['id']
    assert detail_data['detail']['raw_ids']['target_id'] == 'task-audit'
    assert detail_data['detail']['model']['model_id'] == 'doubao-seedance-2-0-260128'
    assert detail_data['detail']['project']['name'] == '审计项目'
    assert 'sanitized_metadata' in detail_data['detail']

    missing = admin_client.get('/api/admin/audit-logs/does-not-exist')
    assert missing.status_code == 404
    assert missing.get_json()['error'] == 'audit_event_not_found'


def test_audit_api_deleted_actor_and_target(app, client, tmp_path):
    alice, _ = support.register_and_login(client, 'alice', nickname='爱丽丝')
    admin_client, _ = _admin_client(app, tmp_path)
    svc = AuditService(str(tmp_path))
    event = _record(
        svc, 'deleted-actor-id', 'generation_succeeded',
        target_type='generation_task', target_id='deleted-task-id',
        details={'task_type': 'image', 'provider': 'ark_seedream',
                 'model_id': 'doubao-seedream-5-0-pro'},
    )
    data = admin_client.get(
        '/api/admin/audit-logs?event_type=generation_succeeded'
    ).get_json()['data']
    item = [entry for entry in data['items'] if entry['id'] == event['id']][0]
    assert item['actor_display'] == '已删除用户'
    assert '原始任务已删除' in item['target_display']
    detail = admin_client.get(
        '/api/admin/audit-logs/{0}'.format(event['id'])
    ).get_json()['data']['detail']
    # Deleted user IDs are masked in the detail dialog.
    assert detail['raw_ids']['actor_user_id'] != 'deleted-actor-id'
    assert '…' in detail['raw_ids']['actor_user_id']
    assert detail['raw_ids']['target_id'] == 'deleted-task-id'


def test_audit_api_date_pagination_and_validation(app, client, tmp_path):
    alice, _ = support.register_and_login(client, 'alice', nickname='爱丽丝')
    admin_client, _ = _admin_client(app, tmp_path)
    db = get_database()
    beijing = timezone(timedelta(hours=8))
    base = int(datetime(2026, 10, 30, 12, 0, tzinfo=beijing).timestamp())
    db.insert('ops_events', _raw_event(
        'pagination_test', created_at=base,
    ).to_insert_params())
    for index in range(1, 15):
        db.insert('ops_events', _raw_event(
            'pagination_test', created_at=base + index,
        ).to_insert_params())

    page = admin_client.get(
        '/api/admin/audit-logs?event_type=pagination_test&limit=5&offset=5'
    ).get_json()['data']
    assert page['total'] == 15
    assert len(page['items']) == 5
    timestamps = [item['created_at'] for item in page['items']]
    assert timestamps == sorted(timestamps, reverse=True)

    dated = admin_client.get(
        '/api/admin/audit-logs?event_type=pagination_test'
        '&start_date=2026-10-30&end_date=2026-10-30'
    ).get_json()['data']
    assert dated['total'] == 15
    assert all(item['created_at'] >= base for item in dated['items'])

    invalid = admin_client.get(
        '/api/admin/audit-logs?start_date=not-a-date'
    )
    assert invalid.status_code == 400
    assert invalid.get_json()['error'] == 'invalid_date'
    invalid_range = admin_client.get(
        '/api/admin/audit-logs?start_date=2026-10-31&end_date=2026-10-30'
    )
    assert invalid_range.status_code == 400
    too_large = admin_client.get('/api/admin/audit-logs?limit=201')
    assert too_large.status_code == 400


def test_audit_api_permissions_and_secret_redaction(app, client, tmp_path):
    alice, _ = support.register_and_login(client, 'alice', nickname='爱丽丝')
    admin_client, _ = _admin_client(app, tmp_path)
    db = get_database()
    event = _raw_event(
        'password_change', actor_user_id=alice['id'],
        details={
            'password': 'do-not-leak',
            'nested': {'api_key': 'sk-do-not-leak', 'safe': 'visible'},
        },
    )
    db.insert('ops_events', event.to_insert_params())

    anonymous = app.test_client()
    assert anonymous.get('/api/admin/audit-logs').status_code == 401
    assert client.get('/api/admin/audit-logs').status_code == 403
    assert client.get(
        '/api/admin/audit-logs/{0}'.format(event.id)
    ).status_code == 403

    response = admin_client.get(
        '/api/admin/audit-logs?event_type=password_change'
    )
    serialized = json.dumps(response.get_json(), ensure_ascii=False)
    assert 'do-not-leak' not in serialized
    assert 'sk-do-not-leak' not in serialized
    assert '[REDACTED]' in serialized
    detail = admin_client.get(
        '/api/admin/audit-logs/{0}'.format(event.id)
    )
    detail_serialized = json.dumps(detail.get_json(), ensure_ascii=False)
    assert 'do-not-leak' not in detail_serialized
    assert 'sk-do-not-leak' not in detail_serialized
    assert '[REDACTED]' in detail_serialized


def test_audit_frontend_contract():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'web', 'admin-users.html'), 'r', encoding='utf-8') as handle:
        html = handle.read()
    with open(os.path.join(root, 'web', 'admin-users.js'), 'r', encoding='utf-8') as handle:
        js = handle.read()
    assert 'admin-audit-event-filter' in html
    assert 'admin-audit-result-filter' in html
    assert 'admin-audit-actor-filter' in html
    assert 'admin-audit-start-date' in html
    assert 'admin-audit-end-date' in html
    assert 'admin-audit-modal' in html
    assert '/api/admin/audit-logs/' in js
    assert 'openAuditDetail' in js
    assert 'event_label' in js
    assert 'target_display' in js
