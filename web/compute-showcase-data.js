/**
 * Stable reference scene for the compute platform display.
 *
 * This dataset is intentionally kept outside the real API/billing paths.  It is
 * only consumed when COMPUTE_SHOWCASE_MODE is enabled; it is never written back
 * to business tables and never used for official billing or AI model usage.
 */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.AIGV_COMPUTE_SHOWCASE = factory().buildScene();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  var POOL_META = [
    { id: 'local-workspace', name: '本地工作站', region: '本地机房', kind: 'local' },
    { id: 'private-cluster', name: '私有 GPU 集群', region: '华中私有云', kind: 'private' },
    { id: 'cloud-gpu', name: '云 GPU 资源池', region: '华东云区域', kind: 'cloud' },
    { id: 'edge-nodes', name: '边缘计算节点', region: '展厅边缘节点', kind: 'edge' }
  ];

  var NODES = [
    {
      id: 'node-local-01',
      name: '本地工作站 01',
      pool: 'local-workspace',
      gpuModel: 'RTX 4090',
      gpuCount: 2,
      vramPerGpuGb: 24,
      usedVramGb: 28,
      utilizationPct: 38,
      status: 'online',
      schedulable: true,
      currentTask: '展厅空间预演',
      queuedTasks: 0,
      latencyMs: 3,
      unitPricePerHour: 6,
      temperatureC: 52
    },
    {
      id: 'node-private-a100-01',
      name: '私有集群 A100 01',
      pool: 'private-cluster',
      gpuModel: 'A100 80GB',
      gpuCount: 4,
      vramPerGpuGb: 80,
      usedVramGb: 210,
      utilizationPct: 62,
      status: 'online',
      schedulable: true,
      currentTask: '非遗纪录片镜头渲染',
      queuedTasks: 1,
      latencyMs: 8,
      unitPricePerHour: 18,
      temperatureC: 68
    },
    {
      id: 'node-cloud-l40s-01',
      name: '云 GPU L40S 01',
      pool: 'cloud-gpu',
      gpuModel: 'L40S 48GB',
      gpuCount: 4,
      vramPerGpuGb: 48,
      usedVramGb: 120,
      utilizationPct: 45,
      status: 'online',
      schedulable: true,
      currentTask: '建筑漫游序列',
      queuedTasks: 1,
      latencyMs: 22,
      unitPricePerHour: 12,
      temperatureC: 58
    },
    {
      id: 'node-edge-rtx6000-01',
      name: '边缘节点 RTX 6000',
      pool: 'edge-nodes',
      gpuModel: 'RTX 6000 Ada',
      gpuCount: 2,
      vramPerGpuGb: 48,
      usedVramGb: 30,
      utilizationPct: 18,
      status: 'online',
      schedulable: true,
      currentTask: '互动展厅实时渲染',
      queuedTasks: 0,
      latencyMs: 12,
      unitPricePerHour: 9,
      temperatureC: 46
    }
  ].map(function(node) {
    node.totalVramGb = node.vramPerGpuGb * node.gpuCount;
    node.vramUsedPct = node.totalVramGb
      ? Number(((node.usedVramGb / node.totalVramGb) * 100).toFixed(1))
      : 0;
    // Compatibility aliases used by older renderers.
    node.totalVram = node.totalVramGb;
    node.usedVram = node.usedVramGb;
    node.utilization = node.utilizationPct;
    return node;
  });

  var TASKS = [
    {
      id: 'task-run-01', name: '展厅空间预演', type: 'render', priority: 'medium',
      status: 'running', nodeId: 'node-local-01', gpuCount: 2, queuePosition: 0,
      submittedLabel: 'S2', durationMin: 18
    },
    {
      id: 'task-run-02', name: '非遗纪录片镜头渲染', type: 'render', priority: 'high',
      status: 'running', nodeId: 'node-private-a100-01', gpuCount: 4, queuePosition: 0,
      submittedLabel: 'S1', durationMin: 42
    },
    {
      id: 'task-run-03', name: '建筑漫游序列', type: 'render', priority: 'medium',
      status: 'running', nodeId: 'node-cloud-l40s-01', gpuCount: 4, queuePosition: 0,
      submittedLabel: 'S3', durationMin: 26
    },
    {
      id: 'task-run-04', name: '互动展厅实时渲染', type: 'inference', priority: 'low',
      status: 'running', nodeId: 'node-edge-rtx6000-01', gpuCount: 2, queuePosition: 0,
      submittedLabel: 'S4', durationMin: 12
    },
    {
      id: 'task-queue-01', name: '文物数字孪生镜头', type: 'render', priority: 'high',
      status: 'queued', nodeId: 'node-private-a100-01', gpuCount: 4, queuePosition: 1,
      submittedLabel: 'S6', durationMin: 0
    },
    {
      id: 'task-queue-02', name: '音乐会舞台预演', type: 'render', priority: 'medium',
      status: 'queued', nodeId: 'node-cloud-l40s-01', gpuCount: 4, queuePosition: 1,
      submittedLabel: 'S7', durationMin: 0
    },
    {
      id: 'task-done-01', name: '城市展厅概念片', type: 'render', priority: 'low',
      status: 'completed', nodeId: 'node-cloud-l40s-01', gpuCount: 2, queuePosition: 0,
      submittedLabel: 'S0', durationMin: 36
    }
  ];

  var TASK_TREND = {
    labels: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'],
    values: [3, 4, 3, 5, 4, 5, 6],
    unit: '个'
  };

  var GPU_TREND = {
    labels: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7'],
    values: [41, 44, 43, 47, 46, 44, 45],
    unit: '%'
  };

  var NETWORK_LINKS = [
    {
      id: 'link-local-private', name: '本地 → 私有集群',
      source: 'node-local-01', target: 'node-private-a100-01',
      sourceName: '本地工作站', targetName: '私有 GPU 集群',
      latencyMs: 8, jitterMs: 0.6, packetLossPct: 0.0,
      bandwidthGbps: 25, throughputGbps: 12.4,
      status: 'normal', health: 'healthy'
    },
    {
      id: 'link-local-cloud', name: '本地 → 云 GPU',
      source: 'node-local-01', target: 'node-cloud-l40s-01',
      sourceName: '本地工作站', targetName: '云 GPU 资源池',
      latencyMs: 22, jitterMs: 1.2, packetLossPct: 0.03,
      bandwidthGbps: 25, throughputGbps: 9.8,
      status: 'normal', health: 'healthy'
    },
    {
      id: 'link-local-edge', name: '本地 → 边缘节点',
      source: 'node-local-01', target: 'node-edge-rtx6000-01',
      sourceName: '本地工作站', targetName: '边缘计算节点',
      latencyMs: 12, jitterMs: 0.8, packetLossPct: 0.01,
      bandwidthGbps: 10, throughputGbps: 4.1,
      status: 'normal', health: 'healthy'
    },
    {
      id: 'link-private-cloud', name: '私有集群 → 云 GPU',
      source: 'node-private-a100-01', target: 'node-cloud-l40s-01',
      sourceName: '私有 GPU 集群', targetName: '云 GPU 资源池',
      latencyMs: 19, jitterMs: 1.0, packetLossPct: 0.02,
      bandwidthGbps: 25, throughputGbps: 8.6,
      status: 'normal', health: 'healthy'
    },
    {
      id: 'link-cloud-edge', name: '云 GPU → 边缘节点',
      source: 'node-cloud-l40s-01', target: 'node-edge-rtx6000-01',
      sourceName: '云 GPU 资源池', targetName: '边缘计算节点',
      latencyMs: 26, jitterMs: 1.6, packetLossPct: 0.08,
      bandwidthGbps: 10, throughputGbps: 3.2,
      status: 'normal', health: 'healthy'
    }
  ];

  var NETWORK_SERIES = {
    labels: ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10',
      'T11', 'T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18', 'T19', 'T20'],
    bandwidthGbps: [37.2, 37.8, 38.4, 38.1, 37.6, 37.9, 38.6, 38.2, 37.7, 38.0,
      38.3, 38.8, 38.5, 38.1, 37.9, 38.2, 38.4, 38.0, 37.8, 38.1],
    latencyMs: [17.6, 17.9, 17.4, 17.2, 17.8, 18.0, 17.5, 17.3, 17.7, 17.6,
      17.4, 17.1, 17.3, 17.5, 17.8, 17.6, 17.4, 17.2, 17.5, 17.4],
    packetLossPct: [0.03, 0.04, 0.03, 0.02, 0.03, 0.04, 0.03, 0.02, 0.03, 0.03,
      0.02, 0.03, 0.04, 0.03, 0.03, 0.02, 0.03, 0.03, 0.04, 0.03]
  };

  var TOPOLOGY = {
    width: 560,
    height: 300,
    nodes: [
      { id: 'node-local-01', name: '本地工作站', x: 70, y: 80, status: 'online' },
      { id: 'node-private-a100-01', name: '私有集群', x: 230, y: 62, status: 'online' },
      { id: 'node-cloud-l40s-01', name: '云 GPU', x: 400, y: 95, status: 'online' },
      { id: 'node-edge-rtx6000-01', name: '边缘节点', x: 300, y: 220, status: 'online' },
      { id: 'storage-primary', name: '主素材存储', x: 500, y: 235, status: 'online' }
    ],
    links: [
      { id: 'link-local-private', source: 'node-local-01', target: 'node-private-a100-01' },
      { id: 'link-local-cloud', source: 'node-local-01', target: 'node-cloud-l40s-01' },
      { id: 'link-local-edge', source: 'node-local-01', target: 'node-edge-rtx6000-01' },
      { id: 'link-private-cloud', source: 'node-private-a100-01', target: 'node-cloud-l40s-01' },
      { id: 'link-cloud-edge', source: 'node-cloud-l40s-01', target: 'node-edge-rtx6000-01' }
    ]
  };

  var STORAGE_NODES = [
    {
      id: 'storage-primary', name: '主素材存储', capacityTB: 2.0, usedTB: 1.94,
      readMBps: 820, writeMBps: 540, connections: 18, status: 'normal'
    },
    {
      id: 'storage-archive', name: '归档存储', capacityTB: 1.0, usedTB: 0.58,
      readMBps: 360, writeMBps: 280, connections: 6, status: 'normal'
    }
  ];

  var SWITCH_RECORDS = [
    {
      id: 'switch-01', time: 'S3', type: '链路切换',
      source: '云 GPU 资源池', target: '私有 GPU 集群',
      reason: '链路抖动超过参考阈值', duration: 2.4, result: '成功'
    },
    {
      id: 'switch-02', time: 'S5', type: '节点切换',
      source: '本地工作站 01', target: '边缘节点 RTX 6000',
      reason: '本地节点进入计划维护', duration: 1.8, result: '成功'
    }
  ];

  var EVENTS = [
    { id: 'event-01', time: 'S2', level: 'info', text: '私有集群完成一次渲染队列调度' },
    { id: 'event-02', time: 'S4', level: 'info', text: '云 GPU 链路时延保持在参考范围内' },
    { id: 'event-03', time: 'S6', level: 'info', text: '边缘节点完成互动场景预热' }
  ];

  var FAULT_SCENARIO = {
    linkId: 'link-cloud-edge',
    linkName: '云 GPU → 边缘节点',
    degraded: {
      latencyMs: 68, jitterMs: 4.6, packetLossPct: 1.2,
      bandwidthGbps: 10, throughputGbps: 1.4,
      status: 'degraded', health: 'warning'
    },
    alert: {
      id: 'alert-showcase-link',
      level: 'warning',
      type: 'link',
      targetId: 'link-cloud-edge',
      targetName: '云 GPU → 边缘节点',
      reason: '时延与丢包率超过参考阈值，正在切换备用链路',
      time: 'S7',
      autoRecovery: true,
      recoveryStatus: 'switching',
      confirmed: false
    },
    timeline: [
      { time: 'S7', text: '检测到云 GPU → 边缘节点链路抖动' },
      { time: 'S7+1', text: '备用路径已建立，业务流量切换中' },
      { time: 'S7+2', text: '链路恢复，告警进入待确认状态' }
    ]
  };

  var IMAGES = {
    filmMuseum: '/web/assets/showcase/film-museum.svg',
    filmTheater: '/web/assets/showcase/film-theater.svg',
    filmGallery: '/web/assets/showcase/film-gallery.svg',
    filmConcert: '/web/assets/showcase/film-concert.svg',
    archBefore: '/web/assets/showcase/arch-before.svg',
    archAfter: '/web/assets/showcase/arch-after.svg',
    archIndustrial: '/web/assets/showcase/arch-industrial.svg',
    gamingHall: '/web/assets/showcase/gaming-hall.svg',
    placeholder: '/web/assets/showcase/placeholder.svg'
  };

  var FILM_SCENES = [
    {
      id: 'film-01', title: '博物馆大厅全景', lens: '广角 24mm',
      resolution: '3840 × 2160', durationSec: 8, frames: 192,
      status: '已渲染', image: IMAGES.filmMuseum,
      description: '金色穹顶与编钟阵列在体积光中展开，镜头缓慢前推。'
    },
    {
      id: 'film-02', title: '剧院舞台开场', lens: '中景 35mm',
      resolution: '3840 × 2160', durationSec: 6, frames: 144,
      status: '已渲染', image: IMAGES.filmTheater,
      description: '红色幕布与暖色顶灯构成舞台层次，适合作为开场镜头。'
    },
    {
      id: 'film-03', title: '画廊长廊', lens: '轨道 50mm',
      resolution: '2560 × 1440', durationSec: 10, frames: 240,
      status: '渲染中', image: IMAGES.filmGallery,
      description: '沿画廊长廊移动，展品与光影形成连续视觉节奏。'
    },
    {
      id: 'film-04', title: '音乐厅环视', lens: '环绕 18mm',
      resolution: '3840 × 2160', durationSec: 12, frames: 288,
      status: '待渲染', image: IMAGES.filmConcert,
      description: '音乐厅观众席与穹顶的环绕视角，强调空间尺度。'
    }
  ];

  var ARCH_SCENES = [
    {
      id: 'arch-01', title: '展厅中庭', material: '哑光石材 / 拉丝金属',
      lighting: '日光 + 天窗补光', config: '1440p · 512 samples · 降噪开',
      before: IMAGES.archBefore, after: IMAGES.archAfter,
      description: '中庭空间材质与天窗光线的前后对比。'
    },
    {
      id: 'arch-02', title: '工业设备间', material: '深色金属 / 玻璃',
      lighting: '冷色顶光 + 机械补光', config: '1080p · 256 samples · 降噪开',
      before: IMAGES.archIndustrial, after: IMAGES.archAfter,
      description: '工业设备与管线材质在冷色光照下的渲染表现。'
    },
    {
      id: 'arch-03', title: '室内展陈空间', material: '木饰面 / 织物',
      lighting: '暖色射灯 + 环境光', config: '1440p · 384 samples · 降噪开',
      before: IMAGES.archBefore, after: IMAGES.archIndustrial,
      description: '展陈空间的材质与灯光组合预览。'
    }
  ];

  var GAMING_SCENE = {
    id: 'game-01',
    title: '虚拟展厅漫游',
    image: IMAGES.gamingHall,
    fps: 60,
    latencyMs: 12,
    bitrateMbps: 45,
    packetLossPct: 0.03,
    dataTransfer: '4.8 GB',
    status: 'connected'
  };

  var SESSIONS = [
    {
      id: 'RS-2401', project: '非遗纪录片 · 镜头 03', engine: 'Blender Cycles',
      nodeId: 'node-private-a100-01', gpuNode: '私有 GPU 集群 / A100',
      status: 'rendering', resolution: '3840 × 2160', fps: 24, bitrate: '120 Mbps',
      latencyMs: 8, runtime: '00:42:18', startedAt: 'S1', eta: 'S7', progressPct: 68
    },
    {
      id: 'RS-2402', project: '城市展厅漫游', engine: 'Unreal Engine 5',
      nodeId: 'node-cloud-l40s-01', gpuNode: '云 GPU 资源池 / L40S',
      status: 'queued', resolution: '2560 × 1440', fps: 30, bitrate: '80 Mbps',
      latencyMs: 22, runtime: '00:00:00', startedAt: 'S6', eta: 'S9', progressPct: 0
    },
    {
      id: 'RS-2403', project: '文物数字孪生', engine: 'Blender Cycles',
      nodeId: 'node-local-01', gpuNode: '本地工作站 / RTX 4090',
      status: 'rendering', resolution: '1920 × 1080', fps: 24, bitrate: '60 Mbps',
      latencyMs: 3, runtime: '00:18:42', startedAt: 'S2', eta: 'S6', progressPct: 45
    },
    {
      id: 'RS-2404', project: '互动展厅预演', engine: 'Unity Cloud',
      nodeId: 'node-edge-rtx6000-01', gpuNode: '边缘计算节点 / RTX 6000 Ada',
      status: 'completed', resolution: '2560 × 1440', fps: 60, bitrate: '90 Mbps',
      latencyMs: 12, runtime: '01:12:20', startedAt: 'S0', eta: 'S5', progressPct: 100
    },
    {
      id: 'RS-2405', project: '音乐会舞台预演', engine: 'Blender Cycles',
      nodeId: 'node-cloud-l40s-01', gpuNode: '云 GPU 资源池 / L40S',
      status: 'paused', resolution: '3840 × 2160', fps: 24, bitrate: '110 Mbps',
      latencyMs: 22, runtime: '00:26:05', startedAt: 'S2', eta: 'S8', progressPct: 37
    }
  ];

  function derivePools(nodes, poolMeta) {
    var pools = [];
    for (var i = 0; i < poolMeta.length; i += 1) {
      var meta = poolMeta[i];
      var selected = nodes.filter(function(node) {
        return node.pool === meta.id;
      });
      var nodeCount = selected.length;
      var onlineCount = selected.filter(function(node) {
        return node.status === 'online';
      }).length;
      var gpuCount = selected.reduce(function(total, node) {
        return total + (node.gpuCount || 0);
      }, 0);
      var availGpu = selected.reduce(function(total, node) {
        return total + (node.status === 'online' && node.schedulable !== false
          ? (node.gpuCount || 0) : 0);
      }, 0);
      var weightedUtil = gpuCount
        ? selected.reduce(function(total, node) {
          return total + (node.utilizationPct || 0) * (node.gpuCount || 0);
        }, 0) / gpuCount
        : 0;
      var avgPrice = nodeCount
        ? selected.reduce(function(total, node) {
          return total + (node.unitPricePerHour || 0);
        }, 0) / nodeCount
        : 0;
      var avgLatency = nodeCount
        ? selected.reduce(function(total, node) {
          return total + (node.latencyMs || 0);
        }, 0) / nodeCount
        : 0;
      pools.push({
        id: meta.id,
        name: meta.name,
        region: meta.region,
        kind: meta.kind,
        nodeCount: nodeCount,
        onlineCount: onlineCount,
        gpuCount: gpuCount,
        availGpu: availGpu,
        avgUtil: Number(weightedUtil.toFixed(1)),
        unitPrice: Number(avgPrice.toFixed(1)),
        latency: Number(avgLatency.toFixed(1)),
        status: onlineCount === nodeCount && nodeCount > 0 ? 'healthy' : 'degraded'
      });
    }
    return pools;
  }

  function deriveOverview(scene) {
    var nodes = scene.nodes || [];
    var tasks = scene.tasks || [];
    var links = scene.networkLinks || [];
    var totalGpus = nodes.reduce(function(total, node) {
      return total + (node.gpuCount || 0);
    }, 0);
    var weightedGpuUtil = totalGpus
      ? nodes.reduce(function(total, node) {
        return total + (node.utilizationPct || 0) * (node.gpuCount || 0);
      }, 0) / totalGpus
      : 0;
    var totalVram = nodes.reduce(function(total, node) {
      return total + (node.totalVramGb || 0);
    }, 0);
    var usedVram = nodes.reduce(function(total, node) {
      return total + (node.usedVramGb || 0);
    }, 0);
    var avgLatency = links.length
      ? links.reduce(function(total, link) {
        return total + (link.latencyMs || 0);
      }, 0) / links.length
      : null;
    var queuedTasks = tasks.filter(function(task) {
      return task.status === 'queued';
    }).length;
    var runningTasks = tasks.filter(function(task) {
      return task.status === 'running';
    }).length;
    return {
      totalNodes: nodes.length,
      onlineNodes: nodes.filter(function(node) { return node.status === 'online'; }).length,
      schedulableNodes: nodes.filter(function(node) {
        return node.status === 'online' && node.schedulable !== false;
      }).length,
      queueDepth: queuedTasks,
      queuedTasks: queuedTasks,
      runningTasks: runningTasks,
      totalGpus: totalGpus,
      avgGpuUtilPct: Number(weightedGpuUtil.toFixed(1)),
      avgGpuMemUsedPct: totalVram ? Number(((usedVram / totalVram) * 100).toFixed(1)) : 0,
      avgNetworkLatencyMs: avgLatency === null ? null : Number(avgLatency.toFixed(1)),
      activeAlerts: (scene.alerts || []).filter(function(alert) {
        return alert.status === 'active';
      }).length
    };
  }

  function buildScene() {
    var nodes = JSON.parse(JSON.stringify(NODES));
    var tasks = JSON.parse(JSON.stringify(TASKS));
    var pools = derivePools(nodes, POOL_META);
    var scene = {
      version: 1,
      source: 'showcase',
      snapshotLabel: 'reference-scene-v1',
      poolMeta: POOL_META,
      nodes: nodes,
      pools: pools,
      tasks: tasks,
      gpuTrend: GPU_TREND,
      taskTrend: TASK_TREND,
      networkLinks: NETWORK_LINKS,
      networkSeries: NETWORK_SERIES,
      topology: TOPOLOGY,
      storageNodes: STORAGE_NODES,
      switchRecords: SWITCH_RECORDS,
      events: EVENTS,
      alerts: [],
      faultScenario: FAULT_SCENARIO,
      images: IMAGES,
      filmScenes: FILM_SCENES,
      archScenes: ARCH_SCENES,
      gamingScene: GAMING_SCENE,
      sessions: SESSIONS
    };
    scene.overview = deriveOverview(scene);
    return scene;
  }

  function uniqueIds(items) {
    var seen = {};
    var duplicates = [];
    (items || []).forEach(function(item) {
      if (seen[item.id]) duplicates.push(item.id);
      seen[item.id] = true;
    });
    return duplicates;
  }

  function validateScene(scene) {
    var issues = [];
    if (!scene) return ['scene is empty'];
    var nodes = scene.nodes || [];
    var pools = scene.pools || [];
    var tasks = scene.tasks || [];
    var links = scene.networkLinks || [];
    var overview = scene.overview || {};

    if (overview.totalNodes !== nodes.length) {
      issues.push('overview.totalNodes does not match nodes.length');
    }
    if (overview.onlineNodes > overview.totalNodes) {
      issues.push('onlineNodes exceeds totalNodes');
    }
    if (overview.queuedTasks !== tasks.filter(function(t) {
      return t.status === 'queued';
    }).length) {
      issues.push('queued task count mismatch');
    }
    if (overview.queuedTasks !== nodes.reduce(function(total, node) {
      return total + (node.queuedTasks || 0);
    }, 0)) {
      issues.push('node queuedTasks does not match overview');
    }
    if (pools.reduce(function(total, pool) {
      return total + pool.nodeCount;
    }, 0) !== nodes.length) {
      issues.push('pool node counts do not match nodes');
    }
    var poolGpuTotal = pools.reduce(function(total, pool) {
      return total + pool.gpuCount;
    }, 0);
    if (poolGpuTotal !== nodes.reduce(function(total, node) {
      return total + node.gpuCount;
    }, 0)) {
      issues.push('pool GPU counts do not match nodes');
    }
    if (uniqueIds(nodes).length) issues.push('duplicate node ids');
    if (uniqueIds(links).length) issues.push('duplicate link ids');
    if (uniqueIds(scene.topology ? scene.topology.nodes : []).length) {
      issues.push('duplicate topology node ids');
    }

    var nodeIds = {};
    nodes.forEach(function(node) { nodeIds[node.id] = true; });
    links.forEach(function(link) {
      if (!nodeIds[link.source] || !nodeIds[link.target]) {
        issues.push('network link references unknown node: ' + link.id);
      }
    });
    var topologyIds = {};
    (scene.topology ? scene.topology.nodes : []).forEach(function(node) {
      topologyIds[node.id] = true;
    });
    (scene.topology ? scene.topology.links : []).forEach(function(link) {
      if (!topologyIds[link.source] || !topologyIds[link.target]) {
        issues.push('topology link references unknown node: ' + link.id);
      }
      if (!links.some(function(networkLink) {
        return networkLink.id === link.id;
      })) {
        issues.push('topology link missing from network links: ' + link.id);
      }
    });
    tasks.forEach(function(task) {
      if (!nodeIds[task.nodeId]) {
        issues.push('task references unknown node: ' + task.id);
      }
    });
    (scene.sessions || []).forEach(function(session) {
      if (!nodeIds[session.nodeId]) {
        issues.push('session references unknown node: ' + session.id);
      }
    });
    Object.keys(scene.images || {}).forEach(function(key) {
      var path = scene.images[key];
      if (path.indexOf('/web/assets/showcase/') !== 0) {
        issues.push('image is not local: ' + path);
      }
      if (path.indexOf('http') !== -1) {
        issues.push('image uses an external URL: ' + path);
      }
    });
    if (scene.officialBilling || scene.volcengine || scene.billingRecords) {
      issues.push('scene contains official billing fields');
    }
    return issues;
  }

  return {
    buildScene: buildScene,
    derivePools: derivePools,
    deriveOverview: deriveOverview,
    validateScene: validateScene,
    POOL_META: POOL_META
  };
});
