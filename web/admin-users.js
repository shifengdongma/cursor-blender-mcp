(function (global) {
  'use strict';

  var state = {
    users: [],
    total: 0,
    page: 1,
    pageSize: 20,
    q: '',
    role: '',
    status: '',
    currentUser: null,
    editing: null,
    tasks: [],
    taskTotal: 0,
    taskPage: 1,
    taskPageSize: 20,
    taskType: '',
    taskStatus: '',
    audit: {
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      full: false,
      eventType: '',
      result: '',
      actor: '',
      startDate: '',
      endDate: '',
      optionsLoaded: false
    }
  };
  var toastContainer = document.getElementById('admin-toast-container');
  var modal = document.getElementById('admin-modal');
  var auditModal = document.getElementById('admin-audit-modal');

  function $(id) { return document.getElementById(id); }

  function showToast(message, type) {
    if (!toastContainer) return;
    var toast = document.createElement('div');
    toast.className = 'toast ' + (type === 'error' ? 'toast-error' : 'toast-success');
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3400);
  }

  function roleLabel(role) { return role === 'admin' ? '管理员' : '普通用户'; }
  function statusLabel(status) { return status === 'active' ? '正常' : '已禁用'; }
  function initial(user) {
    return String((user && (user.nickname || user.username)) || '?').trim().slice(0, 1).toUpperCase();
  }

  function renderStats(stats) {
    var container = $('admin-stats');
    if (!container) return;
    container.textContent = '';
    var users = stats.users || {};
    var tasks = stats.tasks || {};
    var cards = [
      ['总注册用户', users.total, '真实 auth_users'],
      ['正常账户', users.active, 'active'],
      ['禁用账户', users.disabled, 'disabled'],
      ['平台管理员', users.admins, 'role=admin'],
      ['图片任务', tasks.images, '全部状态'],
      ['视频任务', tasks.videos, '全部状态'],
      ['成功任务', tasks.succeeded, 'succeeded'],
      ['失败任务', tasks.failed, 'failed'],
      ['排队中', tasks.queued, 'queued'],
      ['运行中', tasks.running, 'submitting/running'],
      ['待确认', tasks.needs_review, 'needs_review']
    ];
    cards.forEach(function (item) {
      var card = document.createElement('div');
      card.className = 'profile-stat-card';
      var label = document.createElement('span');
      label.className = 'profile-stat-label';
      label.textContent = item[0];
      var value = document.createElement('strong');
      value.className = 'profile-stat-value';
      value.textContent = item[1] === undefined ? 0 : item[1];
      var hint = document.createElement('span');
      hint.className = 'profile-stat-hint';
      hint.textContent = item[2];
      card.appendChild(label);
      card.appendChild(value);
      card.appendChild(hint);
      container.appendChild(card);
    });
  }

  function renderUsers() {
    var container = $('admin-user-table');
    if (!container) return;
    container.textContent = '';
    if (!state.users.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '暂无符合条件的用户。';
      container.appendChild(empty);
    } else {
      var table = document.createElement('table');
      table.className = 'cp-table';
      var thead = document.createElement('thead');
      var headRow = document.createElement('tr');
      ['用户', '邮箱', '角色', '状态', '注册时间', '最近登录', '操作'].forEach(function (title) {
        var th = document.createElement('th');
        th.textContent = title;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);

      var tbody = document.createElement('tbody');
      state.users.forEach(function (user) {
        var row = document.createElement('tr');
        var self = state.currentUser && state.currentUser.id === user.id;

        var userCell = document.createElement('td');
        var userWrap = document.createElement('div');
        userWrap.className = 'admin-user-cell';
        if (user.avatar_url) {
          var img = document.createElement('img');
          img.className = 'nav-avatar';
          img.alt = '';
          img.src = user.avatar_url;
          userWrap.appendChild(img);
        } else {
          var fallback = document.createElement('span');
          fallback.className = 'nav-avatar nav-avatar-fallback';
          fallback.textContent = initial(user);
          userWrap.appendChild(fallback);
        }
        var names = document.createElement('div');
        var name = document.createElement('strong');
        name.textContent = user.nickname || user.username;
        var username = document.createElement('span');
        username.className = 'admin-user-username';
        username.textContent = '@' + user.username;
        names.appendChild(name);
        names.appendChild(username);
        userWrap.appendChild(names);
        userCell.appendChild(userWrap);
        row.appendChild(userCell);

        var email = document.createElement('td');
        email.textContent = user.email || '—';
        row.appendChild(email);

        var role = document.createElement('td');
        var roleBadge = document.createElement('span');
        roleBadge.className = 'cp-badge ' + (user.role === 'admin' ? 'cp-badge-success' : 'cp-badge-muted');
        roleBadge.textContent = roleLabel(user.role);
        role.appendChild(roleBadge);
        row.appendChild(role);

        var status = document.createElement('td');
        var statusBadge = document.createElement('span');
        statusBadge.className = 'cp-badge ' + (user.status === 'active' ? 'cp-badge-success' : 'cp-badge-danger');
        statusBadge.textContent = statusLabel(user.status);
        status.appendChild(statusBadge);
        row.appendChild(status);

        var created = document.createElement('td');
        created.textContent = AIGV.formatTime(user.created_at);
        row.appendChild(created);

        var lastLogin = document.createElement('td');
        lastLogin.textContent = AIGV.formatTime(user.last_login_at);
        row.appendChild(lastLogin);

        var actions = document.createElement('td');
        actions.className = 'admin-actions';
        if (self) {
          var selfLabel = document.createElement('span');
          selfLabel.className = 'field-hint';
          selfLabel.textContent = '当前账户';
          actions.appendChild(selfLabel);
        } else {
          var edit = document.createElement('button');
          edit.type = 'button';
          edit.className = 'cp-action-btn';
          edit.textContent = '编辑';
          edit.addEventListener('click', function () { openEdit(user); });
          actions.appendChild(edit);

          var roleBtn = document.createElement('button');
          roleBtn.type = 'button';
          roleBtn.className = 'cp-action-btn';
          roleBtn.textContent = user.role === 'admin' ? '设为普通用户' : '设为管理员';
          roleBtn.addEventListener('click', function () { changeRole(user); });
          actions.appendChild(roleBtn);

          var statusBtn = document.createElement('button');
          statusBtn.type = 'button';
          statusBtn.className = 'cp-action-btn';
          statusBtn.textContent = user.status === 'active' ? '禁用' : '启用';
          statusBtn.addEventListener('click', function () { changeStatus(user); });
          actions.appendChild(statusBtn);

          var revoke = document.createElement('button');
          revoke.type = 'button';
          revoke.className = 'cp-action-btn';
          revoke.textContent = '使会话失效';
          revoke.addEventListener('click', function () { revokeSessions(user); });
          actions.appendChild(revoke);
        }
        row.appendChild(actions);
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      container.appendChild(table);
    }
    renderPagination();
  }

  function renderPagination() {
    var container = $('admin-pagination');
    if (!container) return;
    container.textContent = '';
    var totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    var info = document.createElement('span');
    info.className = 'field-hint';
    info.textContent = '共 ' + state.total + ' 位用户，第 ' + state.page + ' / ' + totalPages + ' 页';
    container.appendChild(info);

    var controls = document.createElement('div');
    controls.className = 'ch-pagination-controls';
    var prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'ch-page-btn';
    prev.textContent = '上一页';
    prev.disabled = state.page <= 1;
    prev.addEventListener('click', function () { if (state.page > 1) { state.page -= 1; loadUsers(); } });
    controls.appendChild(prev);

    var next = document.createElement('button');
    next.type = 'button';
    next.className = 'ch-page-btn';
    next.textContent = '下一页';
    next.disabled = state.page >= totalPages;
    next.addEventListener('click', function () { if (state.page < totalPages) { state.page += 1; loadUsers(); } });
    controls.appendChild(next);
    container.appendChild(controls);
  }

  function loadStats() {
    return AIGV.api('/api/admin/stats').then(renderStats).catch(function (error) {
      showToast(error.message || '加载统计失败', 'error');
    });
  }

  function loadUsers() {
    var params = new URLSearchParams();
    params.append('limit', state.pageSize);
    params.append('offset', (state.page - 1) * state.pageSize);
    if (state.q) params.append('q', state.q);
    if (state.role) params.append('role', state.role);
    if (state.status) params.append('status', state.status);
    return AIGV.api('/api/admin/users?' + params.toString()).then(function (data) {
      state.users = data.items || [];
      state.total = data.total || 0;
      renderUsers();
    }).catch(function (error) {
      showToast(error.message || '加载用户失败', 'error');
    });
  }

  function taskStatusLabel(status) {
    var labels = {
      queued: '排队中', submitting: '提交中', running: '生成中',
      succeeded: '已完成', failed: '失败', cancelled: '已取消',
      needs_review: '待人工确认'
    };
    return labels[status] || status;
  }

  function renderTasks() {
    var container = $('admin-task-table');
    if (!container) return;
    container.textContent = '';
    if (!state.tasks.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '暂无符合条件的生成任务。';
      container.appendChild(empty);
    } else {
      var table = document.createElement('table');
      table.className = 'cp-table';
      var thead = document.createElement('thead');
      var headRow = document.createElement('tr');
      ['用户', '类型', '模型', '状态', '创建时间', 'Prompt / 错误', '操作'].forEach(function (title) {
        var th = document.createElement('th');
        th.textContent = title;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);

      var tbody = document.createElement('tbody');
      state.tasks.forEach(function (task) {
        var row = document.createElement('tr');
        var creator = task.creator || {};
        var cells = [
          creator.nickname || creator.username || task.created_by || '—',
          task.task_type === 'video' ? '视频' : '图片',
          task.model_id || (task.params && task.params.model_key) || '—',
          taskStatusLabel(task.status),
          AIGV.formatTime(task.created_at)
        ];
        cells.forEach(function (value) {
          var td = document.createElement('td');
          td.textContent = value === null || value === undefined ? '—' : String(value);
          row.appendChild(td);
        });

        var promptCell = document.createElement('td');
        promptCell.className = 'admin-task-prompt';
        var params = task.params || {};
        var prompt = document.createElement('span');
        prompt.textContent = params.prompt ? String(params.prompt).slice(0, 80) : '—';
        promptCell.appendChild(prompt);
        if (task.error_message) {
          var error = document.createElement('span');
          error.className = 'field-hint admin-task-error';
          error.textContent = task.error_message;
          promptCell.appendChild(error);
        }
        var details = document.createElement('details');
        var summary = document.createElement('summary');
        summary.textContent = '参数';
        var pre = document.createElement('pre');
        pre.textContent = JSON.stringify(params, null, 2);
        details.appendChild(summary);
        details.appendChild(pre);
        promptCell.appendChild(details);
        row.appendChild(promptCell);

        var actions = document.createElement('td');
        actions.className = 'admin-actions';
        if (task.status === 'queued' || task.status === 'submitting' || task.status === 'running') {
          var cancel = document.createElement('button');
          cancel.type = 'button';
          cancel.className = 'cp-action-btn';
          cancel.textContent = '取消';
          cancel.addEventListener('click', function () { cancelTask(task); });
          actions.appendChild(cancel);
        }
        if (task.status === 'failed' || task.status === 'needs_review') {
          var retry = document.createElement('button');
          retry.type = 'button';
          retry.className = 'cp-action-btn';
          retry.textContent = '重试';
          retry.addEventListener('click', function () { retryTask(task); });
          actions.appendChild(retry);
        }
        if (!actions.firstChild) {
          actions.textContent = '—';
        }
        row.appendChild(actions);
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      container.appendChild(table);
    }
    renderTaskPagination();
  }

  function renderTaskPagination() {
    var container = $('admin-task-pagination');
    if (!container) return;
    container.textContent = '';
    var totalPages = Math.max(1, Math.ceil(state.taskTotal / state.taskPageSize));
    var info = document.createElement('span');
    info.className = 'field-hint';
    info.textContent = '共 ' + state.taskTotal + ' 个任务，第 ' + state.taskPage + ' / ' + totalPages + ' 页';
    container.appendChild(info);

    var controls = document.createElement('div');
    controls.className = 'ch-pagination-controls';
    var prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'ch-page-btn';
    prev.textContent = '上一页';
    prev.disabled = state.taskPage <= 1;
    prev.addEventListener('click', function () {
      if (state.taskPage > 1) { state.taskPage -= 1; loadTasks(); }
    });
    controls.appendChild(prev);
    var next = document.createElement('button');
    next.type = 'button';
    next.className = 'ch-page-btn';
    next.textContent = '下一页';
    next.disabled = state.taskPage >= totalPages;
    next.addEventListener('click', function () {
      if (state.taskPage < totalPages) { state.taskPage += 1; loadTasks(); }
    });
    controls.appendChild(next);
    container.appendChild(controls);
  }

  function loadTasks() {
    var params = new URLSearchParams();
    params.append('scope', 'all');
    params.append('limit', state.taskPageSize);
    params.append('offset', (state.taskPage - 1) * state.taskPageSize);
    if (state.taskType) params.append('task_type', state.taskType);
    if (state.taskStatus) params.append('status', state.taskStatus);
    return AIGV.api('/api/generation/tasks?' + params.toString()).then(function (data) {
      state.tasks = data.items || [];
      state.taskTotal = data.total || 0;
      renderTasks();
    }).catch(function (error) {
      var container = $('admin-task-table');
      if (container) {
        container.textContent = '';
        var message = document.createElement('p');
        message.className = 'empty-state';
        message.textContent = error.message || '加载生成任务失败';
        container.appendChild(message);
      }
      showToast(error.message || '加载生成任务失败', 'error');
    });
  }

  function cancelTask(task) {
    if (!global.confirm('确认取消该生成任务？已产生的费用不会退回。')) return;
    AIGV.api('/api/generation/tasks/' + encodeURIComponent(task.id) + '/cancel', {
      method: 'POST'
    }).then(function () {
      showToast('取消请求已提交', 'success');
      loadTasks();
    }).catch(function (error) {
      showToast(error.message || '取消失败', 'error');
    });
  }

  function retryTask(task) {
    if (!global.confirm('重试可能重新提交第三方任务并产生费用；若任务已有第三方 ID，将只恢复轮询。确认继续？')) return;
    AIGV.api('/api/generation/tasks/' + encodeURIComponent(task.id) + '/retry', {
      method: 'POST',
      body: { confirm_duplicate: true }
    }).then(function () {
      showToast('任务已重新处理', 'success');
      loadTasks();
    }).catch(function (error) {
      showToast(error.message || '重试失败', 'error');
    });
  }

  function auditResultClass(result) {
    var map = {
      success: 'cp-badge online',
      succeeded: 'cp-badge online',
      failed: 'cp-badge error',
      failure: 'cp-badge error',
      error: 'cp-badge error',
      pending: 'cp-badge warning',
      accepted: 'cp-badge good',
      inconclusive: 'cp-badge warning',
      cancelled: 'cp-badge paused',
      canceled: 'cp-badge paused',
      warning: 'cp-badge warning'
    };
    return map[result] || 'cp-badge info';
  }

  function populateAuditFilterOptions(options) {
    if (!options || state.audit.optionsLoaded) return;
    var eventSelect = $('admin-audit-event-filter');
    var resultSelect = $('admin-audit-result-filter');
    (options.event_types || []).forEach(function (item) {
      if (!eventSelect || !item || !item.value) return;
      var option = document.createElement('option');
      option.value = item.value;
      option.textContent = item.label || item.value;
      eventSelect.appendChild(option);
    });
    (options.results || []).forEach(function (item) {
      if (!resultSelect || !item || !item.value) return;
      var option = document.createElement('option');
      option.value = item.value;
      option.textContent = item.label || item.value;
      resultSelect.appendChild(option);
    });
    state.audit.optionsLoaded = true;
  }

  function renderAudit() {
    var container = $('admin-audit-table');
    if (!container) return;
    container.textContent = '';
    var items = state.audit.items || [];
    if (!items.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '暂无符合条件的审计事件。';
      container.appendChild(empty);
      renderAuditPagination();
      return;
    }
    var table = document.createElement('table');
    table.className = 'cp-table';
    var thead = document.createElement('thead');
    var head = document.createElement('tr');
    ['时间', '事件', '结果', '操作人', '操作目标', '详情'].forEach(function (title) {
      var th = document.createElement('th');
      th.textContent = title;
      head.appendChild(th);
    });
    thead.appendChild(head);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    items.forEach(function (event) {
      var row = document.createElement('tr');

      var timeCell = document.createElement('td');
      timeCell.textContent = AIGV.formatTime(event.created_at);
      row.appendChild(timeCell);

      var eventCell = document.createElement('td');
      eventCell.textContent = event.event_label || '其他系统事件';
      eventCell.title = event.event_type || '';
      row.appendChild(eventCell);

      var resultCell = document.createElement('td');
      var resultBadge = document.createElement('span');
      resultBadge.className = auditResultClass(event.result);
      resultBadge.textContent = event.result_label || event.result || '已记录';
      resultCell.appendChild(resultBadge);
      row.appendChild(resultCell);

      var actorCell = document.createElement('td');
      actorCell.textContent = event.actor_display || '—';
      actorCell.title = event.actor_user_id || '';
      row.appendChild(actorCell);

      var targetCell = document.createElement('td');
      targetCell.textContent = event.target_display || '—';
      targetCell.title = event.target_id || '';
      row.appendChild(targetCell);

      var detailCell = document.createElement('td');
      var detailButton = document.createElement('button');
      detailButton.type = 'button';
      detailButton.className = 'cp-action-btn';
      detailButton.textContent = '查看详情';
      detailButton.addEventListener('click', function () { openAuditDetail(event.id); });
      detailCell.appendChild(detailButton);
      row.appendChild(detailCell);

      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    container.appendChild(table);
    renderAuditPagination();
  }

  function renderAuditPagination() {
    var container = $('admin-audit-pagination');
    if (!container) return;
    container.textContent = '';
    if (!state.audit.full) return;
    var totalPages = Math.max(1, Math.ceil(state.audit.total / state.audit.pageSize));
    var info = document.createElement('span');
    info.className = 'field-hint';
    info.textContent = '共 ' + state.audit.total + ' 条，第 ' + state.audit.page + ' / ' + totalPages + ' 页';
    container.appendChild(info);

    var controls = document.createElement('div');
    controls.className = 'ch-pagination-controls';
    var prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'ch-page-btn';
    prev.textContent = '上一页';
    prev.disabled = state.audit.page <= 1;
    prev.addEventListener('click', function () {
      if (state.audit.page > 1) {
        state.audit.page -= 1;
        loadAudit();
      }
    });
    controls.appendChild(prev);
    var next = document.createElement('button');
    next.type = 'button';
    next.className = 'ch-page-btn';
    next.textContent = '下一页';
    next.disabled = state.audit.page >= totalPages;
    next.addEventListener('click', function () {
      if (state.audit.page < totalPages) {
        state.audit.page += 1;
        loadAudit();
      }
    });
    controls.appendChild(next);
    container.appendChild(controls);
  }

  function loadAudit() {
    var params = new URLSearchParams();
    params.append('limit', state.audit.full ? state.audit.pageSize : 10);
    params.append('offset', state.audit.full ? (state.audit.page - 1) * state.audit.pageSize : 0);
    if (state.audit.eventType) params.append('event_type', state.audit.eventType);
    if (state.audit.result) params.append('result', state.audit.result);
    if (state.audit.actor) params.append('actor', state.audit.actor);
    if (state.audit.startDate) params.append('start_date', state.audit.startDate);
    if (state.audit.endDate) params.append('end_date', state.audit.endDate);
    return AIGV.api('/api/admin/audit-logs?' + params.toString()).then(function (data) {
      state.audit.items = data.items || [];
      state.audit.total = data.total || 0;
      populateAuditFilterOptions(data.filter_options);
      renderAudit();
    }).catch(function (error) {
      state.audit.items = [];
      state.audit.total = 0;
      renderAudit();
      var container = $('admin-audit-table');
      if (container) {
        container.textContent = '';
        var empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.textContent = '审计日志加载失败：' + (error.message || '未知错误');
        container.appendChild(empty);
      }
      showToast(error.message || '审计日志加载失败', 'error');
    });
  }

  function appendAuditDetailRow(container, label, value) {
    var row = document.createElement('div');
    row.className = 'admin-audit-detail-row';
    var labelEl = document.createElement('span');
    labelEl.className = 'admin-audit-detail-label';
    labelEl.textContent = label;
    var valueEl = document.createElement('span');
    valueEl.className = 'admin-audit-detail-value';
    valueEl.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    container.appendChild(row);
    return valueEl;
  }

  function renderAuditDetail(data) {
    var container = $('admin-audit-detail');
    if (!container) return;
    container.textContent = '';
    var detail = data.detail || {};
    var rawIds = detail.raw_ids || {};
    var model = detail.model || null;
    var project = detail.project || null;
    var error = detail.error || null;

    var eventValue = appendAuditDetailRow(container, '事件类型',
      (data.event_label || '其他系统事件') + '（' + (detail.event_raw_code || data.event_type || '—') + '）');
    eventValue.classList.add('admin-audit-mono');
    appendAuditDetailRow(container, '发生时间', AIGV.formatTime(data.created_at));
    appendAuditDetailRow(container, '操作人', data.actor_display || '—');
    if (data.actor_display_snapshot && data.actor_display_snapshot !== data.actor_display) {
      appendAuditDetailRow(container, '操作人快照', data.actor_display_snapshot);
    }
    appendAuditDetailRow(container, '操作对象', data.target_display || '—');
    appendAuditDetailRow(container, '操作结果', data.result_label || data.result || '—');
    appendAuditDetailRow(container, '相关模型', model
      ? [model.provider || '', model.model_id || ''].filter(Boolean).join(' · ')
      : '—');
    appendAuditDetailRow(container, '相关项目', project
      ? (project.name || project.id) + (project.id ? '（' + project.id + '）' : '')
      : '—');
    appendAuditDetailRow(container, '错误原因', error
      ? [error.code || '', error.message || ''].filter(Boolean).join(' · ')
      : '—');
    appendAuditDetailRow(container, '请求 ID', data.request_id || '—');
    var eventIdEl = appendAuditDetailRow(container, '原始事件 ID', rawIds.event_id || data.id || '—');
    eventIdEl.classList.add('admin-audit-mono');
    var targetIdEl = appendAuditDetailRow(container, '原始目标 ID', rawIds.target_id || '—');
    targetIdEl.classList.add('admin-audit-mono');
    var actorIdEl = appendAuditDetailRow(container, '原始操作人 ID（脱敏）', rawIds.actor_user_id || '—');
    actorIdEl.classList.add('admin-audit-mono');

    var metadataTitle = document.createElement('div');
    metadataTitle.className = 'admin-audit-detail-section';
    metadataTitle.textContent = '已脱敏的详细 Metadata';
    container.appendChild(metadataTitle);
    var pre = document.createElement('pre');
    pre.className = 'admin-audit-metadata';
    pre.textContent = JSON.stringify(detail.sanitized_metadata || data.metadata || {}, null, 2);
    container.appendChild(pre);
  }

  function openAuditDetail(eventId) {
    AIGV.api('/api/admin/audit-logs/' + encodeURIComponent(eventId)).then(function (data) {
      renderAuditDetail(data);
      if (auditModal) {
        auditModal.classList.add('is-open');
        auditModal.setAttribute('aria-hidden', 'false');
      }
    }).catch(function (error) {
      showToast(error.message || '审计详情加载失败', 'error');
    });
  }

  function closeAuditDetail() {
    if (auditModal) {
      auditModal.classList.remove('is-open');
      auditModal.setAttribute('aria-hidden', 'true');
    }
  }

  function resetAuditFilters() {
    state.audit.eventType = '';
    state.audit.result = '';
    state.audit.actor = '';
    state.audit.startDate = '';
    state.audit.endDate = '';
    state.audit.page = 1;
    if ($('admin-audit-event-filter')) $('admin-audit-event-filter').value = '';
    if ($('admin-audit-result-filter')) $('admin-audit-result-filter').value = '';
    if ($('admin-audit-actor-filter')) $('admin-audit-actor-filter').value = '';
    if ($('admin-audit-start-date')) $('admin-audit-start-date').value = '';
    if ($('admin-audit-end-date')) $('admin-audit-end-date').value = '';
    loadAudit();
  }

  function refreshAll() {
    loadStats();
    loadUsers();
    loadTasks();
    loadAudit();
  }

  function changeRole(user) {
    var nextRole = user.role === 'admin' ? 'user' : 'admin';
    var label = nextRole === 'admin' ? '设为平台管理员' : '降级为普通用户';
    if (!global.confirm('确认将 ' + (user.nickname || user.username) + ' ' + label + '？')) return;
    AIGV.api('/api/admin/users/' + encodeURIComponent(user.id) + '/role', {
      method: 'PATCH', body: { role: nextRole }
    }).then(function () {
      showToast('角色已更新', 'success');
      refreshAll();
    }).catch(function (error) {
      showToast(error.message || '角色更新失败', 'error');
    });
  }

  function changeStatus(user) {
    var nextStatus = user.status === 'active' ? 'disabled' : 'active';
    var label = nextStatus === 'active' ? '启用' : '禁用';
    if (!global.confirm('确认' + label + '用户 ' + (user.nickname || user.username) + '？')) return;
    AIGV.api('/api/admin/users/' + encodeURIComponent(user.id) + '/status', {
      method: 'PATCH', body: { status: nextStatus }
    }).then(function () {
      showToast('用户状态已更新', 'success');
      refreshAll();
    }).catch(function (error) {
      showToast(error.message || '状态更新失败', 'error');
    });
  }

  function revokeSessions(user) {
    if (!global.confirm('确认使 ' + (user.nickname || user.username) + ' 的所有会话失效？')) return;
    AIGV.api('/api/admin/users/' + encodeURIComponent(user.id) + '/sessions/revoke', {
      method: 'POST'
    }).then(function () {
      showToast('该用户的会话已失效', 'success');
    }).catch(function (error) {
      showToast(error.message || '操作失败', 'error');
    });
  }

  function openEdit(user) {
    state.editing = user;
    $('admin-edit-username').value = user.username || '';
    $('admin-edit-nickname').value = user.nickname || '';
    $('admin-edit-email').value = user.email || '';
    $('admin-edit-bio').value = user.bio || '';
    if (modal) {
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden', 'false');
    }
  }

  function closeEdit() {
    state.editing = null;
    if (modal) {
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
    }
  }

  function submitEdit(event) {
    event.preventDefault();
    if (!state.editing) return;
    AIGV.api('/api/admin/users/' + encodeURIComponent(state.editing.id), {
      method: 'PATCH',
      body: {
        nickname: $('admin-edit-nickname').value.trim(),
        email: $('admin-edit-email').value.trim(),
        bio: $('admin-edit-bio').value.trim()
      }
    }).then(function () {
      showToast('用户资料已更新', 'success');
      closeEdit();
      refreshAll();
    }).catch(function (error) {
      showToast(error.message || '保存失败', 'error');
    });
  }

  function debounce(fn, delay) {
    var timer = null;
    return function () {
      var args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(null, args); }, delay);
    };
  }

  function init() {
    AIGV.getCurrentUser().then(function (user) {
      state.currentUser = user;
      refreshAll();
    }).catch(function () {
      showToast('无法获取当前用户', 'error');
    });

    var search = $('admin-search');
    if (search) {
      search.addEventListener('input', debounce(function () {
        state.q = search.value.trim();
        state.page = 1;
        loadUsers();
      }, 300));
    }
    var roleFilter = $('admin-role-filter');
    if (roleFilter) {
      roleFilter.addEventListener('change', function () {
        state.role = roleFilter.value;
        state.page = 1;
        loadUsers();
      });
    }
    var statusFilter = $('admin-status-filter');
    if (statusFilter) {
      statusFilter.addEventListener('change', function () {
        state.status = statusFilter.value;
        state.page = 1;
        loadUsers();
      });
    }
    var refresh = $('admin-refresh');
    if (refresh) refresh.addEventListener('click', refreshAll);

    var taskRefresh = $('admin-task-refresh');
    if (taskRefresh) taskRefresh.addEventListener('click', loadTasks);
    var taskTypeFilter = $('admin-task-type-filter');
    if (taskTypeFilter) {
      taskTypeFilter.addEventListener('change', function () {
        state.taskType = taskTypeFilter.value;
        state.taskPage = 1;
        loadTasks();
      });
    }
    var taskStatusFilter = $('admin-task-status-filter');
    if (taskStatusFilter) {
      taskStatusFilter.addEventListener('change', function () {
        state.taskStatus = taskStatusFilter.value;
        state.taskPage = 1;
        loadTasks();
      });
    }

    var auditEventFilter = $('admin-audit-event-filter');
    if (auditEventFilter) {
      auditEventFilter.addEventListener('change', function () {
        state.audit.eventType = auditEventFilter.value;
        state.audit.page = 1;
        loadAudit();
      });
    }
    var auditResultFilter = $('admin-audit-result-filter');
    if (auditResultFilter) {
      auditResultFilter.addEventListener('change', function () {
        state.audit.result = auditResultFilter.value;
        state.audit.page = 1;
        loadAudit();
      });
    }
    var auditActorFilter = $('admin-audit-actor-filter');
    if (auditActorFilter) {
      auditActorFilter.addEventListener('input', debounce(function () {
        state.audit.actor = auditActorFilter.value.trim();
        state.audit.page = 1;
        loadAudit();
      }, 350));
    }
    var auditStartDate = $('admin-audit-start-date');
    if (auditStartDate) {
      auditStartDate.addEventListener('change', function () {
        state.audit.startDate = auditStartDate.value;
        state.audit.page = 1;
        loadAudit();
      });
    }
    var auditEndDate = $('admin-audit-end-date');
    if (auditEndDate) {
      auditEndDate.addEventListener('change', function () {
        state.audit.endDate = auditEndDate.value;
        state.audit.page = 1;
        loadAudit();
      });
    }
    var auditReset = $('admin-audit-reset');
    if (auditReset) auditReset.addEventListener('click', resetAuditFilters);

    var auditToggle = $('admin-audit-toggle');
    if (auditToggle) {
      auditToggle.addEventListener('click', function () {
        state.audit.full = !state.audit.full;
        state.audit.page = 1;
        auditToggle.textContent = state.audit.full ? '收起' : '查看全部记录';
        loadAudit();
      });
    }
    var auditModalClose = $('admin-audit-modal-close');
    if (auditModalClose) auditModalClose.addEventListener('click', closeAuditDetail);
    if (auditModal) {
      auditModal.addEventListener('click', function (event) {
        if (event.target === auditModal) closeAuditDetail();
      });
    }
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closeAuditDetail();
    });

    var editForm = $('admin-edit-form');
    if (editForm) editForm.addEventListener('submit', submitEdit);
    var close = $('admin-modal-close');
    if (close) close.addEventListener('click', closeEdit);
    var cancel = $('admin-edit-cancel');
    if (cancel) cancel.addEventListener('click', closeEdit);
    if (modal) {
      modal.addEventListener('click', function (event) {
        if (event.target === modal) closeEdit();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
