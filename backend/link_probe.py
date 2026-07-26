# -*- coding: utf-8 -*-
"""
Link Probe: TCP/HTTP/ICMP network probing for AIGV Studio monitoring.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import logging
import socket
import subprocess
import time

logger = logging.getLogger(__name__)


def _http_get(url, timeout=3):
    """Simple HTTP GET using standard library socket."""
    import sys
    if sys.version_info[0] >= 3:
        from urllib.request import urlopen, Request
    else:
        from urllib2 import urlopen, Request

    req = Request(url)
    req.add_header('User-Agent', 'AIGV-Monitor/1.0')
    start = time.time()
    try:
        resp = urlopen(req, timeout=timeout)
        latency = (time.time() - start) * 1000.0
        return latency, resp.getcode()
    except Exception as e:
        logger.debug("HTTP probe failed for %s: %s", url, str(e))
        return None, None


class LinkProbe(object):
    """Network link probe supporting TCP, HTTP, and ICMP checks."""

    def __init__(self):
        self._consecutive_failures = {}
        self._total_checks = {}
        self._total_failures = {}

    def probe_tcp(self, host, port, timeout=3):
        """Probe TCP endpoint, return {latency_ms, success}."""
        start = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.time() - start) * 1000.0
            return {'latency_ms': round(latency, 2), 'success': True, 'status_code': None}
        except Exception as e:
            logger.debug("TCP probe failed for %s:%s: %s", host, port, str(e))
            return {'latency_ms': None, 'success': False, 'status_code': None}

    def probe_http(self, url, timeout=3):
        """Probe HTTP endpoint, return {latency_ms, success, status_code}."""
        latency, status_code = _http_get(url, timeout=timeout)
        if latency is not None:
            return {'latency_ms': round(latency, 2), 'success': True, 'status_code': status_code}
        return {'latency_ms': None, 'success': False, 'status_code': None}

    def probe_icmp(self, host, timeout=3):
        """Probe with ICMP ping, fall back to TCP:80 if no permissions."""
        try:
            from subprocess import DEVNULL
        except ImportError:
            DEVNULL = open('/dev/null', 'w')

        try:
            start = time.time()
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), host],
                stdout=DEVNULL, stderr=DEVNULL, timeout=timeout + 1,
            )
            if result.returncode == 0:
                latency = (time.time() - start) * 1000.0
                return {'latency_ms': round(latency, 2), 'success': True, 'status_code': None}
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("ICMP probe failed for %s: %s", host, str(e))

        # Fallback to TCP:80
        return self.probe_tcp(host, 80, timeout=timeout)

    def probe_target(self, target_spec):
        """
        Parse and probe a target.
        Format: "name|type|addr"
        - "node1|tcp|10.0.0.11:9100"
        - "api|http|http://10.0.0.12:9108/health"
        - "gateway|icmp|10.0.0.1"
        """
        parts = target_spec.split('|')
        if len(parts) < 3:
            return {
                'target': target_spec.strip(),
                'type': 'unknown',
                'latency_ms': None,
                'success': False,
                'status_code': None,
                'error': 'invalid_spec',
            }

        name = parts[0].strip()
        probe_type = parts[1].strip().lower()
        addr = parts[2].strip()

        if probe_type == 'tcp':
            if ':' in addr:
                host, port_str = addr.rsplit(':', 1)
                port = int(port_str)
            else:
                host, port = addr, 9100
            result = self.probe_tcp(host, port)
        elif probe_type == 'http':
            result = self.probe_http(addr)
        elif probe_type == 'icmp':
            result = self.probe_icmp(addr)
        else:
            return {
                'target': name,
                'type': probe_type,
                'latency_ms': None,
                'success': False,
                'status_code': None,
                'error': 'unknown_type',
            }

        result['target'] = name
        result['type'] = probe_type

        # Track consecutive failures
        key = '{0}:{1}'.format(name, probe_type)
        self._total_checks[key] = self._total_checks.get(key, 0) + 1
        if not result['success']:
            self._total_failures[key] = self._total_failures.get(key, 0) + 1
            self._consecutive_failures[key] = self._consecutive_failures.get(key, 0) + 1
        else:
            self._consecutive_failures[key] = 0

        result['consecutive_failures'] = self._consecutive_failures.get(key, 0)
        total = self._total_checks.get(key, 1)
        failures = self._total_failures.get(key, 0)
        result['packet_loss_pct'] = round((failures / float(total)) * 100.0, 2) if total > 0 else 0.0

        return result

    def probe_all(self, targets_str):
        """Probe all targets from a comma-separated string."""
        if not targets_str or not targets_str.strip():
            return []
        targets = [t.strip() for t in targets_str.split(',') if t.strip()]
        results = []
        for target in targets:
            results.append(self.probe_target(target))
        return results

    def get_stats(self):
        """Return aggregated probe statistics."""
        stats = {}
        for key in self._total_checks:
            total = self._total_checks.get(key, 0)
            failures = self._total_failures.get(key, 0)
            consecutive = self._consecutive_failures.get(key, 0)
            stats[key] = {
                'total_checks': total,
                'total_failures': failures,
                'consecutive_failures': consecutive,
                'availability_pct': round(((total - failures) / float(total)) * 100.0, 2) if total > 0 else 100.0,
            }
        return stats
