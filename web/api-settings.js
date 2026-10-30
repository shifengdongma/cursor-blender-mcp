/**
 * AIGV Studio - API 配置页
 * 每个 Provider 一张卡片，管理当前用户自己的加密 API 凭据。
 * 密钥只以掩码展示；明文仅存在于输入框与提交请求中，保存成功后立即清空。
 */
(function (global) {
  'use strict';

  var AIGV = global.AIGV;
  var cardsEl = document.getElementById('provider-cards');
  var statusEl = document.getElementById('api-settings-status');
  var loadingEl = document.getElementById('api-settings-loading');
  var transportWarningEl = document.getElementById('api-settings-transport-warning');
  var toastContainer = document.getElementById('api-settings-toast-container');

  var state = {
    catalog: [],
    items: {},
    generationModels: []
  };

  function esc(value) {
    return AIGV.escapeHtml(value);
  }

  function itemFor(provider) {
    return state.items[provider] || null;
  }

  function generationModelsFor(provider) {
    return (state.generationModels || []).filter(function (model) {
      return model && model.credential_provider === provider;
    });
  }

  function generationModelByKey(key) {
    var models = state.generationModels || [];
    for (var i = 0; i < models.length; i += 1) {
      if (models[i] && models[i].key === key) return models[i];
    }
    return null;
  }

  function modelSourceLabel(source) {
    if (source === 'user_override') return '个人覆盖';
    if (source === 'env_override') return '环境变量';
    return '注册表默认';
  }

  function keyStatusLabel(status) {
    if (status === 'verified') return '已验证';
    if (status === 'rejected') return '无效';
    if (status === 'unsupported') return '无法通过此方式验证';
    return '未验证';
  }

  function modelStatusLabel(status) {
    if (status === 'listed') return '已列出（不代表可调用）';
    if (status === 'not_listed') return '不在可见列表';
    if (status === 'succeeded') return '真实生图成功';
    if (status === 'accepted') return '已创建任务（未验证生成完成）';
    return '未测试';
  }

  function setTransportWarning() {
    if (!transportWarningEl) return;
    transportWarningEl.hidden = global.location.protocol === 'https:';
  }

  function showToast(message, type) {
    if (!toastContainer) return;
    var toast = document.createElement('div');
    var cls = type === 'error' ? 'toast-error' : (type === 'warning' ? 'toast-warning' : 'toast-success');
    toast.className = 'toast ' + cls;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3600);
  }

  function setStatus(message, type) {
    if (!statusEl) return;
    if (!message) {
      statusEl.hidden = true;
      statusEl.textContent = '';
      statusEl.className = 'api-settings-status';
      return;
    }
    statusEl.hidden = false;
    statusEl.className = 'api-settings-status is-' + (type || 'info');
    statusEl.textContent = message;
  }

  function setLoading(loading) {
    if (loadingEl) loadingEl.hidden = !loading;
  }

  function setCardMessage(card, message, type) {
    var el = card ? card.querySelector('[data-role="message"]') : null;
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = '';
      el.className = 'provider-message';
      return;
    }
    el.hidden = false;
    el.className = 'provider-message is-' + (type || 'info');
    el.textContent = message;
  }

  function setCardBusy(card, busy) {
    if (!card) return;
    card.classList.toggle('is-busy', !!busy);
    var controls = card.querySelectorAll('button, input, select');
    for (var i = 0; i < controls.length; i += 1) {
      var el = controls[i];
      el.disabled = busy ? true : el.getAttribute('data-always-disabled') === '1';
    }
  }

  function safeHref(value) {
    return /^https?:\/\//i.test(String(value || '')) ? value : '';
  }

  // ── Rendering ──

  function badgeFor(entry, item) {
    // `items` only contains providers with a personal row; when no row exists
    // the effective source is the platform default (if one is configured).
    var source = item ? item.source : (entry.platform_available ? 'platform' : null);
    if (source === 'user') {
      return { cls: 'is-user', text: '使用个人配置' };
    }
    if (source === 'platform') {
      return { cls: 'is-platform', text: '使用平台默认' };
    }
    return { cls: 'is-none', text: '未配置' };
  }

  function keyPlaceholder(entry, item) {
    if (!entry.requires_key) return '该 Provider 无需 API Key';
    if (item && item.key_unreadable) return '已保存但无法解密，请重新输入密钥';
    if (item && item.has_key && item.key_last4) {
      return '已保存（••••' + item.key_last4 + '），留空保持不变';
    }
    if (item && item.has_key) return '已保存（••••），留空保持不变';
    return '请输入 API Key';
  }

  function metaHtml(entry, item) {
    var parts = [];
    parts.push('平台默认：' + (entry.platform_available ? '可用' : '未配置'));
    if (item) {
      if (item.has_key && item.key_last4) {
        parts.push('个人密钥：••••' + item.key_last4);
      } else if (item.has_key) {
        parts.push('个人密钥：已保存');
      } else {
        parts.push('个人密钥：未保存');
      }
      if (item.last_verified_at) {
        parts.push('密钥验证于 ' + AIGV.formatTime(item.last_verified_at));
      }
      if (item.updated_at) {
        parts.push('更新于 ' + AIGV.formatTime(item.updated_at));
      }
    } else {
      parts.push('个人密钥：未保存');
    }
    return '<p class="provider-meta">' + esc(parts.join(' · ')) + '</p>';
  }

  function presetHtml(entry, item) {
    var presets = entry.presets || [];
    if (!presets.length) return '';
    var html = '<div class="form-group">';
    html += '<label for="preset-' + esc(entry.provider) + '">服务预设</label>';
    html += '<select id="preset-' + esc(entry.provider) + '" data-role="preset">';
    html += '<option value="">选择预设，自动填充 Base URL 与模型</option>';
    for (var i = 0; i < presets.length; i += 1) {
      var preset = presets[i] || {};
      var selected = item && item.base_url === preset.base_url && item.model === preset.model;
      html += '<option value="' + i + '"' + (selected ? ' selected' : '') + '>' +
        esc(preset.label || preset.base_url || ('预设 ' + (i + 1))) + '</option>';
    }
    html += '</select>';
    html += '</div>';
    return html;
  }

  function modelFieldsHtml(entry, item) {
    var fields = entry.model_fields || [];
    if (!fields.length) {
      return '<div class="form-group">' +
        '<label for="model-' + esc(entry.provider) + '">模型</label>' +
        '<input id="model-' + esc(entry.provider) + '" data-role="model" type="text" spellcheck="false"' +
        ' value="' + esc(item && item.model ? item.model : '') + '"' +
        ' placeholder="' + esc(entry.default_model || '平台默认模型') + '" />' +
        '</div>';
    }

    var overrides = (item && item.model_overrides && typeof item.model_overrides === 'object')
      ? item.model_overrides : {};
    var html = '<details class="provider-advanced">';
    html += '<summary>高级：模型 ID 覆盖（' + fields.length + ' 项，留空使用默认）</summary>';
    html += '<div class="provider-model-grid">';
    for (var i = 0; i < fields.length; i += 1) {
      var field = fields[i] || {};
      var fieldKey = String(field.key || '');
      if (!fieldKey) continue;
      var saved = overrides[fieldKey] ? String(overrides[fieldKey]) : '';
      html += '<div class="form-group">';
      html += '<label for="override-' + esc(entry.provider) + '-' + esc(fieldKey) + '">' + esc(field.label || fieldKey) + '</label>';
      html += '<input id="override-' + esc(entry.provider) + '-' + esc(fieldKey) + '"' +
        ' data-role="override" data-key="' + esc(fieldKey) + '" type="text" spellcheck="false"' +
        ' value="' + esc(saved) + '" placeholder="' + esc(field.default || '默认') + '" />';
      var modelInfo = generationModelByKey(fieldKey);
      var effectiveId = (modelInfo && modelInfo.model_id) || saved || field.default || '—';
      var source = modelSourceLabel(modelInfo && modelInfo.model_id_source);
      var verification = item && item.last_verification && item.last_verification[fieldKey];
      var verificationText = verification
        ? ' · 最近真实测试：' + (verification.status === 'succeeded' ? '生图成功' :
            (verification.status === 'accepted' ? '任务已创建' : verification.status)) +
          (verification.request_id ? '（请求 ID: ' + verification.request_id + '）' : '')
        : '';
      html += '<p class="field-hint">生效模型 ID：' + esc(effectiveId) +
        ' · 来源：' + esc(source) + esc(verificationText) + '</p>';
      html += '</div>';
    }
    html += '</div>';
    html += '</details>';
    return html;
  }

  function cardHtml(entry, item) {
    var provider = entry.provider;
    var badge = badgeFor(entry, item);
    var docsUrl = safeHref(entry.docs_url);
    var html = '<article class="provider-card provider-card-' + esc(badge.cls) + '" data-provider="' + esc(provider) + '">';

    html += '<div class="provider-card-header">';
    html += '<div class="provider-heading">';
    html += '<h2>' + esc(entry.name || provider) + '</h2>';
    html += '<span class="provider-protocol">' + esc(entry.protocol || provider) + '</span>';
    html += '</div>';
    html += '<span class="provider-badge ' + esc(badge.cls) + '">' + esc(badge.text) + '</span>';
    html += '</div>';

    html += '<p class="provider-description">' + esc(entry.description || '') + '</p>';
    html += metaHtml(entry, item);

    if (item && item.key_unreadable) {
      html += '<p class="provider-warning">已保存的密钥无法解密（可能加密密钥已更换），请重新输入密钥并保存。</p>';
    }

    html += '<form class="provider-form" data-form novalidate>';
    html += presetHtml(entry, item);

    html += '<div class="form-group">';
    html += '<label for="base-url-' + esc(provider) + '">Base URL</label>';
    html += '<input id="base-url-' + esc(provider) + '" data-role="base-url" type="url" spellcheck="false"' +
      ' value="' + esc(item && item.base_url ? item.base_url : '') + '"' +
      ' placeholder="' + esc(entry.default_base_url || '平台默认 Base URL') + '" />';
    html += '</div>';

    html += '<div class="form-group">';
    html += '<label for="api-key-' + esc(provider) + '">API Key</label>';
    html += '<input id="api-key-' + esc(provider) + '" data-role="api-key" type="password"' +
      ' autocomplete="new-password" spellcheck="false"' +
      ' placeholder="' + esc(keyPlaceholder(entry, item)) + '" />';
    html += '</div>';

    html += modelFieldsHtml(entry, item);

    var testModels = generationModelsFor(provider);
    if (testModels.length) {
      html += '<div class="provider-real-test">';
      html += '<h3>真实调用测试（可能计费）</h3>';
      html += '<p class="provider-warning">“测试连接”不产生费用；真实调用会直接请求第三方模型。图片测试生成 1 张最低规格图片；视频测试创建最短任务并立即尝试取消，取消失败仍可能计费。</p>';
      html += '<div class="form-group"><label for="test-model-' + esc(provider) + '">测试模型</label>';
      html += '<select id="test-model-' + esc(provider) + '" data-role="test-model">';
      for (var tm = 0; tm < testModels.length; tm += 1) {
        var testModel = testModels[tm];
        var typeLabel = testModel.task_type === 'image' ? '图片' : '视频';
        html += '<option value="' + esc(testModel.key) + '"' +
          (testModel.available ? '' : ' disabled') + '>' +
          esc((testModel.display_name || testModel.key) + ' · ' + (testModel.model_id || '—') +
            ' · ' + typeLabel + (testModel.available ? '' : '（未配置）')) + '</option>';
      }
      html += '</select></div>';
      html += '<button type="button" class="btn-outline btn-sm" data-action="test-generation">真实调用测试</button>';
      html += '<p class="provider-message" data-role="real-message" role="status" aria-live="polite" hidden></p>';
      html += '</div>';
    }

    html += '<div class="provider-actions">';
    html += '<button type="submit" class="btn-primary btn-sm">保存</button>';
    html += '<button type="button" class="btn-outline btn-sm" data-action="test">测试连接</button>';
    html += '<button type="button" class="btn-outline btn-sm provider-delete" data-action="delete"' +
      (item ? '' : ' disabled data-always-disabled="1"') + '>删除个人配置</button>';
    html += '</div>';
    html += '<p class="provider-message" data-role="message" role="status" aria-live="polite" hidden></p>';
    html += '</form>';

    if (docsUrl) {
      html += '<a class="provider-docs" href="' + esc(docsUrl) + '" target="_blank" rel="noopener noreferrer">' +
        '获取密钥 / 查看文档 ↗</a>';
    }

    html += '</article>';
    return html;
  }

  function render() {
    if (!cardsEl) return;
    if (!state.catalog.length) {
      cardsEl.innerHTML = '<p class="empty-state">没有可配置的 Provider。</p>';
      return;
    }
    var html = '';
    for (var i = 0; i < state.catalog.length; i += 1) {
      var entry = state.catalog[i] || {};
      html += cardHtml(entry, itemFor(entry.provider));
    }
    cardsEl.innerHTML = html;
  }

  // ── Data loading ──

  function loadCredentials(quiet) {
    setLoading(true);
    if (!quiet) setStatus('');
    return AIGV.api('/api/user/provider-credentials').then(function (data) {
      state.catalog = (data && data.catalog) || [];
      state.generationModels = (data && data.generation_models) || [];
      state.items = {};
      var items = (data && data.items) || [];
      for (var i = 0; i < items.length; i += 1) {
        if (items[i] && items[i].provider) {
          state.items[items[i].provider] = items[i];
        }
      }
      setTransportWarning();
      render();
      setLoading(false);
      return data;
    }).catch(function (error) {
      setLoading(false);
      setStatus((error && error.message) || '加载 API 配置失败', 'error');
      if (!cardsEl || !cardsEl.children.length) {
        if (cardsEl) cardsEl.innerHTML = '<p class="empty-state">API 配置加载失败，请刷新页面重试。</p>';
      }
      throw error;
    });
  }

  // ── Card actions ──

  function findEntry(provider) {
    for (var i = 0; i < state.catalog.length; i += 1) {
      if (state.catalog[i].provider === provider) return state.catalog[i];
    }
    return null;
  }

  function collectPayload(card, entry) {
    var body = {};
    var baseInput = card.querySelector('[data-role="base-url"]');
    var keyInput = card.querySelector('[data-role="api-key"]');
    if (baseInput) {
      var baseUrl = baseInput.value.trim();
      if (baseUrl) body.base_url = baseUrl;
    }
    if (keyInput) {
      var apiKey = keyInput.value.trim();
      // 空密钥 = 保留已保存的密钥；明文只在本次请求中出现。
      if (apiKey) body.api_key = apiKey;
    }

    var overrideInputs = card.querySelectorAll('[data-role="override"]');
    if (overrideInputs.length) {
      var overrides = {};
      for (var i = 0; i < overrideInputs.length; i += 1) {
        var key = overrideInputs[i].getAttribute('data-key');
        var value = overrideInputs[i].value.trim();
        if (key && value) overrides[key] = value;
      }
      var existing = itemFor(entry.provider);
      var hasExisting = !!(existing && existing.model_overrides &&
        Object.keys(existing.model_overrides).length);
      if (Object.keys(overrides).length || hasExisting) {
        // 显式提交对象：空对象表示清除已有覆盖，回退默认模型。
        body.model_overrides = overrides;
      }
    } else {
      var modelInput = card.querySelector('[data-role="model"]');
      if (modelInput) {
        var model = modelInput.value.trim();
        if (model) body.model = model;
      }
    }
    return body;
  }

  function describeError(error) {
    var code = error && error.code;
    var message = (error && error.message) || '请求失败';
    if (code === 'user_key_required') {
      return '必须填写你自己的密钥：' + message;
    }
    if (code === 'active_tasks') {
      return message;
    }
    if (code === 'provider_not_configured') {
      return message;
    }
    if (code === 'billing_confirmation_required') {
      return '真实调用会产生费用，请先确认计费提示：' + message;
    }
    if (code === 'https_required') {
      return 'API Key 只能通过 HTTPS 传输：' + message;
    }
    if (code === 'test_not_supported') {
      return '该 Provider 暂不支持真实生成测试：' + message;
    }
    return message;
  }

  function handleSave(card, entry) {
    var body = collectPayload(card, entry);
    if (!Object.keys(body).length) {
      setCardMessage(card, '请填写 Base URL、API Key 或模型后再保存。', 'warning');
      return;
    }
    setCardBusy(card, true);
    setCardMessage(card, '正在保存...', 'info');
    AIGV.api('/api/user/provider-credentials/' + encodeURIComponent(entry.provider), {
      method: 'PUT',
      body: body
    }).then(function () {
      var keyInput = card.querySelector('[data-role="api-key"]');
      if (keyInput) keyInput.value = '';
      setCardBusy(card, false);
      showToast(entry.name + ' 配置已保存', 'success');
      setStatus(entry.name + ' 配置已保存', 'success');
      // A reload failure is reported by the global status region; do not show
      // it as if the save itself failed.
      return loadCredentials(true).catch(function () {});
    }).catch(function (error) {
      setCardBusy(card, false);
      var message = describeError(error);
      setCardMessage(card, message, 'error');
      showToast(message, 'error');
    });
  }

  function handleTest(card, entry) {
    setCardBusy(card, true);
    setCardMessage(card, '正在测试连接...', 'info');
    AIGV.api('/api/user/provider-credentials/' + encodeURIComponent(entry.provider) + '/test', {
      method: 'POST'
    }).then(function (data) {
      setCardBusy(card, false);
      var network = (data && data.network) || {};
      var key = (data && data.key) || {};
      var model = (data && data.model) || {};
      var reachable = data && data.reachable !== undefined
        ? !!data.reachable : !!network.reachable;
      var verified = data && data.verified !== undefined
        ? !!data.verified : key.status === 'verified';
      var networkText = '网络：' + (reachable ? '可达' : '不可达');
      if (network.status_code) networkText += '（HTTP ' + network.status_code + '）';
      var parts = [
        networkText,
        '密钥：' + keyStatusLabel(key.status),
        '模型：' + modelStatusLabel(model.status)
      ];
      var detail = (data && data.message) || '';
      if (detail) parts.push(detail);
      if (key.provider_request_id) parts.push('请求 ID: ' + key.provider_request_id);
      var type = verified ? 'success' :
        ((!reachable || key.status === 'rejected') ? 'error' : 'warning');
      setCardMessage(card, parts.join(' · '), type);
    }).catch(function (error) {
      setCardBusy(card, false);
      var message = describeError(error);
      setCardMessage(card, message, 'error');
    });
  }

  function setRealMessage(card, message, type) {
    var el = card ? card.querySelector('[data-role="real-message"]') : null;
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = '';
      el.className = 'provider-message';
      return;
    }
    el.hidden = false;
    el.className = 'provider-message is-' + (type || 'info');
    el.textContent = message;
  }

  function handleRealTest(card, entry) {
    var select = card.querySelector('[data-role="test-model"]');
    if (!select || !select.value) {
      setRealMessage(card, '请选择要真实测试的模型。', 'warning');
      return;
    }
    var model = generationModelByKey(select.value) || {};
    var warning = model.task_type === 'video'
      ? '将真实创建一个最短规格视频任务，并立即尝试取消；若取消失败或服务商不支持取消，仍可能继续产生费用。'
      : '将真实生成 1 张最低规格图片，可能产生少量费用。';
    var confirmed = global.confirm(
      '即将真实调用「' + (model.display_name || select.value) + '」\n' +
      '模型 ID：' + (model.model_id || '—') + '\n\n' +
      warning + '\n\n是否继续？'
    );
    if (!confirmed) return;

    setCardBusy(card, true);
    setRealMessage(card, '正在发起真实调用，请稍候...', 'info');
    AIGV.api(
      '/api/user/provider-credentials/' + encodeURIComponent(entry.provider) +
      '/test-generation',
      {
        method: 'POST',
        body: { model_key: select.value, confirm_billing: true }
      }
    ).then(function (data) {
      setCardBusy(card, false);
      var status = data && data.status;
      var parts = [];
      if (status === 'succeeded') parts.push('真实图片生成成功');
      else if (status === 'accepted') parts.push('视频任务已创建');
      else parts.push('真实调用失败');
      if (data && data.model_id) parts.push('模型：' + data.model_id);
      if (data && data.provider_request_id) parts.push('请求 ID：' + data.provider_request_id);
      if (data && data.provider_job_id) parts.push('第三方任务 ID：' + data.provider_job_id);
      if (status === 'accepted') {
        parts.push(data.cancel_accepted ? '已请求取消' : '取消未确认，仍可能继续计费');
      }
      if (data && data.error_code) parts.push('错误码：' + data.error_code);
      if (data && data.message) parts.push(data.message);
      var type = status === 'failed' ? 'error' : (status === 'accepted' ? 'warning' : 'success');
      setRealMessage(card, parts.join(' · '), type);
    }).catch(function (error) {
      setCardBusy(card, false);
      setRealMessage(card, describeError(error), 'error');
    });
  }

  function handleDelete(card, entry) {
    var confirmed = global.confirm('确定删除「' + entry.name + '」的个人配置吗？删除后将回退使用平台默认配置。');
    if (!confirmed) return;
    setCardBusy(card, true);
    setCardMessage(card, '正在删除...', 'info');
    AIGV.api('/api/user/provider-credentials/' + encodeURIComponent(entry.provider), {
      method: 'DELETE'
    }).then(function () {
      setCardBusy(card, false);
      showToast(entry.name + ' 的个人配置已删除', 'success');
      setStatus(entry.name + ' 的个人配置已删除，已回退平台默认', 'success');
      return loadCredentials(true).catch(function () {});
    }).catch(function (error) {
      setCardBusy(card, false);
      var message = describeError(error);
      setCardMessage(card, message, 'error');
      showToast(message, 'error');
    });
  }

  function applyPreset(card, entry, index) {
    var preset = (entry.presets || [])[Number(index)];
    if (!preset) return;
    var baseInput = card.querySelector('[data-role="base-url"]');
    var modelInput = card.querySelector('[data-role="model"]');
    if (baseInput) baseInput.value = preset.base_url || '';
    if (modelInput) modelInput.value = preset.model || '';
    setCardMessage(card, '已填入预设「' + (preset.label || preset.base_url) + '」，请填写 API Key 后保存。', 'info');
  }

  // ── Event wiring (delegated: cards are re-rendered after every change) ──

  if (cardsEl) {
    cardsEl.addEventListener('submit', function (event) {
      var form = event.target.closest('[data-form]');
      if (!form) return;
      event.preventDefault();
      var card = form.closest('[data-provider]');
      var entry = card ? findEntry(card.getAttribute('data-provider')) : null;
      if (card && entry) handleSave(card, entry);
    });

    cardsEl.addEventListener('click', function (event) {
      var button = event.target.closest('[data-action]');
      if (!button) return;
      var card = button.closest('[data-provider]');
      var entry = card ? findEntry(card.getAttribute('data-provider')) : null;
      if (!card || !entry || button.disabled) return;
      if (button.getAttribute('data-action') === 'test') handleTest(card, entry);
      if (button.getAttribute('data-action') === 'test-generation') handleRealTest(card, entry);
      if (button.getAttribute('data-action') === 'delete') handleDelete(card, entry);
    });

    cardsEl.addEventListener('change', function (event) {
      var select = event.target.closest('[data-role="preset"]');
      if (!select) return;
      var card = select.closest('[data-provider]');
      var entry = card ? findEntry(card.getAttribute('data-provider')) : null;
      if (card && entry && select.value !== '') applyPreset(card, entry, select.value);
    });
  }

  setTransportWarning();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      loadCredentials().catch(function () {});
    });
  } else {
    loadCredentials().catch(function () {});
  }
})(window);
