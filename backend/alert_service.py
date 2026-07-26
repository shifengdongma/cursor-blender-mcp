# -*- coding: utf-8 -*-
"""
Alert Service: Rules evaluation, alert lifecycle management for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import logging
import os
import time
import uuid

from .database import get_database
from .models import Alert, AlertEvent, AlertRule

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def _generate_id():
    return str(uuid.uuid4())


OPERATORS = {
    'gt': lambda val, thresh: val > thresh,
    'lt': lambda val, thresh: val < thresh,
    'gte': lambda val, thresh: val >= thresh,
    'lte': lambda val, thresh: val <= thresh,
    'eq': lambda val, thresh: val == thresh,
}


class AlertService(object):
    """Alert rules evaluation and lifecycle management."""

    DEFAULT_RULES = [
        {'rule_type': 'threshold', 'target_type': 'node', 'metric_name': 'gpu_temperature',
         'operator': 'gt', 'threshold': 85, 'duration_s': 30, 'severity': 'error',
         'metadata': {'description': 'GPU temperature exceeds 85C'}},
        {'rule_type': 'threshold', 'target_type': 'node', 'metric_name': 'gpu_utilization',
         'operator': 'gt', 'threshold': 95, 'duration_s': 120, 'severity': 'warning',
         'metadata': {'description': 'GPU utilization exceeds 95%'}},
        {'rule_type': 'threshold', 'target_type': 'node', 'metric_name': 'gpu_memory_percent',
         'operator': 'gt', 'threshold': 95, 'duration_s': 60, 'severity': 'warning',
         'metadata': {'description': 'GPU memory usage exceeds 95%'}},
        {'rule_type': 'heartbeat', 'target_type': 'node', 'metric_name': 'heartbeat',
         'operator': 'gt', 'threshold': 15, 'duration_s': 15, 'severity': 'critical',
         'metadata': {'description': 'Node heartbeat missing for more than 15 seconds'}},
        {'rule_type': 'health_check', 'target_type': 'node', 'metric_name': 'health_fail_count',
         'operator': 'gte', 'threshold': 3, 'duration_s': 10, 'severity': 'critical',
         'metadata': {'description': 'Health check failed 3 consecutive times'}},
        {'rule_type': 'threshold', 'target_type': 'storage', 'metric_name': 'disk_usage_pct',
         'operator': 'gt', 'threshold': 90, 'duration_s': 30, 'severity': 'warning',
         'metadata': {'description': 'Disk usage exceeds 90%'}},
        {'rule_type': 'threshold', 'target_type': 'storage', 'metric_name': 'free_bytes',
         'operator': 'lt', 'threshold': 10 * 1024 * 1024 * 1024, 'duration_s': 30, 'severity': 'error',
         'metadata': {'description': 'Free disk space below 10GB'}},
        {'rule_type': 'threshold', 'target_type': 'task', 'metric_name': 'failed_count',
         'operator': 'gte', 'threshold': 2, 'duration_s': 60, 'severity': 'warning',
         'metadata': {'description': 'Task failed count >= 2'}},
        {'rule_type': 'budget', 'target_type': 'billing', 'metric_name': 'monthly_usage_pct',
         'operator': 'gt', 'threshold': 90, 'duration_s': 10, 'severity': 'warning',
         'metadata': {'description': 'Monthly budget usage exceeds 90%'}},
    ]

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._alert_states = {}  # Track sustained condition state

    def load_default_rules(self, tenant_id=None):
        """Insert default alert rules if no custom rules file is set."""
        existing = self.db.count('alert_rules')
        if existing > 0:
            logger.info("Alert rules already exist, skipping defaults")
            return existing

        count = 0
        for rule_data in self.DEFAULT_RULES:
            rule = AlertRule(
                tenant_id=tenant_id,
                rule_type=rule_data['rule_type'],
                target_type=rule_data.get('target_type'),
                metric_name=rule_data.get('metric_name'),
                operator=rule_data.get('operator', 'gt'),
                threshold=rule_data.get('threshold', 0),
                duration_s=rule_data.get('duration_s', 30),
                severity=rule_data.get('severity', 'warning'),
                metadata=rule_data.get('metadata', {}),
            )
            self.db.insert(AlertRule.TABLE_NAME, rule.to_insert_params())
            count += 1

        logger.info("Inserted %d default alert rules", count)
        return count

    def load_rules_from_file(self, file_path, tenant_id=None):
        """Load alert rules from a JSON file."""
        if not os.path.exists(file_path):
            logger.warning("Alert rules file not found: %s", file_path)
            return 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
        except (IOError, ValueError) as e:
            logger.error("Failed to load alert rules file: %s", str(e))
            return 0

        count = 0
        for rule_data in rules_data:
            rule = AlertRule(
                tenant_id=tenant_id or rule_data.get('tenant_id'),
                rule_type=rule_data.get('rule_type', 'threshold'),
                target_type=rule_data.get('target_type'),
                metric_name=rule_data.get('metric_name'),
                operator=rule_data.get('operator', 'gt'),
                threshold=rule_data.get('threshold', 0),
                duration_s=rule_data.get('duration_s', 30),
                severity=rule_data.get('severity', 'warning'),
                enabled=rule_data.get('enabled', 1),
                metadata=rule_data.get('metadata', {}),
            )
            self.db.insert(AlertRule.TABLE_NAME, rule.to_insert_params())
            count += 1

        logger.info("Loaded %d alert rules from %s", count, file_path)
        return count

    def get_rules(self, enabled_only=True):
        """Get all alert rules."""
        if enabled_only:
            rows = self.db.fetch_all('SELECT * FROM alert_rules WHERE enabled = 1')
        else:
            rows = self.db.fetch_all('SELECT * FROM alert_rules')
        return [AlertRule.from_row(row).to_dict() for row in rows]

    def evaluate_rule(self, rule, current_value, target_id, target_type=None):
        """
        Evaluate a single alert rule against a current metric value.
        Returns True if alert should fire.
        """
        rule_type = rule.get('rule_type', 'threshold')
        operator_fn = OPERATORS.get(rule.get('operator'))

        if operator_fn is None:
            return False

        threshold = rule.get('threshold', 0)

        if rule_type == 'heartbeat':
            # Special handling: check if last heartbeat exceeds threshold
            return current_value is None or current_value > threshold
        elif rule_type == 'health_check':
            # Special handling: consecutive failures
            return current_value is not None and current_value >= threshold
        elif rule_type == 'budget':
            return current_value is not None and operator_fn(current_value, threshold)
        else:
            # Standard threshold comparison
            if current_value is None:
                return False
            return operator_fn(current_value, threshold)

    def evaluate_all(self, metrics_batch, tenant_id=None):
        """
        Evaluate all enabled rules against a batch of metrics.
        metrics_batch: list of dicts with keys: metric_name, current_value, target_type, target_id
        """
        rules = self.get_rules(enabled_only=True)
        now = _now()
        results = []

        for rule_dict in rules:
            rule_id = rule_dict['id']
            if not rule_dict.get('enabled'):
                continue

            for metric in metrics_batch:
                metric_name = metric.get('metric_name')
                if metric_name != rule_dict.get('metric_name'):
                    continue

                target_id = metric.get('target_id', 'local')
                target_type = metric.get('target_type', rule_dict.get('target_type', 'node'))
                current_value = metric.get('current_value')

                triggered = self.evaluate_rule(rule_dict, current_value, target_id, target_type)

                # Dedup: check existing open alert
                existing = self._check_dup(rule_id, target_id)

                if triggered:
                    if existing:
                        # Update existing alert
                        self._update_alert_trigger(existing, current_value, rule_dict)
                        results.append({'action': 'updated', 'alert_id': existing['id']})
                    else:
                        # Check sustained duration
                        state_key = '{0}:{1}:{2}'.format(rule_id, target_type, target_id)
                        state = self._alert_states.get(state_key, {'breach_start': now, 'alert_created': False})
                        duration = now - state['breach_start']
                        if duration >= rule_dict.get('duration_s', 30) and not state['alert_created']:
                            alert = self._create_alert(rule_dict, target_id, target_type, current_value, tenant_id)
                            state['alert_created'] = True
                            self._alert_states[state_key] = state
                            results.append({'action': 'created', 'alert_id': alert['id']})
                        elif not state.get('alert_created'):
                            self._alert_states[state_key] = state
                            results.append({'action': 'breach_detected', 'rule_id': rule_id, 'duration': duration})
                else:
                    # Check for recovery
                    if existing:
                        self._mark_recovered(existing)
                        results.append({'action': 'recovered', 'alert_id': existing['id']})

                    # Reset sustained state
                    state_key = '{0}:{1}:{2}'.format(rule_id, target_type, target_id)
                    if state_key in self._alert_states:
                        del self._alert_states[state_key]

        return results

    def _check_dup(self, rule_id, target_id):
        """Check for existing open alert for same rule+target."""
        rows = self.db.fetch_all(
            "SELECT * FROM alerts WHERE rule_id = ? AND target_id = ? AND status IN ('open', 'acknowledged', 'processing')",
            (rule_id, target_id)
        )
        if rows:
            return dict(rows[0])
        return None

    def _create_alert(self, rule, target_id, target_type, current_value, tenant_id=None):
        """Create a new alert and triggered event."""
        alert = Alert(
            tenant_id=tenant_id,
            rule_id=rule['id'],
            target_type=target_type,
            target_id=target_id,
            metric_name=rule.get('metric_name'),
            current_value=current_value,
            threshold_value=rule.get('threshold'),
            status=Alert.STATUS_OPEN,
            severity=rule.get('severity', 'warning'),
            first_triggered_at=_now(),
            last_triggered_at=_now(),
            metadata={'rule_type': rule.get('rule_type'), 'rule_metadata': rule.get('metadata')},
        )
        self.db.insert(Alert.TABLE_NAME, alert.to_insert_params())

        # Create triggered event
        event = AlertEvent(
            alert_id=alert.id,
            event_type=AlertEvent.EVENT_TRIGGERED,
            message='Alert triggered: {0} {1} {2} (value={3}, threshold={4})'.format(
                rule.get('metric_name', ''), rule.get('operator', ''),
                rule.get('threshold'), current_value, rule.get('threshold')
            ),
            metadata={'current_value': current_value},
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())

        logger.warning("Alert created: %s for %s/%s", alert.id, target_type, target_id)
        return alert.to_dict()

    def _update_alert_trigger(self, existing_alert, current_value, rule):
        """Update an existing open alert."""
        self.db.update('alerts', {
            'current_value': current_value,
            'last_triggered_at': _now(),
            'updated_at': _now(),
        }, 'id = ?', (existing_alert['id'],))

    def _mark_recovered(self, existing_alert):
        """Mark an alert as recovered."""
        now = _now()
        self.db.update('alerts', {
            'status': Alert.STATUS_RECOVERED,
            'recovered_at': now,
            'updated_at': now,
        }, 'id = ?', (existing_alert['id'],))

        event = AlertEvent(
            alert_id=existing_alert['id'],
            event_type=AlertEvent.EVENT_RECOVERED,
            message='Alert recovered automatically',
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())
        logger.info("Alert %s marked as recovered", existing_alert['id'])

    def acknowledge_alert(self, alert_id, user_id):
        """Acknowledge an alert."""
        alert_row = self.db.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert_row:
            return None

        now = _now()
        self.db.update('alerts', {
            'status': Alert.STATUS_ACKNOWLEDGED,
            'acknowledged_by': user_id,
            'updated_at': now,
        }, 'id = ?', (alert_id,))

        event = AlertEvent(
            alert_id=alert_id,
            event_type=AlertEvent.EVENT_ACKNOWLEDGED,
            user_id=user_id,
            message='Alert acknowledged',
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())
        return self.get_alert_detail(alert_id)

    def assign_alert(self, alert_id, user_id):
        """Assign an alert to a user."""
        alert_row = self.db.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert_row:
            return None

        now = _now()
        self.db.update('alerts', {
            'status': Alert.STATUS_PROCESSING,
            'updated_at': now,
        }, 'id = ?', (alert_id,))

        event = AlertEvent(
            alert_id=alert_id,
            event_type=AlertEvent.EVENT_ASSIGNED,
            user_id=user_id,
            message='Alert assigned to user',
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())
        return self.get_alert_detail(alert_id)

    def close_alert(self, alert_id, user_id, notes=None):
        """Close an alert."""
        alert_row = self.db.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert_row:
            return None

        now = _now()
        self.db.update('alerts', {
            'status': Alert.STATUS_CLOSED,
            'closed_by': user_id,
            'closed_at': now,
            'notes': notes,
            'updated_at': now,
        }, 'id = ?', (alert_id,))

        event = AlertEvent(
            alert_id=alert_id,
            event_type=AlertEvent.EVENT_CLOSED,
            user_id=user_id,
            message='Alert closed%s' % (': ' + notes if notes else ''),
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())
        return self.get_alert_detail(alert_id)

    def add_comment(self, alert_id, user_id, message):
        """Add a comment event to an alert."""
        alert_row = self.db.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert_row:
            return None

        event = AlertEvent(
            alert_id=alert_id,
            event_type=AlertEvent.EVENT_COMMENTED,
            user_id=user_id,
            message=message,
        )
        self.db.insert(AlertEvent.TABLE_NAME, event.to_insert_params())
        return event.to_dict()

    def list_alerts(self, status=None, severity=None, limit=50, offset=0):
        """List alerts with optional filters."""
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = "SELECT * FROM alerts WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?".format(where_clause)
        params.extend([limit, offset])

        rows = self.db.fetch_all(query, tuple(params))
        total = self.db.count('alerts', where_clause, tuple(params[:len(params)-2]) if params else None)
        return [Alert.from_row(row).to_dict() for row in rows], total

    def get_alert_detail(self, alert_id):
        """Get alert detail with event history."""
        alert_row = self.db.fetch_one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        if not alert_row:
            return None

        alert = Alert.from_row(alert_row)

        events_rows = self.db.fetch_all(
            "SELECT * FROM alert_events WHERE alert_id = ? ORDER BY created_at ASC",
            (alert_id,)
        )
        events = [AlertEvent.from_row(row).to_dict() for row in events_rows]

        result = alert.to_dict()
        result['events'] = events
        return result

    def get_alert_stats(self):
        """Get alert statistics by status and severity."""
        stats = {'total': 0, 'by_status': {}, 'by_severity': {}}
        query = "SELECT status, severity, COUNT(*) as cnt FROM alerts GROUP BY status, severity"
        rows = self.db.fetch_all(query)
        for row in rows:
            stats['total'] += row['cnt']
            status = row['status']
            severity = row['severity']
            stats['by_status'][status] = stats['by_status'].get(status, 0) + row['cnt']
            stats['by_severity'][severity] = stats['by_severity'].get(severity, 0) + row['cnt']
        return stats

    def create_rule(self, rule_data):
        """Create or update an alert rule."""
        rule = AlertRule(
            tenant_id=rule_data.get('tenant_id'),
            rule_type=rule_data.get('rule_type', 'threshold'),
            target_type=rule_data.get('target_type'),
            metric_name=rule_data.get('metric_name'),
            operator=rule_data.get('operator', 'gt'),
            threshold=rule_data.get('threshold', 0),
            duration_s=rule_data.get('duration_s', 30),
            severity=rule_data.get('severity', 'warning'),
            enabled=rule_data.get('enabled', 1),
            metadata=rule_data.get('metadata'),
        )
        self.db.insert(AlertRule.TABLE_NAME, rule.to_insert_params())
        return rule.to_dict()


def get_alert_service(data_dir=None):
    return AlertService(data_dir)
