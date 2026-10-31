/*
 * AI model service / Volcengine Ark usage tab for the compute platform.
 * All official data is read from admin-only, cached server snapshots; this
 * module never triggers an upstream sync unless the admin clicks the button.
 */
(function (global) {
  'use strict';

  var state = {
    isAdmin: false,
    bound: false,
    loading: false,
    days: 7,
    data: null,
    message: '',
    messageKind: ''
  };

  function $(id) { return document.getElementById(id); }

  function esc(value) {
    if (global.AIGV && global.AIGV.escapeHtml) return global.AIGV.escapeHtml(value);
    return String(value === null || value === undefined ? '' : value)
      .replace(/[&<>"']/g, function (ch) {
        return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[ch];
      });
  }

  function num(value) {
    if (value === null || value === undefined || value === '') return '—';
    var parsed = Number(value);
    if (isNaN(parsed)) return esc(value);
    return parsed.toLocaleString('zh-CN');
  }

  function duration(ms) {
    if (ms === null || ms === undefined) return '—';
    var value = Number(ms);
    if (isNaN(value)) return '—';
    if (value < 1000) return Math.round(value) + ' ms';
    return (value / 1000).toFixed(1) + ' s';
  }

  function timeLabel(ts) {
    return global.AIGV && global.AIGV.formatTime ? global.AIGV.formatTime(ts) : (ts || '—');
  }

  function taskTypeLabel(type) {
    return ({
      image: '图片生成', video: '视频生成', storyboard: '创意分析',
      tts: 'TTS 配音', compose: '视频合成', refine: '视频精修', export: '视频导出'
    })[type] || (type || '—');
  }

  function statusLabel(status) {
    return ({
      queued: '排队中', submitting: '提交中', running: '运行中',
      succeeded: '成功', failed: '失败', cancelled: '已取消',
      needs_review: '待确认'
    })[status] || (status || '—');
  }

  function sourceLabel(source) {
    return ({
      response: 'Provider 响应', response_poll: 'Provider 轮询',
      response_llm: 'LLM 响应', response_submit: '提交响应',
      official_api: '官方 TaskUsage', local: '本地记录'
    })[source] || (source || '—');
  }

  function statusBadge(status) {
    var cls = 'cp-badge info';
    if (status === 'succeeded') cls = 'cp-badge online';
    else if (status === 'failed') cls = 'cp-badge error';
    else if (status === 'running' || status === 'submitting') cls = 'cp-badge good';
    else if (status === 'queued') cls = 'cp-badge warning';
    else if (status === 'cancelled') cls = 'cp-badge paused';
    return '<span class="' + cls + '">' + esc(statusLabel(status)) + '</span>';
  }

  function maskKey(value) {
    if (!value) return '—';
    var text = String(value);
    if (text.length <= 6) return '••••' + text;
    return '••••' + text.slice(-6);
  }

  function setNotice(text, kind) {
    state.message = text || '';
    state.messageKind = kind || '';
    var container = $('ark-usage-notice');
    if (!container) return;
    container.textContent = text || '';
    container.className = 'cp-source-note' + (kind ? ' ' + kind : '');
  }

  function card(label, value, hint) {
    return '<div class="cp-metric-card">' +
      '<div class="cp-metric-label">' + esc(label) + '</div>' +
      '<div class="cp-metric-value">' + value + '</div>' +
      '<div class="cp-metric-hint">' + esc(hint || '') + '</div>' +
      '</div>';
  }

  function costCard(label, value, hint) {
    return '<div class="cp-cost-card">' +
      '<div class="cp-cost-label">' + esc(label) + '</div>' +
      '<div class="cp-cost-value">' + value + '</div>' +
      '<div class="cp-cost-hint">' + esc(hint || '') + '</div>' +
      '</div>';
  }

  function isAdminNow() {
    return !!state.isAdmin;
  }

  function init() {
    if (state.bound) return;
    state.bound = true;
    if (!global.AIGV || !global.AIGV.getCurrentUser) return;
    global.AIGV.getCurrentUser().then(function (user) {
      state.isAdmin = !!(user && user.capabilities && user.capabilities.is_admin);
      var button = $('cp-ai-tab-btn');
      if (button) button.style.display = state.isAdmin ? '' : 'none';
      var panel = $('tab-ai-models');
      if (panel && !state.isAdmin) panel.classList.remove('active');
    }).catch(function () {
      state.isAdmin = false;
    });

    var days = $('ark-usage-days');
    if (days) {
      days.addEventListener('change', function () {
        state.days = parseInt(days.value, 10) || 7;
        load(true);
      });
    }
    var refresh = $('ark-usage-refresh');
    if (refresh) refresh.addEventListener('click', function () { load(true); });
    var sync = $('ark-usage-sync');
    if (sync) sync.addEventListener('click', syncOfficialUsage);
  }

  function activate() {
    if (!state.isAdmin) {
      setNotice('仅平台管理员可查看 AI 模型服务与火山引擎官方用量。', 'warning');
      return;
    }
    load(false);
  }

  function load(force) {
    if (!state.isAdmin) return Promise.resolve();
    if (state.loading) return Promise.resolve();
    if (state.data && !force) {
      render();
      return Promise.resolve();
    }
    state.loading = true;
    var refresh = $('ark-usage-refresh');
    if (refresh) refresh.disabled = true;
    setNotice('正在读取本地任务与官方用量快照…', 'loading');
    var days = state.days;
    return Promise.all([
      global.AIGV.api('/api/admin/ark/usage/summary?days=' + days),
      global.AIGV.api('/api/admin/ark/usage/models?days=' + days),
      global.AIGV.api('/api/admin/ark/usage/trend?days=' + days),
      global.AIGV.api('/api/admin/ark/usage/tasks?days=' + days + '&limit=20'),
      global.AIGV.api('/api/admin/ark/status')
    ]).then(function (results) {
      state.data = {
        summary: results[0], models: results[1], trend: results[2],
        tasks: results[3], status: results[4]
      };
      render();
    }).catch(function (error) {
      setNotice('AI 模型服务数据加载失败：' + (error.message || '未知错误'), 'error');
    }).then(function () {
      state.loading = false;
      if (refresh) refresh.disabled = false;
    });
  }

  function render() {
    if (!state.data) return;
    var data = state.data;
    var local = (data.summary && data.summary.local) || {};
    var official = (data.summary && data.summary.official) || {};
    var status = data.status || {};
    var sync = (status.sync || {}).ark_usage || {};

    var notes = [];
    if (!status.has_credentials) {
      notes.push('未配置火山引擎管理 AK/SK：官方用量不可用，现有图片/视频/LLM 生成不受影响。');
    }
    if (!status.usage_enabled) {
      notes.push('火山方舟官方用量未启用（VOLCENGINE_USAGE_ENABLED=false）。');
    }
    if (official.has_data === false) {
      notes.push('当前时间范围暂无官方用量数据；本地任务数据仍正常显示。');
    }
    if (official.dimension_filters_supported === false) {
      notes.push('官方接口未接受 API Key/模型维度过滤，当前为账号级汇总。');
    }
    var noteText = notes.length
      ? notes.join(' ')
      : '官方用量为火山引擎账号级只读快照，可能包含同一账号下的其他应用调用；本地任务数与官方计费请求数不等同。';
    setNotice(noteText, notes.length ? 'warning' : '');

    renderLocalMetrics(local, status);
    renderOfficialMetrics(official, sync, status);
    renderModels(data.models || {});
    renderTrend(data.trend || {});
    renderPerformance(local);
    renderTasks((data.tasks && data.tasks.items) || []);
  }

  function renderLocalMetrics(local, status) {
    var container = $('ark-local-metrics');
    if (!container) return;
    var html = '';
    html += card('模型调用次数', num(local.model_calls), '图片 + 视频 + 创意分析');
    html += card('图片生成任务', num(local.images), 'AIGV 本地任务');
    html += card('视频生成任务', num(local.videos), 'AIGV 本地任务');
    html += card('运行中', num(local.running), '排队/提交/生成中');
    html += card('成功', num(local.succeeded), '本地终态任务');
    html += card('失败', num(local.failed), '本地终态任务');
    html += card('成功率', local.success_rate === null || local.success_rate === undefined ? '—' : local.success_rate + '%', '成功 / 终态任务');
    html += card('平均完成耗时', duration(local.avg_duration_ms), '本地计时字段');
    container.innerHTML = html;
  }

  function renderOfficialMetrics(official, sync, status) {
    var container = $('ark-official-metrics');
    if (!container) return;
    var syncText = sync.status === 'success' ? '已同步' : (sync.status || '未同步');
    if (sync.last_error_message) syncText += ' · ' + sync.last_error_message;
    var html = '';
    html += costCard('官方请求数', num(official.req_cnt), '火山引擎官方用量（账号级）');
    html += costCard('输入 Token', num(official.input_tokens), '仅官方实际返回时展示');
    html += costCard('输出 Token', num(official.output_tokens), '图片模型 Token 为参考值');
    html += costCard('总 Token', num(official.total_tokens), '不与图片张数相加');
    html += costCard('图片数', num(official.image_count), '官方 ImageCount');
    html += costCard('最近同步', timeLabel(sync.last_success_at), syncText);
    container.innerHTML = html;
    var syncButton = $('ark-usage-sync');
    if (syncButton) {
      syncButton.disabled = !status.usage_enabled || !status.has_credentials;
      syncButton.textContent = status.usage_enabled && status.has_credentials
        ? '同步官方用量' : '官方用量未启用';
    }
  }

  function renderModels(models) {
    var localContainer = $('ark-local-model-table');
    if (localContainer) {
      var localItems = (models.local && models.local.items) || [];
      if (!localItems.length) {
        localContainer.innerHTML = '<p class="empty-state">暂无本地模型调用记录。</p>';
      } else {
        var localHtml = '<table class="cp-table"><thead><tr>' +
          '<th>模型</th><th>Provider</th><th>任务数</th><th>成功</th><th>失败</th>' +
          '<th>输入 Token</th><th>输出 Token</th><th>总 Token</th><th>图片数</th>' +
          '</tr></thead><tbody>';
        localItems.forEach(function (item) {
          localHtml += '<tr>' +
            '<td>' + esc(item.model_id || '未标注模型') + '</td>' +
            '<td>' + esc(item.provider || '—') + '</td>' +
            '<td>' + num(item.task_count) + '</td>' +
            '<td>' + num(item.succeeded) + '</td>' +
            '<td>' + num(item.failed) + '</td>' +
            '<td>' + num(item.input_tokens) + '</td>' +
            '<td>' + num(item.output_tokens) + '</td>' +
            '<td>' + num(item.total_tokens) + '</td>' +
            '<td>' + num(item.image_count) + '</td>' +
            '</tr>';
        });
        localHtml += '</tbody></table>';
        localContainer.innerHTML = localHtml;
      }
    }

    var officialContainer = $('ark-official-model-table');
    if (officialContainer) {
      var officialItems = (models.official && models.official.items) || [];
      if (!officialItems.length) {
        officialContainer.innerHTML = '<p class="empty-state">暂无官方模型用量数据。</p>';
      } else {
        var officialHtml = '<table class="cp-table"><thead><tr>' +
          '<th>官方模型</th><th>API Key 资源 ID</th><th>请求数</th>' +
          '<th>输入 Token</th><th>输出 Token</th><th>总 Token</th><th>图片数</th>' +
          '</tr></thead><tbody>';
        officialItems.forEach(function (item) {
          officialHtml += '<tr>' +
            '<td>' + esc(item.model_name || '未标注模型') + '</td>' +
            '<td>' + esc(maskKey(item.api_key_id)) + '</td>' +
            '<td>' + num(item.req_cnt) + '</td>' +
            '<td>' + num(item.input_tokens) + '</td>' +
            '<td>' + num(item.output_tokens) + '</td>' +
            '<td>' + num(item.total_tokens) + '</td>' +
            '<td>' + num(item.image_count) + '</td>' +
            '</tr>';
        });
        officialHtml += '</tbody></table>';
        officialContainer.innerHTML = officialHtml;
      }
    }
  }

  function trendMap(trends) {
    var map = {};
    var localItems = (trends.local && trends.local.items) || [];
    var officialItems = (trends.official && trends.official.items) || [];
    localItems.forEach(function (item) {
      var key = item.period_label;
      if (!key) return;
      map[key] = map[key] || { label: key, local: 0, official: 0 };
      map[key].local += Number(item.tasks || 0);
    });
    officialItems.forEach(function (item) {
      var key = item.period_label;
      if (!key) return;
      map[key] = map[key] || { label: key, local: 0, official: 0 };
      map[key].official += Number(item.req_cnt || 0);
    });
    return Object.keys(map).sort().map(function (key) { return map[key]; });
  }

  function renderTrend(trends) {
    var container = $('ark-trend-chart');
    if (!container) return;
    var items = trendMap(trends);
    if (!items.length) {
      container.innerHTML = '<p class="empty-state">暂无数据，不使用演示曲线。</p>';
      return;
    }
    var width = 760;
    var height = 240;
    var left = 44;
    var right = 16;
    var top = 20;
    var bottom = 42;
    var chartWidth = width - left - right;
    var chartHeight = height - top - bottom;
    var maxValue = 1;
    items.forEach(function (item) {
      maxValue = Math.max(maxValue, item.local, item.official);
    });
    var groupWidth = chartWidth / items.length;
    var barWidth = Math.max(3, Math.min(16, groupWidth / 3));
    var svg = '<svg class="ark-trend-svg" viewBox="0 0 ' + width + ' ' + height + '" role="img" aria-label="本地任务与官方请求趋势">';
    for (var i = 0; i <= 4; i++) {
      var y = top + (chartHeight / 4) * i;
      var value = Math.round(maxValue - (maxValue / 4) * i);
      svg += '<line x1="' + left + '" y1="' + y + '" x2="' + (width - right) + '" y2="' + y + '" class="ark-grid-line"/>';
      svg += '<text x="' + (left - 8) + '" y="' + (y + 4) + '" text-anchor="end" class="ark-axis-text">' + value + '</text>';
    }
    items.forEach(function (item, index) {
      var center = left + groupWidth * index + groupWidth / 2;
      var localHeight = item.local / maxValue * chartHeight;
      var officialHeight = item.official / maxValue * chartHeight;
      svg += '<rect x="' + (center - barWidth - 2) + '" y="' + (top + chartHeight - localHeight) +
        '" width="' + barWidth + '" height="' + localHeight + '" class="ark-bar-local"><title>' +
        esc(item.label) + ' 本地任务 ' + item.local + '</title></rect>';
      svg += '<rect x="' + (center + 2) + '" y="' + (top + chartHeight - officialHeight) +
        '" width="' + barWidth + '" height="' + officialHeight + '" class="ark-bar-official"><title>' +
        esc(item.label) + ' 官方请求 ' + item.official + '</title></rect>';
      if (items.length <= 10 || index % Math.ceil(items.length / 7) === 0) {
        svg += '<text x="' + center + '" y="' + (height - 18) + '" text-anchor="middle" class="ark-axis-text">' +
          esc(String(item.label).slice(5)) + '</text>';
      }
    });
    svg += '</svg>';
    svg += '<div class="ark-legend">' +
      '<span><i class="ark-legend-swatch local"></i>本地任务数</span>' +
      '<span><i class="ark-legend-swatch official"></i>官方请求数</span>' +
      '</div>';
    container.innerHTML = svg;
  }

  function renderPerformance(local) {
    var container = $('ark-task-performance');
    if (!container) return;
    var html = '<table class="cp-table"><thead><tr>' +
      '<th>指标</th><th>平均值</th><th>来源</th>' +
      '</tr></thead><tbody>' +
      '<tr><td>平均排队时间</td><td>' + duration(local.avg_queue_ms) + '</td><td>AIGV 本地计时</td></tr>' +
      '<tr><td>平均 Provider 运行时间</td><td>' + duration(local.avg_provider_ms) + '</td><td>AIGV 本地计时（含服务商排队）</td></tr>' +
      '<tr><td>平均下载时间</td><td>' + duration(local.avg_download_ms) + '</td><td>AIGV 本地计时</td></tr>' +
      '<tr><td>平均完成时间</td><td>' + duration(local.avg_duration_ms) + '</td><td>AIGV 本地计时</td></tr>' +
      '<tr><td>任务成功率</td><td>' + (local.success_rate === null || local.success_rate === undefined ? '—' : local.success_rate + '%') + '</td><td>AIGV 本地任务</td></tr>' +
      '</tbody></table>';
    container.innerHTML = html;
  }

  function renderTasks(items) {
    var container = $('ark-task-table');
    if (!container) return;
    if (!items.length) {
      container.innerHTML = '<p class="empty-state">暂无本地任务记录。</p>';
      return;
    }
    var html = '<table class="cp-table"><thead><tr>' +
      '<th>时间</th><th>类型</th><th>状态</th><th>模型</th><th>创建人</th>' +
      '<th>总耗时</th><th>用量来源</th>' +
      '</tr></thead><tbody>';
    items.forEach(function (item) {
      var timings = item.timings || {};
      var usage = item.usage || {};
      var sources = (usage.sources || []).map(sourceLabel).join(' / ') || '—';
      html += '<tr>' +
        '<td>' + esc(timeLabel(item.created_at)) + '</td>' +
        '<td>' + esc(taskTypeLabel(item.task_type)) + '</td>' +
        '<td>' + statusBadge(item.status) + '</td>' +
        '<td>' + esc(item.model_id || '—') + '</td>' +
        '<td>' + esc(item.creator_display || '—') + '</td>' +
        '<td>' + duration(timings.total_ms) + '</td>' +
        '<td>' + esc(sources) + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  }

  function syncOfficialUsage() {
    if (!state.isAdmin) return;
    if (!global.confirm('将调用火山引擎只读用量接口并写入本地快照，不会产生模型生成费用。确认同步？')) {
      return;
    }
    var button = $('ark-usage-sync');
    if (button) { button.disabled = true; button.textContent = '同步中…'; }
    global.AIGV.api('/api/admin/ark/usage/sync', {
      method: 'POST', body: { days: state.days }
    }).then(function (result) {
      setNotice('官方用量同步完成：' + (result.rows || 0) + ' 条快照。', 'success');
      state.data = null;
      return load(true);
    }).catch(function (error) {
      setNotice('官方用量同步失败：' + (error.message || '未知错误'), 'error');
    }).then(function () {
      if (button) {
        button.disabled = false;
        if (button.textContent === '同步中…') button.textContent = '同步官方用量';
      }
    });
  }

  global.AIGVArk = {
    init: init,
    activate: activate,
    isAdmin: isAdminNow,
    load: load,
    syncOfficialUsage: syncOfficialUsage
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
