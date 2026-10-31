# -*- coding: utf-8 -*-
"""Tests for the read-only audit presentation layer."""
from __future__ import absolute_import

import json
import time
import uuid

from backend.audit_presenter import (
    EVENT_LABELS,
    present_event_detail,
    present_events,
)
from backend.audit_service import AuditService
from backend.models import OpsEvent


def _now():
    return int(time.time())


def _insert_user(db, user_id, username, nickname=None):
    db.insert('auth_users', {
        'id': user_id,
        'username': username,
        'password_hash': 'test-hash',
        'nickname': nickname,
        'role': 'user',
        'status': 'active',
        'created_at': _now(),
        'updated_at': _now(),
    })


def _insert_event(db, event_type, message='success', actor_user_id=None,
                  target_type=None, target_id=None, metadata=None,
                  created_at=None, severity='info', job_id=None):
    event = OpsEvent(
        id=str(uuid.uuid4()),
        event_type=event_type,
        message=message,
        severity=severity,
        actor_user_id=actor_user_id,
        job_id=job_id,
        created_at=created_at or _now(),
        updated_at=created_at or _now(),
        metadata={
            'user_id': actor_user_id,
            'target_type': target_type,
            'target_id': target_id,
            'details': metadata or {},
        },
    )
    db.insert(OpsEvent.TABLE_NAME, event.to_insert_params())
    return event.to_dict()


def _row(db, event_id):
    row = db.fetch_one('SELECT * FROM ops_events WHERE id = ?', (event_id,))
    data = {key: row[key] for key in row.keys()}
    if isinstance(data.get('metadata'), str):
        data['metadata'] = json.loads(data['metadata'])
    return data


def test_required_event_labels_are_defined():
    required = [
        'login', 'logout', 'login_failed', 'user_register', 'password_change',
        'admin_user_update', 'admin_role_change', 'admin_status_change',
        'admin_revoke_sessions', 'generation_submit', 'generation_succeeded',
        'generation_failed', 'image_submit', 'video_submit', 'task_cancel',
        'task_retry', 'project_create', 'project_delete', 'storyboard_generate',
        'export_download', 'permission_change', 'cloud_sync', 'resource_allocate',
    ]
    for code in required:
        assert code in EVENT_LABELS
        assert EVENT_LABELS[code]


def test_generation_succeeded_is_presented_with_names(test_db):
    _insert_user(test_db, 'user-alice', 'alice', '爱丽丝')
    test_db.insert('creative_projects', {
        'id': 'project-1', 'name': '项目一', 'created_at': _now(), 'updated_at': _now(),
    })
    test_db.insert('generation_tasks', {
        'id': 'task-1', 'task_type': 'video', 'status': 'succeeded',
        'provider': 'ark_seedance', 'model_id': 'doubao-seedance-2-0-260128',
        'creative_project_id': 'project-1', 'created_by': 'user-alice',
        'created_at': _now(), 'updated_at': _now(),
    })
    event = _insert_event(
        test_db, 'generation_succeeded', actor_user_id='user-alice',
        target_type='generation_task', target_id='task-1',
        metadata={'result_payload': {'provider': 'ark_seedance'}},
    )
    item = present_events(test_db, [_row(test_db, event['id'])])[0]
    assert item['event_label'] == 'AI 生成任务完成'
    assert item['result'] == 'success'
    assert item['result_label'] == '成功'
    assert item['actor_display'] == '爱丽丝（alice）'
    assert 'AI 视频生成任务' in item['target_display']
    assert '火山方舟 Seedance' in item['target_display']
    assert 'doubao-seedance-2-0-260128' in item['target_display']
    assert '项目一' in item['target_display']
    assert '爱丽丝（alice）' in item['summary']


def test_deleted_actor_and_target_are_labelled_not_guessed(test_db):
    event = _insert_event(
        test_db, 'generation_succeeded', actor_user_id='deleted-user',
        target_type='generation_task', target_id='deleted-task',
        metadata={'task_type': 'image', 'provider': 'ark_seedream',
                  'model_id': 'doubao-seedream-5-0-pro'},
    )
    item = present_events(test_db, [_row(test_db, event['id'])])[0]
    assert item['actor_display'] == '已删除用户'
    assert '原始任务已删除' in item['target_display']
    assert item['target_id'] == 'deleted-task'
    assert item['target_type'] == 'generation_task'


