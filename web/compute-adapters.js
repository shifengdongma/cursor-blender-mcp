/**
 * Null-safe adapters between real/demo API payloads and the compute scene
 * shape.  Missing values stay null and are rendered as "未采集" rather than
 * being treated as zero or replaced with showcase data.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ComputeAdapters = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  var ACTIVE_ALERT_STATUSES = ['open', 'acknowledged', 'processing', 'active'];

  function numberOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    var number = Number(value);
    return isFinite(number) ? number : null;
  }

  function statusOnline(status) {
    var value = String(status || '').toLowerCase();
    return value === 'online' || value === 'running' || value === 'active';
  }

  function adaptMonitoringNodes(rawNodes) {
    return (rawNodes || []).map(function(raw) {
      var gpuMemoryMb = numberOrNull(raw.gpu_memory_mb);
      var gpuCount = numberOrNull(raw.gpu_count);
      var perGpu = gpuMemoryMb === null ? null : gpuMemoryMb / 1024;
      var totalVram = perGpu === null || gpuCount === null
        ? null : perGpu * gpuCount;
      var utilization = numberOrNull(
        raw.latest_gpu_percent !== undefined
          ? raw.latest_gpu_percent
          : raw.gpu_percent
      );
      var memoryPercent = numberOrNull(
        raw.latest_gpu_memory_percent !== undefined
          ? raw.latest_gpu_memory_percent
          : raw.gpu_memory_percent
      );
      var usedVram = totalVram !== null && memoryPercent !== null
        ? Number(((totalVram * memoryPercent) / 100).toFixed(1))
        : null;
      return {
        id: raw.id || raw.node_id || raw.node_name,
        name: raw.node_name || raw.name || raw.host_name || raw.id || '未命名节点',
        pool: raw.provider_type || raw.cluster_name || 'cloud',
        gpuModel: raw.gpu_type || '—',
        gpuCount: gpuCount === null ? 0 : gpuCount,
        vramPerGpuGb: perGpu,
        totalVramGb: totalVram,
        usedVramGb: usedVram,
        utilizationPct: utilization,
        status: raw.status || 'unknown',
        schedulable: raw.schedulable !== false,
        currentTask: null,
        queuedTasks: numberOrNull(raw.running_tasks),
        latencyMs: numberOrNull(raw.latency_ms),
        unitPricePerHour: null,
        temperatureC: numberOrNull(
          raw.latest_gpu_temperature !== undefined
            ? raw.latest_gpu_temperature
            : raw.gpu_temperature
        ),
        heartbeat: raw.latest_sample_at || raw.heartbeat_age_s || null,
        source: 'live'
      };
    });
  }

  function adaptMonitoringLinks(rawLinks) {
    return (rawLinks || []).map(function(raw) {
      var latency = numberOrNull(raw.latency_ms);
      var success = raw.success !== false;
      var loss = numberOrNull(raw.packet_loss_pct);
      return {
        id: raw.id || raw.target || raw.name,
        name: raw.name || raw.target || '未命名链路',
        source: raw.source || '本地',
        target: raw.target || raw.name || '—',
        sourceName: raw.source || '本地',
        targetName: raw.target || raw.name || '—',
        latencyMs: latency,
        jitterMs: numberOrNull(raw.jitter_ms),
        packetLossPct: loss,
        bandwidthGbps: numberOrNull(raw.bandwidth_gbps),
        throughputGbps: numberOrNull(raw.throughput_gbps),
        status: success ? (latency !== null && latency > 100 ? 'degraded' : 'normal') : 'down',
        health: success ? 'healthy' : 'warning',
        source_type: 'live'
      };
    });
  }

  function adaptMonitoringSamples(rawSamples) {
    var samples = rawSamples || [];
    var labels = [];
    var bandwidth = [];
    var latency = [];
    var packetLoss = [];
    for (var i = 0; i < samples.length; i += 1) {
      var sample = samples[i] || {};
      labels.push(sample.sampled_at || String(i + 1));
      var rx = numberOrNull(sample.network_rx_bps);
      var tx = numberOrNull(sample.network_tx_bps);
      bandwidth.push(rx === null && tx === null
        ? null
        : Number((((rx || 0) + (tx || 0)) / 1000000000).toFixed(2)));
      latency.push(numberOrNull(sample.latency_ms));
      packetLoss.push(numberOrNull(sample.packet_loss_percent));
    }
    return {
      labels: labels,
      bandwidthGbps: bandwidth,
      latencyMs: latency,
      packetLossPct: packetLoss
    };
  }

  function adaptStorage(rawTargets, summary) {
    return (rawTargets || []).map(function(raw) {
      var total = numberOrNull(raw.total_bytes);
      var used = numberOrNull(raw.used_bytes);
      var pct = numberOrNull(raw.usage_pct);
      if (pct === null && total && used !== null) {
        pct = Number(((used / total) * 100).toFixed(1));
      }
      return {
        id: raw.id || raw.path || raw.label,
        name: raw.label || raw.name || raw.path || '未命名存储',
        capacityTB: total === null ? null : Number((total / 1000000000000).toFixed(2)),
        usedTB: used === null ? null : Number((used / 1000000000000).toFixed(2)),
        usagePct: pct,
        readMBps: summary ? numberOrNull(summary.read_mbps) : null,
        writeMBps: summary ? numberOrNull(summary.write_mbps) : null,
        connections: null,
        status: pct !== null && pct >= 90 ? 'warning' : 'normal',
        source: 'live'
      };
    });
  }

  function formatEpoch(value) {
    var number = numberOrNull(value);
    if (number === null) return '—';
    var date = new Date(number * 1000);
    if (isNaN(date.getTime())) return '—';
    function pad(part) { return part < 10 ? '0' + part : String(part); }
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' +
      pad(date.getDate()) + ' ' + pad(date.getHours()) + ':' +
      pad(date.getMinutes()) + ':' + pad(date.getSeconds());
  }

  function adaptAlerts(rawAlerts) {
    return (rawAlerts || []).map(function(raw) {
      var status = raw.status || 'open';
      return {
        id: raw.id,
        level: raw.severity || raw.level || 'warning',
        type: raw.target_type || raw.type || 'system',
        targetId: raw.target_id,
        targetName: raw.target_id || raw.target_name || '—',
        reason: [raw.metric_name, raw.current_value, raw.threshold_value]
          .filter(function(part) {
            return part !== null && part !== undefined && part !== '';
          }).join(' / ') || raw.content || '—',
        content: raw.content || raw.metric_name || '—',
        time: raw.created_at ? formatEpoch(raw.created_at) : (raw.time || '—'),
        status: status,
        autoRecovery: false,
        recoveryStatus: status === 'closed' || status === 'recovered'
          ? 'recovered' : 'warning',
        confirmed: status === 'acknowledged' || status === 'closed',
        source: 'live'
      };
    });
  }

  function isActiveAlert(status) {
    return ACTIVE_ALERT_STATUSES.indexOf(String(status || '').toLowerCase()) !== -1;
  }

  function derivePoolsFromNodes(nodes) {
    var group = {};
    (nodes || []).forEach(function(node) {
      var key = node.pool || 'default';
      if (!group[key]) {
        group[key] = {
          id: key,
          name: key,
          region: '—',
          kind: key,
          nodeCount: 0,
          onlineCount: 0,
          gpuCount: 0,
          availGpu: 0,
          utilWeighted: 0,
          priceTotal: 0,
          priceCount: 0,
          latencyTotal: 0,
          latencyCount: 0,
          status: 'unknown'
        };
      }
      var pool = group[key];
      pool.nodeCount += 1;
      if (statusOnline(node.status)) pool.onlineCount += 1;
      var gpuCount = numberOrNull(node.gpuCount) || 0;
      pool.gpuCount += gpuCount;
      if (statusOnline(node.status) && node.schedulable !== false) {
        pool.availGpu += gpuCount;
      }
      if (node.utilizationPct !== null && node.utilizationPct !== undefined) {
        pool.utilWeighted += node.utilizationPct * Math.max(1, gpuCount);
      }
      if (node.unitPricePerHour !== null && node.unitPricePerHour !== undefined) {
        pool.priceTotal += node.unitPricePerHour;
        pool.priceCount += 1;
      }
      if (node.latencyMs !== null && node.latencyMs !== undefined) {
        pool.latencyTotal += node.latencyMs;
        pool.latencyCount += 1;
      }
    });
    return Object.keys(group).map(function(key) {
      var pool = group[key];
      var totalWeight = pool.gpuCount || pool.nodeCount;
      pool.avgUtil = totalWeight
        ? Number((pool.utilWeighted / totalWeight).toFixed(1)) : null;
      pool.unitPrice = pool.priceCount
        ? Number((pool.priceTotal / pool.priceCount).toFixed(1)) : null;
      pool.latency = pool.latencyCount
        ? Number((pool.latencyTotal / pool.latencyCount).toFixed(1)) : null;
      pool.status = pool.onlineCount === pool.nodeCount && pool.nodeCount > 0
        ? 'healthy' : 'degraded';
      return pool;
    });
  }

  function adaptRenderSessions(rawJobs) {
    var statusMap = {
      queued: 'queued', running: 'rendering', succeeded: 'completed',
      failed: 'error', cancelled: 'paused'
    };
    return (rawJobs || []).map(function(job) {
      return {
        id: job.id,
        project: job.name || job.project_name || job.id,
        engine: job.engine || job.renderer || '—',
        nodeId: job.node_id || '',
        gpuNode: job.node_name || job.gpu_node || '未采集',
        status: statusMap[job.status] || job.status || 'queued',
        resolution: job.resolution || '—',
        fps: job.fps || null,
        bitrate: job.bitrate || '—',
        latencyMs: numberOrNull(job.latency_ms),
        runtime: job.runtime || '—',
        startedAt: job.started_at ? formatEpoch(job.started_at) : '—',
        eta: job.eta || '—',
        progressPct: numberOrNull(job.progress) || 0,
        source: 'live'
      };
    });
  }

  function sceneFromLive(input) {
    input = input || {};
    var nodes = adaptMonitoringNodes(
      input.nodes && input.nodes.length ? input.nodes : (input.hosts || [])
    );
    var links = adaptMonitoringLinks(input.links || []);
    var series = adaptMonitoringSamples(input.samples || []);
    var storage = adaptStorage(input.storage && input.storage.targets,
      input.storage && input.storage.summary);
    var alerts = adaptAlerts(input.alerts || []);
    var pools = derivePoolsFromNodes(nodes);
    var scene = {
      source: 'live',
      nodes: nodes,
      pools: pools,
      tasks: [],
      networkLinks: links,
      networkSeries: series,
      storageNodes: storage,
      alerts: alerts,
      sessions: adaptRenderSessions(input.renderJobs || []),
      gpuTrend: { labels: [], values: [], unit: '%' },
      taskTrend: { labels: [], values: [], unit: '个' },
      topologies: null
    };
    scene.overview = {
      totalNodes: nodes.length,
      onlineNodes: nodes.filter(function(node) { return statusOnline(node.status); }).length,
      schedulableNodes: nodes.filter(function(node) {
        return statusOnline(node.status) && node.schedulable !== false;
      }).length,
      queueDepth: null,
      queuedTasks: null,
      runningTasks: (input.renderJobs || []).filter(function(job) {
        return job.status === 'running';
      }).length,
      totalGpus: nodes.reduce(function(total, node) {
        return total + (node.gpuCount || 0);
      }, 0),
      avgGpuUtilPct: null,
      avgGpuMemUsedPct: null,
      avgNetworkLatencyMs: links.length
        ? Number((links.reduce(function(total, link) {
          return total + (link.latencyMs || 0);
        }, 0) / links.length).toFixed(1))
        : null,
      activeAlerts: alerts.filter(function(alert) {
        return isActiveAlert(alert.status);
      }).length
    };
    return scene;
  }

  function sceneFromDemo(demoData, showcaseScene) {
    demoData = demoData || {};
    showcaseScene = showcaseScene || {};
    var nodes = (demoData.gpuNodes || []).map(function(node) {
      var totalVram = numberOrNull(node.totalVram);
      var gpuCount = numberOrNull(node.gpuCount) || 1;
      return {
        id: node.id,
        name: node.name,
        pool: node.pool,
        gpuModel: node.gpuModel,
        gpuCount: gpuCount,
        vramPerGpuGb: totalVram === null ? null : totalVram / gpuCount,
        totalVramGb: totalVram,
        usedVramGb: numberOrNull(node.usedVram),
        utilizationPct: numberOrNull(node.utilization),
        status: node.status,
        schedulable: node.status === 'online' || node.status === 'running',
        currentTask: node.currentTask || '—',
        queuedTasks: null,
        latencyMs: null,
        unitPricePerHour: null,
        temperatureC: null,
        heartbeat: null,
        source: 'demo'
      };
    });
    var links = (demoData.networkLinks || []).map(function(link) {
      return {
        id: link.id, name: link.name, source: link.source, target: link.target,
        sourceName: link.source, targetName: link.target,
        latencyMs: numberOrNull(link.latency),
        jitterMs: numberOrNull(link.jitter),
        packetLossPct: numberOrNull(link.packetLoss),
        bandwidthGbps: numberOrNull(link.bandwidth),
        throughputGbps: null,
        status: link.status || 'normal',
        health: link.health || 'healthy',
        source: 'demo'
      };
    });
    var samples = demoData.networkSamples || [];
    var series = {
      labels: samples.map(function(sample, index) { return String(index + 1); }),
      bandwidthGbps: samples.map(function(sample) { return numberOrNull(sample.bandwidth); }),
      latencyMs: samples.map(function(sample) { return numberOrNull(sample.latency); }),
      packetLossPct: samples.map(function(sample) { return numberOrNull(sample.packetLoss); })
    };
    var alerts = (demoData.faultAlerts || []).map(function(alert) {
      return {
        id: alert.id, level: alert.level || 'warning', type: alert.type || 'system',
        targetId: alert.targetId, targetName: alert.targetName || alert.targetId,
        reason: alert.reason || '—', content: alert.reason || '—',
        time: alert.time || '—',
        status: alert.recoveryStatus === 'recovered' ? 'recovered' : 'active',
        autoRecovery: !!alert.autoRecovery,
        recoveryStatus: alert.recoveryStatus || 'warning',
        confirmed: !!alert.confirmed,
        source: 'demo'
      };
    });
    var scene = {
      source: 'demo',
      nodes: nodes,
      pools: demoData.resourcePools || derivePoolsFromNodes(nodes),
      tasks: [],
      networkLinks: links,
      networkSeries: series,
      storageNodes: demoData.storageNodes || [],
      alerts: alerts,
      sessions: demoData.renderSessions || [],
      gpuTrend: showcaseScene.gpuTrend || { labels: [], values: [], unit: '%' },
      taskTrend: showcaseScene.taskTrend || { labels: [], values: [], unit: '个' },
      images: showcaseScene.images || {},
      filmScenes: showcaseScene.filmScenes || [],
      archScenes: showcaseScene.archScenes || [],
      gamingScene: showcaseScene.gamingScene || {},
      topology: null,
      faultScenario: showcaseScene.faultScenario || null,
      events: []
    };
    scene.overview = {
      totalNodes: nodes.length,
      onlineNodes: nodes.filter(function(node) {
        return node.status === 'online' || node.status === 'running';
      }).length,
      schedulableNodes: nodes.filter(function(node) { return node.schedulable; }).length,
      queueDepth: null,
      queuedTasks: null,
      runningTasks: null,
      totalGpus: nodes.reduce(function(total, node) {
        return total + (node.gpuCount || 0);
      }, 0),
      avgGpuUtilPct: null,
      avgGpuMemUsedPct: null,
      avgNetworkLatencyMs: links.length
        ? Number((links.reduce(function(total, link) {
          return total + (link.latencyMs || 0);
        }, 0) / links.length).toFixed(1))
        : null,
      activeAlerts: alerts.filter(function(alert) {
        return isActiveAlert(alert.status);
      }).length
    };
    return scene;
  }

  return {
    adaptMonitoringNodes: adaptMonitoringNodes,
    adaptMonitoringLinks: adaptMonitoringLinks,
    adaptMonitoringSamples: adaptMonitoringSamples,
    adaptStorage: adaptStorage,
    adaptAlerts: adaptAlerts,
    adaptRenderSessions: adaptRenderSessions,
    isActiveAlert: isActiveAlert,
    derivePoolsFromNodes: derivePoolsFromNodes,
    sceneFromLive: sceneFromLive,
    sceneFromDemo: sceneFromDemo
  };
});
