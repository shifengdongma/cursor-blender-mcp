# -*- coding: utf-8 -*-
"""Admin API contract tests for AI usage / Ark official usage."""
from __future__ import absolute_import

import json

import backend.ai_usage_routes as ai_usage_routes
from tests import support


def _admin(app, tmp_path):
    support.create_admin(tmp_path)
    client = app.test_client()
    _, token = support.login_and_token(client, 'rootadmin', 'AdminPass12345')
    return client, token


def test_ai_usage_endpoints_require_admin(app, client, tmp_path):
    support.register_and_login(client, 'alice')
    admin_client, token = _admin(app, tmp_path)
    anonymous = app.test_client()

    for path in (
        '/api/admin/ark/status',
        '/api/admin/ark/usage/summary',
        '/api/admin/ark/usage/models',
        '/api/admin/ark/usage/trend',
        '/api/admin/ark/usage/tasks',
        '/api/admin/ai-usage/users',
        '/api/admin/ai-usage/tasks',
        '/api/admin/ai-usage/reconciliation',
    ):
        assert anonymous.get(path).status_code == 401
        assert client.get(path).status_code == 403
        response = admin_client.get(path)
        assert response.status_code == 200, (path, response.get_data(as_text=True))
        assert response.get_json()['success'] is True

    sync_headers = support.auth_headers(token)
    anonymous_sync = anonymous.post('/api/admin/ark/usage/sync', json={})
    assert anonymous_sync.status_code == 401
    forbidden_sync = client.post(
        '/api/admin/ark/usage/sync', json={}, headers=sync_headers
    )
    assert forbidden_sync.status_code == 403


def test_ai_usage_status_has_no_secrets_and_source_labels(app, tmp_path):
    admin_client, _ = _admin(app, tmp_path)
    response = admin_client.get('/api/admin/ark/status')
    data = response.get_json()['data']
    serialized = json.dumps(data, ensure_ascii=False)
    assert 'VOLCENGINE_ACCESS_KEY_ID' not in serialized
    assert 'VOLCENGINE_SECRET_ACCESS_KEY' not in serialized
    assert 'access_key_id' not in serialized
    assert 'secret_access_key' not in serialized
    assert data['has_credentials'] is False
    assert data['usage_enabled'] is False
    assert data['source'] == 'volcengine_usage'

    summary = admin_client.get('/api/admin/ark/usage/summary?days=7').get_json()['data']
    assert summary['local']['source'] == 'aigv_local'
    assert summary['official']['source'] == 'volcengine_usage'
    assert summary['official']['has_data'] is False
    assert summary['official']['is_estimated'] is False

    models = admin_client.get('/api/admin/ark/usage/models?days=7').get_json()['data']
    assert models['local']['items'] == []
    assert models['official']['items'] == []

    users = admin_client.get('/api/admin/ai-usage/users?days=7').get_json()['data']
    assert users['source'] == 'aigv_local'
    reconciliation = admin_client.get(
        '/api/admin/ai-usage/reconciliation?days=7'
    ).get_json()['data']
    assert reconciliation['source'] == 'internal_estimate'
    assert reconciliation['official']['has_data'] is False


def test_ai_usage_validation_and_disabled_sync(app, tmp_path):
    admin_client, token = _admin(app, tmp_path)
    headers = support.auth_headers(token)
    assert admin_client.get('/api/admin/ark/usage/summary?days=0').status_code == 400
    assert admin_client.get('/api/admin/ark/usage/summary?days=abc').status_code == 400
    assert admin_client.get('/api/admin/ark/usage/tasks?limit=201').status_code == 400
    assert admin_client.get(
        '/api/admin/ark/usage/summary?days=7&start_date=bad'
    ).status_code == 200  # start_date is only used by sync, not the summary

    response = admin_client.post(
        '/api/admin/ark/usage/sync', json={'days': 7}, headers=headers
    )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'official_usage_disabled'

    response = admin_client.post(
        '/api/admin/ark/usage/sync', json={'days': 0}, headers=headers
    )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'invalid_days'

    response = admin_client.post(
        '/api/admin/ark/usage/sync',
        json={'start_date': '2026/10/01'}, headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'invalid_date'


def test_ai_usage_sync_success_contract(app, tmp_path, monkeypatch):
    admin_client, token = _admin(app, tmp_path)

    class FakeService(object):
        def sync_official_usage(self, **kwargs):
            assert kwargs['actor']['id']
            return {
                'status': 'success', 'claimed': True, 'rows': 3,
                'start_date': '2026-10-01', 'end_date': '2026-10-31',
            }

    monkeypatch.setattr(ai_usage_routes, 'get_usage_service', lambda cfg: FakeService())
    response = admin_client.post(
        '/api/admin/ark/usage/sync',
        json={'days': 31}, headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['status'] == 'success'
    assert data['rows'] == 3
