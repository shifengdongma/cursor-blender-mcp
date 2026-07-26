# -*- coding: utf-8 -*-
"""Tests for the scheduler scoring algorithm (no database required)."""
from __future__ import absolute_import

import time

import pytest

from backend.scheduler_scorer import (
    NodeScorer,
    ScheduleRequest,
    DEFAULT_WEIGHTS,
)


def _make_node(node_id="node-1", overrides=None):
    """Build a canonical compute-node dict matching ComputeNode.to_dict()."""
    base = {
        "id": node_id,
        "name": "GPU Node {0}".format(node_id),
        "status": "online",
        "schedulable": True,
        "region": "us-east-1",
        "gpu_type": "NVIDIA-A100",
        "gpu_count": 4,
        "gpu_memory_mb": 40960,
        "cpu_cores": 32,
        "memory_mb": 262144,
        "queue_depth": 0,
        "last_heartbeat_at": int(time.time()),
    }
    if overrides:
        base.update(overrides)
    return base


def _make_metrics(gpu_percent=0, cpu_percent=0, memory_percent=10, latency_ms=5, node_id="node-1", **kwargs):
    """Build a sample NodeMetricSample dict."""
    base = {
        "node_id": node_id,
        "gpu_percent": gpu_percent or 0,
        "cpu_percent": cpu_percent or 0,
        "memory_percent": memory_percent or 10,
        "latency_ms": latency_ms or 5,
    }
    base.update(kwargs)
    return base


