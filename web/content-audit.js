/**
 * Frontend-only keyword audit preview for the creative studio sidebar.
 * The text and rule set never leave the browser.
 */
(function() {
  'use strict';

  var STORAGE_KEY = 'aigv_content_audit_v1';
  var DEFAULT_KEYWORDS = ['未授权素材', '涉密资料', '个人身份信息'];
  var els = {};
  var state = {
    keywords: [],
    mode: 'mask',
    lastText: '',
    lastResult: null
  };

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    els = {
      card: document.getElementById('content-audit-card'),
      status: document.getElementById('audit-status'),
      keywordList: document.getElementById('audit-keyword-list'),
      keywordCount: document.getElementById('audit-keyword-count'),
      keywordInput: document.getElementById('audit-keyword-input'),
      addKeyword: document.getElementById('audit-add-keyword'),
      text: document.getElementById('audit-text'),
      textCount: document.getElementById('audit-text-count'),
      modeInputs: document.querySelectorAll('input[name="audit-mode"]'),
      run: document.getElementById('audit-run'),
      clear: document.getElementById('audit-clear'),
      result: document.getElementById('audit-result'),
      fillButtons: document.querySelectorAll('[data-audit-source]')
    };
    if (!els.card) return;

    loadConfig();
    bindEvents();
    renderKeywords();
    updateTextCount();
    setStatus('pending');
    renderEmptyResult('命中 0 项 / 等待审核');
  }

  function loadConfig() {
    var parsed = null;
    try {
      var raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) parsed = JSON.parse(raw);
    } catch (error) {
      parsed = null;
    }
    var keywords = parsed && parsed.keywords
      ? window.ContentAuditCore.normalizeKeywords(parsed.keywords)
      : [];
    if (!keywords.length) {
      keywords = window.ContentAuditCore.normalizeKeywords(DEFAULT_KEYWORDS);
    }
    state.keywords = keywords;
    state.mode = parsed && parsed.mode === 'mark' ? 'mark' : 'mask';
    for (var i = 0; i < els.modeInputs.length; i += 1) {
      els.modeInputs[i].checked = els.modeInputs[i].value === state.mode;
    }
  }

  function saveConfig() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        version: 1,
        keywords: state.keywords,
        mode: state.mode
      }));
    } catch (error) {
      // Storage may be disabled; the in-memory rules still work.
    }
  }

  function bindEvents() {
    if (els.addKeyword) {
      els.addKeyword.addEventListener('click', addKeyword);
    }
    if (els.keywordInput) {
      els.keywordInput.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          addKeyword();
        }
      });
    }
    if (els.keywordList) {
      els.keywordList.addEventListener('click', function(event) {
        var button = event.target.closest('[data-audit-action]');
        if (!button) return;
        var index = parseInt(button.getAttribute('data-index'), 10);
        if (isNaN(index)) return;
        if (button.getAttribute('data-audit-action') === 'remove') {
          removeKeyword(index);
        } else {
          toggleKeyword(index);
        }
      });
    }
    if (els.text) {
      els.text.addEventListener('input', function() {
        updateTextCount();
        if (state.lastResult) {
          state.lastResult = null;
          state.lastText = '';
          setStatus('pending');
          renderEmptyResult('命中 0 项 / 等待审核');
        }
      });
    }
    for (var i = 0; i < els.modeInputs.length; i += 1) {
      els.modeInputs[i].addEventListener('change', function() {
        setMode(this.value);
      });
    }
    if (els.run) els.run.addEventListener('click', runAudit);
    if (els.clear) els.clear.addEventListener('click', clearAudit);
    for (var j = 0; j < els.fillButtons.length; j += 1) {
      els.fillButtons[j].addEventListener('click', function() {
        fillFromSource(this.getAttribute('data-audit-source'));
      });
    }
  }

  function renderKeywords() {
    if (!els.keywordList) return;
    els.keywordList.textContent = '';
    if (!state.keywords.length) {
      var empty = document.createElement('span');
      empty.className = 'audit-keyword-empty';
      empty.textContent = '暂无关键词规则';
      els.keywordList.appendChild(empty);
    }
    for (var i = 0; i < state.keywords.length; i += 1) {
      var keyword = state.keywords[i];
      var chip = document.createElement('span');
      chip.className = 'audit-keyword-chip' + (keyword.enabled ? '' : ' is-disabled');

      var toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'audit-keyword-toggle';
      toggle.setAttribute('data-audit-action', 'toggle');
      toggle.setAttribute('data-index', String(i));
      toggle.setAttribute('aria-pressed', keyword.enabled ? 'true' : 'false');
      toggle.title = keyword.enabled ? '点击停用该关键词' : '点击启用该关键词';

      var dot = document.createElement('span');
      dot.className = 'audit-keyword-dot';
      toggle.appendChild(dot);
      var text = document.createElement('span');
      text.className = 'audit-keyword-text';
      text.textContent = keyword.text;
      toggle.appendChild(text);
      chip.appendChild(toggle);

      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'audit-keyword-remove';
      remove.setAttribute('data-audit-action', 'remove');
      remove.setAttribute('data-index', String(i));
      remove.setAttribute('aria-label', '删除关键词 ' + keyword.text);
      remove.textContent = '×';
      chip.appendChild(remove);

      els.keywordList.appendChild(chip);
    }
    if (els.keywordCount) {
      var enabledCount = state.keywords.filter(function(item) {
        return item.enabled;
      }).length;
      els.keywordCount.textContent =
        state.keywords.length + ' 条 · ' + enabledCount + ' 启用';
    }
  }

  function addKeyword() {
    if (!els.keywordInput) return;
    var text = els.keywordInput.value.trim();
    if (!text) {
      showToast('请输入关键词', 'warning');
      return;
    }
    if (text.length > 40) {
      showToast('关键词不能超过 40 个字符', 'warning');
      return;
    }
    if (state.keywords.length >= window.ContentAuditCore.MAX_KEYWORDS) {
      showToast('最多添加 ' + window.ContentAuditCore.MAX_KEYWORDS + ' 个关键词', 'warning');
      return;
    }
    var exists = state.keywords.some(function(item) {
      return item.text.toLowerCase() === text.toLowerCase();
    });
    if (exists) {
      showToast('该关键词已存在', 'warning');
      return;
    }
    state.keywords.push({ text: text, enabled: true });
    els.keywordInput.value = '';
    saveConfig();
    renderKeywords();
    resetPreview('关键词规则已更新，等待重新审核');
  }

  function removeKeyword(index) {
    if (index < 0 || index >= state.keywords.length) return;
    state.keywords.splice(index, 1);
    saveConfig();
    renderKeywords();
    resetPreview('关键词规则已更新，等待重新审核');
  }

  function toggleKeyword(index) {
    if (index < 0 || index >= state.keywords.length) return;
    state.keywords[index].enabled = !state.keywords[index].enabled;
    saveConfig();
    renderKeywords();
    resetPreview('关键词规则已更新，等待重新审核');
  }

  function setMode(mode) {
    state.mode = mode === 'mark' ? 'mark' : 'mask';
    saveConfig();
    if (state.lastResult && state.lastText) {
      var result = window.ContentAuditCore.scanText(
        state.lastText,
        state.keywords,
        { mode: state.mode }
      );
      state.lastResult = result;
      setStatus(result.status === 'flagged' ? 'found' : 'passed');
      renderResult(result, state.mode);
    }
  }

  function updateTextCount() {
    if (!els.textCount || !els.text) return;
    els.textCount.textContent = els.text.value.length + ' 字';
  }

  function fillFromSource(source) {
    var text = getCurrentSourceText(source);
    if (!text || !text.trim()) {
      showToast('当前步骤暂无可填入内容', 'warning');
      return;
    }
    els.text.value = text;
    updateTextCount();
    resetPreview('已填入当前步骤内容，等待审核');
    els.text.focus();
  }

  function getCurrentSourceText(source) {
    var studio = window.CreativeStudio;
    if (!studio || !studio.state) return '';
    var current = studio.state;
    var shots = current.shots || [];
    var active = shots[current.activeShotIndex] || null;

    if (source === 'requirements') {
      return (current.requirementsForm && current.requirementsForm.description)
        || (current.project && current.project.description)
        || '';
    }
    if (source === 'shots') {
      return shots.map(function(shot) {
        return [shot.title, shot.sceneDesc].filter(Boolean).join('：');
      }).filter(Boolean).join('\n');
    }
    if (source === 'prompt') {
      if (active && active.keyframePrompt) return active.keyframePrompt;
      return shots.map(function(shot) {
        return shot.keyframePrompt;
      }).filter(Boolean).join('\n');
    }
    if (source === 'narration') {
      if (active && active.narration) return active.narration;
      return shots.map(function(shot) {
        return shot.narration;
      }).filter(Boolean).join('\n');
    }
    return '';
  }

  function runAudit() {
    if (!els.text) return;
    var text = els.text.value;
    if (!text.trim()) {
      setStatus('pending');
      renderEmptyResult('请输入待审核内容');
      return;
    }
    var result = window.ContentAuditCore.scanText(
      text,
      state.keywords,
      { mode: state.mode }
    );
    state.lastText = text;
    state.lastResult = result;
    setStatus(result.status === 'flagged' ? 'found' : 'passed');
    renderResult(result, state.mode);
  }

  function resetPreview(message) {
    state.lastText = '';
    state.lastResult = null;
    setStatus('pending');
    renderEmptyResult(message || '命中 0 项 / 等待审核');
  }

  function clearAudit() {
    if (els.text) els.text.value = '';
    updateTextCount();
    resetPreview('命中 0 项 / 等待审核');
  }

  function setStatus(kind) {
    if (!els.status) return;
    var labels = {
      pending: '待审核',
      passed: '已通过预览',
      found: '发现关键词'
    };
    els.status.className = 'content-audit-status is-' + kind;
    els.status.textContent = labels[kind] || labels.pending;
  }

  function renderEmptyResult(message) {
    if (!els.result) return;
    els.result.textContent = '';
    var empty = document.createElement('div');
    empty.className = 'audit-result-empty';
    empty.textContent = message;
    els.result.appendChild(empty);
  }

  function renderResult(result, mode) {
    if (!els.result) return;
    els.result.textContent = '';

    var summary = document.createElement('div');
    summary.className = 'audit-result-summary';
    if (result.hitCount) {
      summary.textContent = '命中 ' + result.hitCount + ' 处 / '
        + result.matchedKeywords.length + ' 个关键词';
    } else {
      summary.textContent = '命中 0 项 / 通过关键词检查';
    }
    els.result.appendChild(summary);

    if (result.matchedKeywords.length) {
      var chips = document.createElement('div');
      chips.className = 'audit-result-keywords';
      for (var i = 0; i < result.matchedKeywords.length; i += 1) {
        var chip = document.createElement('span');
        chip.className = 'meta-tag meta-tag-keyword';
        chip.textContent = result.matchedKeywords[i];
        chips.appendChild(chip);
      }
      els.result.appendChild(chips);
    }

    var preview = document.createElement('div');
    preview.className = 'audit-result-preview';
    if (mode === 'mark') {
      for (var s = 0; s < result.segments.length; s += 1) {
        var segment = result.segments[s];
        if (segment.hit) {
          var mark = document.createElement('mark');
          mark.textContent = segment.text;
          mark.title = (segment.keywords || []).join('、');
          preview.appendChild(mark);
        } else {
          preview.appendChild(document.createTextNode(segment.text));
        }
      }
    } else {
      preview.textContent = result.maskedText;
    }
    els.result.appendChild(preview);

    var checked = document.createElement('div');
    checked.className = 'audit-result-meta';
    checked.textContent = '已检查 ' + result.text.length + ' 个字符';
    els.result.appendChild(checked);
  }

  function showToast(message, type) {
    if (window.CreativeStudio && window.CreativeStudio.showToast) {
      window.CreativeStudio.showToast(message, type);
    }
  }

  window.ContentAudit = {
    scan: function(text) {
      return window.ContentAuditCore.scanText(text, state.keywords, {
        mode: state.mode
      });
    },
    getState: function() {
      return {
        keywords: state.keywords.slice(),
        mode: state.mode
      };
    }
  };
})();
