# -*- coding: utf-8 -*-
"""Abstract base class for cloud inventory providers."""
from __future__ import absolute_import

import abc


class CloudInventoryProvider(object):
    """Abstract base for all cloud inventory providers.

    Each concrete provider implements list_hosts, get_host, health_check,
    and normalize_status. Credentials are read from env config and never
    stored in the database.
    """
    __metaclass__ = abc.ABCMeta

    STATUS_MAP = {
        'online': 'online',
        'offline': 'offline',
        'error': 'error',
        'maintenance': 'maintenance',
    }

    @abc.abstractmethod
    def list_hosts(self, region=None):
        """List all hosts/inventory from the provider.

        Args:
            region: Optional region filter.

        Returns:
            list of dict with keys matching ComputeNode columns:
            node_name, provider_type, external_id, ip_address, region, zone,
            cpu_cores, memory_mb, disk_gb, gpu_type, gpu_count, gpu_memory_mb,
            status, schedulable, metadata
        """

    @abc.abstractmethod
    def get_host(self, external_id):
        """Get a single host by provider's external ID.

        Returns:
            dict or None
        """

    @abc.abstractmethod
    def health_check(self):
        """Verify connectivity to the provider.

        Returns:
            dict: {'ok': bool, 'latency_ms': float, 'error': str|None}
        """

    def normalize_status(self, provider_status):
        """Map provider-specific status to our standard enum.

        Returns:
            str: 'online' | 'offline' | 'error' | 'maintenance'
        """
        status = (provider_status or '').strip().lower()
        if status in ('running', 'active', 'online', 'ok'):
            return 'online'
        if status in ('stopped', 'stopping', 'offline', 'shutdown'):
            return 'offline'
        if status in ('error', 'failed', 'degraded'):
            return 'error'
        if status in ('maintenance', 'maintaining', 'repairing'):
            return 'maintenance'
        return 'offline'
