# -*- coding: utf-8 -*-
"""Real scheduling scoring algorithm for AIGV Studio."""
from __future__ import absolute_import

import logging
import time

logger = logging.getLogger(__name__)


class ScheduleRequest(object):
    """Structured scheduling request with resource requirements."""

    def __init__(self, task_type='render', engine_target='blender_anchor',
                 required_gpu_count=1, minimum_gpu_memory_mb=0,
                 required_cpu_cores=0, required_memory_mb=0,
                 region_preference=None, maximum_latency_ms=None,
                 maximum_estimated_cost=None, priority='normal',
                 project_id=None, tenant_id=None):
        self.task_type = task_type
        self.engine_target = engine_target
        self.required_gpu_count = required_gpu_count
        self.minimum_gpu_memory_mb = minimum_gpu_memory_mb
        self.required_cpu_cores = required_cpu_cores
        self.required_memory_mb = required_memory_mb
        self.region_preference = region_preference
        self.maximum_latency_ms = maximum_latency_ms
        self.maximum_estimated_cost = maximum_estimated_cost
        self.priority = priority
        self.project_id = project_id
        self.tenant_id = tenant_id

    @classmethod
    def from_dict(cls, d):
        return cls(
            task_type=d.get('task_type', 'render'),
            engine_target=d.get('engine_target', 'blender_anchor'),
            required_gpu_count=d.get('required_gpu_count', 1),
            minimum_gpu_memory_mb=d.get('minimum_gpu_memory_mb', 0),
            required_cpu_cores=d.get('required_cpu_cores', 0),
            required_memory_mb=d.get('required_memory_mb', 0),
            region_preference=d.get('region_preference'),
            maximum_latency_ms=d.get('maximum_latency_ms'),
            maximum_estimated_cost=d.get('maximum_estimated_cost'),
            priority=d.get('priority', 'normal'),
            project_id=d.get('project_id'),
            tenant_id=d.get('tenant_id'),
        )


# Default scoring weights — configurable via scheduler_policies table
DEFAULT_WEIGHTS = {
    'idle_resources': 0.30,
    'region_match': 0.20,
    'queue_depth': 0.15,
    'latency': 0.10,
    'cost': 0.10,
    'gpu_match': 0.10,
    'priority_bonus': 0.05,
}


