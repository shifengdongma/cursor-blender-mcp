# -*- coding: utf-8 -*-
"""Generic REST API inventory provider.

Uses config_metadata from the cloud_accounts table to configure:
  - base_url: Base URL of the inventory API
  - list_hosts_path: Path for listing hosts (default: /hosts)
  - headers: Custom headers (JSON dict)
  - status_mapping: Dict mapping provider status → standard status
  - response_root: JSONPath-like root key in response (default: 'hosts')

Auth: Bearer token from GENERIC_REST_TOKEN env var.
"""
from __future__ import absolute_import

import logging
import time

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None

from .base import CloudInventoryProvider


class GenericRestProvider(CloudInventoryProvider):
    """Configurable REST API inventory provider."""

    PROVIDER_TYPE = 'generic_rest'

    def __init__(self, base_url, token='', config_metadata=None):
        self.base_url = base_url.rstrip('/') if base_url else ''
        self.token = token
        self.config = config_metadata or {}
        self._status_map = self.config.get('status_mapping', {})

    def _get_headers(self):
        headers = {'Authorization': 'Bearer {0}'.format(self.token)} if self.token else {}
        custom = self.config.get('headers', {}) or {}
        headers.update(custom)
        return headers

    def _parse_host(self, raw):
        """Map generic API host fields to ComputeNode-compatible dict."""
        status = str(raw.get('status', '') or raw.get('state', ''))

        # Apply custom status mapping
        for raw_val, std in self._status_map.items():
            if status.lower() == raw_val.lower():
                status = std
                break

        return {
            'node_name': raw.get('name') or raw.get('hostname') or raw.get('id', ''),
            'provider_type': self.PROVIDER_TYPE,
            'external_id': str(raw.get('id') or raw.get('instance_id', '')),
            'ip_address': raw.get('ip') or raw.get('ip_address') or raw.get('address'),
            'region': raw.get('region') or raw.get('datacenter', 'default'),
            'zone': raw.get('zone') or raw.get('az'),
            'cluster_name': raw.get('cluster'),
            'cpu_cores': int(raw.get('cpu') or raw.get('cpu_cores', 0)),
            'memory_mb': int(raw.get('memory') or raw.get('memory_mb') or raw.get('ram', 0)),
            'disk_gb': int(raw.get('disk') or raw.get('disk_gb') or raw.get('storage', 0)),
            'gpu_type': raw.get('gpu_type') or raw.get('gpu_model'),
            'gpu_count': int(raw.get('gpu_count') or raw.get('gpus', 0)),
            'gpu_memory_mb': int(raw.get('gpu_memory') or raw.get('gpu_memory_mb', 0)),
            'status': self.normalize_status(status),
            'schedulable': 1 if self.normalize_status(status) == 'online' else 0,
            'metadata': raw.get('metadata', {}),
        }

    def list_hosts(self, region=None):
        if requests is None:
            raise RuntimeError("requests library not available")

        list_path = self.config.get('list_hosts_path', '/hosts')
        response_root = self.config.get('response_root', 'hosts')

        url = '{0}{1}'.format(self.base_url, list_path)
        params = {}
        if region:
            params['region'] = region

        resp = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        hosts = data
        for key in response_root.split('.'):
            if isinstance(hosts, dict):
                hosts = hosts.get(key, [])
            else:
                break

        if not isinstance(hosts, list):
            hosts = [hosts] if hosts else []

        return [self._parse_host(h) for h in hosts]

    def get_host(self, external_id):
        hosts = self.list_hosts()
        for h in hosts:
            if h.get('external_id') == str(external_id):
                return h
        return None

    def health_check(self):
        start = time.time()
        try:
            if requests is None:
                return {'ok': False, 'latency_ms': 0, 'error': 'requests library not available'}
            url = '{0}{1}'.format(self.base_url, self.config.get('health_path', '/health'))
            resp = requests.get(url, headers=self._get_headers(), timeout=10)
            ok = resp.status_code < 500
            return {'ok': ok, 'latency_ms': int((time.time() - start) * 1000), 'error': None if ok else 'HTTP {0}'.format(resp.status_code)}
        except Exception as e:
            return {'ok': False, 'latency_ms': int((time.time() - start) * 1000), 'error': str(e)[:500]}
