(function () {
  var stageOrder = [
    "queued",
    "knowledge_ready",
    "rights_validated",
    "resource_scheduling",
    "blender_exporting",
    "provider_submitted",
    "provider_running",
    "streaming",
    "billing_recorded",
    "succeeded"
  ];

  var stageLabels = {
    queued: "已创建任务",
    knowledge_ready: "知识检索与 Prompt 编排",
    rights_validated: "版权校验",
    resource_scheduling: "算力调度",
    blender_exporting: "Blender 空间导出",
    provider_submitted: "已提交执行通道",
    provider_running: "视频模型处理中",
    streaming: "推流会话准备",
    billing_recorded: "计费快照记录",
    succeeded: "生成完成",
    error: "执行失败"
  };

  var state = {
    bootstrap: null,
    currentJobId: null,
    pollTimer: null,
    autoTitle: true,
    uiStatus: "loading",
    lastPreview: null,
    currentJob: null,
    demoContext: null,
    previewRequestId: 0,
    submitRequestId: 0,
    pollRequestId: 0
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function apiMessage(payload, fallback) {
    if (payload && payload.message) return payload.message;
    if (payload && payload.error) return payload.error;
    return fallback;
  }

  function api(path, options) {
    return window.AIGV.api(path, options || {});
  }

  function setUiStatus(status, message) {
    state.uiStatus = status;
    if (els.workspaceSection) els.workspaceSection.setAttribute("data-ui-status", status);
    if (els.jobStatus) {
      els.jobStatus.textContent = message || "";
      els.jobStatus.setAttribute("data-status-tone", status);
    }
    syncActionStates();
  }

  function syncActionStates() {
    var busy = state.uiStatus === "loading" || state.uiStatus === "previewing" || state.uiStatus === "submitting";
    if (els.previewBtn) els.previewBtn.disabled = busy;
    if (els.submitBtn) els.submitBtn.disabled = busy;
  }

  function populateSelect(selectEl, items, formatter, selectedValue) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    (items || []).forEach(function (item) {
      var option = document.createElement("option");
      option.value = item.id;
      option.textContent = formatter(item);
      if (selectedValue && selectedValue === item.id) option.selected = true;
      selectEl.appendChild(option);
    });
  }

  function getVenueById(id) {
    var items = (state.bootstrap && state.bootstrap.venue_catalog) || [];
    for (var i = 0; i < items.length; i += 1) if (items[i].id === id) return items[i];
    return null;
  }

  function getAssetsForVenue(venueId) {
    var allAssets = (state.bootstrap && state.bootstrap.asset_catalog) || [];
    return allAssets.filter(function (asset) {
      return asset.id === "text_only" || asset.venue_type === venueId;
    });
  }

  function getRecommendedAsset(venueId) {
    var assets = getAssetsForVenue(venueId);
    for (var i = 0; i < assets.length; i += 1) if (assets[i].recommended) return assets[i];
    return assets[0] || null;
  }

  function populateAssetSelect(venueId, selectedValue) {
    populateSelect(els.assetId, getAssetsForVenue(venueId), function (asset) {
      return asset.name + " · " + (asset.source_type || asset.asset_kind || "");
    }, selectedValue);
  }

  function applyVenueDefaults() {
    var venue = getVenueById(els.venueType && els.venueType.value);
    if (!venue) return;
    if (state.autoTitle || !els.title.value) {
      els.title.value = venue.hero_title || "";
      state.autoTitle = true;
    }
    if (els.environmentHint) els.environmentHint.value = venue.default_environment || "";
    if (els.lightingHint) els.lightingHint.value = venue.default_lighting || "";
    populateAssetSelect(venue.id, (getRecommendedAsset(venue.id) || {}).id);
  }

  function collectPayload() {
    return {
      title: els.title ? els.title.value : "",
      venue_type: els.venueType ? els.venueType.value : "",
      ai_model: els.aiModel ? els.aiModel.value : "",
      asset_id: els.assetId ? els.assetId.value : "",
      shot_type: els.shotType ? els.shotType.value : "orbit",
      camera_move_type: els.shotType ? els.shotType.value : "orbit",
      duration_s: els.duration ? els.duration.value : 6,
      environment_hint: els.environmentHint ? els.environmentHint.value : "",
      lighting_hint: els.lightingHint ? els.lightingHint.value : "",
      tenant_id: els.tenantId ? els.tenantId.value : "",
      user_id: els.userId ? els.userId.value : "",
      project_id: els.projectId ? els.projectId.value : "",
      engine_target: els.engineTarget ? els.engineTarget.value : "blender_anchor",
      render_mode: els.renderMode ? els.renderMode.value : "cinematic",
      stream_profile: els.streamProfile ? els.streamProfile.value : "balanced",
      usage_scope: els.usageScope ? els.usageScope.value : "internal_demo"
    };
  }

  function renderWarnings(warnings) {
    if (!els.previewWarnings) return;
    if (!warnings || !warnings.length) {
      els.previewWarnings.className = 'warning-stack warning-stack-inline';
      els.previewWarnings.innerHTML = '';
      return;
    }
    els.previewWarnings.className = 'warning-stack';
    els.previewWarnings.innerHTML = (warnings || []).map(function (warning) {
      return '<div class="warning-item">' + escapeHtml(warning) + '</div>';
    }).join('');
  }

  function renderModuleCards(modules) {
    modules = modules || {};
    return '<div class="module-grid">' +
      '<div class="module-card"><strong>镜头</strong><p>' + escapeHtml(modules.camera) + '</p></div>' +
      '<div class="module-card"><strong>主体</strong><p>' + escapeHtml(modules.subject) + '</p></div>' +
      '<div class="module-card"><strong>动态</strong><p>' + escapeHtml(modules.dynamics) + '</p></div>' +
      '<div class="module-card"><strong>环境</strong><p>' + escapeHtml(modules.environment) + '</p></div>' +
      '<div class="module-card"><strong>光影</strong><p>' + escapeHtml(modules.lighting) + '</p></div>' +
      '<div class="module-card"><strong>风格</strong><p>' + escapeHtml(modules.style) + '</p></div>' +
      '</div>';
  }

  function renderKeyValueList(items) {
    return '<ul class="meta-list">' + (items || []).map(function (item) {
      return '<li><strong>' + escapeHtml(item.label) + '：</strong>' + escapeHtml(item.value) + '</li>';
    }).join('') + '</ul>';
  }

  function renderPromptPreview(data) {
    if (!els.promptPreview) return;
    if (!data || !data.prompt_bundle) {
      els.promptPreview.innerHTML = '<p class="empty-state">选择场馆后自动生成 Prompt 预览</p>';
      if (els.executionRoute) els.executionRoute.textContent = '未生成';
      renderWarnings([]);
      return;
    }
    state.lastPreview = data;
    var bundle = data.prompt_bundle || {};
    if (els.executionRoute) {
      els.executionRoute.textContent = (data.display_model || bundle.display_model || '未指定') + ' → ' + (data.execution_provider || bundle.execution_provider || '未指定') + ' · ' + (data.route_mode || bundle.route_mode || 'native');
    }
    renderWarnings(data.warnings || []);
    els.promptPreview.innerHTML =
      '<section class="preview-block"><h4>六模块 Prompt</h4>' + renderModuleCards(bundle.modules || {}) + '</section>' +
      '<section class="preview-block"><div class="preview-heading"><h4>最终 Prompt</h4><span class="preview-chip">' + escapeHtml(bundle.workflow_mode || 'text_to_video') + '</span></div><p class="text-block prompt-output">' + escapeHtml(bundle.prompt) + '</p></section>';
  }

  function stageIndex(stage) {
    var idx = stageOrder.indexOf(stage);
    return idx >= 0 ? idx : -1;
  }

  function renderStageList(job) {
    if (!els.stageList) return;
    var currentStage = (job && job.stage) || 'queued';
    var currentIndex = stageIndex(currentStage);
    els.stageList.innerHTML = stageOrder.map(function (stage, index) {
      var className = 'pending';
      if (job && job.status === 'error') {
        if (index < currentIndex) className = 'done';
        else if (stage === currentStage) className = 'error';
      } else if (currentStage === 'succeeded' || index < currentIndex) className = 'done';
      else if (stage === currentStage) className = 'active';
      return '<li class="' + className + '"><span>' + escapeHtml(stageLabels[stage] || stage) + '</span><span>' + escapeHtml(stage) + '</span></li>';
    }).join('');
  }

  function renderContextPanel() {
    if (!els.contextSummary) return;
    var tenantText = els.tenantId && els.tenantId.selectedOptions[0] ? els.tenantId.selectedOptions[0].textContent : '-';
    var userText = els.userId && els.userId.selectedOptions[0] ? els.userId.selectedOptions[0].textContent : '-';
    var projectText = els.projectId && els.projectId.selectedOptions[0] ? els.projectId.selectedOptions[0].textContent : '-';
    els.contextSummary.innerHTML =
      '<div class="context-grid">' +
      '<div class="context-card"><span class="overview-label">当前租户</span><strong class="overview-value">' + escapeHtml(tenantText) + '</strong></div>' +
      '<div class="context-card"><span class="overview-label">当前用户</span><strong class="overview-value">' + escapeHtml(userText) + '</strong></div>' +
      '<div class="context-card"><span class="overview-label">当前项目</span><strong class="overview-value">' + escapeHtml(projectText) + '</strong></div>' +
      '<div class="context-card"><span class="overview-label">引擎目标</span><strong class="overview-value">' + escapeHtml(els.engineTarget && els.engineTarget.selectedOptions[0] ? els.engineTarget.selectedOptions[0].textContent : '-') + '</strong></div>' +
      '<div class="context-card"><span class="overview-label">推流配置</span><strong class="overview-value">' + escapeHtml(els.streamProfile && els.streamProfile.selectedOptions[0] ? els.streamProfile.selectedOptions[0].textContent : '-') + '</strong></div>' +
      '</div>';
  }

  function renderOpsPanel(job) {
    if (!els.opsPanel) return;
    var events = (job && job.result && job.result.ops_events) || [];
    if (!events.length) {
      els.opsPanel.innerHTML = '<p class="empty-state">等待任务事件流</p>';
      return;
    }
    els.opsPanel.innerHTML = '<ul class="meta-list">' + events.map(function (item) {
      return '<li><strong>' + escapeHtml(item.event_type || '-') + '</strong><br />' + escapeHtml(item.message || '') + '</li>';
    }).join('') + '</ul>';
  }

  function renderSchedulePanel(job) {
    if (!els.schedulePanel) return;
    var data = job && job.result && job.result.schedule_result;
    if (!data) {
      els.schedulePanel.innerHTML = '<p class="empty-state">等待调度结果</p>';
      return;
    }
    var node = data.node || {};
    els.schedulePanel.innerHTML = renderKeyValueList([
      { label: '节点', value: node.node_name || '-' },
      { label: 'GPU', value: node.gpu_type || '-' },
      { label: '资源池', value: data.pool_type || '-' },
      { label: '队列深度', value: String(data.queue_depth || 0) },
      { label: '调度原因', value: data.reason || '-' }
    ]);
  }

  function renderMonitorPanel(job) {
    if (!els.monitorPanel) return;
    var latest = job && job.result && job.result.monitor_summary && job.result.monitor_summary.latest;
    if (!latest) {
      els.monitorPanel.innerHTML = '<p class="empty-state">等待监控快照</p>';
      return;
    }
    els.monitorPanel.innerHTML = renderKeyValueList([
      { label: 'GPU 使用率', value: latest.gpu_utilization + '%' },
      { label: '显存', value: latest.gpu_memory_gb + ' GB' },
      { label: '网络', value: latest.network_mbps + ' Mbps' },
      { label: '码率', value: latest.bitrate_mbps + ' Mbps' },
      { label: '延迟', value: latest.latency_ms + ' ms' },
      { label: 'FPS', value: String(latest.fps || '-') }
    ]);
  }

  function renderRightsPanel(job) {
    if (!els.rightsPanel) return;
    var rights = job && job.result && job.result.rights_result;
    if (!rights) {
      els.rightsPanel.innerHTML = '<p class="empty-state">等待版权校验</p>';
      return;
    }
    var rightsInfo = rights.rights || {};
    els.rightsPanel.innerHTML = renderKeyValueList([
      { label: '授权状态', value: rights.status || '-' },
      { label: '许可类型', value: rightsInfo.license_type || '-' },
      { label: '来源', value: rightsInfo.source_name || '-' },
      { label: '用途范围', value: rights.usage_scope || '-' },
      { label: '审批状态', value: rightsInfo.approval_status || '-' }
    ]);
  }

  function renderBillingPanel(job) {
    if (!els.billingPanel) return;
    var billing = job && job.result && job.result.billing_result;
    if (!billing) {
      els.billingPanel.innerHTML = '<p class="empty-state">等待计费快照</p>';
      return;
    }
    els.billingPanel.innerHTML = renderKeyValueList([
      { label: '任务费用', value: billing.amount + ' ' + (billing.currency || 'CNY') },
      { label: 'GPU 时长', value: String(billing.gpu_hours || 0) },
      { label: '引擎时长', value: String(billing.engine_hours || 0) },
      { label: '推流时长', value: String(billing.stream_hours || 0) },
      { label: '资源节点', value: billing.resource_node || '-' }
    ]);
  }

  function renderJobResult(job) {
    if (!els.jobResult) return;
    if (!job || !job.result) {
      els.jobResult.innerHTML = '<p class="empty-state">任务完成后在此展示视频结果</p>';
      renderSchedulePanel(null);
      renderMonitorPanel(null);
      renderRightsPanel(null);
      renderBillingPanel(null);
      renderOpsPanel(null);
      return;
    }
    var result = job.result;
    var blocks = [];
    var provider = result.provider_result || {};
    blocks.push('<div class="result-block"><h4>调度结果</h4>' + renderKeyValueList([
      { label: '资源池', value: ((result.schedule_result || {}).pool_type) || '-' },
      { label: '节点', value: (((result.schedule_result || {}).node) || {}).node_name || '-' },
      { label: '原因', value: (result.schedule_result || {}).reason || '-' }
    ]) + '</div>');
    blocks.push('<div class="result-block"><h4>引擎会话</h4>' + renderKeyValueList([
      { label: '引擎', value: ((result.engine_session || {}).display_name) || '-' },
      { label: '渲染模式', value: ((result.engine_session || {}).render_mode) || '-' },
      { label: '会话状态', value: ((result.engine_session || {}).session_status) || '-' },
      { label: '预览链接', value: ((result.engine_session || {}).preview_link) || '-' }
    ]) + '</div>');
    blocks.push('<div class="result-block"><h4>推流会话</h4>' + renderKeyValueList([
      { label: '协议', value: ((result.stream_session || {}).protocol) || '-' },
      { label: '码率', value: String(((result.stream_session || {}).bitrate_mbps) || '-') },
      { label: '延迟', value: String(((result.stream_session || {}).latency_ms) || '-') },
      { label: 'FPS', value: String(((result.stream_session || {}).fps) || '-') }
    ]) + '</div>');
    blocks.push('<div class="result-block"><h4>版权快照摘要</h4>' + renderKeyValueList([
      { label: '状态', value: ((result.rights_result || {}).status) || '-' },
      { label: '说明', value: ((result.rights_result || {}).message) || '-' }
    ]) + '</div>');
    blocks.push('<div class="result-block"><h4>计费明细</h4>' + renderKeyValueList([
      { label: '总费用', value: result.billing_result ? (result.billing_result.amount + ' ' + result.billing_result.currency) : '-' },
      { label: '执行通道', value: provider.execution_provider || '-' },
      { label: '路由模式', value: provider.route_mode || '-' }
    ]) + '</div>');
    if (result.video_url) {
      blocks.push('<div class="result-block result-block-video"><h4>视频结果</h4><video class="result-video" controls preload="metadata"><source src="' + encodeURI(result.video_url) + '" type="video/mp4" /></video></div>');
    }
    if (job.status === 'error') {
      blocks.push('<div class="result-block result-block-error"><h4>错误信息</h4><p class="text-block">' + escapeHtml(job.error || '未知错误') + '</p></div>');
    }
    els.jobResult.innerHTML = blocks.join('');
    renderSchedulePanel(job);
    renderMonitorPanel(job);
    renderRightsPanel(job);
    renderBillingPanel(job);
    renderOpsPanel(job);
  }

  function renderJob(job) {
    state.currentJob = job || null;
    if (els.jobId) els.jobId.textContent = job && job.id ? job.id : '等待提交';
    renderStageList(job);
    renderJobResult(job);
    renderContextPanel();
    if (!job) {
      setUiStatus('ready', '工作台就绪，请配置场景参数后提交任务。');
      return;
    }
    var statusText = '状态：' + (job.status || 'unknown') + ' · 阶段：' + (job.stage || 'queued');
    if (job.error) statusText += ' · 错误：' + job.error;
    if (job.status === 'succeeded') setUiStatus('success', statusText);
    else if (job.status === 'error') setUiStatus('error', statusText);
    else if (state.pollTimer) setUiStatus('polling', statusText);
    else setUiStatus('ready', statusText);
    if (job.result && job.result.prompt_bundle) {
      renderPromptPreview({
        prompt_bundle: job.result.prompt_bundle,
        warnings: job.result.warnings,
        display_model: job.result.provider_result && job.result.provider_result.display_model,
        execution_provider: job.result.provider_result && job.result.provider_result.execution_provider,
        route_mode: job.result.provider_result && job.result.provider_result.route_mode
      });
    }
  }

  function clearPoll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function fetchJob(jobId, requestId) {
    var job = await api('/api/jobs/' + encodeURIComponent(jobId));
    if (requestId !== state.pollRequestId) return null;
    return job;
  }

  function startPolling(jobId) {
    clearPoll();
    state.currentJobId = jobId;
    state.pollRequestId += 1;
    var requestId = state.pollRequestId;
    setUiStatus('polling', '任务已提交，正在轮询执行状态...');
    state.pollTimer = setInterval(async function () {
      try {
        var job = await fetchJob(jobId, requestId);
        if (!job) return;
        renderJob(job);
        if (job.status === 'succeeded' || job.status === 'error') clearPoll();
      } catch (err) {
        clearPoll();
        setUiStatus('error', '轮询失败：' + err.message);
      }
    }, 5000);
  }

  async function previewPrompt(options) {
    options = options || {};
    var silent = !!options.silent;
    state.previewRequestId += 1;
    var requestId = state.previewRequestId;
    if (!silent) setUiStatus('previewing', '正在生成 Prompt 预览...');
    var data = await api('/api/prompt/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collectPayload())
    });
    if (requestId !== state.previewRequestId) return null;
    renderPromptPreview(data);
    if (!silent) setUiStatus('ready', 'Prompt 预览已更新。');
    return data;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    clearPoll();
    state.submitRequestId += 1;
    var requestId = state.submitRequestId;
    setUiStatus('submitting', '正在创建任务...');
    try {
      await previewPrompt({ silent: true });
      if (requestId !== state.submitRequestId) return;
      var job = await api('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectPayload())
      });
      if (requestId !== state.submitRequestId) return;
      renderJob(job);
      startPolling(job.id);
    } catch (err) {
      setUiStatus('error', '创建任务失败：' + err.message);
    }
  }

  function queueSilentPreview() {
    previewPrompt({ silent: true }).catch(function () {});
    renderContextPanel();
  }

  function bindEvents() {
    if (els.title) {
      els.title.addEventListener('input', function () { state.autoTitle = false; });
    }
    ['venueType', 'aiModel', 'assetId', 'shotType', 'tenantId', 'userId', 'projectId', 'engineTarget', 'renderMode', 'streamProfile', 'usageScope'].forEach(function (key) {
      if (els[key]) {
        els[key].addEventListener('change', function () {
          if (key === 'venueType') {
            state.autoTitle = true;
            applyVenueDefaults();
          }
          queueSilentPreview();
        });
      }
    });
    if (els.previewBtn) els.previewBtn.addEventListener('click', function () { previewPrompt({ silent: false }).catch(function (err) { setUiStatus('error', 'Prompt 预览失败：' + err.message); }); });
    if (els.form) els.form.addEventListener('submit', handleSubmit);
  }

  function cacheElements() {
    els.workspaceSection = $('workspace');
    els.form = $('job-form');
    els.title = $('title');
    els.venueType = $('venue_type');
    els.aiModel = $('ai_model');
    els.assetId = $('asset_id');
    els.shotType = $('shot_type');
    els.duration = $('duration_s');
    els.environmentHint = $('environment_hint');
    els.lightingHint = $('lighting_hint');
    els.tenantId = $('tenant_id');
    els.userId = $('user_id');
    els.projectId = $('project_id');
    els.engineTarget = $('engine_target');
    els.renderMode = $('render_mode');
    els.streamProfile = $('stream_profile');
    els.usageScope = $('usage_scope');
    els.previewBtn = $('preview-btn');
    els.submitBtn = $('submit-btn');
    els.jobId = $('job-id');
    els.jobStatus = $('job-status');
    els.stageList = $('stage-list');
    els.executionRoute = $('execution-route');
    els.previewWarnings = $('preview-warnings');
    els.promptPreview = $('prompt-preview');
    els.jobResult = $('job-result');
    els.contextSummary = $('context-summary');
    els.schedulePanel = $('schedule-panel');
    els.monitorPanel = $('monitor-panel');
    els.rightsPanel = $('rights-panel');
    els.billingPanel = $('billing-panel');
    els.opsPanel = $('ops-panel');
    els.metricsGrid = $('metrics-grid');
    els.modelGrid = $('model-grid');
  }

  function renderMetrics(metrics) {
    if (!els.metricsGrid) return;
    els.metricsGrid.innerHTML = (metrics || []).map(function (metric) {
      return '<article class="metric-card"><strong>' + escapeHtml(metric.value) + '</strong><span>' + escapeHtml(metric.title) + '</span><p>' + escapeHtml(metric.description) + '</p></article>';
    }).join('');
  }

  function renderModels(models) {
    if (!els.modelGrid) return;
    els.modelGrid.innerHTML = (models || []).map(function (model) {
      return '<article class="model-card"><header><h3>' + escapeHtml(model.display_model) + '</h3><span class="route-badge">' + escapeHtml(model.route_mode || 'native') + '</span></header><p>' + escapeHtml(model.description || '') + '</p></article>';
    }).join('');
  }

  function initializeSelects() {
    populateSelect(els.venueType, state.bootstrap.venue_catalog || [], function (venue) { return venue.name + ' · ' + (venue.hero_title || ''); }, ((state.bootstrap.venue_catalog || [])[0] || {}).id);
    populateSelect(els.aiModel, state.bootstrap.model_catalog || [], function (model) { return model.display_model + ' · ' + (model.route_mode || 'native'); }, ((state.bootstrap.model_catalog || [])[0] || {}).id);
    populateSelect(els.shotType, state.bootstrap.shot_catalog || [], function (shot) { return shot.label; }, ((state.bootstrap.shot_catalog || [])[0] || {}).id);
    populateSelect(els.engineTarget, state.bootstrap.engine_catalog || [], function (item) { return item.label; }, ((state.bootstrap.engine_catalog || [])[0] || {}).id);
    populateSelect(els.streamProfile, state.bootstrap.stream_profile_catalog || [], function (item) { return item.label; }, ((state.bootstrap.stream_profile_catalog || [])[1] || (state.bootstrap.stream_profile_catalog || [])[0] || {}).id);
    populateSelect(els.tenantId, state.demoContext ? [state.demoContext.tenant] : [], function (item) { return item.name; }, state.demoContext && state.demoContext.tenant && state.demoContext.tenant.id);
    populateSelect(els.userId, (state.demoContext && state.demoContext.available_users) || [], function (item) { return item.name + ' · ' + (item.role || ''); }, state.demoContext && state.demoContext.user && state.demoContext.user.id);
    populateSelect(els.projectId, (state.demoContext && state.demoContext.available_projects) || [], function (item) { return item.name; }, state.demoContext && state.demoContext.project && state.demoContext.project.id);
  }

  async function loadAssetLibrary() {
    var grid = document.getElementById('asset-grid');
    if (!grid) return;
    var typeLabels = {
      glb: '3D模型', image: '图片', video: '视频', audio: '音频',
      document: '文档', archive: '压缩包', spatial_anchor: '空间锚点'
    };
    try {
      var data = await api('/api/assets?limit=6');
      var items = (data && data.items) || [];
      if (!items.length) {
        grid.innerHTML = '<div class="empty-state-container">' +
          '<h3 class="empty-title">素材库还是空的</h3>' +
          '<p class="empty-desc">在素材库上传文件，或从创意工作台生成第一张图片。</p>' +
          '<a class="btn-outline btn-sm" href="/assets">前往素材库</a></div>';
        return;
      }
      grid.innerHTML = items.map(function (asset) {
        var typeLabel = typeLabels[asset.asset_type] || asset.asset_type || '素材';
        return '<a class="asset-card" href="/assets" style="text-decoration:none;color:inherit;display:block;">' +
          '<header><h3>' + escapeHtml(asset.name) + '</h3>' +
          '<span class="route-badge">' + escapeHtml(typeLabel) + '</span></header>' +
          '<p>' + escapeHtml(asset.description || '暂无描述') + '</p>' +
          '<div class="meta-tag">' + escapeHtml(window.AIGV.formatTime(asset.created_at)) + '</div>' +
          '</a>';
      }).join('');
    } catch (err) {
      grid.innerHTML = '<div class="empty-state-container">' +
        '<h3 class="empty-title">素材加载失败</h3>' +
        '<p class="empty-desc">' + escapeHtml(err.message || '请稍后重试') + '</p></div>';
    }
  }

  async function bootstrap() {
    cacheElements();
    bindEvents();
    syncActionStates();
    setUiStatus('loading', '正在加载项目知识库...');
    try {
      state.bootstrap = await api('/api/bootstrap');
      state.demoContext = await api('/api/demo/context');
      renderModels(state.bootstrap.model_catalog || []);
      initializeSelects();
      applyVenueDefaults();
      renderJob(null);
      await Promise.all([previewPrompt({ silent: true }), loadAssetLibrary()]);
      setUiStatus('ready', '工作台就绪，请配置场景参数后提交任务。');
    } catch (err) {
      setUiStatus('error', '初始化失败：' + err.message);
    }
  }

  bootstrap();
})();
