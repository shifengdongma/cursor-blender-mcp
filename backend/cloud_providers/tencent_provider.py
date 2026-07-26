# -*- coding: utf-8 -*-
"""Tencent Cloud CVM inventory provider."""
from __future__ import absolute_import

import hashlib
import hmac
import json
import logging
import time

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None

from .base import CloudInventoryProvider

_GPU_TYPE_MAP = {
    'GN10X': 'T4',
    'GN10Xp': 'T4',
    'GN7': 'T4',
    'GN7vi': 'T4',
    'GN8': 'A100',
    'GT4': 'A10',
    'GC1': 'L40',
    'PNV4': 'A10',
    'HCCPNV4h': 'A100',
}


class TencentProvider(CloudInventoryProvider):
    """Tencent Cloud CVM inventory using TC3-HMAC-SHA256."""

    PROVIDER_TYPE = 'tencent'

    def __init__(self, secret_id, secret_key, region='ap-guangzhou'):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        self.endpoint = 'cvm.tencentcloudapi.com'
        self.service = 'cvm'

    def _sign_tc3(self, payload, timestamp):
        """TC3-HMAC-SHA256 signing."""
        date = time.strftime('%Y-%m-%d', time.gmtime(timestamp))
        ct = 'application/json; charset=utf-8'
        canonical_headers = 'content-type:{0}\nhost:{1}\n'.format(ct, self.endpoint)
        signed_headers = 'content-type;host'
        hashed_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        canonical_request = 'POST\n/\n\n{0}\n{1}\n{2}'.format(
            canonical_headers, signed_headers, hashed_payload
        )
        algorithm = 'TC3-HMAC-SHA256'
        credential_scope = '{0}/{1}/tc3_request'.format(date, self.service)
        hashed_canonical = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = '{0}\n{1}\n{2}\n{3}'.format(
            algorithm, timestamp, credential_scope, hashed_canonical
        )

        def _hmac(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

        secret_date = _hmac(('TC3' + self.secret_key).encode('utf-8'), date)
        secret_service = _hmac(secret_date, self.service)
        secret_signing = _hmac(secret_service, 'tc3_request')
        signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        return 'TC3-HMAC-SHA256 Credential={0}/{1}, SignedHeaders={2}, Signature={3}'.format(
            self.secret_id, credential_scope, signed_headers, signature
        )

    def _request(self, action, params_dict=None):
        """Send a signed POST request to Tencent CVM API."""
        if requests is None:
            raise RuntimeError("requests library not available")

        timestamp = int(time.time())
        payload = json.dumps(params_dict or {})
        headers = {
            'Authorization': self._sign_tc3(payload, timestamp),
            'Content-Type': 'application/json; charset=utf-8',
            'Host': self.endpoint,
            'X-TC-Action': action,
            'X-TC-Timestamp': str(timestamp),
            'X-TC-Version': '2017-03-12',
            'X-TC-Region': self.region,
        }
        url = 'https://{0}'.format(self.endpoint)
        resp = requests.post(url, headers=headers, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get('Response', {}).get('Error'):
            raise RuntimeError(data['Response']['Error'].get('Message', 'Unknown CVM error'))
        return data.get('Response', {})

    def _parse_instance(self, instance):
        """Parse CVM instance into ComputeNode-compatible dict."""
        gpu_info = instance.get('GPUInfo', {}) or {}
        gpu_type_raw = gpu_info.get('GPUType') or ''
        gpu_type = _GPU_TYPE_MAP.get(gpu_type_raw, gpu_type_raw)
        gpu_count = int(gpu_info.get('GPUCount', 0))
        gpu_memory_mb = 0

        ip_addr = None
        pub_ips = instance.get('PublicIpAddresses', [])
        if pub_ips:
            ip_addr = pub_ips[0]
        else:
            pri_ips = instance.get('PrivateIpAddresses', [])
            if pri_ips:
                ip_addr = pri_ips[0]

        placement = instance.get('Placement', {}) or {}

        return {
            'node_name': instance.get('InstanceName') or instance.get('InstanceId', ''),
            'provider_type': self.PROVIDER_TYPE,
            'external_id': instance.get('InstanceId', ''),
            'ip_address': ip_addr,
            'region': self.region,
            'zone': placement.get('Zone'),
            'cluster_name': None,
            'cpu_cores': int(instance.get('CPU', 0)),
            'memory_mb': int(instance.get('Memory', 0)),
            'disk_gb': int(instance.get('SystemDisk', {}).get('DiskSize', 0)),
            'gpu_type': gpu_type,
            'gpu_count': gpu_count,
            'gpu_memory_mb': gpu_memory_mb,
            'status': self.normalize_status(instance.get('InstanceState')),
            'schedulable': 1 if instance.get('InstanceState') == 'RUNNING' else 0,
            'metadata': {
                'instance_type': instance.get('InstanceType'),
                'os_name': instance.get('OsName'),
                'created_time': instance.get('CreatedTime'),
            },
        }

    def list_hosts(self, region=None):
        all_instances = []
        offset = 0
        limit_val = 50

        while True:
            params = {'Offset': offset, 'Limit': limit_val}
            if region:
                params['Filters'] = [{'Name': 'zone', 'Values': [region]}]

            result = self._request('DescribeInstances', params)
            instances = result.get('InstanceSet', [])
            all_instances.extend(instances)

            total = result.get('TotalCount', 0)
            if offset + limit_val >= total:
                break
            offset += limit_val

        return [self._parse_instance(i) for i in all_instances]

    def get_host(self, external_id):
        result = self._request('DescribeInstances', {
            'InstanceIds': [external_id]
        })
        instances = result.get('InstanceSet', [])
        if not instances:
            return None
        return self._parse_instance(instances[0])

    def health_check(self):
        start = time.time()
        try:
            self._request('DescribeZones')
            return {'ok': True, 'latency_ms': int((time.time() - start) * 1000), 'error': None}
        except Exception as e:
            return {'ok': False, 'latency_ms': int((time.time() - start) * 1000), 'error': str(e)[:500]}
