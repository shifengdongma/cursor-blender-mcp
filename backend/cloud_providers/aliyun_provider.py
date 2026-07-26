# -*- coding: utf-8 -*-
"""Alibaba Cloud ECS inventory provider."""
from __future__ import absolute_import

import hashlib
import hmac
import logging
import time
import urllib.parse

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None

from .base import CloudInventoryProvider

# ── GPU instance type prefix-to-GPU mapping ──
_GPU_TYPE_MAP = {
    'ecs.gn6': 'T4',
    'ecs.gn6v': 'V100',
    'ecs.gn6i': 'T4',
    'ecs.gn7': 'A10',
    'ecs.gn7i': 'A10',
    'ecs.gn8': 'A100',
    'ecs.ebmgn7': 'A10',
    'ecs.ebmgn8': 'A100',
}

# GPU count per instance type family
_GPU_COUNT_MAP = {
    'ecs.gn6i-c4g1': 1,
    'ecs.gn6i-c8g1': 1,
    'ecs.gn6i-c16g1': 1,
    'ecs.gn6v-c8g1': 1,
    'ecs.gn7i-c8g1': 1,
    'ecs.gn7i-c16g1': 1,
    'ecs.gn7i-c32g1': 1,
    'ecs.gn7i-c48g2': 2,
    'ecs.gn8-c24g1': 1,
    'ecs.gn8-c48g1': 1,
    'ecs.gn8-c96g2': 2,
    'ecs.ebmgn7-c24g1': 1,
    'ecs.ebmgn8-c48g1': 1,
}


class AliyunProvider(CloudInventoryProvider):
    """Alibaba Cloud ECS inventory using Signature V1."""

    PROVIDER_TYPE = 'aliyun'

    def __init__(self, access_key_id, access_key_secret, region_id='cn-hangzhou'):
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.region_id = region_id
        self.endpoint = 'ecs.{0}.aliyuncs.com'.format(region_id)

    def _sign(self, params):
        """Aliyun Signature V1."""
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        canonical = '&'.join([
            '{0}={1}'.format(
                urllib.parse.quote(str(k), safe=''),
                urllib.parse.quote(str(v), safe='')
            )
            for k, v in sorted_params
        ])
        string_to_sign = 'GET&{0}&{1}'.format(
            urllib.parse.quote('/', safe=''),
            urllib.parse.quote(canonical, safe='')
        )
        key = self.access_key_secret + '&'
        signature = hmac.new(
            key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        ).digest()
        import base64
        return base64.b64encode(signature).decode('utf-8')

    def _request(self, action, extra_params=None):
        """Send a signed GET request to Aliyun ECS API."""
        if requests is None:
            raise RuntimeError("requests library not available")

        params = {
            'Action': action,
            'Format': 'JSON',
            'Version': '2014-05-26',
            'AccessKeyId': self.access_key_id,
            'SignatureMethod': 'HMAC-SHA1',
            'SignatureVersion': '1.0',
            'SignatureNonce': str(int(time.time() * 1000000)),
            'Timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'RegionId': self.region_id,
        }
        if extra_params:
            params.update(extra_params)

        params['Signature'] = self._sign(params)

        url = 'https://{0}/'.format(self.endpoint)
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _parse_instance(self, instance):
        """Parse ECS instance JSON into ComputeNode-compatible dict."""
        inst_type = (instance.get('InstanceType') or '').split('.')[0] if '.' in (instance.get('InstanceType') or '') else ''
        full_type = (instance.get('InstanceType') or '')

        gpu_type = None
        gpu_count = 0
        gpu_memory_mb = 0
        for prefix, gtype in _GPU_TYPE_MAP.items():
            if inst_type.startswith(prefix):
                gpu_type = gtype
                break
        if full_type in _GPU_COUNT_MAP:
            gpu_count = _GPU_COUNT_MAP[full_type]

        ip_addr = None
        ips = instance.get('PublicIpAddress', {}).get('IpAddress', [])
        if ips:
            ip_addr = ips[0]
        else:
            ips = instance.get('VpcAttributes', {}).get('PrivateIpAddress', {}).get('IpAddress', [])
            if ips:
                ip_addr = ips[0]

        return {
            'node_name': instance.get('InstanceName') or instance.get('InstanceId', ''),
            'provider_type': self.PROVIDER_TYPE,
            'external_id': instance.get('InstanceId', ''),
            'ip_address': ip_addr,
            'region': instance.get('RegionId') or self.region_id,
            'zone': instance.get('ZoneId'),
            'cluster_name': instance.get('ClusterId'),
            'cpu_cores': int(instance.get('Cpu', 0)),
            'memory_mb': int(instance.get('Memory', 0)),
            'disk_gb': 0,  # requires separate DescribeDisks call
            'gpu_type': gpu_type,
            'gpu_count': gpu_count,
            'gpu_memory_mb': gpu_memory_mb,
            'status': self.normalize_status(instance.get('Status')),
            'schedulable': 1 if instance.get('Status') == 'Running' else 0,
            'metadata': {
                'instance_type': instance.get('InstanceType'),
                'os_name': instance.get('OSName'),
                'creation_time': instance.get('CreationTime'),
            },
        }

    def list_hosts(self, region=None):
        all_instances = []
        page_number = 1
        page_size = 50

        while True:
            params = {
                'PageNumber': str(page_number),
                'PageSize': str(page_size),
            }
            if region:
                params['RegionId'] = region

            result = self._request('DescribeInstances', params)
            instances = result.get('Instances', {}).get('Instance', [])
            all_instances.extend(instances)

            total = int(result.get('TotalCount', 0))
            if page_number * page_size >= total:
                break
            page_number += 1

        return [self._parse_instance(i) for i in all_instances]

    def get_host(self, external_id):
        result = self._request('DescribeInstances', {'InstanceIds': '[{0}]'.format(external_id)})
        instances = result.get('Instances', {}).get('Instance', [])
        if not instances:
            return None
        return self._parse_instance(instances[0])

    def health_check(self):
        start = time.time()
        try:
            self._request('DescribeRegions')
            return {'ok': True, 'latency_ms': int((time.time() - start) * 1000), 'error': None}
        except Exception as e:
            return {'ok': False, 'latency_ms': int((time.time() - start) * 1000), 'error': str(e)[:500]}
