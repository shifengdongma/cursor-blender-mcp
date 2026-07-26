# -*- coding: utf-8 -*-
"""
Pytest tests for the auth middleware decorators.

Tests cover:
  - login_required decorator (401 on no session, 200 on valid session)
  - permission_required decorator (403 without permission, bypass for admin/owner,
    200 with correct permission, 401 on empty user dict)
  - Permission constants are all defined.
"""
from __future__ import absolute_import

import os
import tempfile

import pytest
from flask import Flask, jsonify

# Point DATA_DIR at a temporary directory BEFORE any backend imports so that
# demo_seed_service and database modules pick up the test path.
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

# ── Permission constants test ──


class TestPermissionConstants:
    """Verify that all six permission constants are defined with expected values."""

    def test_permission_constants_defined(self):
        assert PERM_VIEW_COMPUTE == 'view_compute'
        assert PERM_MANAGE_COMPUTE == 'manage_compute'
        assert PERM_SUBMIT_RENDER_JOB == 'submit_render_job'
        assert PERM_MANAGE_CLOUD_ACCOUNTS == 'manage_cloud_accounts'
        assert PERM_VIEW_BILLING == 'view_billing'
        assert PERM_VIEW_MONITOR == 'view_monitor'


# ── Fixtures ──


@pytest.fixture
def app():
    """Create a Flask app with test routes and seed demo data.

    The app has three protected endpoints:

      GET /api/test/login-required
          Guarded only by @login_required.

      GET /api/test/perm-manage-cloud
          Guarded by @login_required + @permission_required('manage_cloud_accounts').

      GET /api/test/perm-view-compute
          Guarded by @login_required + @permission_required('view_compute').
    """
    # Reset the global database singleton so that seed_demo_data creates a fresh DB.
    reset_database()

    _app = Flask(__name__)
    _app.secret_key = 'test-secret-key-for-auth'

    # ── Test routes ──

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

    # Seed demo data into the temporary database.
    seed_demo_data(_tmp_data_dir)

    yield _app

    reset_database()


# ── login_required tests ──


class TestLoginRequired:
    """Tests for the @login_required decorator."""

    def test_login_required_returns_401(self, app):
        """No session at all should yield a 401 response."""
        with app.test_client() as client:
            resp = client.get('/api/test/login-required')
        assert resp.status_code == 401
        body = resp.get_json()
        assert body is not None
        assert body['success'] is False
        assert body['error'] == 'unauthorized'

    def test_login_required_passes_with_session(self, app):
        """A valid session user should reach the view and get 200."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = {
                    'id': 'user_curator_01',
                    'name': '陈策展',
                    'role': 'owner',
                    'tenant_id': 'tenant_museum_group',
                }
            resp = client.get('/api/test/login-required')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body is not None
        assert body['success'] is True


# ── permission_required tests ──


class TestPermissionRequired:
    """Tests for the @permission_required decorator."""

    def test_permission_required_returns_403(self, app):
        """An editor without the required 'manage_cloud_accounts' permission gets 403."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = {
                    'id': 'user_pm_01',
                    'name': '刘制片',
                    'role': 'producer',
                    'tenant_id': 'tenant_museum_group',
                }
            resp = client.get(
                '/api/test/perm-manage-cloud',
                query_string={'project_id': 'project_mid_demo'},
            )
        assert resp.status_code == 403
        body = resp.get_json()
        assert body is not None
        assert body['success'] is False
        assert body['error'] == 'forbidden'
        # The details should indicate which permission was required
        assert body['details'] is not None
        assert body['details']['required_permission'] == 'manage_cloud_accounts'

    def test_admin_bypass_permission(self, app):
        """Owner/admin role bypasses the permission check and receives 200."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = {
                    'id': 'user_curator_01',
                    'name': '陈策展',
                    'role': 'owner',
                    'tenant_id': 'tenant_museum_group',
                }
            resp = client.get(
                '/api/test/perm-manage-cloud',
                query_string={'project_id': 'project_mid_demo'},
            )
        # Owner/Admin bypasses permission check
        assert resp.status_code == 200
        body = resp.get_json()
        assert body is not None
        assert body['success'] is True

    def test_editor_with_permission_passes(self, app):
        """An editor who has the required permission in their membership gets 200."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = {
                    'id': 'user_pm_01',
                    'name': '刘制片',
                    'role': 'producer',
                    'tenant_id': 'tenant_museum_group',
                }
            resp = client.get(
                '/api/test/perm-view-compute',
                query_string={'project_id': 'project_mid_demo'},
            )
        # user_pm_01 has 'view_compute' in their membership permissions
        assert resp.status_code == 200
        body = resp.get_json()
        assert body is not None
        assert body['success'] is True

    def test_missing_user_session_returns_401(self, app):
        """An empty user dict in the session is falsy and triggers 401."""
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = {}
            resp = client.get(
                '/api/test/perm-view-compute',
                query_string={'project_id': 'project_mid_demo'},
            )
        # Empty dict is falsy - the decorator treats it as "not logged in"
        assert resp.status_code == 401
        body = resp.get_json()
        assert body is not None
        assert body['success'] is False
        assert body['error'] == 'unauthorized'
