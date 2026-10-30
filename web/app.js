(function () {
  'use strict';

  var LAST_TASK_KEY = 'aigv_workbench_last_task_v1';
  var ACTIVE_STATUSES = ['queued', 'submitting', 'running'];
  var PREVIEW_MODEL_MAP = {
    ark_seedance_25: 'ark_seedance_25',
    ark_seedance_20: 'ark_seedance_20',
    ark_seedance_10_pro: 'ark_seedance_25',
    atlas_seedance_default: 'seedance_pro',
    luma_default: 'luma_optional'
  };

  var state = {
    bootstrap: null,
    models: [],
    selectedModel: null,
    lastPreview: null,
    currentTask: null,
    currentTaskId: null,
    pollTimer: null,
    pollSeq: 0,
    previewSeq: 0,
    submitSeq: 0,
    previewing: false,
    submitting: false,
    previousVenue: null,
    demoMode: false,
    refreshedTaskId: null
  };

  var els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function api(path, options) {
    return window.AIGV.api(path, options || {});
  }

  function setStatus(tone, message) {
    if (!els.jobStatus) return;
    els.jobStatus.textContent = message || '';
    els.jobStatus.setAttribute('data-status-tone', tone || 'ready');
  }

  function updateActionState() {
    var busy = state.previewing || state.submitting;
    if (els.previewBtn) els.previewBtn.disabled = busy;
    if (els.submitBtn) {
      els.submitBtn.disabled = busy || !state.selectedModel ||
        !state.selectedModel.available;
    }
  }

  function setPreviewing(value) {
    state.previewing = value;
    updateActionState();
  }

  function setSubmitting(value) {
    state.submitting = value;
    updateActionState();
  }

  function populateSelect(selectEl, values, formatter, selectedValue) {
    if (!selectEl) return;
    selectEl.innerHTML = '';
    (values || []).forEach(function (value) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = formatter ? formatter(value) : String(value);
      if (selectedValue !== undefined && String(selectedValue) === String(value)) {
        option.selected = true;
      }
      selectEl.appendChild(option);
    });
  }

  function findModel(key) {
    for (var i = 0; i < state.models.length; i += 1) {
      if (state.models[i].key === key) return state.models[i];
    }
    return null;
  }

  function findVenue(id) {
    var venues = (state.bootstrap && state.bootstrap.venue_catalog) || [];
    for (var i = 0; i < venues.length; i += 1) {
      if (venues[i].id === id) return venues[i];
    }
    return null;
  }

  function previewModelKey(key) {
    return PREVIEW_MODEL_MAP[key] || key;
  }

  function randomRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    return 'wb-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  }

  function saveLastTask(taskId) {
    try {
      if (taskId) window.localStorage.setItem(LAST_TASK_KEY, taskId);
    } catch (e) {
      // localStorage can be unavailable in private mode; polling still works.
    }
  }

  function clearLastTask() {
    try {
      window.localStorage.removeItem(LAST_TASK_KEY);
    } catch (e) {
      // ignore
    }
  }

  function readLastTask() {
    try {
      return window.localStorage.getItem(LAST_TASK_KEY);
    } catch (e) {
      return null;
    }
  }

  function loadBootstrap() {
    return api('/api/bootstrap').then(function (data) {
      state.bootstrap = data || {};
      populateSelect(
        els.venueType,
        (state.bootstrap.venue_catalog || []).map(function (venue) { return venue.id; }),
        function (id) {
          var venue = findVenue(id);
          return venue ? (venue.name + ' · ' + (venue.hero_title || '')) : id;
        },
        ((state.bootstrap.venue_catalog || [])[0] || {}).id
      );
      populateSelect(
        els.shotType,
        (state.bootstrap.shot_catalog || []).map(function (shot) { return shot.id; }),
        function (id) {
          var shots = state.bootstrap.shot_catalog || [];
          for (var i = 0; i < shots.length; i += 1) {
            if (shots[i].id === id) return shots[i].label || id;
          }
          return id;
        },
        ((state.bootstrap.shot_catalog || [])[0] || {}).id
      );
    });
  }

  function loadModels() {
    return api('/api/generation/models?task_type=video').then(function (data) {
      state.models = (data && data.items) || [];
      var available = state.models.filter(function (model) { return model.available; });
      var preferred = null;
      for (var i = 0; i < available.length; i += 1) {
        if (available[i].default) { preferred = available[i]; break; }
      }
      if (!preferred) preferred = available[0] || state.models[0] || null;

      populateSelect(
        els.modelKey,
        state.models.map(function (model) { return model.key; }),
        function (key) {
          var model = findModel(key);
          if (!model) return key;
          return model.display_name + ' · ' + (model.model_id || '—') +
            (model.available ? '' : '（未配置）');
        },
        preferred ? preferred.key : ''
      );
      state.selectedModel = preferred;
      renderReadiness();
      renderCapabilityControls();
      renderModelGrid();
    });
  }

  function renderModelGrid() {
    if (!els.modelGrid) return;
    if (!state.models.length) {
      els.modelGrid.innerHTML = '<p class="empty-state">尚未接入视频生成模型。</p>';
      return;
    }
    els.modelGrid.innerHTML = state.models.map(function (model) {
      var caps = model.capabilities || {};
      var details = [];
      if (caps.duration_range) {
        details.push('时长 ' + caps.duration_range[0] + '-' + caps.duration_range[1] + 's');
      } else if (caps.durations && caps.durations.length) {
        details.push('时长 ' + caps.durations.join('/') + 's');
      }
      if (caps.resolutions && caps.resolutions.length) {
        details.push('分辨率 ' + caps.resolutions.join('/'));
      }
      details.push(caps.supports_audio ? '支持音频' : '无音频');
      var statusText = model.available ? '可用' : '未配置';
      var statusClass = model.available ? 'native' : 'preview-only';
      return '<article class="model-card">' +
        '<header><h3>' + escapeHtml(model.display_name || model.key) + '</h3>' +
        '<span class="route-badge ' + statusClass + '">' + statusText + '</span></header>' +
        '<p>' + escapeHtml(model.model_id || '—') + ' · ' + escapeHtml(model.provider || '') + '</p>' +
        '<p>' + escapeHtml(details.join(' · ')) + '</p>' +
        (model.available ? '' : '<p class="field-hint">' +
          escapeHtml(model.unavailable_reason || '请在 API 配置中保存密钥') + '</p>') +
        '</article>';
    }).join('');
  }

  function renderReadiness() {
    if (!els.readinessBanner) return;
    var available = state.models.filter(function (model) { return model.available; });
    var parts = [];
    if (state.demoMode) {
      parts.push('<strong class="content-note-title">演示模式</strong>');
      parts.push('<p class="content-note-desc">当前实例启用了演示标识；真实生成仍取决于服务商凭据和模型开通状态。</p>');
    }
    if (!state.models.length) {
      parts.push('<strong class="content-note-title">尚未接入视频模型</strong>');
      parts.push('<p class="content-note-desc">请在 <a class="field-hint-link" href="/api-settings">API 配置</a> 中配置火山方舟或其他视频服务商。</p>');
    } else if (!available.length) {
      var reasons = state.models.map(function (model) {
        return '<li>' + escapeHtml(model.display_name || model.key) + '：' +
          escapeHtml(model.unavailable_reason || '未配置凭据') + '</li>';
      }).join('');
      parts.push('<strong class="content-note-title">没有可用的视频模型</strong>');
      parts.push('<p class="content-note-desc">请先在 <a class="field-hint-link" href="/api-settings">API 配置</a> 中保存密钥。</p>');
      parts.push('<ul class="field-hint">' + reasons + '</ul>');
    } else {
      parts.push('<strong class="content-note-title">已配置 ' + available.length + ' 个视频模型</strong>');
      parts.push('<p class="content-note-desc">“可用”只表示凭据已配置，不代表模型已在服务商控制台开通；提交后以真实结果为准。</p>');
    }
    els.readinessBanner.innerHTML = parts.join('');
    els.readinessBanner.hidden = !parts.length;
  }

  function applyVenueDefaults(force) {
    var venue = findVenue(els.venueType ? els.venueType.value : '');
    if (!venue) return;
    var previous = state.previousVenue;
    var currentEnv = els.environmentHint ? els.environmentHint.value : '';
    var currentLight = els.lightingHint ? els.lightingHint.value : '';
    var envIsAuto = !currentEnv || (previous && currentEnv === previous.default_environment);
    var lightIsAuto = !currentLight || (previous && currentLight === previous.default_lighting);
    if (force || envIsAuto) {
      els.environmentHint.value = venue.default_environment || '';
    }
    if (force || lightIsAuto) {
      els.lightingHint.value = venue.default_lighting || '';
    }
    state.previousVenue = venue;
  }

  function selectedCapabilities() {
    return (state.selectedModel && state.selectedModel.capabilities) || {};
  }

  function durationValues(caps) {
    if (caps.durations && caps.durations.length) return caps.durations.slice();
    if (caps.duration_range && caps.duration_range.length === 2) {
      var values = [];
      for (var i = caps.duration_range[0]; i <= caps.duration_range[1]; i += 1) {
        values.push(i);
      }
      return values;
    }
    return [5];
  }

  function renderCapabilityControls() {
    var caps = selectedCapabilities();
    var durations = durationValues(caps);
    var currentDuration = els.duration ? parseInt(els.duration.value, 10) : NaN;
    var duration = durations.indexOf(currentDuration) >= 0
      ? currentDuration
      : (durations.indexOf(5) >= 0 ? 5 : durations[0]);
    populateSelect(
      els.duration,
      durations,
      function (value) { return value + 's'; },
      duration
    );

    var ratios = caps.ratios || ['16:9'];
    var currentRatio = els.ratio ? els.ratio.value : '';
    var ratio = ratios.indexOf(currentRatio) >= 0
      ? currentRatio : (ratios.indexOf('16:9') >= 0 ? '16:9' : ratios[0]);
    populateSelect(els.ratio, ratios, null, ratio);

    var resolutions = caps.resolutions || ['720p'];
    var currentResolution = els.resolution ? els.resolution.value : '';
    var resolution = resolutions.indexOf(currentResolution) >= 0
      ? currentResolution
      : (resolutions.indexOf('720p') >= 0 ? '720p' : resolutions[0]);
    populateSelect(els.resolution, resolutions, null, resolution);

    if (els.audioGroup) els.audioGroup.hidden = !caps.supports_audio;
    if (els.generateAudio) {
      els.generateAudio.checked = !!caps.default_audio;
      els.generateAudio.disabled = !caps.supports_audio;
    }
    if (els.seedGroup) els.seedGroup.hidden = !caps.supports_seed;
    if (els.seed && !caps.supports_seed) els.seed.value = '';

    if (els.modelHint) {
      if (!state.selectedModel) {
        els.modelHint.textContent = '没有可用的视频模型，请先配置 API。';
      } else {
        var model = state.selectedModel;
        var range = caps.duration_range
          ? (caps.duration_range[0] + '-' + caps.duration_range[1] + 's')
          : (durationValues(caps).join('/') + 's');
        var reference = caps.max_reference_images
          ? ('最多 ' + caps.max_reference_images + ' 张参考图')
          : '不支持参考图';
        els.modelHint.innerHTML =
          '实际调用：<strong>' + escapeHtml(model.model_id || '—') + '</strong>' +
          ' · ' + escapeHtml(model.provider || '—') +
          ' · 时长 ' + escapeHtml(range) +
          ' · 分辨率 ' + escapeHtml((caps.resolutions || []).join('/')) +
          ' · ' + escapeHtml(reference);
        if (!model.available) {
          els.modelHint.innerHTML += ' · <span class="field-hint">' +
            escapeHtml(model.unavailable_reason || '未配置凭据') + '</span>';
        }
      }
    }
    updateActionState();
  }

  function renderWarnings(warnings) {
    if (!els.previewWarnings) return;
    if (!warnings || !warnings.length) {
      els.previewWarnings.innerHTML = '';
      els.previewWarnings.className = 'warning-stack warning-stack-inline';
      return;
    }
    els.previewWarnings.className = 'warning-stack';
    els.previewWarnings.innerHTML = warnings.map(function (warning) {
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

  function renderPromptPreview(data) {
    if (!els.promptPreview) return;
    if (!data || !data.prompt_bundle) {
      els.promptPreview.innerHTML = '<p class="empty-state">选择场馆和模型后生成 Prompt 预览</p>';
      if (els.executionRoute) els.executionRoute.textContent = '未生成';
      renderWarnings([]);
      return;
    }
    state.lastPreview = data;
    var bundle = data.prompt_bundle || {};
    var model = state.selectedModel || {};
    if (els.executionRoute) {
      els.executionRoute.textContent = (model.display_name || bundle.display_model || '未指定') +
        ' · ' + (model.model_id || '') + ' → ' + (model.provider || '') + ' · 真实生成';
    }
    renderWarnings(data.warnings || []);
    var html = '<section class="preview-block"><h4>六模块 Prompt</h4>' +
      renderModuleCards(bundle.modules || {}) + '</section>' +
      '<section class="preview-block"><div class="preview-heading"><h4>最终 Prompt</h4>' +
      '<span class="preview-chip">text_to_video</span></div>' +
      '<p class="text-block prompt-output">' + escapeHtml(bundle.prompt) + '</p></section>';
    if (bundle.negative_prompt) {
      html += '<section class="preview-block"><h4>负向 Prompt</h4>' +
        '<p class="text-block">' + escapeHtml(bundle.negative_prompt) + '</p></section>';
    }
    els.promptPreview.innerHTML = html;
  }

  function collectPreviewPayload() {
    var model = state.selectedModel || {};
    return {
      venue_type: els.venueType ? els.venueType.value : '',
      shot_type: els.shotType ? els.shotType.value : '',
      ai_model: previewModelKey(model.key || ''),
      asset_id: 'text_only',
      workflow_mode: 'text_to_video',
      include_engine_context: false,
      duration_s: els.duration ? parseInt(els.duration.value, 10) : 5,
      environment_hint: els.environmentHint ? els.environmentHint.value : '',
      lighting_hint: els.lightingHint ? els.lightingHint.value : ''
    };
  }

  function previewPrompt(options) {
    options = options || {};
    var silent = !!options.silent;
    if (!state.selectedModel) return Promise.resolve(null);
    state.previewSeq += 1;
    var sequence = state.previewSeq;
    setPreviewing(true);
    if (!silent) setStatus('previewing', '正在生成 Prompt 预览...');
    return api('/api/prompt/preview', {
      method: 'POST',
      body: collectPreviewPayload()
    }).then(function (data) {
      if (sequence !== state.previewSeq) return null;
      renderPromptPreview(data);
      if (!silent) setStatus('ready', 'Prompt 预览已更新。');
      return data;
    }).catch(function (error) {
      if (sequence !== state.previewSeq) return null;
      renderWarnings([(error && error.message) || 'Prompt 预览失败']);
      setStatus('error', 'Prompt 预览失败：' + ((error && error.message) || '请稍后重试'));
      throw error;
    }).finally(function () {
      if (sequence === state.previewSeq) setPreviewing(false);
    });
  }

  function buildGenerationPayload(preview) {
    var model = state.selectedModel;
    var caps = selectedCapabilities();
    var payload = {
      model_key: model.key,
      prompt: preview.prompt_bundle.prompt,
      ratio: els.ratio ? els.ratio.value : '16:9',
      duration_s: els.duration ? parseInt(els.duration.value, 10) : 5,
      resolution: els.resolution ? els.resolution.value : '720p',
      watermark: false,
      client_request_id: randomRequestId()
    };
    if (caps.supports_audio && els.generateAudio) {
      payload.generate_audio = !!els.generateAudio.checked;
    }
    if (caps.supports_seed && els.seed && els.seed.value !== '') {
      var seed = parseInt(els.seed.value, 10);
      if (!isNaN(seed)) payload.seed = seed;
    }
    return payload;
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (state.submitting) return;
    if (!state.selectedModel || !state.selectedModel.available) {
      setStatus('error', '没有可用的视频模型，请先在 API 配置中保存密钥。');
      return;
    }
    state.submitSeq += 1;
    var sequence = state.submitSeq;
    setSubmitting(true);
    setStatus('submitting', '正在准备 Prompt 并创建真实任务...');
    previewPrompt({ silent: true }).then(function (preview) {
      if (sequence !== state.submitSeq) return null;
      if (!preview || !preview.prompt_bundle || !preview.prompt_bundle.prompt) {
        throw new Error('Prompt 预览不可用，请先点击“预览 Prompt”检查。');
      }
      return api('/api/generation/videos', {
        method: 'POST',
        body: buildGenerationPayload(preview)
      });
    }).then(function (task) {
      if (!task || sequence !== state.submitSeq) return;
      state.currentTask = task;
      state.currentTaskId = task.id;
      saveLastTask(task.id);
      renderTask(task);
      startPolling(task.id);
      setStatus('polling', '任务已创建，正在生成视频...');
    }).catch(function (error) {
      var message = (error && error.message) || '创建任务失败';
      setStatus('error', '创建任务失败：' + message);
      renderSubmitError(error);
    }).finally(function () {
      setSubmitting(false);
    });
  }

  function renderSubmitError(error) {
    if (!els.jobResult) return;
    var html = '<div class="result-block result-block-error"><h4>提交失败</h4>' +
      '<p class="text-block">' + escapeHtml((error && error.message) || '请稍后重试') + '</p>';
    var code = error && error.code;
    if (code === 'provider_not_configured' || code === 'model_not_activated' ||
        code === 'provider_credential_missing') {
      html += '<p class="field-hint"><a class="field-hint-link" href="/api-settings">前往 API 配置</a></p>';
    }
    html += '<p class="field-hint"><a class="field-hint-link" href="/assets?tab=history">到生成历史确认是否已创建任务</a></p></div>';
    els.jobResult.innerHTML = html;
  }

  function clearPoll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function startPolling(taskId) {
    clearPoll();
    state.currentTaskId = taskId;
    state.pollSeq += 1;
    var sequence = state.pollSeq;
    var poll = function () {
      api('/api/generation/tasks/' + encodeURIComponent(taskId)).then(function (task) {
        if (sequence !== state.pollSeq || !task) return;
        state.currentTask = task;
        renderTask(task);
        if (task.status === 'succeeded' || task.status === 'failed' ||
            task.status === 'cancelled' || task.status === 'needs_review') {
          clearPoll();
          if (task.status === 'succeeded') {
            setStatus('success', '视频生成完成，已保存到素材库。');
          } else if (task.status === 'failed') {
            setStatus('error', '生成失败：' + (task.error_message || task.error_code || '请查看结果'));
          } else if (task.status === 'needs_review') {
            setStatus('error', '任务需人工确认，请到生成历史查看。');
          } else {
            setStatus('ready', '任务已取消。');
          }
        }
      }).catch(function (error) {
        if (sequence !== state.pollSeq) return;
        if (error && error.status === 404) {
          clearLastTask();
          clearPoll();
        }
        setStatus('error', '状态查询失败：' + ((error && error.message) || '请稍后重试'));
      });
    };
    poll();
    state.pollTimer = setInterval(poll, 3000);
  }

  function statusLabel(status) {
    var labels = {
      queued: '已排队',
      submitting: '提交中',
      running: '生成中',
      succeeded: '已完成',
      failed: '生成失败',
      cancelled: '已取消',
      needs_review: '需人工确认'
    };
    return labels[status] || status || '未知状态';
  }

  function renderStages(task) {
    if (!els.stageList) return;
    var stages = [
      { label: '任务已创建' },
      { label: '提交模型' },
      { label: '模型生成中' },
      { label: '完成' }
    ];
    var status = task ? task.status : 'queued';
    var classes = ['pending', 'pending', 'pending', 'pending'];
    if (status === 'queued') {
      classes[0] = 'active';
    } else if (status === 'submitting') {
      classes[0] = 'done';
      classes[1] = 'active';
    } else if (status === 'running') {
      classes[0] = 'done';
      classes[1] = 'done';
      classes[2] = 'active';
    } else if (status === 'succeeded') {
      classes = ['done', 'done', 'done', 'done'];
    } else if (status === 'failed') {
      classes = ['done', 'done', 'error', 'pending'];
    } else if (status === 'cancelled') {
      classes = ['done', 'done', 'pending', 'pending'];
    } else if (status === 'needs_review') {
      classes = ['done', 'done', 'done', 'error'];
    }
    els.stageList.innerHTML = stages.map(function (stage, index) {
      return '<li class="' + classes[index] + '"><span>' + escapeHtml(stage.label) + '</span></li>';
    }).join('');
  }

  function renderTaskMeta(task) {
    if (!els.taskMeta) return;
    if (!task) {
      els.taskMeta.innerHTML = '';
      return;
    }
    var params = task.params || {};
    var items = [
      ['模型 ID', task.model_id || params.model_key || '—'],
      ['Provider', task.provider || '—'],
      ['时长', (params.duration_s || '—') + 's'],
      ['分辨率', params.resolution || '—'],
      ['比例', params.ratio || '—'],
      ['创建时间', window.AIGV.formatTime(task.created_at)]
    ];
    if (task.error_code) items.push(['错误码', task.error_code]);
    els.taskMeta.innerHTML = '<ul class="meta-list">' + items.map(function (item) {
      return '<li><strong>' + escapeHtml(item[0]) + '：</strong>' + escapeHtml(item[1]) + '</li>';
    }).join('') + '</ul>';
  }

  function resultMetaList(items) {
    return '<ul class="meta-list">' + items.map(function (item) {
      return '<li><strong>' + escapeHtml(item[0]) + '：</strong>' + escapeHtml(item[1]) + '</li>';
    }).join('') + '</ul>';
  }

  function renderTaskResult(task) {
    if (!els.jobResult) return;
    if (!task) {
      els.jobResult.innerHTML = '<p class="empty-state">任务完成后在此播放视频；结果会自动保存到素材库。</p>';
      return;
    }
    var status = task.status;
    var blocks = [];
    if (status === 'succeeded') {
      var asset = task.output_asset;
      if (asset && asset.id) {
        var fileUrl = '/api/assets/' + encodeURIComponent(asset.id) + '/file';
        var downloadUrl = '/api/assets/' + encodeURIComponent(asset.id) + '/download';
        blocks.push('<div class="result-block result-block-video"><h4>视频结果</h4>' +
          '<video class="result-video" controls preload="metadata"><source src="' +
          escapeHtml(fileUrl) + '" type="video/mp4" /></video>' +
          '<p class="field-hint" data-video-fallback hidden>视频加载失败，请尝试下载。</p>' +
          '<div class="action-buttons"><a class="btn-primary btn-sm" href="' +
          escapeHtml(downloadUrl) + '">下载视频</a>' +
          '<a class="btn-outline btn-sm" href="/assets?tab=history">查看生成历史</a></div>' +
          '<p class="field-hint">结果已保存到素材库。</p></div>');
      } else {
        blocks.push('<div class="result-block result-block-error"><h4>生成结果未入库</h4>' +
          '<p class="text-block">服务商返回成功，但本地没有可播放的输出。请到生成历史或素材库检查。</p></div>');
      }
    } else if (status === 'failed') {
      var errorHtml = '<div class="result-block result-block-error"><h4>生成失败</h4>' +
        '<p class="text-block">' + escapeHtml(task.error_message || '服务商未返回可用结果') + '</p>';
      if (task.error_code) {
        errorHtml += '<p class="field-hint">错误码：' + escapeHtml(task.error_code) + '</p>';
      }
      if (task.error_code && (task.error_code.indexOf('model') >= 0 ||
          task.error_code.indexOf('provider_auth') >= 0 ||
          task.error_code.indexOf('credential') >= 0)) {
        errorHtml += '<p class="field-hint"><a class="field-hint-link" href="/api-settings">前往 API 配置检查密钥与模型</a></p>';
      }
      errorHtml += '<p class="field-hint"><a class="field-hint-link" href="/assets?tab=history">查看生成历史</a></p></div>';
      blocks.push(errorHtml);
    } else if (status === 'needs_review') {
      blocks.push('<div class="result-block result-block-error"><h4>需人工确认</h4>' +
        '<p class="text-block">提交结果不确定，请到生成历史确认服务商是否已创建任务，避免重复付费。</p></div>');
    } else if (status === 'cancelled') {
      blocks.push('<div class="result-block"><h4>任务已取消</h4>' +
        '<p class="text-block">已请求取消；若服务商已开始执行，仍可能产生费用。</p></div>');
    } else {
      blocks.push('<div class="result-block"><h4>正在生成</h4>' +
        '<p class="text-block">当前状态：' + escapeHtml(statusLabel(status)) +
        '。完成后会自动显示视频并保存到素材库。</p></div>');
    }
    els.jobResult.innerHTML = blocks.join('');
    var video = els.jobResult.querySelector('video');
    if (video) {
      video.addEventListener('error', function () {
        var fallback = els.jobResult.querySelector('[data-video-fallback]');
        if (fallback) fallback.hidden = false;
      });
    }
  }

  function renderTask(task) {
    state.currentTask = task || null;
    if (els.jobId) els.jobId.textContent = task ? task.id : '尚未提交';
    renderStages(task);
    renderTaskMeta(task);
    renderTaskResult(task);
    var active = task && ACTIVE_STATUSES.indexOf(task.status) >= 0;
    if (els.cancelBtn) els.cancelBtn.hidden = !active;
    if (task && task.status === 'succeeded' && state.refreshedTaskId !== task.id) {
      state.refreshedTaskId = task.id;
      loadRecentAssets();
    }
  }

  function cancelTask() {
    if (!state.currentTask || ACTIVE_STATUSES.indexOf(state.currentTask.status) < 0) return;
    els.cancelBtn.disabled = true;
    api('/api/generation/tasks/' + encodeURIComponent(state.currentTask.id) + '/cancel', {
      method: 'POST'
    }).then(function () {
      setStatus('polling', '已请求取消，等待服务商确认...');
    }).catch(function (error) {
      setStatus('error', '取消失败：' + ((error && error.message) || '请稍后重试'));
    }).finally(function () {
      els.cancelBtn.disabled = false;
    });
  }

  function resumeLastTask() {
    var taskId = readLastTask();
    if (!taskId) return Promise.resolve();
    return api('/api/generation/tasks/' + encodeURIComponent(taskId)).then(function (task) {
      if (!task) return;
      state.currentTaskId = task.id;
      renderTask(task);
      if (ACTIVE_STATUSES.indexOf(task.status) >= 0) {
        startPolling(task.id);
        setStatus('polling', '正在恢复上次任务的进度...');
      } else if (task.status === 'succeeded') {
        setStatus('success', '已恢复上次任务：视频生成完成，结果已保存到素材库。');
      } else if (task.status === 'failed') {
        setStatus('error', '上次任务生成失败：' + (task.error_message || task.error_code || '请查看结果'));
      } else if (task.status === 'needs_review') {
        setStatus('error', '上次任务需人工确认，请到生成历史查看。');
      } else if (task.status === 'cancelled') {
        setStatus('ready', '上次任务已取消。');
      }
    }).catch(function (error) {
      if (error && (error.status === 403 || error.status === 404)) clearLastTask();
    });
  }

  function loadRecentAssets() {
    if (!els.assetGrid) return Promise.resolve();
    var typeLabels = {
      glb: '3D模型', image: '图片', video: '视频', audio: '音频',
      document: '文档', archive: '压缩包', spatial_anchor: '空间锚点'
    };
    return api('/api/assets?limit=6').then(function (data) {
      var items = (data && data.items) || [];
      if (!items.length) {
        els.assetGrid.innerHTML = '<div class="empty-state-container">' +
          '<h3 class="empty-title">素材库还是空的</h3>' +
          '<p class="empty-desc">生成第一条视频后，结果会自动出现在这里。</p>' +
          '<a class="btn-outline btn-sm" href="/assets">前往素材库</a></div>';
        return;
      }
      els.assetGrid.innerHTML = items.map(function (asset) {
        var typeLabel = typeLabels[asset.asset_type] || asset.asset_type || '素材';
        return '<a class="asset-card" href="/assets" style="text-decoration:none;color:inherit;display:block;">' +
          '<header><h3>' + escapeHtml(asset.name) + '</h3>' +
          '<span class="route-badge">' + escapeHtml(typeLabel) + '</span></header>' +
          '<p>' + escapeHtml(asset.description || '暂无描述') + '</p>' +
          '<div class="meta-tag">' + escapeHtml(window.AIGV.formatTime(asset.created_at)) + '</div>' +
          '</a>';
      }).join('');
    }).catch(function () {
      els.assetGrid.innerHTML = '<div class="empty-state-container">' +
        '<h3 class="empty-title">素材加载失败</h3>' +
        '<p class="empty-desc">请稍后刷新重试。</p></div>';
    });
  }

  function bindEvents() {
    if (els.form) els.form.addEventListener('submit', handleSubmit);
    if (els.previewBtn) {
      els.previewBtn.addEventListener('click', function () {
        previewPrompt({ silent: false }).catch(function () {});
      });
    }
    if (els.cancelBtn) els.cancelBtn.addEventListener('click', cancelTask);
    if (els.venueType) {
      els.venueType.addEventListener('change', function () {
        applyVenueDefaults(false);
        previewPrompt({ silent: true }).catch(function () {});
      });
    }
    if (els.modelKey) {
      els.modelKey.addEventListener('change', function () {
        state.selectedModel = findModel(els.modelKey.value);
        renderReadiness();
        renderCapabilityControls();
        previewPrompt({ silent: true }).catch(function () {});
      });
    }
    ['shotType', 'duration', 'ratio', 'resolution', 'generateAudio', 'seed',
      'environmentHint', 'lightingHint'].forEach(function (key) {
      if (!els[key]) return;
      els[key].addEventListener('change', function () {
        previewPrompt({ silent: true }).catch(function () {});
      });
    });
  }

  function cacheElements() {
    els.workspace = $('workspace');
    els.form = $('job-form');
    els.venueType = $('venue_type');
    els.shotType = $('shot_type');
    els.modelKey = $('model_key');
    els.modelHint = $('model-hint');
    els.duration = $('duration_s');
    els.ratio = $('ratio');
    els.resolution = $('resolution');
    els.audioGroup = $('audio-group');
    els.generateAudio = $('generate_audio');
    els.seedGroup = $('seed-group');
    els.seed = $('seed');
    els.environmentHint = $('environment_hint');
    els.lightingHint = $('lighting_hint');
    els.previewBtn = $('preview-btn');
    els.submitBtn = $('submit-btn');
    els.submitHint = $('submit-hint');
    els.jobId = $('job-id');
    els.jobStatus = $('job-status');
    els.stageList = $('stage-list');
    els.taskMeta = $('task-meta');
    els.cancelBtn = $('cancel-btn');
    els.executionRoute = $('execution-route');
    els.previewWarnings = $('preview-warnings');
    els.promptPreview = $('prompt-preview');
    els.jobResult = $('job-result');
    els.readinessBanner = $('readiness-banner');
    els.assetGrid = $('asset-grid');
    els.modelGrid = $('model-grid');
  }

  function bootstrap() {
    cacheElements();
    bindEvents();
    state.demoMode = !!(window.AIGV_RUNTIME && window.AIGV_RUNTIME.demoMode);
    if (window.AIGV && typeof window.AIGV.getCurrentUser === 'function') {
      window.AIGV.getCurrentUser(true).then(function (user) {
        var capabilities = (user && user.capabilities) || {};
        if (capabilities.view_compute === false) {
          var cta = $('enterprise-cta');
          if (cta) cta.hidden = true;
        }
      }).catch(function () {});
    }
    setStatus('loading', '正在加载场馆与模型...');
    updateActionState();
    loadBootstrap().then(loadModels).then(function () {
      applyVenueDefaults(true);
      renderTask(null);
      return previewPrompt({ silent: true }).catch(function () {});
    }).then(function () {
      return Promise.all([loadRecentAssets(), resumeLastTask()]);
    }).then(function () {
      if (state.currentTask) return;
      if (!state.selectedModel || !state.selectedModel.available) {
        setStatus('error', '没有可用的视频模型，请先在 API 配置中保存密钥。');
      } else if (state.lastPreview) {
        setStatus('ready', '选择场馆和模型后，先预览 Prompt。');
      }
    }).catch(function (error) {
      setStatus('error', '初始化失败：' + ((error && error.message) || '请刷新重试'));
      renderReadiness();
    });
  }

  bootstrap();
})();
