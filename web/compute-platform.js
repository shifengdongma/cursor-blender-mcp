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
    renderSessions: [],
    gpuNodeFilter: { search: '', pool: 'all', status: 'all' },
    schedulingForm: {},
    schedulingResult: null,
    isNetworkAutoRefresh: true,
    networkRefreshCountdown: 5,
    networkLinksCopy: [],
    sensingNodesCopy: [],
    storageNodesCopy: [],
    networkSamplesCopy: [],
    faultAlertsCopy: [],
    switchRecordsCopy: [],
    monitoringTimer: null,
    clockTimer: null,
    faultSimTimers: [],
    faultSimActive: false,
    pendingConfirmAlerts: [],
    sdLsKey: 'aigv_sensing_dashboard_v1',
    rolePermissions: {},
    alerts: [],
    opsEvents: [],
    anomalyTimers: [],
    // Sub-tab state for cloud rendering
    renderSubTab: 'film',
    renderSubTabPrev: null,
    // Film scene
    filmThreeScene: null,
    filmThreeRenderer: null,
    filmAnimFrameId: null,
    filmAutoplayInterval: null,
    filmSelectedKeyframe: 0,
    filmOrbitControls: null,
    // Architecture scene
    archThreeScene: null,
    archThreeRenderer: null,
    archAnimFrameId: null,
    archSelectedMaterial: 'arch-mat-matte',
    archSelectedLighting: 'arch-lit-daylight',
    archModelMesh: null,
    archTaskRunning: false,
    // Gaming scene
    gameThreeScene: null,
    gameThreeRenderer: null,
    gameAnimFrameId: null,
    gamePlayerPos: { x: 0, y: 1.6, z: 0 },
    gamePlayerAngle: 0,
    gameKeysPressed: {},
    gameNetworkInterval: null,
    gameConnected: true,
    gameExhibitMeshes: []
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
      cancelFaultSimulation();
      if (state.clockTimer) { clearInterval(state.clockTimer); state.clockTimer = null; }
      // Clear monitoring poll interval
      if (monitoringPollInterval) {
        clearInterval(monitoringPollInterval);
        monitoringPollInterval = null;
      }
    } else {
      startClockTimer();
      if (state.isNetworkAutoRefresh) { state.networkRefreshCountdown = 5; startMonitoring(); }
      // 5-second auto-refresh for monitoring
      if (monitoringPollInterval) clearInterval(monitoringPollInterval);
      monitoringPollInterval = setInterval(function() {
        if (state.activeTab !== 'network') {
          clearInterval(monitoringPollInterval);
          monitoringPollInterval = null;
          return;
        }
        refreshMonitoringData();
      }, 5000);
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
        if (isThreeAvailable() && isWebGLAvailable()) {
          renderFilmSubTab();
        } else {
          showWebGLFallback('cp-sub-film');
        }
        break;
      case 'architecture':
        if (isThreeAvailable() && isWebGLAvailable()) {
          renderArchitectureSubTab();
        } else {
          showWebGLFallback('cp-sub-architecture');
        }
        break;
      case 'gaming':
        if (isThreeAvailable() && isWebGLAvailable()) {
          renderGamingSubTab();
        } else {
          showWebGLFallback('cp-sub-gaming');
        }
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
  function renderOverview() {
    var d = state.demoData;
    var s = state.apiSummary || {};
    var rj = state.apiRenderJobs || {};
    var b = state.apiBilling || {};

    // Use real API data with demo data fallback
    var totalNodes = s.total_nodes || 0;
    var onlineNodes = s.online_nodes || 0;
    var queueDepth = s.queue_depth || 0;

    // Render counts from API
    var runningTasks = (s.running_render_jobs || 0);
    var queuedTasks = (s.queued_render_jobs || 0);
    var avgLatency = 0;

    // Prefer real monitoring links; fall back to demo links only in demo mode.
    var latencyLinks = (state.networkLinksCopy && state.networkLinksCopy.length)
      ? state.networkLinksCopy
      : (demoEnabled() && d && d.networkLinks ? d.networkLinks : []);
    var avgNetLatency = null;
    if (latencyLinks.length) {
      var latencyTotal = 0;
      for (var l = 0; l < latencyLinks.length; l++) {
        latencyTotal += latencyLinks[l].latency || 0;
      }
      avgNetLatency = latencyTotal / latencyLinks.length;
    }

    var dailyCost = (b.total_amount || 0).toFixed(2);
    var activeAlerts = 0;
    if (state.alerts) {
      for (var a = 0; a < state.alerts.length; a++) {
        if (state.alerts[a].status === 'active') activeAlerts++;
      }
    }

    // GPU types
    var availGpu = totalNodes;
    var avgUtil = 0;

    var metrics = [
      { value: totalNodes, label: '算力节点', unit: '台' },
      { value: onlineNodes, label: '在线节点', unit: '台' },
      { value: availGpu, label: '可调度节点', unit: '台' },
      { value: queueDepth, label: '排队深度', unit: '个' },
      { value: queuedTasks, label: '排队任务', unit: '个' },
      { value: runningTasks, label: '运行任务', unit: '个' },
      { value: avgLatency ? avgLatency.toFixed(0) : '—', label: '平均渲染时延', unit: 'ms' },
      { value: avgNetLatency === null ? '—' : avgNetLatency.toFixed(0), label: '平均网络时延', unit: 'ms' },
      { value: dailyCost, label: '累计费用', unit: '元' },
      { value: activeAlerts, label: '当前告警', unit: '条' }
    ];

    var grid = $('cp-metrics-grid');
    if (!grid) return;
    var h = '';
    for (var m = 0; m < metrics.length; m++) {
      var met = metrics[m];
      h += '<div class="cp-metric-card">' +
           '<div class="cp-metric-value">' + escapeHtml(met.value) + '<span class="cp-metric-unit"> ' + escapeHtml(met.unit) + '</span></div>' +
           '<div class="cp-metric-label">' + escapeHtml(met.label) + '</div>' +
           '</div>';
    }
    grid.innerHTML = h;

    renderMiniCharts(d);
  }

  function renderMiniCharts(d) {
    var grid = $('cp-charts-grid');
    if (!grid) return;
    var demoMode = !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
    var emptyChart = '<div class="cp-chart-empty">暂无真实采集数据</div>';

    // Chart 1: GPU Utilization bar chart
    var pools = (d && d.resourcePools) ? d.resourcePools : [];
    var barColors = ['#78bfd2', '#94ddf1', '#5fa8b8', '#78bfd2', '#d7a84f'];
    var barW = 280, barGap = 8;
    var barCount = pools.length;
    var chart1 = emptyChart;
    if (barCount) {
      var barWidth = Math.max(10, (barW - (barCount - 1) * barGap - 40) / barCount);
      chart1 = '<svg viewBox="0 0 280 150" xmlns="http://www.w3.org/2000/svg">' +
        '<line x1="38" y1="10" x2="38" y2="120" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>' +
        '<line x1="38" y1="120" x2="275" y2="120" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>';
      for (var i = 0; i < barCount; i++) {
        var x = 42 + i * (barWidth + barGap);
        var h = ((pools[i].avgUtil || 0) / 100) * 108;
        chart1 += '<rect x="' + x + '" y="' + (120 - h) + '" width="' + barWidth + '" height="' + h + '" rx="3" fill="' + barColors[i % barColors.length] + '"/>' +
          '<text x="' + (x + barWidth/2) + '" y="135" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="8">' +
          escapeHtml(pools[i].name || '') + '</text>';
      }
      chart1 += '</svg>';
    }

    // Chart 2: Task count trend. Only show the historical demo curve in demo mode.
    var chart2 = emptyChart;
    if (demoMode) {
      var pts = [[8,110],[52,95],[96,108],[140,88],[184,72],[228,82],[272,58]];
      var polyPoints = '';
      for (var p = 0; p < pts.length; p++) {
        polyPoints += pts[p][0] + ',' + pts[p][1] + ' ';
      }
      chart2 = '<svg viewBox="0 0 280 150" xmlns="http://www.w3.org/2000/svg">' +
        '<line x1="8" y1="120" x2="275" y2="120" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>' +
        '<line x1="8" y1="60" x2="275" y2="60" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>' +
        '<polyline points="' + polyPoints + '" fill="none" stroke="#78bfd2" stroke-width="2" stroke-linejoin="round"/>' +
        '<polygon points="8,120 ' + polyPoints + ' 272,120" fill="rgba(120,191,210,0.1)"/>';
      for (var q = 0; q < pts.length; q++) {
        chart2 += '<circle cx="' + pts[q][0] + '" cy="' + pts[q][1] + '" r="3" fill="#78bfd2"/>';
      }
      chart2 += '</svg>';
    }

    // Chart 3: Resource pool distribution donut
    var donutColors = ['#78bfd2', '#94ddf1', '#5fa8b8', '#d7a84f', '#c9876e'];
    var cx = 140, cy = 80;
    var total = 0;
    for (var u = 0; u < pools.length; u++) { total += (pools[u].nodeCount || 0); }
    var chart3 = total ? '<svg viewBox="0 0 280 160" xmlns="http://www.w3.org/2000/svg">' : emptyChart;
    var cumulative = 0;
    if (total) {
      for (var v = 0; v < pools.length; v++) {
        var startAngle = (cumulative / total) * 2 * Math.PI - Math.PI / 2;
        var sliceAngle = ((pools[v].nodeCount || 0) / total) * 2 * Math.PI;
        var endAngle = startAngle + sliceAngle;
        cumulative += (pools[v].nodeCount || 0);
        var r1 = 20, r2 = 32;
        var x1 = cx + r1 * Math.cos(startAngle), y1 = cy + r1 * Math.sin(startAngle);
        var x2 = cx + r2 * Math.cos(startAngle), y2 = cy + r2 * Math.sin(startAngle);
        var x3 = cx + r2 * Math.cos(endAngle), y3 = cy + r2 * Math.sin(endAngle);
        var x4 = cx + r1 * Math.cos(endAngle), y4 = cy + r1 * Math.sin(endAngle);
        var largeArc = sliceAngle > Math.PI ? 1 : 0;
        var d = 'M' + x1 + ',' + y1 + ' L' + x2 + ',' + y2 +
          ' A' + r2 + ',' + r2 + ' 0 ' + largeArc + ' 1 ' + x3 + ',' + y3 +
          ' L' + x4 + ',' + y4 +
          ' A' + r1 + ',' + r1 + ' 0 ' + largeArc + ' 0 ' + x1 + ',' + y1 + ' Z';
        chart3 += '<path d="' + d + '" fill="' + donutColors[v % donutColors.length] + '"/>';
      }
      for (var w = 0; w < pools.length; w++) {
        chart3 += '<rect x="10" y="' + (122 + w * 14) + '" width="8" height="8" rx="2" fill="' + donutColors[w % donutColors.length] + '"/>' +
          '<text x="22" y="' + (130 + w * 14) + '" fill="rgba(255,255,255,0.55)" font-size="8">' + escapeHtml(pools[w].name || '') + '</text>';
      }
      chart3 += '</svg>';
    }

    // Chart 4: Network latency bars. Demo values are never shown in production.
    var chart4 = emptyChart;
    if (demoMode) {
      chart4 = '<svg viewBox="0 0 280 150" xmlns="http://www.w3.org/2000/svg">' +
        '<line x1="8" y1="120" x2="275" y2="120" stroke="rgba(255,255,255,0.1)" stroke-width="1"/>';
      var labels4 = ['本地', '阿里云', '腾讯云', '边缘'];
      var vals4 = [3, 18, 22, 8];
      var col4 = ['#74c798', '#78bfd2', '#78bfd2', '#d7a84f'];
      for (var n = 0; n < 4; n++) {
        var bw = 40, bx = 22 + n * 62;
        var bh = Math.min(vals4[n] * 4, 100);
        chart4 += '<rect x="' + bx + '" y="' + (120 - bh) + '" width="' + bw + '" height="' + bh + '" rx="3" fill="' + col4[n] + '"/>' +
          '<text x="' + (bx + bw/2) + '" y="' + (118 - bh) + '" text-anchor="middle" fill="rgba(255,255,255,0.6)" font-size="9">' + vals4[n] + 'ms</text>' +
          '<text x="' + (bx + bw/2) + '" y="135" text-anchor="middle" fill="rgba(255,255,255,0.45)" font-size="8">' + labels4[n] + '</text>';
      }
      chart4 += '</svg>';
    }

    grid.innerHTML =
      '<div class="cp-chart-container"><div class="cp-chart-title">GPU 利用率</div>' + chart1 + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">任务量趋势</div>' + chart2 + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">资源池分布</div>' + chart3 + '</div>' +
      '<div class="cp-chart-container"><div class="cp-chart-title">网络时延</div>' + chart4 + '</div>';
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
    if (!demoEnabled()) {
      if (placeholder) {
        placeholder.textContent = '影视动画关键帧仅为演示模块，生产模式未接入实时渲染数据';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';

    // Init scene if not already
    setTimeout(function() {
      initFilmScene();
      loadFilmModel();
      renderFilmKeyframes();
      updateFilmInfo(0);
      animateFilmScene();
    }, 50);
  }

  function initFilmScene() {
    if (state.filmThreeScene) return; // Already initialized
    var viewer = document.getElementById('cp-film-viewer');
    if (!viewer) return;
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
    // Try to load a GLB demo model; fall back to basic geometry on error
    if (typeof THREE.GLTFLoader === 'function') {
      var loader = new THREE.GLTFLoader();
      loader.load(
        '/data/assets/demo-scene.glb',
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
          // Fallback to basic geometry
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
    var d = state.demoData;
    if (!d || !d.filmKeyframes) return;
    var strip = document.getElementById('cp-film-thumb-strip');
    if (!strip) return;

    var kfs = d.filmKeyframes;
    var h = '';
    for (var i = 0; i < kfs.length; i++) {
      var kf = kfs[i];
      var activeCls = (i === state.filmSelectedKeyframe) ? ' active' : '';
      h += '<div class="cp-film-thumb' + activeCls + '" onclick="ComputePlatform.selectFilmKeyframe(' + i + ')" data-kf="' + i + '">' +
           '<div class="cp-film-thumb-num">#' + escapeHtml(kf.index) + '</div>' +
           '<div class="cp-film-thumb-title">' + escapeHtml(kf.title) + '</div>' +
           '<div class="cp-film-thumb-time">' + escapeHtml(kf.duration) + 's</div>' +
           '<div class="cp-film-thumb-bar" style="background:' + escapeHtml(kf.color) + '"></div>' +
           '</div>';
    }
    strip.innerHTML = h;
  }

  function updateFilmInfo(index) {
    var d = state.demoData;
    if (!d || !d.filmKeyframes) return;
    var kf = d.filmKeyframes[index];
    if (!kf) return;

    var titleEl = document.getElementById('cp-film-shot-title');
    var descEl = document.getElementById('cp-film-shot-desc');
    var lensEl = document.getElementById('cp-film-lens');
    var durEl = document.getElementById('cp-film-dur');
    var frameEl = document.getElementById('cp-film-frame');
    if (titleEl) titleEl.textContent = kf.title;
    if (descEl) descEl.textContent = kf.description;
    if (lensEl) lensEl.textContent = kf.lensDesc;
    if (durEl) durEl.textContent = kf.duration + '秒';
    if (frameEl) frameEl.textContent = (index + 1) + ' / ' + d.filmKeyframes.length;
  }

  function selectFilmKeyframe(index) {
    var d = state.demoData;
    if (!d || !d.filmKeyframes) return;
    if (index < 0 || index >= d.filmKeyframes.length) return;
    state.filmSelectedKeyframe = index;
    updateFilmInfo(index);
    renderFilmKeyframes();
    // Scroll thumbnail into view
    var thumb = document.querySelector('.cp-film-thumb[data-kf="' + index + '"]');
    if (thumb) {
      thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }

  function prevFilmKeyframe() {
    var d = state.demoData;
    if (!d || !d.filmKeyframes) return;
    var idx = state.filmSelectedKeyframe - 1;
    if (idx < 0) idx = d.filmKeyframes.length - 1;
    selectFilmKeyframe(idx);
  }

  function nextFilmKeyframe() {
    var d = state.demoData;
    if (!d || !d.filmKeyframes) return;
    var idx = state.filmSelectedKeyframe + 1;
    if (idx >= d.filmKeyframes.length) idx = 0;
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
    if (!demoEnabled()) {
      if (placeholder) {
        placeholder.textContent = '建筑/工业渲染仅为演示模块，生产模式未接入实时渲染数据';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';

    setTimeout(function() {
      initArchScene();
      applyArchMaterial(state.archSelectedMaterial);
      applyArchLighting(state.archSelectedLighting);
      renderArchPresets();
      renderArchEffectImages();
      animateArchScene();
    }, 50);
  }

  function initArchScene() {
    if (state.archThreeScene) return;
    var viewer = document.getElementById('cp-arch-viewer');
    if (!viewer) return;
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
    var d = state.demoData;
    if (!d) return;
    var container = document.getElementById('cp-arch-presets');
    if (!container) return;

    var materials = d.archMaterialPresets || [];
    var lightings = d.archLightingPresets || [];

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
    var d = state.demoData;
    if (!d || !state.archModelMesh) { renderArchPresets(); return; }

    var preset = null;
    var materials = d.archMaterialPresets || [];
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
    var d = state.demoData;
    if (!d) { renderArchPresets(); return; }

    var preset = null;
    var lightings = d.archLightingPresets || [];
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
    if (!demoEnabled()) {
      showToast('云渲染动画仅为演示功能，生产模式不可用', 'warning');
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
      { pct: 100, info: '渲染完成！结果已存入素材库' }
    ];

    var stepIndex = 0;
    function runStep() {
      if (stepIndex >= steps.length) {
        state.archTaskRunning = false;
        if (btn) { btn.disabled = false; btn.textContent = '提交云渲染任务'; }
        showToast('云渲染任务模拟完成', 'success');
        return;
      }
      var s = steps[stepIndex];
      if (bar) bar.style.width = s.pct + '%';
      if (info) info.textContent = s.info;
      if (label) label.textContent = s.pct + '%';
      stepIndex++;
      setTimeout(runStep, 1000);
    }
    runStep();
  }

  function renderArchEffectImages() {
    var d = state.demoData;
    if (!d || !d.archEffectImages) return;
    var grid = document.getElementById('cp-arch-effect-grid');
    if (!grid) return;

    var images = d.archEffectImages;
    var h = '';
    for (var i = 0; i < images.length; i++) {
      var img = images[i];
      h += '<div class="cp-arch-effect-item">' +
           '<canvas class="cp-arch-effect-canvas" id="arch-effect-canvas-' + i + '" width="200" height="100"></canvas>' +
           '<div class="cp-arch-effect-label">' + escapeHtml(img.label) + '</div>' +
           '</div>';
    }
    grid.innerHTML = h;

    // Draw placeholder gradients
    var colorSets = [
      ['#d4c5a9', '#87ceeb'],
      ['#b8b8c8', '#112244'],
      ['#f5f0e0', '#f5e6d3']
    ];
    for (var j = 0; j < images.length; j++) {
      setTimeout(function(idx) {
        return function() {
          var canvas = document.getElementById('arch-effect-canvas-' + idx);
          if (!canvas) return;
          var ctx = canvas.getContext('2d');
          var grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
          var cs = colorSets[idx] || ['#cccccc', '#666666'];
          grad.addColorStop(0, cs[0]);
          grad.addColorStop(1, cs[1]);
          ctx.fillStyle = grad;
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = 'rgba(0,0,0,0.3)';
          ctx.fillRect(0, canvas.height * 0.7, canvas.width, canvas.height * 0.3);
          ctx.fillStyle = 'rgba(255,255,255,0.6)';
          ctx.font = '10px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('DEMO', canvas.width / 2, canvas.height * 0.9);
        };
      }(j), 100);
    }
  }

  function cleanupArchitectureResources() {
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
    if (!demoEnabled()) {
      if (placeholder) {
        placeholder.textContent = '云游戏互动仅为演示模块，生产模式未接入实时串流';
        placeholder.style.display = 'block';
      }
      return;
    }
    if (placeholder) placeholder.style.display = 'block';

    setTimeout(function() {
      initGameScene();
      buildGameRoom();
      renderGameMetrics();
      setupGameTouchControls();
      bindGameKeyboard();
      animateGameScene();
      startGameNetworkSimulation();
    }, 50);
  }

  function initGameScene() {
    if (state.gameThreeScene) return;
    var viewer = document.getElementById('cp-game-viewer');
    if (!viewer) return;
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
    var d = state.demoData;
    var exhibits = d ? d.gameExhibits : [];
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
      mesh.__exhRotSpeed = 0.3 + Math.random() * 0.5;

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

    var buttons = dpad.querySelectorAll('.cp-game-dpad-btn');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('touchstart', function(e) {
        e.preventDefault();
        var dir = '';
        if (this.classList.contains('dpad-up')) dir = 'w';
        else if (this.classList.contains('dpad-down')) dir = 's';
        else if (this.classList.contains('dpad-left')) dir = 'a';
        else if (this.classList.contains('dpad-right')) dir = 'd';
        if (dir) state.gameKeysPressed[dir] = true;
      });
      buttons[i].addEventListener('touchend', function(e) {
        e.preventDefault();
        var dir = '';
        if (this.classList.contains('dpad-up')) dir = 'w';
        else if (this.classList.contains('dpad-down')) dir = 's';
        else if (this.classList.contains('dpad-left')) dir = 'a';
        else if (this.classList.contains('dpad-right')) dir = 'd';
        if (dir) state.gameKeysPressed[dir] = false;
      });
      buttons[i].addEventListener('mousedown', function() {
        var dir = '';
        if (this.classList.contains('dpad-up')) dir = 'w';
        else if (this.classList.contains('dpad-down')) dir = 's';
        else if (this.classList.contains('dpad-left')) dir = 'a';
        else if (this.classList.contains('dpad-right')) dir = 'd';
        if (dir) state.gameKeysPressed[dir] = true;
      });
      buttons[i].addEventListener('mouseup', function() {
        var dir = '';
        if (this.classList.contains('dpad-up')) dir = 'w';
        else if (this.classList.contains('dpad-down')) dir = 's';
        else if (this.classList.contains('dpad-left')) dir = 'a';
        else if (this.classList.contains('dpad-right')) dir = 'd';
        if (dir) state.gameKeysPressed[dir] = false;
      });
      buttons[i].addEventListener('mouseleave', function() {
        var dir = '';
        if (this.classList.contains('dpad-up')) dir = 'w';
        else if (this.classList.contains('dpad-down')) dir = 's';
        else if (this.classList.contains('dpad-left')) dir = 'a';
        else if (this.classList.contains('dpad-right')) dir = 'd';
        if (dir) state.gameKeysPressed[dir] = false;
      });
    }
  }

  function renderGameMetrics() {
    var container = document.getElementById('cp-game-metrics');
    if (!container) return;

    container.innerHTML =
      '<div class="cp-game-metric"><div class="cp-game-metric-value">--</div><div class="cp-game-metric-label">延迟 (ms)</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">--</div><div class="cp-game-metric-label">FPS</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">--</div><div class="cp-game-metric-label">码率 (Mbps)</div></div>' +
      '<div class="cp-game-metric"><div class="cp-game-metric-value">--</div><div class="cp-game-metric-label">数据不可用</div></div>';
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
      showToast('连接已断开 (模拟)', 'warning');
    } else {
      if (overlay) overlay.classList.remove('visible');
      if (btn) btn.textContent = '断开连接';
      showToast('已重新连接 (模拟)', 'success');
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
  function renderSessionsSubTab() {
    var sessions = state.renderSessions;
    var d = state.demoData;
    var projects = d ? d.creativeProjects : [];
    if (!sessions || !sessions.length) {
      var emptyContainer = document.getElementById('cp-render-table');
      if (emptyContainer) {
        emptyContainer.innerHTML = '<div class="empty-state-container">' +
          '<h3 class="empty-title">暂无渲染会话</h3>' +
          '<p class="empty-desc">提交渲染任务后可在这里查看真实会话状态。</p></div>';
      }
      return;
    }

    function projName(pid) {
      for (var i = 0; i < projects.length; i++) {
        if (projects[i].id === pid) return projects[i].name;
      }
      return pid;
    }

    var statusLabels = {
      rendering: '渲染中', queued: '排队中', preparing: '准备中',
      paused: '已暂停', completed: '已完成', error: '错误'
    };

    var h = '<table class="cp-table"><thead><tr>' +
      '<th>会话编号</th><th>项目名</th><th>渲染引擎</th><th>GPU 节点</th>' +
      '<th>分辨率</th><th>FPS</th><th>码率</th><th>时延</th>' +
      '<th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>';

    for (var s = 0; s < sessions.length; s++) {
      var sess = sessions[s];
      h += '<tr>' +
        '<td>' + escapeHtml(sess.id) + '</td>' +
        '<td>' + escapeHtml(projName(sess.project)) + '</td>' +
        '<td>' + escapeHtml(sess.engine) + '</td>' +
        '<td>' + escapeHtml(sess.gpuNode) + '</td>' +
        '<td>' + escapeHtml(sess.resolution) + '</td>' +
        '<td>' + escapeHtml(sess.fps) + '</td>' +
        '<td>' + escapeHtml(sess.bitrate) + '</td>' +
        '<td>' + escapeHtml(sess.latency) + 'ms</td>' +
        '<td>' + badge(statusLabels[sess.status] || sess.status, sess.status) + '</td>' +
        '<td>' +
        '<button class="cp-action-btn" onclick="ComputePlatform.handleSessionDetail(\'' + escapeHtml(sess.id) + '\')">详情</button>' +
        '<button class="cp-action-btn" onclick="ComputePlatform.handleChangeStatus(\'' + escapeHtml(sess.id) + '\')">切换状态</button>' +
        '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';

    var container = document.getElementById('cp-render-table');
    if (container) container.innerHTML = h;
  }

  function handleSessionDetail(id) {
    var sessions = state.renderSessions;
    var session = null;
    for (var i = 0; i < sessions.length; i++) {
      if (sessions[i].id === id) { session = sessions[i]; break; }
    }
    if (!session) return;

    var d = state.demoData;
    var node = null;
    if (d && d.gpuNodes) {
      for (var j = 0; j < d.gpuNodes.length; j++) {
        if (d.gpuNodes[j].id === session.gpuNode) { node = d.gpuNodes[j]; break; }
      }
    }

    var vramPct = node ? ((node.usedVram / node.totalVram) * 100).toFixed(1) : '--';
    var vramClass = (parseFloat(vramPct) > 80) ? 'danger' : ((parseFloat(vramPct) > 60) ? 'warning' : '');

    var html =
      '<div class="cp-video-preview" id="cp-video-canvas-' + escapeHtml(id) + '">' +
      '<canvas id="cp-canvas-' + escapeHtml(id) + '"></canvas>' +
      '<div class="cp-video-play-btn"><svg viewBox="0 0 24 24" fill="white"><polygon points="8,5 19,12 8,19"/></svg></div>' +
      '</div>' +
      '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 型号</div><div class="cp-detail-value">' + escapeHtml(node ? node.gpuModel : '--') + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 显存</div><div class="cp-detail-value">' + escapeHtml(node ? node.usedVram : '--') + ' / ' + escapeHtml(node ? node.totalVram : '--') + ' GB</div></div>' +
      '</div>' +
      '<div class="cp-progress-bar-wrap"><div class="cp-detail-label">显存使用率 ' + vramPct + '%</div>' +
      '<div class="cp-progress-bar"><div class="cp-progress-bar-fill ' + vramClass + '" style="width:' + vramPct + '%"></div></div></div>' +
      '<div class="cp-detail-grid" style="margin-top:16px">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">利用率</div><div class="cp-detail-value">' + escapeHtml(node ? node.utilization : '--') + '%</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">码率</div><div class="cp-detail-value">' + escapeHtml(session.bitrate) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">FPS</div><div class="cp-detail-value">' + escapeHtml(session.fps) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">编码延时</div><div class="cp-detail-value">' + escapeHtml(Math.round(session.latency * 0.6)) + 'ms</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">网络延时</div><div class="cp-detail-value">' + escapeHtml(Math.round(session.latency * 0.35)) + 'ms</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">丢包率</div><div class="cp-detail-value">' + (session.latency > 100 ? '0.12' : '0.03') + '%</div></div>' +
      '</div>' +
      '<div class="cp-progress-bar-wrap" style="margin-top:16px"><div class="cp-detail-label">预计费用</div>' +
      '<div class="cp-progress-bar"><div class="cp-progress-bar-fill" style="width:' + (session.latency > 100 ? '72' : '35') + '%"></div></div></div>' +
      '<div class="cp-detail-label" style="margin-top:4px">预计 ¥' + (session.latency > 150 ? '48.50' : session.latency > 80 ? '28.30' : '12.60') + '/小时</div>' +
      '<div class="cp-section-divider" style="margin-top:16px; padding-top:12px">' +
      '<div class="cp-detail-label">运维日志</div>' +
      '<div class="cp-log-entry"><span class="cp-log-time">14:32</span><span class="cp-log-msg">渲染会话 ' + escapeHtml(id) + ' 运行中，GPU利用率正常</span></div>' +
      '<div class="cp-log-entry"><span class="cp-log-time">13:15</span><span class="cp-log-msg">帧编码器初始化完成，编码模式: NVENC H.264</span></div>' +
      '<div class="cp-log-entry"><span class="cp-log-time">12:48</span><span class="cp-log-msg">资源分配完成，分配GPU: ' + escapeHtml(node ? node.gpuModel : '--') + '</span></div>' +
      '</div>' +
      '<div class="cp-demo-info">当前为云渲染可视化演示，未接入真实 Unity 推流</div>';

    showDetailDrawer('会话详情: ' + id, html);

    // Animated canvas background
    setTimeout(function() {
      var canvasEl = $('cp-canvas-' + id);
      if (!canvasEl) return;
      var parent = canvasEl.parentNode;
      canvasEl.width = parent.offsetWidth;
      canvasEl.height = parent.offsetHeight;
      var ctx = canvasEl.getContext('2d');
      if (!ctx) return;
      var hue = 195;
      function animate() {
        hue = (hue + 0.3) % 360;
        var grad = ctx.createLinearGradient(0, 0, canvasEl.width, canvasEl.height);
        grad.addColorStop(0, 'hsla(' + hue + ', 50%, 40%, 0.4)');
        grad.addColorStop(0.5, 'hsla(' + ((hue + 60) % 360) + ', 30%, 25%, 0.2)');
        grad.addColorStop(1, 'hsla(' + ((hue + 120) % 360) + ', 50%, 35%, 0.3)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
        if ($('cp-detail-drawer').classList.contains('open')) {
          requestAnimationFrame(animate);
        }
      }
      animate();
    }, 100);
  }

  function handleChangeStatus(id) {
    var sessions = state.renderSessions;
    for (var i = 0; i < sessions.length; i++) {
      if (sessions[i].id === id) {
        var cur = sessions[i].status;
        if (cur === 'rendering') sessions[i].status = 'completed';
        else if (cur === 'queued') sessions[i].status = 'rendering';
        else if (cur === 'paused') sessions[i].status = 'rendering';
        else if (cur === 'completed') sessions[i].status = 'queued';
        else sessions[i].status = 'rendering';
        break;
      }
    }
    renderRendering();
    showToast('会话 ' + id + ' 状态已切换', 'info');
  }

  // ══════════════════════════════════════════════════
  // Tab 3: GPU Resource Pools
  // ══════════════════════════════════════════════════
  function demoEnabled() {
    return !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
  }

  function getGpuPools() {
    var d = state.demoData || {};
    if (demoEnabled() && d.resourcePools) return d.resourcePools;
    var hosts = (state.apiHosts && state.apiHosts.items) || [];
    var seen = {};
    var pools = [];
    for (var i = 0; i < hosts.length; i++) {
      var key = hosts[i].provider_type || 'cloud';
      if (!seen[key]) {
        seen[key] = true;
        pools.push({ id: key, name: key, region: hosts[i].region || '—', nodeCount: 0, onlineCount: 0, availGpu: 0, unitPrice: null, avgUtil: null, status: 'unknown' });
      }
      var pool = pools[seen[key] ? pools.length - 1 : 0];
      for (var p = 0; p < pools.length; p++) {
        if (pools[p].id === key) { pool = pools[p]; break; }
      }
      pool.nodeCount += 1;
      if (hosts[i].status === 'online' || hosts[i].status === 'running') pool.onlineCount += 1;
      pool.availGpu += hosts[i].gpu_count || 0;
    }
    return pools;
  }

  function getGpuNodes() {
    var d = state.demoData || {};
    if (demoEnabled() && d.gpuNodes) return d.gpuNodes;
    var hosts = (state.apiHosts && state.apiHosts.items) || [];
    return hosts.map(function (h) {
      return {
        id: h.id,
        name: h.node_name || h.id,
        pool: h.provider_type || 'cloud',
        gpuModel: h.gpu_type || '—',
        gpuCount: h.gpu_count || 0,
        totalVram: h.gpu_memory_mb ? (h.gpu_memory_mb / 1024).toFixed(0) : 0,
        usedVram: 0,
        utilization: '—',
        currentTask: '—',
        status: h.status || 'unknown'
      };
    });
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
      var utilPct = pool.avgUtil || 0;
      var utilCls = utilPct > 70 ? ' danger' : (utilPct > 50 ? ' caution' : '');
      html += '<div class="cp-pool-card' + statusCls + '">' +
        '<div class="cp-pool-name">' + escapeHtml(pool.name) + '</div>' +
        '<div class="cp-pool-region">' + escapeHtml(pool.region) + '</div>' +
        '<div class="cp-pool-stats">' +
        '<div><div class="cp-pool-stat-label">节点数</div><div class="cp-pool-stat-value">' + pool.nodeCount + '</div></div>' +
        '<div><div class="cp-pool-stat-label">在线</div><div class="cp-pool-stat-value">' + pool.onlineCount + '</div></div>' +
        '<div><div class="cp-pool-stat-label">可用GPU</div><div class="cp-pool-stat-value">' + pool.availGpu + '</div></div>' +
        '<div><div class="cp-pool-stat-label">单价</div><div class="cp-pool-stat-value">' + (pool.unitPrice > 0 ? '¥' + pool.unitPrice : '免费') + '</div></div>' +
        '</div>' +
        '<div class="cp-pool-stat-label" style="margin-top:12px">利用率 ' + utilPct + '%</div>' +
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
            '<span>主机以实时列表为准</span>' +
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
            '<span>主机以实时列表为准</span>' +
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

  function renderNodeTable() {
    var nodes = getGpuNodes();
    var f = state.gpuNodeFilter;

    // Filter
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
      '<th>总显存</th><th>已用显存</th><th>利用率</th>' +
      '<th>当前任务</th><th>状态</th><th>操作</th>' +
      '</tr></thead><tbody>';

    if (!filtered.length) {
      h += '<tr><td colspan="10"><div class="cp-chart-empty">暂无真实 GPU 节点数据</div></td></tr>';
    }
    for (var k = 0; k < filtered.length; k++) {
      var node = filtered[k];
      var totalVram = Number(node.totalVram) || 0;
      var usedVram = Number(node.usedVram) || 0;
      var vramPct = totalVram ? ((usedVram / totalVram) * 100).toFixed(1) : '—';
      var util = node.utilization === null || node.utilization === undefined ? '—' : node.utilization;
      h += '<tr>' +
        '<td>' + escapeHtml(node.name) + '</td>' +
        '<td>' + escapeHtml(poolNames[node.pool] || node.pool) + '</td>' +
        '<td>' + escapeHtml(node.gpuModel) + '</td>' +
        '<td>' + (node.gpuCount || 0) + '</td>' +
        '<td>' + (totalVram || '—') + ' GB</td>' +
        '<td>' + (vramPct === '—' ? '—' : usedVram + ' GB (' + vramPct + '%)') + '</td>' +
        '<td>' + util + (util === '—' ? '' : '%') + '</td>' +
        '<td>' + escapeHtml(node.currentTask || '—') + '</td>' +
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

    var totalVram = Number(node.totalVram) || 0;
    var usedVram = Number(node.usedVram) || 0;
    var vramPct = totalVram ? ((usedVram / totalVram) * 100).toFixed(1) : '—';
    var vramCls = vramPct !== '—' && parseFloat(vramPct) > 80 ? 'danger' :
      (vramPct !== '—' && parseFloat(vramPct) > 60 ? 'warning' : '');
    var util = node.utilization === null || node.utilization === undefined ? '—' : node.utilization;
    var vramWidth = vramPct === '—' ? 0 : vramPct;

    var html =
      '<div class="cp-detail-grid">' +
      '<div class="cp-detail-group"><div class="cp-detail-label">节点名称</div><div class="cp-detail-value">' + escapeHtml(node.name) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">所属资源池</div><div class="cp-detail-value">' + escapeHtml(poolName) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 型号</div><div class="cp-detail-value">' + escapeHtml(node.gpuModel) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">GPU 数量</div><div class="cp-detail-value">' + (node.gpuCount || 0) + '</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">总显存</div><div class="cp-detail-value">' + (totalVram || '—') + ' GB</div></div>' +
      '<div class="cp-detail-group"><div class="cp-detail-label">利用率</div><div class="cp-detail-value">' + util + (util === '—' ? '' : '%') + '</div></div>' +
      '</div>' +
      '<div class="cp-progress-bar-wrap" style="margin-top:16px"><div class="cp-detail-label">显存使用率 ' + vramPct + (vramPct === '—' ? '' : '%') + '</div>' +
      '<div class="cp-progress-bar"><div class="cp-progress-bar-fill ' + vramCls + '" style="width:' + vramWidth + '%"></div></div></div>' +
      '<div class="cp-detail-group" style="margin-top:12px"><div class="cp-detail-label">当前任务</div><div class="cp-detail-value">' + escapeHtml(node.currentTask || '—') + '</div></div>' +
      '<div class="cp-detail-group" style="margin-top:12px"><div class="cp-detail-label">状态</div><div class="cp-detail-value">' + badge(node.status, node.status) + '</div></div>' +
      '';

    showDetailDrawer('节点详情: ' + node.name, html);
  }

  // ══════════════════════════════════════════════════
  // Tab 4: Scheduling Tasks
  // ══════════════════════════════════════════════════
  function renderScheduling() {
    var layout = $('cp-schedule-layout');
    if (!layout) return;

    // Form
    var formHtml =
      '<div class="cp-schedule-form">' +
      '<div class="cp-form-group"><label class="cp-form-label">任务名称</label><input type="text" class="cp-form-input" id="cp-sched-name" placeholder="输入任务名称"></div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">任务类型</label><select class="cp-form-select" id="cp-sched-type"><option value="render">渲染任务</option><option value="training">模型训练</option><option value="inference">推理服务</option></select></div>' +
      '<div class="cp-form-group"><label class="cp-form-label">优先级</label><select class="cp-form-select" id="cp-sched-priority"><option value="high">高</option><option value="medium" selected>中</option><option value="low">低</option></select></div>' +
      '</div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">最低显存 (GB)</label><input type="range" class="cp-form-range" id="cp-sched-vram" min="4" max="80" value="16" step="4" oninput="document.getElementById(\'cp-sched-vram-val\').textContent=this.value"><span class="cp-range-value" id="cp-sched-vram-val">16</span> GB</div>' +
      '<div class="cp-form-group"><label class="cp-form-label">GPU 数量</label><select class="cp-form-select" id="cp-sched-gpu-count"><option value="1">1</option><option value="2">2</option><option value="4">4</option><option value="8">8</option></select></div>' +
      '</div>' +
      '<div class="cp-form-row">' +
      '<div class="cp-form-group"><label class="cp-form-label">最大费用 (元/小时)</label><input type="text" class="cp-form-input" id="cp-sched-cost" placeholder="0 表示不限" value="0"></div>' +
      '<div class="cp-form-group"><label class="cp-form-label">最大时延 (ms)</label><input type="text" class="cp-form-input" id="cp-sched-latency" placeholder="0 表示不限" value="0"></div>' +
      '</div>' +
      '<div class="cp-form-group"><label class="cp-form-label">调度策略</label><select class="cp-form-select" id="cp-sched-strategy"><option value="lowest_cost">最低费用</option><option value="lowest_latency">最低时延</option><option value="shortest_queue">最短排队</option><option value="highest_performance">最高性能</option><option value="local_first">本地优先</option></select></div>' +
      '<button class="cp-form-submit" onclick="ComputePlatform.handleGenerateSchedule()">生成调度方案</button>' +
      '</div>';

    // Result card
    var resultHtml = '';
    if (state.schedulingResult) {
      var r = state.schedulingResult;
      resultHtml =
        '<div class="cp-schedule-result-card">' +
        '<div class="cp-result-title">调度结果</div>' +
        '<div class="cp-result-row"><span class="cp-result-label">推荐节点</span><span class="cp-result-value">' + escapeHtml(r.nodeName) + '</span></div>' +
        '<div class="cp-result-row"><span class="cp-result-label">GPU 型号</span><span class="cp-result-value">' + escapeHtml(r.gpuModel) + '</span></div>' +
        '<div class="cp-result-row"><span class="cp-result-label">预计等待</span><span class="cp-result-value">' + escapeHtml(r.estimatedWait) + '</span></div>' +
        '<div class="cp-result-row"><span class="cp-result-label">预计执行时间</span><span class="cp-result-value">' + escapeHtml(r.estimatedTime) + '</span></div>' +
        '<div class="cp-result-row"><span class="cp-result-label">预计费用</span><span class="cp-result-value">' + escapeHtml(r.estimatedCost) + '</span></div>' +
        '<div class="cp-result-reason">' + escapeHtml(r.reason) + '</div>' +
        '</div>';
    } else {
      resultHtml = '<div class="cp-schedule-result-card empty">填写表单后点击"生成调度方案"</div>';
    }

    layout.innerHTML = formHtml + resultHtml;
  }

  function handleGenerateSchedule() {
    var nameEl = $('cp-sched-name');
    var typeEl = $('cp-sched-type');
    var priorityEl = $('cp-sched-priority');
    var vramEl = $('cp-sched-vram');
    var gpuCountEl = $('cp-sched-gpu-count');
    var costEl = $('cp-sched-cost');
    var latencyEl = $('cp-sched-latency');
    var strategyEl = $('cp-sched-strategy');

    var taskName = (nameEl ? nameEl.value : '') || '未命名任务';
    var taskType = typeEl ? typeEl.value : 'render';
    var priority = priorityEl ? priorityEl.value : 'medium';
    var minVram = parseInt(vramEl ? vramEl.value : 16, 10);
    var gpuCount = parseInt(gpuCountEl ? gpuCountEl.value : 1, 10);
    var maxCost = parseFloat(costEl ? (costEl.value || '0') : '0');
    var maxLatency = parseFloat(latencyEl ? (latencyEl.value || '0') : '0');
    var strategy = strategyEl ? strategyEl.value : 'lowest_cost';

    state.schedulingForm = { taskName: taskName, taskType: taskType, priority: priority, minVram: minVram, gpuCount: gpuCount, maxCost: maxCost, maxLatency: maxLatency, strategy: strategy };

    var nodes = getGpuNodes();
    if (!nodes.length) {
      showToast('暂无真实 GPU 节点数据', 'warning');
      return;
    }

    // Filter GPU nodes by VRAM requirement
    var candidates = [];
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var vramPerGpu = (Number(node.totalVram) || 0) / Math.max(1, Number(node.gpuCount) || 1);
      if (vramPerGpu >= minVram) candidates.push(node);
    }

    // Get pool info for latency/cost
    var poolMap = {};
    var pools = getGpuPools();
    for (var j = 0; j < pools.length; j++) {
      var p = pools[j];
      poolMap[p.id] = p;
    }

    if (candidates.length === 0) {
      state.schedulingResult = null;
      renderScheduling();
      showToast('没有满足最低显存要求的GPU节点', 'warning');
      return;
    }

    // Score each candidate
    var scored = [];
    for (var k = 0; k < candidates.length; k++) {
      var n = candidates[k];
      var pinfo = poolMap[n.pool] || { unitPrice: 15, latency: 20 };

      // Base score components (lower = better)
      var util = Number(n.utilization);
      if (isNaN(util)) util = 0;
      var utilScore = (100 - util) / 100;  // lower utilization = better
      var statusScore = (n.status === 'online' || n.status === 'running') ? 1 : 0.4;
      var costScore = pinfo.unitPrice > 0 ? (30 / pinfo.unitPrice) : 2;  // cheaper = better, free = max
      var latencyScore = pinfo.latency > 0 ? (50 / pinfo.latency) : 2;  // lower latency = better
      var vramScore = (((Number(n.totalVram) || 0) / Math.max(1, Number(n.gpuCount) || 1)) / minVram);  // more vram headroom = better

      // Strategy multiplier
      var strategyMult = { lowest_cost: [2, 0.5, 0.5, 0.5], lowest_latency: [0.5, 0.5, 0.5, 2], shortest_queue: [2, 0.5, 0.5, 0.5], highest_performance: [0.5, 1, 0.5, 0.5], local_first: [1, 1, 0, 2] };

      var w = strategyMult[strategy] || [1, 1, 1, 1];
      var score = utilScore * w[0] + statusScore * 1.5 + costScore * w[1] + latencyScore * w[2] + vramScore * w[3];
      if (strategy === 'local_first' && n.pool && n.pool.indexOf('local') === 0) score += 3;
      if (maxCost > 0 && pinfo.unitPrice > maxCost) score -= 5;
      if (maxLatency > 0 && pinfo.latency > maxLatency) score -= 5;

      scored.push({ node: n, score: score, pool: pinfo });
    }

    // Sort by score descending
    scored.sort(function(a, b) { return b.score - a.score; });

    var best = scored[0];
    var bestNode = best.node;
    var bestPool = best.pool;

    var reasonMap = {
      lowest_cost: '根据"最低费用"策略，选择单价最低的满足要求的GPU节点，综合评分 ' + best.score.toFixed(2),
      lowest_latency: '根据"最低时延"策略，选择网络时延最低的满足要求的GPU节点，综合评分 ' + best.score.toFixed(2),
      shortest_queue: '根据"最短排队"策略，选择利用率最低的满足要求的GPU节点，综合评分 ' + best.score.toFixed(2),
      highest_performance: '根据"最高性能"策略，选择计算性能最强的满足要求的GPU节点，综合评分 ' + best.score.toFixed(2),
      local_first: '根据"本地优先"策略，优先选择本地/私有集群的满足要求的GPU节点，综合评分 ' + best.score.toFixed(2)
    };

    // Estimated wait time is only meaningful when a real utilization metric exists.
    var bestUtil = Number(bestNode.utilization);
    var estimatedWait = isNaN(bestUtil) ? '未知（缺少实时利用率）' : (bestUtil > 70 ? '5-10 分钟' : (bestUtil > 40 ? '1-5 分钟' : '<1 分钟'));

    state.schedulingResult = {
      nodeName: bestNode.name,
      gpuModel: bestNode.gpuModel,
      estimatedWait: estimatedWait,
      estimatedTime: taskType === 'training' ? '2-4 小时' : (taskType === 'inference' ? '实时' : '15-45 分钟'),
      estimatedCost: '¥' + (bestPool.unitPrice > 0 ? (bestPool.unitPrice * gpuCount).toFixed(2) : '0.00') + '/小时',
      reason: reasonMap[strategy] || ('综合调度评分 ' + best.score.toFixed(2))
    };

    renderScheduling();
    showToast('调度方案已生成: ' + bestNode.name, 'success');
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
    fetchMonitoringNodes().then(function(data) {
      if (data.nodes && data.nodes.length > 0) {
        state.sensingNodesCopy = data.nodes;
        renderSensingNodes();
        renderBottomMetrics();
      }
    });
    fetchNetworkLinks().then(function(data) {
      if (data.links && data.links.length > 0) {
        state.networkLinksCopy = data.links;
        renderSensingLinks();
        renderBottomMetrics();
      }
    });
    fetchMonitoringSamples(20).then(function(data) {
      if (data.samples && data.samples.length > 0) {
        state.networkSamplesCopy = data.samples;
        renderSensingCharts();
      }
    });
    fetchStorageData().then(function(data) {
      if (data.targets && data.targets.length > 0) {
        state.storageNodesCopy = data.targets;
      }
      renderStorageNodes();
      renderStorageSummary();
    });
    fetchAlerts('open', 20).then(function(data) {
      if (data.items && data.items.length > 0) {
        state.faultAlertsCopy = data.items;
      }
      renderFaultAlerts();
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
        '<p class="empty-desc">尚未接入节点采集数据源。</p></div>';
      return;
    }
    var h = '';
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var barClass = n.gpuUtil >= 85 ? 'danger' : (n.gpuUtil >= 70 ? 'warn' : '');
      h += '<div class="sd-node-card status-' + n.status + '" onclick="ComputePlatform.showNodeDetail(\'' + n.id + '\')">' +
        '<div class="sd-node-name">' + escapeHtml(n.name) + '</div>' +
        '<div class="sd-node-model">' + escapeHtml(n.gpuModel) + '</div>' +
        '<div class="sd-node-metric"><span>GPU</span><span>' + n.gpuUtil + '%</span></div>' +
        '<div class="sd-node-bar"><div class="sd-node-bar-fill ' + barClass + '" style="width:' + n.gpuUtil + '%"></div></div>' +
        '<div class="sd-node-metric"><span>VRAM</span><span>' + n.vramUtil + '%</span></div>' +
        '<div class="sd-node-bar"><div class="sd-node-bar-fill ' + barClass + '" style="width:' + n.vramUtil + '%"></div></div>' +
        '<div class="sd-node-bottom"><span class="sd-node-temp">' + n.temp + '°C</span><span class="sd-node-heartbeat">' + escapeHtml(n.heartbeat.length > 10 ? n.heartbeat.substr(-8) : n.heartbeat) + '</span></div>' +
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
    var h = '';
    for (var i = 0; i < links.length; i++) {
      var l = links[i];
      var st = l.status || 'normal';
      var bwStr = l.bandwidth >= 1000 ? (l.bandwidth / 1000).toFixed(1) + ' Gbps' : l.bandwidth + ' Mbps';
      var stLabel = { excellent: '极佳', normal: '正常', congested: '拥塞', unstable: '不稳定', down: '中断' };
      h += '<div class="sd-link-item status-' + st + '">' +
        '<div class="sd-link-top">' +
          '<span class="sd-link-name">' + escapeHtml(l.name || (l.source + ' → ' + l.target)) + '</span>' +
          '<span class="sd-link-status-label ' + st + '">' + (stLabel[st] || st) + '</span>' +
        '</div>' +
        '<div class="sd-link-path">' + escapeHtml(l.source) + ' → ' + escapeHtml(l.target) + '</div>' +
        '<div class="sd-link-metrics">' +
          '<span>时延 <strong>' + l.latency + 'ms</strong></span>' +
          '<span>抖动 <strong>' + l.jitter + 'ms</strong></span>' +
          '<span>丢包 <strong>' + l.packetLoss + '%</strong></span>' +
          '<span>带宽 <strong>' + bwStr + '</strong></span>' +
        '</div>' +
      '</div>';
    }
    list.innerHTML = h;
  }

  // ── Fault Alerts ──
  function renderFaultAlerts() {
    var panel = $('sd-alerts-panel');
    if (!panel) return;
    var alerts = state.faultAlertsCopy;
    if (alerts.length === 0) {
      panel.innerHTML = '<div class="sd-alerts-empty">当前无故障告警</div>';
      return;
    }
    var h = '';
    for (var i = 0; i < alerts.length; i++) {
      var a = alerts[i];
      var lvl = a.level || 'warning';
      var levelTxt = lvl === 'critical' ? '严重' : (lvl === 'warning' ? '警告' : '错误');
      h += '<div class="sd-alert-card level-' + lvl + '">' +
        '<div class="sd-alert-top">' +
          '<span class="sd-alert-level ' + lvl + '">' + levelTxt + '</span>' +
          '<span class="sd-alert-time">' + escapeHtml(a.time) + '</span>' +
        '</div>' +
        '<div class="sd-alert-detail">' + escapeHtml(typeLabel(a.type)) + ': ' + escapeHtml(a.targetName || a.targetId) + '</div>' +
        '<div class="sd-alert-reason">' + escapeHtml(a.reason) + '</div>';
      if (a.autoRecovery && a.recoveryStatus !== 'recovered') {
        h += '<div class="sd-alert-recovery">自动恢复中… (' + recoveryStatusLabel(a.recoveryStatus) + ')</div>';
      }
      if (a.recoveryStatus === 'recovered' && !a.confirmed) {
        h += '<div class="sd-alert-actions">' +
          '<button onclick="ComputePlatform.confirmAlertRecovery(\'' + a.id + '\')">确认恢复</button>' +
          '<button onclick="ComputePlatform.resolveAlert(\'' + a.id + '\')">忽略</button>' +
        '</div>';
      }
      h += '</div>';
    }
    panel.innerHTML = h;
  }

  // ── Charts ──
  function buildMiniSvgChart(samples, field, unit, color) {
    color = color || '#78bfd2';
    var svgW = 280, svgH = 130, padL = 40, padR = 15, padT = 10, padB = 25;
    var w = svgW - padL - padR, h = svgH - padT - padB;
    if (samples.length < 2) samples = [{ bandwidth: 0, latency: 0, packetLoss: 0 }, { bandwidth: 0, latency: 0, packetLoss: 0 }];
    var vals = samples.map(function(s) { return s[field]; });
    var maxV = Math.max.apply(null, vals);
    var minV = Math.min.apply(null, vals);
    var range = (maxV - minV) || 1;
    var pts = '';
    for (var i = 0; i < vals.length; i++) {
      var x = padL + (i / Math.max(1, vals.length - 1)) * w;
      var y = padT + h - ((vals[i] - minV) / range) * h;
      pts += x.toFixed(1) + ',' + y.toFixed(1) + ' ';
    }
    var lastX = padL + w;
    var lastY = padT + h - ((vals[vals.length - 1] - minV) / range) * h;
    var fillPts = padL.toFixed(1) + ',' + (padT + h).toFixed(1) + ' ' + pts + lastX.toFixed(1) + ',' + (padT + h).toFixed(1);

    var valDisplay = vals[vals.length - 1];
    if (field === 'bandwidth') {
      valDisplay = valDisplay >= 10 ? valDisplay.toFixed(2) + ' Gbps' : valDisplay.toFixed(2) + ' Gbps';
    } else if (field === 'latency') {
      valDisplay = valDisplay.toFixed(1) + ' ms';
    } else {
      valDisplay = valDisplay.toFixed(2) + '%';
    }

    return '<svg viewBox="0 0 ' + svgW + ' ' + svgH + '" xmlns="http://www.w3.org/2000/svg">' +
      '<polyline fill="none" stroke="' + color + '" stroke-width="1.5" points="' + pts.trim() + '"/>' +
      '<polygon fill="' + color + '" fill-opacity="0.1" points="' + fillPts.trim() + '"/>' +
      '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="3" fill="' + color + '"/>' +
      '<text x="' + padL + '" y="' + (padT + h + 16) + '" fill="#999" font-size="9" text-anchor="middle">' + minV.toFixed(1) + '</text>' +
      '<text x="' + padL + '" y="' + (padT + 9) + '" fill="#999" font-size="9" text-anchor="middle">' + maxV.toFixed(1) + '</text>' +
      '<text x="' + (padL + w) + '" y="' + (padT + h + 16) + '" fill="#999" font-size="9" text-anchor="end">' + vals.length + '</text>' +
      '</svg>';
  }

  function renderSensingCharts() {
    var samples = state.networkSamplesCopy;
    var titles = [
      { id: 'sd-chart-bandwidth', field: 'bandwidth', unit: 'Gbps', color: '#78bfd2', label: '总带宽' },
      { id: 'sd-chart-latency', field: 'latency', unit: 'ms', color: '#d7a84f', label: '平均时延' },
      { id: 'sd-chart-loss', field: 'packetLoss', unit: '%', color: '#d67f85', label: '丢包率' }
    ];
    for (var i = 0; i < titles.length; i++) {
      var t = titles[i];
      var wrap = $(t.id);
      if (!wrap) continue;
      var svg = buildMiniSvgChart(samples, t.field, t.unit, t.color);
      var last = samples[samples.length - 1];
      var cur = last[t.field];
      var curStr;
      if (t.field === 'bandwidth') curStr = cur.toFixed(2) + ' Gbps';
      else if (t.field === 'latency') curStr = cur.toFixed(1) + ' ms';
      else curStr = cur.toFixed(2) + '%';
      wrap.innerHTML = '<div class="sd-chart-title">' + t.label + '</div>' + svg + '<div class="sd-chart-current">当前: ' + curStr + '</div>';
    }
  }

  // ── Storage ──
  function renderStorageNodes() {
    var grid = $('sd-storage-grid');
    if (!grid) return;
    var storages = state.storageNodesCopy;
    var h = '';
    for (var i = 0; i < storages.length; i++) {
      var s = storages[i];
      var pct = Math.round((s.usedTB / s.capacityTB) * 100);
      var barClass = pct >= 90 ? 'danger' : (pct >= 75 ? 'warn' : '');
      h += '<div class="sd-storage-card' + (s.status === 'warning' ? ' status-warning' : '') + '">' +
        '<div class="sd-storage-name">' + escapeHtml(s.name) + '</div>' +
        '<div class="sd-storage-used">' + s.usedTB.toFixed(1) + ' / ' + s.capacityTB + ' TB (' + pct + '%)</div>' +
        '<div class="sd-storage-bar"><div class="sd-storage-bar-fill ' + barClass + '" style="width:' + pct + '%"></div></div>' +
        '<div class="sd-storage-speed"><span>读 ' + s.readMBps + ' MB/s</span><span>写 ' + s.writeMBps + ' MB/s</span></div>' +
        '<div class="sd-storage-conn">连接数: ' + s.connections + '</div>' +
        '</div>';
    }
    grid.innerHTML = h;
  }

  function renderStorageSummary() {
    var sum = $('sd-storage-summary');
    if (!sum) return;
    var storages = state.storageNodesCopy;
    var totalCap = 0, totalUsed = 0, totalRead = 0, totalWrite = 0, totalConn = 0;
    for (var i = 0; i < storages.length; i++) {
      var s = storages[i];
      totalCap += s.capacityTB;
      totalUsed += s.usedTB;
      totalRead += s.readMBps;
      totalWrite += s.writeMBps;
      totalConn += s.connections;
    }
    var cacheHit = '--';
    sum.innerHTML =
      '<div class="sd-storage-stat"><strong>' + totalCap.toFixed(0) + ' TB</strong>总容量</div>' +
      '<div class="sd-storage-stat"><strong>' + totalUsed.toFixed(1) + ' TB</strong>已使用</div>' +
      '<div class="sd-storage-stat"><strong>' + totalRead + ' MB/s</strong>总读吞吐</div>' +
      '<div class="sd-storage-stat"><strong>' + totalWrite + ' MB/s</strong>总写吞吐</div>' +
      '<div class="sd-storage-stat"><strong>' + cacheHit + '</strong>缓存命中率</div>' +
      '<div class="sd-storage-stat"><strong>' + totalConn + '</strong>总连接数</div>';
  }

  // ── Switch History ──
  function renderSwitchHistory() {
    var wrap = $('sd-switch-table-wrapper');
    if (!wrap) return;
    var records = state.switchRecordsCopy;
    var h = '<table class="sd-switch-table"><thead><tr><th>时间</th><th>类型</th><th>源 → 目标</th><th>原因</th><th>耗时(s)</th><th>结果</th></tr></thead><tbody>';
    for (var i = 0; i < records.length; i++) {
      var r = records[i];
      var srcDst = escapeHtml(r.source) + ' → ' + escapeHtml(r.target);
      if (srcDst.length > 30) srcDst = srcDst.substr(0, 28) + '…';
      h += '<tr>' +
        '<td>' + escapeHtml(r.time) + '</td>' +
        '<td>' + escapeHtml(r.type) + '</td>' +
        '<td>' + srcDst + '</td>' +
        '<td>' + escapeHtml(r.reason) + '</td>' +
        '<td>' + r.duration.toFixed(1) + '</td>' +
        '<td class="result-' + (r.result === '成功' ? 'success' : 'fail') + '">' + escapeHtml(r.result) + '</td>' +
        '</tr>';
    }
    h += '</tbody></table>';
    wrap.innerHTML = h;
  }

  // ── Bottom Metrics ──
  function renderBottomMetrics() {
    var bar = $('sd-metrics-bar');
    if (!bar) return;
    var links = state.networkLinksCopy;
    var totalLat = 0, totalBw = 0, onlineNodes = 0, activeLinks = 0;
    for (var i = 0; i < links.length; i++) {
      totalLat += links[i].latency;
      totalBw += links[i].bandwidth;
      if (links[i].status !== 'down') activeLinks++;
    }
    var nodes = state.sensingNodesCopy;
    for (var j = 0; j < nodes.length; j++) {
      if (nodes[j].status !== 'offline') onlineNodes++;
    }
    var availRate = activeLinks / Math.max(1, links.length) * 100;
    var taskCount = nodes.reduce(function(acc, n) { return acc + (n.status === 'normal' || n.status === 'highload' || n.status === 'abnormal' ? 1 : 0); }, 0);
    bar.innerHTML =
      '<div class="sd-metric-item"><div class="sd-metric-label">全链路时延</div><div class="sd-metric-value">' + (totalLat).toFixed(0) + ' ms</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">可用率</div><div class="sd-metric-value">' + availRate.toFixed(1) + '%</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">活跃任务</div><div class="sd-metric-value">' + taskCount + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">总吞吐</div><div class="sd-metric-value">' + (totalBw / 1000).toFixed(1) + ' Gbps</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">在线节点</div><div class="sd-metric-value">' + onlineNodes + '/' + nodes.length + '</div></div>' +
      '<div class="sd-metric-item"><div class="sd-metric-label">活跃链路</div><div class="sd-metric-value">' + activeLinks + '/' + links.length + '</div></div>';
  }

  // ── Monitoring lifecycle ──
  function startMonitoring() {
    stopMonitoring();
    state.networkRefreshCountdown = 5;
    state.monitoringTimer = setInterval(function() {
      state.networkRefreshCountdown--;
      if (state.networkRefreshCountdown <= 0) {
        refreshMonitoringData();
        state.networkRefreshCountdown = 5;
      }
    }, 1000);
  }

  function stopMonitoring() {
    if (state.monitoringTimer) {
      clearInterval(state.monitoringTimer);
      state.monitoringTimer = null;
    }
  }

  // ── Entry ──
  function renderNetwork() {
    // Load from localStorage (overrides switch records)
    loadSensingFromLocalStorage();

    // Show loading states
    showLoading('sd-nodes-grid');
    showLoading('sd-links-list');
    showLoading('sd-storage-grid');
    showLoading('sd-alerts-panel');

    // Fetch real data from API
    fetchMonitoringNodes().then(function(data) {
      if (data.nodes && data.nodes.length > 0) {
        state.sensingNodesCopy = data.nodes;
      }
      hideLoading('sd-nodes-grid');
      renderSensingNodes();
      renderBottomMetrics();
    });

    fetchNetworkLinks().then(function(data) {
      var links = data.links || [];
      var stats = data.stats || {};
      if (links.length === 0) {
        state.networkLinksCopy = [];
      } else {
        state.networkLinksCopy = links;
      }
      hideLoading('sd-links-list');
      renderSensingLinks();
      renderBottomMetrics();
    });

    fetchMonitoringSamples(20).then(function(data) {
      if (data.samples && data.samples.length > 0) {
        state.networkSamplesCopy = data.samples;
      }
      renderSensingCharts();
    });

    fetchStorageData().then(function(data) {
      if (data.targets && data.targets.length > 0) {
        state.storageNodesCopy = data.targets;
      }
      hideLoading('sd-storage-grid');
      renderStorageNodes();
      renderStorageSummary();
    });

    fetchAlerts('open', 20).then(function(data) {
      if (data.items && data.items.length > 0) {
        state.faultAlertsCopy = data.items;
      }
      hideLoading('sd-alerts-panel');
      renderFaultAlerts();
    });

    renderSensingHeader();
    renderSwitchHistory();

    // Start/stop monitoring
    if (state.activeTab === 'network' && state.isNetworkAutoRefresh) {
      startMonitoring();
      startClockTimer();
    } else {
      stopMonitoring();
    }
  }

  function toggleNetworkRefresh() {
    var cb = document.getElementById('sd-auto-refresh');
    state.isNetworkAutoRefresh = cb ? cb.checked : !state.isNetworkAutoRefresh;
    if (state.isNetworkAutoRefresh && state.activeTab === 'network') {
      state.networkRefreshCountdown = 5;
      startMonitoring();
    } else {
      stopMonitoring();
    }
    saveSensingToLocalStorage();
    renderSensingHeader();
  }

  function manualNetworkRefresh() {
    refreshMonitoringData();
    state.networkRefreshCountdown = 5;
    showToast('感知数据已刷新', 'info');
  }

  // ── Node Detail ──
  function showNodeDetail(nodeId) {
    var nodes = state.sensingNodesCopy;
    var node = null;
    for (var i = 0; i < nodes.length; i++) { if (nodes[i].id === nodeId) { node = nodes[i]; break; } }
    if (!node) return;
    var st = statusLabel(node.status);
    var h = '<div style="line-height:2;">' +
      '<div><strong>名称:</strong> ' + escapeHtml(node.name) + '</div>' +
      '<div><strong>GPU型号:</strong> ' + escapeHtml(node.gpuModel) + '</div>' +
      '<div><strong>GPU利用率:</strong> ' + node.gpuUtil + '%</div>' +
      '<div><strong>VRAM利用率:</strong> ' + node.vramUtil + '%</div>' +
      '<div><strong>温度:</strong> ' + node.temp + '°C</div>' +
      '<div><strong>当前任务:</strong> ' + escapeHtml(node.currentTask) + '</div>' +
      '<div><strong>心跳:</strong> ' + escapeHtml(node.heartbeat) + '</div>' +
      '<div><strong>状态:</strong> ' + badge(st, 'status-' + node.status) + '</div>' +
      '</div>';
    showDetailDrawer(node.name + ' - 节点详情', h);
  }

  // ── Fault Simulation ──
  function showFaultSimModal() {
    if (!demoEnabled()) {
      showToast('故障模拟仅为演示功能，生产模式不可用', 'warning');
      return;
    }
    var overlay = document.getElementById('sd-fault-modal');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'sd-fault-modal';
      overlay.className = 'sd-modal-overlay';
      overlay.innerHTML =
        '<div class="sd-modal-card">' +
          '<div class="sd-modal-title">故障模拟配置</div>' +
          '<div class="sd-modal-field">' +
            '<label>故障目标</label>' +
            '<select id="sd-fault-target"></select>' +
          '</div>' +
          '<div class="sd-modal-field">' +
            '<label>故障类型</label>' +
            '<select id="sd-fault-type">' +
              '<option value="gpu_overheat">GPU温度过高</option>' +
              '<option value="link_degrade">链路降级</option>' +
              '<option value="storage_corrupt">存储故障</option>' +
              '<option value="node_offline">节点离线</option>' +
            '</select>' +
          '</div>' +
          '<div class="sd-modal-actions">' +
            '<button onclick="ComputePlatform.closeFaultSimModal()">取消</button>' +
            '<button class="sd-modal-btn-primary" onclick="ComputePlatform.startFaultSimulation()">开始模拟</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(overlay);
    }
    // Populate target dropdown
    var sel = document.getElementById('sd-fault-target');
    if (sel) {
      var opts = '';
      var nodes = state.sensingNodesCopy;
      for (var i = 0; i < nodes.length; i++) {
        opts += '<option value="sn-' + (i + 1) + '">' + (nodes[i].name + ' (' + nodes[i].gpuModel + ')') + '</option>';
      }
      var links = state.networkLinksCopy;
      for (var j = 0; j < links.length; j++) {
        opts += '<option value="' + links[j].id + '">' + (links[j].name || (links[j].source + ' → ' + links[j].target)) + '</option>';
      }
      var storages = state.storageNodesCopy;
      for (var k = 0; k < storages.length; k++) {
        opts += '<option value="' + storages[k].id + '">' + storages[k].name + '</option>';
      }
      sel.innerHTML = opts;
    }
    overlay.classList.add('open');
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
      '<div class="cp-cost-card"><div class="cp-cost-label">累计费用</div><div class="cp-cost-value">' + ((typeof total === 'number') ? total.toFixed(2) : total) + '<span class="cp-cost-unit"> 元</span></div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">活跃渲染任务</div><div class="cp-cost-value">' + (b.render_stats ? b.render_stats.active_render_jobs || 0 : 0) + '<span class="cp-cost-unit"> 个</span></div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">总渲染任务</div><div class="cp-cost-value">' + (b.render_stats ? b.render_stats.total_render_jobs || 0 : 0) + '<span class="cp-cost-unit"> 个</span></div></div>' +
      '<div class="cp-cost-card"><div class="cp-cost-label">账户余额</div>' +
      '<div class="cp-cost-breakdown">' + accountBalances + '</div></div>';

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
      updateStatusBar();
      renderOverviewIfActive();
    }).catch(function(err) {
      console.error('资源摘要加载失败:', err);
      showToast('资源摘要加载失败', 'warning');
    });

    // Load hosts (GPU scheduling tab)
    api('/api/cloud/hosts?limit=200').then(function(hostsData) {
      state.apiHosts = hostsData || {};
      if (state.activeTab === 'gpu') renderGPU();
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
      if (state.activeTab === 'overview') renderOverview();
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
    var s = state.apiSummary || {};
    var nodes = s.total_nodes || 0;
    var online = s.online_nodes || 0;
    var queue = s.queue_depth || 0;
    demoStatus.textContent = '算力节点：共 ' + nodes + ' 台，在线 ' + online + ' 台，排队 ' + queue + ' 个任务';
  }

  // ══════════════════════════════════════════════════
  // Initialization
  // ══════════════════════════════════════════════════
  function init() {
    // Demo datasets are only used for clearly-labelled visual modules.  In
    // production they must never populate nodes, sessions or metrics.
    var demoMode = !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
    var data = demoMode ? (window.AIGV_DEMO_DATA || {}) : {};
    state.demoData = data;
    state.renderSessions = JSON.parse(JSON.stringify(data.renderSessions || []));
    state.networkLinksCopy = JSON.parse(JSON.stringify(data.networkLinks || []));
    state.sensingNodesCopy = JSON.parse(JSON.stringify(data.sensingNodes || []));
    state.storageNodesCopy = JSON.parse(JSON.stringify(data.storageNodes || []));
    state.networkSamplesCopy = JSON.parse(JSON.stringify(data.networkSamples || []));
    state.faultAlertsCopy = JSON.parse(JSON.stringify(data.faultAlerts || []));
    state.switchRecordsCopy = JSON.parse(JSON.stringify(data.switchRecords || []));
    state.alerts = JSON.parse(JSON.stringify(data.alerts || []));
    state.opsEvents = JSON.parse(JSON.stringify(data.opsEvents || []));

    // Load from localStorage (overrides above)
    loadFromLocalStorage();

    // Fetch real data from APIs
    loadRealData();

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

    // Tab 5
    toggleNetworkRefresh: toggleNetworkRefresh,
    manualNetworkRefresh: manualNetworkRefresh,
    handleSimulateAnomaly: handleSimulateAnomaly,
    showNodeDetail: showNodeDetail,
    showFaultSimModal: showFaultSimModal,
    closeFaultSimModal: closeFaultSimModal,
    startFaultSimulation: startFaultSimulation,
    confirmAlertRecovery: confirmAlertRecovery,
    resolveAlert: resolveAlert,

    // Tab 7
    handleAcknowledgeAlert: handleAcknowledgeAlert,
    handleMarkProcessing: handleMarkProcessing,
    handleCloseAlert: handleCloseAlert
  };

  document.addEventListener('DOMContentLoaded', init);
})();
