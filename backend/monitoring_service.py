# -*- coding: utf-8 -*-
"""
Monitoring Worker: Background monitoring loop for AIGV Studio.
Collects metrics, probes links, evaluates alerts, stores samples.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import logging
import os
import threading
import time
import uuid

from .database import get_database
from .link_probe import LinkProbe
from .models import ComputeNode, HealthCheck, NodeMetricSample

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def _generate_id():
    return str(uuid.uuid4())


class MonitoringWorker(object):
    """Background worker that polls metrics, evaluates alerts, and probes targets."""

    def __init__(self, data_dir=None, interval_s=5, timeout_s=3,
                 monitor_targets='', storage_targets='',
                 node_agent_urls='', node_agent_token=''):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self.monitor_targets_str = monitor_targets
        self.storage_targets_str = storage_targets
        self.node_agent_urls_str = node_agent_urls
        self.node_agent_token = node_agent_token

        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self.link_probe = LinkProbe()
        self.metrics_collector = None
        self.alert_service = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._latest_data = {
            'links': [],
            'samples': [],
            'storage': None,
            'agents': [],
            'alerts_evaluated': 0,
            'last_cycle_at': None,
            'cycle_count': 0,
        }

    def start(self):
        """Start the monitoring worker daemon thread."""
        if self._running:
            logger.warning("MonitoringWorker already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name='monitoring-worker')
        self._thread.start()
        logger.info("MonitoringWorker started (interval=%ds)", self.interval_s)

    def stop(self):
        """Signal graceful shutdown."""
        self._running = False
        logger.info("MonitoringWorker stop signal sent")

    def get_latest_data(self):
        """Get the latest monitoring data snapshot."""
        with self._lock:
            return dict(self._latest_data)

    def _run_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._poll_cycle()
            except Exception as e:
                logger.error("Monitoring cycle error: %s", str(e))

            # Sleep with early wake-up on stop
            for _ in range(self.interval_s):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("MonitoringWorker stopped")

    def _poll_cycle(self):
        """Execute one monitoring poll cycle."""
        now = _now()

        # 1. Collect local metrics
        local_metrics = self._collect_local_metrics()

        # 2. Poll remote agents
        agent_results = self._poll_remote_agents()

        # 3. Run link probes
        link_results = self._probe_links()

        # 4. Collect storage metrics
        storage_data = self._collect_storage()

        # 5. Save samples
        self._save_samples(local_metrics, agent_results, now)

        # 6. Evaluate alert rules
        alert_count = self._evaluate_alerts(local_metrics, agent_results, link_results, storage_data)

        # 7. Clean expired samples
        self._cleanup_old_samples()

        with self._lock:
            self._latest_data = {
                'links': link_results,
                'samples': self._get_recent_samples(),
                'storage': storage_data,
                'agents': agent_results,
                'alerts_evaluated': alert_count,
                'last_cycle_at': now,
                'cycle_count': self._latest_data.get('cycle_count', 0) + 1,
            }

    def _collect_local_metrics(self):
        """Collect local system metrics using MetricsCollector."""
        if self.metrics_collector is None:
            try:
                from .monitoring.local_collector import MetricsCollector
                self.metrics_collector = MetricsCollector()
            except ImportError:
                logger.warning("MetricsCollector not available")
                return None

        try:
            return self.metrics_collector.collect()
        except Exception as e:
            logger.warning("Failed to collect local metrics: %s", str(e))
            return None

    def _probe_links(self):
        """Probe all configured monitoring targets."""
        return self.link_probe.probe_all(self.monitor_targets_str)

    def _collect_storage(self):
        """Collect storage metrics."""
        try:
            from .storage_monitor import StorageMonitor
            monitor = StorageMonitor(self.storage_targets_str)
            return monitor.collect()
        except Exception as e:
            logger.warning("Failed to collect storage: %s", str(e))
            return None

    def _poll_remote_agents(self):
        """Poll remote node agents via HTTP."""
        if not self.node_agent_urls_str:
            return []

        results = []
        import sys
        if sys.version_info[0] >= 3:
            from urllib.request import Request, urlopen
            from urllib.error import URLError
        else:
            from urllib2 import Request, urlopen, URLError

        for agent_url in self.node_agent_urls_str.split(','):
            agent_url = agent_url.strip()
            if not agent_url:
                continue

            try:
                req = Request(agent_url)
                req.add_header('User-Agent', 'AIGV-Monitor/1.0')
                if self.node_agent_token:
                    req.add_header('Authorization', 'Bearer ' + self.node_agent_token)

                start = time.time()
                resp = urlopen(req, timeout=self.timeout_s)
                latency = (time.time() - start) * 1000.0
                data = resp.read()
                if data:
                    payload = json.loads(data)
                else:
                    payload = {}
                results.append({
                    'url': agent_url,
                    'success': True,
                    'latency_ms': round(latency, 2),
                    'data': payload,
                })
            except Exception as e:
                results.append({
                    'url': agent_url,
                    'success': False,
                    'latency_ms': None,
                    'error': str(e),
                })

        return results

    def _ensure_local_node(self, sampled_at):
        """Ensure local compute_node exists for FK reference."""
        node_row = self.db.fetch_one("SELECT id FROM compute_nodes WHERE id = ?", ('local',))
        if not node_row:
            self.db.insert('compute_nodes', {
                'id': 'local',
                'node_name': 'local-host',
                'host_name': 'localhost',
                'status': 'online',
                'schedulable': 1,
                'last_heartbeat_at': sampled_at,
                'created_at': sampled_at,
                'updated_at': sampled_at,
            })

    def _save_samples(self, local_metrics, agent_results, sampled_at):
        """Save metric samples to database."""
        if local_metrics:
            try:
                # Ensure local node exists in compute_nodes for FK
                self._ensure_local_node(sampled_at)

                # Save to node_metric_samples for local node
                sample_id = _generate_id()
                sample = {
                    'id': sample_id,
                    'node_id': 'local',
                    'sampled_at': sampled_at,
                    'cpu_percent': local_metrics.get('cpu_percent'),
                    'memory_percent': local_metrics.get('memory_percent'),
                    'gpu_percent': local_metrics.get('gpu_percent'),
                    'gpu_memory_percent': local_metrics.get('gpu_memory_percent'),
                    'gpu_temperature': local_metrics.get('gpu_temperature'),
                    'disk_read_bps': local_metrics.get('disk_read_bps'),
                    'disk_write_bps': local_metrics.get('disk_write_bps'),
                    'network_rx_bps': local_metrics.get('network_rx_bps'),
                    'network_tx_bps': local_metrics.get('network_tx_bps'),
                    'running_tasks': local_metrics.get('running_tasks', 0),
                    'metadata': json.dumps({'source': 'local'}),
                }
                self.db.insert('node_metric_samples', sample)

                # Update compute_node heartbeat
                self.db.update('compute_nodes', {
                    'last_heartbeat_at': sampled_at,
                    'updated_at': sampled_at,
                }, 'id = ?', ('local',))

            except Exception as e:
                logger.warning("Failed to save local metric sample: %s", str(e))

        # Save agent samples
        for agent_result in agent_results:
            if agent_result.get('success') and agent_result.get('data'):
                try:
                    agent_data = agent_result['data']
                    agent_id = agent_data.get('node_id', 'agent_' + agent_result['url'].replace('://', '_').replace('/', '_'))

                    sample_id = _generate_id()
                    sample = {
                        'id': sample_id,
                        'node_id': agent_id,
                        'sampled_at': sampled_at,
                        'cpu_percent': agent_data.get('cpu_percent'),
                        'memory_percent': agent_data.get('memory_percent'),
                        'gpu_percent': agent_data.get('gpu_percent'),
                        'gpu_memory_percent': agent_data.get('gpu_memory_percent'),
                        'gpu_temperature': agent_data.get('gpu_temperature'),
                        'disk_read_bps': agent_data.get('disk_read_bps'),
                        'disk_write_bps': agent_data.get('disk_write_bps'),
                        'network_rx_bps': agent_data.get('network_rx_bps'),
                        'network_tx_bps': agent_data.get('network_tx_bps'),
                        'running_tasks': agent_data.get('running_tasks', 0),
                        'metadata': json.dumps({'source': 'agent', 'url': agent_result['url']}),
                    }
                    self.db.insert('node_metric_samples', sample)
                except Exception as e:
                    logger.warning("Failed to save agent sample: %s", str(e))

    def _evaluate_alerts(self, local_metrics, agent_results, link_results, storage_data):
        """Evaluate alert rules against collected metrics."""
        if self.alert_service is None:
            try:
                from .alert_service import AlertService
                self.alert_service = AlertService(self.data_dir)
            except ImportError:
                logger.warning("AlertService not available")
                return 0

        metrics_batch = []

        # Local node metrics
        if local_metrics:
            node_id = 'local'
            metrics_batch.append({
                'metric_name': 'cpu_percent', 'current_value': local_metrics.get('cpu_percent'),
                'target_type': 'node', 'target_id': node_id,
            })
            metrics_batch.append({
                'metric_name': 'memory_percent', 'current_value': local_metrics.get('memory_percent'),
                'target_type': 'node', 'target_id': node_id,
            })
            metrics_batch.append({
                'metric_name': 'gpu_utilization', 'current_value': local_metrics.get('gpu_percent'),
                'target_type': 'node', 'target_id': node_id,
            })
            metrics_batch.append({
                'metric_name': 'gpu_memory_percent', 'current_value': local_metrics.get('gpu_memory_percent'),
                'target_type': 'node', 'target_id': node_id,
            })
            if local_metrics.get('gpu_temperature') is not None:
                metrics_batch.append({
                    'metric_name': 'gpu_temperature', 'current_value': local_metrics.get('gpu_temperature'),
                    'target_type': 'node', 'target_id': node_id,
                })

            # Heartbeat check
            heartbeat_age = None
            node_row = self.db.fetch_one("SELECT last_heartbeat_at FROM compute_nodes WHERE id = ?", (node_id,))
            if node_row and node_row.get('last_heartbeat_at'):
                heartbeat_age = _now() - node_row['last_heartbeat_at']
            metrics_batch.append({
                'metric_name': 'heartbeat', 'current_value': heartbeat_age,
                'target_type': 'node', 'target_id': node_id,
            })

        # Link probe metrics
        for link in link_results:
            metrics_batch.append({
                'metric_name': 'health_fail_count',
                'current_value': link.get('consecutive_failures', 0),
                'target_type': link.get('type', 'node'),
                'target_id': link.get('target', 'unknown'),
            })

        # Storage metrics
        if storage_data and storage_data.get('summary'):
            metrics_batch.append({
                'metric_name': 'disk_usage_pct',
                'current_value': storage_data['summary'].get('usage_pct'),
                'target_type': 'storage',
                'target_id': 'local',
            })
            metrics_batch.append({
                'metric_name': 'free_bytes',
                'current_value': storage_data['summary'].get('free_bytes'),
                'target_type': 'storage',
                'target_id': 'local',
            })

        try:
            results = self.alert_service.evaluate_all(metrics_batch)
            return len(results)
        except Exception as e:
            logger.warning("Alert evaluation failed: %s", str(e))
            return 0

    def _get_recent_samples(self, limit=20):
        """Get recent metric samples from database."""
        try:
            rows = self.db.fetch_all(
                'SELECT * FROM node_metric_samples ORDER BY sampled_at DESC LIMIT ?',
                (limit,)
            )
            samples = []
            for row in rows:
                d = dict(row)
                if d.get('metadata'):
                    try:
                        d['metadata'] = json.loads(d['metadata'])
                    except (TypeError, ValueError):
                        pass
                samples.append(d)
            return samples
        except Exception:
            return []

    def _cleanup_old_samples(self):
        """Remove metric samples older than 24 hours."""
        try:
            cutoff = _now() - 86400  # 24 hours
            self.db.execute('DELETE FROM node_metric_samples WHERE sampled_at < ?', (cutoff,))
        except Exception as e:
            logger.debug("Failed to clean old samples: %s", str(e))


def get_monitoring_worker(data_dir=None, **kwargs):
    """Get or create monitoring worker singleton."""
    return MonitoringWorker(data_dir=data_dir, **kwargs)
