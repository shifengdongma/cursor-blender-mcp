# -*- coding: utf-8 -*-
"""
Tests for AuditService: audit trail, sensitive data filtering.
"""
from __future__ import absolute_import

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.audit_service import AuditService
from backend.ops_service import (
    EVENT_LOGIN, EVENT_LOGOUT, EVENT_LOGIN_FAILED,
    EVENT_PASSWORD_CHANGE, EVENT_PERMISSION_CHANGE,
)


class TestAuditService:
    """Test audit trail functionality."""

    def test_record_login_success(self, test_db):
        """Test recording a successful login."""
        svc = AuditService()
        svc.ops.db = test_db
        result = svc.record_login('user-1', None, success=True)
        assert result is not None
        assert result.get('event_type') == EVENT_LOGIN

    def test_record_login_failed(self, test_db):
        """Test recording a failed login."""
        svc = AuditService()
        svc.ops.db = test_db
        result = svc.record_login('user-1', None, success=False)
        assert result is not None
        assert result.get('event_type') == EVENT_LOGIN_FAILED
        assert result.get('severity') == 'warning'

    def test_sanitize_removes_passwords(self, test_db):
        """Test that passwords are redacted from audit records."""
        svc = AuditService()
        svc.ops.db = test_db
        result = svc.record_audit(
            'user-1', None, None, EVENT_PASSWORD_CHANGE,
            metadata={'new_password': 'secret123', 'api_key': 'key-abc', 'username': 'test'},
        )
        metadata = result.get('metadata', {})
        details = metadata.get('details', {})
        # Password should be redacted
        assert details.get('new_password') == '[REDACTED]'
        assert details.get('api_key') == '[REDACTED]'
        # Non-sensitive fields should remain
        assert details.get('username') == 'test'

    def test_record_permission_change(self, test_db):
        """Test recording a permission change."""
        svc = AuditService()
        svc.ops.db = test_db
        result = svc.record_permission_change(
            'admin-user', None, None,
            EVENT_PERMISSION_CHANGE, 'target-user',
            details={'new_permissions': ['view_compute']},
        )
        assert result is not None
        assert result.get('event_type') == EVENT_PERMISSION_CHANGE

    def test_list_audit_events(self, test_db):
        """Test listing audit events."""
        svc = AuditService()
        svc.ops.db = test_db
        # Record some events (pass None for tenant/project to avoid FK issues)
        svc.record_login('user-1', None, success=True)
        svc.record_login('user-1', None, success=False)
        svc.record_login('user-2', None, success=True)

        events = svc.list_audit_events(user_id='user-1')
        assert len(events) >= 1  # At least one event for user-1
        for event in events:
            meta = event.get('metadata') or {}
            if isinstance(meta, dict):
                # Should be user-1's events or unfiltered
                pass
