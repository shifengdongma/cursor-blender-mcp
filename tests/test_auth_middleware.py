# -*- coding: utf-8 -*-
"""Tests for the database-backed auth middleware decorators."""
from __future__ import absolute_import

import os
import tempfile

import pytest
from flask import Flask, g, jsonify, session

_tmp_data_dir = tempfile.mkdtemp(prefix="aigv_test_auth_")
os.environ["DATA_DIR"] = _tmp_data_dir

from backend.auth_middleware import (
    login_required,
    permission_required,
    PERM_VIEW_COMPUTE,
    PERM_MANAGE_COMPUTE,
    PERM_SUBMIT_RENDER_JOB,
    PERM_MANAGE_CLOUD_ACCOUNTS,
    PERM_VIEW_BILLING,
    PERM_VIEW_MONITOR,
)
from backend.demo_seed_service import seed_demo_data
from backend.database import reset_database


class TestPermissionConstants:
    def test_permission_constants_defined(self):
        assert PERM_VIEW_COMPUTE == 'view_compute'
        assert PERM_MANAGE_COMPUTE == 'manage_compute'
        assert PERM_SUBMIT_RENDER_JOB == 'submit_render_job'
        assert PERM_MANAGE_CLOUD_ACCOUNTS == 'manage_cloud_accounts'
        assert PERM_VIEW_BILLING == 'view_billing'
        assert PERM_VIEW_MONITOR == 'view_monitor'


@pytest.fixture
def app():
    reset_database()
    _app = Flask(__name__)
    _app.secret_key = 'test-secret-key-for-auth'

    @_app.before_request
    def _inject_user():
        user = session.get('test_user')
        if user:
            g.current_user = user

    @_app.route('/api/test/login-required')
    @login_required
    def _login_view():
        return jsonify({'success': True, 'data': 'ok'}), 200

    @_app.route('/api/test/perm-manage-cloud')
    @permission_required(PERM_MANAGE_CLOUD_ACCOUNTS)
    def _perm_manage_cloud():
        return jsonify({'success': True, 'data': 'ok'}), 200

    @_app.route('/api/test/perm-view-compute')
    @permission_required(PERM_VIEW_COMPUTE)
    def _perm_view_compute():
        return jsonify({'success': True, 'data': 'ok'}), 200

    seed_demo_data(_tmp_data_dir)
    yield _app
    reset_database()


def _session_user(client, user):
    with client.session_transaction() as sess:
        sess['test_user'] = user


class TestLoginRequired:
    def test_login_required_returns_401(self, app):
        with app.test_client() as client:
            resp = client.get('/api/test/login-required')
        assert resp.status_code == 401
        body = resp.get_json()
        assert body['success'] is False
        assert body['error'] == 'unauthorized'

    def test_login_required_passes_with_db_user(self, app):
        with app.test_client() as client:
            _session_user(client, {
                'id': 'user_curator_01',
                'tenant_id': 'tenant_museum_group',
                'role': 'owner',
                'status': 'active',
            })
            resp = client.get('/api/test/login-required')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


class TestPermissionRequired:
    def test_permission_required_returns_403(self, app):
        with app.test_client() as client:
            _session_user(client, {
                'id': 'user_pm_01',
                'tenant_id': 'tenant_museum_group',
                'role': 'producer',
                'status': 'active',
            })
            resp = client.get('/api/test/perm-manage-cloud')
        assert resp.status_code == 403
        body = resp.get_json()
        assert body['success'] is False
        assert body['error'] == 'forbidden'
        assert body['details']['required_permission'] == 'manage_cloud_accounts'

    def test_platform_admin_bypasses_permission(self, app):
        with app.test_client() as client:
            _session_user(client, {
                'id': 'platform-admin',
                'tenant_id': 'tenant_platform',
                'role': 'admin',
                'status': 'active',
            })
            resp = client.get('/api/test/perm-manage-cloud')
        assert resp.status_code == 200

    def test_editor_with_permission_passes(self, app):
        with app.test_client() as client:
            _session_user(client, {
                'id': 'user_pm_01',
                'tenant_id': 'tenant_museum_group',
                'role': 'producer',
                'status': 'active',
            })
            resp = client.get('/api/test/perm-view-compute')
        assert resp.status_code == 200

    def test_missing_user_returns_401(self, app):
        with app.test_client() as client:
            resp = client.get('/api/test/perm-view-compute')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'unauthorized'
