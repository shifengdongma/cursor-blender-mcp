/**
 * AIGV Studio Compute Platform Frontend
 * Vanilla JS implementation for compute orchestration center
 * Tabs: 运行总览, 云渲染, GPU调度, 网络监控, 权限安全, 费用告警
 */
(function() {
  'use strict';

  // ── DOM helpers ──
  function $(id) { return document.getElementById(id); }
  // Quote-safe: values are used inside onclick/title attributes.
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[ch];
    });
  }

  // ── Toast notification ──
  var toastContainer = null;
  function createToastContainer() {
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.className = 'toast-container';
      document.body.appendChild(toastContainer);
    }
    return toastContainer;
  }
  function showToast(message, type) {
    type = type || 'info';
    var container = createToastContainer();
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(function() {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, 3000);
  }

  // ── API helper ──
  function api(path, opts) {
    opts = opts || {};
    return window.AIGV.api(path, {
      method: opts.method || 'GET',
      headers: opts.headers || {},
      body: opts.body || undefined
    });
  }
  function apiSuppress() {
    return null; // fallback for optional data
  }

  // ── Monitoring API helpers ──

  var monitoringPollInterval = null;

  function fetchMonitoringNodes() {
    return api('/api/monitoring/nodes').catch(function(err) {
      console.error('fetchMonitoringNodes error:', err);
      return { nodes: [], total: 0 };
    });
  }

  function fetchNetworkLinks() {
    return api('/api/monitoring/links').catch(function(err) {
      console.error('fetchNetworkLinks error:', err);
      return { links: [], stats: {} };
    });
  }

  function fetchMonitoringSamples(limit) {
    return api('/api/monitoring/samples?limit=' + (limit || 20)).catch(function(err) {
      console.error('fetchMonitoringSamples error:', err);
      return { samples: [], total: 0 };
    });
  }

  function fetchStorageData() {
    return api('/api/monitoring/storage').catch(function(err) {
      console.error('fetchStorageData error:', err);
      return { targets: [], summary: {} };
    });
  }

  function fetchAlerts(status, limit) {
    return api('/api/alerts?status=' + (status || 'open') + '&limit=' + (limit || 20)).catch(function(err) {
      console.error('fetchAlerts error:', err);
      return { items: [], total: 0 };
    });
  }

  function acknowledgeAlert(alertId) {
    return api('/api/alerts/' + alertId + '/acknowledge', { method: 'POST' });
  }

  function closeAlert(alertId, notes) {
    return api('/api/alerts/' + alertId + '/close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notes || '' })
    });
  }

  // ── Loading/error state helpers ──

  function showLoading(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="loading-indicator" style="text-align:center;padding:40px;color:var(--text-soft)"><div class="spinner" style="width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px"></div><p>加载中...</p></div>';
  }

  function hideLoading(containerId) {
    var el = document.getElementById(containerId);
    if (el) {
      var indicator = el.querySelector('.loading-indicator');
      if (indicator) indicator.remove();
    }
  }

  // Add slideIn and spin animations
  var platformStyle = document.createElement('style');
  platformStyle.textContent = '@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}@keyframes spin{to{transform:rotate(360deg)}}';
  if (!document.getElementById('cp-platform-ext-style')) {
    platformStyle.id = 'cp-platform-ext-style';
    document.head.appendChild(platformStyle);
  }

  // ── State ──
  var state = {
    activeTab: 'overview',
    demoData: null,
    scene: null,
    sceneSource: 'live',
    realShowcaseImages: [],
    realShowcaseGlb: null,
    gpuNodeFilter: { search: '', pool: 'all', status: 'all' },
    schedulingForm: {},
    schedulingResult: null,
    schedulingFlow: 'pending',
    isNetworkAutoRefresh: true,
    networkRefreshCountdown: 5,
    networkLinksCopy: [],
    sensingNodesCopy: [],
    storageNodesCopy: [],
    networkSamplesCopy: { labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: [] },
    faultAlertsCopy: [],
    eventsCopy: [],
    switchRecordsCopy: [],
    monitoringTimer: null,
    clockTimer: null,
    faultSimTimers: [],
    faultSimActive: false,
    networkPlaybackTimer: null,
    networkPlaybackPaused: false,
    networkPlaybackCursor: 11,
    networkScenarioFault: false,
    networkFaultSnapshot: null,
    pendingConfirmAlerts: [],
    sdLsKey: 'aigv_sensing_dashboard_v1',
    rolePermissions: {},
    alerts: [],
    liveMonitoringNodes: [],
    opsEvents: [],
    anomalyTimers: [],
    // Sub-tab state for cloud rendering
    renderSubTab: 'film',
    renderSubTabPrev: null,
    filmInitTimeout: null,
    filmSelectedKeyframe: 0,
    // Architecture scene
    archInitTimeout: null,
    archTaskTimers: [],
    archThumbTimers: [],
    archShowcaseIndex: 0,
    archComparePct: 50,
    archSelectedMaterial: 'arch-mat-stone',
    archSelectedLighting: 'arch-lit-warm',
    archTaskRunning: false,
    // Gaming scene
    gameInitTimeout: null,
    gamePlayerPos: { x: 0, y: 1.6, z: 0 },
    gamePlayerAngle: 0,
    gameKeysPressed: {},
    gameNetworkInterval: null,
    gameDpadAbort: null,
    gameConnected: true,
    gameExhibitMeshes: [],
    // Film scene
    filmThreeScene: null,
    filmThreeRenderer: null,
    filmAnimFrameId: null,
    filmAutoplayInterval: null,
    filmOrbitControls: null,
    // Architecture scene
    archThreeScene: null,
    archThreeRenderer: null,
    archAnimFrameId: null,
    archModelMesh: null,
    // Gaming scene
    gameThreeScene: null,
    gameThreeRenderer: null,
    gameAnimFrameId: null
  };

  // ── localStorage Persistence ──
  var LS_KEY = 'aigv_compute_platform_v1';
  var LS_VERSION = 1;

  function demoMode() {
    return !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
  }

  function saveToLocalStorage() {
    if (!demoMode()) return;
    try {
      var payload = {
        version: LS_VERSION,
        alerts: state.alerts,
        opsEvents: state.opsEvents
      };
      localStorage.setItem(LS_KEY, JSON.stringify(payload));
    } catch (e) { /* quota exceeded or disabled */ }
  }

  function loadFromLocalStorage() {
    if (!demoMode()) {
      try { localStorage.removeItem(LS_KEY); } catch (e) {}
      return false;
    }
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return false;
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== LS_VERSION) return false;
      if (parsed.alerts && parsed.alerts.length) state.alerts = parsed.alerts;
      if (parsed.opsEvents && parsed.opsEvents.length) state.opsEvents = parsed.opsEvents;
      return true;
    } catch (e) { return false; }
  }

  function saveSensingToLocalStorage() {
    if (!demoMode()) return;
    try {
      var payload = {
        autoRefresh: state.isNetworkAutoRefresh,
        confirmedAlerts: state.faultAlertsCopy.filter(function(a) { return a.confirmed; }).map(function(a) { return a.id; }),
        switchRecords: state.switchRecordsCopy,
        lastUpdate: new Date().toISOString()
      };
      localStorage.setItem(state.sdLsKey, JSON.stringify(payload));
    } catch (e) { /* quota exceeded or disabled */ }
  }

  function loadSensingFromLocalStorage() {
    if (!demoMode()) {
      try { localStorage.removeItem(state.sdLsKey); } catch (e) {}
      return false;
    }
    try {
      var raw = localStorage.getItem(state.sdLsKey);
      if (!raw) return false;
      var parsed = JSON.parse(raw);
      if (!parsed) return false;
      if (parsed.autoRefresh !== undefined) state.isNetworkAutoRefresh = parsed.autoRefresh;
      if (parsed.switchRecords && parsed.switchRecords.length) {
        state.switchRecordsCopy = parsed.switchRecords;
      }
      return true;
    } catch (e) { return false; }
  }

  // ── Tab Switching ──
  function switchTab(tabId) {
    if (tabId === 'ai-models' && window.AIGVArk && !window.AIGVArk.isAdmin()) {
      showToast('仅平台管理员可查看 AI 模型服务', 'warning');
      tabId = 'overview';
    }
    state.activeTab = tabId;

    // Update tab buttons
    var buttons = document.querySelectorAll('.cp-tab-btn');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].classList.remove('active');
      buttons[i].setAttribute('aria-selected', 'false');
      if (buttons[i].getAttribute('data-tab') === tabId) {
        buttons[i].classList.add('active');
        buttons[i].setAttribute('aria-selected', 'true');
      }
    }

    // Update panels
    var panels = document.querySelectorAll('.cp-panel');
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.remove('active');
    }
    var activePanel = $('tab-' + tabId);
    if (activePanel) activePanel.classList.add('active');

    // Timer management for network tab
    if (tabId !== 'network') {
      stopMonitoring();
      stopNetworkPlayback();
      cancelFaultSimulation();
      if (state.clockTimer) { clearInterval(state.clockTimer); state.clockTimer = null; }
      if (monitoringPollInterval) {
        clearInterval(monitoringPollInterval);
        monitoringPollInterval = null;
      }
    } else {
      startClockTimer();
      if (scenarioMode()) {
        stopMonitoring();
        if (!state.networkLinksCopy.length) syncScenarioNetworkState();
        updateNetworkControls();
        if (!state.networkPlaybackPaused) startNetworkPlayback();
      } else {
        if (state.isNetworkAutoRefresh) startMonitoring();
        else stopMonitoring();
      }
    }

    // Cleanup Three.js scenes when leaving cloud rendering tab
    if (state.activeTab !== 'rendering') {
      cleanupAllRenderSubTabs();
    }

    // Render
    renderCurrentTab();
  }

  function renderCurrentTab() {
    switch (state.activeTab) {
      case 'overview': renderOverview(); break;
      case 'rendering': renderRendering(); break;
      case 'gpu': renderGPU(); break;
      case 'scheduling': renderScheduling(); break;
      case 'ai-models':
        if (window.AIGVArk) window.AIGVArk.activate();
        break;
      case 'network': renderNetwork(); break;
      case 'permissions': renderPermissions(); break;
      case 'billing': renderBilling(); break;
    }
  }

  // ── Detail Drawer ──
  function showDetailDrawer(title, html) {
    var titleEl = $('cp-drawer-title');
    var bodyEl = $('cp-drawer-body');
    var drawer = $('cp-detail-drawer');
    var backdrop = $('cp-drawer-backdrop');
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.innerHTML = html;
    if (drawer) drawer.classList.add('open');
    if (backdrop) backdrop.classList.add('open');
  }

  function closeDetailDrawer() {
    var drawer = $('cp-detail-drawer');
    var backdrop = $('cp-drawer-backdrop');
    if (drawer) drawer.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
  }

  // ── Badge helper ──
  function badge(text, cls) {
    return '<span class="cp-badge ' + escapeHtml(cls) + '">' + escapeHtml(text) + '</span>';
  }

  // ── WebGL Availability check ──
  function isThreeAvailable() {
    try {
      return typeof THREE !== 'undefined' && typeof THREE.Scene === 'function';
    } catch (e) {
      return false;
    }
  }

  function isWebGLAvailable() {
    try {
      var canvas = document.createElement('canvas');
      var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      return !!gl;
    } catch (e) {
      return false;
    }
  }

  // ── Render Sub-Tab System ──
  function switchRenderSubTab(subTabId) {
    if (state.renderSubTab === subTabId) return;
    state.renderSubTabPrev = state.renderSubTab;
    state.renderSubTab = subTabId;

    // Update sub-tab buttons
    var buttons = document.querySelectorAll('.cp-sub-tab-btn');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].classList.remove('active');
      buttons[i].setAttribute('aria-selected', 'false');
      if (buttons[i].getAttribute('data-subtab') === subTabId) {
        buttons[i].classList.add('active');
        buttons[i].setAttribute('aria-selected', 'true');
      }
    }

    // Hide all sub-panels
    var panels = document.querySelectorAll('.cp-sub-panel');
    for (var j = 0; j < panels.length; j++) {
      panels[j].classList.remove('active');
    }

    // Show target sub-panel
    var activePanel = document.getElementById('cp-sub-' + subTabId);
    if (activePanel) activePanel.classList.add('active');

    // Cleanup previous sub-tab resources
    if (state.renderSubTabPrev) {
      cleanupRenderSubTab(state.renderSubTabPrev);
    }

    // Render new sub-tab
    renderSubTab(subTabId);
  }

  function renderSubTab(subTabId) {
    switch (subTabId) {
      case 'film':
        renderFilmSubTab();
        break;
      case 'architecture':
        renderArchitectureSubTab();
        break;
      case 'gaming':
        renderGamingSubTab();
        break;
      case 'sessions':
        renderSessionsSubTab();
        break;
    }
  }

  function cleanupRenderSubTab(subTabId) {
    switch (subTabId) {
      case 'film': cleanupFilmResources(); break;
      case 'architecture': cleanupArchitectureResources(); break;
      case 'gaming': cleanupGamingResources(); break;
      case 'sessions': break; // No cleanup needed
    }
  }

  function cleanupAllRenderSubTabs() {
    cleanupFilmResources();
    cleanupArchitectureResources();
    cleanupGamingResources();
  }

  function showWebGLFallback(panelId) {
    var panel = document.getElementById(panelId);
    if (!panel) return;
    var msgHtml =
      '<div style="padding:40px;text-align:center;color:var(--text-soft)">' +
      '<div style="font-size:1.2rem;margin-bottom:8px">WebGL 不可用</div>' +
      '<div style="font-size:0.85rem">您的浏览器不支持 WebGL 或 Three.js 未加载成功，3D 预览功能不可用。</div>' +
      '<div style="font-size:0.75rem;margin-top:8px">建议使用 Chrome / Edge / Firefox 最新版本。</div>' +
      '</div>';
    panel.innerHTML = msgHtml;
  }

  // ── Resize helper for Three.js canvases ──
  var resizeTimer = null;
  function handleResize() {
    if (!resizeTimer) {
      resizeTimer = setTimeout(function() {
        resizeTimer = null;
        resizeFilmCanvas();
        resizeArchCanvas();
        resizeGameCanvas();
      }, 150);
    }
  }

  function resizeFilmCanvas() {
    if (!state.filmThreeRenderer) return;
    var el = document.getElementById('cp-film-viewer');
    if (!el) return;
    var w = el.clientWidth;
    var h = el.clientHeight;
    if (w <= 0 || h <= 0) return;
    state.filmThreeRenderer.setSize(w, h, false);
    var cam = state.filmThreeRenderer.domElement.__filmCam;
    if (cam && cam.aspect) {
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    }
  }

  function resizeArchCanvas() {
    if (!state.archThreeRenderer) return;
    var el = document.getElementById('cp-arch-viewer');
    if (!el) return;
    var w = el.clientWidth;
    var h = el.clientHeight;
    if (w <= 0 || h <= 0) return;
    state.archThreeRenderer.setSize(w, h, false);
    var cam = state.archThreeRenderer.domElement.__archCam;
    if (cam && cam.aspect) {
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    }
  }

  function resizeGameCanvas() {
    if (!state.gameThreeRenderer) return;
    var el = document.getElementById('cp-game-viewer');
    if (!el) return;
    var w = el.clientWidth;
    var h = el.clientHeight;
    if (w <= 0 || h <= 0) return;
    state.gameThreeRenderer.setSize(w, h, false);
    var cam = state.gameThreeRenderer.domElement.__gameCam;
    if (cam && cam.aspect) {
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
    }
  }

  // ══════════════════════════════════════════════════
  // Tab 1: Overview Dashboard
  // ══════════════════════════════════════════════════
  function computeGpuUtilFromNodes(nodes) {
    var weight = 0;
    var total = 0;
    (nodes || []).forEach(function(node) {
      if (node.utilizationPct === null || node.utilizationPct === undefined) return;
      var gpuCount = Math.max(1, Number(node.gpuCount) || 1);
      total += Number(node.utilizationPct) * gpuCount;
      weight += gpuCount;
    });
    return weight ? Number((total / weight).toFixed(1)) : null;
  }

  function computeLatencyFromLinks(links) {
    var values = (links || []).map(function(link) {
      return link.latencyMs;
    }).filter(function(value) {
      return value !== null && value !== undefined && isFinite(Number(value));
    });
    if (!values.length) return null;
    return Number((values.reduce(function(sum, value) {
      return sum + Number(value);
    }, 0) / values.length).toFixed(1));
  }

  function countActiveAlerts(alerts) {
    return (alerts || []).filter(function(alert) {
      return window.ComputeAdapters
        ? window.ComputeAdapters.isActiveAlert(alert.status)
        : (alert.status === 'active' || alert.status === 'open');
    }).length;
  }

  function renderOverview() {
    var scene = state.scene || {};
    var overview = scene.overview || {};
    var summary = state.apiSummary || {};
    var activeAlerts = scenarioMode()
      ? countActiveAlerts(state.faultAlertsCopy)
      : countActiveAlerts(state.alerts);
    var avgGpuUtil = scenarioMode()
      ? overview.avgGpuUtilPct
      : computeGpuUtilFromNodes(scene.nodes);
    var avgLatency = scenarioMode()
      ? overview.avgNetworkLatencyMs
      : computeLatencyFromLinks(scene.networkLinks);

    var metrics;
    if (scenarioMode()) {
      metrics = [
        { value: overview.totalNodes, label: '算力节点', unit: '台' },
        { value: overview.onlineNodes, label: '在线节点', unit: '台' },
        { value: overview.schedulableNodes, label: '可调度节点', unit: '台' },
        { value: overview.queueDepth, label: '排队深度', unit: '个' },
        { value: overview.queuedTasks, label: '排队任务', unit: '个' },
        { value: overview.runningTasks, label: '运行任务', unit: '个' },
        { value: overview.totalGpus, label: 'GPU 总数', unit: '卡' },
        { value: valueOrDash(avgGpuUtil), label: 'GPU 平均利用率', unit: '%' },
        { value: valueOrDash(avgLatency), label: '平均网络时延', unit: 'ms' },
        { value: activeAlerts, label: '当前告警', unit: '条' }
      ];
    } else {
      metrics = [
        { value: valueOrDash(summary.total_nodes !== undefined ? summary.total_nodes : overview.totalNodes), label: '算力节点', unit: '台' },
        { value: valueOrDash(summary.online_nodes !== undefined ? summary.online_nodes : overview.onlineNodes), label: '在线节点', unit: '台' },
        { value: valueOrDash(overview.schedulableNodes), label: '可调度节点', unit: '台' },
        { value: valueOrDash(summary.queue_depth), label: '排队深度', unit: '个' },
        { value: valueOrDash(summary.queued_render_jobs), label: '排队任务', unit: '个' },
        { value: valueOrDash(summary.running_render_jobs), label: '运行任务', unit: '个' },
        { value: valueOrDash(overview.totalGpus), label: 'GPU 总数', unit: '卡' },
        { value: valueOrDash(avgGpuUtil), label: 'GPU 平均利用率', unit: '%' },
        { value: valueOrDash(avgLatency), label: '平均网络时延', unit: 'ms' },
        { value: activeAlerts, label: '当前告警', unit: '条' }
      ];
    }

    var grid = $('cp-metrics-grid');
    if (!grid) return;
    var h = '';
    for (var m = 0; m < metrics.length; m += 1) {
      var met = metrics[m];
      h += '<div class="cp-metric-card">' +
        '<div class="cp-metric-value">' + escapeHtml(met.value) +
        '<span class="cp-metric-unit"> ' + escapeHtml(met.unit) + '</span></div>' +
        '<div class="cp-metric-label">' + escapeHtml(met.label) + '</div>' +
        '</div>';
    }
    grid.innerHTML = h;

    renderMiniCharts(scene);
  }

  function renderMiniCharts(scene) {
    var grid = $('cp-charts-grid');
    if (!grid) return;
    var charts = window.ComputeCharts;
    if (!charts) {
      grid.innerHTML = '<div class="cp-chart-empty">图表组件未加载</div>';
      return;
    }
    var pools = (scene && scene.pools) || [];
    var links = (scene && scene.networkLinks) || [];
    var gpuValues = pools.map(function(pool) { return pool.avgUtil; });
    var gpuChart = charts.barChart({
      labels: pools.map(function(pool) { return pool.name; }),
      values: gpuValues,
      unit: '%',
      yMax: 100,
      xAxisLabel: '资源池',
      title: 'GPU 利用率',
      ariaLabel: 'GPU 利用率柱状图'
    });

    var taskTrend = scenarioMode() && scene.taskTrend
      ? scene.taskTrend
      : { labels: [], values: [], unit: '个' };
    var taskChart = charts.lineChart({
      labels: taskTrend.labels || [],
      values: taskTrend.values || [],
      unit: taskTrend.unit || '个',
      zeroBaseline: true,
      xAxisLabel: '采样点',
      title: '任务量趋势',
      ariaLabel: '任务量趋势折线图'
    });

    var donutChart = charts.donutChart({
      items: pools.map(function(pool, index) {
        return {
          label: pool.name,
          value: pool.nodeCount,
          color: charts.PALETTE[index % charts.PALETTE.length]
        };
      }),
      unit: '台',
      title: '资源池分布',
      ariaLabel: '资源池节点分布环形图'
    });

    var latencyChart = charts.barChart({
      labels: links.map(function(link) { return link.name; }),
      values: links.map(function(link) { return link.latencyMs; }),
      unit: 'ms',
      xAxisLabel: '链路',
      title: '网络时延',
      ariaLabel: '网络链路时延柱状图',
      colors: ['#74c798', '#78bfd2', '#78bfd2', '#d7a84f', '#c9876e']
    });

    grid.innerHTML =
      '<div class="cp-chart-container"><div class="cp-chart-title">GPU 利用率</div>' + gpuChart + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">任务量趋势</div>' + taskChart + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">资源池分布</div>' + donutChart + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">网络时延</div>' + latencyChart + '</div>';
  }

  // ══════════════════════════════════════════════════
  // Tab 2: Cloud Render — Sub-Tab Dispatch
  // ══════════════════════════════════════════════════
  function renderRendering() {
    renderSubTab(state.renderSubTab);
  }

  // ══════════════════════════════════════════════════
  // Sub-Tab: 影视与动画 (Film & Animation)
  // ══════════════════════════════════════════════════
  function renderFilmSubTab() {
    var placeholder = document.getElementById('cp-film-placeholder');
    if (!scenarioMode()) {
      if (placeholder) {
        placeholder.textContent = '影视动画关键帧未接入实时渲染数据';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';
    if (state.filmThreeScene) {
      renderFilmKeyframes();
      updateFilmInfo(state.filmSelectedKeyframe);
      renderFilmShowcase(state.filmSelectedKeyframe);
      if (!state.filmAnimFrameId) animateFilmScene();
      return;
    }
    if (state.filmInitTimeout) clearTimeout(state.filmInitTimeout);
    state.filmInitTimeout = setTimeout(function() {
      state.filmInitTimeout = null;
      initFilmScene();
      loadFilmModel();
      renderFilmKeyframes();
      updateFilmInfo(state.filmSelectedKeyframe);
      renderFilmShowcase(state.filmSelectedKeyframe);
      animateFilmScene();
    }, 50);
  }

  function renderFilmShowcase(index) {
    var container = document.getElementById('cp-film-showcase');
    if (!container) return;
    var scenes = getFilmScenes();
    if (!scenes.length) {
      container.innerHTML = '';
      return;
    }
    var item = scenes[index] || scenes[0];
    var image = resolveSceneImage(item, index);
    container.innerHTML = '<div class="cp-film-reference">' +
      '<div class="cp-film-reference-frame">' +
      '<img loading="lazy" decoding="async" src="' + escapeHtml(image) +
      '" alt="' + escapeHtml(item.title || '影视参考画面') + '" ' +
      imageFallbackAttr() + ' />' +
      '<span class="cp-film-reference-status">' + escapeHtml(item.status || '参考画面') + '</span>' +
      '</div>' +
      '<div class="cp-film-reference-info">' +
      '<div class="cp-film-reference-title">' + escapeHtml(item.title || '未命名镜头') + '</div>' +
      '<div class="cp-film-reference-desc">' + escapeHtml(item.description || '') + '</div>' +
      '<div class="cp-film-reference-grid">' +
      '<div><span>分辨率</span><strong>' + escapeHtml(item.resolution || '—') + '</strong></div>' +
      '<div><span>时长</span><strong>' + escapeHtml(String(item.durationSec || '—')) + ' 秒</strong></div>' +
      '<div><span>帧数</span><strong>' + escapeHtml(String(item.frames || '—')) + '</strong></div>' +
      '<div><span>镜头</span><strong>' + escapeHtml(item.lens || '—') + '</strong></div>' +
      '</div></div></div>';
  }

  function initFilmScene() {
    if (state.filmThreeScene) return; // Already initialized
    var viewer = document.getElementById('cp-film-viewer');
    if (!viewer) return;
    if (!isThreeAvailable() || !isWebGLAvailable()) {
      var unsupported = document.getElementById('cp-film-placeholder');
      if (unsupported) {
        unsupported.textContent = '当前环境不支持 WebGL 3D 预览，参考画面仍可浏览';
        unsupported.style.display = 'block';
      }
      return;
    }
    var w = viewer.clientWidth;
    var h = viewer.clientHeight;
    if (w <= 0 || h <= 0) return;

    // Scene
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a1018);
    state.filmThreeScene = scene;

    // Camera
    var camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
    camera.position.set(4, 3, 6);
    camera.lookAt(0, 0.5, 0);

    // Renderer
    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.__filmCam = camera;
    viewer.appendChild(renderer.domElement);
    state.filmThreeRenderer = renderer;

    // OrbitControls
    if (typeof THREE.OrbitControls === 'function') {
      var controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = 2;
      controls.maxDistance = 15;
      controls.target.set(0, 0.5, 0);
      state.filmOrbitControls = controls;
    }

    // Lights
    var ambient = new THREE.AmbientLight(0x334455, 0.7);
    scene.add(ambient);

    var key = new THREE.DirectionalLight(0xd7a84f, 1.2);
    key.position.set(5, 8, 3);
    key.castShadow = true;
    key.shadow.mapSize.width = 512;
    key.shadow.mapSize.height = 512;
    scene.add(key);

    var fill = new THREE.DirectionalLight(0x78bfd2, 0.5);
    fill.position.set(-3, 2, -2);
    scene.add(fill);

    var rim = new THREE.DirectionalLight(0xffffff, 0.4);
    rim.position.set(0, 1, -4);
    scene.add(rim);

    // Ground plane
    var planeGeo = new THREE.PlaneGeometry(20, 20);
    var planeMat = new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0.8, metalness: 0.1 });
    var plane = new THREE.Mesh(planeGeo, planeMat);
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = -1;
    plane.receiveShadow = true;
    scene.add(plane);

    // Hide placeholder
    var placeholder = document.getElementById('cp-film-placeholder');
    if (placeholder) placeholder.style.display = 'none';
  }

  function loadFilmModel() {
    var scene = state.filmThreeScene;
    if (!scene) return;
    // Prefer an accessible asset-library GLB; local fallback geometry otherwise.
    var modelUrl = state.realShowcaseGlb;
    if (modelUrl && typeof THREE.GLTFLoader === 'function') {
      var loader = new THREE.GLTFLoader();
      loader.load(
        modelUrl,
        function(gltf) {
          var model = gltf.scene;
          model.position.set(0, 0, 0);
          model.scale.set(1, 1, 1);
          model.castShadow = true;
          model.receiveShadow = true;
          scene.add(model);
          state.filmThreeScene.__model = model;
        },
        function() { /* progress */ },
        function() {
          buildFilmFallbackGeometry();
        }
      );
    } else {
      buildFilmFallbackGeometry();
    }
  }

  function buildFilmFallbackGeometry() {
    var scene = state.filmThreeScene;
    if (!scene) return;

    // Torus knot as centerpiece
    var knotGeo = new THREE.TorusKnotGeometry(0.8, 0.2, 100, 16);
    var knotMat = new THREE.MeshStandardMaterial({ color: 0xd7a84f, roughness: 0.2, metalness: 0.8 });
    var knot = new THREE.Mesh(knotGeo, knotMat);
    knot.position.set(0, 0.5, 0);
    knot.castShadow = true;
    knot.receiveShadow = true;
    scene.add(knot);

    // Floating cubes
    var cubeColors = [0x78bfd2, 0xc9876e, 0x94ddf1, 0xe8c97a, 0x5fa8b8];
    for (var i = 0; i < cubeColors.length; i++) {
      var cubeGeo = new THREE.BoxGeometry(0.25, 0.25, 0.25);
      var cubeMat = new THREE.MeshStandardMaterial({ color: cubeColors[i], roughness: 0.3, metalness: 0.5 });
      var cube = new THREE.Mesh(cubeGeo, cubeMat);
      var angle = (i / cubeColors.length) * Math.PI * 2;
      cube.position.set(Math.cos(angle) * 2, 0.5 + i * 0.3, Math.sin(angle) * 2);
      cube.castShadow = true;
      cube.receiveShadow = true;
      scene.add(cube);
      if (!state.filmThreeScene.__cubes) state.filmThreeScene.__cubes = [];
      state.filmThreeScene.__cubes.push(cube);
    }
    state.filmThreeScene.__model = knot;
  }

  function animateFilmScene() {
    if (!state.filmThreeScene || !state.filmThreeRenderer) {
      state.filmAnimFrameId = null;
      return;
    }

    state.filmAnimFrameId = requestAnimationFrame(animateFilmScene);

    // Animate torus knot
    var model = state.filmThreeScene.__model;
    if (model) {
      model.rotation.y += 0.005;
      model.rotation.x += 0.002;
    }
    // Animate cubes
    var cubes = state.filmThreeScene.__cubes;
    if (cubes) {
      for (var i = 0; i < cubes.length; i++) {
        cubes[i].rotation.x += 0.01;
        cubes[i].rotation.y += 0.008;
        cubes[i].position.y = 0.5 + i * 0.3 + Math.sin(Date.now() * 0.002 + i) * 0.15;
      }
    }

    if (state.filmOrbitControls) state.filmOrbitControls.update();
    state.filmThreeRenderer.render(state.filmThreeScene, state.filmThreeRenderer.domElement.__filmCam);
  }

  function renderFilmKeyframes() {
    var strip = document.getElementById('cp-film-thumb-strip');
    if (!strip) return;
    var scenes = getFilmScenes();
    if (!scenes.length) {
      strip.innerHTML = '<div class="cp-chart-empty">暂无镜头参考数据</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < scenes.length; i += 1) {
      var item = scenes[i];
      var activeCls = (i === state.filmSelectedKeyframe) ? ' active' : '';
      h += '<div class="cp-film-thumb' + activeCls + '" onclick="ComputePlatform.selectFilmKeyframe(' + i + ')" data-kf="' + i + '">' +
        '<img loading="lazy" decoding="async" src="' + escapeHtml(resolveSceneImage(item, i)) +
        '" alt="' + escapeHtml(item.title || '') + '" ' + imageFallbackAttr() + ' />' +
        '<div class="cp-film-thumb-title">' + escapeHtml(item.title || '') + '</div>' +
        '<div class="cp-film-thumb-time">' + escapeHtml(String(item.durationSec || '—')) + 's</div>' +
        '</div>';
    }
    strip.innerHTML = h;
  }

  function updateFilmInfo(index) {
    var scenes = getFilmScenes();
    var item = scenes[index];
    if (!item) return;

    var titleEl = document.getElementById('cp-film-shot-title');
    var descEl = document.getElementById('cp-film-shot-desc');
    var lensEl = document.getElementById('cp-film-lens');
    var durEl = document.getElementById('cp-film-dur');
    var frameEl = document.getElementById('cp-film-frame');
    if (titleEl) titleEl.textContent = item.title || '未命名镜头';
    if (descEl) descEl.textContent = item.description || '';
    if (lensEl) lensEl.textContent = item.lens || '—';
    if (durEl) durEl.textContent = (item.durationSec || '—') + '秒';
    if (frameEl) frameEl.textContent = (index + 1) + ' / ' + scenes.length;
  }

  function selectFilmKeyframe(index) {
    var scenes = getFilmScenes();
    if (index < 0 || index >= scenes.length) return;
    state.filmSelectedKeyframe = index;
    updateFilmInfo(index);
    renderFilmKeyframes();
    renderFilmShowcase(index);
    var thumb = document.querySelector('.cp-film-thumb[data-kf="' + index + '"]');
    if (thumb) {
      thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }

  function prevFilmKeyframe() {
    var scenes = getFilmScenes();
    if (!scenes.length) return;
    var idx = state.filmSelectedKeyframe - 1;
    if (idx < 0) idx = scenes.length - 1;
    selectFilmKeyframe(idx);
  }

  function nextFilmKeyframe() {
    var scenes = getFilmScenes();
    if (!scenes.length) return;
    var idx = state.filmSelectedKeyframe + 1;
    if (idx >= scenes.length) idx = 0;
    selectFilmKeyframe(idx);
  }

  function toggleFilmAutoplay() {
    var btn = document.getElementById('cp-film-autoplay-btn');
    if (state.filmAutoplayInterval) {
      clearInterval(state.filmAutoplayInterval);
      state.filmAutoplayInterval = null;
      if (btn) { btn.classList.remove('autoplay-active'); btn.textContent = '自动轮播'; }
    } else {
      state.filmAutoplayInterval = setInterval(function() {
        nextFilmKeyframe();
      }, 3000);
      if (btn) { btn.classList.add('autoplay-active'); btn.textContent = '停止轮播'; }
    }
  }

  function cleanupFilmResources() {
    if (state.filmInitTimeout) {
      clearTimeout(state.filmInitTimeout);
      state.filmInitTimeout = null;
    }
    // Stop autoplay
    if (state.filmAutoplayInterval) {
      clearInterval(state.filmAutoplayInterval);
      state.filmAutoplayInterval = null;
      var btn = document.getElementById('cp-film-autoplay-btn');
      if (btn) { btn.classList.remove('autoplay-active'); btn.textContent = '自动轮播'; }
    }
    // Stop animation
    if (state.filmAnimFrameId) {
      cancelAnimationFrame(state.filmAnimFrameId);
      state.filmAnimFrameId = null;
    }
    // Dispose scene
    if (state.filmThreeScene) {
      disposeThreeScene(state.filmThreeScene);
      state.filmThreeScene = null;
    }
    // Remove renderer
    if (state.filmThreeRenderer) {
      var viewer = document.getElementById('cp-film-viewer');
      if (viewer && state.filmThreeRenderer.domElement && state.filmThreeRenderer.domElement.parentNode) {
        state.filmThreeRenderer.domElement.parentNode.removeChild(state.filmThreeRenderer.domElement);
      }
      state.filmThreeRenderer.dispose();
      state.filmThreeRenderer = null;
    }
    state.filmOrbitControls = null;
    state.filmSelectedKeyframe = 0;
    // Show placeholder again
    var placeholder = document.getElementById('cp-film-placeholder');
    if (placeholder) placeholder.style.display = 'block';
  }

  // ── Helper: dispose Three.js scene recursively ──
  function disposeThreeScene(scene) {
    if (!scene) return;
    scene.traverse(function(obj) {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) {
          for (var m = 0; m < obj.material.length; m++) {
            disposeMaterial(obj.material[m]);
          }
        } else {
          disposeMaterial(obj.material);
        }
      }
    });
    while (scene.children.length > 0) {
      scene.remove(scene.children[0]);
    }
  }

  function disposeMaterial(mat) {
    if (!mat) return;
    for (var key in mat) {
      if (mat[key] && mat[key].isTexture) {
        mat[key].dispose();
      }
    }
    mat.dispose();
  }

  // ══════════════════════════════════════════════════
  // Sub-Tab: 建筑与工业 (Architecture & Industrial)
  // ══════════════════════════════════════════════════
  function renderArchitectureSubTab() {
    var placeholder = document.getElementById('cp-arch-placeholder');
    if (!scenarioMode()) {
      if (placeholder) {
        placeholder.textContent = '建筑/工业渲染未接入实时渲染数据';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';
    renderArchShowcase();
    if (state.archThreeScene) {
      renderArchPresets();
      renderArchEffectImages();
      applyArchMaterial(state.archSelectedMaterial);
      applyArchLighting(state.archSelectedLighting);
      if (!state.archAnimFrameId) animateArchScene();
      return;
    }
    if (state.archInitTimeout) clearTimeout(state.archInitTimeout);
    state.archInitTimeout = setTimeout(function() {
      state.archInitTimeout = null;
      initArchScene();
      applyArchMaterial(state.archSelectedMaterial);
      applyArchLighting(state.archSelectedLighting);
      renderArchPresets();
      renderArchEffectImages();
      animateArchScene();
    }, 50);
  }

  function renderArchShowcase() {
    var container = document.getElementById('cp-arch-showcase');
    if (!container) return;
    var scenes = getArchScenes();
    if (!scenes.length) {
      container.innerHTML = '';
      return;
    }
    var item = scenes[state.archShowcaseIndex] || scenes[0];
    var before = resolveSceneImage({ image: item.before }, state.archShowcaseIndex);
    var after = resolveSceneImage({ image: item.after }, state.archShowcaseIndex + 1);
    var compare = state.archComparePct;
    var thumbs = '';
    for (var i = 0; i < scenes.length; i += 1) {
      thumbs += '<button type="button" class="cp-arch-showcase-thumb' +
        (i === state.archShowcaseIndex ? ' active' : '') +
        '" onclick="ComputePlatform.selectArchScene(' + i + ')">' +
        escapeHtml(scenes[i].title) + '</button>';
    }
    container.innerHTML = '<div class="cp-arch-showcase-head">' +
      '<div class="cp-arch-showcase-title">' + escapeHtml(item.title || '建筑场景') + '</div>' +
      '<div class="cp-arch-showcase-thumbs">' + thumbs + '</div></div>' +
      '<div class="cp-arch-compare" style="--compare:' + compare + '%">' +
      '<img class="cp-arch-compare-before" loading="lazy" decoding="async" src="' + escapeHtml(before) +
      '" alt="' + escapeHtml(item.title || '') + ' 白模/线框" ' + imageFallbackAttr() + ' />' +
      '<div class="cp-arch-compare-after-wrap"><img class="cp-arch-compare-after" loading="lazy" decoding="async" src="' +
      escapeHtml(after) + '" alt="' + escapeHtml(item.title || '') + ' 渲染效果" ' + imageFallbackAttr() + ' /></div>' +
      '<input type="range" min="0" max="100" value="' + compare +
      '" class="cp-arch-compare-range" oninput="ComputePlatform.handleArchCompare(this.value)" aria-label="渲染前后对比" />' +
      '</div>' +
      '<div class="cp-arch-showcase-desc">' + escapeHtml(item.description || '') + '</div>' +
      '<div class="cp-arch-showcase-grid">' +
      '<div><span>材质方案</span><strong>' + escapeHtml(item.material || '—') + '</strong></div>' +
      '<div><span>光照方案</span><strong>' + escapeHtml(item.lighting || '—') + '</strong></div>' +
      '<div><span>渲染配置</span><strong>' + escapeHtml(item.config || '—') + '</strong></div>' +
      '</div>';
  }

  function selectArchScene(index) {
    var scenes = getArchScenes();
    if (index < 0 || index >= scenes.length) return;
    state.archShowcaseIndex = index;
    state.archComparePct = 50;
    renderArchShowcase();
  }

  function handleArchCompare(value) {
    state.archComparePct = Math.max(0, Math.min(100, parseInt(value, 10) || 0));
    var compare = document.querySelector('.cp-arch-compare');
    if (compare) compare.style.setProperty('--compare', state.archComparePct + '%');
  }

  function getArchMaterialPresets() {
    var d = state.demoData || {};
    if (d.archMaterialPresets && d.archMaterialPresets.length) {
      return d.archMaterialPresets;
    }
    return [
      { id: 'arch-mat-stone', name: '哑光石材', roughness: 0.82, metalness: 0.05, color: '#b39e7b', description: '暖灰色哑光石材' },
      { id: 'arch-mat-metal', name: '拉丝金属', roughness: 0.35, metalness: 0.75, color: '#7d8b93', description: '冷色拉丝金属' },
      { id: 'arch-mat-wood', name: '木饰面', roughness: 0.68, metalness: 0.02, color: '#8d6642', description: '暖色木饰面' }
    ];
  }

  function getArchLightingPresets() {
    var d = state.demoData || {};
    if (d.archLightingPresets && d.archLightingPresets.length) {
      return d.archLightingPresets;
    }
    return [
      { id: 'arch-lit-warm', name: '暖色展厅光', ambientColor: '#ffd9a0', ambientIntensity: 0.55, sunColor: '#fff0c9', sunIntensity: 1.1, sunPos: [10, 15, 5], bgColor: '#1a1510', description: '暖色展厅照明' },
      { id: 'arch-lit-day', name: '日光天窗', ambientColor: '#cfe8ef', ambientIntensity: 0.5, sunColor: '#fffde8', sunIntensity: 1.2, sunPos: [8, 18, 6], bgColor: '#1a2430', description: '冷色日光补光' },
      { id: 'arch-lit-night', name: '夜间展陈', ambientColor: '#8fa2c8', ambientIntensity: 0.35, sunColor: '#d7e8ff', sunIntensity: 0.7, sunPos: [6, 12, 8], bgColor: '#0b1018', description: '低照度夜间展陈' }
    ];
  }

  function initArchScene() {
    if (state.archThreeScene) return;
    var viewer = document.getElementById('cp-arch-viewer');
    if (!viewer) return;
    if (!isThreeAvailable() || !isWebGLAvailable()) {
      var unsupported = document.getElementById('cp-arch-placeholder');
      if (unsupported) {
        unsupported.textContent = '当前环境不支持 WebGL 3D 预览，参考画面仍可浏览';
        unsupported.style.display = 'block';
      }
      return;
    }
    var w = viewer.clientWidth;
    var h = viewer.clientHeight;
    if (w <= 0 || h <= 0) return;

    // Scene
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87ceeb);
    state.archThreeScene = scene;

    // Camera
    var camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(5, 4, 7);
    camera.lookAt(0, 1, 0);

    // Renderer
    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.__archCam = camera;
    viewer.appendChild(renderer.domElement);
    state.archThreeRenderer = renderer;

    // OrbitControls
    if (typeof THREE.OrbitControls === 'function') {
      var controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.minDistance = 3;
      controls.maxDistance = 20;
      controls.target.set(0, 1, 0);
      state.archThreeScene.__controls = controls;
    }

    // Grid helper
    var grid = new THREE.GridHelper(12, 12, 0x444444, 0x222222);
    scene.add(grid);

    // Build building model
    var boxGeo = new THREE.BoxGeometry(2, 2.5, 2);
    var boxMat = new THREE.MeshStandardMaterial({ color: 0xd4c5a9, roughness: 0.8, metalness: 0.0 });
    var box = new THREE.Mesh(boxGeo, boxMat);
    box.position.set(0, 1.25, 0);
    box.castShadow = true;
    box.receiveShadow = true;
    scene.add(box);
    state.archModelMesh = box;

    // Roof
    var roofGeo = new THREE.ConeGeometry(1.5, 0.8, 4);
    var roofMat = new THREE.MeshStandardMaterial({ color: 0x8b4513, roughness: 0.5, metalness: 0.0 });
    var roof = new THREE.Mesh(roofGeo, roofMat);
    roof.position.set(0, 2.9, 0);
    roof.rotation.y = Math.PI / 4;
    roof.castShadow = true;
    scene.add(roof);
    state.archThreeScene.__roof = roof;

    // Pillars
    var pillarGeo = new THREE.CylinderGeometry(0.12, 0.12, 2.5, 16);
    var pillarMat = new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 0.4, metalness: 0.3 });
    var pillarPositions = [
      [-0.8, 1.25, -0.8], [0.8, 1.25, -0.8], [-0.8, 1.25, 0.8], [0.8, 1.25, 0.8],
      [-0.8, 1.25, 0], [0.8, 1.25, 0]
    ];
    for (var p = 0; p < pillarPositions.length; p++) {
      var pillar = new THREE.Mesh(pillarGeo, pillarMat);
      pillar.position.set(pillarPositions[p][0], pillarPositions[p][1], pillarPositions[p][2]);
      pillar.castShadow = true;
      pillar.receiveShadow = true;
      scene.add(pillar);
    }
    scene.__pillars = pillarPositions.length;

    // Initial lights
    var ambient = new THREE.AmbientLight(0xffffff, 0.4);
    ambient.name = 'archAmbient';
    scene.add(ambient);

    var sun = new THREE.DirectionalLight(0xfffde8, 1.0);
    sun.position.set(10, 15, 5);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 1024;
    sun.shadow.mapSize.height = 1024;
    sun.shadow.camera.near = 0.5;
    sun.shadow.camera.far = 50;
    sun.shadow.camera.left = -10;
    sun.shadow.camera.right = 10;
    sun.shadow.camera.top = 10;
    sun.shadow.camera.bottom = -10;
    sun.name = 'archSun';
    scene.add(sun);

    // Hide placeholder
    var placeholder = document.getElementById('cp-arch-placeholder');
    if (placeholder) placeholder.style.display = 'none';
  }

  function renderArchPresets() {
    var container = document.getElementById('cp-arch-presets');
    if (!container) return;

    var materials = getArchMaterialPresets();
    var lightings = getArchLightingPresets();

    var h = '<div class="cp-arch-preset-group">' +
            '<div class="cp-arch-preset-group-label">材质预设</div>' +
            '<div class="cp-arch-preset-grid">';
    for (var i = 0; i < materials.length; i++) {
      var active = (materials[i].id === state.archSelectedMaterial) ? ' active' : '';
      h += '<button class="cp-arch-preset-btn' + active + '" onclick="ComputePlatform.applyArchMaterial(\'' + escapeHtml(materials[i].id) + '\')" title="' + escapeHtml(materials[i].description) + '">' + escapeHtml(materials[i].name) + '</button>';
    }
    h += '</div></div>' +
         '<div class="cp-arch-preset-group">' +
         '<div class="cp-arch-preset-group-label">光照预设</div>' +
         '<div class="cp-arch-preset-grid">';
    for (var j = 0; j < lightings.length; j++) {
      var active2 = (lightings[j].id === state.archSelectedLighting) ? ' active' : '';
      h += '<button class="cp-arch-preset-btn' + active2 + '" onclick="ComputePlatform.applyArchLighting(\'' + escapeHtml(lightings[j].id) + '\')" title="' + escapeHtml(lightings[j].description) + '">' + escapeHtml(lightings[j].name) + '</button>';
    }
    h += '</div></div>';
    container.innerHTML = h;
  }

  function applyArchMaterial(presetId) {
    state.archSelectedMaterial = presetId;
    if (!state.archModelMesh) { renderArchPresets(); return; }

    var preset = null;
    var materials = getArchMaterialPresets();
    for (var i = 0; i < materials.length; i++) {
      if (materials[i].id === presetId) { preset = materials[i]; break; }
    }
    if (!preset) { renderArchPresets(); return; }

    var mat = state.archModelMesh.material;
    mat.roughness = preset.roughness;
    mat.metalness = preset.metalness;
    mat.color.set(preset.color);

    // Update roof material too
    if (state.archThreeScene && state.archThreeScene.__roof) {
      var roofMat = state.archThreeScene.__roof.material;
      roofMat.roughness = preset.roughness;
      roofMat.metalness = preset.metalness;
    }

    renderArchPresets();
    showToast('材质已切换: ' + preset.name, 'info');
  }

  function applyArchLighting(presetId) {
    state.archSelectedLighting = presetId;
    var preset = null;
    var lightings = getArchLightingPresets();
    for (var i = 0; i < lightings.length; i++) {
      if (lightings[i].id === presetId) { preset = lightings[i]; break; }
    }
    if (!preset) { renderArchPresets(); return; }

    var scene = state.archThreeScene;
    if (!scene) { renderArchPresets(); return; }

    // Find lights by name
    scene.traverse(function(obj) {
      if (obj.isAmbientLight && obj.name === 'archAmbient') {
        obj.color.set(preset.ambientColor);
        obj.intensity = preset.ambientIntensity;
      }
      if (obj.isDirectionalLight && obj.name === 'archSun') {
        obj.color.set(preset.sunColor);
        obj.intensity = preset.sunIntensity;
        obj.position.set(preset.sunPos[0], preset.sunPos[1], preset.sunPos[2]);
      }
    });
    scene.background = new THREE.Color(preset.bgColor);

    renderArchPresets();
    showToast('光照已切换: ' + preset.name, 'info');
  }

  function animateArchScene() {
    if (!state.archThreeScene || !state.archThreeRenderer) {
      state.archAnimFrameId = null;
      return;
    }
    state.archAnimFrameId = requestAnimationFrame(animateArchScene);

    if (state.archThreeScene.__controls) state.archThreeScene.__controls.update();
    state.archThreeRenderer.render(state.archThreeScene, state.archThreeRenderer.domElement.__archCam);
  }

  function submitArchRenderTask() {
    if (!scenarioMode()) {
      showToast('当前环境未接入云渲染任务接口', 'warning');
      return;
    }
    if (state.archTaskRunning) return;
    state.archTaskRunning = true;

    var btn = document.getElementById('cp-arch-render-btn');
    var info = document.getElementById('cp-arch-task-info');
    var bar = document.getElementById('cp-arch-progress-bar');
    var label = document.getElementById('cp-arch-progress-label');
    if (btn) { btn.disabled = true; btn.textContent = '渲染中…'; }

    var steps = [
      { pct: 15, info: '正在校验模型几何体…' },
      { pct: 30, info: 'GPU 节点分配中: local-rtx4090-01' },
      { pct: 50, info: '渲染资源上传中…' },
      { pct: 72, info: 'Blender Cycles 正在渲染…' },
      { pct: 90, info: '合成输出帧，生成最终图像…' },
      { pct: 100, info: '渲染流程完成' }
    ];

    var stepIndex = 0;
    function runStep() {
      if (stepIndex >= steps.length) {
        state.archTaskRunning = false;
        state.archTaskTimers = [];
        if (btn) { btn.disabled = false; btn.textContent = '提交云渲染任务'; }
        showToast('云渲染任务流程已完成', 'success');
        return;
      }
      var s = steps[stepIndex];
      if (bar) bar.style.width = s.pct + '%';
      if (info) info.textContent = s.info;
      if (label) label.textContent = s.pct + '%';
      stepIndex++;
      state.archTaskTimers.push(setTimeout(runStep, 1000));
    }
    runStep();
  }

  function renderArchEffectImages() {
    var grid = document.getElementById('cp-arch-effect-grid');
    if (!grid) return;
    var scenes = getArchScenes();
    if (!scenes.length) {
      grid.innerHTML = '<div class="cp-chart-empty">暂无建筑渲染参考场景</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < scenes.length; i += 1) {
      var item = scenes[i];
      h += '<div class="cp-arch-effect-item' + (i === state.archShowcaseIndex ? ' active' : '') +
        '" onclick="ComputePlatform.selectArchScene(' + i + ')">' +
        '<img class="cp-arch-effect-image" loading="lazy" decoding="async" src="' +
        escapeHtml(resolveSceneImage({ image: item.after }, i)) + '" alt="' +
        escapeHtml(item.title || '') + '" ' + imageFallbackAttr() + ' />' +
        '<div class="cp-arch-effect-label">' + escapeHtml(item.title || '') + '</div>' +
        '</div>';
    }
    grid.innerHTML = h;
  }

  function cleanupArchitectureResources() {
    if (state.archInitTimeout) {
      clearTimeout(state.archInitTimeout);
      state.archInitTimeout = null;
    }
    for (var t = 0; t < state.archTaskTimers.length; t += 1) {
      clearTimeout(state.archTaskTimers[t]);
    }
    state.archTaskTimers = [];
    for (var u = 0; u < state.archThumbTimers.length; u += 1) {
      clearTimeout(state.archThumbTimers[u]);
    }
    state.archThumbTimers = [];
    if (state.archAnimFrameId) {
      cancelAnimationFrame(state.archAnimFrameId);
      state.archAnimFrameId = null;
    }
    if (state.archThreeScene) {
      disposeThreeScene(state.archThreeScene);
      state.archThreeScene = null;
    }
    if (state.archThreeRenderer) {
      var viewer = document.getElementById('cp-arch-viewer');
      if (viewer && state.archThreeRenderer.domElement && state.archThreeRenderer.domElement.parentNode) {
        state.archThreeRenderer.domElement.parentNode.removeChild(state.archThreeRenderer.domElement);
      }
      state.archThreeRenderer.dispose();
      state.archThreeRenderer = null;
    }
    state.archModelMesh = null;
    state.archTaskRunning = false;
    var btn = document.getElementById('cp-arch-render-btn');
    if (btn) { btn.disabled = false; btn.textContent = '提交云渲染任务'; }
    var bar = document.getElementById('cp-arch-progress-bar');
    if (bar) bar.style.width = '0%';
    var info = document.getElementById('cp-arch-task-info');
    if (info) info.textContent = '准备就绪，点击提交将模拟云渲染任务流程';
    var label = document.getElementById('cp-arch-progress-label');
    if (label) label.textContent = '';
    var placeholder = document.getElementById('cp-arch-placeholder');
    if (placeholder) placeholder.style.display = 'block';
  }

  // ══════════════════════════════════════════════════
  // Sub-Tab: 云游戏互动 (Cloud Gaming & Interactive)
  // ══════════════════════════════════════════════════
  function renderGamingSubTab() {
    var placeholder = document.getElementById('cp-game-placeholder');
    if (!scenarioMode()) {
      if (placeholder) {
        placeholder.textContent = '云游戏互动未接入实时串流数据';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';
    renderGameShowcase();
    if (state.gameThreeScene) {
      renderGameMetrics();
      if (!state.gameAnimFrameId) animateGameScene();
      return;
    }
    if (state.gameInitTimeout) clearTimeout(state.gameInitTimeout);
    state.gameInitTimeout = setTimeout(function() {
      state.gameInitTimeout = null;
      initGameScene();
      buildGameRoom();
      renderGameMetrics();
      setupGameTouchControls();
      bindGameKeyboard();
      animateGameScene();
    }, 50);
  }

  function renderGameShowcase() {
    var container = document.getElementById('cp-game-showcase');
    if (!container) return;
    var gaming = getGamingScene();
    if (!gaming || !gaming.image) {
      container.innerHTML = '';
      return;
    }
    var gameStatusLabel = gaming.status === 'connected'
      ? '已连接' : (gaming.status === 'disconnected' ? '已断开' : (gaming.status || '—'));
    container.innerHTML = '<div class="cp-game-showcase-card">' +
      '<div class="cp-game-showcase-media"><img loading="lazy" decoding="async" src="' +
      escapeHtml(resolveSceneImage(gaming, 0)) + '" alt="' +
      escapeHtml(gaming.title || '云游戏场景') + '" ' + imageFallbackAttr() + ' />' +
      '<span class="cp-game-showcase-status">' + escapeHtml(gameStatusLabel) + '</span></div>' +
      '<div class="cp-game-showcase-info"><div class="cp-film-reference-title">' +
      escapeHtml(gaming.title || '虚拟展厅漫游') + '</div>' +
      '<div class="cp-film-reference-desc">WASD 移动，鼠标拖拽观察；画面指标来自同一参考场景。</div>' +
      '<div class="cp-film-reference-grid">' +
      '<div><span>FPS</span><strong>' + valueOrDash(gaming.fps) + '</strong></div>' +
      '<div><span>时延</span><strong>' + valueOrDash(gaming.latencyMs, ' ms') + '</strong></div>' +
      '<div><span>码率</span><strong>' + valueOrDash(gaming.bitrateMbps, ' Mbps') + '</strong></div>' +
      '<div><span>丢包</span><strong>' + valueOrDash(gaming.packetLossPct, '%') + '</strong></div>' +
      '<div><span>数据传输</span><strong>' + escapeHtml(gaming.dataTransfer || '—') + '</strong></div>' +
      '</div></div></div>';
  }

  function initGameScene() {
    if (state.gameThreeScene) return;
    var viewer = document.getElementById('cp-game-viewer');
    if (!viewer) return;
    if (!isThreeAvailable() || !isWebGLAvailable()) {
      var unsupported = document.getElementById('cp-game-placeholder');
      if (unsupported) {
        unsupported.textContent = '当前环境不支持 WebGL 3D 预览，场景画面仍可浏览';
        unsupported.style.display = 'block';
      }
      return;
    }
    var w = viewer.clientWidth;
    var h = viewer.clientHeight;
    if (w <= 0 || h <= 0) return;

    // Scene
    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);
    scene.fog = new THREE.Fog(0x1a1a2e, 10, 35);
    state.gameThreeScene = scene;

    // Camera (FPS-style)
    var camera = new THREE.PerspectiveCamera(70, w / h, 0.1, 100);
    camera.position.set(state.gamePlayerPos.x, state.gamePlayerPos.y, state.gamePlayerPos.z);
    scene.__gameCam = camera;

    // Renderer
    var renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.__gameCam = camera;
    viewer.appendChild(renderer.domElement);
    state.gameThreeRenderer = renderer;

    // Lights
    var ambient = new THREE.AmbientLight(0x334466, 0.5);
    scene.add(ambient);

    var ceiling = new THREE.PointLight(0xffeedd, 0.8, 20);
    ceiling.position.set(0, 5.5, 0);
    scene.add(ceiling);

    // Hide placeholder
    var placeholder = document.getElementById('cp-game-placeholder');
    if (placeholder) placeholder.style.display = 'none';
  }

  function buildGameRoom() {
    var scene = state.gameThreeScene;
    if (!scene) return;

    // Floor
    var floorGeo = new THREE.PlaneGeometry(24, 24);
    var floorMat = new THREE.MeshStandardMaterial({ color: 0x221c18, roughness: 0.9, metalness: 0.0 });
    var floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0;
    floor.receiveShadow = true;
    scene.add(floor);

    // Grid on floor
    var floorGrid = new THREE.GridHelper(24, 24, 0x444444, 0x333333);
    floorGrid.position.y = 0.01;
    scene.add(floorGrid);

    // Walls (4 walls, semi-transparent)
    var wallMat = new THREE.MeshStandardMaterial({ color: 0x2a2a3e, roughness: 0.7, metalness: 0.1, transparent: true, opacity: 0.6 });
    var wallConfigs = [
      { w: 24, h: 6, x: 0, y: 3, z: -12, ry: 0 },
      { w: 24, h: 6, x: 0, y: 3, z: 12, ry: 0 },
      { w: 24, h: 6, x: -12, y: 3, z: 0, ry: Math.PI / 2 },
      { w: 24, h: 6, x: 12, y: 3, z: 0, ry: Math.PI / 2 }
    ];
    for (var w = 0; w < wallConfigs.length; w++) {
      var cfg = wallConfigs[w];
      var wallGeo = new THREE.PlaneGeometry(cfg.w, cfg.h);
      var wall = new THREE.Mesh(wallGeo, wallMat);
      wall.position.set(cfg.x, cfg.y, cfg.z);
      wall.rotation.y = cfg.ry;
      wall.receiveShadow = true;
      scene.add(wall);
    }

    // Ceiling
    var ceilGeo = new THREE.PlaneGeometry(24, 24);
    var ceilMat = new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0.8, metalness: 0.0 });
    var ceil = new THREE.Mesh(ceilGeo, ceilMat);
    ceil.rotation.x = Math.PI / 2;
    ceil.position.y = 6;
    scene.add(ceil);

    // Exhibits
    var d = state.demoData || {};
    var exhibits = d.gameExhibits && d.gameExhibits.length ? d.gameExhibits : [
      { id: 'exh-showcase-1', name: '数字编钟', color: '#d7a84f', shape: 'cylinder', pos: [-3, 0, -2] },
      { id: 'exh-showcase-2', name: '光影装置', color: '#78bfd2', shape: 'torus', pos: [0, 0, -4] },
      { id: 'exh-showcase-3', name: '城市模型', color: '#c9876e', shape: 'box', pos: [3, 0, -2] },
      { id: 'exh-showcase-4', name: '沉浸式屏幕', color: '#8f84df', shape: 'icosahedron', pos: [0, 0, 2] }
    ];
    state.gameExhibitMeshes = [];

    var shapeMap = {
      cylinder: function() { return new THREE.CylinderGeometry(0.5, 0.5, 1.2, 16); },
      box: function() { return new THREE.BoxGeometry(0.7, 0.7, 0.7); },
      torus: function() { return new THREE.TorusGeometry(0.5, 0.2, 16, 16); },
      cone: function() { return new THREE.ConeGeometry(0.5, 1, 16); },
      dodecahedron: function() { return new THREE.DodecahedronGeometry(0.5); },
      icosahedron: function() { return new THREE.IcosahedronGeometry(0.5); }
    };

    for (var e = 0; e < exhibits.length; e++) {
      var exh = exhibits[e];
      var geoFactory = shapeMap[exh.shape] || shapeMap.box;
      var geo = geoFactory();
      var mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(exh.color), roughness: 0.4, metalness: 0.4 });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(exh.pos[0], 0.6, exh.pos[2]);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.__exhId = exh.id;
      mesh.__exhName = exh.name;
      mesh.__exhColor = exh.color;
      // Rotating animation for each exhibit
      mesh.__exhRotSpeed = 0.3 + (e % 4) * 0.12;

      scene.add(mesh);
      state.gameExhibitMeshes.push(mesh);

      // Pedestal
      var pedestalGeo = new THREE.CylinderGeometry(0.3, 0.35, 0.15, 16);
      var pedestalMat = new THREE.MeshStandardMaterial({ color: 0x333333, roughness: 0.6, metalness: 0.5 });
      var ped = new THREE.Mesh(pedestalGeo, pedestalMat);
      ped.position.set(exh.pos[0], 0.05, exh.pos[2]);
      ped.receiveShadow = true;
      scene.add(ped);
    }
  }

  function animateGameScene() {
    if (!state.gameThreeScene || !state.gameThreeRenderer) {
      state.gameAnimFrameId = null;
      return;
    }
    state.gameAnimFrameId = requestAnimationFrame(animateGameScene);

    updateGamePlayerPosition();

    // Animate exhibits
    var exh = state.gameExhibitMeshes;
    for (var i = 0; i < exh.length; i++) {
      exh[i].rotation.y += 0.005 * exh[i].__exhRotSpeed;
      exh[i].position.y = 0.6 + Math.sin(Date.now() * 0.002 + i) * 0.1;
    }

    var cam = state.gameThreeScene.__gameCam;
    state.gameThreeRenderer.render(state.gameThreeScene, cam);
  }

  function updateGamePlayerPosition() {
    var keys = state.gameKeysPressed;
    var moveSpeed = 0.08;
    var newX = state.gamePlayerPos.x;
    var newZ = state.gamePlayerPos.z;

    if (keys['w'] || keys['arrowup'])    newZ -= moveSpeed;
    if (keys['s'] || keys['arrowdown'])  newZ += moveSpeed;
    if (keys['a'] || keys['arrowleft'])  newX -= moveSpeed;
    if (keys['d'] || keys['arrowright']) newX += moveSpeed;

    // Boundary check (room is 24x24, walls at ±12)
    var bound = 11.2;
    newX = Math.max(-bound, Math.min(bound, newX));
    newZ = Math.max(-bound, Math.min(bound, newZ));

    state.gamePlayerPos.x = newX;
    state.gamePlayerPos.z = newZ;

    var cam = state.gameThreeScene ? state.gameThreeScene.__gameCam : null;
    if (cam) {
      cam.position.set(newX, state.gamePlayerPos.y, newZ);
      cam.lookAt(newX, 1.5, newZ - 3);
    }
  }

  function handleGameKeyDown(e) {
    if (state.renderSubTab !== 'gaming' || state.activeTab !== 'rendering') return;
    var key = e.key.toLowerCase();
    state.gameKeysPressed[key] = true;
    // Prevent page scrolling for game keys
    if (key === 'w' || key === 'a' || key === 's' || key === 'd' || key === 'arrowup' || key === 'arrowdown' || key === 'arrowleft' || key === 'arrowright') {
      e.preventDefault();
    }
  }

  function handleGameKeyUp(e) {
    if (state.renderSubTab !== 'gaming' || state.activeTab !== 'rendering') return;
    var key = e.key.toLowerCase();
    state.gameKeysPressed[key] = false;
  }

  function bindGameKeyboard() {
    document.addEventListener('keydown', handleGameKeyDown);
    document.addEventListener('keyup', handleGameKeyUp);
  }

  function unbindGameKeyboard() {
    document.removeEventListener('keydown', handleGameKeyDown);
    document.removeEventListener('keyup', handleGameKeyUp);
    state.gameKeysPressed = {};
  }

  function setupGameTouchControls() {
    var dpad = document.getElementById('cp-game-dpad');
    if (!dpad) return;
    if (state.gameDpadAbort) {
      state.gameDpadAbort.abort();
      state.gameDpadAbort = null;
    }
    state.gameDpadAbort = typeof AbortController === 'function'
      ? new AbortController() : null;
    var options = state.gameDpadAbort
      ? { signal: state.gameDpadAbort.signal } : false;

    function dirFor(button) {
      if (button.classList.contains('dpad-up')) return 'w';
      if (button.classList.contains('dpad-down')) return 's';
      if (button.classList.contains('dpad-left')) return 'a';
      if (button.classList.contains('dpad-right')) return 'd';
      return '';
    }
    function setDir(button, pressed) {
      var dir = dirFor(button);
      if (dir) state.gameKeysPressed[dir] = pressed;
    }

    var buttons = dpad.querySelectorAll('.cp-game-dpad-btn');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].addEventListener('touchstart', function(e) {
        e.preventDefault();
        setDir(this, true);
      }, options);
      buttons[i].addEventListener('touchend', function(e) {
        e.preventDefault();
        setDir(this, false);
      }, options);
      buttons[i].addEventListener('mousedown', function() {
        setDir(this, true);
      }, options);
      buttons[i].addEventListener('mouseup', function() {
        setDir(this, false);
      }, options);
      buttons[i].addEventListener('mouseleave', function() {
        setDir(this, false);
      }, options);
    }
  }

  function renderGameMetrics() {
    var container = document.getElementById('cp-game-metrics');
    if (!container) return;
    var gaming = getGamingScene();
    container.innerHTML =
      '<div class="cp-game-metric"><div class="cp-game-metric-value">' +
      valueOrDash(gaming.latencyMs) + '</div><div class="cp-game-metric-label">延迟 (ms)</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">' +
      valueOrDash(gaming.fps) + '</div><div class="cp-game-metric-label">FPS</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">' +
      valueOrDash(gaming.bitrateMbps) + '</div><div class="cp-game-metric-label">码率 (Mbps)</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">' +
      escapeHtml(gaming.dataTransfer || '—') + '</div><div class="cp-game-metric-label">数据传输</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">' +
      valueOrDash(gaming.packetLossPct, '%') + '</div><div class="cp-game-metric-label">丢包率</div></div>';
  }

  function startGameNetworkSimulation() {
    stopGameNetworkSimulation();
    state.gameNetworkInterval = setInterval(function() {
      if (state.renderSubTab !== 'gaming' || state.activeTab !== 'rendering') return;
      renderGameMetrics();
    }, 1500);
  }

  function stopGameNetworkSimulation() {
    if (state.gameNetworkInterval) {
      clearInterval(state.gameNetworkInterval);
      state.gameNetworkInterval = null;
    }
  }

  function toggleGameConnection() {
    state.gameConnected = !state.gameConnected;
    var overlay = document.getElementById('cp-game-overlay');
    var btn = document.getElementById('cp-game-connect-btn');

    if (!state.gameConnected) {
      if (overlay) overlay.classList.add('visible');
      if (btn) btn.textContent = '重新连接';
      showToast('连接已断开', 'warning');
    } else {
      if (overlay) overlay.classList.remove('visible');
      if (btn) btn.textContent = '断开连接';
      showToast('已重新连接', 'success');
    }
  }

  function toggleGameFullscreen() {
    var viewer = document.getElementById('cp-game-viewer');
    if (!viewer) return;
    if (!document.fullscreenElement) {
      viewer.requestFullscreen().catch(function() {
        showToast('全屏功能不可用', 'error');
      });
    } else {
      document.exitFullscreen();
    }
  }

  function simulateGameNetworkMetrics() {
    return {
      latency: 0,
      fps: 0,
      bitrate: 0,
      packetLoss: 0
    };
  }

  function cleanupGamingResources() {
    if (state.gameInitTimeout) {
      clearTimeout(state.gameInitTimeout);
      state.gameInitTimeout = null;
    }
    if (state.gameDpadAbort) {
      state.gameDpadAbort.abort();
      state.gameDpadAbort = null;
    }
    if (state.gameAnimFrameId) {
      cancelAnimationFrame(state.gameAnimFrameId);
      state.gameAnimFrameId = null;
    }
    stopGameNetworkSimulation();
    unbindGameKeyboard();
    state.gameKeysPressed = {};
    state.gameExhibitMeshes = [];
    if (state.gameThreeScene) {
      disposeThreeScene(state.gameThreeScene);
      state.gameThreeScene = null;
    }
    if (state.gameThreeRenderer) {
      var viewer = document.getElementById('cp-game-viewer');
      if (viewer && state.gameThreeRenderer.domElement && state.gameThreeRenderer.domElement.parentNode) {
        state.gameThreeRenderer.domElement.parentNode.removeChild(state.gameThreeRenderer.domElement);
      }
      state.gameThreeRenderer.dispose();
      state.gameThreeRenderer = null;
    }
    state.gamePlayerPos = { x: 0, y: 1.6, z: 0 };
    state.gameConnected = true;
    var overlay = document.getElementById('cp-game-overlay');
    var btn = document.getElementById('cp-game-connect-btn');
    if (overlay) overlay.classList.remove('visible');
    if (btn) btn.textContent = '断开连接';
    var placeholder = document.getElementById('cp-game-placeholder');
    if (placeholder) placeholder.style.display = 'block';
  }

  // ══════════════════════════════════════════════════
  // Sub-Tab: 渲染会话 (Sessions)
  // ══════════════════════════════════════════════════
  var SESSION_STATE_KEY = 'aigv_compute_sessions_showcase_v1';

  function getRenderSessions() {
    if (scenarioMode()) return state.renderSessions || [];
    var jobs = (state.apiRenderJobs && state.apiRenderJobs.items) || [];
    return window.ComputeAdapters
      ? window.ComputeAdapters.adaptRenderSessions(jobs)
      : [];
  }

  function saveShowcaseSessions() {
    if (!scenarioMode()) return;
    try {
      sessionStorage.setItem(SESSION_STATE_KEY, JSON.stringify(
        (state.renderSessions || []).map(function(session) {
          return { id: session.id, status: session.status };
        })
      ));
    } catch (error) {
      // Session storage may be disabled.
    }
  }

  function loadShowcaseSessions() {
    if (!scenarioMode()) return;
    try {
      var raw = sessionStorage.getItem(SESSION_STATE_KEY);
      if (!raw) return;
      var statuses = JSON.parse(raw);
      if (!Array.isArray(statuses)) return;
      var map = {};
      statuses.forEach(function(item) { map[item.id] = item.status; });
      (state.renderSessions || []).forEach(function(session) {
        if (map[session.id]) session.status = map[session.id];
      });
    } catch (error) {
      // Ignore corrupt session state.
    }
  }

  function renderSessionsSubTab() {
    var sessions = getRenderSessions();
    var container = document.getElementById('cp-render-table');
    if (!container) return;
    if (!sessions.length) {
      container.innerHTML = '<div class="empty-state-container">' +
        '<h3 class="empty-title">暂无渲染会话</h3>' +
        '<p class="empty-desc">提交渲染任务后可在这里查看会话状态。</p></div>';
      return;
    }

    var statusLabels = {
      rendering: '渲染中', queued: '排队中', preparing: '准备中',
      paused: '已暂停', completed: '已完成', error: '错误'
    };

    var h = '<table class="cp-table"><thead><tr>' +
      '<th>会话编号</th><th>项目名称</th><th>渲染引擎</th><th>GPU 节点</th>' +
      '<th>分辨率</th><th>已运行</th><th>开始</th><th>预计完成</th>' +
      '<th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>';

    for (var s = 0; s < sessions.length; s += 1) {
      var session = sessions[s];
      h += '<tr>' +
        '<td>' + escapeHtml(session.id) + '</td>' +
        '<td>' + escapeHtml(session.project || session.projectName || session.id) + '</td>' +
        '<td>' + escapeHtml(session.engine || '—') + '</td>' +
        '<td>' + escapeHtml(session.gpuNode || '—') + '</td>' +
        '<td>' + escapeHtml(session.resolution || '—') + '</td>' +
        '<td>' + escapeHtml(session.runtime || '—') + '</td>' +
        '<td>' + escapeHtml(session.startedAt || '—') + '</td>' +
        '<td>' + escapeHtml(session.eta || '—') + '</td>' +
        '<td>' + badge(statusLabels[session.status] || session.status, session.status) + '</td>' +
        '<td>' +
        '<button class="cp-action-btn" onclick="ComputePlatform.handleSessionDetail(\'' + escapeHtml(session.id) + '\')">详情</button>' +
        (scenarioMode()
          ? '<button class="cp-action-btn" onclick="ComputePlatform.handleChangeStatus(\'' + escapeHtml(session.id) + '\')">切换状态</button>'
          : '') +
        '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';
    container.innerHTML = h;
  }

  function handleSessionDetail(id) {
    var sessions = getRenderSessions();
    var session = null;
    for (var i = 0; i < sessions.length; i += 1) {
      if (sessions[i].id === id) { session = sessions[i]; break; }
    }
    if (!session) return;

    var nodes = getGpuNodes();
    var node = null;
    for (var j = 0; j < nodes.length; j += 1) {
      if (nodes[j].id === session.nodeId ||
          nodes[j].name === session.gpuNode ||
          (nodes[j].name && session.gpuNode &&
            session.gpuNode.indexOf(nodes[j].name) !== -1)) {
        node = nodes[j];
        break;
      }
    }
    var progress = session.progressPct === null || session.progressPct === undefined
      ? null : Math.max(0, Math.min(100, Number(session.progressPct)));

    var html =
      '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">项目名称</div><div class="cp-detail-value">' + escapeHtml(session.project || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">渲染引擎</div><div class="cp-detail-value">' + escapeHtml(session.engine || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 节点</div><div class="cp-detail-value">' + escapeHtml(session.gpuNode || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">分辨率</div><div class="cp-detail-value">' + escapeHtml(session.resolution || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">FPS</div><div class="cp-detail-value">' + valueOrDash(session.fps) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">码率</div><div class="cp-detail-value">' + escapeHtml(session.bitrate || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">已运行</div><div class="cp-detail-value">' + escapeHtml(session.runtime || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">网络时延</div><div class="cp-detail-value">' + valueOrDash(session.latencyMs, ' ms') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">开始</div><div class="cp-detail-value">' + escapeHtml(session.startedAt || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">预计完成</div><div class="cp-detail-value">' + escapeHtml(session.eta || '—') + '</div></div>' +
      '</div>';

    if (progress !== null) {
      html += '<div class="cp-progress-bar-wrap" style="margin-top:16px">' +
        '<div class="cp-detail-label">渲染进度 ' + progress + '%</div>' +
        '<div class="cp-progress-bar"><div class="cp-progress-bar-fill" style="width:' + progress + '%"></div></div></div>';
    }
    if (node) {
      html += '<div class="cp-detail-grid" style="margin-top:16px">' +
        '<div class="cp-detail-group"><div class="cp-detail-label">GPU 型号</div><div class="cp-detail-value">' + escapeHtml(node.gpuModel || '—') + '</div></div>' +
        '<div class="cp-detail-group"><div class="cp-detail-label">GPU 利用率</div><div class="cp-detail-value">' + valueOrDash(node.utilizationPct, '%') + '</div></div>' +
        '<div class="cp-detail-group"><div class="cp-detail-label">显存占用</div><div class="cp-detail-value">' + valueOrDash(node.usedVramGb, ' GB') + ' / ' + valueOrDash(node.totalVramGb, ' GB') + '</div></div>' +
        '</div>';
    }
    html += '<div class="cp-session-note">会话状态仅通过当前页面更新，不调用真实云主机控制接口。</div>';
    showDetailDrawer('会话详情: ' + id, html);
  }

  function handleChangeStatus(id) {
    if (!scenarioMode()) {
      showToast('真实渲染任务状态由服务端管理', 'warning');
      return;
    }
    var sessions = state.renderSessions;
    for (var i = 0; i < sessions.length; i += 1) {
      if (sessions[i].id === id) {
        var current = sessions[i].status;
        if (current === 'rendering') sessions[i].status = 'completed';
        else if (current === 'queued') sessions[i].status = 'rendering';
        else if (current === 'paused') sessions[i].status = 'rendering';
        else if (current === 'completed') sessions[i].status = 'queued';
        else sessions[i].status = 'rendering';
        break;
      }
    }
    saveShowcaseSessions();
    renderSessionsSubTab();
    showToast('会话 ' + id + ' 状态已切换', 'info');
  }

  // ══════════════════════════════════════════════════
  // Tab 3: GPU Resource Pools
  // ══════════════════════════════════════════════════
  function demoEnabled() {
    return !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
  }

  function showcaseMode() {
    return !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.computeShowcase &&
      window.AIGV_COMPUTE_SHOWCASE);
  }

  function scenarioMode() {
    return showcaseMode() || demoEnabled();
  }

  function cloneData(value) {
    return value === null || value === undefined
      ? value : JSON.parse(JSON.stringify(value));
  }

  function sceneData() {
    return state.scene || {};
  }

  function getFilmScenes() {
    return sceneData().filmScenes || [];
  }

  function getArchScenes() {
    return sceneData().archScenes || [];
  }

  function getGamingScene() {
    return sceneData().gamingScene || {};
  }

  function getShowcaseImage(key, index) {
    var realImages = state.realShowcaseImages || [];
    if (realImages.length && key !== 'placeholder') {
      return realImages[index % realImages.length];
    }
    var images = sceneData().images || {};
    return images[key] || '/web/assets/showcase/placeholder.svg';
  }

  function resolveSceneImage(item, index) {
    var realImages = state.realShowcaseImages || [];
    if (realImages.length) {
      return realImages[index % realImages.length];
    }
    return (item && item.image) || getShowcaseImage('placeholder');
  }

  function imageFallbackAttr() {
    var fallback = getShowcaseImage('placeholder');
    return 'onerror="this.onerror=null;this.src=\'' +
      escapeHtml(fallback) + '\'"';
  }

  function loadRealShowcaseAssets() {
    if (!showcaseMode() || !window.AIGV) return;
    Promise.all([
      api('/api/assets?asset_type=image&limit=12').catch(function() { return null; }),
      api('/api/assets?asset_type=glb&limit=4').catch(function() { return null; })
    ]).then(function(results) {
      var imageData = results[0] || {};
      var glbData = results[1] || {};
      state.realShowcaseImages = (imageData.items || []).filter(function(item) {
        return item && item.file_url;
      }).map(function(item) {
        return item.file_url;
      });
      var glbItems = (glbData.items || []).filter(function(item) {
        return item && item.file_url;
      });
      state.realShowcaseGlb = glbItems.length ? glbItems[0].file_url : null;
      if (state.activeTab === 'rendering') {
        if (state.renderSubTab === 'film') {
          renderFilmKeyframes();
          renderFilmReference(state.filmSelectedKeyframe);
        } else if (state.renderSubTab === 'architecture') {
          renderArchShowcase();
        } else if (state.renderSubTab === 'gaming') {
          renderGameShowcase();
        }
      }
    }).catch(function() {
      // Local SVG assets remain available if the asset library is empty.
    });
  }

  function sensingNodesFromScene(nodes) {
    return (nodes || []).map(function(node) {
      return {
        id: node.id,
        name: node.name,
        gpuModel: node.gpuModel,
        gpuUtil: node.utilizationPct,
        vramUtil: node.vramUsedPct,
        temp: node.temperatureC,
        currentTask: node.currentTask || '—',
        heartbeat: '参考快照',
        status: node.status === 'online' ? 'normal' : node.status,
        pool: node.pool
      };
    });
  }

  function syncScenarioNetworkState() {
    var scene = sceneData();
    state.sensingNodesCopy = sensingNodesFromScene(scene.nodes);
    state.networkLinksCopy = cloneData(scene.networkLinks || []);
    state.storageNodesCopy = cloneData(scene.storageNodes || []);
    state.networkSamplesCopy = cloneData(scene.networkSeries || {
      labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: []
    });
    state.faultAlertsCopy = cloneData(scene.alerts || []);
    state.eventsCopy = cloneData(scene.events || []);
    state.switchRecordsCopy = cloneData(scene.switchRecords || []);
    state.renderSessions = cloneData(scene.sessions || []);
  }

  function buildLiveScene() {
    if (scenarioMode() || !window.ComputeAdapters) return;
    var nodes = state.liveMonitoringNodes || [];
    if (!nodes.length) {
      nodes = window.ComputeAdapters.adaptMonitoringNodes(
        (state.apiHosts && state.apiHosts.items) || []
      );
    }
    var summary = state.apiSummary || {};
    var links = state.networkLinksCopy || [];
    var series = state.networkSamplesCopy || {
      labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: []
    };
    var totalVram = 0;
    var usedVram = 0;
    nodes.forEach(function(node) {
      if (node.totalVramGb !== null && node.totalVramGb !== undefined) {
        totalVram += Number(node.totalVramGb) || 0;
      }
      if (node.usedVramGb !== null && node.usedVramGb !== undefined) {
        usedVram += Number(node.usedVramGb) || 0;
      }
    });
    var scene = {
      source: 'live',
      nodes: nodes,
      pools: window.ComputeAdapters.derivePoolsFromNodes(nodes),
      tasks: [],
      networkLinks: links,
      networkSeries: series,
      storageNodes: state.storageNodesCopy || [],
      alerts: state.faultAlertsCopy || [],
      sessions: getRenderSessions(),
      gpuTrend: { labels: [], values: [], unit: '%' },
      taskTrend: { labels: [], values: [], unit: '个' }
    };
    scene.overview = {
      totalNodes: summary.total_nodes !== undefined ? summary.total_nodes : nodes.length,
      onlineNodes: summary.online_nodes !== undefined ? summary.online_nodes
        : nodes.filter(function(node) { return node.status === 'online'; }).length,
      schedulableNodes: nodes.filter(function(node) {
        return node.status === 'online' && node.schedulable !== false;
      }).length,
      queueDepth: summary.queue_depth,
      queuedTasks: summary.queued_render_jobs,
      runningTasks: summary.running_render_jobs,
      totalGpus: nodes.reduce(function(total, node) {
        return total + (Number(node.gpuCount) || 0);
      }, 0),
      avgGpuUtilPct: computeGpuUtilFromNodes(nodes),
      avgGpuMemUsedPct: totalVram ? Number(((usedVram / totalVram) * 100).toFixed(1)) : null,
      avgNetworkLatencyMs: computeLatencyFromLinks(links),
      activeAlerts: countActiveAlerts(state.faultAlertsCopy)
    };
    state.scene = scene;
  }

  function normalizeGpuNode(node) {
    if (!node) return node;
    node.totalVram = node.totalVramGb;
    node.usedVram = node.usedVramGb;
    node.utilization = node.utilizationPct;
    return node;
  }

  function getGpuPools() {
    var scene = sceneData();
    if (scene.pools && scene.pools.length) {
      return scene.pools;
    }
    var nodes = getGpuNodes();
    return window.ComputeAdapters
      ? window.ComputeAdapters.derivePoolsFromNodes(nodes)
      : [];
  }

  function getGpuNodes() {
    var scene = sceneData();
    if (scene.nodes && scene.nodes.length) {
      return scene.nodes.map(normalizeGpuNode);
    }
    var hosts = (state.apiHosts && state.apiHosts.items) || [];
    var nodes = window.ComputeAdapters
      ? window.ComputeAdapters.adaptMonitoringNodes(hosts)
      : [];
    return nodes.map(normalizeGpuNode);
  }

  function renderGPU() {
    renderPoolCards();
    renderCloudEntry();
    renderNodeFilters();
    renderNodeTable();
  }

  function renderPoolCards() {
    var pools = getGpuPools();
    var grid = $('cp-pool-grid');
    if (!grid) return;
    if (!pools.length) {
      grid.innerHTML = '<div class="cp-chart-empty">暂无真实 GPU 资源池数据</div>';
      return;
    }
    var poolNodeCount = {};
    for (var i = 0; i < pools.length; i++) {
      poolNodeCount[pools[i].id] = pools[i].nodeCount;
    }

    var html = '';
    for (var p = 0; p < pools.length; p++) {
      var pool = pools[p];
      var statusCls = pool.status === 'degraded' ? ' status-degraded' : (pool.status !== 'healthy' ? ' status-error' : '');
      var hasUtil = typeof pool.avgUtil === 'number' && isFinite(pool.avgUtil);
      var utilPct = hasUtil ? pool.avgUtil : 0;
      var utilCls = utilPct > 70 ? ' danger' : (utilPct > 50 ? ' caution' : '');
      var priceLabel = typeof pool.unitPrice === 'number'
        ? '¥' + pool.unitPrice : '—';
      html += '<div class="cp-pool-card' + statusCls + '">' +
        '<div class="cp-pool-name">' + escapeHtml(pool.name) + '</div>' +
        '<div class="cp-pool-region">' + escapeHtml(pool.region || '—') + '</div>' +
        '<div class="cp-pool-stats">' +
        '<div><div class="cp-pool-stat-label">节点数</div><div class="cp-pool-stat-value">' + (pool.nodeCount || 0) + '</div></div>' +
        '<div><div class="cp-pool-stat-label">在线</div><div class="cp-pool-stat-value">' + (pool.onlineCount || 0) + '</div></div>' +
        '<div><div class="cp-pool-stat-label">可用GPU</div><div class="cp-pool-stat-value">' + (pool.availGpu || 0) + '</div></div>' +
        '<div><div class="cp-pool-stat-label">参考单价</div><div class="cp-pool-stat-value">' + escapeHtml(priceLabel) + '</div></div>' +
        '</div>' +
        '<div class="cp-pool-stat-label" style="margin-top:12px">利用率 ' + (hasUtil ? utilPct + '%' : '—') + '</div>' +
        '<div class="cp-pool-progress"><div class="cp-pool-progress-bar' + utilCls + '" style="width:' + utilPct + '%"></div></div>' +
        '</div>';
    }
    grid.innerHTML = html;
  }

  function renderCloudEntry() {
    var grid = $('cp-cloud-entry-grid');
    if (!grid) return;

    var html = '' +
      '<div class="cp-cloud-entry-card cp-cloud-entry-public" onclick="ComputePlatform.navigateToHosts(\'public\')">' +
        '<div class="cp-cloud-entry-icon">&#9729;</div>' +
        '<div class="cp-cloud-entry-body">' +
          '<div class="cp-cloud-entry-title">公有云</div>' +
          '<div class="cp-cloud-entry-desc">阿里云 · 腾讯云 · AWS · Azure</div>' +
          '<div class="cp-cloud-entry-stats">' +
            '<span>主机以资源平台列表为准</span>' +
            '<span>需配置云账号</span>' +
          '</div>' +
        '</div>' +
        '<button class="cp-cloud-entry-link">查看列表 &rarr;</button>' +
      '</div>' +
      '<div class="cp-cloud-entry-card cp-cloud-entry-private" onclick="ComputePlatform.navigateToHosts(\'private\')">' +
        '<div class="cp-cloud-entry-icon">&#127970;</div>' +
        '<div class="cp-cloud-entry-body">' +
          '<div class="cp-cloud-entry-title">私有云</div>' +
          '<div class="cp-cloud-entry-desc">私有云 / VMware / 通用 REST</div>' +
          '<div class="cp-cloud-entry-stats">' +
            '<span>主机以资源平台列表为准</span>' +
            '<span>需配置私有云凭据</span>' +
          '</div>' +
        '</div>' +
        '<button class="cp-cloud-entry-link">查看列表 &rarr;</button>' +
      '</div>';
    grid.innerHTML = html;
  }

  function navigateToHosts(scope) {
    window.location.href = '/compute-platform/hosts?scope=' + scope;
  }

  function renderNodeFilters() {
    var pools = getGpuPools();
    var filterBar = $('cp-node-filter-bar');
    if (!filterBar) return;

    var poolOptions = '<option value="all">全部资源池</option>';
    for (var i = 0; i < pools.length; i++) {
      poolOptions += '<option value="' + escapeHtml(pools[i].id) + '">' + escapeHtml(pools[i].name) + '</option>';
    }

    filterBar.innerHTML =
      '<input type="text" class="cp-search-input" id="cp-node-search" placeholder="搜索节点名称..." oninput="ComputePlatform.handleNodeFilter()">' +
      '<select class="cp-filter-select" id="cp-node-pool-filter" onchange="ComputePlatform.handleNodeFilter()">' + poolOptions + '</select>' +
      '<select class="cp-filter-select" id="cp-node-status-filter" onchange="ComputePlatform.handleNodeFilter()">' +
      '<option value="all">全部状态</option><option value="online">在线</option><option value="degraded">降级</option><option value="offline">离线</option>' +
      '</select>';
  }

  function handleNodeFilter() {
    var searchEl = $('cp-node-search');
    var poolEl = $('cp-node-pool-filter');
    var statusEl = $('cp-node-status-filter');
    if (searchEl) state.gpuNodeFilter.search = searchEl.value.toLowerCase();
    if (poolEl) state.gpuNodeFilter.pool = poolEl.value;
    if (statusEl) state.gpuNodeFilter.status = statusEl.value;
    renderNodeTable();
  }

  function valueOrDash(value, suffix) {
    if (value === null || value === undefined || value === '' || isNaN(Number(value))) {
      return '—';
    }
    return value + (suffix || '');
  }

  function renderNodeTable() {
    var nodes = getGpuNodes();
    var f = state.gpuNodeFilter;

    var filtered = [];
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (f.search && String(n.name || '').toLowerCase().indexOf(f.search) === -1) continue;
      if (f.pool !== 'all' && n.pool !== f.pool) continue;
      if (f.status !== 'all' && n.status !== f.status) continue;
      filtered.push(n);
    }

    var poolNames = {};
    var pools = getGpuPools();
    for (var j = 0; j < pools.length; j++) {
      poolNames[pools[j].id] = pools[j].name;
    }

    var h = '<table class="cp-table"><thead><tr>' +
      '<th>节点名称</th><th>资源池</th><th>GPU 型号</th><th>GPU 数</th>' +
      '<th>单卡显存</th><th>显存占用</th><th>利用率</th>' +
      '<th>当前任务</th><th>排队</th><th>时延</th><th>参考单价</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>';

    if (!filtered.length) {
      h += '<tr><td colspan="13"><div class="cp-chart-empty">' +
        (scenarioMode() ? '暂无符合条件的 GPU 节点' : '暂无真实 GPU 节点数据') +
        '</div></td></tr>';
    }
    for (var k = 0; k < filtered.length; k++) {
      var node = filtered[k];
      var totalVram = node.totalVramGb;
      var usedVram = node.usedVramGb;
      var vramPct = totalVram && usedVram !== null && usedVram !== undefined
        ? ((usedVram / totalVram) * 100).toFixed(1) : null;
      h += '<tr>' +
        '<td>' + escapeHtml(node.name) + '</td>' +
        '<td>' + escapeHtml(poolNames[node.pool] || node.pool) + '</td>' +
        '<td>' + escapeHtml(node.gpuModel) + '</td>' +
        '<td>' + (node.gpuCount || 0) + '</td>' +
        '<td>' + valueOrDash(node.vramPerGpuGb, ' GB') + '</td>' +
        '<td>' + (vramPct === null ? '—' : usedVram + ' / ' + totalVram + ' GB (' + vramPct + '%)') + '</td>' +
        '<td>' + valueOrDash(node.utilizationPct, '%') + '</td>' +
        '<td>' + escapeHtml(node.currentTask || '—') + '</td>' +
        '<td>' + valueOrDash(node.queuedTasks, ' 个') + '</td>' +
        '<td>' + valueOrDash(node.latencyMs, ' ms') + '</td>' +
        '<td>' + valueOrDash(node.unitPricePerHour, ' 元/卡/时') + '</td>' +
        '<td>' + badge(node.status, node.status) + '</td>' +
        '<td><button class="cp-action-btn" onclick="ComputePlatform.handleNodeDetail(\'' + escapeHtml(node.id) + '\')">详情</button></td>' +
        '</tr>';
    }
    h += '</tbody></table>';

    var container = $('cp-node-table');
    if (container) container.innerHTML = h;
  }

  function handleNodeDetail(id) {
    var nodes = getGpuNodes();
    var node = null;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id === id) { node = nodes[i]; break; }
    }
    if (!node) return;

    var poolName = node.pool;
    var pools = getGpuPools();
    for (var j = 0; j < pools.length; j++) {
      if (pools[j].id === node.pool) { poolName = pools[j].name; break; }
    }

    var totalVram = node.totalVramGb;
    var usedVram = node.usedVramGb;
    var vramPct = totalVram && usedVram !== null && usedVram !== undefined
      ? ((usedVram / totalVram) * 100).toFixed(1) : null;
    var vramCls = vramPct !== null && parseFloat(vramPct) > 80 ? 'danger' :
      (vramPct !== null && parseFloat(vramPct) > 60 ? 'warning' : '');
    var vramWidth = vramPct === null ? 0 : vramPct;

    var html =
      '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">节点名称</div><div class="cp-detail-value">' + escapeHtml(node.name) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">所属资源池</div><div class="cp-detail-value">' + escapeHtml(poolName) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 型号</div><div class="cp-detail-value">' + escapeHtml(node.gpuModel) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 数量</div><div class="cp-detail-value">' + (node.gpuCount || 0) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">单卡显存</div><div class="cp-detail-value">' + valueOrDash(node.vramPerGpuGb, ' GB') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">总显存</div><div class="cp-detail-value">' + valueOrDash(totalVram, ' GB') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">利用率</div><div class="cp-detail-value">' + valueOrDash(node.utilizationPct, '%') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">排队任务</div><div class="cp-detail-value">' + valueOrDash(node.queuedTasks, ' 个') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">网络时延</div><div class="cp-detail-value">' + valueOrDash(node.latencyMs, ' ms') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">参考单价</div><div class="cp-detail-value">' + valueOrDash(node.unitPricePerHour, ' 元/卡/时') + '</div></div>' +
      '</div>' +
      '<div class="cp-progress-bar-wrap" style="margin-top:16px"><div class="cp-detail-label">显存使用率 ' + (vramPct === null ? '—' : vramPct + '%') + '</div>' +
      '<div class="cp-progress-bar"><div class="cp-progress-bar-fill ' + vramCls + '" style="width:' + vramWidth + '%"></div></div></div>' +
      '<div class="cp-detail-group" style="margin-top:12px"><div class="cp-detail-label">当前任务</div><div class="cp-detail-value">' + escapeHtml(node.currentTask || '—') + '</div></div>' +
      '<div class="cp-detail-group" style="margin-top:12px"><div class="cp-detail-label">状态</div><div class="cp-detail-value">' + badge(node.status, node.status) + '</div></div>' +
      '';

    showDetailDrawer('节点详情: ' + node.name, html);
  }

  // ══════════════════════════════════════════════════
  // Tab 4: Scheduling Tasks
  // ══════════════════════════════════════════════════
  var SCHEDULE_FLOW_KEY = 'aigv_compute_schedule_showcase_v1';

  function selectedAttr(value, expected) {
    return value === expected ? ' selected' : '';
  }

  function formatScheduleMinutes(value) {
    if (value === null || value === undefined || !isFinite(Number(value))) {
      return '未采集';
    }
    var minutes = Math.max(1, Math.round(Number(value)));
    return '约 ' + minutes + ' 分钟';
  }

  function formatScheduleCost(value) {
    if (value === null || value === undefined || !isFinite(Number(value))) {
      return '未采集';
    }
    return '¥' + Number(value).toFixed(2) + '/小时';
  }

  function renderScheduleFlow() {
    if (!scenarioMode()) {
      return '<div class="cp-schedule-live-note">推荐结果仅供预览，真实调度需在资源平台确认后执行。</div>';
    }
    var states = window.ComputeScheduling ? window.ComputeScheduling.STATES : [];
    var labels = window.ComputeScheduling ? window.ComputeScheduling.STATE_LABELS : {};
    var current = state.schedulingFlow || 'pending';
    var currentIndex = states.indexOf(current);
    var steps = '';
    for (var i = 0; i < states.length; i += 1) {
      var cls = i < currentIndex ? ' done' : (i === currentIndex ? ' active' : '');
      steps += '<span class="cp-schedule-flow-step' + cls + '">' +
        escapeHtml(labels[states[i]] || states[i]) + '</span>';
    }
    return '<div class="cp-schedule-flow">' +
      '<div class="cp-schedule-flow-title">任务流转</div>' +
      '<div class="cp-schedule-flow-steps">' + steps + '</div>' +
      '<div class="cp-schedule-flow-actions">' +
      '<button type="button" class="cp-action-btn" onclick="ComputePlatform.advanceScheduleState()">推进状态</button>' +
      '<button type="button" class="cp-action-btn" onclick="ComputePlatform.resetScheduleState()">重置</button>' +
      '</div></div>';
  }

  function saveScheduleFlowState() {
    if (!scenarioMode()) return;
    try {
      sessionStorage.setItem(SCHEDULE_FLOW_KEY, JSON.stringify({
        flow: state.schedulingFlow,
        result: state.schedulingResult,
        form: state.schedulingForm
      }));
    } catch (error) {
      // Session storage may be disabled.
    }
  }

  function loadScheduleFlowState() {
    if (!scenarioMode()) return;
    try {
      var raw = sessionStorage.getItem(SCHEDULE_FLOW_KEY);
      if (!raw) return;
      var parsed = JSON.parse(raw);
      if (!parsed) return;
      if (parsed.form && typeof parsed.form === 'object') {
        state.schedulingForm = parsed.form;
      }
      if (parsed.result && typeof parsed.result === 'object') {
        state.schedulingResult = parsed.result;
      }
      var states = window.ComputeScheduling ? window.ComputeScheduling.STATES : [];
      if (states.indexOf(parsed.flow) !== -1) {
        state.schedulingFlow = parsed.flow;
      }
    } catch (error) {
      // Ignore corrupt session state.
    }
  }

  function renderScheduling() {
    var layout = $('cp-schedule-layout');
    if (!layout) return;

    var form = state.schedulingForm || {};
    var taskName = form.taskName || '';
    var minVram = Number(form.minVram) || 16;
    var gpuCount = Number(form.gpuCount) || 1;
    var maxCost = form.maxCost === undefined ? 0 : form.maxCost;
    var maxLatency = form.maxLatency === undefined ? 0 : form.maxLatency;
    var formHtml =
      '<div class="cp-schedule-form">' +
      '<div class="cp-form-group"><label class="cp-form-label">任务名称</label><input type="text" class="cp-form-input" id="cp-sched-name" placeholder="输入任务名称" value="' + escapeHtml(taskName) + '"></div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">任务类型</label><select class="cp-form-select" id="cp-sched-type">' +
      '<option value="render"' + selectedAttr(form.taskType || 'render', 'render') + '>渲染任务</option>' +
      '<option value="training"' + selectedAttr(form.taskType, 'training') + '>模型训练</option>' +
      '<option value="inference"' + selectedAttr(form.taskType, 'inference') + '>推理服务</option></select></div>' +
      '<div class="cp-form-group"><label class="cp-form-label">优先级</label><select class="cp-form-select" id="cp-sched-priority">' +
      '<option value="high"' + selectedAttr(form.priority, 'high') + '>高</option>' +
      '<option value="medium"' + selectedAttr(form.priority || 'medium', 'medium') + '>中</option>' +
      '<option value="low"' + selectedAttr(form.priority, 'low') + '>低</option></select></div>' +
      '</div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">最低显存 (GB)</label><input type="range" class="cp-form-range" id="cp-sched-vram" min="4" max="80" value="' + minVram + '" step="4" oninput="document.getElementById(\'cp-sched-vram-val\').textContent=this.value"><span class="cp-range-value" id="cp-sched-vram-val">' + minVram + '</span> GB</div>' +
      '<div class="cp-form-group"><label class="cp-form-label">GPU 数量</label><select class="cp-form-select" id="cp-sched-gpu-count">' +
      [1, 2, 4, 8].map(function(count) {
        return '<option value="' + count + '"' + selectedAttr(gpuCount, count) + '>' + count + '</option>';
      }).join('') + '</select></div>' +
      '</div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">预算 (元/小时)</label><input type="text" class="cp-form-input" id="cp-sched-cost" placeholder="0 表示不限" value="' + escapeHtml(maxCost) + '"></div>' +
      '<div class="cp-form-group"><label class="cp-form-label">最大时延 (ms)</label><input type="text" class="cp-form-input" id="cp-sched-latency" placeholder="0 表示不限" value="' + escapeHtml(maxLatency) + '"></div>' +
      '</div>' +
      '<div class="cp-form-group"><label class="cp-form-label">调度策略</label><select class="cp-form-select" id="cp-sched-strategy">' +
      '<option value="lowest_cost"' + selectedAttr(form.strategy || 'lowest_cost', 'lowest_cost') + '>最低费用</option>' +
      '<option value="lowest_latency"' + selectedAttr(form.strategy, 'lowest_latency') + '>最低时延</option>' +
      '<option value="shortest_queue"' + selectedAttr(form.strategy, 'shortest_queue') + '>最短排队</option>' +
      '<option value="highest_performance"' + selectedAttr(form.strategy, 'highest_performance') + '>最高性能</option>' +
      '<option value="local_first"' + selectedAttr(form.strategy, 'local_first') + '>本地优先</option></select></div>' +
      '<div class="cp-schedule-hint">先满足在线、GPU 数量、单卡显存、预算与时延硬性约束，再按策略评分。</div>' +
      '<button class="cp-form-submit" onclick="ComputePlatform.handleGenerateSchedule()">生成调度方案</button>' +
      '</div>';

    var resultHtml = '';
    var result = state.schedulingResult;
    if (result) {
      if (result.recommendations && result.recommendations.length) {
        resultHtml = '<div class="cp-schedule-result-card">' +
          '<div class="cp-result-title">调度推荐</div>';
        for (var i = 0; i < result.recommendations.length; i += 1) {
          var rec = result.recommendations[i];
          resultHtml += '<div class="cp-schedule-rec">' +
            '<div class="cp-schedule-rec-head"><span class="cp-schedule-rec-name">' +
            (i + 1) + '. ' + escapeHtml(rec.nodeName) + '</span>' +
            '<span class="cp-schedule-score">评分 ' + Number(rec.score).toFixed(3) + '</span></div>' +
            '<div class="cp-result-row"><span class="cp-result-label">GPU 型号</span><span class="cp-result-value">' + escapeHtml(rec.gpuModel) + '</span></div>' +
            '<div class="cp-result-row"><span class="cp-result-label">当前利用率</span><span class="cp-result-value">' + valueOrDash(rec.utilizationPct, '%') + '</span></div>' +
            '<div class="cp-result-row"><span class="cp-result-label">预计排队</span><span class="cp-result-value">' + escapeHtml(formatScheduleMinutes(rec.estimatedWaitMinutes)) + '</span></div>' +
            '<div class="cp-result-row"><span class="cp-result-label">预计执行</span><span class="cp-result-value">' + escapeHtml(formatScheduleMinutes(rec.estimatedExecMinutes)) + '</span></div>' +
            '<div class="cp-result-row"><span class="cp-result-label">参考费用</span><span class="cp-result-value">' + escapeHtml(formatScheduleCost(rec.estimatedCostPerHour)) + '</span></div>' +
            '<div class="cp-result-reason">' + escapeHtml(rec.reason) + '</div>' +
            '</div>';
        }
        resultHtml += '<div class="cp-schedule-rejected">已过滤 ' + result.rejectedCount + ' / ' + result.totalCandidates + ' 个不满足硬性约束的节点</div>';
        if (result.rejected && result.rejected.length) {
          resultHtml += '<details class="cp-schedule-reject-details"><summary>查看过滤原因</summary>';
          for (var r = 0; r < result.rejected.length; r += 1) {
            resultHtml += '<div class="cp-schedule-reject-row"><strong>' + escapeHtml(result.rejected[r].nodeName) + '</strong>：' +
              escapeHtml((result.rejected[r].reasons || []).join('、')) + '</div>';
          }
          resultHtml += '</details>';
        }
        resultHtml += renderScheduleFlow();
        resultHtml += '</div>';
      } else {
        resultHtml = '<div class="cp-schedule-result-card empty">没有满足全部硬性约束的节点。已检查 ' +
          result.totalCandidates + ' 个候选节点。</div>';
        if (result.rejected && result.rejected.length) {
          resultHtml += '<details class="cp-schedule-reject-details"><summary>查看过滤原因</summary>';
          for (var q = 0; q < result.rejected.length; q += 1) {
            resultHtml += '<div class="cp-schedule-reject-row"><strong>' + escapeHtml(result.rejected[q].nodeName) + '</strong>：' +
              escapeHtml((result.rejected[q].reasons || []).join('、')) + '</div>';
          }
          resultHtml += '</details>';
        }
      }
    } else {
      resultHtml = '<div class="cp-schedule-result-card empty">填写表单后点击“生成调度方案”。推荐仅供预览，不会提交真实调度任务。</div>';
    }

    layout.innerHTML = formHtml + resultHtml;
  }

  function handleGenerateSchedule() {
    var taskName = ($('cp-sched-name') ? $('cp-sched-name').value : '') || '未命名任务';
    var form = {
      taskName: taskName,
      taskType: $('cp-sched-type') ? $('cp-sched-type').value : 'render',
      priority: $('cp-sched-priority') ? $('cp-sched-priority').value : 'medium',
      minVram: parseInt($('cp-sched-vram') ? $('cp-sched-vram').value : 16, 10),
      gpuCount: parseInt($('cp-sched-gpu-count') ? $('cp-sched-gpu-count').value : 1, 10),
      maxCost: parseFloat($('cp-sched-cost') ? ($('cp-sched-cost').value || '0') : '0'),
      maxLatency: parseFloat($('cp-sched-latency') ? ($('cp-sched-latency').value || '0') : '0'),
      strategy: $('cp-sched-strategy') ? $('cp-sched-strategy').value : 'lowest_cost'
    };
    state.schedulingForm = form;

    var nodes = getGpuNodes();
    if (!nodes.length) {
      state.schedulingResult = null;
      state.schedulingFlow = 'pending';
      saveScheduleFlowState();
      renderScheduling();
      showToast('暂无可用 GPU 节点数据', 'warning');
      return;
    }

    var result = window.ComputeScheduling
      ? window.ComputeScheduling.evaluate(nodes, form)
      : null;
    state.schedulingResult = result;
    state.schedulingFlow = result && result.recommendations.length
      ? 'recommended' : 'pending';
    saveScheduleFlowState();
    renderScheduling();
    if (result && result.recommendations.length) {
      showToast('调度推荐已生成', 'success');
    } else {
      showToast('没有满足全部硬性约束的节点', 'warning');
    }
  }

  function advanceScheduleState() {
    if (!scenarioMode()) {
      showToast('真实模式不提供本地状态推进', 'warning');
      return;
    }
    if (!state.schedulingResult || !state.schedulingResult.recommendations.length) {
      showToast('请先生成调度方案', 'warning');
      return;
    }
    var next = window.ComputeScheduling
      ? window.ComputeScheduling.nextState(state.schedulingFlow)
      : state.schedulingFlow;
    if (next === state.schedulingFlow) {
      showToast('任务流转已完成', 'info');
      return;
    }
    state.schedulingFlow = next;
    saveScheduleFlowState();
    renderScheduling();
  }

  function resetScheduleState() {
    state.schedulingFlow = 'pending';
    saveScheduleFlowState();
    renderScheduling();
  }

  // ══════════════════════════════════════════════════
  // Tab 5: 智能感知与传输优化
  // ══════════════════════════════════════════════════

  // ── Utility label mappers ──
  function statusLabel(s) {
    var map = { normal: '正常', highload: '高负载', abnormal: '异常', standby: '待机', offline: '离线', switching: '切换中' };
    return map[s] || s;
  }
  function typeLabel(t) {
    var map = { gpu: 'GPU故障', link: '链路故障', storage: '存储故障', network: '网络故障' };
    return map[t] || t;
  }
  function recoveryStatusLabel(r) {
    var map = { switching: '切换中', detecting: '检测中', warning: '预警中', recovered: '已恢复', failed: '切换失败', pending: '等待中' };
    return map[r] || r;
  }
  function formatTime(date) {
    var d = date || new Date();
    var yyyy = d.getFullYear();
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    var hh = String(d.getHours()).padStart(2, '0');
    var mi = String(d.getMinutes()).padStart(2, '0');
    var ss = String(d.getSeconds()).padStart(2, '0');
    return yyyy + '-' + mm + '-' + dd + ' ' + hh + ':' + mi + ':' + ss;
  }

  // ── Retained helpers (fetch from API when available) ──
  function refreshMonitoringData() {
    if (scenarioMode() || !window.ComputeAdapters) return;
    fetchMonitoringNodes().then(function(data) {
      state.liveMonitoringNodes = window.ComputeAdapters.adaptMonitoringNodes(
        data.nodes || []
      );
      state.sensingNodesCopy = sensingNodesFromScene(state.liveMonitoringNodes);
      buildLiveScene();
      renderSensingNodes();
      renderBottomMetrics();
      renderNetworkTopology();
      if (state.activeTab === 'overview') renderOverview();
      if (state.activeTab === 'gpu') renderGPU();
      if (state.activeTab === 'rendering' && state.renderSubTab === 'sessions') {
        renderSessionsSubTab();
      }
    });
    fetchNetworkLinks().then(function(data) {
      state.networkLinksCopy = window.ComputeAdapters.adaptMonitoringLinks(
        data.links || []
      );
      buildLiveScene();
      renderSensingLinks();
      renderBottomMetrics();
      renderSensingCharts();
      renderNetworkTopology();
      if (state.activeTab === 'overview') renderOverview();
    });
    fetchMonitoringSamples(20).then(function(data) {
      state.networkSamplesCopy = window.ComputeAdapters.adaptMonitoringSamples(
        data.samples || []
      );
      buildLiveScene();
      renderSensingCharts();
      if (state.activeTab === 'overview') renderOverview();
    });
    fetchStorageData().then(function(data) {
      state.storageNodesCopy = window.ComputeAdapters.adaptStorage(
        data.targets || [], data.summary || {}
      );
      buildLiveScene();
      renderStorageNodes();
      renderStorageSummary();
    });
    fetchAlerts('open', 20).then(function(data) {
      state.faultAlertsCopy = window.ComputeAdapters.adaptAlerts(
        data.items || []
      );
      buildLiveScene();
      renderFaultAlerts();
      renderSensingHeader();
      renderBottomMetrics();
      renderEventTimeline();
      if (state.activeTab === 'overview') renderOverview();
    });
  }

  function randomizeNetworkMetrics() {
    // Replaced by refreshMonitoringData() -- kept as no-op for backward compat
  }

  function addNetworkSample() {
    var links = state.networkLinksCopy;
    var avgBw = 0, avgLat = 0, avgLoss = 0;
    for (var i = 0; i < links.length; i++) {
      avgBw += links[i].bandwidth / 1000;
      avgLat += links[i].latency;
      avgLoss += links[i].packetLoss;
    }
    avgBw = avgBw / (links.length || 1);
    avgLat = avgLat / (links.length || 1);
    avgLoss = avgLoss / (links.length || 1);
    state.networkSamplesCopy.push({ bandwidth: parseFloat(avgBw.toFixed(2)), latency: parseFloat(avgLat.toFixed(1)), packetLoss: parseFloat(avgLoss.toFixed(2)) });
    // Keep max 20
    while (state.networkSamplesCopy.length > 20) { state.networkSamplesCopy.shift(); }
  }

  function updateClock() {
    var el = $('sd-clock');
    if (el) el.textContent = formatTime(new Date());
  }

  function startClockTimer() {
    if (state.clockTimer) return;
    updateClock();
    state.clockTimer = setInterval(updateClock, 1000);
  }

  function computeSystemStatus() {
    var critical = 0, warning = 0;
    var alerts = state.faultAlertsCopy;
    for (var i = 0; i < alerts.length; i++) {
      var rs = alerts[i].recoveryStatus;
      if (rs === 'detecting' || rs === 'switching') critical++;
      else if (rs === 'warning') warning++;
    }
    var nodes = state.sensingNodesCopy;
    for (var j = 0; j < nodes.length; j++) {
      if (nodes[j].status === 'abnormal') critical++;
      else if (nodes[j].status === 'highload') warning++;
    }
    if (critical > 0) return 'critical';
    if (warning > 0) return 'warning';
    return 'normal';
  }

  function refreshAllData() {
    // Delegate to API-based refresh
    refreshMonitoringData();
  }

  function refreshAllDisplay() {
    renderSensingNodes();
    renderSensingLinks();
    renderFaultAlerts();
    renderSensingCharts();
    renderStorageNodes();
    renderStorageSummary();
    renderSwitchHistory();
    renderBottomMetrics();
    renderNetworkTopology();
    renderEventTimeline();
    if (state.activeTab === 'overview') renderOverview();
  }

  // ── Header ──
  function renderSensingHeader() {
    var st = computeSystemStatus();
    var dot = $('sd-status-dot');
    var label = $('sd-status-label');
    if (dot) { dot.className = 'sd-status-dot ' + st; }
    if (label) {
      var m = { normal: '系统状态：正常', warning: '系统状态：注意', critical: '系统状态：异常' };
      label.textContent = m[st] || '系统状态：未知';
    }
    var cb = document.getElementById('sd-auto-refresh');
    if (cb) cb.checked = state.isNetworkAutoRefresh;
  }

  // ── Nodes Grid ──
  function renderSensingNodes() {
    var grid = $('sd-nodes-grid');
    if (!grid) return;
    var nodes = state.sensingNodesCopy;
    if (!nodes || !nodes.length) {
      grid.innerHTML = '<div class="empty-state-container">' +
        '<h3 class="empty-title">暂无采集节点</h3>' +
        '<p class="empty-desc">' + (scenarioMode() ? '暂无参考节点。' : '尚未接入节点采集数据源。') + '</p></div>';
      return;
    }
    var h = '';
    for (var i = 0; i < nodes.length; i += 1) {
      var n = nodes[i];
      var gpuUtil = n.gpuUtil;
      var vramUtil = n.vramUtil;
      var hasGpu = gpuUtil !== null && gpuUtil !== undefined && isFinite(Number(gpuUtil));
      var hasVram = vramUtil !== null && vramUtil !== undefined && isFinite(Number(vramUtil));
      var barClass = hasGpu && gpuUtil >= 85 ? 'danger' : (hasGpu && gpuUtil >= 70 ? 'warn' : '');
      var heartbeat = n.heartbeat ? String(n.heartbeat) : '—';
      h += '<div class="sd-node-card status-' + escapeHtml(n.status || 'normal') + '" onclick="ComputePlatform.showNodeDetail(\'' + escapeHtml(n.id) + '\')">' +
        '<div class="sd-node-name">' + escapeHtml(n.name) + '</div>' +
        '<div class="sd-node-model">' + escapeHtml(n.gpuModel || '—') + '</div>' +
        '<div class="sd-node-metric"><span>GPU</span><span>' + (hasGpu ? gpuUtil + '%' : '—') + '</span></div>' +
        '<div class="sd-node-bar"><div class="sd-node-bar-fill ' + barClass + '" style="width:' + (hasGpu ? gpuUtil : 0) + '%"></div></div>' +
        '<div class="sd-node-metric"><span>VRAM</span><span>' + (hasVram ? vramUtil + '%' : '—') + '</span></div>' +
        '<div class="sd-node-bar"><div class="sd-node-bar-fill ' + barClass + '" style="width:' + (hasVram ? vramUtil : 0) + '%"></div></div>' +
        '<div class="sd-node-bottom"><span class="sd-node-temp">' + valueOrDash(n.temp, '°C') + '</span><span class="sd-node-heartbeat">' +
        escapeHtml(heartbeat.length > 12 ? heartbeat.substr(-10) : heartbeat) + '</span></div>' +
        '</div>';
    }
    grid.innerHTML = h;
  }

  // ── Links List ──
  function renderSensingLinks() {
    var list = $('sd-links-list');
    if (!list) return;
    var links = state.networkLinksCopy;
    if (!links || !links.length) {
      list.innerHTML = '<div class="sd-alerts-empty">暂无网络链路采集数据</div>';
      return;
    }
    var stLabels = {
      excellent: '极佳', normal: '正常', degraded: '降级', congested: '拥塞',
      unstable: '不稳定', down: '中断', warning: '预警'
    };
    var h = '';
    for (var i = 0; i < links.length; i += 1) {
      var link = links[i];
      var status = link.status || 'normal';
      var source = link.sourceName || link.source || '—';
      var target = link.targetName || link.target || '—';
      var bandwidth = link.bandwidthGbps;
      var bandwidthLabel = bandwidth === null || bandwidth === undefined
        ? '—' : Number(bandwidth).toFixed(1) + ' Gbps';
      h += '<div class="sd-link-item status-' + escapeHtml(status) +
        '" onclick="ComputePlatform.showNetworkLinkDetail(\'' + escapeHtml(link.id) + '\')">' +
        '<div class="sd-link-top">' +
        '<span class="sd-link-name">' + escapeHtml(link.name || (source + ' → ' + target)) + '</span>' +
        '<span class="sd-link-status-label ' + escapeHtml(status) + '">' + escapeHtml(stLabels[status] || status) + '</span>' +
        '</div>' +
        '<div class="sd-link-path">' + escapeHtml(source) + ' → ' + escapeHtml(target) + '</div>' +
        '<div class="sd-link-metrics">' +
        '<span>时延 <strong>' + valueOrDash(link.latencyMs, 'ms') + '</strong></span>' +
        '<span>抖动 <strong>' + valueOrDash(link.jitterMs, 'ms') + '</strong></span>' +
        '<span>丢包 <strong>' + valueOrDash(link.packetLossPct, '%') + '</strong></span>' +
        '<span>带宽 <strong>' + escapeHtml(bandwidthLabel) + '</strong></span>' +
        '</div>' +
        '</div>';
    }
    list.innerHTML = h;
  }

  // ── Fault Alerts ──
  function renderFaultAlerts() {
    var panel = $('sd-alerts-panel');
    if (!panel) return;
    var alerts = state.faultAlertsCopy || [];
    if (alerts.length === 0) {
      panel.innerHTML = '<div class="sd-alerts-empty">当前无故障告警</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < alerts.length; i += 1) {
      var alert = alerts[i];
      var level = alert.level || alert.severity || 'warning';
      var levelText = level === 'critical' ? '严重' : (level === 'warning' ? '警告' : '错误');
      var statusText = alert.recoveryStatus
        ? recoveryStatusLabel(alert.recoveryStatus)
        : (alert.status || '—');
      h += '<div class="sd-alert-card level-' + escapeHtml(level) + '">' +
        '<div class="sd-alert-top">' +
        '<span class="sd-alert-level ' + escapeHtml(level) + '">' + levelText + '</span>' +
        '<span class="sd-alert-time">' + escapeHtml(alert.time || '—') + '</span>' +
        '</div>' +
        '<div class="sd-alert-detail">' + escapeHtml(typeLabel(alert.type || 'system')) + ': ' +
        escapeHtml(alert.targetName || alert.targetId || '—') + '</div>' +
        '<div class="sd-alert-reason">' + escapeHtml(alert.reason || alert.content || '—') + '</div>';
      if (alert.autoRecovery && alert.recoveryStatus !== 'recovered') {
        h += '<div class="sd-alert-recovery">自动恢复中… (' + escapeHtml(statusText) + ')</div>';
      }
      if (scenarioMode() && alert.recoveryStatus === 'recovered' && !alert.confirmed) {
        h += '<div class="sd-alert-actions">' +
          '<button onclick="ComputePlatform.confirmAlertRecovery(\'' + escapeHtml(alert.id) + '\')">确认恢复</button>' +
          '<button onclick="ComputePlatform.resolveAlert(\'' + escapeHtml(alert.id) + '\')">忽略</button>' +
          '</div>';
      }
      h += '</div>';
    }
    panel.innerHTML = h;
  }

  // ── Charts ──
  function lastNumericValue(values) {
    for (var i = (values || []).length - 1; i >= 0; i -= 1) {
      if (values[i] !== null && values[i] !== undefined && isFinite(Number(values[i]))) {
        return Number(values[i]);
      }
    }
    return null;
  }

  function getDisplayedNetworkSeries() {
    var series = state.networkSamplesCopy || {
      labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: []
    };
    if (!scenarioMode() || state.networkPlaybackPaused) return series;
    var total = (series.labels || []).length;
    if (!total) return series;
    var end = Math.max(1, Math.min(total, state.networkPlaybackCursor + 1));
    var start = Math.max(0, end - 12);
    return {
      labels: series.labels.slice(start, end),
      bandwidthGbps: (series.bandwidthGbps || []).slice(start, end),
      latencyMs: (series.latencyMs || []).slice(start, end),
      packetLossPct: (series.packetLossPct || []).slice(start, end)
    };
  }

  function renderSensingCharts() {
    var charts = window.ComputeCharts;
    if (!charts) return;
    var series = getDisplayedNetworkSeries();
    var titles = [
      { id: 'sd-chart-bandwidth', field: 'bandwidthGbps', unit: 'Gbps', color: '#78bfd2', label: '总带宽', zero: true },
      { id: 'sd-chart-latency', field: 'latencyMs', unit: 'ms', color: '#d7a84f', label: '平均时延', zero: true },
      { id: 'sd-chart-packetLossPct', field: 'packetLossPct', unit: '%', color: '#d67f85', label: '丢包率', zero: true }
    ];
    // The loss chart wrapper keeps its historical id.
    titles[2].id = 'sd-chart-loss';
    for (var i = 0; i < titles.length; i += 1) {
      var item = titles[i];
      var wrap = $(item.id);
      if (!wrap) continue;
      var values = series[item.field] || [];
      var last = lastNumericValue(values);
      var chart = charts.lineChart({
        labels: series.labels || [],
        values: values,
        unit: item.unit,
        color: item.color,
        zeroBaseline: item.zero,
        title: item.label,
        ariaLabel: item.label + '趋势图'
      });
      var current = last === null ? '—' : (Number(last).toFixed(item.field === 'bandwidthGbps' ? 2 : 1) + ' ' + item.unit);
      wrap.innerHTML = '<div class="sd-chart-title">' + item.label + '</div>' + chart +
        '<div class="sd-chart-current">当前: ' + current + '</div>';
    }
  }

  // ── Storage ──
  // ── Storage ──
  function renderStorageNodes() {
    var grid = $('sd-storage-grid');
    if (!grid) return;
    var storages = state.storageNodesCopy || [];
    if (!storages.length) {
      grid.innerHTML = '<div class="sd-alerts-empty">暂无存储采集数据</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < storages.length; i += 1) {
      var storage = storages[i];
      var capacity = storage.capacityTB;
      var used = storage.usedTB;
      var pct = storage.usagePct;
      if (pct === null || pct === undefined) {
        pct = capacity && used !== null && used !== undefined
          ? Math.round((used / capacity) * 100) : null;
      }
      var barClass = pct !== null && pct >= 90 ? 'danger' : (pct !== null && pct >= 75 ? 'warn' : '');
      h += '<div class="sd-storage-card' + (storage.status === 'warning' ? ' status-warning' : '') + '">' +
        '<div class="sd-storage-name">' + escapeHtml(storage.name || '—') + '</div>' +
        '<div class="sd-storage-used">' + valueOrDash(used, ' TB') + ' / ' + valueOrDash(capacity, ' TB') +
        (pct === null ? '' : ' (' + pct + '%)') + '</div>' +
        '<div class="sd-storage-bar"><div class="sd-storage-bar-fill ' + barClass + '" style="width:' + (pct || 0) + '%"></div></div>' +
        '<div class="sd-storage-speed"><span>读 ' + valueOrDash(storage.readMBps, ' MB/s') + '</span><span>写 ' + valueOrDash(storage.writeMBps, ' MB/s') + '</span></div>' +
        '<div class="sd-storage-conn">连接数: ' + valueOrDash(storage.connections) + '</div>' +
        '</div>';
    }
    grid.innerHTML = h;
  }

  function renderStorageSummary() {
    var sum = $('sd-storage-summary');
    if (!sum) return;
    var storages = state.storageNodesCopy || [];
    var totalCap = 0;
    var totalUsed = 0;
    var totalRead = 0;
    var totalWrite = 0;
    var totalConn = 0;
    var hasCap = false;
    var hasUsed = false;
    var hasRead = false;
    var hasWrite = false;
    var hasConn = false;
    for (var i = 0; i < storages.length; i += 1) {
      var storage = storages[i];
      if (storage.capacityTB !== null && storage.capacityTB !== undefined) {
        totalCap += Number(storage.capacityTB) || 0;
        hasCap = true;
      }
      if (storage.usedTB !== null && storage.usedTB !== undefined) {
        totalUsed += Number(storage.usedTB) || 0;
        hasUsed = true;
      }
      if (storage.readMBps !== null && storage.readMBps !== undefined) {
        totalRead += Number(storage.readMBps) || 0;
        hasRead = true;
      }
      if (storage.writeMBps !== null && storage.writeMBps !== undefined) {
        totalWrite += Number(storage.writeMBps) || 0;
        hasWrite = true;
      }
      if (storage.connections !== null && storage.connections !== undefined) {
        totalConn += Number(storage.connections) || 0;
        hasConn = true;
      }
    }
    sum.innerHTML =
      '<div class="sd-storage-stat"><strong>' + (hasCap ? totalCap.toFixed(1) + ' TB' : '—') + '</strong>总容量</div>' +
      '<div class="sd-storage-stat"><strong>' + (hasUsed ? totalUsed.toFixed(2) + ' TB' : '—') + '</strong>已使用</div>' +
      '<div class="sd-storage-stat"><strong>' + (hasRead ? totalRead + ' MB/s' : '—') + '</strong>总读吞吐</div>' +
      '<div class="sd-storage-stat"><strong>' + (hasWrite ? totalWrite + ' MB/s' : '—') + '</strong>总写吞吐</div>' +
      '<div class="sd-storage-stat"><strong>—</strong>缓存命中率</div>' +
      '<div class="sd-storage-stat"><strong>' + (hasConn ? totalConn : '—') + '</strong>总连接数</div>';
  }

  // ── Switch History ──
  function renderSwitchHistory() {
    var wrap = $('sd-switch-table-wrapper');
    if (!wrap) return;
    var records = state.switchRecordsCopy || [];
    if (!records.length) {
      wrap.innerHTML = '<div class="sd-alerts-empty">暂无故障切换记录</div>';
      return;
    }
    var h = '<table class="sd-switch-table"><thead><tr><th>时间</th><th>类型</th><th>源 → 目标</th><th>原因</th><th>耗时(s)</th><th>结果</th></tr></thead><tbody>';
    for (var i = 0; i < records.length; i += 1) {
      var record = records[i];
      var source = record.source || '—';
      var target = record.target || '—';
      var srcDst = escapeHtml(source) + ' → ' + escapeHtml(target);
      if (srcDst.length > 30) srcDst = srcDst.substr(0, 28) + '…';
      h += '<tr>' +
        '<td>' + escapeHtml(record.time || '—') + '</td>' +
        '<td>' + escapeHtml(record.type || '—') + '</td>' +
        '<td>' + srcDst + '</td>' +
        '<td>' + escapeHtml(record.reason || '—') + '</td>' +
        '<td>' + valueOrDash(record.duration) + '</td>' +
        '<td class="result-' + (record.result === '成功' ? 'success' : 'fail') + '">' + escapeHtml(record.result || '—') + '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';
    wrap.innerHTML = h;
  }

  // ── Bottom Metrics ──
  function renderBottomMetrics() {
    var bar = $('sd-metrics-bar');
    if (!bar) return;
    var links = state.networkLinksCopy || [];
    var nodes = state.sensingNodesCopy || [];
    var latencies = [];
    var throughputs = [];
    var activeLinks = 0;
    for (var i = 0; i < links.length; i += 1) {
      if (links[i].latencyMs !== null && links[i].latencyMs !== undefined) {
        latencies.push(Number(links[i].latencyMs));
      }
      if (links[i].throughputGbps !== null && links[i].throughputGbps !== undefined) {
        throughputs.push(Number(links[i].throughputGbps));
      }
      if (links[i].status !== 'down') activeLinks += 1;
    }
    var onlineNodes = nodes.filter(function(node) {
      return node.status !== 'offline' && node.status !== 'unknown';
    }).length;
    var activeTasks = nodes.filter(function(node) {
      return node.status === 'normal' || node.status === 'highload' || node.status === 'abnormal';
    }).length;
    var avgLatency = latencies.length
      ? (latencies.reduce(function(sum, value) { return sum + value; }, 0) / latencies.length)
      : null;
    var totalThroughput = throughputs.length
      ? throughputs.reduce(function(sum, value) { return sum + value; }, 0)
      : null;
    var availRate = links.length ? (activeLinks / links.length) * 100 : null;
    bar.innerHTML =
      '<div class="sd-metric-item"><div class="sd-metric-label">平均链路时延</div><div class="sd-metric-value">' +
      (avgLatency === null ? '—' : avgLatency.toFixed(1) + ' ms') + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">可用率</div><div class="sd-metric-value">' +
      (availRate === null ? '—' : availRate.toFixed(1) + '%') + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">活跃任务</div><div class="sd-metric-value">' + activeTasks + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">总吞吐</div><div class="sd-metric-value">' +
      (totalThroughput === null ? '—' : totalThroughput.toFixed(1) + ' Gbps') + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">在线节点</div><div class="sd-metric-value">' +
      onlineNodes + '/' + nodes.length + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">活跃链路</div><div class="sd-metric-value">' +
      activeLinks + '/' + links.length + '</div></div>';
  }

  // ── Monitoring lifecycle ──
  function startMonitoring() {
    if (scenarioMode()) return;
    stopMonitoring();
    state.monitoringTimer = setInterval(function() {
      if (state.activeTab !== 'network' || scenarioMode()) {
        stopMonitoring();
        return;
      }
      refreshMonitoringData();
    }, 5000);
  }

  function stopMonitoring() {
    if (state.monitoringTimer) {
      clearInterval(state.monitoringTimer);
      state.monitoringTimer = null;
    }
  }

  function stopNetworkPlayback() {
    if (state.networkPlaybackTimer) {
      clearInterval(state.networkPlaybackTimer);
      state.networkPlaybackTimer = null;
    }
  }

  function startNetworkPlayback() {
    if (!scenarioMode() || state.networkPlaybackPaused) return;
    stopNetworkPlayback();
    state.networkPlaybackTimer = setInterval(function() {
      if (state.activeTab !== 'network' || !scenarioMode()) {
        stopNetworkPlayback();
        return;
      }
      var total = (state.networkSamplesCopy.labels || []).length;
      if (!total) return;
      state.networkPlaybackCursor = state.networkPlaybackCursor >= total - 1
        ? Math.min(11, total - 1)
        : state.networkPlaybackCursor + 1;
      renderSensingCharts();
    }, 2500);
  }

  function toggleNetworkPlayback() {
    if (!scenarioMode()) {
      showToast('当前环境不支持场景播放控制', 'warning');
      return;
    }
    state.networkPlaybackPaused = !state.networkPlaybackPaused;
    if (state.networkPlaybackPaused) {
      stopNetworkPlayback();
    } else {
      startNetworkPlayback();
    }
    updateNetworkControls();
  }

  function resetNetworkScenario() {
    if (!scenarioMode()) return;
    stopNetworkPlayback();
    state.networkPlaybackPaused = false;
    state.networkScenarioFault = false;
    state.networkFaultSnapshot = null;
    syncScenarioNetworkState();
    state.networkPlaybackCursor = Math.min(
      11, Math.max(0, (state.networkSamplesCopy.labels || []).length - 1)
    );
    updateNetworkControls();
    refreshAllDisplay();
    startNetworkPlayback();
    showToast('场景已重置', 'info');
  }

  function updateNetworkControls() {
    var scenario = scenarioMode();
    var autoLabel = document.getElementById('sd-auto-refresh-label');
    var manualBtn = document.getElementById('sd-manual-refresh-btn');
    var playbackBtn = document.getElementById('sd-playback-btn');
    var resetBtn = document.getElementById('sd-reset-scenario-btn');
    var simulateBtn = document.getElementById('sd-simulate-btn');
    if (autoLabel) autoLabel.style.display = scenario ? 'none' : '';
    if (manualBtn) manualBtn.style.display = scenario ? 'none' : '';
    if (playbackBtn) {
      playbackBtn.style.display = scenario ? '' : 'none';
      playbackBtn.textContent = state.networkPlaybackPaused ? '恢复展示' : '暂停播放';
    }
    if (resetBtn) resetBtn.style.display = scenario ? '' : 'none';
    if (simulateBtn) simulateBtn.style.display = scenario ? '' : 'none';
  }

  // ── Entry ──
  function renderNetwork() {
    updateNetworkControls();
    if (scenarioMode()) {
      if (!state.networkLinksCopy.length) syncScenarioNetworkState();
      renderSensingHeader();
      renderSensingNodes();
      renderSensingLinks();
      renderFaultAlerts();
      renderSensingCharts();
      renderStorageNodes();
      renderStorageSummary();
      renderSwitchHistory();
      renderBottomMetrics();
      renderNetworkTopology();
      renderEventTimeline();
      if (!state.networkPlaybackPaused) startNetworkPlayback();
      return;
    }

    loadSensingFromLocalStorage();
    showLoading('sd-nodes-grid');
    showLoading('sd-links-list');
    showLoading('sd-storage-grid');
    showLoading('sd-alerts-panel');

    fetchMonitoringNodes().then(function(data) {
      state.liveMonitoringNodes = window.ComputeAdapters
        ? window.ComputeAdapters.adaptMonitoringNodes(data.nodes || [])
        : [];
      state.sensingNodesCopy = sensingNodesFromScene(state.liveMonitoringNodes);
      buildLiveScene();
      hideLoading('sd-nodes-grid');
      renderSensingNodes();
      renderBottomMetrics();
      renderNetworkTopology();
      if (state.activeTab === 'overview') renderOverview();
    });

    fetchNetworkLinks().then(function(data) {
      state.networkLinksCopy = window.ComputeAdapters
        ? window.ComputeAdapters.adaptMonitoringLinks(data.links || [])
        : [];
      buildLiveScene();
      hideLoading('sd-links-list');
      renderSensingLinks();
      renderSensingCharts();
      renderBottomMetrics();
      renderNetworkTopology();
      if (state.activeTab === 'overview') renderOverview();
    });

    fetchMonitoringSamples(20).then(function(data) {
      state.networkSamplesCopy = window.ComputeAdapters
        ? window.ComputeAdapters.adaptMonitoringSamples(data.samples || [])
        : { labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: [] };
      renderSensingCharts();
    });

    fetchStorageData().then(function(data) {
      state.storageNodesCopy = window.ComputeAdapters
        ? window.ComputeAdapters.adaptStorage(data.targets || [], data.summary || {})
        : [];
      hideLoading('sd-storage-grid');
      renderStorageNodes();
      renderStorageSummary();
    });

    fetchAlerts('open', 20).then(function(data) {
      state.faultAlertsCopy = window.ComputeAdapters
        ? window.ComputeAdapters.adaptAlerts(data.items || [])
        : [];
      buildLiveScene();
      hideLoading('sd-alerts-panel');
      renderFaultAlerts();
      renderSensingHeader();
      renderEventTimeline();
      renderBottomMetrics();
      if (state.activeTab === 'overview') renderOverview();
    });

    renderSensingHeader();
    renderSwitchHistory();
    renderSensingCharts();
    renderNetworkTopology();
    renderEventTimeline();
    renderBottomMetrics();

    if (state.activeTab === 'network' && state.isNetworkAutoRefresh) {
      startMonitoring();
      startClockTimer();
    } else {
      stopMonitoring();
    }
  }

  function toggleNetworkRefresh() {
    if (scenarioMode()) return;
    var cb = document.getElementById('sd-auto-refresh');
    state.isNetworkAutoRefresh = cb ? cb.checked : !state.isNetworkAutoRefresh;
    if (state.isNetworkAutoRefresh && state.activeTab === 'network') {
      startMonitoring();
    } else {
      stopMonitoring();
    }
    saveSensingToLocalStorage();
    renderSensingHeader();
  }

  function manualNetworkRefresh() {
    if (scenarioMode()) {
      refreshAllDisplay();
      showToast('场景数据已刷新', 'info');
      return;
    }
    refreshMonitoringData();
    state.networkRefreshCountdown = 5;
    showToast('感知数据已刷新', 'info');
  }

  function renderNetworkTopology() {
    var container = $('sd-topology');
    if (!container) return;
    var topology = scenarioMode() ? sceneData().topology : null;
    if (!topology || !topology.nodes || !topology.nodes.length) {
      container.innerHTML = '<div class="cp-chart-empty">' +
        (scenarioMode() ? '暂无拓扑数据' : '暂无真实拓扑数据') + '</div>';
      return;
    }
    var nodeMap = {};
    topology.nodes.forEach(function(node) { nodeMap[node.id] = node; });
    var linkMap = {};
    (state.networkLinksCopy || []).forEach(function(link) { linkMap[link.id] = link; });
    var width = topology.width || 560;
    var height = topology.height || 300;
    var svg = '<svg class="sd-topology-svg" viewBox="0 0 ' + width + ' ' + height +
      '" role="img" aria-label="网络拓扑图">';
    (topology.links || []).forEach(function(link) {
      var from = nodeMap[link.source];
      var to = nodeMap[link.target];
      if (!from || !to) return;
      var networkLink = linkMap[link.id] || {};
      var status = networkLink.status || 'normal';
      svg += '<line class="sd-topo-link status-' + escapeHtml(status) + '" x1="' +
        from.x + '" y1="' + from.y + '" x2="' + to.x + '" y2="' + to.y + '">' +
        '<title>' + escapeHtml(networkLink.name || link.id) + ' · ' +
        escapeHtml(status) + '</title></line>';
    });
    (topology.nodes || []).forEach(function(node) {
      var networkNode = null;
      for (var i = 0; i < state.sensingNodesCopy.length; i += 1) {
        if (state.sensingNodesCopy[i].id === node.id) {
          networkNode = state.sensingNodesCopy[i];
          break;
        }
      }
      var status = networkNode ? networkNode.status : (node.status || 'normal');
      svg += '<g class="sd-topo-node status-' + escapeHtml(status) +
        '" data-node-id="' + escapeHtml(node.id) + '" tabindex="0" role="button">' +
        '<circle cx="' + node.x + '" cy="' + node.y + '" r="18"></circle>' +
        '<text x="' + node.x + '" y="' + (node.y + 33) + '" text-anchor="middle">' +
        escapeHtml(node.name) + '</text></g>';
    });
    svg += '</svg>';
    container.innerHTML = svg;
    var nodes = container.querySelectorAll('.sd-topo-node');
    for (var n = 0; n < nodes.length; n += 1) {
      nodes[n].addEventListener('click', function() {
        showTopologyNodeDetail(this.getAttribute('data-node-id'));
      });
      nodes[n].addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          showTopologyNodeDetail(this.getAttribute('data-node-id'));
        }
      });
    }
  }

  function renderEventTimeline() {
    var container = $('sd-event-timeline');
    if (!container) return;
    var events = state.eventsCopy || [];
    if (state.networkScenarioFault && sceneData().faultScenario) {
      events = events.concat(sceneData().faultScenario.timeline || []);
    }
    if (!events.length) {
      container.innerHTML = '<div class="sd-alerts-empty">暂无事件记录</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < events.length; i += 1) {
      var event = events[i];
      h += '<div class="sd-event-item level-' + escapeHtml(event.level || 'info') + '">' +
        '<span class="sd-event-time">' + escapeHtml(event.time || '—') + '</span>' +
        '<span class="sd-event-text">' + escapeHtml(event.text || '') + '</span></div>';
    }
    container.innerHTML = h;
  }

  function showNodeDetail(nodeId) {
    var nodes = state.sensingNodesCopy || [];
    var node = null;
    for (var i = 0; i < nodes.length; i += 1) {
      if (nodes[i].id === nodeId) { node = nodes[i]; break; }
    }
    if (!node) return;
    var status = statusLabel(node.status);
    var h = '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">名称</div><div class="cp-detail-value">' + escapeHtml(node.name) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 型号</div><div class="cp-detail-value">' + escapeHtml(node.gpuModel || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 利用率</div><div class="cp-detail-value">' + valueOrDash(node.gpuUtil, '%') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">VRAM 利用率</div><div class="cp-detail-value">' + valueOrDash(node.vramUtil, '%') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">温度</div><div class="cp-detail-value">' + valueOrDash(node.temp, '°C') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">当前任务</div><div class="cp-detail-value">' + escapeHtml(node.currentTask || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">心跳</div><div class="cp-detail-value">' + escapeHtml(node.heartbeat || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">状态</div><div class="cp-detail-value">' + badge(status, 'status-' + node.status) + '</div></div>' +
      '</div>';
    showDetailDrawer(node.name + ' - 节点详情', h);
  }

  function showNetworkLinkDetail(linkId) {
    var links = state.networkLinksCopy || [];
    var link = null;
    for (var i = 0; i < links.length; i += 1) {
      if (links[i].id === linkId) { link = links[i]; break; }
    }
    if (!link) return;
    var h = '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">链路</div><div class="cp-detail-value">' + escapeHtml(link.name || link.id) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">路径</div><div class="cp-detail-value">' + escapeHtml((link.sourceName || link.source) + ' → ' + (link.targetName || link.target)) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">状态</div><div class="cp-detail-value">' + escapeHtml(link.status || '—') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">时延</div><div class="cp-detail-value">' + valueOrDash(link.latencyMs, ' ms') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">抖动</div><div class="cp-detail-value">' + valueOrDash(link.jitterMs, ' ms') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">丢包率</div><div class="cp-detail-value">' + valueOrDash(link.packetLossPct, '%') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">带宽</div><div class="cp-detail-value">' + valueOrDash(link.bandwidthGbps, ' Gbps') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">吞吐</div><div class="cp-detail-value">' + valueOrDash(link.throughputGbps, ' Gbps') + '</div></div>' +
      '</div>';
    showDetailDrawer('链路详情: ' + (link.name || link.id), h);
  }

  function showTopologyNodeDetail(nodeId) {
    var nodes = state.sensingNodesCopy || [];
    for (var i = 0; i < nodes.length; i += 1) {
      if (nodes[i].id === nodeId) { showNodeDetail(nodeId); return; }
    }
    var storages = state.storageNodesCopy || [];
    for (var j = 0; j < storages.length; j += 1) {
      if (storages[j].id === nodeId) {
        var storage = storages[j];
        showDetailDrawer('存储详情: ' + (storage.name || nodeId),
          '<div class="cp-detail-grid">' +
          '<div class="cp-detail-group"><div class="cp-detail-label">名称</div><div class="cp-detail-value">' + escapeHtml(storage.name || '—') + '</div></div>' +
          '<div class="cp-detail-group"><div class="cp-detail-label">已用 / 容量</div><div class="cp-detail-value">' +
          valueOrDash(storage.usedTB, ' TB') + ' / ' + valueOrDash(storage.capacityTB, ' TB') + '</div></div>' +
          '<div class="cp-detail-group"><div class="cp-detail-label">读吞吐</div><div class="cp-detail-value">' + valueOrDash(storage.readMBps, ' MB/s') + '</div></div>' +
          '<div class="cp-detail-group"><div class="cp-detail-label">写吞吐</div><div class="cp-detail-value">' + valueOrDash(storage.writeMBps, ' MB/s') + '</div></div>' +
          '</div>');
        return;
      }
    }
  }

  // ── Fault Simulation ──
  // ── Fault Simulation ──
  function applyShowcaseFault() {
    if (!scenarioMode()) {
      showToast('当前环境不可注入故障场景', 'warning');
      return;
    }
    if (state.networkScenarioFault) {
      showToast('故障场景已处于激活状态', 'info');
      return;
    }
    var scenario = sceneData().faultScenario;
    if (!scenario) {
      showToast('暂无可用的故障参考场景', 'warning');
      return;
    }
    state.networkFaultSnapshot = {
      links: cloneData(state.networkLinksCopy),
      alerts: cloneData(state.faultAlertsCopy),
      events: cloneData(state.eventsCopy),
      switchRecords: cloneData(state.switchRecordsCopy)
    };
    var links = state.networkLinksCopy || [];
    for (var i = 0; i < links.length; i += 1) {
      if (links[i].id === scenario.linkId) {
        links[i].latencyMs = scenario.degraded.latencyMs;
        links[i].jitterMs = scenario.degraded.jitterMs;
        links[i].packetLossPct = scenario.degraded.packetLossPct;
        links[i].bandwidthGbps = scenario.degraded.bandwidthGbps;
        links[i].throughputGbps = scenario.degraded.throughputGbps;
        links[i].status = scenario.degraded.status;
        links[i].health = scenario.degraded.health;
        break;
      }
    }
    var alert = cloneData(scenario.alert || {});
    alert.status = 'active';
    alert.time = 'S7';
    alert.confirmed = false;
    alert.recoveryStatus = 'switching';
    state.faultAlertsCopy.unshift(alert);
    state.switchRecordsCopy.unshift({
      id: 'switch-showcase-link',
      time: 'S7',
      type: '链路降级切换',
      source: scenario.linkName,
      target: '备用链路',
      reason: '时延与丢包率超过参考阈值',
      duration: 2.6,
      result: '切换中'
    });
    state.networkScenarioFault = true;
    refreshAllDisplay();
    renderSensingHeader();
    showToast('故障场景已触发', 'warning');
  }

  function showFaultSimModal() {
    applyShowcaseFault();
  }

  function closeFaultSimModal() {
    var overlay = document.getElementById('sd-fault-modal');
    if (overlay) overlay.classList.remove('open');
  }

  function startFaultSimulation() {
    closeFaultSimModal();
    cancelFaultSimulation();
    state.faultSimActive = true;

    var targetSel = document.getElementById('sd-fault-target');
    var typeSel = document.getElementById('sd-fault-type');
    var targetId = targetSel ? targetSel.value : 'sn-005';
    var faultType = typeSel ? typeSel.value : 'gpu_overheat';

    showToast('故障模拟已启动: ' + faultType, 'warning');

    // Stage 1: warning (0s - immediate)
    simulateFaultEvent(targetId, faultType, 'warning');

    // Stage 2: detecting (3s)
    state.faultSimTimers.push(setTimeout(function() {
      simulateFaultEvent(targetId, faultType, 'detecting');
    }, 3000));

    // Stage 3: switching (6s)
    state.faultSimTimers.push(setTimeout(function() {
      simulateFaultEvent(targetId, faultType, 'switching');
      addSwitchRecord(targetId, faultType);
    }, 6000));

    // Stage 4: recovered (15s)
    state.faultSimTimers.push(setTimeout(function() {
      simulateFaultEvent(targetId, faultType, 'recovered');
      state.faultSimActive = false;
      showToast('故障模拟已完成，请确认恢复', 'success');
    }, 15000));
  }

  function simulateFaultEvent(targetId, faultType, stage) {
    // Handle GPU nodes
    var nodes = state.sensingNodesCopy;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id === targetId) {
        if (stage === 'warning') {
          nodes[i].status = 'abnormal';
          nodes[i].gpuUtil = Math.min(100, nodes[i].gpuUtil + 15);
          nodes[i].temp = Math.min(95, nodes[i].temp + 20);
        } else if (stage === 'switching') {
          nodes[i].status = 'switching';
          // Set the backup node
          var backupName = nodes[i].id === 'sn-005' ? '备份节点-01' : ('备用-' + nodes[i].name);
          // Add fault alert
          state.faultAlertsCopy.unshift({
            id: 'fa-sim-' + Date.now(),
            level: 'critical',
            type: faultType.indexOf('gpu') >= 0 ? 'gpu' : (faultType.indexOf('link') >= 0 ? 'link' : 'storage'),
            targetId: targetId,
            targetName: nodes[i].name,
            reason: faultType === 'gpu_overheat' ? 'GPU温度超过阈值，触发过热保护' : (faultType === 'node_offline' ? '节点心跳丢失，触发故障转移' : '故障触发自动切换'),
            time: formatTime(new Date()),
            autoRecovery: true,
            recoveryStatus: 'switching',
            standbyNode: backupName,
            confirmed: false,
            isDemo: true
          });
        } else if (stage === 'recovered') {
          nodes[i].status = 'normal';
          nodes[i].gpuUtil = Math.round(Math.max(10, nodes[i].gpuUtil - 25));
          nodes[i].temp = Math.round(Math.max(40, nodes[i].temp - 15));
        }
        break;
      }
    }

    // Handle links
    var links = state.networkLinksCopy;
    for (var j = 0; j < links.length; j++) {
      if (links[j].id === targetId) {
        if (stage === 'warning') {
          links[j].status = 'congested';
          links[j].packetLoss = parseFloat((links[j].packetLoss + 0.5).toFixed(3));
          links[j].latency = Math.round(links[j].latency * 3);
        } else if (stage === 'switching') {
          links[j].status = 'unstable';
          state.faultAlertsCopy.unshift({
            id: 'fa-sim-' + Date.now(),
            level: 'warning',
            type: 'link',
            targetId: targetId,
            targetName: links[j].name || links[j].source + ' → ' + links[j].target,
            reason: '链路丢包率超过阈值，正在切换备用路径',
            time: formatTime(new Date()),
            autoRecovery: true,
            recoveryStatus: 'switching',
            standbyNode: '备用链路',
            confirmed: false,
            isDemo: true
          });
        } else if (stage === 'recovered') {
          links[j].status = 'normal';
          links[j].packetLoss = parseFloat((links[j].packetLoss * 0.2).toFixed(3));
          links[j].latency = Math.round(links[j].latency * 0.4);
        }
        break;
      }
    }

    // Handle storage
    var storages = state.storageNodesCopy;
    for (var k = 0; k < storages.length; k++) {
      if (storages[k].id === targetId) {
        if (stage === 'warning') {
          storages[k].status = 'warning';
          storages[k].readMBps = Math.round(storages[k].readMBps * 0.5);
          storages[k].writeMBps = Math.round(storages[k].writeMBps * 0.4);
        } else if (stage === 'switching') {
          state.faultAlertsCopy.unshift({
            id: 'fa-sim-' + Date.now(),
            level: 'warning',
            type: 'storage',
            targetId: targetId,
            targetName: storages[k].name,
            reason: '存储I/O错误，正在故障转移',
            time: formatTime(new Date()),
            autoRecovery: true,
            recoveryStatus: 'switching',
            standbyNode: 'SSD存储阵列-04',
            confirmed: false,
            isDemo: true
          });
        } else if (stage === 'recovered') {
          storages[k].status = 'normal';
          storages[k].readMBps = Math.round(storages[k].readMBps * 2.2);
          storages[k].writeMBps = Math.round(storages[k].writeMBps * 2.5);
        }
        break;
      }
    }

    // Mark existing alerts for this target as recovered
    if (stage === 'recovered') {
      var alerts = state.faultAlertsCopy;
      for (var a = 0; a < alerts.length; a++) {
        if (alerts[a].targetId === targetId && alerts[a].recoveryStatus !== 'recovered') {
          alerts[a].recoveryStatus = 'recovered';
        }
      }
    }

    refreshAllDisplay();
    renderSensingHeader();
  }

  function addSwitchRecord(targetId, faultType) {
    var targetObj = null;
    var sourcetext = targetId;
    var nodes = state.sensingNodesCopy;
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].id === targetId) { targetObj = nodes[i]; break; }
    }
    var links = state.networkLinksCopy;
    for (var j = 0; j < links.length; j++) {
      if (links[j].id === targetId) { targetObj = links[j]; break; }
    }
    var storages = state.storageNodesCopy;
    for (var k = 0; k < storages.length; k++) {
      if (storages[k].id === targetId) { targetObj = storages[k]; break; }
    }
    if (targetObj) sourcetext = targetObj.name || targetId;
    var record = {
      id: 'sw-sim-' + Date.now(),
      time: formatTime(new Date()),
      type: faultType === 'gpu_overheat' ? 'GPU过热切换' : (faultType === 'link_degrade' ? '链路降级切换' : (faultType === 'storage_corrupt' ? '存储故障转移' : '节点离线切换')),
      source: sourcetext,
      target: faultType === 'storage_corrupt' ? 'SSD存储阵列-04' : '备用节点',
      reason: faultType === 'gpu_overheat' ? 'GPU温度超过阈值' : (faultType === 'link_degrade' ? '丢包率超阈值' : (faultType === 'storage_corrupt' ? '磁盘I/O错误' : '节点心跳丢失')),
      duration: parseFloat((3.5).toFixed(1)),
      result: '成功',
      isDemo: false
    };
    state.switchRecordsCopy.unshift(record);
    // Keep max 5
    while (state.switchRecordsCopy.length > 5) { state.switchRecordsCopy.pop(); }
    saveSensingToLocalStorage();
  }

  function cancelFaultSimulation() {
    for (var t = 0; t < state.faultSimTimers.length; t++) {
      clearTimeout(state.faultSimTimers[t]);
    }
    state.faultSimTimers = [];
    state.faultSimActive = false;
  }

  function confirmAlertRecovery(alertId) {
    var alerts = state.faultAlertsCopy;
    for (var i = 0; i < alerts.length; i++) {
      if (alerts[i].id === alertId) {
        alerts[i].confirmed = true;
        // Write to ops events
        state.opsEvents.unshift({
          id: 'ev-fault-rec-' + Date.now(),
          alertId: alertId,
          action: '故障恢复确认',
          timestamp: formatTime(new Date()),
          description: '故障' + alerts[i].targetName + ' 恢复已确认，系统正常',
          isDemo: true
        });
        // Remove from fault alerts
        state.faultAlertsCopy.splice(i, 1);
        break;
      }
    }
    saveToLocalStorage();
    saveSensingToLocalStorage();
    if (scenarioMode() && state.networkScenarioFault) {
      resetNetworkScenario();
      showToast('故障恢复已确认', 'success');
      return;
    }
    refreshAllDisplay();
    renderSensingHeader();
    showToast('故障恢复已确认', 'success');
  }

  function resolveAlert(alertId) {
    var alerts = state.faultAlertsCopy;
    for (var i = 0; i < alerts.length; i++) {
      if (alerts[i].id === alertId) {
        state.faultAlertsCopy.splice(i, 1);
        break;
      }
    }
    saveSensingToLocalStorage();
    if (scenarioMode() && state.networkScenarioFault) {
      resetNetworkScenario();
      showToast('告警已忽略', 'info');
      return;
    }
    refreshAllDisplay();
    renderSensingHeader();
    showToast('告警已忽略', 'info');
  }

  function handleSimulateAnomaly() {
    showFaultSimModal();
  }

  // ══════════════════════════════════════════════════
  // Tab 6: Permissions & Security
  // ══════════════════════════════════════════════════
  function renderPermissions() {
    var container = $('cp-perms-table');
    if (container) {
      container.innerHTML = '<p class="empty-state">加载中...</p>';
    }
    window.AIGV.getCurrentUser().then(function (user) {
      var caps = (user && user.capabilities) || {};
      if (!user || !caps.is_admin) {
        if (container) {
          container.innerHTML = '<div class="empty-state-container">' +
            '<h3 class="empty-title">仅平台管理员可查看成员权限</h3>' +
            '<p class="empty-desc">项目成员权限由管理员在服务端管理；普通用户只能管理自己的项目。</p>' +
            '</div>';
        }
        renderSecurityCards();
        return;
      }
      loadPermissions().then(function (result) {
        renderPermsTable(result.members, result.project);
        renderSecurityCards();
      }).catch(function (error) {
        if (container) {
          container.innerHTML = '<div class="empty-state-container">' +
            '<h3 class="empty-title">权限数据加载失败</h3>' +
            '<p class="empty-desc">' + escapeHtml((error && error.message) || '请稍后重试') + '</p>' +
            '</div>';
        }
        renderSecurityCards();
      });
    }).catch(function () {
      if (container) {
        container.innerHTML = '<p class="empty-state">无法获取当前账户信息</p>';
      }
    });
  }

  function loadPermissions() {
    return api('/api/demo/context').then(function (context) {
      var projects = (context && context.available_projects) || [];
      var project = (context && context.project) || projects[0] || null;
      if (!project || !project.id) {
        return { members: [], project: null };
      }
      return api('/api/projects/' + encodeURIComponent(project.id) + '/members')
        .then(function (data) {
          return {
            members: (data && data.members) || data || [],
            project: project
          };
        });
    });
  }

  function renderPermsTable(members, project) {
    var container = $('cp-perms-table');
    if (!container) return;
    members = members || [];
    if (!members.length) {
      container.innerHTML = '<div class="empty-state-container">' +
        '<h3 class="empty-title">暂无项目成员</h3>' +
        '<p class="empty-desc">当前账户还没有可查看的项目成员记录。</p></div>';
      return;
    }

    var permLabels = {
      submit_job: '提交任务', generate_media: '生成素材', manage_own_projects: '管理个人项目',
      view_compute: '查看算力', manage_compute: '管理算力', submit_render_job: '提交渲染',
      manage_cloud_accounts: '云账户管理', view_billing: '查看费用', view_monitor: '查看监控',
      approve_rights: '版权审批', view_billing_global: '全局费用', admin: '平台管理员'
    };
    var roleLabels = { owner: '项目所有者', admin: '项目管理员', editor: '编辑', viewer: '只读' };

    var h = '<div class="cp-detail-label" style="margin-bottom:8px">项目：' +
      escapeHtml((project && project.name) || '—') + '</div>';
    h += '<table class="cp-table cp-perms-table"><thead><tr>' +
      '<th>成员</th><th>用户名</th><th>项目角色</th><th>权限</th><th>加入时间</th>' +
      '</tr></thead><tbody>';
    for (var i = 0; i < members.length; i += 1) {
      var member = members[i] || {};
      var user = member.user || {};
      var permissions = member.permissions || [];
      if (typeof permissions === 'string') {
        try { permissions = JSON.parse(permissions); } catch (e) { permissions = []; }
      }
      var permissionText = permissions.length
        ? permissions.map(function (permission) { return permLabels[permission] || permission; }).join('、')
        : '—';
      h += '<tr>' +
        '<td>' + escapeHtml(user.nickname || user.name || member.user_id || '—') + '</td>' +
        '<td>' + escapeHtml(user.username || '—') + '</td>' +
        '<td>' + escapeHtml(roleLabels[member.role] || member.role || '—') + '</td>' +
        '<td>' + escapeHtml(permissionText) + '</td>' +
        '<td>' + escapeHtml(AIGV.formatTime(member.created_at)) + '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';
    h += '<p class="field-hint">权限为只读展示；尚无可用的在线编辑接口，请在服务端管理。</p>';
    container.innerHTML = h;
  }

  function renderSecurityCards() {
    var cards = [
      { icon: '&#9679;', status: 'safe', label: '登录安全', desc: '服务端 Session + CSRF 保护' },
      { icon: '&#9679;', status: 'safe', label: 'API 密钥', desc: '仅通过服务端环境变量配置' },
      { icon: '&#9679;', status: 'warn', label: '传输加密', desc: '是否启用取决于 HTTPS/反向代理配置' },
      { icon: '&#9679;', status: 'safe', label: '操作审计', desc: '认证与管理员操作写入 ops_events' },
      { icon: '&#9679;', status: 'warn', label: '素材版权', desc: '版权数据需配置后使用' },
      { icon: '&#9679;', status: 'warn', label: '数据备份', desc: '未接入自动备份状态展示' }
    ];

    var statusLabels = { safe: '正常', warn: '关注', danger: '异常' };

    var grid = $('cp-security-cards');
    if (!grid) return;
    var h = '';
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      h += '<div class="cp-security-card">' +
        '<div class="cp-security-icon ' + c.status + '">' + c.icon + '</div>' +
        '<div><div class="cp-security-label">' + escapeHtml(c.label) + '</div>' +
        '<div class="cp-security-status">' + escapeHtml(c.desc) + ' (' + statusLabels[c.status] + ')</div></div>' +
        '</div>';
    }
    grid.innerHTML = h;
  }

  // ══════════════════════════════════════════════════
  // Tab 7: Billing & Alerts
  // ══════════════════════════════════════════════════
  function renderBilling() {
    if (window.AIGVArk && window.AIGVArk.renderBilling) window.AIGVArk.renderBilling();
    renderCostSummary();
    renderAlertTable();
    renderOpsTable();
  }

  function renderCostSummary() {
    var d = state.demoData;
    var b = state.apiBilling || {};
    var demoMode = !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
    var total = b.total_amount;
    if ((total === undefined || total === null) && demoMode && d && d.billingRecords && d.billingRecords.length) {
      total = d.billingRecords[0].dailyCost;
    }
    if (total === undefined || total === null) total = 0;
    var accounts = b.accounts || [];

    var grid = $('cp-cost-grid');
    if (!grid) return;

    var accountBalances = '';
    for (var i = 0; i < accounts.length; i++) {
      var acct = accounts[i];
      accountBalances += '<div class="cp-cost-breakdown-item"><div class="cp-cost-bd-label">' + escapeHtml(acct.plan_name || '账户') + '</div><div class="cp-cost-bd-value">¥' + (acct.balance || 0).toFixed(0) + '</div></div>';
    }
    if (!accountBalances) {
      accountBalances = '<div class="cp-cost-breakdown-item"><div class="cp-cost-bd-label">未配置</div><div class="cp-cost-bd-value">-</div></div>';
    }

    var html =
      '<div class="cp-cost-card"><div class="cp-cost-label">内部核算累计（全部历史）</div><div class="cp-cost-value">' + ((typeof total === 'number') ? total.toFixed(2) : total) + '<span class="cp-cost-unit"> 元</span></div><div class="cp-cost-hint">AIGV 内部 GPU/渲染估算，非火山官方账单</div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">活跃渲染任务</div><div class="cp-cost-value">' + (b.render_stats ? b.render_stats.active_render_jobs || 0 : 0) + '<span class="cp-cost-unit"> 个</span></div><div class="cp-cost-hint">平台内部渲染队列</div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">总渲染任务</div><div class="cp-cost-value">' + (b.render_stats ? b.render_stats.total_render_jobs || 0 : 0) + '<span class="cp-cost-unit"> 个</span></div><div class="cp-cost-hint">平台内部渲染记录</div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">内部核算余额（非火山账户）</div>' +
      '<div class="cp-cost-breakdown">' + accountBalances + '</div><div class="cp-cost-hint">不代表火山引擎资金账户余额</div></div>';

    grid.innerHTML = html;
  }

  function renderAlertTable() {
    var alerts = state.alerts;
    var levelLabels = { info: '信息', warning: '警告', error: '错误', critical: '严重' };
    var statusLabels = { active: '活跃', acknowledged: '已确认', processing: '处理中', resolved: '已解决', closed: '已关闭' };

    var h = '<table class="cp-table cp-alert-table"><thead><tr>' +
      '<th>级别</th><th>类型</th><th>节点</th><th>内容</th><th>时间</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>';

    for (var i = 0; i < alerts.length; i++) {
      var a = alerts[i];
      var actions = '';
      if (a.status === 'active') {
        actions = '<button class="cp-action-btn" onclick="ComputePlatform.handleAcknowledgeAlert(\'' + escapeHtml(a.id) + '\')">确认</button>' +
                  '<button class="cp-action-btn" onclick="ComputePlatform.handleMarkProcessing(\'' + escapeHtml(a.id) + '\')">处理中</button>' +
                  '<button class="cp-action-btn danger" onclick="ComputePlatform.handleCloseAlert(\'' + escapeHtml(a.id) + '\')">关闭</button>';
      } else if (a.status === 'acknowledged') {
        actions = '<button class="cp-action-btn" onclick="ComputePlatform.handleMarkProcessing(\'' + escapeHtml(a.id) + '\')">处理中</button>' +
                  '<button class="cp-action-btn danger" onclick="ComputePlatform.handleCloseAlert(\'' + escapeHtml(a.id) + '\')">关闭</button>';
      } else if (a.status === 'processing') {
        actions = '<button class="cp-action-btn danger" onclick="ComputePlatform.handleCloseAlert(\'' + escapeHtml(a.id) + '\')">关闭</button>';
      } else {
        actions = '<span style="color:var(--text-soft);font-size:0.78rem">已完成</span>';
      }

      h += '<tr>' +
        '<td>' + badge(levelLabels[a.level] || a.level, a.level) + '</td>' +
        '<td>' + escapeHtml(a.type) + '</td>' +
        '<td>' + escapeHtml(a.node) + '</td>' +
        '<td>' + escapeHtml(a.content) + '</td>' +
        '<td>' + escapeHtml(a.time) + '</td>' +
        '<td>' + badge(statusLabels[a.status] || a.status, a.status) + '</td>' +
        '<td>' + actions + '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';

    var container = $('cp-alert-table');
    if (container) container.innerHTML = h;
  }

  function renderOpsTable() {
    // Prefer API ops events, fall back to local state
    var apiEvents = state.apiOpsEvents || [];
    var localEvents = state.opsEvents || [];
    var events = apiEvents.length > 0 ? apiEvents : localEvents;

    var h = '<table class="cp-table"><thead><tr>' +
      '<th>事件类型</th><th>严重级别</th><th>时间</th><th>消息</th>' +
      '</tr></thead><tbody>';

    if (apiEvents.length > 0) {
      for (var i = 0; i < events.length; i++) {
        var ev = events[i];
        var ts = ev.created_at ? new Date(ev.created_at * 1000).toISOString().slice(0, 19).replace('T', ' ') : '--';
        var severityBadge = '<span class="ch-badge-' + (ev.severity === 'error' ? 'error' : ev.severity === 'warning' ? 'maintenance' : 'running') + '">' + escapeHtml(ev.severity || 'info') + '</span>';
        h += '<tr>' +
          '<td>' + escapeHtml(ev.event_type || '--') + '</td>' +
          '<td>' + severityBadge + '</td>' +
          '<td>' + escapeHtml(ts) + '</td>' +
          '<td>' + escapeHtml(ev.message || '') + '</td>' +
          '</tr>';
      }
    } else {
      for (var j = 0; j < events.length; j++) {
        var ev2 = events[j];
        h += '<tr>' +
          '<td>' + escapeHtml(ev2.action || ev2.event_type || '--') + '</td>' +
          '<td>' + escapeHtml(ev2.severity || 'info') + '</td>' +
          '<td>' + escapeHtml(ev2.timestamp || ev2.created_at || '--') + '</td>' +
          '<td>' + escapeHtml(ev2.description || ev2.message || '') + '</td>' +
          '</tr>';
      }
    }
    h += '</tbody></table>';

    var container = $('cp-ops-table');
    if (container) container.innerHTML = h;
  }

  function handleAcknowledgeAlert(id) {
    changeAlertStatus(id, 'acknowledged');
    showToast('告警 ' + id + ' 已确认', 'info');
  }

  function handleMarkProcessing(id) {
    changeAlertStatus(id, 'processing');
    showToast('告警 ' + id + ' 处理中', 'info');
  }

  function handleCloseAlert(id) {
    changeAlertStatus(id, 'closed');
    showToast('告警 ' + id + ' 已关闭', 'success');
  }

  function changeAlertStatus(id, newStatus) {
    for (var i = 0; i < state.alerts.length; i++) {
      if (state.alerts[i].id === id) {
        var oldStatus = state.alerts[i].status;
        state.alerts[i].status = newStatus;

        // Add ops event
        var now = new Date();
        var ts = now.getFullYear() + '-' +
          String(now.getMonth() + 1).padStart(2, '0') + '-' +
          String(now.getDate()).padStart(2, '0') + ' ' +
          String(now.getHours()).padStart(2, '0') + ':' +
          String(now.getMinutes()).padStart(2, '0') + ':' +
          String(now.getSeconds()).padStart(2, '0');
        var actionMap = { acknowledged: '告警确认', processing: '开始处理', closed: '告警关闭' };
        state.opsEvents.unshift({
          id: 'ev-' + Date.now(),
          alertId: id,
          action: actionMap[newStatus] || '状态变更',
          timestamp: ts,
          description: '告警 ' + id + ' 状态从 ' + oldStatus + ' 变更为 ' + newStatus,
          isDemo: true
        });
        break;
      }
    }
    saveToLocalStorage();
    renderBilling();
  }

  // ══════════════════════════════════════════════════
  // Real Data Loading
  // ══════════════════════════════════════════════════
  function loadRealData() {
    // Load resource summary
    api('/api/resources/summary').then(function(summary) {
      state.apiSummary = summary || {};
      if (!scenarioMode()) buildLiveScene();
      updateStatusBar();
      renderOverviewIfActive();
      if (state.activeTab === 'gpu') renderGPU();
    }).catch(function(err) {
      console.error('资源摘要加载失败:', err);
      showToast('资源摘要加载失败', 'warning');
    });

    // Load hosts (GPU scheduling tab)
    api('/api/cloud/hosts?limit=200').then(function(hostsData) {
      state.apiHosts = hostsData || {};
      if (!scenarioMode()) buildLiveScene();
      if (state.activeTab === 'gpu') renderGPU();
      if (state.activeTab === 'overview') renderOverview();
    }).catch(function(err) {
      console.error('GPU主机数据加载失败:', err);
    });

    // Load billing summary
    api('/api/billing/summary').then(function(billing) {
      state.apiBilling = billing || {};
      if (state.activeTab === 'billing') renderBilling();
    }).catch(function(err) {
      console.error('账单摘要加载失败:', err);
    });

    // Load alerts (real data only; no demo fallback in production)
    api('/api/alerts?limit=50').then(function(alerts) {
      state.alerts = (alerts && alerts.items) || [];
      if (state.activeTab === 'billing') renderBilling();
    }).catch(function(err) {
      console.error('告警数据加载失败:', err);
      state.alerts = [];
    });

    // Load ops events
    api('/api/ops/events?limit=50').then(function(events) {
      state.apiOpsEvents = events || [];
      if (state.activeTab === 'billing') renderBilling();
    }).catch(function(err) {
      console.error('运维事件加载失败:', err);
    });

    // Load render jobs
    api('/api/render/jobs?limit=50').then(function(render) {
      state.apiRenderJobs = render || {};
      if (!scenarioMode()) buildLiveScene();
      if (state.activeTab === 'overview') renderOverview();
      if (state.activeTab === 'rendering' && state.renderSubTab === 'sessions') {
        renderSessionsSubTab();
      }
    }).catch(function(err) {
      console.error('渲染任务加载失败:', err);
    });
  }

  function renderOverviewIfActive() {
    if (state.activeTab === 'overview') renderOverview();
  }

  function updateStatusBar() {
    var demoStatus = $('demo-data-status');
    if (!demoStatus) return;
    var overview = scenarioMode() ? (sceneData().overview || {}) : {};
    var summary = state.apiSummary || {};
    var nodes = scenarioMode()
      ? (overview.totalNodes || 0) : (summary.total_nodes || 0);
    var online = scenarioMode()
      ? (overview.onlineNodes || 0) : (summary.online_nodes || 0);
    var queue = scenarioMode()
      ? (overview.queueDepth || 0) : (summary.queue_depth || 0);
    demoStatus.textContent = '算力节点：共 ' + nodes + ' 台，在线 ' + online + ' 台，排队 ' + queue + ' 个任务';
  }

  // ══════════════════════════════════════════════════
  // Initialization
  // ══════════════════════════════════════════════════
  function init() {
    var demoMode = demoEnabled();
    var data = demoMode ? (window.AIGV_DEMO_DATA || {}) : {};
    state.demoData = data;
    state.sceneSource = showcaseMode() ? 'showcase' : (demoMode ? 'demo' : 'live');

    if (showcaseMode()) {
      state.scene = window.AIGV_COMPUTE_SHOWCASE;
    } else if (demoMode && window.ComputeAdapters) {
      state.scene = window.ComputeAdapters.sceneFromDemo(
        data, window.AIGV_COMPUTE_SHOWCASE || {}
      );
    } else {
      state.scene = {
        source: 'live',
        nodes: [],
        pools: [],
        tasks: [],
        networkLinks: [],
        networkSeries: { labels: [], bandwidthGbps: [], latencyMs: [], packetLossPct: [] },
        storageNodes: [],
        alerts: [],
        sessions: [],
        gpuTrend: { labels: [], values: [], unit: '%' },
        taskTrend: { labels: [], values: [], unit: '个' },
        overview: {}
      };
    }

    var tabContent = $('cp-tab-content');
    if (tabContent) tabContent.setAttribute('data-source', state.sceneSource);

    state.alerts = demoMode ? cloneData(data.alerts || []) : [];
    state.opsEvents = demoMode ? cloneData(data.opsEvents || []) : [];
    if (scenarioMode()) {
      syncScenarioNetworkState();
      loadShowcaseSessions();
      loadScheduleFlowState();
      loadRealShowcaseAssets();
    }

    // Load from localStorage (demo-only persisted alerts)
    loadFromLocalStorage();

    // Fetch real data for billing/Ark and live-mode monitoring
    loadRealData();
    if (!scenarioMode()) refreshMonitoringData();
    if (window.AIGVArk) window.AIGVArk.init();

    // Update status bar
    updateStatusBar();

    // Bind tab click events
    var tabButtons = document.querySelectorAll('.cp-tab-btn');
    for (var i = 0; i < tabButtons.length; i++) {
      (function(btn) {
        btn.addEventListener('click', function() {
          var tabId = btn.getAttribute('data-tab');
          if (tabId) switchTab(tabId);
        });
      })(tabButtons[i]);
    }

    // Bind drawer close
    var closeBtn = $('cp-drawer-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', closeDetailDrawer);
    }
    var backdrop = $('cp-drawer-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', closeDetailDrawer);
    }

    // Keyboard close drawer
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeDetailDrawer();
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
      stopMonitoring();
      stopNetworkPlayback();
      cancelFaultSimulation();
      if (state.clockTimer) { clearInterval(state.clockTimer); state.clockTimer = null; }
      if (monitoringPollInterval) { clearInterval(monitoringPollInterval); monitoringPollInterval = null; }
      cleanupAllRenderSubTabs();
    });

    // Resize handler for Three.js canvases
    window.addEventListener('resize', handleResize);

    // Bind sub-tab click events
    var subTabButtons = document.querySelectorAll('.cp-sub-tab-btn');
    for (var k = 0; k < subTabButtons.length; k++) {
      (function(btn) {
        btn.addEventListener('click', function() {
          var subTabId = btn.getAttribute('data-subtab');
          if (subTabId) switchRenderSubTab(subTabId);
        });
      })(subTabButtons[k]);
    }

    // Render overview tab
    renderOverview();

    // Handle URL hash for tab restoration
    if (window.location.hash) {
      var hashTab = window.location.hash.replace('#', '');
      switchTab(hashTab);
    }

    showToast('算力调度平台就绪', 'success');
  }

  // ── Expose public API ──
  window.ComputePlatform = {
    init: init,
    showToast: showToast,
    $: $,
    escapeHtml: escapeHtml,
    showLoading: showLoading,
    hideLoading: hideLoading,
    refreshMonitoringData: refreshMonitoringData,
    fetchMonitoringNodes: fetchMonitoringNodes,
    fetchNetworkLinks: fetchNetworkLinks,
    fetchMonitoringSamples: fetchMonitoringSamples,
    fetchStorageData: fetchStorageData,
    fetchAlerts: fetchAlerts,
    acknowledgeAlert: acknowledgeAlert,
    closeAlert: closeAlert,

    // Tab 2 - sub-tabs
    handleSessionDetail: handleSessionDetail,
    handleChangeStatus: handleChangeStatus,
    // Film sub-tab
    selectFilmKeyframe: selectFilmKeyframe,
    prevFilmKeyframe: prevFilmKeyframe,
    nextFilmKeyframe: nextFilmKeyframe,
    toggleFilmAutoplay: toggleFilmAutoplay,
    // Architecture sub-tab
    applyArchMaterial: applyArchMaterial,
    applyArchLighting: applyArchLighting,
    submitArchRenderTask: submitArchRenderTask,
    selectArchScene: selectArchScene,
    handleArchCompare: handleArchCompare,
    // Gaming sub-tab
    toggleGameConnection: toggleGameConnection,
    toggleGameFullscreen: toggleGameFullscreen,

    // Tab 3
    handleNodeFilter: handleNodeFilter,
    handleNodeDetail: handleNodeDetail,
    renderCloudEntry: renderCloudEntry,
    navigateToHosts: navigateToHosts,

    // Tab 4
    handleGenerateSchedule: handleGenerateSchedule,
    advanceScheduleState: advanceScheduleState,
    resetScheduleState: resetScheduleState,

    // Tab 5
    toggleNetworkRefresh: toggleNetworkRefresh,
    manualNetworkRefresh: manualNetworkRefresh,
    toggleNetworkPlayback: toggleNetworkPlayback,
    resetNetworkScenario: resetNetworkScenario,
    handleSimulateAnomaly: handleSimulateAnomaly,
    showNodeDetail: showNodeDetail,
    showNetworkLinkDetail: showNetworkLinkDetail,
    showTopologyNodeDetail: showTopologyNodeDetail,
    showFaultSimModal: showFaultSimModal,
    closeFaultSimModal: closeFaultSimModal,
    startFaultSimulation: startFaultSimulation,
    confirmAlertRecovery: confirmAlertRecovery,
    resolveAlert: resolveAlert,
    renderNetworkTopology: renderNetworkTopology,

    // Tab 7
    handleAcknowledgeAlert: handleAcknowledgeAlert,
    handleMarkProcessing: handleMarkProcessing,
    handleCloseAlert: handleCloseAlert
  };

  document.addEventListener('DOMContentLoaded', init);
})();
