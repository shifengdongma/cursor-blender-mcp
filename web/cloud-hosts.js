/**
 * AIGV Studio Cloud Hosts Page
 * Vanilla JS implementation for public/private cloud host management
 * Scope: public (120 hosts) | private (100 hosts)
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

  // ── PRNG: mulberry32 ──
  function mulberry32(seed) {
    return function() {
      seed |= 0;
      seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // ── Status constants ──
  var STATUS_MAP = {
    running: { label: '运行中', cls: 'ch-badge-running' },
    stopped: { label: '已关机', cls: 'ch-badge-stopped' },
    error: { label: '异常', cls: 'ch-badge-error' },
    maintenance: { label: '维护中', cls: 'ch-badge-maintenance' }
  };

  // ── Generation configs ──
  var PUBLIC_CONFIG = {
    scope: 'public',
    count: 120,
    seed: 20260715,
    vendors: [
      { name: '阿里云', prefix: 'ecs-ali' },
      { name: '腾讯云', prefix: 'cvm-tx' },
      { name: 'AWS', prefix: 'ec2-aws' },
      { name: 'Azure', prefix: 'vm-az' }
    ],
    regions: ['华东1', '华东2', '华北1', '华北2', '华南1', '西南1', '新加坡', '美东1'],
    ipPrefix: 10
  };

  var PRIVATE_CONFIG = {
    scope: 'private',
    count: 100,
    seed: 20260716,
    vendors: [
      { name: '武汉超算中心', prefix: 'wh-hpc' },
      { name: '武汉光谷节点', prefix: 'wh-ggj' },
      { name: '武汉临空港', prefix: 'wh-lkg' },
      { name: '武汉东湖', prefix: 'wh-dh' },
      { name: '武汉经开区', prefix: 'wh-jkq' }
    ],
    regions: ['武汉-超算中心', '武汉-光谷节点', '武汉-临空港', '武汉-东湖', '武汉-经开区'],
    ipPrefix: '172.16'
  };

  var CPU_OPTIONS = [8, 16, 32, 64, 128];
  var DISK_OPTIONS = [500, 1000, 2000, 4000, 8000];
  var USED_IPS = {};

  function pickRandom(arr, rng) {
    return arr[Math.floor(rng() * arr.length)];
  }

  function weightedPick(rng) {
    var v = rng();
    if (v < 0.75) return 'running';
    if (v < 0.85) return 'stopped';
    if (v < 0.93) return 'error';
    return 'maintenance';
  }

  function generateIp(prefix, rng) {
    var ip;
    var attempts = 0;
    while (attempts < 2000) {
      if (typeof prefix === 'number') {
        var b1 = Math.floor(rng() * 256);
        var b2 = Math.floor(rng() * 256);
        var b3 = Math.floor(rng() * 256);
        var b4 = Math.floor(rng() * 50) + 1;
        ip = prefix + '.' + b1 + '.' + b2 + '.' + b3;
        // Keep public IPs in 10.x.x.x range for visual consistency
        if (b1 > 200) b1 = b1 % 200;
        if (b2 > 200) b2 = b2 % 200;
        if (b3 > 200) b3 = b3 % 200;
        ip = prefix + '.' + b1 + '.' + b2 + '.' + b3;
      } else {
        var p3 = Math.floor(rng() * 50) + 1;
        var p4 = Math.floor(rng() * 250) + 1;
        ip = prefix + '.' + p3 + '.' + p4;
      }
      if (!USED_IPS[ip]) {
        USED_IPS[ip] = true;
        return ip;
      }
      attempts++;
    }
    return ip; // fallback
  }

  function generateHost(index, config, rng) {
    var vendor = config.vendors[index % config.vendors.length];
    var region = config.regions[index % config.regions.length];
    var cpu = pickRandom(CPU_OPTIONS, rng);
    var memMultiplier = [2, 4, 8][Math.floor(rng() * 3)];
    var memory = cpu * memMultiplier;
    var disk = pickRandom(DISK_OPTIONS, rng);
    var gpuCount = [0, 1, 2, 4, 8][Math.floor(rng() * 5)];
    var gpuType = gpuCount > 0 ? pickRandom(['NVIDIA A100', 'NVIDIA V100', 'NVIDIA T4', 'NVIDIA A10', 'NVIDIA H800'], rng) : '-';
    var status = weightedPick(rng);
    var cpuUsage = status === 'running' ? Math.floor(rng() * 80) + 5 : (status === 'maintenance' ? Math.floor(rng() * 30) : 0);
    var memUsage = status === 'running' ? Math.floor(rng() * 75) + 10 : (status === 'maintenance' ? Math.floor(rng() * 25) : 0);

    var hostId = config.scope + '-' + (index + 1).toString().padStart(3, '0');
    var ip = generateIp(config.ipPrefix, rng);
    var name = vendor.prefix + '-' + (index + 1).toString().padStart(3, '0');

    return {
      id: hostId,
      name: name,
      vendor: vendor.name,
      region: region,
      ip: ip,
      cpu: cpu,
      memory: memory,
      disk: disk,
      gpuCount: gpuCount,
      gpuType: gpuType,
      status: status,
      cpuUsage: cpuUsage,
      memUsage: memUsage,
      os: pickRandom(['CentOS 7.9', 'Ubuntu 22.04', 'RHEL 8.6', 'Debian 11', 'Rocky Linux 9'], rng),
      uptime: status === 'running' ? Math.floor(rng() * 365) + '天' : '-'
    };
  }

  function generateAllHosts(scope) {
    USED_IPS = {};
    var config = scope === 'private' ? PRIVATE_CONFIG : PUBLIC_CONFIG;
    var rng = mulberry32(config.seed);
    var hosts = [];
    for (var i = 0; i < config.count; i++) {
      hosts.push(generateHost(i, config, rng));
    }
    return hosts;
  }

  // ── State management ──
  var state = {
    scope: 'public',
    allHosts: [],
    filteredHosts: [],
    searchQuery: '',
    filters: { vendor: 'all', region: 'all', status: 'all' },
    sortField: 'name',
    sortAsc: true,
    currentPage: 1,
    pageSize: 20,
    modifiedStates: {} // key: hostId -> { status, cpuUsage, memUsage }
  };

  var LS_KEY = 'aigv_cloud_hosts_v1';

  function saveToLocalStorage() {
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
    var mod = state.modifiedStates[host.id];
    if (mod) {
      var h = {};
      for (var k in host) h[k] = host[k];
      if (mod.status !== undefined) h.status = mod.status;
      if (mod.cpuUsage !== undefined) h.cpuUsage = mod.cpuUsage;
      if (mod.memUsage !== undefined) h.memUsage = mod.memUsage;
      if (mod.status === 'stopped') { h.cpuUsage = 0; h.memUsage = 0; h.uptime = '-'; }
      return h;
    }
    return host;
  }

  function getScopeConfig() {
    return state.scope === 'private' ? PRIVATE_CONFIG : PUBLIC_CONFIG;
  }

  // ── Render functions ──
  function renderSummary() {
    var hosts = state.allHosts;
    var running = 0, stopped = 0, error = 0, maintenance = 0;
    var totalCpu = 0, totalMem = 0;

    for (var i = 0; i < hosts.length; i++) {
      var h = getEffectiveHost(hosts[i]);
      switch (h.status) {
        case 'running': running++; totalCpu += h.cpu; totalMem += h.memory; break;
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
      { label: '总内存', value: totalMem, unit: 'GB', accent: 'gold' }
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
      vendorSet[hosts[i].vendor] = true;
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
      applyFiltersAndRender();
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
    applyFiltersAndRender();
  }

  function applyFiltersAndRender() {
    var hosts = state.allHosts;
    var filtered = [];

    for (var i = 0; i < hosts.length; i++) {
      var h = getEffectiveHost(hosts[i]);
      if (state.filters.vendor !== 'all' && h.vendor !== state.filters.vendor) continue;
      if (state.filters.region !== 'all' && h.region !== state.filters.region) continue;
      if (state.filters.status !== 'all' && h.status !== state.filters.status) continue;
      if (state.searchQuery) {
        var lq = state.searchQuery;
        if (h.name.toLowerCase().indexOf(lq) === -1 && h.ip.toLowerCase().indexOf(lq) === -1) continue;
      }
      filtered.push(h);
    }

    // Sort
    var sf = state.sortField;
    var asc = state.sortAsc;
    filtered.sort(function(a, b) {
      var va = a[sf], vb = b[sf];
      if (typeof va === 'number' && typeof vb === 'number') return asc ? va - vb : vb - va;
      va = String(va || '').toLowerCase();
      vb = String(vb || '').toLowerCase();
      if (asc) return va < vb ? -1 : va > vb ? 1 : 0;
      return va > vb ? -1 : va < vb ? 1 : 0;
    });

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
    applyFiltersAndRender();

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

    // Sort arrow helpers
    function sortArrow(field) {
      if (state.sortField !== field) return '';
      return '<span class="ch-sort-arrow" data-field="' + field + '">' + (state.sortAsc ? ' \u25B2' : ' \u25BC') + '</span>';
    }

    var html = '<table class="cp-table ch-host-table">' +
      '<thead><tr>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'name\')">名称' + sortArrow('name') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'vendor\')">厂商' + sortArrow('vendor') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'region\')">区域' + sortArrow('region') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'ip\')">IP地址' + sortArrow('ip') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'cpu\')">CPU（核）' + sortArrow('cpu') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'memory\')">内存（GB）' + sortArrow('memory') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'gpuCount\')">GPU' + sortArrow('gpuCount') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'status\')">状态' + sortArrow('status') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'cpuUsage\')">CPU利用率' + sortArrow('cpuUsage') + '</th>' +
      '<th class="ch-sortable" onclick="CloudHosts.handleSort(\'memUsage\')">内存利用率' + sortArrow('memUsage') + '</th>' +
      '<th>操作</th>' +
      '</tr></thead><tbody>';

    if (pageData.length === 0) {
      html += '<tr><td colspan="11" style="text-align:center;padding:40px;color:var(--text-muted)">没有匹配的主机数据</td></tr>';
    } else {
      for (var i = 0; i < pageData.length; i++) {
        var h = pageData[i];
        var statusInfo = STATUS_MAP[h.status] || STATUS_MAP.running;
        var gpuLabel = h.gpuCount > 0 ? (h.gpuType + ' x' + h.gpuCount) : '-';
        html += '<tr>' +
          '<td><span class="ch-host-name-link" onclick="CloudHosts.showDetail(\'' + h.id + '\')">' + escapeHtml(h.name) + '</span></td>' +
          '<td>' + escapeHtml(h.vendor) + '</td>' +
          '<td>' + escapeHtml(h.region) + '</td>' +
          '<td class="ch-cell-mono">' + escapeHtml(h.ip) + '</td>' +
          '<td>' + h.cpu + '</td>' +
          '<td>' + h.memory + '</td>' +
          '<td>' + escapeHtml(gpuLabel) + '</td>' +
          '<td><span class="' + statusInfo.cls + '">' + statusInfo.label + '</span></td>' +
          '<td>' + renderUsageBar(h.cpuUsage) + '</td>' +
          '<td>' + renderUsageBar(h.memUsage) + '</td>' +
          '<td><button class="ch-action-btn" onclick="CloudHosts.showDetail(\'' + h.id + '\')">详情</button></td>' +
          '</tr>';
      }
    }

    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function renderUsageBar(pct) {
    var cls = pct > 80 ? ' ch-usage-danger' : (pct > 60 ? ' ch-usage-caution' : '');
    return '<div class="ch-usage-bar"><div class="ch-usage-fill' + cls + '" style="width:' + pct + '%"></div><span class="ch-usage-text">' + pct + '%</span></div>';
  }

  function renderPagination() {
    var container = $('ch-pagination');
    if (!container) return;

    var totalItems = state.filteredHosts.length;
    var pageSize = state.pageSize;
    var totalPages = Math.ceil(totalItems / pageSize) || 1;
    var current = state.currentPage;
    if (current > totalPages) current = totalPages;
    if (current < 1) current = 1;

    var start = (current - 1) * pageSize + 1;
    var end = Math.min(current * pageSize, totalItems);

    var html = '<div class="ch-pagination-info">显示 ' + start + '-' + end + '，共 ' + totalItems + ' 台</div>';
    html += '<div class="ch-pagination-controls">';
    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(1)"' + (current <= 1 ? ' disabled' : '') + '>首页</button>';
    html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + (current - 1) + ')"' + (current <= 1 ? ' disabled' : '') + '>上一页</button>';

    // Page numbers
    var pageStart = Math.max(1, current - 2);
    var pageEnd = Math.min(totalPages, current + 2);
    if (pageStart > 1) {
      html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(1)">1</button>';
      if (pageStart > 2) html += '<span class="ch-page-ellipsis">...</span>';
    }
    for (var p = pageStart; p <= pageEnd; p++) {
      html += '<button class="ch-page-btn' + (p === current ? ' active' : '') + '" onclick="CloudHosts.goToPage(' + p + ')">' + p + '</button>';
    }
    if (pageEnd < totalPages) {
      if (pageEnd < totalPages - 1) html += '<span class="ch-page-ellipsis">...</span>';
      html += '<button class="ch-page-btn" onclick="CloudHosts.goToPage(' + totalPages + ')">' + totalPages + '</button>';
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
    var totalPages = Math.ceil(state.filteredHosts.length / state.pageSize) || 1;
    if (page < 1) page = 1;
    if (page > totalPages) page = totalPages;
    state.currentPage = page;
    renderTable();
    renderPagination();
  }

  function changePageSize(val) {
    state.pageSize = parseInt(val, 10);
    state.currentPage = 1;
    applyFiltersAndRender();
    saveToLocalStorage();
  }

  // ── Detail Drawer ──
  function showDetail(hostId) {
    var host = null;
    for (var i = 0; i < state.allHosts.length; i++) {
      if (state.allHosts[i].id === hostId) { host = state.allHosts[i]; break; }
    }
    if (!host) return;

    var h = getEffectiveHost(host);
    var statusInfo = STATUS_MAP[h.status] || STATUS_MAP.running;

    var title = $('ch-drawer-title');
    if (title) title.textContent = h.name + ' - 主机详情';

    var body = $('ch-drawer-body');
    if (!body) return;

    var fields = [
      { label: '主机名称', value: h.name },
      { label: '主机ID', value: h.id },
      { label: '云厂商', value: h.vendor },
      { label: '所在区域', value: h.region },
      { label: 'IP地址', value: '<code>' + escapeHtml(h.ip) + '</code>' },
      { label: '操作系统', value: h.os },
      { label: 'CPU', value: h.cpu + ' 核' },
      { label: '内存', value: h.memory + ' GB' },
      { label: '磁盘', value: h.disk + ' GB' },
      { label: 'GPU', value: h.gpuCount > 0 ? (h.gpuType + ' x' + h.gpuCount) : '无' },
      { label: '运行状态', value: '<span class="' + statusInfo.cls + '">' + statusInfo.label + '</span>' },
      { label: 'CPU利用率', value: (h.cpuUsage || 0) + '%', progress: h.cpuUsage || 0 },
      { label: '内存利用率', value: (h.memUsage || 0) + '%', progress: h.memUsage || 0 }
    ];

    var html = '<div class="ch-detail-grid">';
    for (var f = 0; f < fields.length; f++) {
      var field = fields[f];
      html += '<div class="ch-detail-field">' +
        '<span class="ch-detail-label">' + field.label + '</span>';
      if (field.progress !== undefined) {
        var pct = field.progress;
        var barCls = pct > 80 ? ' ch-usage-danger' : (pct > 60 ? ' ch-usage-caution' : '');
        html += '<div class="ch-detail-value">' + field.value + '</div>' +
          '<div class="ch-usage-bar ch-detail-usage"><div class="ch-usage-fill' + barCls + '" style="width:' + pct + '%"></div></div>';
      } else {
        html += '<span class="ch-detail-value">' + field.value + '</span>';
      }
      html += '</div>';
    }
    html += '</div>';

    // Action buttons
    html += '<div class="ch-detail-actions">';
    html += '<p class="ch-detail-action-hint">模拟操作（演示模式，未调用真实云平台）</p>';
    if (h.status === 'stopped') {
      html += '<button class="ch-action-btn ch-action-start" onclick="CloudHosts.performAction(\'' + host.id + '\', \'start\')">开机</button>';
    }
    if (h.status === 'running') {
      html += '<button class="ch-action-btn ch-action-stop" onclick="CloudHosts.performAction(\'' + host.id + '\', \'stop\')">关机</button>';
    }
    if (h.status === 'running' || h.status === 'stopped') {
      html += '<button class="ch-action-btn ch-action-restart" onclick="CloudHosts.performAction(\'' + host.id + '\', \'restart\')">重启</button>';
    }
    html += '<button class="ch-action-btn ch-action-maintenance" onclick="CloudHosts.performAction(\'' + host.id + '\', \'maintenance\')">维护</button>';
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

  function performAction(hostId, action) {
    var actionLabels = { start: '开机', stop: '关机', restart: '重启', maintenance: '进入维护' };

    if (!state.modifiedStates[hostId]) state.modifiedStates[hostId] = {};

    var host = null;
    for (var i = 0; i < state.allHosts.length; i++) {
      if (state.allHosts[i].id === hostId) { host = state.allHosts[i]; break; }
    }

    switch (action) {
      case 'start':
        state.modifiedStates[hostId].status = 'running';
        state.modifiedStates[hostId].cpuUsage = 5 + Math.floor(Math.random() * 40);
        state.modifiedStates[hostId].memUsage = 10 + Math.floor(Math.random() * 40);
        break;
      case 'stop':
        state.modifiedStates[hostId].status = 'stopped';
        state.modifiedStates[hostId].cpuUsage = 0;
        state.modifiedStates[hostId].memUsage = 0;
        break;
      case 'restart':
        state.modifiedStates[hostId].status = 'running';
        state.modifiedStates[hostId].cpuUsage = host ? 10 + Math.floor(Math.random() * 30) : 15;
        state.modifiedStates[hostId].memUsage = host ? 15 + Math.floor(Math.random() * 30) : 20;
        break;
      case 'maintenance':
        state.modifiedStates[hostId].status = 'maintenance';
        state.modifiedStates[hostId].cpuUsage = Math.floor(Math.random() * 20);
        state.modifiedStates[hostId].memUsage = Math.floor(Math.random() * 15);
        break;
    }

    saveToLocalStorage();
    applyFiltersAndRender();
    renderSummary();

    // Refresh drawer if open
    var drawer = $('ch-detail-drawer');
    if (drawer && drawer.classList.contains('open')) {
      showDetail(hostId);
    }

    showToast(actionLabels[action] + '：演示操作已完成，未调用真实云平台', 'success');
  }

  // ── Init ──
  function init() {
    // Read scope from URL
    var params = new URLSearchParams(window.location.search);
    state.scope = params.get('scope') === 'private' ? 'private' : 'public';

    // Generate all hosts
    state.allHosts = generateAllHosts(state.scope);

    // Load localStorage
    loadFromLocalStorage();

    // Update page title and header
    var config = getScopeConfig();
    var scopeLabel = state.scope === 'private' ? '私有云' : '公有云';

    document.title = scopeLabel + '主机列表 - AIGV Studio';

    var badge = $('ch-hero-badge');
    var title = $('ch-page-title');
    var desc = $('ch-page-desc');
    var chip = $('ch-summary-chip');
    var hostStatus = $('host-data-status');

    if (badge) badge.textContent = scopeLabel + ' · ' + config.count + ' Hosts';
    if (title) title.textContent = scopeLabel + '主机列表';
    if (desc) desc.textContent = '统一管理' + (scopeLabel === '公有云' ? '阿里云/腾讯云/AWS/Azure' : '武汉五大区域') + '云主机资源，查看运行状态与资源使用情况';
    if (chip) chip.textContent = '共计 ' + config.count + ' 台主机';
    if (hostStatus) hostStatus.textContent = '数据面板：' + scopeLabel + ' · ' + config.count + ' 台主机';

    // Render all sections
    renderSummary();

    // Set initial sort asc
    state.sortAsc = true;
    state.sortField = 'name';
    applyFiltersAndRender();

    // Render filter bar (has its own HTML)
    renderFilterBar();

    // Bind events
    var searchEl = $('ch-search-input');
    if (searchEl) {
      searchEl.addEventListener('input', handleSearchInput);
    }

    var vendorEl = $('ch-filter-vendor');
    var regionEl = $('ch-filter-region');
    var statusEl = $('ch-filter-status');
    if (vendorEl) vendorEl.addEventListener('change', handleFilter);
    if (regionEl) regionEl.addEventListener('change', handleFilter);
    if (statusEl) statusEl.addEventListener('change', handleFilter);

    // Drawer close
    var closeBtn = $('ch-drawer-close');
    if (closeBtn) closeBtn.addEventListener('click', closeDetailDrawer);
    var backdrop = $('ch-drawer-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeDetailDrawer);
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') closeDetailDrawer();
    });

    showToast(scopeLabel + '主机列表加载完成（' + config.count + ' 台）', 'success');
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
