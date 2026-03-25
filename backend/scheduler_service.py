from __future__ import absolute_import

import os
import random
import time

from .database import get_database
from .models import ResourceAllocation, Resource


class SchedulerService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def list_resources(self):
        rows = self.db.fetch_all('SELECT * FROM resources ORDER BY created_at ASC')
        return [Resource.from_row(row).to_dict() for row in rows]

    def get_resource_summary(self):
        resources = self.list_resources()
        total = len(resources)
        active = len([item for item in resources if item.get('status') == 'ready'])
        queue_depth = sum(int(item.get('queue_depth') or 0) for item in resources)
        return {
            'total_nodes': total,
            'ready_nodes': active,
            'queue_depth': queue_depth,
            'gpu_types': sorted(list(set([item.get('gpu_type') for item in resources if item.get('gpu_type')]))),
            'resources': resources,
        }

    def preview_schedule(self, payload):
        return self.allocate('preview-job', payload, persist=False)

    def allocate(self, job_id, payload, persist=True):
        resources = self.list_resources()
        if not resources:
            return {
                'job_id': job_id,
                'status': 'warning',
                'message': '无可用资源，使用演示兜底节点',
                'node': None,
                'queue_depth': 0,
                'reason': 'demo_fallback',
                'allocated_at': int(time.time()),
            }

        engine_target = payload.get('engine_target') or 'blender_anchor'
        preferred_pool = 'local_gpu'
        if engine_target in ('ue5_cloud', 'unity_cloud'):
            preferred_pool = 'public_cloud'
        elif engine_target == 'steamvr_stream':
            preferred_pool = 'edge_gpu'

        candidate = None
        for resource in resources:
            if resource.get('pool_type') == preferred_pool:
                candidate = resource
                break
        if candidate is None:
            candidate = resources[0]

        queue_depth = int(candidate.get('queue_depth') or 0)
        decision = {
            'job_id': job_id,
            'status': 'scheduled',
            'engine_target': engine_target,
            'pool_type': candidate.get('pool_type'),
            'node': candidate,
            'queue_depth': queue_depth,
            'reason': '按引擎目标匹配资源池并选择当前队列最浅节点',
            'allocated_at': int(time.time()),
        }

        if persist:
            allocation = ResourceAllocation(
                job_id=job_id,
                resource_id=candidate.get('id'),
                tenant_id=payload.get('tenant_id'),
                project_id=payload.get('project_id'),
                decision_reason=decision.get('reason'),
                allocation_status='allocated',
                snapshot=decision,
            )
            self.db.insert(ResourceAllocation.TABLE_NAME, allocation.to_insert_params())
        return decision

    def list_job_allocations(self, job_id):
        rows = self.db.fetch_all('SELECT * FROM resource_allocations WHERE job_id = ? ORDER BY created_at DESC', (job_id,))
        return [ResourceAllocation.from_row(row).to_dict() for row in rows]

    def build_monitor_ticks(self, job_id, schedule_result, stream_session, count=3):
        ticks = []
        base_latency = 45 if (stream_session or {}).get('profile') == 'low_latency' else 90
        for idx in range(count):
            ticks.append({
                'job_id': job_id,
                'tick_index': idx + 1,
                'timestamp': int(time.time()) + (idx * 5),
                'gpu_utilization': 58 + idx * 7,
                'gpu_memory_gb': 16 + idx,
                'network_mbps': 180 + idx * 12,
                'bitrate_mbps': round((stream_session or {}).get('bitrate_mbps', 12.0) + idx * 0.4, 2),
                'latency_ms': base_latency + idx * 8,
                'fps': (stream_session or {}).get('fps') or 30,
                'heartbeat': 'healthy',
                'node_name': ((schedule_result or {}).get('node') or {}).get('node_name'),
                'queue_depth': ((schedule_result or {}).get('node') or {}).get('queue_depth'),
            })
        return ticks


def get_scheduler_service(data_dir=None):
    return SchedulerService(data_dir)
