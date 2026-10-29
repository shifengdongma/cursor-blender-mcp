/**
 * AIGV Studio Cloud Hosts Page
 * Vanilla JS implementation for public/private cloud host management
 * Fetches real data from GET /api/cloud/hosts
 * Scope: public (aliyun,tencent) | private (vmware,generic_rest)
 */
(function() {
  'use strict';

  // ── DOM helpers ──
  function $(id) { return document.getElementById(id); }
  function escapeHtml(text) {
    if (text == null) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ── API helper ──
  function api(path) {
    return window.AIGV.api(path);
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

  // ── Status constants ──
  var STATUS_MAP = {
    running: { label: '运行中', cls: 'ch-badge-running' },
    stopped: { label: '已关机', cls: 'ch-badge-stopped' },
    error: { label: '异常', cls: 'ch-badge-error' },
    maintenance: { label: '维护中', cls: 'ch-badge-maintenance' }
  };

  // ── Metrics helper ──
  function getMetricValue(host, field) {
    if (host[field] !== undefined && host[field] !== null) return host[field];
    if (host.metrics && host.metrics.latest && host.metrics.latest[field] !== undefined) return host.metrics.latest[field];
    return null;
  }

  function getCpuPercent(host) {
    return getMetricValue(host, 'cpu_percent');
  }

  function getMemPercent(host) {
    return getMetricValue(host, 'memory_percent');
  }

  // ── State management ──
  var state = {
    scope: 'public',
    allHosts: [],
    filteredHosts: [],
    searchQuery: '',
    filters: { vendor: 'all', region: 'all', status: 'all' },
    sortField: 'node_name',
    sortAsc: true,
    currentPage: 1,
    pageSize: 20,
    isLoading: false,
    totalItems: 0,
    modifiedStates: {} // key: node_name -> { status, cpuUsage, memUsage }
  };

  var LS_KEY = 'aigv_cloud_hosts_v1';

  function demoMode() {
    return !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
  }

  function saveToLocalStorage() {
    if (!demoMode()) return;
    try {
      var payload = {
        scope: state.scope,
        modifiedStates: state.modifiedStates,
        pageSize: state.pageSize
      };
      localStorage.setItem(LS_KEY, JSON.stringify(payload));
    } catch (e) {}
  }

  function loadFromLocalStorage() {
    if (!demoMode()) {
      try { localStorage.removeItem(LS_KEY); } catch (e) {}
      return;
    }
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return;
      var payload = JSON.parse(raw);
      if (payload && payload.scope === state.scope) {
        if (payload.modifiedStates) state.modifiedStates = payload.modifiedStates;
        if (payload.pageSize) state.pageSize = payload.pageSize;
      }
    } catch (e) {}
  }

  function getEffectiveHost(host) {
    var mod = state.modifiedStates[host.node_name];
    if (mod) {
      var h = {};
      for (var k in host) h[k] = host[k];
      if (mod.status !== undefined) h.status = mod.status;
      if (mod.cpuUsage !== undefined) h.cpu_percent = mod.cpuUsage;
      if (mod.memUsage !== undefined) h.memory_percent = mod.memUsage;
      if (mod.status === 'stopped') { h.cpu_percent = 0; h.memory_percent = 0; }
      return h;
    }
    return host;
  }

  // ── Data loading ──
  function loadHosts() {
    state.isLoading = true;
    showLoadingIndicator();

    // Map scope to provider_type
    var providerType = state.scope === 'private' ? 'vmware,generic_rest' : 'aliyun,tencent';

    // Override provider_type if vendor filter is active
    if (state.filters.vendor !== 'all') {
      providerType = state.filters.vendor;
    }

    var params = [];
    params.push('provider_type=' + encodeURIComponent(providerType));
    params.push('limit=' + state.pageSize);
    params.push('offset=' + ((state.currentPage - 1) * state.pageSize));
    params.push('sort=' + encodeURIComponent(state.sortField));
    params.push('order=' + (state.sortAsc ? 'asc' : 'desc'));

    if (state.filters.region !== 'all') {
      params.push('region=' + encodeURIComponent(state.filters.region));
    }
    if (state.filters.status !== 'all') {
      params.push('status=' + encodeURIComponent(state.filters.status));
    }
    if (state.searchQuery) {
      params.push('keyword=' + encodeURIComponent(state.searchQuery));
    }

    var path = '/api/cloud/hosts?' + params.join('&');

    api(path).then(function(response) {
      state.allHosts = response.items || [];
      state.totalItems = response.total || state.allHosts.length;
      state.isLoading = false;
      hideLoadingIndicator();
      applyFiltersAndRender();
      renderSummary();
    }).catch(function(err) {
      state.isLoading = false;
      hideLoadingIndicator();
      showToast('加载主机列表失败: ' + (err.message || '未知错误'), 'error');
      state.allHosts = [];
      state.totalItems = 0;
      applyFiltersAndRender();
      renderSummary();
    });
  }

  function showLoadingIndicator() {
    var container = $('ch-host-table');
    if (!container) return;
    container.innerHTML = '<div class="ch-loading"><div class="ch-loading-spinner"></div><p>正在加载主机数据...</p></div>';
    var pag = $('ch-pagination');
    if (pag) pag.innerHTML = '';
  }

  function hideLoadingIndicator() {
    // Loading indicator is replaced when renderTable is called
  }

  // ── Render functions ──
  function renderSummary() {
    var hosts = state.allHosts;
    var running = 0, stopped = 0, error = 0, maintenance = 0;
    var totalCpu = 0, totalMem = 0;

    for (var i = 0; i < hosts.length; i++) {
      var h = getEffectiveHost(hosts[i]);
      switch (h.status) {
        case 'running': running++; totalCpu += (h.cpu_cores || 0); totalMem += (h.memory_mb || 0); break;
        case 'stopped': stopped++; break;
        case 'error': error++; break;
        case 'maintenance': maintenance++; break;
      }
    }

    var grid = $('ch-summary-grid');
    if (!grid) return;

    var items = [
      { label: '运行中', value: running, unit: '台', accent: 'green' },
      { label: '已关机', value: stopped, unit: '台', accent: 'muted' },
      { label: '异常', value: error, unit: '台', accent: 'red' },
      { label: '维护中', value: maintenance, unit: '台', accent: 'purple' },
      { label: '总CPU', value: totalCpu, unit: '核', accent: 'cyan' },
      { label: '总内存', value: Math.round(totalMem / 1024 * 10) / 10, unit: 'GB', accent: 'gold' }
    ];

    var html = '';
    for (var j = 0; j < items.length; j++) {
      var item = items[j];
      html += '<div class="ch-stat-card ch-stat-accent-' + item.accent + '">' +
        '<div class="ch-stat-value">' + item.value + '<span class="ch-stat-unit"> ' + item.unit + '</span></div>' +
        '<div class="ch-stat-label">' + item.label + '</div>' +
        '</div>';
    }
    grid.innerHTML = html;
  }

  function renderFilterBar() {
    var bar = $('ch-filter-bar');
    if (!bar) return;

    var hosts = state.allHosts;
    var vendorSet = {}, regionSet = {};
    for (var i = 0; i < hosts.length; i++) {
      vendorSet[hosts[i].provider_type] = true;
      regionSet[hosts[i].region] = true;
    }

    var vendorOptions = '<option value="all">全部厂商</option>';
    var keys = [];
    for (var v in vendorSet) keys.push(v);
    keys.sort();
    for (var k = 0; k < keys.length; k++) {
      vendorOptions += '<option value="' + escapeHtml(keys[k]) + '">' + escapeHtml(keys[k]) + '</option>';
    }

    var regionKeys = [];
    for (var r in regionSet) regionKeys.push(r);
    regionKeys.sort();
    var regionOptions = '<option value="all">全部区域</option>';
    for (var m = 0; m < regionKeys.length; m++) {
      regionOptions += '<option value="' + escapeHtml(regionKeys[m]) + '">' + escapeHtml(regionKeys[m]) + '</option>';
    }

    bar.innerHTML =
      '<div class="ch-search-wrapper">' +
      '<input type="text" class="ch-search-input" id="ch-search-input" placeholder="搜索主机名称或IP..." value="' + escapeHtml(state.searchQuery) + '">' +
      '</div>' +
      '<select class="ch-filter-select" id="ch-filter-vendor">' + vendorOptions + '</select>' +
      '<select class="ch-filter-select" id="ch-filter-region">' + regionOptions + '</select>' +
      '<select class="ch-filter-select" id="ch-filter-status">' +
      '<option value="all">全部状态</option>' +
      '<option value="running">运行中</option>' +
      '<option value="stopped">已关机</option>' +
      '<option value="error">异常</option>' +
      '<option value="maintenance">维护中</option>' +
      '</select>' +
      '<span class="ch-count-badge" id="ch-count-badge"></span>';

    // Set filter values
    var selVendor = $('ch-filter-vendor');
    var selRegion = $('ch-filter-region');
    var selStatus = $('ch-filter-status');
    if (selVendor && state.filters.vendor) selVendor.value = state.filters.vendor;
    if (selRegion && state.filters.region) selRegion.value = state.filters.region;
    if (selStatus && state.filters.status) selStatus.value = state.filters.status;
  }

  var _searchTimer = null;
  function handleSearchInput() {
    var el = $('ch-search-input');
    if (!el) return;
    if (_searchTimer) clearTimeout(_searchTimer);
    _searchTimer = setTimeout(function() {
      state.searchQuery = el.value.trim().toLowerCase();
      state.currentPage = 1;
      // Pass keyword to backend API for server-side search, fallback to client-side
      loadHosts();
    }, 300);
  }

  function handleFilter() {
    var vendorEl = $('ch-filter-vendor');
    var regionEl = $('ch-filter-region');
    var statusEl = $('ch-filter-status');
    if (vendorEl) state.filters.vendor = vendorEl.value;
    if (regionEl) state.filters.region = regionEl.value;
    if (statusEl) state.filters.status = statusEl.value;
    state.currentPage = 1;
    loadHosts();
  }

  function applyFiltersAndRender() {
    var hosts = state.allHosts;
    var filtered = [];

    for (var i = 0; i < hosts.length; i++) {
      var h = getEffectiveHost(hosts[i]);
      // Client-side search fallback: further filter by name or IP
      if (state.searchQuery) {
        var lq = state.searchQuery;
        var nameMatch = h.node_name && h.node_name.toLowerCase().indexOf(lq) !== -1;
        var ipMatch = h.ip_address && h.ip_address.toLowerCase().indexOf(lq) !== -1;
        var providerMatch = h.provider_type && h.provider_type.toLowerCase().indexOf(lq) !== -1;
        if (!nameMatch && !ipMatch && !providerMatch) continue;
      }
      filtered.push(h);
    }

    state.filteredHosts = filtered;
    renderTable();
    renderPagination();

    var badge = $('ch-count-badge');
    if (badge) badge.textContent = '共 ' + filtered.length + ' 台主机';
  }

  function handleSort(field) {
    if (state.sortField === field) {
      state.sortAsc = !state.sortAsc;
    } else {
      state.sortField = field;
      state.sortAsc = true;
    }
    state.currentPage = 1;
    loadHosts();

    // Update sort arrows in DOM
    var arrows = document.querySelectorAll('.ch-sort-arrow');
    for (var i = 0; i < arrows.length; i++) {
      arrows[i].textContent = '';
    }
    var activeArrow = document.querySelector('.ch-sort-arrow[data-field="' + field + '"]');
    if (activeArrow) {
      activeArrow.textContent = state.sortAsc ? ' \u25B2' : ' \u25BC';
    }
  }

  function renderTable() {
    var container = $('ch-host-table');
    if (!container) return;

    var hosts = state.filteredHosts;
    var page = state.currentPage;
    var size = state.pageSize;
    var start = (page - 1) * size;
    var pageData = hosts.slice(start, start + size);

    // If there are search-filtered results, show them; otherwise show paginated slice
    if (state.searchQuery && hosts.length < size) {
      pageData = hosts; // show all search results
    }

    // Sort arrow helpers
    function sortArrow(field) {
      if (state.sortField !== field) return '';
      return '<span class="ch-sort-arrow" data-field="' + field + '">' + (state.sortAsc ? ' \u25B2' : ' \u25BC') + '</span>';
    }

    var html = '<table class="cp-table ch-host-table">' +
      '<thead><tr>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'node_name\')">名称' + sortArrow('node_name') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'provider_type\')">厂商' + sortArrow('provider_type') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'region\')">区域' + sortArrow('region') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'ip_address\')">IP地址' + sortArrow('ip_address') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'cpu_cores\')">CPU（核）' + sortArrow('cpu_cores') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'memory_mb\')">内存（GB）' + sortArrow('memory_mb') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'gpu_count\')">GPU' + sortArrow('gpu_count') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'status\')">状态' + sortArrow('status') + '</th>' +
      '<th>CPU利用率</th>' +
      '<th>内存利用率</th>' +
      '<th>操作</th>' +
      '</tr></thead><tbody>';

    if (pageData.length === 0) {
      html += '<tr><td colspan="11" style="text-align:center;padding:40px;color:var(--text-muted)">没有匹配的主机数据</td></tr>';
    } else {
      for (var i = 0; i < pageData.length; i++) {
        var h = pageData[i];
        var statusInfo = STATUS_MAP[h.status] || STATUS_MAP.running;
        var gpuLabel = (h.gpu_count || 0) > 0 ? ((h.gpu_type || 'GPU') + ' x' + h.gpu_count) : '-';
        var cpuPct = getCpuPercent(h);
        var memPct = getMemPercent(h);
        html += '<tr>' +
          '<td><span class="ch-host-name-link" onclick="CloudHosts.showDetail(\'' + escapeHtml(h.node_name) + '\')">' + escapeHtml(h.node_name) + '</span></td>' +
          '<td>' + escapeHtml(h.provider_type) + '</td>' +
          '<td>' + escapeHtml(h.region) + '</td>' +
          '<td class="ch-cell-mono">' + escapeHtml(h.ip_address) + '</td>' +
          '<td>' + (h.cpu_cores != null ? h.cpu_cores : '-') + '</td>' +
          '<td>' + (h.memory_mb != null ? Math.round(h.memory_mb / 1024 * 10) / 10 : '-') + '</td>' +
          '<td>' + escapeHtml(gpuLabel) + '</td>' +
          '<td><span class="' + statusInfo.cls + '">' + statusInfo.label + '</span></td>' +
          '<td>' + renderUsageBar(cpuPct) + '</td>' +
          '<td>' + renderUsageBar(memPct) + '</td>' +
          '<td><button class="ch-action-btn" onclick="CloudHosts.showDetail(\'' + escapeHtml(h.node_name) + '\')">详情</button></td>' +
          '</tr>';
      }
    }

    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function renderUsageBar(pct) {
    if (pct === null || pct === undefined) {
      return '<div class="ch-usage-bar"><div class="ch-usage-fill" style="width:0%"></div><span class="ch-usage-text">N/A</span></div>';
    }
    var cls = pct > 80 ? ' ch-usage-danger' : (pct > 60 ? ' ch-usage-caution' : '');
    return '<div class="ch-usage-bar"><div class="ch-usage-fill' + cls + '" style="width:' + pct + '%"></div><span class="ch-usage-text">' + pct + '%</span></div>';
  }

  function renderPagination() {
    var container = $('ch-pagination');
    if (!container) return;

    var totalItems = state.totalItems;
    // If client-side search is active, use filtered length for display but API total for page count
    var displayTotal = totalItems;
    if (state.searchQuery) {
      displayTotal = state.filteredHosts.length;
    }

    var pageSize = state.pageSize;
    var totalPages = Math.ceil(totalItems / pageSize) || 1;
    // When search is active, use filtered count for page calculation
    var displayPages = state.searchQuery ? (Math.ceil(displayTotal / pageSize) || 1) : totalPages;

    var current = state.currentPage;
    if (current > totalPages) current = totalPages;
    if (current < 1) current = 1;

    var start = (current - 1) * pageSize + 1;
    var end = Math.min(current * pageSize, displayTotal);

    var html = '<div class="ch-pagination-info">显示 ' + start + '-' + end + '，共 ' + displayTotal + ' 台</div>';
    html += '<div class="ch-pagination-controls">';
    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(1)"' + (current <= 1 ? ' disabled' : '') + '>首页</button>';
    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + (current - 1) + ')"' + (current <= 1 ? ' disabled' : '') + '>上一页</button>';

    // Page numbers
    var pageStart = Math.max(1, current - 2);
    var pageEnd = Math.min(displayPages, current + 2);
    if (pageStart > 1) {
      html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(1)">1</button>';
      if (pageStart > 2) html += '<span class="ch-page-ellipsis">...</span>';
    }
    for (var p = pageStart; p <= pageEnd; p++) {
      html += '<button class="ch-page-btn' + (p === current ? ' active' : '') + '" onclick="CloudHosts.goToPage(' + p + ')">' + p + '</button>';
    }
    if (pageEnd < displayPages) {
      if (pageEnd < displayPages - 1) html += '<span class="ch-page-ellipsis">...</span>';
      html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + displayPages + ')">' + displayPages + '</button>';
    }

    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + (current + 1) + ')"' + (current >= totalPages ? ' disabled' : '') + '>下一页</button>';
    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + totalPages + ')"' + (current >= totalPages ? ' disabled' : '') + '>末页</button>';
    html += '</div>';

    html += '<div class="ch-page-size">' +
      '<span>每页</span>' +
      '<select onchange="CloudHosts.changePageSize(this.value)">' +
      '<option value="10"' + (pageSize === 10 ? ' selected' : '') + '>10</option>' +
      '<option value="20"' + (pageSize === 20 ? ' selected' : '') + '>20</option>' +
      '<option value="50"' + (pageSize === 50 ? ' selected' : '') + '>50</option>' +
      '</select>' +
      '<span>条</span>' +
      '</div>';

    container.innerHTML = html;
  }

  function goToPage(page) {
    var totalPages = Math.ceil(state.totalItems / state.pageSize) || 1;
    if (page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    state.currentPage = page;
    loadHosts();
  }

  function changePageSize(val) {
    state.pageSize = parseInt(val, 10);
    state.currentPage = 1;
    loadHosts();
    saveToLocalStorage();
  }

  // ── Detail Drawer ──
  function showDetail(nodeName) {
    var host = null;
    for (var i = 0; i < state.allHosts.length; i++) {
      if (state.allHosts[i].node_name === nodeName) { host = state.allHosts[i]; break; }
    }
    if (!host) {
      showToast('未找到主机: ' + nodeName, 'error');
      return;
    }

    var h = getEffectiveHost(host);
    var statusInfo = STATUS_MAP[h.status] || STATUS_MAP.running;
    var gpuLabel = (h.gpu_count || 0) > 0 ? ((h.gpu_type || 'GPU') + ' x' + h.gpu_count) : '无';

    var title = $('ch-drawer-title');
    if (title) title.textContent = h.node_name + ' - 主机详情';

    var body = $('ch-drawer-body');
    if (!body) return;

    var cpuPct = getCpuPercent(h);
    var memPct = getMemPercent(h);

    var fields = [
      { label: '主机名称', value: h.node_name },
      { label: '厂商', value: h.provider_type },
      { label: '所在区域', value: h.region },
      { label: 'IP地址', value: '<code>' + escapeHtml(h.ip_address) + '</code>' },
      { label: '操作系统', value: h.os || 'N/A' },
      { label: 'CPU', value: (h.cpu_cores != null ? h.cpu_cores : 'N/A') + ' 核' },
      { label: '内存', value: (h.memory_mb != null ? Math.round(h.memory_mb / 1024 * 10) / 10 : 'N/A') + ' GB' },
      { label: '磁盘', value: (h.disk_gb != null ? h.disk_gb : 'N/A') + ' GB' },
      { label: 'GPU', value: gpuLabel },
      { label: '运行状态', value: '<span class="' + statusInfo.cls + '">' + statusInfo.label + '</span>' },
      { label: 'CPU利用率', value: (cpuPct != null ? cpuPct + '%' : 'N/A'), progress: cpuPct },
      { label: '内存利用率', value: (memPct != null ? memPct + '%' : 'N/A'), progress: memPct }
    ];

    var html = '<div class="ch-detail-grid">';
    for (var f = 0; f < fields.length; f++) {
      var field = fields[f];
      html += '<div class="ch-detail-field">' +
        '<span class="ch-detail-label">' + field.label + '</span>';
      if (field.progress !== undefined && field.progress !== null) {
        var pct = field.progress;
        var barCls = pct > 80 ? ' ch-usage-danger' : (pct > 60 ? ' ch-usage-caution' : '');
        html += '<div class="ch-detail-value">' + field.value + '</div>' +
          '<div class="ch-usage-bar ch-detail-usage"><div class="ch-usage-fill' + barCls + '" style="width:' + pct + '%"></div></div>';
      } else if (field.progress === null) {
        // N/A case: no progress bar
        html += '<span class="ch-detail-value">' + field.value + '</span>';
      } else {
        html += '<span class="ch-detail-value">' + field.value + '</span>';
      }
      html += '</div>';
    }
    html += '</div>';

    // Action buttons
    html += '<div class="ch-detail-actions">';
    html += '<p class="ch-detail-action-hint">操作将触发真实API调用</p>';
    if (h.status === 'stopped') {
      html += '<button class="ch-action-btn ch-action-start" onclick="CloudHosts.performAction(\'' + escapeHtml(h.node_name) + '\', \'start\')">开机</button>';
    }
    if (h.status === 'running') {
      html += '<button class="ch-action-btn ch-action-stop" onclick="CloudHosts.performAction(\'' + escapeHtml(h.node_name) + '\', \'stop\')">关机</button>';
    }
    if (h.status === 'running' || h.status === 'stopped') {
      html += '<button class="ch-action-btn ch-action-restart" onclick="CloudHosts.performAction(\'' + escapeHtml(h.node_name) + '\', \'restart\')">重启</button>';
    }
    html += '<button class="ch-action-btn ch-action-maintenance" onclick="CloudHosts.performAction(\'' + escapeHtml(h.node_name) + '\', \'maintenance\')">维护</button>';
    html += '</div>';

    body.innerHTML = html;

    // Show drawer
    var drawer = $('ch-detail-drawer');
    var backdrop = $('ch-drawer-backdrop');
    if (drawer) drawer.classList.add('open');
    if (backdrop) backdrop.classList.add('show');
  }

  function closeDetailDrawer() {
    var drawer = $('ch-detail-drawer');
    var backdrop = $('ch-drawer-backdrop');
    if (drawer) drawer.classList.remove('open');
    if (backdrop) backdrop.classList.remove('show');
  }

  function performAction(nodeName, action) {
    var actionLabels = { start: '开机', stop: '关机', restart: '重启', maintenance: '进入维护' };
    if (!demoMode()) {
      showToast('未接入真实云主机操作 API，生产模式不允许模拟启停', 'warning');
      return;
    }

    if (!state.modifiedStates[nodeName]) state.modifiedStates[nodeName] = {};

    var host = null;
    for (var i = 0; i < state.allHosts.length; i++) {
      if (state.allHosts[i].node_name === nodeName) { host = state.allHosts[i]; break; }
    }

    switch (action) {
      case 'start':
        state.modifiedStates[nodeName].status = 'running';
        state.modifiedStates[nodeName].cpuUsage = 5 + Math.floor(Math.random() * 40);
        state.modifiedStates[nodeName].memUsage = 10 + Math.floor(Math.random() * 40);
        break;
      case 'stop':
        state.modifiedStates[nodeName].status = 'stopped';
        state.modifiedStates[nodeName].cpuUsage = 0;
        state.modifiedStates[nodeName].memUsage = 0;
        break;
      case 'restart':
        state.modifiedStates[nodeName].status = 'running';
        state.modifiedStates[nodeName].cpuUsage = host ? 10 + Math.floor(Math.random() * 30) : 15;
        state.modifiedStates[nodeName].memUsage = host ? 15 + Math.floor(Math.random() * 30) : 20;
        break;
      case 'maintenance':
        state.modifiedStates[nodeName].status = 'maintenance';
        state.modifiedStates[nodeName].cpuUsage = Math.floor(Math.random() * 20);
        state.modifiedStates[nodeName].memUsage = Math.floor(Math.random() * 15);
        break;
    }

    saveToLocalStorage();
    applyFiltersAndRender();
    renderSummary();

    // Refresh drawer if open
    var drawer = $('ch-detail-drawer');
    if (drawer && drawer.classList.contains('open')) {
      showDetail(nodeName);
    }

    showToast(actionLabels[action] + '：演示模式（模拟操作，已记录本地修改）', 'success');
  }

  // ── Init ──
  function init() {
    // Read scope from URL
    var params = new URLSearchParams(window.location.search);
    state.scope = params.get('scope') === 'private' ? 'private' : 'public';

    // Load localStorage
    loadFromLocalStorage();

    // Update page title and header
    var scopeLabel = state.scope === 'private' ? '私有云' : '公有云';
    var providerLabel = state.scope === 'private' ? 'VMware/通用REST' : '阿里云/腾讯云';

    document.title = scopeLabel + '主机列表 - AIGV Studio';

    var badge = $('ch-hero-badge');
    var title = $('ch-page-title');
    var desc = $('ch-page-desc');
    var chip = $('ch-summary-chip');
    var hostStatus = $('host-data-status');

    if (badge) badge.textContent = scopeLabel + ' · Cloud Hosts';
    if (title) title.textContent = scopeLabel + '主机列表';
    if (desc) desc.textContent = '统一管理' + providerLabel + '云主机资源，查看运行状态与资源使用情况';
    if (chip) chip.textContent = '数据来源：GET /api/cloud/hosts';
    if (hostStatus) hostStatus.textContent = '数据面板：' + scopeLabel + ' · Cloud Hosts';

    // Render filter bar first (empty state, then populated on load)
    renderFilterBar();

    // Bind search events
    var searchEl = $('ch-search-input');
    if (searchEl) {
      searchEl.addEventListener('input', handleSearchInput);
    }

    // Bind filter events
    bindFilterEvents();

    // Drawer close
    var closeBtn = $('ch-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', closeDetailDrawer);
    var backdrop = $('ch-drawer-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeDetailDrawer);
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeDetailDrawer();
    });

    // Load data from API
    loadHosts();
  }

  function bindFilterEvents() {
    var vendorEl = $('ch-filter-vendor');
    var regionEl = $('ch-filter-region');
    var statusEl = $('ch-filter-status');
    if (vendorEl) vendorEl.addEventListener('change', handleFilter);
    if (regionEl) regionEl.addEventListener('change', handleFilter);
    if (statusEl) statusEl.addEventListener('change', handleFilter);
  }

  // ── Expose public API ──
  window.CloudHosts = {
    init: init,
    showDetail: showDetail,
    closeDetailDrawer: closeDetailDrawer,
    handleSort: handleSort,
    goToPage: goToPage,
    changePageSize: changePageSize,
    performAction: performAction,
    handleSearchInput: handleSearchInput,
    handleFilter: handleFilter,
    showToast: showToast,
    $: $
  };

  document.addEventListener('DOMContentLoaded', init);
})();