class TestNodeScorer(object):

    def make_scorer(self, weights=None, gpu_price_map=None):
        return NodeScorer(weights=weights, gpu_price_map=gpu_price_map)

    # ── 1. Idle node gets highest score ──

    def test_score_idle_node(self):
        """An idle node (0% GPU/CPU) should receive a near-perfect idle_resources score."""
        scorer = self.make_scorer()
        node = _make_node()
        metrics = _make_metrics(gpu_percent=0, cpu_percent=0)
        request = ScheduleRequest()

        result = scorer.score_node(node, request, metrics)

        breakdown = result["score_breakdown"]
        # idle_resources = max(0, (1.0 - 0.0) * 100) = 100
        assert breakdown["idle_resources"] == 100.0
        assert result["utilization_estimate"] == 0.0
        assert result["filtered_out"] is False
        assert result["score"] > 0

    # ── 2. Busy node gets overload penalty ──

    def test_score_busy_node_gets_penalty(self):
        """A node at 95% utilization should receive an overload penalty of -50."""
        scorer = self.make_scorer()
        node = _make_node()
        metrics = _make_metrics(gpu_percent=95, cpu_percent=80)
        request = ScheduleRequest()

        result = scorer.score_node(node, request, metrics)

        assert result["utilization_estimate"] == 95.0
        assert "heavily loaded" in " ".join(result["warnings"]).lower()
        assert result["score_breakdown"]["idle_resources"] == 5.0
        # Final score should be heavily penalized (overload -50 + low idle resources)
        assert result["score"] < 20.0

    # ── 3. Offline nodes filtered out ──

    def test_filter_offline_nodes(self):
        """Offline nodes (status != 'online' OR schedulable != True) must be filtered out."""
        scorer = self.make_scorer()
        request = ScheduleRequest()

        online_node = _make_node("online-1")
        offline_node = _make_node("offline-1", {"status": "offline"})
        unschedulable_node = _make_node("unsched-1", {"schedulable": False})
        draining_node = _make_node("draining-1", {"status": "draining"})

        nodes = [online_node, offline_node, unschedulable_node, draining_node]
        passed, filtered = scorer.filter_candidates(nodes, request)

        assert len(passed) == 1
        assert passed[0]["id"] == "online-1"
        assert len(filtered) == 3
        # Verify the filter reasons are descriptive
        filter_reasons = " ".join(r for _, r in filtered)
        assert "offline" in filter_reasons.lower()
        assert "schedulable" in filter_reasons.lower()

    # ── 4. Region match scoring ──

    def test_region_match_scoring(self):
        """Region preferences should affect the region_match dimension."""
        scorer = self.make_scorer()

        # Exact region match
        node_exact = _make_node("exact", {"region": "ap-southeast-1"})
        req_exact = ScheduleRequest(region_preference="ap-southeast-1")
        r1 = scorer.score_node(node_exact, req_exact)
        assert r1["score_breakdown"]["region_match"] == 100.0

        # Partial region match (same zone prefix)
        node_partial = _make_node("partial", {"region": "ap-southeast-2"})
        r2 = scorer.score_node(node_partial, req_exact)
        assert r2["score_breakdown"]["region_match"] == 50.0

        # No match
        node_no_match = _make_node("no-match", {"region": "us-west-2"})
        r3 = scorer.score_node(node_no_match, req_exact)
        assert r3["score_breakdown"]["region_match"] == 0.0

        # No region preference: all nodes tie at 100
        req_none = ScheduleRequest()
        r4 = scorer.score_node(node_exact, req_none)
        r5 = scorer.score_node(node_no_match, req_none)
        assert r4["score_breakdown"]["region_match"] == 100.0
        assert r5["score_breakdown"]["region_match"] == 100.0

    # ── 5. GPU count filter ──

    def test_gpu_count_filter(self):
        """Nodes with fewer GPUs than required should be filtered out."""
        scorer = self.make_scorer()

        # 4-GPU node for a request needing 2 GPUs
        request = ScheduleRequest(required_gpu_count=2)

        node_big = _make_node("big", {"gpu_count": 4})
        node_small = _make_node("small", {"gpu_count": 1})
        node_exact = _make_node("exact", {"gpu_count": 2})
        node_no_gpu = _make_node("no-gpu", {"gpu_count": 0})

        nodes = [node_big, node_small, node_exact, node_no_gpu]
        passed, filtered = scorer.filter_candidates(nodes, request)

        passed_ids = [n["id"] for n in passed]
        assert sorted(passed_ids) == ["big", "exact"]
        assert len(filtered) == 2
        assert "GPU count 1 < required 2" in filtered[0][1] or "GPU count 0 < required 2" in filtered[0][1]

    # ── 6. Ranking order ──

    def test_ranking_order(self):
        """Multiple nodes must be ranked in descending score order."""
        scorer = self.make_scorer()
        request = ScheduleRequest(region_preference="us-east-1")

        # Best: idle, no queue, correct region
        best = _make_node("best", {"region": "us-east-1", "queue_depth": 0})
        # Medium: correct region but queued
        medium = _make_node("medium", {"region": "us-east-1", "queue_depth": 5})
        # Worst: wrong region and queued
        worst = _make_node("worst", {"region": "eu-west-1", "queue_depth": 10})

        result = scorer.rank_nodes([worst, best, medium], request)

        rankings = result["rankings"]
        assert len(rankings) == 3
        # Must be sorted descending
        assert rankings[0]["node"]["id"] == "best"
        assert rankings[1]["node"]["id"] == "medium"
        assert rankings[2]["node"]["id"] == "worst"
        # Verify scores are strictly descending
        assert rankings[0]["score"] >= rankings[1]["score"] >= rankings[2]["score"]

    # ── 7. ScheduleRequest.from_dict payload parsing ──

    def test_schedule_request_from_dict(self):
        """ScheduleRequest.from_dict must correctly parse a payload dict."""
        payload = {
            "task_type": "video-render",
            "engine_target": "ue5_cloud",
            "required_gpu_count": 2,
            "minimum_gpu_memory_mb": 8192,
            "required_cpu_cores": 8,
            "required_memory_mb": 16384,
            "region_preference": "eu-central-1",
            "maximum_latency_ms": 50,
            "maximum_estimated_cost": 500,
            "priority": "high",
            "project_id": "proj-123",
            "tenant_id": "tenant-abc",
        }
        req = ScheduleRequest.from_dict(payload)

        assert req.task_type == "video-render"
        assert req.engine_target == "ue5_cloud"
        assert req.required_gpu_count == 2
        assert req.minimum_gpu_memory_mb == 8192
        assert req.required_cpu_cores == 8
        assert req.required_memory_mb == 16384
        assert req.region_preference == "eu-central-1"
        assert req.maximum_latency_ms == 50
        assert req.maximum_estimated_cost == 500
        assert req.priority == "high"
        assert req.project_id == "proj-123"
        assert req.tenant_id == "tenant-abc"

    def test_schedule_request_from_dict_defaults(self):
        """Empty dict should yield default values."""
        req = ScheduleRequest.from_dict({})
        assert req.task_type == "render"
        assert req.engine_target == "blender_anchor"
        assert req.required_gpu_count == 1
        assert req.minimum_gpu_memory_mb == 0
        assert req.required_cpu_cores == 0
        assert req.required_memory_mb == 0
        assert req.region_preference is None
        assert req.maximum_latency_ms is None
        assert req.maximum_estimated_cost is None
        assert req.priority == "normal"
        assert req.project_id is None
        assert req.tenant_id is None

    # ── 8. Scoring breakdown contains all dimensions ──

    def test_scoring_breakdown_has_all_dimensions(self):
        """The score_breakdown dict must include every dimension defined in DEFAULT_WEIGHTS."""
        scorer = self.make_scorer()
        node = _make_node()
        request = ScheduleRequest()

        result = scorer.score_node(node, request)

        breakdown = result["score_breakdown"]
        expected_keys = set(DEFAULT_WEIGHTS.keys())
        assert set(breakdown.keys()) == expected_keys, (
            "Missing dimensions: {0}".format(expected_keys - set(breakdown.keys()))
        )
        # Each dimension must be a non-negative number
        for key, value in breakdown.items():
            assert isinstance(value, (int, float)), "{0} should be numeric".format(key)
            assert value >= 0, "{0} should be non-negative".format(key)

    # ── 9. Heartbeat age penalty ──

    def test_heartbeat_age_penalty(self):
        """A stale heartbeat (older than 0.5h) should produce a penalty and a warning."""
        scorer = self.make_scorer()
        stale_ts = int(time.time()) - 7200  # 2 hours ago
        node = _make_node("stale-node", {"last_heartbeat_at": stale_ts})
        request = ScheduleRequest()

        result = scorer.score_node(node, request)

        warnings = " ".join(result["warnings"])
        assert "heartbeat" in warnings.lower()
        assert "2.0h" in warnings or "stale" in warnings.lower()
        # Penalty should be negative
        # hours_since = 2.0, penalty = min(100, -20 * 2.0) = -40
        # The final score must reflect this penalty (raw weighted sum + penalty)
        # With default weights and all other dimensions = 100, raw = 100.0, final = 100 - 40 = 60
        # But region_match with no preference = 100, idle = utilization None so default... let's verify:
        # when node_metrics is None, utilization defaults to 0.0 (from the code: utilization = max(gpu_util, cpu_util) / 100.0 where gpu_util/cpu_util default to 0)
        # Wait: "if node_metrics: gpu_util = node_metrics.get('gpu_percent') or 0"
        # Since node_metrics is None, the if block is skipped, and utilization stays 0.0
        # So idle = 100, region = 100 (no preference), queue = 100, latency = 100 (no metrics), cost = some score, gpu_match = 100, priority_bonus = 50
        # Weighted: 0.30*100 + 0.20*100 + 0.15*100 + 0.10*100 + 0.10*cost + 0.10*100 + 0.05*50
        # Normalized weights:
        # total = 1.0, so no normalization needed
        # Actually wait, they sum to 1.0 already: .30+.20+.15+.10+.10+.10+.05 = 1.0, so no normalization
        # Weighted: 30 + 20 + 15 + 10 + cost_val + 10 + 2.5 = 87.5 + cost_val
        # cost_val = 0.10 * max(0, 100 - (unit_price / max(budget,1)) * 100)
        # unit_price = gpu_price_map.get(node_gpu, 100) = 100 (no map)
        # budget = maximum_estimated_cost or unit_price * 2 = 200
        # cost_score = max(0, 100 - (100/200)*100) = max(0, 100 - 50) = 50
        # cost_val = 0.10 * 50 = 5
        # raw = 87.5 + 5 = 92.5
        # final = 92.5 + (-40 penalty) = 52.5
        # Hmm, let me just check it's less than without the penalty rather than exact value
        assert result["score"] < 60, "Stale heartbeat should reduce score significantly"

    def test_fresh_heartbeat_no_penalty(self):
        """A recent heartbeat should produce no heartbeat warning."""
        scorer = self.make_scorer()
        fresh_ts = int(time.time()) - 60  # 1 minute ago
        node = _make_node("fresh-node", {"last_heartbeat_at": fresh_ts})
        request = ScheduleRequest()

        result = scorer.score_node(node, request)

        warnings_text = " ".join(result["warnings"]).lower()
        assert "heartbeat" not in warnings_text

    # ── 10. Empty candidates returns gracefully ──

    def test_empty_candidates_returns_graceful(self):
        """An empty node list should produce a valid empty result, not crash."""
        scorer = self.make_scorer()
        request = ScheduleRequest()

        passed, filtered = scorer.filter_candidates([], request)
        assert passed == []
        assert filtered == []

        result = scorer.rank_nodes([], request)
        assert result["rankings"] == []
        assert result["filtered"] == []
        assert result["total_candidates"] == 0
        assert result["passed"] == 0

    # ── Additional edge cases ──

    def test_gpu_memory_filter(self):
        """Nodes with insufficient GPU memory should be filtered out."""
        scorer = self.make_scorer()
        request = ScheduleRequest(minimum_gpu_memory_mb=16384)

        node_enough = _make_node("enough", {"gpu_memory_mb": 40960})
        node_insufficient = _make_node("insufficient", {"gpu_memory_mb": 8192})

        passed, filtered = scorer.filter_candidates(
            [node_enough, node_insufficient], request
        )
        assert len(passed) == 1
        assert passed[0]["id"] == "enough"
        assert len(filtered) == 1
        assert "GPU memory" in filtered[0][1]

    def test_cpu_and_memory_filters(self):
        """Nodes with insufficient CPU cores or RAM should be filtered out."""
        scorer = self.make_scorer()
        request = ScheduleRequest(required_cpu_cores=16, required_memory_mb=65536)

        node_ok = _make_node("ok", {"cpu_cores": 32, "memory_mb": 262144})
        node_low_cpu = _make_node("low-cpu", {"cpu_cores": 4, "memory_mb": 262144})
        node_low_ram = _make_node("low-ram", {"cpu_cores": 32, "memory_mb": 8192})

        passed, filtered = scorer.filter_candidates(
            [node_ok, node_low_cpu, node_low_ram], request
        )
        assert len(passed) == 1
        assert passed[0]["id"] == "ok"
        assert len(filtered) == 2
        filter_text = " ".join(r for _, r in filtered)
        assert "CPU" in filter_text
        assert "Memory" in filter_text

    def test_priority_bonus_scoring(self):
        """High-priority requests should get a higher priority_bonus score."""
        scorer = self.make_scorer()

        node = _make_node()
        req_high = ScheduleRequest(priority="high")
        req_normal = ScheduleRequest(priority="normal")

        result_high = scorer.score_node(node, req_high)
        result_normal = scorer.score_node(node, req_normal)

        assert result_high["score_breakdown"]["priority_bonus"] == 100.0
        assert result_normal["score_breakdown"]["priority_bonus"] == 50.0
        assert result_high["score"] > result_normal["score"]

    def test_cost_scoring_with_price_map(self):
        """GPU price map should influence the cost score dimension."""
        price_map = {"NVIDIA-A100": 50, "NVIDIA-H100": 200}
        scorer = self.make_scorer(gpu_price_map=price_map)

        cheap_node = _make_node("cheap", {"gpu_type": "NVIDIA-A100"})
        expensive_node = _make_node("expensive", {"gpu_type": "NVIDIA-H100"})
        request = ScheduleRequest(maximum_estimated_cost=100)

        result_cheap = scorer.score_node(cheap_node, request)
        result_expensive = scorer.score_node(expensive_node, request)

        assert result_cheap["unit_price_estimate"] == 50
        assert result_expensive["unit_price_estimate"] == 200
        assert result_cheap["score_breakdown"]["cost"] > result_expensive["score_breakdown"]["cost"]

    def test_latency_scoring_with_metrics(self):
        """Higher latency should produce a lower latency score."""
        scorer = self.make_scorer()
        node = _make_node()
        request = ScheduleRequest()

        low_latency = _make_metrics(latency_ms=5)
        high_latency = _make_metrics(latency_ms=500)

        result_low = scorer.score_node(node, request, low_latency)
        result_high = scorer.score_node(node, request, high_latency)

        assert result_low["score_breakdown"]["latency"] == 99.0  # max(0, 100 - 5/5) = 99
        # Actually: latency_score = max(0, 100 - latency / 5)
        # low: max(0, 100 - 5/5) = max(0, 99) = 99  ... wait, 5/5 = 1, 100 - 1 = 99
        # Hmm: 100 - latency/5 where latency=5 => 100 - 1 = 99. Yes.
        # high: max(0, 100 - 500/5) = max(0, 100 - 100) = 0
        assert result_low["score_breakdown"]["latency"] == 99.0
        assert result_high["score_breakdown"]["latency"] == 0.0

    def test_queue_depth_scoring(self):
        """Longer queue depths should reduce the queue_depth score."""
        scorer = self.make_scorer()

        node_empty = _make_node("empty", {"queue_depth": 0})
        node_busy = _make_node("busy", {"queue_depth": 8})

        request = ScheduleRequest()

        result_empty = scorer.score_node(node_empty, request)
        result_busy = scorer.score_node(node_busy, request)

        # queue_score = max(0, 100 - depth * 10)
        assert result_empty["score_breakdown"]["queue_depth"] == 100.0
        # max(0, 100 - 8*10) = max(0, 20) = 20
        assert result_busy["score_breakdown"]["queue_depth"] == 20.0

    def test_all_filtered_rankings_still_valid(self):
        """When all nodes are filtered out, rank_nodes should return empty rankings."""
        scorer = self.make_scorer()
        request = ScheduleRequest(required_gpu_count=100)

        nodes = [
            _make_node("n1", {"gpu_count": 1}),
            _make_node("n2", {"gpu_count": 4}),
        ]

        result = scorer.rank_nodes(nodes, request)
        assert result["rankings"] == []
        assert len(result["filtered"]) == 2
        assert result["total_candidates"] == 2
        assert result["passed"] == 0