def test_unknown_event_and_system_ops_event(test_db):
    unknown = _insert_event(test_db, 'mystery_event', actor_user_id='user-x')
    system = _insert_event(
        test_db, 'rights_validated', message='版权校验通过',
        actor_user_id=None, job_id='job-1', severity='info',
    )
    items = present_events(test_db, [
        _row(test_db, unknown['id']), _row(test_db, system['id']),
    ])
    by_type = {item['event_type']: item for item in items}
    assert by_type['mystery_event']['event_label'] == '其他系统事件'
    assert by_type['mystery_event']['event_type'] == 'mystery_event'
    assert by_type['rights_validated']['event_label'] == '版权校验完成'
    assert by_type['rights_validated']['actor_display'] == '系统任务'
    assert by_type['rights_validated']['summary'] == '版权校验通过'
    assert by_type['rights_validated']['target_type'] == 'job'
    assert by_type['rights_validated']['target_id'] == 'job-1'


def test_login_failed_uses_metadata_username(test_db):
    event = _insert_event(
        test_db, 'login_failed', message='failed', actor_user_id=None,
        metadata={'username': 'ghost'},
    )
    item = present_events(test_db, [_row(test_db, event['id'])])[0]
    assert item['actor_display'] == '未认证用户（ghost）'
    assert item['result_label'] == '失败'
    assert '登录失败' in item['summary']


def test_sensitive_metadata_is_redacted_on_read(test_db):
    event = _insert_event(
        test_db, 'password_change', actor_user_id='user-1',
        metadata={
            'password': 'plain-password',
            'nested': {
                'api_key': 'sk-secret',
                'access_key': 'AKLT-secret',
                'Authorization': 'Bearer abc',
                'cookie': 'session=abc',
                'safe': 'visible',
            },
        },
    )
    item = present_event_detail(test_db, _row(test_db, event['id']))
    serialized = json.dumps(item, ensure_ascii=False)
    assert 'plain-password' not in serialized
    assert 'sk-secret' not in serialized
    assert 'AKLT-secret' not in serialized
    assert 'Bearer abc' not in serialized
    assert 'session=abc' not in serialized
    assert '[REDACTED]' in serialized
    assert 'visible' in serialized
    assert item['detail']['raw_ids']['event_id'] == event['id']


def test_batched_queries_are_bounded(test_db):
    class CountingDB(object):
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.fetch_all_calls = 0

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def fetch_all(self, *args, **kwargs):
            self.fetch_all_calls += 1
            return self.wrapped.fetch_all(*args, **kwargs)

    rows = []
    for index in range(12):
        user_id = 'user-{0}'.format(index)
        _insert_user(test_db, user_id, 'user{0}'.format(index))
        test_db.insert('generation_tasks', {
            'id': 'task-{0}'.format(index), 'task_type': 'image',
            'status': 'succeeded', 'created_by': user_id,
            'created_at': _now(), 'updated_at': _now(),
        })
        event = _insert_event(
            test_db, 'generation_succeeded', actor_user_id=user_id,
            target_type='generation_task', target_id='task-{0}'.format(index),
        )
        rows.append(_row(test_db, event['id']))
    counter = CountingDB(test_db)
    items = present_events(counter, rows)
    assert len(items) == 12
    # Users + tasks (+ potentially projects/assets/jobs/render jobs) are
    # fetched by type, never per event.
    assert counter.fetch_all_calls <= 7


def test_actor_snapshot_survives_user_deletion(test_db):
    _insert_user(test_db, 'user-snap', 'snapuser', '快照用户')
    service = AuditService()
    service.ops.db = test_db
    event = service.record_audit(
        'user-snap', None, None, 'generation_submit',
        target_type='generation_task', target_id='task-snap',
        result='success', metadata={'task_type': 'image'},
    )
    row = _row(test_db, event['id'])
    details = row['metadata']['details']
    assert details['actor_display'] == '快照用户（snapuser）'

    test_db.execute('DELETE FROM auth_users WHERE id = ?', ('user-snap',))
    item = present_events(test_db, [row])[0]
    assert item['actor_display'] == '快照用户（snapuser）'
    assert item['actor_display_snapshot'] == '快照用户（snapuser）'
