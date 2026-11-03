/**
 * Deterministic GPU scheduling preview engine.
 *
 * Hard constraints are applied before scoring.  Missing price/latency values
 * are never treated as zero; when a budget or latency limit is set and the
 * value is unknown, the candidate is rejected.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ComputeScheduling = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  var STRATEGIES = [
    'lowest_cost', 'lowest_latency', 'shortest_queue',
    'highest_performance', 'local_first'
  ];
  var STATES = ['pending', 'recommended', 'queued', 'running', 'completed'];
  var STATE_LABELS = {
    pending: '待分配',
    recommended: '已推荐',
    queued: '排队中',
    running: '运行中',
    completed: '已完成'
  };

  function toNumber(value, fallback) {
    if (value === null || value === undefined || value === '') return fallback;
    var number = Number(value);
    return isFinite(number) ? number : fallback;
  }

  function normalizeRequest(form) {
    form = form || {};
    return {
      taskName: String(form.taskName || '未命名任务').trim() || '未命名任务',
      taskType: form.taskType || 'render',
      priority: form.priority || 'medium',
      gpuCount: Math.max(1, toNumber(form.gpuCount, 1)),
      minVram: Math.max(0, toNumber(form.minVram, 0)),
      maxCost: Math.max(0, toNumber(form.maxCost, 0)),
      maxLatency: Math.max(0, toNumber(form.maxLatency, 0)),
      strategy: STRATEGIES.indexOf(form.strategy) === -1
        ? 'lowest_cost' : form.strategy
    };
  }

  function nodeVramPerGpu(node) {
    var perGpu = toNumber(node.vramPerGpuGb, null);
    if (perGpu !== null) return perGpu;
    var total = toNumber(node.totalVramGb, null);
    var count = Math.max(1, toNumber(node.gpuCount, 1));
    return total === null ? null : total / count;
  }

  function evaluateCandidates(nodes, request) {
    request = normalizeRequest(request);
    var candidates = [];
    var rejected = [];
    (nodes || []).forEach(function(node) {
      var reasons = [];
      if (node.status !== 'online' || node.schedulable === false) {
        reasons.push('节点不在线或不可调度');
      }
      var gpuCount = toNumber(node.gpuCount, 0);
      if (gpuCount < request.gpuCount) {
        reasons.push('GPU 数量不足');
      }
      var vramPerGpu = nodeVramPerGpu(node);
      if (vramPerGpu === null || vramPerGpu < request.minVram) {
        reasons.push('单卡显存不足');
      }
      var unitPrice = toNumber(node.unitPricePerHour, null);
      var estimatedCost = unitPrice === null ? null : unitPrice * request.gpuCount;
      if (request.maxCost > 0) {
        if (estimatedCost === null) {
          reasons.push('缺少参考单价，无法校验预算');
        } else if (estimatedCost > request.maxCost) {
          reasons.push('超过预算上限');
        }
      }
      var latency = toNumber(node.latencyMs, null);
      if (request.maxLatency > 0) {
        if (latency === null) {
          reasons.push('缺少网络时延，无法校验时延上限');
        } else if (latency > request.maxLatency) {
          reasons.push('超过最大时延');
        }
      }
      if (reasons.length) {
        rejected.push({ nodeId: node.id, nodeName: node.name, reasons: reasons });
        return;
      }
      candidates.push({
        node: node,
        estimatedCostPerHour: estimatedCost,
        vramPerGpuGb: vramPerGpu
      });
    });
    return {
      request: request,
      candidates: candidates,
      rejected: rejected,
      rejectedCount: rejected.length,
      totalCandidates: (nodes || []).length
    };
  }

  function strategyWeights(strategy) {
    var weights = {
      lowest_cost: { util: 0.15, queue: 0.15, cost: 0.4, latency: 0.1, vram: 0.1, local: 0.1 },
      lowest_latency: { util: 0.15, queue: 0.15, cost: 0.1, latency: 0.4, vram: 0.1, local: 0.1 },
      shortest_queue: { util: 0.25, queue: 0.35, cost: 0.1, latency: 0.15, vram: 0.1, local: 0.05 },
      highest_performance: { util: 0.3, queue: 0.15, cost: 0.1, latency: 0.15, vram: 0.25, local: 0.05 },
      local_first: { util: 0.2, queue: 0.15, cost: 0.15, latency: 0.1, vram: 0.1, local: 0.3 }
    };
    return weights[strategy] || weights.lowest_cost;
  }

  function isLocalPool(node) {
    var pool = String(node.pool || '').toLowerCase();
    return pool.indexOf('local') === 0 || pool.indexOf('private') === 0;
  }

  function scoreCandidates(candidates, request) {
    request = normalizeRequest(request);
    var weights = strategyWeights(request.strategy);
    var scored = (candidates || []).map(function(candidate) {
      var node = candidate.node;
      var util = Math.max(0, Math.min(100, toNumber(node.utilizationPct, 0)));
      var queued = Math.max(0, toNumber(node.queuedTasks, 0));
      var latency = toNumber(node.latencyMs, null);
      var price = candidate.estimatedCostPerHour;
      var utilScore = (100 - util) / 100;
      var queueScore = 1 / (1 + queued);
      var latencyScore = latency === null ? 0.35 : 1 / (1 + (latency / 10));
      var costScore = price === null ? 0.35 : 1 / (1 + (price / 12));
      var vram = candidate.vramPerGpuGb || 0;
      var vramScore = request.minVram > 0
        ? Math.max(0, Math.min(1, 1 - (request.minVram / Math.max(vram, 0.01))))
        : 1;
      var localScore = isLocalPool(node) ? 1 : 0;
      var score =
        utilScore * weights.util +
        queueScore * weights.queue +
        costScore * weights.cost +
        latencyScore * weights.latency +
        vramScore * weights.vram +
        localScore * weights.local;
      var waitMinutes = queued * 8 + (util >= 70 ? 10 : (util >= 40 ? 4 : 1));
      var baseMinutes = request.taskType === 'training'
        ? 120
        : (request.taskType === 'inference' ? 5 : 35);
      var execMinutes = baseMinutes + Math.round(util / 10) * 2;
      if (request.priority === 'high') execMinutes = Math.round(execMinutes * 0.85);
      return {
        nodeId: node.id,
        nodeName: node.name,
        pool: node.pool,
        gpuModel: node.gpuModel,
        gpuCount: node.gpuCount,
        vramPerGpuGb: candidate.vramPerGpuGb,
        utilizationPct: util,
        queuedTasks: queued,
        latencyMs: latency,
        estimatedCostPerHour: price,
        estimatedWaitMinutes: waitMinutes,
        estimatedExecMinutes: execMinutes,
        score: Number(score.toFixed(4)),
        reason: buildReason(node, request, candidate, score)
      };
    });
    scored.sort(function(a, b) {
      if (b.score !== a.score) return b.score - a.score;
      var costA = a.estimatedCostPerHour === null ? Infinity : a.estimatedCostPerHour;
      var costB = b.estimatedCostPerHour === null ? Infinity : b.estimatedCostPerHour;
      if (costA !== costB) return costA - costB;
      var latencyA = a.latencyMs === null ? Infinity : a.latencyMs;
      var latencyB = b.latencyMs === null ? Infinity : b.latencyMs;
      if (latencyA !== latencyB) return latencyA - latencyB;
      return a.nodeName.localeCompare(b.nodeName);
    });
    return scored;
  }

  function buildReason(node, request, candidate, score) {
    var parts = [
      '满足在线、GPU 数量、单卡显存' +
        (request.maxCost > 0 ? '、预算' : '') +
        (request.maxLatency > 0 ? '、时延' : '') +
        '约束'
    ];
    parts.push('利用率 ' + toNumber(node.utilizationPct, 0) + '%');
    parts.push('排队 ' + toNumber(node.queuedTasks, 0) + ' 个');
    if (candidate.estimatedCostPerHour !== null) {
      parts.push('参考费用 ¥' + candidate.estimatedCostPerHour.toFixed(2) + '/小时');
    }
    if (node.latencyMs !== null && node.latencyMs !== undefined) {
      parts.push('时延 ' + node.latencyMs + 'ms');
    }
    var strategyLabels = {
      lowest_cost: '最低费用',
      lowest_latency: '最低时延',
      shortest_queue: '最短排队',
      highest_performance: '最高性能',
      local_first: '本地优先'
    };
    parts.push('策略：' + (strategyLabels[request.strategy] || request.strategy));
    parts.push('评分 ' + Number(score).toFixed(3));
    return parts.join('；');
  }

  function evaluate(nodes, request) {
    var filtered = evaluateCandidates(nodes, request);
    var ranked = scoreCandidates(filtered.candidates, filtered.request);
    return {
      request: filtered.request,
      ranked: ranked,
      recommendations: ranked.slice(0, 3),
      rejected: filtered.rejected,
      rejectedCount: filtered.rejectedCount,
      totalCandidates: filtered.totalCandidates
    };
  }

  function canTransition(from, to) {
    var fromIndex = STATES.indexOf(from);
    var toIndex = STATES.indexOf(to);
    return fromIndex !== -1 && toIndex !== -1 && toIndex === fromIndex + 1;
  }

  function transition(current, to) {
    return canTransition(current, to) ? to : current;
  }

  function nextState(current) {
    var index = STATES.indexOf(current);
    return index >= 0 && index < STATES.length - 1 ? STATES[index + 1] : current;
  }

  return {
    STRATEGIES: STRATEGIES,
    STATES: STATES,
    STATE_LABELS: STATE_LABELS,
    normalizeRequest: normalizeRequest,
    evaluateCandidates: evaluateCandidates,
    scoreCandidates: scoreCandidates,
    evaluate: evaluate,
    canTransition: canTransition,
    transition: transition,
    nextState: nextState
  };
});
