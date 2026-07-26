# -*- coding: utf-8 -*-
"""Scheduler service — node allocation with configurable scoring."""
from __future__ import absolute_import

import os
import time

from .config import Config
from .database import get_database
from .models import (
    ResourceAllocation,
    Resource,
    ComputeNode,
    NodeMetricSample,
    SchedulerPolicy,
)
from .scheduler_scorer import NodeScorer, ScheduleRequest, DEFAULT_WEIGHTS

# Parse GPU price map: "A100:150,A10:80,L40:120"
def _parse_gpu_price_map(raw):
    mapping = {}
    if raw:
        for pair in raw.split(','):
            parts = pair.strip().split(':')
            if len(parts) == 2:
                try:
                    mapping[parts[0].strip()] = float(parts[1].strip())
                except ValueError:
                    pass
    return mapping


class SchedulerService(object):
    def __init__(self, data_dir=None, cfg=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.cfg = cfg or Config()
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._gpu_price_map = _parse_gpu_price_map(self.cfg.GPU_PRICE_MAP)

    def _load_policy_weights(self, tenant_id=None):
        """Load scoring weights from scheduler_policies table."""
        if tenant_id:
            row = self.db.fetch_one(
                'SELECT * FROM scheduler_policies WHERE tenant_id = ? AND enabled = 1 ORDER BY created_at DESC LIMIT 1',
                (tenant_id,)
            )
        else:
            row = self.db.fetch_one(
                'SELECT * FROM scheduler_policies WHERE enabled = 1 ORDER BY created_at DESC LIMIT 1'
            )
        if row:
            policy = SchedulerPolicy.from_row(row)
            return policy.scoring_weights or DEFAULT_WEIGHTS
        return DEFAULT_WEIGHTS

    def _get_latest_metrics(self, node_ids):
        """Get latest metric sample for each node."""
        if not node_ids:
            return {}
        placeholders = ','.join(['?' for _ in node_ids])
        rows = self.db.fetch_all(
            'SELECT * FROM node_metric_samples WHERE id IN ('
            '  SELECT id FROM node_metric_samples WHERE node_id IN ({0})'
            '  GROUP BY node_id HAVING MAX(sampled_at)'
            ') ORDER BY sampled_at DESC'.format(placeholders),
            tuple(node_ids)
        )
        return {row['node_id']: NodeMetricSample.from_row(row).to_dict() for row in rows}

    # ── Legacy resource queries (backward compat) ──

    def list_resources(self):
        rows = self.db.fetch_all('SELECT * FROM resources ORDER BY created_at ASC')
        return [Resource.from_row(row).to_dict() for row in rows]

    def get_resource_summary(self):
        """Get resource summary from compute_nodes (real) + resources (legacy)."""
        # From compute_nodes
        nodes = self.db.fetch_all('SELECT status, gpu_type, gpu_count FROM compute_nodes')
        cn_total = len(nodes)
        cn_online = len([n for n in nodes if n['status'] == 'online'])
        cn_gpu_types = sorted(set(n['gpu_type'] for n in nodes if n.get('gpu_type')))

        # From legacy resources
        legacy = self.list_resources()
        legacy_total = len(legacy)
        legacy_ready = len([r for r in legacy if r.get('status') == 'ready'])

        # From render_jobs (queue depth)
        running = self.db.count('render_jobs', "status = 'rendering'")
        queued = self.db.count('render_jobs', "status = 'pending'")

        return {
            'total_nodes': cn_total + legacy_total,
            'online_nodes': cn_online + legacy_ready,
            'queue_depth': running + queued,
            'gpu_types': sorted(set(cn_gpu_types + [
                r.get('gpu_type') for r in legacy if r.get('gpu_type')
            ])),
            'compute_nodes': cn_total,
            'legacy_resources': legacy_total,
            'running_render_jobs': running,
            'queued_render_jobs': queued,
        }

    # ── Real Scheduling ──

    def _get_candidate_nodes(self, tenant_id=None):
        """Get all schedulable compute nodes + legacy resources."""
        # Real nodes
        if tenant_id:
            rows = self.db.fetch_all(
                'SELECT * FROM compute_nodes WHERE schedulable = 1 AND status = ? AND tenant_id = ? ORDER BY updated_at ASC',
                (ComputeNode.STATUS_ONLINE, tenant_id)
            )
        else:
            rows = self.db.fetch_all(
                'SELECT * FROM compute_nodes WHERE schedulable = 1 AND status = ? ORDER BY updated_at ASC',
                (ComputeNode.STATUS_ONLINE,)
            )
        return [ComputeNode.from_row(row).to_dict() for row in rows]

    def preview_schedule(self, payload):
        """Preview scheduling decision — returns top 3 ranked nodes with scores."""
        request = ScheduleRequest.from_dict(payload)

        nodes = self._get_candidate_nodes(payload.get('tenant_id'))

        # If no compute_nodes, fall back to legacy resources
        if not nodes:
            legacy = self.list_resources()
            nodes = [
                {
                    'id': r.get('id', ''),
                    'node_name': r.get('node_name', ''),
                    'provider_type': 'legacy',
                    'region': r.get('region', ''),
                    'gpu_type': r.get('gpu_type', ''),
                    'gpu_count': r.get('capacity_units', 0),
                    'gpu_memory_mb': 0,
                    'cpu_cores': r.get('capacity_units', 0) * 8,
                    'memory_mb': r.get('capacity_units', 0) * 16384,
                    'status': 'online' if r.get('status') == 'ready' else 'offline',
                    'schedulable': r.get('status') == 'ready',
                    'last_heartbeat_at': int(time.time()),
                    'queue_depth': r.get('queue_depth', 0),
                    'utilization_hint': r.get('utilization_hint', 0),
                }
                for r in legacy
            ]

        node_ids = [n.get('id') for n in nodes if n.get('id')]
        metrics_map = self._get_latest_metrics(node_ids)

        tenant_id = payload.get('tenant_id')
        weights = self._load_policy_weights(tenant_id)
        scorer = NodeScorer(weights=weights, gpu_price_map=self._gpu_price_map)

        result = scorer.rank_nodes(nodes, request, metrics_map)

        # Return top 3
        return {
            'job_id': 'preview-job',
            'status': 'preview',
            'top_candidates': result['rankings'][:3],
            'filtered_count': len(result['filtered']),
            'total_candidates': result['total_candidates'],
            'passed_count': result['passed'],
            'scoring_weights': weights,
            'request': {
                'task_type': request.task_type,
                'engine_target': request.engine_target,
                'required_gpu_count': request.required_gpu_count,
                'region_preference': request.region_preference,
            },
        }

    def allocate(self, job_id, payload, persist=True):
        """Allocate the best node for a job using scoring."""
        preview = self.preview_schedule(payload)
        candidates = preview.get('top_candidates', [])

        if not candidates:
            return {
                'job_id': job_id,
                'status': 'warning',
                'message': '无可用调度节点',
                'node': None,
                'queue_depth': 0,
                'reason': 'no_candidates',
                'allocated_at': int(time.time()),
            }

        best = candidates[0]
        node = best.get('node', {})
        decision = {
            'job_id': job_id,
            'status': 'scheduled',
            'node': node,
            'score': best.get('score'),
            'score_breakdown': best.get('score_breakdown'),
            'warnings': best.get('warnings', []),
            'reason': '按多维度评分算法选择最优节点 (score={0})'.format(best.get('score')),
            'allocated_at': int(time.time()),
            'engine_target': payload.get('engine_target', 'blender_anchor'),
            'queue_depth': node.get('queue_depth', 0),
        }

        if persist:
            allocation = ResourceAllocation(
                job_id=job_id,
                resource_id=node.get('id', ''),
                tenant_id=payload.get('tenant_id'),
                project_id=payload.get('project_id'),
                decision_reason=decision.get('reason'),
                allocation_status='allocated',
                snapshot=decision,
            )
            self.db.insert(ResourceAllocation.TABLE_NAME, allocation.to_insert_params())

        return decision

    def re_schedule(self, job_id):
        """Re-schedule a job, excluding the previously allocated node."""
        existing_allocations = self.list_job_allocations(job_id)
        excluded_node_ids = [a.get('resource_id') for a in existing_allocations if a.get('resource_id')]

        # Get current allocation to extract the payload
        job_row = self.db.fetch_one(
            'SELECT * FROM resource_allocations WHERE job_id = ? ORDER BY created_at DESC LIMIT 1',
            (job_id,)
        )
        if not job_row:
            raise ValueError('No allocation found for job {0}'.format(job_id))

        payload = job_row.get('snapshot', '{}')
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        if isinstance(payload, dict):
            payload.pop('node', None)
            payload.pop('score', None)
            payload.pop('score_breakdown', None)

        # Re-run preview excluding previous nodes
        request = ScheduleRequest.from_dict(payload or {})
        nodes = self._get_candidate_nodes(payload.get('tenant_id'))
        nodes = [n for n in nodes if n.get('id') not in excluded_node_ids]

        if not nodes:
            return {
                'job_id': job_id,
                'status': 'error',
                'message': '无可用的替代节点（所有节点均已尝试）',
                'reason': 'no_alternatives',
            }

        node_ids = [n.get('id') for n in nodes if n.get('id')]
        metrics_map = self._get_latest_metrics(node_ids)
        tenant_id = payload.get('tenant_id')
        weights = self._load_policy_weights(tenant_id)
        scorer = NodeScorer(weights=weights, gpu_price_map=self._gpu_price_map)
        result = scorer.rank_nodes(nodes, request, metrics_map)

        if not result['rankings']:
            return {
                'job_id': job_id,
                'status': 'error',
                'message': '无可用的替代节点',
                'reason': 'no_alternatives',
            }

        best = result['rankings'][0]
        node = best.get('node', {})

        # Mark previous allocation as cancelled
        for alloc in existing_allocations:
            self.db.update(
                ResourceAllocation.TABLE_NAME,
                {'allocation_status': 'cancelled', 'updated_at': int(time.time())},
                'id = ?',
                (alloc.get('id'),)
            )

        # Create new allocation
        decision = {
            'job_id': job_id,
            'status': 'rescheduled',
            'node': node,
            'score': best.get('score'),
            'score_breakdown': best.get('score_breakdown'),
            'reason': '重新调度 (attempt {0})'.format(len(existing_allocations) + 1),
            'allocated_at': int(time.time()),
            'previous_allocation_count': len(existing_allocations),
        }

        allocation = ResourceAllocation(
            job_id=job_id,
            resource_id=node.get('id', ''),
            tenant_id=payload.get('tenant_id'),
            project_id=payload.get('project_id'),
            decision_reason=decision.get('reason'),
            allocation_status='allocated',
            snapshot=decision,
        )
        self.db.insert(ResourceAllocation.TABLE_NAME, allocation.to_insert_params())
        return decision

    def cancel_allocation(self, job_id):
        """Cancel all allocations for a job."""
        updated = self.db.update(
            ResourceAllocation.TABLE_NAME,
            {'allocation_status': 'cancelled', 'updated_at': int(time.time())},
            'job_id = ?',
            (job_id,)
        )
        return {'job_id': job_id, 'cancelled': updated > 0}

    def list_job_allocations(self, job_id):
        rows = self.db.fetch_all(
            'SELECT * FROM resource_allocations WHERE job_id = ? ORDER BY created_at DESC',
            (job_id,)
        )
        return [ResourceAllocation.from_row(row).to_dict() for row in rows]

    def build_monitor_ticks(self, job_id, schedule_result, stream_session, count=3):
        """Build monitor ticks — now pulls real metrics for the allocated node."""
        ticks = []
        node = (schedule_result or {}).get('node') or {}
        node_id = node.get('id')
        base_latency = 45 if (stream_session or {}).get('profile') == 'low_latency' else 90

        # Try to get real metrics
        real_metrics = None
        if node_id:
            row = self.db.fetch_one(
                'SELECT * FROM node_metric_samples WHERE node_id = ? ORDER BY sampled_at DESC LIMIT 1',
                (node_id,)
            )
            if row:
                real_metrics = NodeMetricSample.from_row(row).to_dict()

        for idx in range(count):
            tick = {
                'job_id': job_id,
                'tick_index': idx + 1,
                'timestamp': int(time.time()) + (idx * 5),
                'node_name': node.get('node_name'),
                'queue_depth': node.get('queue_depth'),
                'heartbeat': 'healthy',
            }

            if real_metrics:
                tick['gpu_utilization'] = real_metrics.get('gpu_percent') or 0
                tick['gpu_memory_gb'] = int((real_metrics.get('gpu_memory_percent') or 0) / 100 * (node.get('gpu_memory_mb', 0) / 1024))
                tick['network_mbps'] = int((real_metrics.get('network_rx_bps') or 0) / (1024 * 1024) * 8)
                tick['latency_ms'] = real_metrics.get('latency_ms') or base_latency
                tick['bitrate_mbps'] = (stream_session or {}).get('bitrate_mbps', 12.0)
                tick['fps'] = (stream_session or {}).get('fps') or 30
            else:
                tick['gpu_utilization'] = 0
                tick['gpu_memory_gb'] = 0
                tick['network_mbps'] = 0
                tick['latency_ms'] = base_latency
                tick['bitrate_mbps'] = (stream_session or {}).get('bitrate_mbps', 12.0)
                tick['fps'] = (stream_session or {}).get('fps') or 30

            ticks.append(tick)

        return ticks


def get_scheduler_service(data_dir=None, cfg=None):
    return SchedulerService(data_dir, cfg)
