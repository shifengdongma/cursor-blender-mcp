# -*- coding: utf-8 -*-
"""VMware vSphere REST API inventory provider."""
from __future__ import absolute_import

import logging
import time

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None

from .base import CloudInventoryProvider


class VMwareProvider(CloudInventoryProvider):
    """VMware vSphere inventory via REST API (session auth)."""

    PROVIDER_TYPE = 'vmware'

    def __init__(self, host, username, password):
        self.host = host.rstrip('/')
        self.username = username
        self.password = password
        self._session_id = None

    def _login(self):
        """Create a session with vSphere REST API."""
        if requests is None:
            raise RuntimeError("requests library not available")

        url = '{0}/rest/com/vmware/cis/session'.format(self.host)
        resp = requests.post(
            url,
            auth=(self.username, self.password),
            headers={'Content-Type': 'application/json'},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        self._session_id = resp.json().get('value')

    def _logout(self):
        """Delete the current session."""
        if not self._session_id:
            return
        try:
            url = '{0}/rest/com/vmware/cis/session'.format(self.host)
            requests.delete(
                url,
                headers={'vmware-api-session-id': self._session_id},
                timeout=5,
                verify=False,
            )
        except Exception:
            pass
        self._session_id = None

    def _ensure_session(self):
        if not self._session_id:
            self._login()

    def _get_vms(self):
        """Get all VMs and their hardware info."""
        self._ensure_session()
        headers = {
            'vmware-api-session-id': self._session_id,
            'Content-Type': 'application/json',
        }

        # Get VM list
        url = '{0}/rest/vcenter/vm'.format(self.host)
        resp = requests.get(url, headers=headers, timeout=30, verify=False)
        resp.raise_for_status()
        vm_list = resp.json().get('value', [])

        hosts = []
        for vm_ref in vm_list:
            vm_id = vm_ref.get('vm')
            name = vm_ref.get('name', vm_id)

            # Get VM details
            url_vm = '{0}/rest/vcenter/vm/{1}'.format(self.host, vm_id)
            try:
                resp_vm = requests.get(url_vm, headers=headers, timeout=10, verify=False)
                vm_detail = resp_vm.json().get('value', {})
            except Exception:
                vm_detail = {}

            # Get VM hardware
            url_hw = '{0}/rest/vcenter/vm/{1}/hardware'.format(self.host, vm_id)
            try:
                resp_hw = requests.get(url_hw, headers=headers, timeout=10, verify=False)
                hw_info = resp_hw.json().get('value', {})
            except Exception:
                hw_info = {}

            host = self._parse_vm(vm_id, name, vm_detail, hw_info)
            hosts.append(host)

        return hosts

    def _parse_vm(self, vm_id, name, vm_detail, hw_info):
        """Parse VM info into ComputeNode-compatible dict."""
        power_state = vm_detail.get('power_state', '')
        memory_mb = hw_info.get('memory', {}).get('size_MiB', 0)
        cpu_count = hw_info.get('cpu', {}).get('count', 0)
        cpu_cores = cpu_count * (hw_info.get('cpu', {}).get('cores_per_socket', 1))

        # Check for GPU passthrough (pci_devices)
        gpu_count = 0
        gpu_type = None
        try:
            self._ensure_session()
            headers = {'vmware-api-session-id': self._session_id}
            url_pci = '{0}/rest/vcenter/vm/{1}/hardware/pci'.format(self.host, vm_id)
            resp_pci = requests.get(url_pci, headers=headers, timeout=10, verify=False)
            pci_devices = resp_pci.json().get('value', [])
            gpu_devices = [
                d for d in pci_devices
                if any(kw in (d.get('label') or '') for kw in ['NVIDIA', 'AMD', 'Graphics'])
            ]
            gpu_count = len(gpu_devices)
            if gpu_devices:
                gpu_type = 'passthrough_gpu'
        except Exception:
            pass

        return {
            'node_name': name,
            'provider_type': self.PROVIDER_TYPE,
            'external_id': vm_id,
            'ip_address': vm_detail.get('guest_OS') or ', '.join(vm_detail.get('ip_addresses', []) or []),
            'region': 'vcenter',
            'zone': vm_detail.get('guest_OS'),
            'cluster_name': None,
            'cpu_cores': cpu_cores,
            'memory_mb': memory_mb,
            'disk_gb': 0,
            'gpu_type': gpu_type,
            'gpu_count': gpu_count,
            'gpu_memory_mb': 0,
            'status': self.normalize_status(power_state),
            'schedulable': 1 if power_state == 'POWERED_ON' else 0,
            'metadata': {
                'vm_id': vm_id,
                'power_state': power_state,
                'guest_os': vm_detail.get('guest_OS'),
            },
        }

    def list_hosts(self, region=None):
        return self._get_vms()

    def get_host(self, external_id):
        hosts = self._get_vms()
        for h in hosts:
            if h.get('external_id') == external_id:
                return h
        return None

    def health_check(self):
        start = time.time()
        try:
            url = '{0}/rest/com/vmware/cis/session'.format(self.host)
            requests.get(url, auth=(self.username, self.password), timeout=5, verify=False)
            return {'ok': True, 'latency_ms': int((time.time() - start) * 1000), 'error': None}
        except Exception as e:
            return {'ok': False, 'latency_ms': int((time.time() - start) * 1000), 'error': str(e)[:500]}
