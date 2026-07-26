# -*- coding: utf-8 -*-
"""
Tests for AlertService: rule evaluation, alert lifecycle, deduplication.
"""
from __future__ import absolute_import

import os
import sys
import time
import uuid

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.alert_service import AlertService
from backend.models import Alert, AlertEvent, AlertRule


@pytest.fixture
def alert_svc(test_db):
    """Create AlertService with test database."""
    svc = AlertService(os.environ.get('DATA_DIR', './data'))
    svc.db = test_db  # Override with test database
    return svc


@pytest.fixture
def sample_rules(alert_svc):
    """Insert sample alert rules and return them."""
    rule_data = [
        {'rule_type': 'threshold', 'target_type': 'node', 'metric_name': 'gpu_temperature',
         'operator': 'gt', 'threshold': 85, 'duration_s': 0, 'severity': 'error',
         'metadata': {'description': 'GPU temp > 85C'}},
        {'rule_type': 'threshold', 'target_type': 'node', 'metric_name': 'cpu_percent',
         'operator': 'gt', 'threshold': 95, 'duration_s': 0, 'severity': 'warning',
         'metadata': {'description': 'CPU > 95%'}},
    ]
    rules = []
    for rd in rule_data:
        rule = alert_svc.create_rule(rd)
        rules.append(rule)
    return rules


class TestAlertRuleEvaluation:
    """Test rule evaluation logic."""

    def test_threshold_gt_triggers(self, alert_svc, sample_rules):
        """Test that a gt rule fires when value exceeds threshold."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-1',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        assert len(created) == 1

    def test_threshold_below_does_not_trigger(self, alert_svc, sample_rules):
        """Test that a gt rule does NOT fire when value is below threshold."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 60,
            'target_type': 'node', 'target_id': 'node-1',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        assert len(created) == 0

    def test_multiple_rules_evaluate(self, alert_svc, sample_rules):
        """Test that multiple rules are evaluated."""
        metrics = [
            {'metric_name': 'gpu_temperature', 'current_value': 90,
             'target_type': 'node', 'target_id': 'node-1'},
            {'metric_name': 'cpu_percent', 'current_value': 98,
             'target_type': 'node', 'target_id': 'node-1'},
        ]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        assert len(created) == 2

    def test_alert_dedup(self, alert_svc, sample_rules):
        """Test that same rule+target does not create duplicate alerts."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-1',
        }]
        # First evaluation - should create
        results1 = alert_svc.evaluate_all(metrics)
        # Second evaluation - should update, not create
        metrics[0]['current_value'] = 91
        results2 = alert_svc.evaluate_all(metrics)
        created = [r for r in results2 if r.get('action') == 'created']
        assert len(created) == 0


class TestAlertLifecycle:
    """Test alert status transitions."""

    def test_alert_open_on_create(self, alert_svc, sample_rules):
        """Test that new alerts have status 'open'."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-2',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        assert len(created) == 1
        alert_id = created[0]['alert_id']

        alert_detail = alert_svc.get_alert_detail(alert_id)
        assert alert_detail['status'] == 'open'

    def test_acknowledge_alert(self, alert_svc, sample_rules):
        """Test acknowledging an alert."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-3',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        alert_id = created[0]['alert_id']

        result = alert_svc.acknowledge_alert(alert_id, 'user-1')
        assert result['status'] == 'acknowledged'
        assert result['acknowledged_by'] == 'user-1'

    def test_close_alert(self, alert_svc, sample_rules):
        """Test closing an alert."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-4',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        alert_id = created[0]['alert_id']

        result = alert_svc.close_alert(alert_id, 'user-1', 'Issue resolved')
        assert result['status'] == 'closed'
        assert result['notes'] == 'Issue resolved'

    def test_auto_recovery(self, alert_svc, sample_rules):
        """Test auto-recovery when metric returns to normal."""
        metrics_high = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-5',
        }]
        results = alert_svc.evaluate_all(metrics_high)
        created = [r for r in results if r.get('action') == 'created']
        alert_id = created[0]['alert_id']

        # Now value drops below threshold
        metrics_normal = [{
            'metric_name': 'gpu_temperature', 'current_value': 60,
            'target_type': 'node', 'target_id': 'node-5',
        }]
        results2 = alert_svc.evaluate_all(metrics_normal)
        recovered = [r for r in results2 if r.get('action') == 'recovered']
        assert len(recovered) == 1

    def test_alert_event_history(self, alert_svc, sample_rules):
        """Test that alert events are recorded."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-6',
        }]
        results = alert_svc.evaluate_all(metrics)
        created = [r for r in results if r.get('action') == 'created']
        alert_id = created[0]['alert_id']

        alert_svc.acknowledge_alert(alert_id, 'user-1')
        alert_svc.add_comment(alert_id, 'user-1', 'Investigating')
        alert_svc.close_alert(alert_id, 'user-1', 'Fixed')

        detail = alert_svc.get_alert_detail(alert_id)
        assert len(detail.get('events', [])) >= 4  # triggered + acknowledged + commented + closed


class TestAlertListing:
    """Test alert listing and filtering."""

    def test_list_all_alerts(self, alert_svc, sample_rules):
        """Test listing all alerts."""
        metrics = [{
            'metric_name': 'gpu_temperature', 'current_value': 90,
            'target_type': 'node', 'target_id': 'node-7',
        }]
        alert_svc.evaluate_all(metrics)

        alerts_list, total = alert_svc.list_alerts()
        assert total >= 1

    def test_list_by_status(self, alert_svc, sample_rules):
        """Test filtering alerts by status."""
        metrics = [{
            'metric_name': 'cpu_percent', 'current_value': 98,
            'target_type': 'node', 'target_id': 'node-8',
        }]
        alert_svc.evaluate_all(metrics)

        alerts_list, total = alert_svc.list_alerts(status='open')
        for alert in alerts_list:
            assert alert['status'] == 'open'

    def test_default_rules_insertion(self, alert_svc):
        """Test that default rules are inserted when DB is empty."""
        count = alert_svc.load_default_rules()
        assert count > 0
        rules = alert_svc.get_rules()
        assert len(rules) == count

    def test_default_rules_idempotent(self, alert_svc):
        """Test that loading default rules twice doesn't duplicate."""
        first = alert_svc.load_default_rules()
        second = alert_svc.load_default_rules()
        assert first == second
