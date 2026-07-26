/**
 * AIGV Studio Creative Studio Frontend
 * Vanilla JS implementation for creative production workspace
 * Creative Production Workbench with 6 Modules
 */
(function() {
  'use strict';

  // ---------------------------------------------------------------
  // Toast notification system
  // ---------------------------------------------------------------
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
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }

  // DOM helpers
  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // API helpers
  function apiMessage(payload, fallback) {
    if (payload && payload.message) return payload.message;
    if (payload && payload.error) return payload.error;
    return fallback || '';
  }

  async function api(path, options) {
    var res = await fetch(path, options || {});
    var contentType = res.headers.get('content-type') || '';
    var payload = contentType.indexOf('application/json') >= 0 ? await res.json() : await res.text();
    if (!res.ok) throw new Error(apiMessage(payload, '请求失败: ' + res.status));
    if (payload && typeof payload === 'object' && payload.success !== undefined) {
      if (!payload.success) throw new Error(apiMessage(payload, '请求失败'));
      return payload.data;
    }
    return payload;
  }

  // ---------------------------------------------------------------
  // Custom Modal Dialogs (replaces browser native confirm/prompt)
  // ---------------------------------------------------------------
  function showConfirmDialog(title, message, confirmText, onConfirm) {
    title = title || '确认';
    message = message || '';
    confirmText = confirmText || '确认';
    onConfirm = onConfirm || function() {};

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    overlay.innerHTML =
      '<div class="modal-content modal-dialog-sm">' +
      '  <div class="studio-modal-header">' +
      '    <span class="studio-modal-title">' + escapeHtml(title) + '</span>' +
      '    <button class="studio-modal-close" aria-label="关闭">&times;</button>' +
      '  </div>' +
      '  <div class="studio-modal-body">' +
      '    <p class="modal-message">' + escapeHtml(message) + '</p>' +
      '  </div>' +
      '  <div class="modal-form-actions">' +
      '    <button class="modal-btn-cancel">取消</button>' +
      '    <button class="modal-btn-confirm">' + escapeHtml(confirmText) + '</button>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(overlay);

    var closeBtn = overlay.querySelector('.studio-modal-close');
    var cancelBtn = overlay.querySelector('.modal-btn-cancel');
    var confirmBtn = overlay.querySelector('.modal-btn-confirm');

    function closeModal() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeModal();
    });
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    confirmBtn.addEventListener('click', function() {
      closeModal();
      onConfirm();
    });

    // Keyboard support
    function onKeyDown(e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKeyDown); }
      if (e.key === 'Enter') { confirmBtn.click(); document.removeEventListener('keydown', onKeyDown); }
    }
    document.addEventListener('keydown', onKeyDown);

    // Focus confirm button
    setTimeout(function() { confirmBtn.focus(); }, 50);
  }

  function showEditShotDialog(shot, onSave) {
    if (!shot) return;
    onSave = onSave || function() {};

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    var shotTypeOptions = ['wide-shot', 'close-up', 'macro', 'medium-shot', 'aerial', 'orbit'];
    var shotTypeSelect = '';
    for (var i = 0; i < shotTypeOptions.length; i++) {
      var s = shotTypeOptions[i];
      var sel = (shot.shotType || '').toLowerCase() === s ? ' selected' : '';
      shotTypeSelect += '<option value="' + s + '"' + sel + '>' + s + '</option>';
    }

    overlay.innerHTML =
      '<div class="modal-content modal-dialog-md">' +
      '  <div class="studio-modal-header">' +
      '    <span class="studio-modal-title">编辑分镜</span>' +
      '    <button class="studio-modal-close" aria-label="关闭">&times;</button>' +
      '  </div>' +
      '  <div class="studio-modal-body">' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">分镜标题</label>' +
      '      <input type="text" class="modal-form-input" id="edit-shot-title" value="' + escapeHtml(shot.title || '') + '" />' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">时长 (秒)</label>' +
      '      <input type="number" class="modal-form-input" id="edit-shot-duration" value="' + (shot.duration || 5) + '" min="1" />' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">镜头类型</label>' +
      '      <select class="modal-form-input" id="edit-shot-type">' + shotTypeSelect + '</select>' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">运镜方式</label>' +
      '      <input type="text" class="modal-form-input" id="edit-shot-camera" value="' + escapeHtml(shot.cameraMove || '') + '" />' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">旁白文案</label>' +
      '      <textarea class="modal-form-input modal-form-textarea" id="edit-shot-narration" rows="3">' + escapeHtml(shot.narration || '') + '</textarea>' +
      '    </div>' +
      '  </div>' +
      '  <div class="modal-form-actions">' +
      '    <button class="modal-btn-cancel">取消</button>' +
      '    <button class="modal-btn-confirm">保存</button>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(overlay);

    function closeModal() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    function handleSave() {
      var titleEl = document.getElementById('edit-shot-title');
      var durEl = document.getElementById('edit-shot-duration');
      var typeEl = document.getElementById('edit-shot-type');
      var camEl = document.getElementById('edit-shot-camera');
      var narEl = document.getElementById('edit-shot-narration');

      if (titleEl && titleEl.value.trim()) {
        shot.title = titleEl.value.trim();
      }
      if (durEl) {
        var dur = parseInt(durEl.value, 10);
        if (!isNaN(dur) && dur > 0) shot.duration = dur;
      }
      if (typeEl && typeEl.value.trim()) {
        shot.shotType = typeEl.value.trim();
      }
      if (camEl && camEl.value.trim()) {
        shot.cameraMove = camEl.value.trim();
      }
      if (narEl && narEl.value.trim()) {
        shot.narration = narEl.value.trim();
      }

      closeModal();
      onSave();
    }

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeModal();
    });
    var closeBtn = overlay.querySelector('.studio-modal-close');
    closeBtn.addEventListener('click', closeModal);
    var cancelBtn = overlay.querySelector('.modal-btn-cancel');
    cancelBtn.addEventListener('click', closeModal);
    var confirmBtn = overlay.querySelector('.modal-btn-confirm');
    confirmBtn.addEventListener('click', handleSave);

    function onKeyDown(e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKeyDown); }
      if (e.key === 'Enter' && e.target && e.target.tagName !== 'TEXTAREA') {
        handleSave();
        document.removeEventListener('keydown', onKeyDown);
      }
    }
    document.addEventListener('keydown', onKeyDown);

    setTimeout(function() {
      var titleInput = document.getElementById('edit-shot-title');
      if (titleInput) titleInput.focus();
    }, 50);
  }

  function showEditTrackBlockDialog(block, onSave, totalDuration) {
    if (!block) return;
    onSave = onSave || function() {};
    totalDuration = totalDuration || 300;

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    overlay.innerHTML =
      '<div class="modal-content modal-dialog-md">' +
      '  <div class="studio-modal-header">' +
      '    <span class="studio-modal-title">编辑片段</span>' +
      '    <button class="studio-modal-close" aria-label="关闭">&times;</button>' +
      '  </div>' +
      '  <div class="studio-modal-body">' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">片段名称</label>' +
      '      <input type="text" class="modal-form-input" id="edit-block-label" value="' + escapeHtml(block.label || '') + '" />' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">开始时间 (秒)</label>' +
      '      <input type="number" class="modal-form-input" id="edit-block-start" value="' + (block.start || 0) + '" min="0" max="' + totalDuration + '" step="0.1" />' +
      '    </div>' +
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label">时长 (秒)</label>' +
      '      <input type="number" class="modal-form-input" id="edit-block-duration" value="' + (block.duration || 5) + '" min="0.1" step="0.1" />' +
      '    </div>' +
      '  </div>' +
      '  <div class="modal-form-actions">' +
      '    <button class="modal-btn-cancel">取消</button>' +
      '    <button class="modal-btn-confirm">保存</button>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(overlay);

    function closeModal() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    function handleSave() {
      var labelEl = document.getElementById('edit-block-label');
      var startEl = document.getElementById('edit-block-start');
      var durEl = document.getElementById('edit-block-duration');

      if (labelEl && labelEl.value !== null) block.label = labelEl.value;
      if (startEl) {
        var ns = parseFloat(startEl.value);
        if (!isNaN(ns) && ns >= 0) block.start = ns;
      }
      if (durEl) {
        var nd = parseFloat(durEl.value);
        if (!isNaN(nd) && nd > 0) block.duration = nd;
      }

      closeModal();
      onSave(block);
    }

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeModal();
    });
    var closeBtn = overlay.querySelector('.studio-modal-close');
    closeBtn.addEventListener('click', closeModal);
    var cancelBtn = overlay.querySelector('.modal-btn-cancel');
    cancelBtn.addEventListener('click', closeModal);
    var confirmBtn = overlay.querySelector('.modal-btn-confirm');
    confirmBtn.addEventListener('click', handleSave);

    function onKeyDown(e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKeyDown); }
      if (e.key === 'Enter' && e.target && e.target.tagName !== 'TEXTAREA') {
        handleSave();
        document.removeEventListener('keydown', onKeyDown);
      }
    }
    document.addEventListener('keydown', onKeyDown);

    setTimeout(function() {
      var labelInput = document.getElementById('edit-block-label');
      if (labelInput) labelInput.focus();
    }, 50);
  }

  // ---------------------------------------------------------------
  // Central State
  // ---------------------------------------------------------------
  var state = {
    activeProjectId: null,
    projects: [],
    activeProject: null,
    activeStep: 1,
    stepsCompleted: [false, false, false, false, false, false],
    activeShotIndex: 0,
    requirementsForm: {
      projectName: '',
      theme: '',
      elements: '',
      audience: '',
      channels: '',
      duration: 60,
      aspect: '16:9',
      style: 'cinematic-realistic',
      mood: '',
      description: '',
      restrictions: ''
    },
    analysisInProgress: false,
    analysisStage: '',
    conceptImages: {},
    imageGenInProgress: false,
    videoGenInProgress: false,
    videoGenStage: '',
    videoProgress: 0,
    videoCancelRequested: false,
    videoResults: {},
    narrationForm: {
      voiceId: 'vp-001',
      speechRate: 1.0,
      volume: 1.0,
      backgroundMusic: 'none',
      musicVolume: 0.3
    },
    trackData: {
      video: [],
      narration: [],
      music: [],
      effects: [],
      subtitles: []
    },
    filterParams: {
      brightness: 100,
      contrast: 100,
      saturation: 100,
      blur: 0,
      hueRotate: 0,
      sepia: 0,
      vignette: 0
    },
    humanParams: {
      exposure: 0,
      contrast: 0,
      highlights: 0,
      shadows: 0,
      temperature: 0,
      saturation: 0,
      clarity: 0,
      sharpening: 0
    },
    aiBatchInProgress: false,
    outputForm: {
      platformId: '',
      format: 'MP4',
      resolution: '1080p',
      fps: 30,
      bitrate: '15Mbps',
      includeSubtitles: true
    },
    exportInProgress: false,
    exportTree: null,
    demoData: null,
    conceptGenTimer: null,
    videoGenTimer: null,
    aiBatchTimer: null,
    exportTimer: null,
    analysisTimer: null,
    // Backend-driven fields
    projectId: null,
    project: null,
    shots: [],
    tasks: {}
  };

  // ---------------------------------------------------------------
  // Element cache
  // ---------------------------------------------------------------
  var els = {};

  function cacheElements() {
    els.projectSelect = $('project-select');
    els.projectMetrics = $('project-metrics');
    els.projectActions = $('project-actions');
    els.btnSaveProject = $('btn-save-project');
    els.btnResetProject = $('btn-reset-project');
    els.flowNav = $('flow-nav');
    els.studioContentPanel = $('studio-content-panel');
    els.studioPreviewPanel = $('studio-preview-panel');
    els.previewStepLabel = $('preview-step-label');
    els.previewBody = $('preview-body');
  }

  // ---------------------------------------------------------------
  // localStorage Persistence
  // ---------------------------------------------------------------
  var STORAGE_KEY = 'aigv_creative_studio_v1';

  function saveToLocalStorage() {
    try {
      // Only save UI preferences, not business data (which comes from backend)
      var prefs = {
        version: 1,
        activeStep: state.activeStep,
        activeShotIndex: state.activeShotIndex,
        stepsCompleted: state.stepsCompleted,
        requirementsForm: state.requirementsForm,
        narrationForm: state.narrationForm,
        filterParams: state.filterParams,
        humanParams: state.humanParams,
        outputForm: state.outputForm,
        trackData: state.trackData
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch (e) {
      // Silently ignore
    }
  }

  function loadFromLocalStorage() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      var prefs = JSON.parse(raw);
      if (!prefs) { localStorage.removeItem(STORAGE_KEY); return false; }
      if (prefs.activeStep) state.activeStep = prefs.activeStep;
      if (prefs.activeShotIndex != null) state.activeShotIndex = prefs.activeShotIndex;
      if (prefs.stepsCompleted) state.stepsCompleted = prefs.stepsCompleted;
      if (prefs.requirementsForm) Object.assign(state.requirementsForm, prefs.requirementsForm);
      if (prefs.narrationForm) Object.assign(state.narrationForm, prefs.narrationForm);
      if (prefs.filterParams) Object.assign(state.filterParams, prefs.filterParams);
      if (prefs.humanParams) Object.assign(state.humanParams, prefs.humanParams);
      if (prefs.outputForm) Object.assign(state.outputForm, prefs.outputForm);
      if (prefs.trackData) Object.assign(state.trackData, prefs.trackData);
      return true;
    } catch (e) {
      try { localStorage.removeItem(STORAGE_KEY); } catch (ex) {}
      return false;
    }
  }

  // ---------------------------------------------------------------
  // Demo data helpers
  // ---------------------------------------------------------------
  function loadDemoData() {
    var data = window.AIGV_DEMO_DATA;
    if (!data) {
      showToast('演示数据加载失败', 'error');
      return null;
    }
    var demoStatus = $('demo-data-status');
    if (demoStatus) {
      var projectCount = (data.creativeProjects && data.creativeProjects.length) || 0;
      var shotCount = (data.storyboardShots && data.storyboardShots.length) || 0;
      demoStatus.textContent = '演示数据: 已加载 ' + projectCount + ' 个项目，' + shotCount + ' 个分镜';
    }
    return data;
  }

  // ---------------------------------------------------------------
  // Core Functions
  // ---------------------------------------------------------------

  function init() {
    cacheElements();

    // Try restoring UI prefs from localStorage
    loadFromLocalStorage();

    // Set active project
    if (state.projectId) {
      state.activeProjectId = state.projectId;
      state.activeProject = state.project;
    } else {
      state.activeProject = getActiveProject();
    }

    // Bind events
    bindEvents();

    // Render
    renderCurrentModule();
    updateFlowNav();
    updatePreviewPanel(state.activeStep);
    updateProjectMetrics();
  }

  function getActiveProject() {
    return state.project;
  }

  function getShotsForActiveProject() {
    return state.shots || [];
  }

  // Map backend shot fields to frontend-friendly aliases
  function normalizeShot(shot) {
    if (!shot) return null;
    // Backend fields: id, scene_title, duration_s, shot_type, camera_movement,
    //   scene_description, dialogue, prompt_en, prompt_cn, negative_prompt,
    //   status, sequence_no, primary_image_asset_id, video_url, video_asset_id
    if (!shot.shotId) {
      shot.shotId = shot.id;
      shot.title = shot.scene_title || '';
      shot.duration = shot.duration_s || 5;
      shot.shotType = shot.shot_type || 'medium-shot';
      shot.cameraMove = shot.camera_movement || '';
      shot.sceneDesc = shot.scene_description || '';
      shot.narration = shot.dialogue || '';
      shot.keyframePrompt = shot.prompt_en || shot.prompt_cn || '';
      shot.negativePrompt = shot.negative_prompt || '';
      shot.number = shot.sequence_no || 0;
      shot.isDemo = false;
    }
    return shot;
  }

  // Normalize all shots in state and return
  function getNormalizedShots() {
    var shots = state.shots || [];
    for (var i = 0; i < shots.length; i++) {
      normalizeShot(shots[i]);
    }
    return shots;
  }

  // Find shot in state.shots by ID
  function findShotById(shotId) {
    var shots = state.shots || [];
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].id === shotId) {
        return normalizeShot(shots[i]);
      }
    }
    return null;
  }

  function populateProjectSelector() {
    if (!els.projectSelect) return;
    els.projectSelect.innerHTML = '';
    for (var i = 0; i < state.projects.length; i++) {
      var p = state.projects[i];
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name || p.theme || ('项目 ' + (i + 1));
      if (p.id === state.activeProjectId) {
        opt.selected = true;
      }
      els.projectSelect.appendChild(opt);
    }
  }

  function bindEvents() {
    // Project selector change
    if (els.projectSelect) {
      els.projectSelect.addEventListener('change', function(e) {
        switchProject(e.target.value);
      });
    }

    // Flow nav clicks
    if (els.flowNav) {
      els.flowNav.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-step]');
        if (btn) {
          var step = parseInt(btn.getAttribute('data-step'), 10);
          switchStep(step);
        }
      });
    }

    // Save button
    if (els.btnSaveProject) {
      els.btnSaveProject.addEventListener('click', function() {
        saveToLocalStorage();
        showToast('项目已保存', 'success');
      });
    }

    // Reset button
    if (els.btnResetProject) {
      els.btnResetProject.addEventListener('click', function() {
        showConfirmDialog('重置项目', '确定要重置所有进度吗？此操作不可撤销。', '重置', function() {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        state.projectId = null;
        state.project = null;
        state.shots = [];
        state.activeProjectId = null;
        state.activeProject = null;
        state.activeStep = 1;
        state.stepsCompleted = [false, false, false, false, false, false];
        state.activeShotIndex = 0;
        state.conceptImages = {};
        state.videoResults = {};
        state.trackData = { video: [], narration: [], music: [], effects: [], subtitles: [] };
        state.exportTree = null;
        state.analysisInProgress = false;
        state.analysisStage = '';
        state.imageGenInProgress = false;
        state.videoGenInProgress = false;
        state.videoGenStage = '';
        state.videoProgress = 0;
        state.videoCancelRequested = false;
        state.narrationForm = { voiceId: 'vp-001', speechRate: 1.0, volume: 1.0, backgroundMusic: 'none', musicVolume: 0.3 };
        state.filterParams = { brightness: 100, contrast: 100, saturation: 100, blur: 0, hueRotate: 0, sepia: 0, vignette: 0 };
        state.humanParams = { exposure: 0, contrast: 0, highlights: 0, shadows: 0, temperature: 0, saturation: 0, clarity: 0, sharpening: 0 };
        state.aiBatchInProgress = false;
        state.outputForm = { platformId: '', format: 'MP4', resolution: '1080p', fps: 30, bitrate: '15Mbps', includeSubtitles: true };
        state.exportInProgress = false;
        state.tasks = {};
        // Clear timers
        if (state.conceptGenTimer) { clearTimeout(state.conceptGenTimer); state.conceptGenTimer = null; }
        if (state.videoGenTimer) { clearTimeout(state.videoGenTimer); state.videoGenTimer = null; }
        if (state.aiBatchTimer) { clearTimeout(state.aiBatchTimer); state.aiBatchTimer = null; }
        if (state.exportTimer) { clearTimeout(state.exportTimer); state.exportTimer = null; }
        populateProjectSelector();
        renderCurrentModule();
        updateFlowNav();
        updatePreviewPanel(state.activeStep);
        updateProjectMetrics();
        showToast('项目已重置', 'success');
      });
      });
    }
  }

  function switchProject(id) {
    state.activeProjectId = id;
    // Load project from backend
    loadProjectFromBackend(id);
    state.activeShotIndex = 0;
    saveToLocalStorage();
    renderCurrentModule();
    updateFlowNav();
    updatePreviewPanel(state.activeStep);
    updateProjectMetrics();
  }

  async function loadProjectFromBackend(projectId) {
    try {
      var project = await api('/api/creative/projects/' + projectId);
      state.project = project;
      state.projectId = projectId;
      state.activeProject = project;
      // Load shots
      var shots = await api('/api/creative/projects/' + projectId + '/shots');
      state.shots = shots || [];
      // Update form fields
      if (project) {
        state.requirementsForm.projectName = project.name || '';
      }
    } catch (e) {
      showToast('加载项目失败: ' + e.message, 'error');
    }
  }

  function switchStep(n) {
    if (n < 1 || n > 6) return;
    state.activeStep = n;
    updateFlowNav();
    renderCurrentModule();
    updatePreviewPanel(n);
  }

  function updateFlowNav() {
    if (!els.flowNav) return;
    var steps = els.flowNav.querySelectorAll('[data-step]');
    for (var i = 0; i < steps.length; i++) {
      var stepNum = parseInt(steps[i].getAttribute('data-step'), 10);
      steps[i].classList.remove('active', 'completed');
      if (stepNum === state.activeStep) {
        steps[i].classList.add('active');
      } else if (state.stepsCompleted[stepNum - 1]) {
        steps[i].classList.add('completed');
      }
    }
  }

  function updateProjectMetrics() {
    if (!els.projectMetrics) return;
    var project = getActiveProject();
    if (!project) {
      els.projectMetrics.innerHTML = '<div class="metric-empty">未选择项目</div>';
      return;
    }
    var shots = project.shots || [];
    var totalDuration = 0;
    for (var i = 0; i < shots.length; i++) {
      totalDuration += (shots[i].duration || 0);
    }
    var confirmedCount = 0;
    for (var j = 0; j < shots.length; j++) {
      if (shots[j].status === 'confirmed') confirmedCount++;
    }
    var html = '';
    html += '<div class="metric-item"><span class="metric-label">分镜数</span><span class="metric-value">' + shots.length + '</span></div>';
    html += '<div class="metric-item"><span class="metric-label">总时长</span><span class="metric-value">' + totalDuration + 's</span></div>';
    html += '<div class="metric-item"><span class="metric-label">已确认</span><span class="metric-value">' + confirmedCount + '</span></div>';
    html += '<div class="metric-item"><span class="metric-label">状态</span><span class="metric-value status-badge status-' + escapeHtml(project.status || 'draft') + '">' + escapeHtml(project.status || '草稿') + '</span></div>';
    els.projectMetrics.innerHTML = html;
  }

  function updatePreviewPanel(stepNum) {
    var labels = ['', '需求与分镜', '概念图生成', '视频生成', '多模态增强', '人机精调', '输出适配'];
    var descriptions = [
      '',
      '填写创作需求，AI自动分析并生成分镜脚本。可对每个分镜进行编辑、排序和确认。',
      '为已确认的分镜生成概念参考图。支持多种模型，可设置关键帧。',
      '基于关键帧生成视频。支持多种参数调整和模型选择。',
      '添加配音、背景音乐、音效，并编辑时间线。',
      '使用滤镜和AI批处理工具对画面进行精细化调整。',
      '选择输出平台，配置导出参数，生成最终成果包。'
    ];

    if (els.previewStepLabel) {
      els.previewStepLabel.textContent = '步骤 ' + stepNum + ': ' + (labels[stepNum] || '');
    }
    if (els.previewBody) {
      var project = getActiveProject();
      var projName = project ? (project.name || project.theme || '未命名项目') : '未选择项目';
      var html = '';
      html += '<div class="preview-info-card">';
      html += '  <div class="preview-info-title">' + escapeHtml(projName) + '</div>';
      html += '  <div class="preview-info-desc">' + escapeHtml(descriptions[stepNum] || '') + '</div>';
      html += '  <div class="preview-info-meta">';
      html += '    <span class="meta-chip">步骤 ' + stepNum + '/6</span>';
      if (state.stepsCompleted[stepNum - 1]) {
        html += '    <span class="meta-chip chip-success">已完成</span>';
      } else {
        html += '    <span class="meta-chip chip-pending">待完成</span>';
      }
      html += '  </div>';
      // Module-specific preview
      html += getStepPreviewContent(stepNum);
      html += '</div>';
      els.previewBody.innerHTML = html;
    }
  }

  function getStepPreviewContent(stepNum) {
    var html = '<div class="preview-module-detail">';
    switch (stepNum) {
      case 1: {
        var shots = getShotsForActiveProject();
        html += '<p>分镜数量: <strong>' + shots.length + '</strong></p>';
        var confirmed = 0;
        for (var i = 0; i < shots.length; i++) {
          if (shots[i].status === 'confirmed') confirmed++;
        }
        html += '<p>已确认: <strong>' + confirmed + '</strong></p>';
        break;
      }
      case 2: {
        var shot = getActiveShot();
        if (shot) {
          html += '<p>当前镜头: <strong>' + escapeHtml(shot.title) + '</strong></p>';
        }
        var shotId = shot ? shot.shotId : null;
        var images = shotId && state.conceptImages[shotId] ? state.conceptImages[shotId] : [];
        html += '<p>概念图: <strong>' + images.length + '</strong> 张</p>';
        var keyframes = 0;
        for (var k = 0; k < images.length; k++) {
          if (images[k].isKeyframe) keyframes++;
        }
        html += '<p>关键帧: <strong>' + keyframes + '</strong></p>';
        break;
      }
      case 3: {
        var s = getActiveShot();
        var sid = s ? s.shotId : null;
        var vr = sid && state.videoResults[sid] ? state.videoResults[sid] : null;
        html += '<p>视频状态: <strong>' + (vr ? vr.status : '未生成') + '</strong></p>';
        break;
      }
      case 4: {
        var tracks = state.trackData;
        html += '<p>视频轨: <strong>' + (tracks.video ? tracks.video.length : 0) + '</strong> 片段</p>';
        html += '<p>配音轨: <strong>' + (tracks.narration ? tracks.narration.length : 0) + '</strong> 片段</p>';
        break;
      }
      case 5: {
        var fp = state.filterParams;
        html += '<p>亮度: ' + fp.brightness + '% | 对比度: ' + fp.contrast + '% | 饱和度: ' + fp.saturation + '%</p>';
        break;
      }
      case 6: {
        html += '<p>输出格式: <strong>' + escapeHtml(state.outputForm.format) + '</strong></p>';
        html += '<p>分辨率: <strong>' + escapeHtml(state.outputForm.resolution) + '</strong></p>';
        html += '<p>导出包: <strong>' + (state.exportTree ? '已生成' : '未生成') + '</strong></p>';
        break;
      }
    }
    html += '</div>';
    return html;
  }

  function renderCurrentModule() {
    if (!els.studioContentPanel) return;
    switch (state.activeStep) {
      case 1: renderModule1(); break;
      case 2: renderModule2(); break;
      case 3: renderModule3(); break;
      case 4: renderModule4(); break;
      case 5: renderModule5(); break;
      case 6: renderModule6(); break;
      default: renderModule1(); break;
    }
  }

  // ---------------------------------------------------------------
  // Shot helpers
  // ---------------------------------------------------------------

  function getActiveShot() {
    var shots = getNormalizedShots();
    if (shots.length === 0) return null;
    if (state.activeShotIndex >= shots.length) {
      state.activeShotIndex = 0;
    }
    return shots[state.activeShotIndex];
  }

  function getConfirmedShots() {
    var shots = getNormalizedShots();
    var result = [];
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].status === 'confirmed') {
        result.push(shots[i]);
      }
    }
    return result;
  }

  // ---------------------------------------------------------------
  // Template Generator
  // ---------------------------------------------------------------

  function templateGenerator(project) {
    var shots = [];
    if (!project) return shots;

    var theme = project.theme || '文化场馆';
    var elements = project.elements || '';

    var shotTypes = ['wide-shot', 'close-up', 'macro', 'medium-shot', 'aerial', 'orbit'];
    var cameraMoves = ['pan-left', 'pan-right', 'tilt-up', 'tilt-down', 'dolly-in', 'dolly-out', 'track-left', 'track-right', 'static', 'crane-up', 'crane-down'];
    var durations = [8, 10, 12, 6, 15, 8];

    var titles = [
      '开场全景 - ' + theme,
      '细节特写',
      '空间氛围',
      '主体呈现',
      '动态叙事',
      '收尾升华'
    ];

    var sceneDescs = [
      '场馆外景全景，展示建筑整体风貌和环境',
      '场馆内部装饰细节，材质与纹理特写',
      '空间内部光影氛围，展示空间感与层次',
      '核心展品或表演主体居中呈现',
      '人物或展品在空间中的动态过程',
      '场馆全景或标志性视角，配合结尾文案'
    ];

    var subjectDescs = [
      '建筑外观与周边环境',
      '局部细节与材质纹理',
      '空间内部结构与光线',
      '核心展品或表演者',
      '人物/展品运动轨迹',
      '整体场景鸟瞰'
    ];

    var actionDescs = [
      '缓慢平移展示全貌',
      '极慢推进聚焦细节',
      '环绕拍摄展现空间',
      '由远及近推向主体',
      '跟随主体运动轨迹',
      '缓慢拉升或后退'
    ];

    var lightingDescs = [
      '自然光，黄昏时分，暖色调',
      '聚光灯，局部照明，高对比',
      '环境光，柔和均匀，氛围感',
      '主光+补光，突出主体',
      '动态光线变化，跟随运动',
      '渐变光线，由亮转暗'
    ];

    var narrations = [
      '欢迎来到' + theme + '，让我们一同探索文化与艺术的魅力。',
      '每一处细节都承载着历史的记忆与匠心的温度。',
      '空间与光线交织，营造出沉浸式的观展体验。',
      '现在呈现在您面前的是本次展览的核心作品。',
      '跟随时间的轨迹，感受艺术与空间的对话。',
      '感谢您的观看，期待与您再次相遇。'
    ];

    var keyframePrompts = [
      ' cinematic wide shot of a cultural venue exterior, golden hour lighting, majestic architecture, professional photography, 8K',
      ' macro close-up of intricate decorative details, rich textures, shallow depth of field, museum lighting',
      ' interior ambient shot of a gallery space, soft natural light through windows, volumetric rays, serene atmosphere',
      ' medium shot of central exhibit/performance, dramatic key light, professional stage lighting, deep shadows',
      ' dynamic tracking shot of moving subject, motion blur, cinematic composition, action sequence',
      ' aerial establishing shot pulling back, cityscape background, epic scale, golden ratio composition'
    ];

    var negativePrompts = [
      'blurry, low quality, distortion, oversaturated, watermark, text overlay',
      'motion blur, camera shake, out of focus, noise, grain',
      'harsh lighting, overexposed, underexposed, flat lighting, no contrast',
      'cluttered background, distracting elements, poor composition, bad framing',
      'static motion, frozen, stiff, unnatural movement, robotic',
      'oversharpened, artificial, CGI looking, fake, plastic'
    ];

    for (var i = 0; i < 6; i++) {
      var idx = i % shotTypes.length;
      var camIdx = i % cameraMoves.length;
      var shot = {
        shotId: project.id + '-shot-' + (i + 1),
        projectId: project.id,
        number: i + 1,
        title: titles[i],
        duration: durations[i],
        shotType: shotTypes[idx],
        cameraMove: cameraMoves[camIdx],
        sceneDesc: sceneDescs[i],
        subjectDesc: subjectDescs[i],
        actionDesc: actionDescs[i],
        lightingDesc: lightingDescs[i],
        narration: narrations[i],
        keyframePrompt: keyframePrompts[i],
        negativePrompt: negativePrompts[i],
        status: 'draft',
        isDemo: true
      };
      shots.push(shot);
    }

    return shots;
  }

  // ---------------------------------------------------------------
  // MODULE 1: Requirements & Storyboard
  // ---------------------------------------------------------------

  function renderModule1() {
    var project = getActiveProject();
    if (!project) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-icon">&#128196;</div><p>请先选择一个项目开始创作</p></div>';
      return;
    }

    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">需求分析与分镜脚本</h2>';
    html += '</div>';

    // Requirements form
    html += '<div class="requirements-form card">';
    html += '  <h3>创作需求</h3>';
    html += '  <div class="form-grid">';
    html += '    <div class="form-group"><label>项目名称</label><input type="text" id="req-project-name" value="' + escapeHtml(state.requirementsForm.projectName) + '" /></div>';
    html += '    <div class="form-group"><label>主题</label><input type="text" id="req-theme" value="' + escapeHtml(state.requirementsForm.theme) + '" /></div>';
    html += '    <div class="form-group"><label>核心元素</label><input type="text" id="req-elements" value="' + escapeHtml(state.requirementsForm.elements) + '" placeholder="建筑、展品、表演..." /></div>';
    html += '    <div class="form-group"><label>目标受众</label><input type="text" id="req-audience" value="' + escapeHtml(state.requirementsForm.audience) + '" /></div>';
    html += '    <div class="form-group"><label>投放渠道</label><input type="text" id="req-channels" value="' + escapeHtml(state.requirementsForm.channels) + '" /></div>';
    html += '    <div class="form-group"><label>时长 (秒)</label><input type="number" id="req-duration" value="' + state.requirementsForm.duration + '" min="10" max="300" /></div>';
    html += '    <div class="form-group"><label>画面比例</label>';
    html += '      <select id="req-aspect">';
    html += '        <option value="16:9"' + (state.requirementsForm.aspect === '16:9' ? ' selected' : '') + '>16:9 横屏</option>';
    html += '        <option value="9:16"' + (state.requirementsForm.aspect === '9:16' ? ' selected' : '') + '>9:16 竖屏</option>';
    html += '        <option value="1:1"' + (state.requirementsForm.aspect === '1:1' ? ' selected' : '') + '>1:1 方形</option>';
    html += '        <option value="4:3"' + (state.requirementsForm.aspect === '4:3' ? ' selected' : '') + '>4:3 经典</option>';
    html += '        <option value="21:9"' + (state.requirementsForm.aspect === '21:9' ? ' selected' : '') + '>21:9 宽屏</option>';
    html += '      </select></div>';
    html += '    <div class="form-group"><label>视觉风格</label>';
    html += '      <select id="req-style">';
    html += '        <option value="cinematic-realistic"' + (state.requirementsForm.style === 'cinematic-realistic' ? ' selected' : '') + '>电影写实</option>';
    html += '        <option value="minimalist"' + (state.requirementsForm.style === 'minimalist' ? ' selected' : '') + '>极简主义</option>';
    html += '        <option value="dramatic"' + (state.requirementsForm.style === 'dramatic' ? ' selected' : '') + '>戏剧光影</option>';
    html += '        <option value="vintage"' + (state.requirementsForm.style === 'vintage' ? ' selected' : '') + '>复古质感</option>';
    html += '        <option value="cyberpunk"' + (state.requirementsForm.style === 'cyberpunk' ? ' selected' : '') + '>赛博朋克</option>';
    html += '      </select></div>';
    html += '    <div class="form-group"><label>情绪基调</label><input type="text" id="req-mood" value="' + escapeHtml(state.requirementsForm.mood) + '" placeholder="庄重、温馨、震撼..." /></div>';
    html += '    <div class="form-group full-width"><label>详细描述</label><textarea id="req-description" rows="3">' + escapeHtml(state.requirementsForm.description) + '</textarea></div>';
    html += '    <div class="form-group full-width"><label>限制条件</label><textarea id="req-restrictions" rows="2" placeholder="版权限制、技术限制等">' + escapeHtml(state.requirementsForm.restrictions) + '</textarea></div>';
    html += '  </div>';
    html += '  <div class="form-actions">';
    html += '    <button class="btn btn-primary" id="btn-analyze-requirements">';
    if (state.analysisInProgress) {
      html += '      <span class="spinner"></span> ' + escapeHtml(state.analysisStage);
    } else {
      html += '      &#9889; 分析需求';
    }
    html += '    </button>';
    html += '  </div>';
    html += '</div>';

    // Analysis progress
    if (state.analysisInProgress) {
      html += '<div class="analysis-progress card">';
      html += '  <div class="progress-bar">';
      html += '    <div class="progress-fill progress-animate"></div>';
      html += '  </div>';
      html += '  <p class="progress-label">' + escapeHtml(state.analysisStage) + '</p>';
      html += '</div>';
    }

    // Shot cards
    html += '<div class="shot-cards-section">';
    html += '  <h3>分镜脚本 <span class="badge">' + getShotsForActiveProject().length + '</span></h3>';
    html += '  <div class="shot-cards-grid" id="shot-cards-grid">';
    html += renderShotCardsHTML();
    html += '  </div>';
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind form listeners
    bindRequirementFormListeners();

    // Bind analyze button
    var analyzeBtn = $('btn-analyze-requirements');
    if (analyzeBtn) {
      analyzeBtn.addEventListener('click', handleAnalyzeRequirements);
    }

    // Bind shot card actions
    bindShotCardActions();
  }

  function bindRequirementFormListeners() {
    var fields = [
      { id: 'req-project-name', key: 'projectName' },
      { id: 'req-theme', key: 'theme' },
      { id: 'req-elements', key: 'elements' },
      { id: 'req-audience', key: 'audience' },
      { id: 'req-channels', key: 'channels' },
      { id: 'req-mood', key: 'mood' },
      { id: 'req-restrictions', key: 'restrictions' }
    ];
    for (var i = 0; i < fields.length; i++) {
      (function(field) {
        var el = $(field.id);
        if (el) {
          el.addEventListener('input', function() {
            state.requirementsForm[field.key] = el.value;
          });
        }
      })(fields[i]);
    }

    // Number field
    var durEl = $('req-duration');
    if (durEl) {
      durEl.addEventListener('change', function() {
        state.requirementsForm.duration = parseInt(durEl.value, 10) || 60;
      });
    }

    // Select fields
    var aspectEl = $('req-aspect');
    if (aspectEl) {
      aspectEl.addEventListener('change', function() {
        state.requirementsForm.aspect = aspectEl.value;
      });
    }
    var styleEl = $('req-style');
    if (styleEl) {
      styleEl.addEventListener('change', function() {
        state.requirementsForm.style = styleEl.value;
      });
    }
    var descEl = $('req-description');
    if (descEl) {
      descEl.addEventListener('input', function() {
        state.requirementsForm.description = descEl.value;
      });
    }
  }

  function handleAnalyzeRequirements() {
    if (state.analysisInProgress) return;
    state.analysisInProgress = true;
    state.analysisStage = '正在创建项目...';
    renderModule1();

    (async function() {
      try {
        // Step 1: Create project via API if not already created
        if (!state.projectId) {
          state.analysisStage = '正在创建项目...';
          renderModule1();

          var projectData = {
            name: state.requirementsForm.projectName || state.requirementsForm.theme || '未命名项目',
            description: state.requirementsForm.description,
            genre: state.requirementsForm.style || 'cinematic',
            concept: state.requirementsForm.theme,
            requirements: {
              elements: state.requirementsForm.elements,
              audience: state.requirementsForm.audience,
              channels: state.requirementsForm.channels,
              duration: state.requirementsForm.duration,
              aspect: state.requirementsForm.aspect,
              style: state.requirementsForm.style,
              mood: state.requirementsForm.mood,
              restrictions: state.requirementsForm.restrictions
            }
          };

          var project = await api('/api/creative/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(projectData)
          });

          state.projectId = project.id;
          state.project = project;
          state.activeProjectId = project.id;
          state.activeProject = project;
        }

        // Step 2: Trigger LLM storyboard analysis
        state.analysisStage = '正在调用 LLM 分析需求...';
        renderModule1();

        var task = await api('/api/creative/projects/' + state.projectId + '/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });

        // Step 3: Poll task until complete
        var taskId = task.id;
        await pollTask(taskId, function(progress, stage) {
          state.analysisStage = stage || '正在分析...';
          renderModule1();
        });

        // Step 4: Load shots from backend
        state.analysisStage = '正在加载分镜...';
        var shots = await api('/api/creative/projects/' + state.projectId + '/shots');
        state.shots = shots || [];

        // Init track data from shots
        state.trackData.video = [];
        for (var s = 0; s < state.shots.length; s++) {
          state.trackData.video.push({
            id: 'track-v-' + state.shots[s].id,
            shotId: state.shots[s].id,
            label: state.shots[s].scene_title || state.shots[s].title,
            start: s * (state.shots[s].duration_s || state.shots[s].duration || 10),
            duration: state.shots[s].duration_s || state.shots[s].duration || 10
          });
        }

        state.stepsCompleted[0] = true;
        state.analysisInProgress = false;
        state.analysisStage = '';
        updateFlowNav();
        saveToLocalStorage();
        renderModule1();
        updateProjectMetrics();
        showToast('需求分析完成，已生成 ' + state.shots.length + ' 个分镜', 'success');

      } catch (e) {
        state.analysisInProgress = false;
        state.analysisStage = '';
        if (e.message && e.message.indexOf('provider_not_configured') >= 0) {
          showToast('LLM 服务未配置，请先配置 LLM API Key', 'warning');
        } else {
          showToast('分析失败: ' + e.message, 'error');
        }
        renderModule1();
      }
    })();
  }

  // Poll a task until completion
  async function pollTask(taskId, onProgress) {
    var maxPolls = 120;
    for (var i = 0; i < maxPolls; i++) {
      await new Promise(function(r) { setTimeout(r, 2000); });
      var task = await api('/api/creative/tasks/' + taskId);
      if (onProgress) onProgress(task.progress || 0, task.stage || task.status);
      if (task.status === 'succeeded' || task.status === 'failed' || task.status === 'cancelled') {
        if (task.status === 'failed') {
          throw new Error(task.error_message || '任务执行失败');
        }
        return task;
      }
    }
    throw new Error('任务超时');
  }

  function renderShotCardsHTML() {
    var shots = getNormalizedShots();
    if (!shots || shots.length === 0) {
      return '<div class="empty-state">点击"分析需求"生成分镜脚本</div>';
    }

    var html = '';
    for (var i = 0; i < shots.length; i++) {
      var shot = shots[i];
      var statusClass = shot.status === 'confirmed' ? 'status-confirmed' : 'status-draft';
      var statusLabel = shot.status === 'confirmed' ? '已确认' : '草稿';
      var shotTypeLabels = {
        'wide-shot': '全景',
        'close-up': '特写',
        'macro': '微距',
        'medium-shot': '中景',
        'aerial': '航拍',
        'orbit': '环绕'
      };
      var shotTypeLabel = shotTypeLabels[shot.shotType] || shot.shotType;

      html += '<div class="shot-card" data-shot-id="' + escapeHtml(shot.shotId) + '">';
      html += '  <div class="shot-number-badge">' + shot.number + '</div>';
      html += '  <div class="shot-content">';
      html += '    <div class="shot-card-title" data-editable="title">' + escapeHtml(shot.title) + '</div>';
      html += '    <div class="shot-card-meta">';
      html += '      <span class="meta-chip">' + shot.duration + 's</span>';
      html += '      <span class="meta-chip">' + escapeHtml(shotTypeLabel) + '</span>';
      html += '    </div>';
      html += '    <div class="shot-desc">' + escapeHtml(shot.sceneDesc || '') + '</div>';
      html += '    <div class="shot-status-badge ' + statusClass + '">' + statusLabel + '</div>';
      html += '  </div>';
      html += '  <div class="shot-actions">';
      html += '    <button class="btn-icon btn-edit-shot" title="编辑" data-action="edit">&#9998;</button>';
      html += '    <button class="btn-icon btn-copy-shot" title="复制" data-action="copy">&#128203;</button>';
      html += '    <button class="btn-icon btn-delete-shot" title="删除" data-action="delete">&#128465;</button>';
      html += '    <button class="btn-icon btn-move-up" title="上移" data-action="move-up">&#9650;</button>';
      html += '    <button class="btn-icon btn-move-down" title="下移" data-action="move-down">&#9660;</button>';
      html += '    <button class="btn-icon btn-confirm-shot" title="确认" data-action="confirm">&#10003;</button>';
      html += '  </div>';
      html += '</div>';
    }
    return html;
  }

  function bindShotCardActions() {
    var grid = $('shot-cards-grid');
    if (!grid) return;

    grid.addEventListener('click', function(e) {
      var target = e.target.closest('[data-action]');
      if (!target) return;
      var card = target.closest('.shot-card');
      if (!card) return;
      var shotId = card.getAttribute('data-shot-id');
      var action = target.getAttribute('data-action');

      switch (action) {
        case 'edit': handleEditShot(shotId); break;
        case 'copy': handleCopyShot(shotId); break;
        case 'delete': handleDeleteShot(shotId); break;
        case 'move-up': handleMoveShot(shotId, -1); break;
        case 'move-down': handleMoveShot(shotId, 1); break;
        case 'confirm': handleConfirmShot(shotId); break;
      }
    });

    // Double-click on title to edit
    grid.addEventListener('dblclick', function(e) {
      var titleEl = e.target.closest('[data-editable="title"]');
      if (!titleEl) return;
      var card = titleEl.closest('.shot-card');
      if (!card) return;
      var shotId = card.getAttribute('data-shot-id');
      handleEditShot(shotId);
    });
  }

  function findShotById(shotId) {
    var shots = getShotsForActiveProject();
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].shotId === shotId) return shots[i];
    }
    return null;
  }

  function findShotIndex(shotId) {
    var shots = getShotsForActiveProject();
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].shotId === shotId) return i;
    }
    return -1;
  }

  function handleEditShot(shotId) {
    var shot = findShotById(shotId);
    if (!shot) return;

    showEditShotDialog(shot, function() {
    saveToLocalStorage();
    renderModule1();
    updatePreviewPanel(state.activeStep);
    showToast('分镜已更新', 'success');
  });
  }

  function handleCopyShot(shotId) {
    var shots = getShotsForActiveProject();
    var shot = findShotById(shotId);
    if (!shot) return;

    var newShot = JSON.parse(JSON.stringify(shot));
    var project = getActiveProject();
    newShot.shotId = project.id + '-shot-copy-' + Date.now();
    newShot.number = shots.length + 1;
    newShot.title = shot.title + ' (副本)';
    newShot.status = 'draft';
    shots.push(newShot);

    saveToLocalStorage();
    renderModule1();
    updateProjectMetrics();
    showToast('分镜已复制', 'success');
  }

  function handleDeleteShot(shotId) {
    showConfirmDialog('删除分镜', '确定要删除该分镜吗？', '删除', function() {
    var shots = getShotsForActiveProject();
    var idx = findShotIndex(shotId);
    if (idx === -1) return;
    shots.splice(idx, 1);
    // Renumber
    for (var i = 0; i < shots.length; i++) {
      shots[i].number = i + 1;
    }
    saveToLocalStorage();
    renderModule1();
    updateProjectMetrics();
    showToast('分镜已删除', 'info');
  });
  }

  function handleMoveShot(shotId, dir) {
    var shots = getShotsForActiveProject();
    var idx = findShotIndex(shotId);
    if (idx === -1) return;
    var newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= shots.length) return;

    var temp = shots[idx];
    shots[idx] = shots[newIdx];
    shots[newIdx] = temp;

    // Renumber
    for (var i = 0; i < shots.length; i++) {
      shots[i].number = i + 1;
    }

    saveToLocalStorage();
    renderModule1();
    updateProjectMetrics();
  }

  function handleConfirmShot(shotId) {
    var shot = findShotById(shotId);
    if (!shot) return;
    shot.status = (shot.status === 'confirmed') ? 'draft' : 'confirmed';

    // Update stepsCompleted: check if at least one shot is confirmed
    var shots = getShotsForActiveProject();
    var anyConfirmed = false;
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].status === 'confirmed') {
        anyConfirmed = true;
        break;
      }
    }
    state.stepsCompleted[0] = anyConfirmed;

    saveToLocalStorage();
    renderModule1();
    updateFlowNav();
    updateProjectMetrics();
    showToast(shot.status === 'confirmed' ? '分镜已确认' : '分镜已取消确认', 'info');
  }

  // ---------------------------------------------------------------
  // MODULE 2: Text-to-Image (Concept Images)
  // ---------------------------------------------------------------

  function renderModule2() {
    var confirmedShots = getConfirmedShots();
    if (confirmedShots.length === 0) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-icon">&#128248;</div><p>请先在模块1中确认至少一个分镜</p><button class="btn btn-primary" onclick="document.getElementById(\'flow-nav\').querySelector(\'[data-step=\\\'1\\\']\').click()">前往模块1</button></div>';
      return;
    }

    // Ensure activeShotIndex is valid
    if (state.activeShotIndex >= confirmedShots.length) {
      state.activeShotIndex = 0;
    }
    var currentShot = confirmedShots[state.activeShotIndex];
    var shotId = currentShot ? currentShot.shotId : null;

    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">概念图生成</h2>';
    html += '</div>';

    // Shot selector bar
    html += '<div class="shot-selector-bar">';
    html += '  <span class="selector-label">已确认分镜:</span>';
    html += '  <div class="selector-chips">';
    for (var i = 0; i < confirmedShots.length; i++) {
      var activeClass = (i === state.activeShotIndex) ? ' chip-active' : '';
      html += '    <button class="selector-chip' + activeClass + '" data-shot-select="' + i + '">#' + confirmedShots[i].number + ' ' + escapeHtml(confirmedShots[i].title) + '</button>';
    }
    html += '  </div>';
    html += '</div>';

    if (!currentShot) {
      html += '<div class="module-empty">请选择一个分镜</div>';
      els.studioContentPanel.innerHTML = html;
      bindShotSelector();
      return;
    }

    // Current shot info
    html += '<div class="current-shot-info card">';
    html += '  <h4>当前分镜: #' + currentShot.number + ' ' + escapeHtml(currentShot.title) + '</h4>';
    html += '  <div class="shot-details-grid">';
    html += '    <div><strong>场景:</strong> ' + escapeHtml(currentShot.sceneDesc || '') + '</div>';
    html += '    <div><strong>主体:</strong> ' + escapeHtml(currentShot.subjectDesc || '') + '</div>';
    html += '    <div><strong>动作:</strong> ' + escapeHtml(currentShot.actionDesc || '') + '</div>';
    html += '    <div><strong>光线:</strong> ' + escapeHtml(currentShot.lightingDesc || '') + '</div>';
    html += '  </div>';
    html += '</div>';

    // Prompt fields
    html += '<div class="prompt-fields card">';
    html += '  <div class="form-group"><label>正向提示词</label><textarea id="module2-keyframe-prompt" rows="2">' + escapeHtml(currentShot.keyframePrompt || '') + '</textarea></div>';
    html += '  <div class="form-group"><label>负向提示词</label><textarea id="module2-negative-prompt" rows="2">' + escapeHtml(currentShot.negativePrompt || '') + '</textarea></div>';
    html += '</div>';

    // Model selector
    html += '<div class="model-selector card">';
    html += '  <label>选择模型:</label>';
    html += '  <select id="module2-model">';
    html += '    <option value="seedance-1.5">Seedance-1.5</option>';
    html += '    <option value="midjourney-v6">Midjourney-v6</option>';
    html += '    <option value="luma-dreammachine">Luma-DreamMachine</option>';
    html += '    <option value="sdxl">SDXL</option>';
    html += '  </select>';
    if (state.imageGenInProgress) {
      html += '  <button class="btn btn-primary" disabled><span class="spinner"></span> 生成中...</button>';
    } else {
      html += '  <button class="btn btn-primary" id="btn-generate-concept">&#9889; 生成概念图</button>';
    }
    html += '</div>';

    // Concept images grid
    html += '<div class="concept-images-section">';
    html += renderConceptImagesHTML(shotId);
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind shot selectors
    bindShotSelector();

    // Bind prompt changes
    var kpEl = $('module2-keyframe-prompt');
    if (kpEl) {
      kpEl.addEventListener('input', function() {
        if (currentShot) currentShot.keyframePrompt = kpEl.value;
        saveToLocalStorage();
      });
    }
    var npEl = $('module2-negative-prompt');
    if (npEl) {
      npEl.addEventListener('input', function() {
        if (currentShot) currentShot.negativePrompt = npEl.value;
        saveToLocalStorage();
      });
    }

    // Generate button
    var genBtn = $('btn-generate-concept');
    if (genBtn) {
      genBtn.addEventListener('click', handleGenerateConceptImage);
    }

    // Bind image actions
    bindConceptImageActions(shotId);
  }

  function bindShotSelector() {
    var container = els.studioContentPanel;
    if (!container) return;
    var chips = container.querySelectorAll('[data-shot-select]');
    for (var i = 0; i < chips.length; i++) {
      (function(idx) {
        chips[i].addEventListener('click', function() {
          state.activeShotIndex = parseInt(idx, 10);
          saveToLocalStorage();
          renderModule2();
        });
      })(chips[i].getAttribute('data-shot-select'));
    }
  }

  function handleGenerateConceptImage() {
    if (state.imageGenInProgress) return;
    var shot = getActiveShot();
    if (!shot) return;

    state.imageGenInProgress = true;
    renderModule2();

    (async function() {
      try {
        if (!state.projectId) {
          throw new Error('请先创建项目');
        }

        var task = await api('/api/creative/shots/' + shot.id + '/images', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });

        await pollTask(task.id, function(progress, stage) {
          // Progress updates handled by pollTask
        });

        // Reload shot data
        var shots = await api('/api/creative/projects/' + state.projectId + '/shots');
        state.shots = shots || [];
        state.imageGenInProgress = false;
        state.stepsCompleted[1] = true;
        updateFlowNav();
        saveToLocalStorage();
        renderModule2();
        showToast('概念图生成完成', 'success');

      } catch (e) {
        state.imageGenInProgress = false;
        if (e.message && e.message.indexOf('provider_not_configured') >= 0) {
          showToast('ComfyUI 图片生成服务未配置', 'warning');
        } else {
          showToast('图片生成失败: ' + e.message, 'error');
        }
        renderModule2();
      }
    })();
  }

  function renderConceptImagesHTML(shotId) {
    var images = shotId && state.conceptImages[shotId] ? state.conceptImages[shotId] : [];
    if (!images || images.length === 0) {
      return '<div class="empty-state">点击"生成概念图"生成概念参考图</div>';
    }

    var html = '<div class="concept-image-grid">';
    for (var i = 0; i < images.length; i++) {
      var img = images[i];
      var gradient = 'linear-gradient(135deg, ' + img.colors.join(', ') + ')';
      var keyframeBadge = img.isKeyframe ? '<span class="keyframe-badge">&#9733; 关键帧</span>' : '';
      var favClass = img.isFavorite ? 'fav-active' : '';
      var label = 'Image ' + (i + 1);

      html += '<div class="concept-image-card" data-image-id="' + escapeHtml(img.id) + '">';
      html += '  <div class="concept-image-thumb" style="background: ' + gradient + ';">';
      html += '    <div class="concept-overlay">';
      html += '      <svg viewBox="0 0 64 64" width="48" height="48" fill="rgba(255,255,255,0.6)">';
      html += '        <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.8)" stroke-width="2" fill="none"/>';
      html += '        <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.5)"/>';
      html += '        <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.4)"/>';
      html += '        <rect x="14" y="40" width="12" height="2" rx="1" fill="rgba(255,255,255,0.3)"/>';
      html += '      </svg>';
      html += '    </div>';
      html += '    <div class="concept-hover-actions">';
      html += '      <button class="btn-icon-sm" data-action="set-keyframe" title="设为关键帧">&#9733;</button>';
      html += '      <button class="btn-icon-sm ' + favClass + '" data-action="favorite" title="收藏">&#9829;</button>';
      html += '      <button class="btn-icon-sm" data-action="view-large" title="查看大图">&#128269;</button>';
      html += '      <button class="btn-icon-sm" data-action="view-params" title="生成参数">&#9881;</button>';
      html += '      <button class="btn-icon-sm" data-action="delete-image" title="删除">&#128465;</button>';
      html += '    </div>';
      html += keyframeBadge;
      html += '  </div>';
      html += '  <div class="concept-image-info">';
      html += '    <span class="concept-image-label">' + label + '</span>';
      html += '    <span class="meta-chip">' + escapeHtml(img.modelLabel || img.model) + '</span>';
      html += '    <span class="meta-chip">#' + img.seed + '</span>';
      html += '  </div>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function bindConceptImageActions(shotId) {
    var container = els.studioContentPanel;
    if (!container) return;

    container.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var card = btn.closest('.concept-image-card');
      if (!card) return;
      var imageId = card.getAttribute('data-image-id');
      var action = btn.getAttribute('data-action');

      switch (action) {
        case 'set-keyframe': handleSetKeyframe(imageId); break;
        case 'favorite': handleFavoriteImage(imageId); break;
        case 'view-large': handleViewImageLarge(imageId); break;
        case 'view-params': handleViewImageParams(imageId); break;
        case 'delete-image': handleDeleteImage(imageId); break;
      }
    });
  }

  function findImageById(imageId) {
    var keys = Object.keys(state.conceptImages);
    for (var k = 0; k < keys.length; k++) {
      var arr = state.conceptImages[keys[k]];
      for (var i = 0; i < arr.length; i++) {
        if (arr[i].id === imageId) return arr[i];
      }
    }
    return null;
  }

  function findImageContainerShotId(imageId) {
    var keys = Object.keys(state.conceptImages);
    for (var k = 0; k < keys.length; k++) {
      var arr = state.conceptImages[keys[k]];
      for (var i = 0; i < arr.length; i++) {
        if (arr[i].id === imageId) return keys[k];
      }
    }
    return null;
  }

  function handleSetKeyframe(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    var shotId = img.shotId;
    var images = state.conceptImages[shotId] || [];
    for (var i = 0; i < images.length; i++) {
      images[i].isKeyframe = (images[i].id === imageId);
    }
    saveToLocalStorage();
    renderModule2();
    showToast('关键帧已设置', 'success');
  }

  function handleFavoriteImage(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    img.isFavorite = !img.isFavorite;
    saveToLocalStorage();
    renderModule2();
  }

  function handleViewImageLarge(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    var gradient = 'linear-gradient(135deg, ' + img.colors.join(', ') + ')';
    var html = '';
    html += '<div class="modal-overlay" id="image-modal">';
    html += '  <div class="modal-content modal-lg">';
    html += '    <button class="modal-close" id="modal-close-btn">&times;</button>';
    html += '    <div class="modal-body">';
    html += '      <div class="large-image" style="background: ' + gradient + '; width: 100%; aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center;">';
    html += '        <svg viewBox="0 0 64 64" width="96" height="96" fill="rgba(255,255,255,0.4)">';
    html += '          <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.6)" stroke-width="2" fill="none"/>';
    html += '          <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.3)"/>';
    html += '          <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.3)"/>';
    html += '        </svg>';
    html += '      </div>';
    html += '      <div class="image-details">';
    html += '        <p><strong>提示词:</strong> ' + escapeHtml(img.prompt) + '</p>';
    html += '        <p><strong>模型:</strong> ' + escapeHtml(img.modelLabel || img.model) + '</p>';
    html += '        <p><strong>种子:</strong> ' + img.seed + '</p>';
    html += '        <p><strong>分辨率:</strong> ' + img.width + 'x' + img.height + '</p>';
    html += '        <p><strong>关键帧:</strong> ' + (img.isKeyframe ? '是' : '否') + '</p>';
    html += '      </div>';
    html += '    </div>';
    html += '  </div>';
    html += '</div>';

    var modalContainer = document.createElement('div');
    modalContainer.innerHTML = html;
    document.body.appendChild(modalContainer.firstElementChild);

    var closeBtn = $('modal-close-btn');
    var modal = $('image-modal');
    if (closeBtn && modal) {
      closeBtn.addEventListener('click', function() {
        modal.parentNode.removeChild(modal);
      });
      modal.addEventListener('click', function(e) {
        if (e.target === modal) {
          modal.parentNode.removeChild(modal);
        }
      });
    }
  }

  function handleViewImageParams(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    var html = '';
    html += '<div class="modal-overlay" id="params-modal">';
    html += '  <div class="modal-content">';
    html += '    <button class="modal-close" id="params-close-btn">&times;</button>';
    html += '    <h3>生成参数</h3>';
    html += '    <div class="params-table">';
    html += '      <div class="param-row"><span class="param-label">模型</span><span>' + escapeHtml(img.modelLabel || img.model) + '</span></div>';
    html += '      <div class="param-row"><span class="param-label">分辨率</span><span>' + img.width + 'x' + img.height + '</span></div>';
    html += '      <div class="param-row"><span class="param-label">种子</span><span>' + img.seed + '</span></div>';
    html += '      <div class="param-row"><span class="param-label">步数</span><span>' + img.steps + '</span></div>';
    html += '      <div class="param-row"><span class="param-label">生成时间</span><span>' + escapeHtml(img.generatedAt) + '</span></div>';
    html += '      <div class="param-row"><span class="param-label">正向提示词</span><span class="param-prompt">' + escapeHtml(img.prompt) + '</span></div>';
    html += '    </div>';
    html += '  </div>';
    html += '</div>';

    var modalContainer = document.createElement('div');
    modalContainer.innerHTML = html;
    document.body.appendChild(modalContainer.firstElementChild);

    var closeBtn = $('params-close-btn');
    var modal = $('params-modal');
    if (closeBtn && modal) {
      closeBtn.addEventListener('click', function() {
        modal.parentNode.removeChild(modal);
      });
      modal.addEventListener('click', function(e) {
        if (e.target === modal) {
          modal.parentNode.removeChild(modal);
        }
      });
    }
  }

  function handleDeleteImage(imageId) {
    showConfirmDialog('删除概念图', '确定要删除该概念图吗？', '删除', function() {
    var shotId = findImageContainerShotId(imageId);
    if (!shotId) return;
    var images = state.conceptImages[shotId] || [];
    for (var i = 0; i < images.length; i++) {
      if (images[i].id === imageId) {
        images.splice(i, 1);
        break;
      }
    }
    if (images.length === 0) {
      delete state.conceptImages[shotId];
    }
    saveToLocalStorage();
    renderModule2();
  });
  }

  // ---------------------------------------------------------------
  // MODULE 3: Image-to-Video
  // ---------------------------------------------------------------

  function renderModule3() {
    var confirmedShots = getConfirmedShots();
    var shot = confirmedShots[state.activeShotIndex] || getActiveShot();
    var shotId = shot ? shot.shotId : null;

    // Check if current shot has a keyframe
    var images = shotId && state.conceptImages[shotId] ? state.conceptImages[shotId] : [];
    var keyframe = null;
    for (var i = 0; i < images.length; i++) {
      if (images[i].isKeyframe) {
        keyframe = images[i];
        break;
      }
    }

    if (!keyframe) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-icon">&#127916;</div><p>请先在模块2中为镜头设置关键帧</p><button class="btn btn-primary" onclick="document.getElementById(\'flow-nav\').querySelector(\'[data-step=\\\'2\\\']\').click()">前往模块2</button></div>';
      return;
    }

    var gradient = 'linear-gradient(135deg, ' + keyframe.colors.join(', ') + ')';
    var existingVideo = shotId && state.videoResults[shotId] ? state.videoResults[shotId] : null;

    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">视频生成</h2>';
    html += '</div>';

    // Keyframe display
    html += '<div class="keyframe-display card">';
    html += '  <h4>关键帧</h4>';
    html += '  <div class="keyframe-preview" style="background: ' + gradient + '; aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center;">';
    html += '    <svg viewBox="0 0 64 64" width="64" height="64" fill="rgba(255,255,255,0.4)">';
    html += '      <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.6)" stroke-width="2" fill="none"/>';
    html += '      <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.3)"/>';
    html += '      <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.3)"/>';
    html += '    </svg>';
    html += '  </div>';
    html += '  <p class="keyframe-prompt">' + escapeHtml(keyframe.prompt) + '</p>';
    html += '</div>';

    // Video params form
    html += '<div class="video-params card">';
    html += '  <h4>视频参数</h4>';
    html += '  <div class="form-grid">';
    html += '    <div class="form-group"><label>时长 (秒)</label><input type="range" id="vparam-duration" min="4" max="30" value="8" step="1" /><span id="vparam-duration-val">8s</span></div>';
    html += '    <div class="form-group"><label>运镜类型</label><select id="vparam-camera">';
    html += '      <option value="static">静态</option><option value="pan">平移</option><option value="tilt">俯仰</option><option value="zoom">变焦</option><option value="dolly">推进</option><option value="orbit">环绕</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>运动强度</label><input type="range" id="vparam-motion" min="1" max="5" value="3" step="1" /><span id="vparam-motion-val">3</span></div>';
    html += '    <div class="form-group"><label>稳定性</label><input type="range" id="vparam-stability" min="1" max="10" value="7" step="1" /><span id="vparam-stability-val">7</span></div>';
    html += '    <div class="form-group"><label>分辨率</label><select id="vparam-resolution">';
    html += '      <option value="720p">720p</option><option value="1080p" selected>1080p</option><option value="4K">4K</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>帧率</label><select id="vparam-fps">';
    html += '      <option value="24">24fps</option><option value="30" selected>30fps</option><option value="60">60fps</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>模型</label><select id="vparam-model">';
    html += '      <option value="seedance-1.5">Seedance-1.5</option><option value="luma-dreammachine">Luma-DreamMachine</option>';
    html += '    </select></div>';
    html += '  </div>';

    // Generate / Status
    if (state.videoGenInProgress) {
      html += '  <div class="video-progress">';
      html += '    <div class="progress-bar"><div class="progress-fill" style="width: ' + state.videoProgress + '%"></div></div>';
      html += '    <p class="progress-label">' + escapeHtml(state.videoGenStage) + ' (' + state.videoProgress + '%)</p>';
      html += '    <button class="btn btn-danger" id="btn-cancel-video">取消生成</button>';
      html += '  </div>';
    } else if (existingVideo && existingVideo.status === 'completed') {
      html += '  <div class="video-result">';
      html += '    <div class="video-placeholder" style="background: #000; aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center; position: relative;">';
      html += '      <svg viewBox="0 0 64 64" width="64" height="64" fill="rgba(255,255,255,0.3)">';
      html += '        <circle cx="32" cy="32" r="28" stroke="rgba(255,255,255,0.5)" stroke-width="2" fill="none"/>';
      html += '        <polygon points="26,20 26,44 46,32" fill="rgba(255,255,255,0.5)"/>';
      html += '      </svg>';
      html += '      <div class="video-corner-badge top-left">' + (existingVideo.duration || '8') + 's</div>';
      html += '      <div class="video-corner-badge bottom-right">' + escapeHtml(existingVideo.resolution || '1080p') + '</div>';
      html += '    </div>';
      html += '    <div class="video-actions">';
      html += '      <button class="btn btn-secondary" id="btn-regenerate-video">重新生成</button>';
      html += '    </div>';
      html += '  </div>';
    } else {
      html += '  <div class="form-actions">';
      html += '    <button class="btn btn-primary" id="btn-generate-video">&#127916; 生成视频</button>';
      html += '  </div>';
    }
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind range sliders
    bindVideoRangeSliders();

    // Generate button
    var genBtn = $('btn-generate-video');
    if (genBtn) {
      genBtn.addEventListener('click', handleGenerateVideo);
    }

    // Cancel button
    var cancelBtn = $('btn-cancel-video');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', handleCancelVideo);
    }

    // Regenerate button
    var regenBtn = $('btn-regenerate-video');
    if (regenBtn) {
      regenBtn.addEventListener('click', handleRegenerateVideo);
    }
  }

  function bindVideoRangeSliders() {
    var durSlider = $('vparam-duration');
    var durVal = $('vparam-duration-val');
    if (durSlider && durVal) {
      durSlider.addEventListener('input', function() {
        durVal.textContent = durSlider.value + 's';
      });
    }
    var motSlider = $('vparam-motion');
    var motVal = $('vparam-motion-val');
    if (motSlider && motVal) {
      motSlider.addEventListener('input', function() {
        motVal.textContent = motSlider.value;
      });
    }
    var stabSlider = $('vparam-stability');
    var stabVal = $('vparam-stability-val');
    if (stabSlider && stabVal) {
      stabSlider.addEventListener('input', function() {
        stabVal.textContent = stabSlider.value;
      });
    }
  }

  function handleGenerateVideo() {
    if (state.videoGenInProgress) return;
    var shot = getActiveShot();
    if (!shot) return;

    state.videoGenInProgress = true;
    state.videoProgress = 0;
    state.videoCancelRequested = false;
    state.videoGenStage = '提交中...';
    renderModule3();

    (async function() {
      try {
        if (!state.projectId) {
          throw new Error('请先创建项目');
        }

        var task = await api('/api/creative/shots/' + shot.id + '/videos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });

        await pollTask(task.id, function(progress, stage) {
          state.videoProgress = progress || 0;
          state.videoGenStage = stage || '生成中...';
          renderModule3();
        });

        // Reload shots
        var shots = await api('/api/creative/projects/' + state.projectId + '/shots');
        state.shots = shots || [];

        // Update shot reference
        for (var i = 0; i < state.shots.length; i++) {
          if (state.shots[i].id === shot.id) {
            shot = state.shots[i];
            break;
          }
        }

        state.videoGenInProgress = false;
        state.videoProgress = 100;
        state.videoGenStage = '完成';
        state.videoResults[shot.id] = {
          id: 'video-' + shot.id,
          shotId: shot.id,
          video_url: shot.video_url,
          status: 'completed',
          progress: 100
        };
        state.stepsCompleted[2] = true;
        updateFlowNav();
        saveToLocalStorage();
        renderModule3();
        showToast('视频生成完成', 'success');

      } catch (e) {
        state.videoGenInProgress = false;
        state.videoProgress = 0;
        state.videoGenStage = '';
        if (e.message && e.message.indexOf('provider_not_configured') >= 0) {
          showToast('视频生成服务未配置', 'warning');
        } else {
          showToast('视频生成失败: ' + e.message, 'error');
        }
        renderModule3();
      }
    })();
  }

  function handleCancelVideo() {
    state.videoCancelRequested = true;
    showToast('正在取消...', 'info');
  }

  function handleRegenerateVideo() {
    var shot = getActiveShot();
    if (!shot) return;
    if (state.videoResults[shot.shotId]) {
      delete state.videoResults[shot.shotId];
    }
    state.stepsCompleted[2] = false;
    saveToLocalStorage();
    handleGenerateVideo();
  }

  // ---------------------------------------------------------------
  // MODULE 4: Multimodal Enhancement
  // ---------------------------------------------------------------

  function renderModule4() {
    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">多模态增强</h2>';
    html += '</div>';

    // Narration Panel
    html += '<div class="enhance-section card">';
    html += '  <h3 class="collapsible-header" data-collapse="narration">配音 &#9660;</h3>';
    html += '  <div class="collapsible-body" id="collapse-narration">';
    html += renderNarrationPanelHTML();
    html += '  </div>';
    html += '</div>';

    // Music Panel
    html += '<div class="enhance-section card">';
    html += '  <h3 class="collapsible-header" data-collapse="music">背景音乐 &#9660;</h3>';
    html += '  <div class="collapsible-body" id="collapse-music">';
    html += renderMusicPanelHTML();
    html += '  </div>';
    html += '</div>';

    // Effects Panel
    html += '<div class="enhance-section card">';
    html += '  <h3 class="collapsible-header" data-collapse="effects">音效 &#9660;</h3>';
    html += '  <div class="collapsible-body" id="collapse-effects">';
    html += renderEffectsPanelHTML();
    html += '  </div>';
    html += '</div>';

    // Timeline
    html += '<div class="enhance-section card">';
    html += '  <h3 class="collapsible-header" data-collapse="timeline">时间线 &#9660;</h3>';
    html += '  <div class="collapsible-body" id="collapse-timeline">';
    html += renderSimplifiedTimelineHTML();
    html += '  </div>';
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind collapsible headers
    var headers = els.studioContentPanel.querySelectorAll('.collapsible-header');
    for (var h = 0; h < headers.length; h++) {
      (function(header) {
        header.addEventListener('click', function() {
          var targetId = header.getAttribute('data-collapse');
          var body = $('collapse-' + targetId);
          if (body) {
            if (body.style.display === 'none') {
              body.style.display = 'block';
              header.innerHTML = header.innerHTML.replace('&#9650;', '&#9660;');
            } else {
              body.style.display = 'none';
              header.innerHTML = header.innerHTML.replace('&#9660;', '&#9650;');
            }
          }
        });
      })(headers[h]);
    }

    // Bind narration form
    bindNarrationForm();
    bindMusicForm();
    bindEffectsForm();
    bindTimelineEvents();
  }

  // Narration
  function renderNarrationPanelHTML() {
    var voices = [
      { id: 'vp-001', label: '沉稳男声', desc: '低沉磁性，适合纪录片' },
      { id: 'vp-002', label: '温柔女声', desc: '柔和亲切，适合导览' },
      { id: 'vp-003', label: '博物馆讲解员', desc: '专业端庄，标准播音' },
      { id: 'vp-004', label: '古风旁白', desc: '古典韵味，适合文化题材' }
    ];

    var shot = getActiveShot();
    var narrationText = shot ? (shot.narration || '') : '';

    var html = '';
    html += '<div class="voice-selector">';
    html += '  <label>配音角色:</label>';
    html += '  <div class="voice-radio-group">';
    for (var i = 0; i < voices.length; i++) {
      var checked = state.narrationForm.voiceId === voices[i].id ? ' checked' : '';
      html += '    <label class="voice-radio-card' + (checked ? ' card-selected' : '') + '">';
      html += '      <input type="radio" name="voice" value="' + voices[i].id + '"' + checked + ' />';
      html += '      <span class="voice-name">' + escapeHtml(voices[i].label) + '</span>';
      html += '      <span class="voice-desc">' + escapeHtml(voices[i].desc) + '</span>';
      html += '    </label>';
    }
    html += '  </div>';
    html += '</div>';

    html += '<div class="form-grid">';
    html += '  <div class="form-group"><label>语速: ' + state.narrationForm.speechRate.toFixed(1) + 'x</label><input type="range" id="narration-rate" min="0.5" max="2.0" step="0.1" value="' + state.narrationForm.speechRate + '" /></div>';
    html += '  <div class="form-group"><label>音量: ' + state.narrationForm.volume.toFixed(1) + '</label><input type="range" id="narration-volume" min="0" max="1.0" step="0.1" value="' + state.narrationForm.volume + '" /></div>';
    html += '</div>';
    html += '<div class="form-group"><label>配音文案</label><textarea id="narration-text" rows="3">' + escapeHtml(narrationText) + '</textarea></div>';
    html += '<p class="hint">当前未接入真实语音克隆服务</p>';
    html += '<button class="btn btn-primary" id="btn-generate-narration">生成配音</button>';

    return html;
  }

  function bindNarrationForm() {
    // Voice radio
    var voiceRadios = els.studioContentPanel.querySelectorAll('input[name="voice"]');
    for (var i = 0; i < voiceRadios.length; i++) {
      (function(r) {
        r.addEventListener('change', function() {
          if (r.checked) {
            state.narrationForm.voiceId = r.value;
            // Update card styles
            var cards = els.studioContentPanel.querySelectorAll('.voice-radio-card');
            for (var c = 0; c < cards.length; c++) {
              cards[c].classList.remove('card-selected');
            }
            r.closest('.voice-radio-card').classList.add('card-selected');
            saveToLocalStorage();
          }
        });
      })(voiceRadios[i]);
    }

    var rateSlider = $('narration-rate');
    if (rateSlider) {
      rateSlider.addEventListener('input', function() {
        state.narrationForm.speechRate = parseFloat(rateSlider.value);
        var label = rateSlider.parentElement.querySelector('label');
        if (label) label.textContent = '语速: ' + state.narrationForm.speechRate.toFixed(1) + 'x';
        saveToLocalStorage();
      });
    }

    var volSlider = $('narration-volume');
    if (volSlider) {
      volSlider.addEventListener('input', function() {
        state.narrationForm.volume = parseFloat(volSlider.value);
        var label = volSlider.parentElement.querySelector('label');
        if (label) label.textContent = '音量: ' + state.narrationForm.volume.toFixed(1);
        saveToLocalStorage();
      });
    }

    var narText = $('narration-text');
    if (narText) {
      narText.addEventListener('input', function() {
        var shot = getActiveShot();
        if (shot) {
          shot.narration = narText.value;
          saveToLocalStorage();
        }
      });
    }

    var genBtn = $('btn-generate-narration');
    if (genBtn) {
      genBtn.addEventListener('click', function() {
        showToast('配音生成中', 'info');
        setTimeout(function() {
          showToast('配音已生成', 'success');
        }, 1500);
      });
    }
  }

  // Music
  function renderMusicPanelHTML() {
    var musicOptions = [
      { id: 'none', label: '无', icon: '&#10060;' },
      { id: 'classical', label: '古典', icon: '&#127929;' },
      { id: 'folk', label: '民乐', icon: '&#127926;' },
      { id: 'ambient', label: '环境音', icon: '&#127907;' },
      { id: 'electronic', label: '电子', icon: '&#128288;' },
      { id: 'custom', label: '自定义', icon: '&#128196;' }
    ];

    var html = '';
    html += '<div class="music-option-grid">';
    for (var i = 0; i < musicOptions.length; i++) {
      var selected = state.narrationForm.backgroundMusic === musicOptions[i].id ? ' music-selected' : '';
      html += '  <div class="music-option-card' + selected + '" data-music-id="' + musicOptions[i].id + '">';
      html += '    <div class="music-icon">' + musicOptions[i].icon + '</div>';
      html += '    <div class="music-label">' + escapeHtml(musicOptions[i].label) + '</div>';
      html += '  </div>';
    }
    html += '</div>';
    html += '<div class="form-group"><label>音乐音量: ' + state.narrationForm.musicVolume.toFixed(1) + '</label><input type="range" id="music-volume" min="0" max="1.0" step="0.1" value="' + state.narrationForm.musicVolume + '" /></div>';
    html += '<button class="btn btn-secondary" id="btn-preview-music">预览</button>';

    return html;
  }

  function bindMusicForm() {
    var container = els.studioContentPanel;
    if (!container) return;

    var musicCards = container.querySelectorAll('[data-music-id]');
    for (var i = 0; i < musicCards.length; i++) {
      (function(card) {
        card.addEventListener('click', function() {
          var mid = card.getAttribute('data-music-id');
          state.narrationForm.backgroundMusic = mid;
          var allCards = container.querySelectorAll('[data-music-id]');
          for (var c = 0; c < allCards.length; c++) {
            allCards[c].classList.remove('music-selected');
          }
          card.classList.add('music-selected');
          saveToLocalStorage();
        });
      })(musicCards[i]);
    }

    var volSlider = $('music-volume');
    if (volSlider) {
      volSlider.addEventListener('input', function() {
        state.narrationForm.musicVolume = parseFloat(volSlider.value);
        var label = volSlider.parentElement.querySelector('label');
        if (label) label.textContent = '音乐音量: ' + state.narrationForm.musicVolume.toFixed(1);
        saveToLocalStorage();
      });
    }

    var previewBtn = $('btn-preview-music');
    if (previewBtn) {
      previewBtn.addEventListener('click', function() {
        showToast('音乐预览', 'info');
      });
    }
  }

  // Effects
  function renderEffectsPanelHTML() {
    var presets = [];
    if (state.demoData && state.demoData.effectPresets) {
      presets = state.demoData.effectPresets;
    } else {
      presets = [
        { id: 'ef-001', name: '大门回声', icon: '&#128227;' },
        { id: 'ef-002', name: '脚步', icon: '&#128694;' },
        { id: 'ef-003', name: '翻页', icon: '&#128214;' },
        { id: 'ef-004', name: '掌声', icon: '&#128079;' },
        { id: 'ef-005', name: '钟声', icon: '&#128343;' }
      ];
    }

    var activeEffects = state.trackData.effects || [];

    var html = '';
    html += '<div class="effects-grid">';
    for (var i = 0; i < presets.length; i++) {
      var isSelected = false;
      for (var e = 0; e < activeEffects.length; e++) {
        if (activeEffects[e].presetId === presets[i].id) {
          isSelected = true;
          break;
        }
      }
      html += '  <div class="effect-card' + (isSelected ? ' effect-selected' : '') + '" data-preset-id="' + escapeHtml(presets[i].id) + '">';
      html += '    <div class="effect-icon">' + (presets[i].icon || '&#128266;') + '</div>';
      html += '    <div class="effect-name">' + escapeHtml(presets[i].name) + '</div>';
      html += '  </div>';
    }
    html += '</div>';

    return html;
  }

  function bindEffectsForm() {
    var container = els.studioContentPanel;
    if (!container) return;

    container.addEventListener('click', function(e) {
      var card = e.target.closest('[data-preset-id]');
      if (!card) return;
      var presetId = card.getAttribute('data-preset-id');
      var effects = state.trackData.effects || [];

      // Toggle selection
      var found = false;
      for (var i = 0; i < effects.length; i++) {
        if (effects[i].presetId === presetId) {
          effects.splice(i, 1);
          found = true;
          break;
        }
      }

      if (!found) {
        // Find preset name
        var presets = (state.demoData && state.demoData.effectPresets) || [];
        var presetName = presetId;
        for (var p = 0; p < presets.length; p++) {
          if (presets[p].id === presetId) {
            presetName = presets[p].name;
            break;
          }
        }
        effects.push({
          id: 'effect-' + Date.now(),
          presetId: presetId,
          name: presetName,
          start: 0,
          duration: 3
        });
      }

      state.trackData.effects = effects;
      saveToLocalStorage();
      renderModule4();
    });
  }

  // Timeline
  function renderSimplifiedTimelineHTML() {
    var tracks = [
      { key: 'video', label: '视频轨', icon: '&#127916;' },
      { key: 'narration', label: '配音轨', icon: '&#127897;' },
      { key: 'music', label: '音乐轨', icon: '&#127925;' },
      { key: 'effects', label: '音效轨', icon: '&#128266;' },
      { key: 'subtitles', label: '字幕轨', icon: '&#128196;' }
    ];

    var totalDuration = 0;
    var shots = getShotsForActiveProject();
    for (var s = 0; s < shots.length; s++) {
      totalDuration += (shots[s].duration || 10);
    }
    if (totalDuration < 10) totalDuration = 60;

    var html = '<div class="timeline-container">';

    for (var t = 0; t < tracks.length; t++) {
      var track = tracks[t];
      var blocks = state.trackData[track.key] || [];

      html += '<div class="timeline-track" data-track="' + track.key + '">';
      html += '  <div class="timeline-track-label">' + track.icon + ' ' + escapeHtml(track.label) + '</div>';
      html += '  <div class="timeline-track-content">';
      html += '    <div class="track-ruler"></div>';

      for (var b = 0; b < blocks.length; b++) {
        var block = blocks[b];
        var blockStart = block.start || 0;
        var blockDur = block.duration || 5;
        var leftPct = (blockStart / totalDuration) * 100;
        var widthPct = (blockDur / totalDuration) * 100;
        var mutedClass = block.muted ? 'block-muted' : '';

        html += '    <div class="timeline-block ' + mutedClass + '" data-track="' + track.key + '" data-block-index="' + b + '" style="left: ' + leftPct + '%; width: ' + widthPct + '%;" title="' + escapeHtml(block.label || '') + ' (' + blockStart + 's, ' + blockDur + 's)">';
        html += '      <span class="block-label">' + escapeHtml(block.label || '') + '</span>';
        html += '      <span class="block-time">' + blockStart + 's | ' + blockDur + 's</span>';
        html += '      <button class="block-delete" data-action="delete-block" data-track="' + track.key + '" data-block-index="' + b + '">&times;</button>';
        html += '      <button class="block-mute-btn" data-action="mute-block" data-track="' + track.key + '" data-block-index="' + b + '">' + (block.muted ? '&#128263;' : '&#128266;') + '</button>';
        html += '    </div>';
      }

      html += '    <button class="btn-add-block" data-action="add-block" data-track="' + track.key + '">+</button>';
      html += '  </div>';
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  function bindTimelineEvents() {
    var container = els.studioContentPanel;
    if (!container) return;

    container.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var trackKey = btn.getAttribute('data-track');

      switch (action) {
        case 'add-block': handleAddTrackBlock(trackKey); break;
        case 'delete-block': {
          var blockIdx = parseInt(btn.getAttribute('data-block-index'), 10);
          handleDeleteTrackBlock(trackKey, blockIdx);
          break;
        }
        case 'mute-block': {
          var bIdx = parseInt(btn.getAttribute('data-block-index'), 10);
          handleToggleMuteBlock(trackKey, bIdx);
          break;
        }
      }
    });

    // Double click to edit block
    container.addEventListener('dblclick', function(e) {
      var block = e.target.closest('.timeline-block');
      if (!block) return;
      var trackKey = block.getAttribute('data-track');
      var blockIdx = parseInt(block.getAttribute('data-block-index'), 10);
      if (!isNaN(blockIdx)) {
        handleEditTrackBlock(trackKey, blockIdx);
      }
    });
  }

  function handleAddTrackBlock(trackKey) {
    var blocks = state.trackData[trackKey] || [];
    var shots = getShotsForActiveProject();
    var start = 0;
    if (blocks.length > 0) {
      var last = blocks[blocks.length - 1];
      start = (last.start || 0) + (last.duration || 5);
    }
    blocks.push({
      id: 'block-' + trackKey + '-' + Date.now(),
      label: trackKey === 'subtitles' ? '字幕片段' : '新片段',
      start: start,
      duration: 5,
      muted: false
    });
    state.trackData[trackKey] = blocks;
    saveToLocalStorage();
    renderModule4();
  }

  function handleDeleteTrackBlock(trackKey, blockIndex) {
    showConfirmDialog('删除片段', '确定要删除该片段吗？', '删除', function() {
    var blocks = state.trackData[trackKey] || [];
    if (blockIndex >= 0 && blockIndex < blocks.length) {
      blocks.splice(blockIndex, 1);
      state.trackData[trackKey] = blocks;
      saveToLocalStorage();
      renderModule4();
    }
  });
  }

  function handleEditTrackBlock(trackKey, blockIndex) {
    var blocks = state.trackData[trackKey] || [];
    var block = blocks[blockIndex];
    if (!block) return;

    // Calculate total project duration for max start time
    var project = getActiveProject();
    var totalDur = 300;
    if (project && project.shots) {
      var sum = 0;
      for (var si = 0; si < project.shots.length; si++) {
        sum += project.shots[si].duration || 0;
      }
      if (sum > 0) totalDur = sum;
    }

    showEditTrackBlockDialog(block, function(updatedBlock) {
    state.trackData[trackKey] = blocks;
    saveToLocalStorage();
    renderModule4();
    showToast('片段已更新', 'success');
  }, totalDur);
  }

  function handleToggleMuteBlock(trackKey, blockIndex) {
    var blocks = state.trackData[trackKey] || [];
    var block = blocks[blockIndex];
    if (!block) return;
    block.muted = !block.muted;
    state.trackData[trackKey] = blocks;
    saveToLocalStorage();
    renderModule4();
  }

  // ---------------------------------------------------------------
  // MODULE 5: Human-AI Refinement
  // ---------------------------------------------------------------

  function renderModule5() {
    var filterStyle = getFilterStyleString();

    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">人机精调</h2>';
    html += '</div>';

    // Comparison layout
    html += '<div class="comparison-layout">';
    html += '  <div class="compare-panel">';
    html += '    <h4>原始画面</h4>';
    html += '    <div class="compare-image original-image" style="background: linear-gradient(135deg, #2d3436, #636e72, #b2bec3); aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center;">';
    html += '      <svg viewBox="0 0 64 64" width="48" height="48" fill="rgba(255,255,255,0.3)">';
    html += '        <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.5)" stroke-width="2" fill="none"/>';
    html += '        <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.2)"/>';
    html += '        <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.2)"/>';
    html += '      </svg>';
    html += '    </div>';
    html += '  </div>';
    html += '  <div class="compare-panel">';
    html += '    <h4>精调画面</h4>';
    html += '    <div class="compare-image refined-image" id="refined-image" style="background: linear-gradient(135deg, #2d3436, #636e72, #b2bec3); aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center; filter: ' + filterStyle + ';">';
    html += '      <svg viewBox="0 0 64 64" width="48" height="48" fill="rgba(255,255,255,0.3)">';
    html += '        <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.5)" stroke-width="2" fill="none"/>';
    html += '        <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.2)"/>';
    html += '        <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.2)"/>';
    html += '      </svg>';
    html += '    </div>';
    html += '  </div>';
    html += '</div>';

    // Filter Controls
    html += '<div class="filter-controls card">';
    html += '  <h4>基础滤镜</h4>';
    html += '  <div class="filter-grid">';
    html += '    <div class="filter-item"><label>亮度: <span id="fp-brightness-val">' + state.filterParams.brightness + '</span>%</label><input type="range" class="filter-slider" data-param="brightness" min="0" max="200" value="' + state.filterParams.brightness + '" /></div>';
    html += '    <div class="filter-item"><label>对比度: <span id="fp-contrast-val">' + state.filterParams.contrast + '</span>%</label><input type="range" class="filter-slider" data-param="contrast" min="0" max="200" value="' + state.filterParams.contrast + '" /></div>';
    html += '    <div class="filter-item"><label>饱和度: <span id="fp-saturation-val">' + state.filterParams.saturation + '</span>%</label><input type="range" class="filter-slider" data-param="saturation" min="0" max="200" value="' + state.filterParams.saturation + '" /></div>';
    html += '    <div class="filter-item"><label>模糊: <span id="fp-blur-val">' + state.filterParams.blur + '</span>px</label><input type="range" class="filter-slider" data-param="blur" min="0" max="10" step="0.5" value="' + state.filterParams.blur + '" /></div>';
    html += '    <div class="filter-item"><label>暖调偏移: <span id="fp-hue-val">' + state.filterParams.hueRotate + '</span>deg</label><input type="range" class="filter-slider" data-param="hueRotate" min="0" max="360" value="' + state.filterParams.hueRotate + '" /></div>';
    html += '    <div class="filter-item"><label>怀旧: <span id="fp-sepia-val">' + state.filterParams.sepia + '</span>%</label><input type="range" class="filter-slider" data-param="sepia" min="0" max="100" value="' + state.filterParams.sepia + '" /></div>';
    html += '  </div>';
    html += '</div>';

    // Human params
    html += '<div class="human-params card">';
    html += '  <h4>专业调色</h4>';
    html += '  <div class="human-params-grid">';
    html += '    <div class="filter-item"><label>曝光: <span id="hp-exposure-val">' + state.humanParams.exposure + '</span></label><input type="range" class="human-slider" data-param="exposure" min="-5" max="5" step="0.1" value="' + state.humanParams.exposure + '" /></div>';
    html += '    <div class="filter-item"><label>对比度: <span id="hp-contrast-val">' + state.humanParams.contrast + '</span></label><input type="range" class="human-slider" data-param="contrast" min="-100" max="100" value="' + state.humanParams.contrast + '" /></div>';
    html += '    <div class="filter-item"><label>高光: <span id="hp-highlights-val">' + state.humanParams.highlights + '</span></label><input type="range" class="human-slider" data-param="highlights" min="-100" max="100" value="' + state.humanParams.highlights + '" /></div>';
    html += '    <div class="filter-item"><label>阴影: <span id="hp-shadows-val">' + state.humanParams.shadows + '</span></label><input type="range" class="human-slider" data-param="shadows" min="-100" max="100" value="' + state.humanParams.shadows + '" /></div>';
    html += '    <div class="filter-item"><label>色温: <span id="hp-temperature-val">' + state.humanParams.temperature + '</span></label><input type="range" class="human-slider" data-param="temperature" min="-100" max="100" value="' + state.humanParams.temperature + '" /></div>';
    html += '    <div class="filter-item"><label>饱和度: <span id="hp-saturation-val">' + state.humanParams.saturation + '</span></label><input type="range" class="human-slider" data-param="saturation" min="-100" max="100" value="' + state.humanParams.saturation + '" /></div>';
    html += '    <div class="filter-item"><label>清晰度: <span id="hp-clarity-val">' + state.humanParams.clarity + '</span></label><input type="range" class="human-slider" data-param="clarity" min="0" max="100" value="' + state.humanParams.clarity + '" /></div>';
    html += '    <div class="filter-item"><label>锐化: <span id="hp-sharpening-val">' + state.humanParams.sharpening + '</span></label><input type="range" class="human-slider" data-param="sharpening" min="0" max="100" value="' + state.humanParams.sharpening + '" /></div>';
    html += '  </div>';
    html += '</div>';

    // AI Batch
    html += '<div class="ai-batch card">';
    html += '  <h4>AI 批量处理</h4>';
    html += '  <div class="ai-batch-grid">';

    var batchItems = [
      { id: 'blur-fix', label: '模糊修复', desc: '修复画面模糊' },
      { id: 'denoise', label: '降噪处理', desc: '减少画面噪点' },
      { id: 'color-restore', label: '色彩修复', desc: '还原真实色彩' },
      { id: 'detail-enhance', label: '细节增强', desc: '增强纹理细节' },
      { id: 'super-res', label: '超分辨率', desc: '提升画面分辨率' },
      { id: 'frame-expand', label: '帧扩展', desc: '扩展画面边缘' }
    ];

    for (var bi = 0; bi < batchItems.length; bi++) {
      html += '    <label class="batch-checkbox">';
      html += '      <input type="checkbox" class="batch-option" value="' + batchItems[bi].id + '" />';
      html += '      <span class="batch-label">' + escapeHtml(batchItems[bi].label) + '</span>';
      html += '      <span class="batch-desc">' + escapeHtml(batchItems[bi].desc) + '</span>';
      html += '    </label>';
    }

    html += '  </div>';

    if (state.aiBatchInProgress) {
      html += '  <div class="batch-progress">';
      html += '    <div class="progress-bar"><div class="progress-fill progress-animate"></div></div>';
      html += '    <p class="progress-label">AI 处理中...</p>';
      html += '  </div>';
    } else {
      html += '  <button class="btn btn-primary" id="btn-start-ai-batch">&#9889; 开始 AI 批量处理</button>';
    }
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind filter sliders
    bindFilterSliders();
    bindHumanSliders();
    bindAiBatch();
  }

  function getFilterStyleString() {
    var fp = state.filterParams;
    var parts = [];
    parts.push('brightness(' + fp.brightness + '%)');
    parts.push('contrast(' + fp.contrast + '%)');
    parts.push('saturate(' + fp.saturation + '%)');
    parts.push('blur(' + fp.blur + 'px)');
    parts.push('hue-rotate(' + fp.hueRotate + 'deg)');
    parts.push('sepia(' + fp.sepia + '%)');
    return parts.join(' ');
  }

  function bindFilterSliders() {
    var sliders = els.studioContentPanel.querySelectorAll('.filter-slider');
    for (var i = 0; i < sliders.length; i++) {
      (function(slider) {
        slider.addEventListener('input', function() {
          var param = slider.getAttribute('data-param');
          var val = parseFloat(slider.value);
          state.filterParams[param] = val;
          // Update label display
          var valSpan = $('fp-' + param + '-val');
          if (valSpan) {
            var suffix = (param === 'blur') ? 'px' : (param === 'hueRotate') ? 'deg' : (param === 'sepia') ? '%' : '%';
            valSpan.textContent = val + suffix;
          }
          // Update refined image filter
          var refinedImg = $('refined-image');
          if (refinedImg) {
            refinedImg.style.filter = getFilterStyleString();
          }
          saveToLocalStorage();
        });
      })(sliders[i]);
    }
  }

  function bindHumanSliders() {
    var sliders = els.studioContentPanel.querySelectorAll('.human-slider');
    for (var i = 0; i < sliders.length; i++) {
      (function(slider) {
        slider.addEventListener('input', function() {
          var param = slider.getAttribute('data-param');
          var val = parseFloat(slider.value);
          state.humanParams[param] = val;
          var valSpan = $('hp-' + param + '-val');
          if (valSpan) {
            valSpan.textContent = val;
          }
          saveToLocalStorage();
        });
      })(sliders[i]);
    }
  }

  function bindAiBatch() {
    var btn = $('btn-start-ai-batch');
    if (!btn) return;

    btn.addEventListener('click', handleStartAiBatch);
  }

  function handleStartAiBatch() {
    if (state.aiBatchInProgress) return;

    // Check if any options selected
    var options = els.studioContentPanel.querySelectorAll('.batch-option:checked');
    if (options.length === 0) {
      showToast('请至少选择一个处理选项', 'warning');
      return;
    }

    state.aiBatchInProgress = true;
    renderModule5();

    var stages = [
      { label: '分析画面特征...', delay: 1000 },
      { label: '准备处理资源...', delay: 1000 },
      { label: '执行批量处理...', delay: 1200 },
      { label: '完成处理', delay: 800 }
    ];

    var stepIndex = 0;

    function runStage() {
      if (stepIndex >= stages.length) {
        state.aiBatchInProgress = false;
        renderModule5();
        showToast('AI 批量处理完成', 'success');
        return;
      }
      stepIndex++;
      state.aiBatchTimer = setTimeout(runStage, stages[stepIndex - 1].delay);
    }

    runStage();
  }

  // ---------------------------------------------------------------
  // MODULE 6: Output Adaptation
  // ---------------------------------------------------------------

  function renderModule6() {
    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">输出适配</h2>';
    html += '</div>';

    // Platform selector
    html += '<div class="platform-section card">';
    html += '  <h4>选择输出平台</h4>';
    html += '  <div class="platform-grid">';

    var platforms = [
      { id: 'museum-screen', name: '博物馆大屏', desc: '4K/60fps', icon: '&#128225;' },
      { id: 'online-gallery', name: '线上展厅', desc: '1080p/30fps', icon: '&#127760;' },
      { id: 'social-vertical', name: '社交媒体竖版', desc: '1080x1920/30fps', icon: '&#128241;' },
      { id: 'vr-device', name: 'VR设备', desc: '360/立体声', icon: '&#127911;' },
      { id: 'douyin-bilibili', name: '抖音/B站', desc: '1080p/30fps', icon: '&#127916;' },
      { id: 'wechat-video', name: '微信视频号', desc: '720p/30fps', icon: '&#128172;' },
      { id: 'academic', name: '学术会议', desc: '4K/24fps', icon: '&#127891;' },
      { id: 'mobile', name: '移动端', desc: '720p/30fps', icon: '&#128242;' },
      { id: 'custom', name: '自定义', desc: '自由配置', icon: '&#9881;' }
    ];

    for (var pi = 0; pi < platforms.length; pi++) {
      var p = platforms[pi];
      var platSelected = state.outputForm.platformId === p.id ? ' platform-selected' : '';
      html += '    <div class="platform-card' + platSelected + '" data-platform-id="' + p.id + '">';
      html += '      <div class="platform-icon">' + p.icon + '</div>';
      html += '      <div class="platform-name">' + escapeHtml(p.name) + '</div>';
      html += '      <div class="platform-card-desc">' + escapeHtml(p.desc) + '</div>';
      html += '    </div>';
    }

    html += '  </div>';
    html += '</div>';

    // Parameter form
    html += '<div class="output-params card">';
    html += '  <h4>导出参数</h4>';
    html += '  <div class="form-grid">';
    html += '    <div class="form-group"><label>封装格式</label><select id="out-format">';
    html += '      <option value="MP4"' + (state.outputForm.format === 'MP4' ? ' selected' : '') + '>MP4</option>';
    html += '      <option value="MOV"' + (state.outputForm.format === 'MOV' ? ' selected' : '') + '>MOV</option>';
    html += '      <option value="AVI"' + (state.outputForm.format === 'AVI' ? ' selected' : '') + '>AVI</option>';
    html += '      <option value="WEBM"' + (state.outputForm.format === 'WEBM' ? ' selected' : '') + '>WEBM</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>分辨率</label><select id="out-resolution">';
    html += '      <option value="720p"' + (state.outputForm.resolution === '720p' ? ' selected' : '') + '>720p</option>';
    html += '      <option value="1080p"' + (state.outputForm.resolution === '1080p' ? ' selected' : '') + '>1080p</option>';
    html += '      <option value="4K"' + (state.outputForm.resolution === '4K' ? ' selected' : '') + '>4K</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>帧率</label><select id="out-fps">';
    html += '      <option value="24"' + (state.outputForm.fps === 24 ? ' selected' : '') + '>24fps</option>';
    html += '      <option value="30"' + (state.outputForm.fps === 30 ? ' selected' : '') + '>30fps</option>';
    html += '      <option value="60"' + (state.outputForm.fps === 60 ? ' selected' : '') + '>60fps</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label>比特率</label><select id="out-bitrate">';
    html += '      <option value="10Mbps"' + (state.outputForm.bitrate === '10Mbps' ? ' selected' : '') + '>10Mbps</option>';
    html += '      <option value="15Mbps"' + (state.outputForm.bitrate === '15Mbps' ? ' selected' : '') + '>15Mbps</option>';
    html += '      <option value="25Mbps"' + (state.outputForm.bitrate === '25Mbps' ? ' selected' : '') + '>25Mbps</option>';
    html += '      <option value="50Mbps"' + (state.outputForm.bitrate === '50Mbps' ? ' selected' : '') + '>50Mbps</option>';
    html += '    </select></div>';
    html += '    <div class="form-group"><label><input type="checkbox" id="out-subtitles"' + (state.outputForm.includeSubtitles ? ' checked' : '') + ' /> 包含字幕</label></div>';
    html += '  </div>';
    html += '  <p class="hint">当前为输出适配界面原型，未执行真实转码</p>';
    html += '</div>';

    // Export button
    html += '<div class="export-section card">';
    if (state.exportInProgress) {
      html += '  <div class="export-progress">';
      html += '    <div class="progress-bar"><div class="progress-fill progress-animate"></div></div>';
      html += '    <p class="progress-label">正在准备导出包...</p>';
      html += '  </div>';
    } else {
      html += '  <button class="btn btn-primary" id="btn-export-package">&#128230; 生成导出包</button>';
    }
    html += '</div>';

    // Export tree
    if (state.exportTree) {
      html += '<div class="export-tree card">';
      html += '  <h4>导出目录结构</h4>';
      html += renderExportTreeHTML(state.exportTree);
      html += '  <div class="export-tree-actions">';
      html += '    <button class="btn btn-secondary" id="btn-copy-manifest">复制 Manifest</button>';
      html += '    <button class="btn btn-secondary" id="btn-sim-download">模拟下载</button>';
      html += '  </div>';
      html += '</div>';
    }

    els.studioContentPanel.innerHTML = html;

    // Bind platform cards
    bindPlatformCards();
    bindOutputForm();
    bindExportActions();

    if (state.exportTree) {
      bindTreeToggle();
      var copyBtn = $('btn-copy-manifest');
      if (copyBtn) copyBtn.addEventListener('click', handleCopyManifest);
      var dlBtn = $('btn-sim-download');
      if (dlBtn) dlBtn.addEventListener('click', handleSimulatedDownload);
    }
  }

  function bindPlatformCards() {
    var container = els.studioContentPanel;
    if (!container) return;
    var cards = container.querySelectorAll('[data-platform-id]');
    for (var i = 0; i < cards.length; i++) {
      (function(card) {
        card.addEventListener('click', function() {
          var pid = card.getAttribute('data-platform-id');
          state.outputForm.platformId = pid;
          var allCards = container.querySelectorAll('[data-platform-id]');
          for (var c = 0; c < allCards.length; c++) {
            allCards[c].classList.remove('platform-selected');
          }
          card.classList.add('platform-selected');

          // Auto-fill recommended settings
          var platformSettings = {
            'museum-screen': { format: 'MP4', resolution: '4K', fps: 60, bitrate: '50Mbps' },
            'online-gallery': { format: 'MP4', resolution: '1080p', fps: 30, bitrate: '15Mbps' },
            'social-vertical': { format: 'MP4', resolution: '1080p', fps: 30, bitrate: '15Mbps' },
            'vr-device': { format: 'MP4', resolution: '4K', fps: 60, bitrate: '50Mbps' },
            'douyin-bilibili': { format: 'MP4', resolution: '1080p', fps: 30, bitrate: '15Mbps' },
            'wechat-video': { format: 'MP4', resolution: '720p', fps: 30, bitrate: '10Mbps' },
            'academic': { format: 'MP4', resolution: '4K', fps: 24, bitrate: '25Mbps' },
            'mobile': { format: 'MP4', resolution: '720p', fps: 30, bitrate: '10Mbps' },
            'custom': { format: 'MP4', resolution: '1080p', fps: 30, bitrate: '15Mbps' }
          };

          var settings = platformSettings[pid];
          if (settings) {
            state.outputForm.format = settings.format;
            state.outputForm.resolution = settings.resolution;
            state.outputForm.fps = settings.fps;
            state.outputForm.bitrate = settings.bitrate;

            // Update select fields
            var fmtEl = $('out-format');
            if (fmtEl) fmtEl.value = settings.format;
            var resEl = $('out-resolution');
            if (resEl) resEl.value = settings.resolution;
            var fpsEl = $('out-fps');
            if (fpsEl) fpsEl.value = settings.fps;
            var bitEl = $('out-bitrate');
            if (bitEl) bitEl.value = settings.bitrate;
          }

          saveToLocalStorage();
        });
      })(cards[i]);
    }
  }

  function bindOutputForm() {
    var fmtEl = $('out-format');
    if (fmtEl) {
      fmtEl.addEventListener('change', function() {
        state.outputForm.format = fmtEl.value;
        saveToLocalStorage();
      });
    }
    var resEl = $('out-resolution');
    if (resEl) {
      resEl.addEventListener('change', function() {
        state.outputForm.resolution = resEl.value;
        saveToLocalStorage();
      });
    }
    var fpsEl = $('out-fps');
    if (fpsEl) {
      fpsEl.addEventListener('change', function() {
        state.outputForm.fps = parseInt(fpsEl.value, 10);
        saveToLocalStorage();
      });
    }
    var bitEl = $('out-bitrate');
    if (bitEl) {
      bitEl.addEventListener('change', function() {
        state.outputForm.bitrate = bitEl.value;
        saveToLocalStorage();
      });
    }
    var subEl = $('out-subtitles');
    if (subEl) {
      subEl.addEventListener('change', function() {
        state.outputForm.includeSubtitles = subEl.checked;
        saveToLocalStorage();
      });
    }
  }

  function bindExportActions() {
    var exportBtn = $('btn-export-package');
    if (exportBtn) {
      exportBtn.addEventListener('click', handleExportPackage);
    }
  }

  function handleExportPackage() {
    if (state.exportInProgress) return;
    state.exportInProgress = true;
    renderModule6();

    (async function() {
      try {
        if (!state.projectId) {
          throw new Error('请先创建项目');
        }

        var task = await api('/api/creative/projects/' + state.projectId + '/exports', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });

        await pollTask(task.id, function(progress, stage) {
          // Progress updates
        });

        // Get artifacts
        var artifacts = await api('/api/creative/projects/' + state.projectId + '/artifacts');
        var project = state.project || {};
        var projectName = project.name || '未命名项目';
        var safeName = projectName.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '_');

        state.exportTree = {
          name: safeName,
          type: 'folder',
          children: []
        };

        // Build export tree from actual artifacts
        if (artifacts && artifacts.length) {
          var typeFolders = {};
          for (var i = 0; i < artifacts.length; i++) {
            var a = artifacts[i];
            var type = a.artifact_type || 'other';
            var folderName = type === 'image' ? 'images' : type === 'video' ? 'video' :
                            type === 'audio' ? 'audio' : 'metadata';
            if (!typeFolders[folderName]) {
              typeFolders[folderName] = [];
            }
            typeFolders[folderName].push({
              name: a.name || 'file_' + i,
              type: type,
              size: formatFileSize(a.file_size || 0)
            });
          }

          var order = ['video', 'images', 'audio', 'metadata'];
          for (var o = 0; o < order.length; o++) {
            var key = order[o];
            if (typeFolders[key]) {
              state.exportTree.children.push({
                name: key, type: 'folder', children: typeFolders[key]
              });
            }
          }
        } else {
          // Fallback placeholder
          state.exportTree.children = [
            { name: 'video', type: 'folder', children: [] },
            { name: 'audio', type: 'folder', children: [] },
            { name: 'metadata', type: 'folder', children: [
              { name: 'manifest.json', type: 'json', size: '1KB' }
            ]}
          ];
        }

        state.exportInProgress = false;
        state.stepsCompleted[5] = true;
        updateFlowNav();
        saveToLocalStorage();
        renderModule6();
        showToast('导出包已生成', 'success');

      } catch (e) {
        state.exportInProgress = false;
        showToast('导出失败: ' + e.message, 'error');
        renderModule6();
      }
    })();
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + 'GB';
  }

  function renderExportTreeHTML(node, depth) {
    if (!node) return '';
    depth = depth || 0;
    var indent = depth * 20;

    if (node.type === 'folder') {
      var childrenHTML = '';
      if (node.children) {
        for (var i = 0; i < node.children.length; i++) {
          childrenHTML += renderExportTreeHTML(node.children[i], depth + 1);
        }
      }
      var collapsed = depth > 1 ? ' tree-collapsed' : '';
      var html = '';
      html += '<div class="tree-node tree-folder' + collapsed + '" style="padding-left: ' + indent + 'px;">';
      html += '  <span class="tree-toggle" data-toggle>' + (depth > 1 ? '&#9654;' : '&#9660;') + '</span>';
      html += '  <span class="tree-icon">&#128193;</span>';
      html += '  <span class="tree-name">' + escapeHtml(node.name) + '</span>';
      html += '  <div class="tree-children"' + (depth > 1 ? ' style="display: none;"' : '') + '>' + childrenHTML + '</div>';
      html += '</div>';
      return html;
    } else {
      var iconMap = {
        video: '&#127916;',
        audio: '&#128266;',
        text: '&#128196;',
        json: '&#128220;',
        image: '&#128247;'
      };
      var icon = iconMap[node.type] || '&#128196;';
      var html = '';
      html += '<div class="tree-node tree-file" style="padding-left: ' + indent + 'px;">';
      html += '  <span class="tree-icon">' + icon + '</span>';
      html += '  <span class="tree-name">' + escapeHtml(node.name) + '</span>';
      if (node.size) {
        html += '  <span class="tree-size">' + escapeHtml(node.size) + '</span>';
      }
      html += '</div>';
      return html;
    }
  }

  function bindTreeToggle() {
    var container = els.studioContentPanel;
    if (!container) return;
    var toggles = container.querySelectorAll('[data-toggle]');
    for (var i = 0; i < toggles.length; i++) {
      (function(toggle) {
        toggle.addEventListener('click', function() {
          var node = toggle.closest('.tree-folder');
          if (!node) return;
          var children = node.querySelector('.tree-children');
          if (!children) return;
          if (children.style.display === 'none') {
            children.style.display = 'block';
            toggle.innerHTML = '&#9660;';
            node.classList.remove('tree-collapsed');
          } else {
            children.style.display = 'none';
            toggle.innerHTML = '&#9654;';
            node.classList.add('tree-collapsed');
          }
        });
      })(toggles[i]);
    }
  }

  function handleCopyManifest() {
    if (!state.exportTree) return;
    var manifest = {
      projectName: state.exportTree.name,
      generatedAt: new Date().toISOString(),
      format: state.outputForm.format,
      resolution: state.outputForm.resolution,
      fps: state.outputForm.fps,
      bitrate: state.outputForm.bitrate,
      structure: state.exportTree
    };

    try {
      var text = JSON.stringify(manifest, null, 2);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function() {
          showToast('Manifest 已复制到剪贴板', 'success');
        }).catch(function() {
          fallbackCopy(text);
        });
      } else {
        fallbackCopy(text);
      }
    } catch (e) {
      showToast('复制失败: ' + e.message, 'error');
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      showToast('Manifest 已复制到剪贴板', 'success');
    } catch (e) {
      showToast('复制失败，请手动复制', 'error');
    }
    document.body.removeChild(ta);
  }

  function handleSimulatedDownload() {
    showToast('导出包已准备就绪', 'success');
  }

  // ---------------------------------------------------------------
  // Initialize
  // ---------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', function() {
    init();
  });

  // Expose utilities
  window.CreativeStudio = {
    showToast: showToast,
    $: $,
    escapeHtml: escapeHtml,
    state: state,
    init: init,
    switchStep: switchStep,
    switchProject: switchProject,
    saveToLocalStorage: saveToLocalStorage
  };

})();