class NodeScorer(object):
    """Scores compute nodes based on configurable weights."""

    def __init__(self, weights=None, gpu_price_map=None):
        self.weights = weights or DEFAULT_WEIGHTS
        self.gpu_price_map = gpu_price_map or {}

        # Normalize weights to sum to 1.0
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score_node(self, node, request, node_metrics=None):
        """Score a single compute node against a schedule request.

        Args:
            node: dict from ComputeNode.to_dict()
            request: ScheduleRequest instance
            node_metrics: Optional latest NodeMetricSample dict

        Returns:
            dict with 'score', 'score_breakdown', 'warnings', 'filtered_out', 'filter_reason'
        """
        breakdown = {}
        warnings = []

        # ── 1. Idle Resources Score ──
        utilization = 0.0
        if node_metrics:
            gpu_util = node_metrics.get('gpu_percent') or 0
            cpu_util = node_metrics.get('cpu_percent') or 0
            utilization = max(gpu_util, cpu_util) / 100.0

        idle_score = max(0, (1.0 - utilization) * 100)
        breakdown['idle_resources'] = round(idle_score, 1)

        # Overload penalty
        if utilization > 0.9:
            warnings.append('Node heavily loaded (utilization > 90%)')
        overload_penalty = -50 if utilization > 0.9 else 0

        # ── 2. Region Match Score ──
        region_score = 0
        req_region = request.region_preference
        if req_region:
            node_region = node.get('region', '')
            if req_region == node_region:
                region_score = 100
            elif req_region.split('-')[0] == node_region.split('-')[0] if node_region else False:
                region_score = 50
        else:
            region_score = 100  # No preference → all nodes equal
        breakdown['region_match'] = round(region_score, 1)

        # ── 3. Queue Depth Score ──
        queue_depth = node.get('queue_depth', 0)
        queue_score = max(0, 100 - queue_depth * 10)
        breakdown['queue_depth'] = round(queue_score, 1)

        # ── 4. Latency Score ──
        latency = node_metrics.get('latency_ms') if node_metrics else None
        latency_score = 100
        if latency is not None:
            latency_score = max(0, 100 - latency / 5)
        breakdown['latency'] = round(latency_score, 1)

        # ── 5. Cost Score ──
        node_gpu = node.get('gpu_type', '')
        unit_price = self.gpu_price_map.get(node_gpu, 100)
        budget = request.maximum_estimated_cost or unit_price * 2
        cost_score = max(0, 100 - (unit_price / max(budget, 1)) * 100)
        breakdown['cost'] = round(cost_score, 1)

        # ── 6. GPU Match Score ──
        gpu_match_score = 0
        node_gpu_count = node.get('gpu_count', 0)
        node_gpu_memory = node.get('gpu_memory_mb', 0)
        if node_gpu_count >= request.required_gpu_count:
            gpu_match_score = 100
            if request.minimum_gpu_memory_mb > 0 and node_gpu_memory < request.minimum_gpu_memory_mb:
                gpu_match_score = 0
        breakdown['gpu_match'] = round(gpu_match_score, 1)

        # ── 7. Priority Bonus ──
        priority_score = 0
        if request.priority == 'high':
            priority_score = 100
        elif request.priority == 'normal':
            priority_score = 50
        breakdown['priority_bonus'] = round(priority_score, 1)

        # ── 8. Heartbeat Age Penalty ──
        heartbeat_penalty = 0
        last_hb = node.get('last_heartbeat_at')
        if last_hb:
            hours_since = (int(time.time()) - int(last_hb)) / 3600.0
            if hours_since > 0.5:
                heartbeat_penalty = min(100, int(-20 * hours_since))
                warnings.append('Last heartbeat {0:.1f}h ago'.format(hours_since))

        # ── Total Score ──
        raw_score = (
            self.weights.get('idle_resources', 0) * idle_score +
            self.weights.get('region_match', 0) * region_score +
            self.weights.get('queue_depth', 0) * queue_score +
            self.weights.get('latency', 0) * latency_score +
            self.weights.get('cost', 0) * cost_score +
            self.weights.get('gpu_match', 0) * gpu_match_score +
            self.weights.get('priority_bonus', 0) * priority_score
        ) + overload_penalty + heartbeat_penalty

        return {
            'score': round(raw_score, 2),
            'score_breakdown': breakdown,
            'warnings': warnings,
            'filtered_out': False,
            'filter_reason': None,
            'utilization_estimate': round(utilization * 100, 1),
            'unit_price_estimate': unit_price,
        }

    def filter_candidates(self, nodes, request, node_metrics_map=None):
        """Filter nodes that meet minimum requirements.

        Args:
            nodes: list of dict from ComputeNode.to_dict()
            request: ScheduleRequest
            node_metrics_map: Optional dict mapping node_id → latest metrics

        Returns:
            (passed_nodes, filtered_out) — two lists of (node, filter_reason)
        """
        passed = []
        filtered = []

        for node in nodes:
            reasons = []

            if node.get('schedulable') != True:
                reasons.append('Not schedulable')

            if node.get('status') != 'online':
                reasons.append('Status is {0}'.format(node.get('status')))

            if request.required_gpu_count > 0:
                if node.get('gpu_count', 0) < request.required_gpu_count:
                    reasons.append('GPU count {0} < required {1}'.format(
                        node.get('gpu_count'), request.required_gpu_count))

            if request.minimum_gpu_memory_mb > 0:
                if node.get('gpu_memory_mb', 0) < request.minimum_gpu_memory_mb:
                    reasons.append('GPU memory {0}MB < required {1}MB'.format(
                        node.get('gpu_memory_mb'), request.minimum_gpu_memory_mb))

            if request.required_cpu_cores > 0:
                if node.get('cpu_cores', 0) < request.required_cpu_cores:
                    reasons.append('CPU cores {0} < required {1}'.format(
                        node.get('cpu_cores'), request.required_cpu_cores))

            if request.required_memory_mb > 0:
                if node.get('memory_mb', 0) < request.required_memory_mb:
                    reasons.append('Memory {0}MB < required {1}MB'.format(
                        node.get('memory_mb'), request.required_memory_mb))

            if reasons:
                filtered.append((node, '; '.join(reasons)))
            else:
                passed.append(node)

        return passed, filtered

    def rank_nodes(self, nodes, request, node_metrics_map=None):
        """Filter, score, and rank nodes.

        Returns:
            dict with 'rankings', 'filtered', 'total_candidates'
        """
        passed, filtered = self.filter_candidates(nodes, request, node_metrics_map)
        metrics_map = node_metrics_map or {}

        rankings = []
        for node in passed:
            metrics = metrics_map.get(node.get('id'))
            result = self.score_node(node, request, metrics)
            result['node'] = node
            rankings.append(result)

        # Sort by score descending
        rankings.sort(key=lambda r: r['score'], reverse=True)

        return {
            'rankings': rankings,
            'filtered': [{'node': n, 'reasons': r} for n, r in filtered],
            'total_candidates': len(nodes),
            'passed': len(passed),
        }
