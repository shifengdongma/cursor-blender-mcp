# -*- coding: utf-8 -*-
"""Admin API tests for Volcengine official billing endpoints."""
from __future__ import absolute_import

import json

import backend.ark_billing_routes as billing_routes
from tests import support


def _admin(app, tmp_path):
    support.create_admin(tmp_path)
    client = app.test_client()
    _, token = support.login_and_token(client, 'rootadmin', 'AdminPass12345')
    return client, token


def test_billing_endpoints_require_admin(app, client, tmp_path):
    support.register_and_login(client, 'alice')
    admin_client, _ = _admin(app, tmp_path)
    anonymous = app.test_client()
    paths = (
        '/api/admin/ark/billing/summary',
        '/api/admin/ark/billing/details',
        '/api/admin/ark/billing/balance',
        '/api/admin/ark/billing/sync-status',
        '/api/admin/ark/billing/models',
        '/api/admin/ark/billing/trend',
        '/api/admin/ark/billing/attribution',
        '/api/admin/ark/billing/reconciliation',
    )
    for path in paths:
        assert anonymous.get(path).status_code == 401
        assert client.get(path).status_code == 403
        response = admin_client.get(path)
        assert response.status_code == 200, (path, response.get_data(as_text=True))
        assert response.get_json()['success'] is True


def test_billing_empty_state_sources_and_no_secrets(app, tmp_path):
    admin_client, _ = _admin(app, tmp_path)
    summary = admin_client.get(
        '/api/admin/ark/billing/summary?bill_period=2026-10'
    ).get_json()['data']
    serialized = json.dumps(summary, ensure_ascii=False)
    assert 'VOLCENGINE_ACCESS_KEY_ID' not in serialized
    assert 'VOLCENGINE_SECRET_ACCESS_KEY' not in serialized
    assert summary['source'] == 'volcengine_billing'
    assert summary['is_estimated'] is False
    assert summary['current_month']['has_data'] is False
    assert summary['previous_month']['has_data'] is False
    assert summary['balance']['has_data'] is False
    assert summary['split_status'] == 'not_configured'

    balance = admin_client.get('/api/admin/ark/billing/balance').get_json()['data']
    assert balance['has_data'] is False
    assert balance['source'] == 'volcengine_billing'

    attribution = admin_client.get(
        '/api/admin/ark/billing/attribution?bill_period=2026-10'
    ).get_json()['data']
    assert attribution['has_data'] is False
    assert attribution['source'] == 'volcengine_billing'

    reconciliation = admin_client.get(
        '/api/admin/ark/billing/reconciliation?bill_period=2026-10'
    ).get_json()['data']
    assert reconciliation['source'] == 'volcengine_billing'
    assert reconciliation['official']['has_data'] is False


def test_billing_validation_and_disabled_sync(app, tmp_path):
    admin_client, token = _admin(app, tmp_path)
    headers = support.auth_headers(token)
    assert admin_client.get(
        '/api/admin/ark/billing/summary?bill_period=2026/10'
    ).status_code == 400
    assert admin_client.get(
        '/api/admin/ark/billing/details?level=bad'
    ).status_code == 400
    assert admin_client.get(
        '/api/admin/ark/billing/details?limit=301'
    ).status_code == 400

    response = admin_client.post(
        '/api/admin/ark/billing/sync', json={}, headers=headers
    )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'official_billing_disabled'

    response = admin_client.post(
        '/api/admin/ark/billing/sync',
        json={'bill_period': '2026/10'}, headers=headers,
    )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'invalid_bill_period'


def test_billing_sync_success_contract(app, tmp_path, monkeypatch):
    admin_client, token = _admin(app, tmp_path)

    class FakeService(object):
        def sync_billing(self, **kwargs):
            assert kwargs['actor']['id']
            return {
                'status': 'success', 'claimed': True,
                'periods': ['2026-10'],
                'counts': {'overview': 2, 'bill': 3, 'detail': 3, 'split': 0},
                'split_status': 'not_enabled',
                'balance': {'status': 'success', 'available_balance': '77.01'},
            }

    monkeypatch.setattr(billing_routes, 'get_billing_service', lambda cfg: FakeService())
    response = admin_client.post(
        '/api/admin/ark/billing/sync',
        json={'bill_period': '2026-10'}, headers=support.auth_headers(token),
    )
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['status'] == 'success'
    assert data['split_status'] == 'not_enabled'
    assert data['counts']['detail'] == 3
