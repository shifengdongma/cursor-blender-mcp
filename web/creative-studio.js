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

  // Quote-safe: this helper is interpolated into HTML attributes, so it must
  // escape both quote characters.  A textContent round-trip does not.
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[ch];
    });
  }

  // API helpers
  function apiMessage(payload, fallback) {
    if (payload && payload.message) return payload.message;
    if (payload && payload.error) return payload.error;
    return fallback || '';
  }

  function api(path, options) {
    return window.AIGV.api(path, options || {});
  }

  // Provider configuration errors surface through AIGV.ApiError.code for HTTP
  // failures; task failures only carry the backend error message, so also match
  // codes embedded in the text and the configure_url hint.
  function isProviderConfigError(error) {
    if (!error) return false;
    if (error.code === 'provider_not_configured' ||
        error.code === 'provider_credential_missing') {
      return true;
    }
    var message = typeof error === 'string' ? error : (error.message || '');
    return message.indexOf('provider_not_configured') !== -1 ||
      message.indexOf('provider_credential_missing') !== -1 ||
      message.indexOf('/api-settings') !== -1 ||
      message.indexOf('API 配置页') !== -1;
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

  function showPromptDialog(title, message, defaultValue, confirmText, onSubmit) {
    title = title || '输入';
    message = message || '';
    defaultValue = defaultValue || '';
    confirmText = confirmText || '确定';
    onSubmit = onSubmit || function() {};

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
      '    <div class="modal-form-group">' +
      '      <label class="modal-form-label" for="prompt-dialog-input">项目名称</label>' +
      '      <input type="text" class="modal-form-input" id="prompt-dialog-input" maxlength="80" />' +
      '    </div>' +
      '  </div>' +
      '  <div class="modal-form-actions">' +
      '    <button class="modal-btn-cancel">取消</button>' +
      '    <button class="modal-btn-confirm">' + escapeHtml(confirmText) + '</button>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(overlay);

    var input = overlay.querySelector('.modal-form-input');
    var closeBtn = overlay.querySelector('.studio-modal-close');
    var cancelBtn = overlay.querySelector('.modal-btn-cancel');
    var confirmBtn = overlay.querySelector('.modal-btn-confirm');
    input.value = defaultValue;

    function closeModal() {
      document.removeEventListener('keydown', onKeyDown);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    function submit() {
      var value = (input.value || '').trim();
      if (!value) {
        showToast('项目名称不能为空', 'warning');
        input.focus();
        return;
      }
      closeModal();
      onSubmit(value);
    }

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeModal();
    });
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    confirmBtn.addEventListener('click', submit);
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') submit();
    });

    function onKeyDown(e) {
      if (e.key === 'Escape') closeModal();
    }
    document.addEventListener('keydown', onKeyDown);

    // Preselect the current name so typing replaces it.
    setTimeout(function() { input.focus(); input.select(); }, 50);
  }

  function showEditShotDialog(shot, onSave) {
    if (!shot) return;
    onSave = onSave || function() {};

    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    var shotTypeOptions = [
      'wide', 'medium', 'close_up', 'establishing', 'detail', 'tracking',
      'macro', 'aerial', 'orbit'
    ];
    var currentType = String(shot.shotType || '').toLowerCase()
      .replace('wide-shot', 'wide')
      .replace('medium-shot', 'medium')
      .replace('close-up', 'close_up');
    var shotTypeSelect = '';
    for (var i = 0; i < shotTypeOptions.length; i++) {
      var s = shotTypeOptions[i];
      var sel = currentType === s ? ' selected' : '';
      shotTypeSelect += '<option value="' + s + '"' + sel + '>' +
        shotTypeLabel(s) + '</option>';
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
    analysisError: '',
    analysisNeedsConfig: false,
    conceptImages: {},
    imageGenInProgress: false,
    videoGenInProgress: false,
    videoGenStage: '',
    videoProgress: 0,
    videoCancelRequested: false,
    videoResults: {},
    narrationForm: {
      voiceId: '',
      speechRate: 1.0,
      volume: 1.0,
      musicVolume: 0.3
    },
    filterParams: {
      brightness: 100,
      contrast: 100,
      saturation: 100,
      blur: 0,
      hueRotate: 0,
      exposure: 0,
      sharpen: 0
    },
    humanParams: {},
    aiBatchInProgress: false,
    outputForm: {
      platformId: '',
      format: 'MP4',
      resolution: '720p',
      fps: 30,
      bitrate: '15Mbps',
      subtitleMode: 'none',
      keepSourceAudio: true,
      musicDucking: false,
      loudnessNormalize: true,
      crf: 20,
      audioBitrate: '192k'
    },
    exportInProgress: false,
    exportTree: null,
    exportDownloadUrl: null,
    exportManifest: null,
    // Real media workflow state
    ttsVoices: [],
    defaultVoiceId: null,
    audioAssets: { music: [], sfx: [] },
    audioPresets: { music: [], sfx: [] },
    shotAudio: {},
    shotAudioLoaded: {},
    shotVideoVersions: {},
    shotVideoVersionsLoaded: {},
    selectedVideoShotId: null,
    selectedVideoAssetId: null,
    videoVersionInProgress: false,
    timeline: {
      version: 0,
      tracks: [],
      duration_s: 0,
      initialized: false,
      warnings: [],
      saveState: '',
      dirty: false,
      loading: false
    },
    timelineSaveTimer: null,
    timelineSaving: false,
    timelineSaveQueued: false,
    timelineSavePromise: null,
    timelineRevision: 0,
    timelineDragging: false,
    finalVideo: null,
    workflow: null,
    composeInProgress: false,
    composeProgress: 0,
    composeStage: '',
    refineInProgress: false,
    ttsInProgress: false,
    pollAbortControllers: {},
    workflowPollTaskIds: {},
    demoData: null,
    conceptGenTimer: null,
    videoGenTimer: null,
    aiBatchTimer: null,
    exportTimer: null,
    analysisTimer: null,
    // Backend-driven fields
    projectId: null,
    project: null,
    newProjectDraft: false,
    shots: [],
    tasks: {},
    generationModels: { image: [], video: [] },
    referenceAssets: [],
    projectImageTasks: {},
    projectVideoTasks: {},
    selectedImageModel: null,
    selectedVideoModel: null,
    selectedReferenceAssetId: '',
    currentImageTaskId: null,
    currentVideoTaskId: null,
    analysisTaskId: null
  };

  // ---------------------------------------------------------------
  // Element cache
  // ---------------------------------------------------------------
  var els = {};

  function cacheElements() {
    els.projectSelect = $('project-select');
    els.projectMetrics = $('project-metrics');
    els.projectActions = $('project-actions');
    els.btnNewProject = $('btn-new-project');
    els.btnSaveProject = $('btn-save-project');
    els.btnRenameProject = $('btn-rename-project');
    els.btnDeleteProject = $('btn-delete-project');
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
        version: 2,
        activeStep: state.activeStep,
        activeShotIndex: state.activeShotIndex,
        requirementsForm: state.requirementsForm,
        narrationForm: state.narrationForm,
        filterParams: state.filterParams,
        outputForm: state.outputForm,
        // Business ids only, never cached business data. Workflow completion
        // and timelines always come from the server.
        projectId: state.projectId,
        currentImageTaskId: state.currentImageTaskId,
        currentVideoTaskId: state.currentVideoTaskId,
        selectedImageModel: state.selectedImageModel,
        selectedVideoModel: state.selectedVideoModel
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
      if (prefs.requirementsForm) Object.assign(state.requirementsForm, prefs.requirementsForm);
      if (prefs.narrationForm) Object.assign(state.narrationForm, prefs.narrationForm);
      if (prefs.filterParams) Object.assign(state.filterParams, prefs.filterParams);
      if (prefs.outputForm) Object.assign(state.outputForm, prefs.outputForm);
      if (prefs.projectId) state.projectId = prefs.projectId;
      if (prefs.currentImageTaskId) state.currentImageTaskId = prefs.currentImageTaskId;
      if (prefs.currentVideoTaskId) state.currentVideoTaskId = prefs.currentVideoTaskId;
      if (prefs.selectedImageModel) state.selectedImageModel = normalizeModelKey(prefs.selectedImageModel);
      if (prefs.selectedVideoModel) state.selectedVideoModel = normalizeModelKey(prefs.selectedVideoModel);
      return true;
    } catch (e) {
      try { localStorage.removeItem(STORAGE_KEY); } catch (ex) {}
      return false;
    }
  }

  // ---------------------------------------------------------------
  // Core Functions
  // ---------------------------------------------------------------

  function checkServiceHealth() {
    var statusEl = document.getElementById('connection-status');
    if (!statusEl) return;
    api('/api/health').then(function () {
      statusEl.textContent = '服务正常';
      statusEl.setAttribute('data-status-tone', 'success');
    }).catch(function () {
      statusEl.textContent = '服务不可用';
      statusEl.setAttribute('data-status-tone', 'error');
    });
  }

  function init() {
    cacheElements();

    // Try restoring UI prefs from localStorage
    loadFromLocalStorage();

    // Hand-off from the generation-history page: preselect a reference image.
    var refAssetFromUrl = new URLSearchParams(window.location.search).get('reference_asset_id');
    if (refAssetFromUrl) {
      state.selectedReferenceAssetId = refAssetFromUrl;
      state.activeStep = 2;
    }

    // Set active project
    if (state.projectId) {
      state.activeProjectId = state.projectId;
      state.activeProject = state.project;
    } else {
      state.activeProject = getActiveProject();
    }

    // Bind events
    bindEvents();
    checkServiceHealth();

    // Render shell immediately, then hydrate real projects/tasks/modules.
    renderCurrentModule();
    updateFlowNav();
    updatePreviewPanel(state.activeStep);
    updateProjectMetrics();

    Promise.all([loadProjects(), loadGenerationModels(), loadReferenceAssets(), loadTtsVoices()]).then(function () {
      renderCurrentModule();
      updateProjectMetrics();
      updatePreviewPanel(state.activeStep);
      restoreActiveTasks();
      if (state.projectId && state.activeStep === 4) {
        loadTimeline(true).then(loadAudioLibrary).then(function () {
          if (state.activeStep === 4) renderCurrentModule();
        });
      } else if (state.projectId && state.activeStep === 6) {
        loadTimeline(false).then(function () {
          if (state.activeStep === 6) renderCurrentModule();
        });
      }
    }).catch(function () {});
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
      shot.primaryImageAssetId = shot.primary_image_asset_id || null;
      shot.keyframeAssetId = shot.keyframe_asset_id || null;
      shot.videoAssetId = shot.video_asset_id || null;
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
    if (!state.projects.length) {
      var empty = document.createElement('option');
      empty.value = '';
      empty.textContent = '暂无创意项目';
      els.projectSelect.appendChild(empty);
      return;
    }
    var placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '-- 选择项目 --';
    els.projectSelect.appendChild(placeholder);
    for (var i = 0; i < state.projects.length; i++) {
      var p = state.projects[i];
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name || p.theme || ('项目 ' + (i + 1));
      if (p.id === state.activeProjectId || p.id === state.projectId) {
        opt.selected = true;
      }
      els.projectSelect.appendChild(opt);
    }
  }

  function hydrateConceptImages() {
    var shots = state.shots || [];
    for (var i = 0; i < shots.length; i++) {
      var shot = normalizeShot(shots[i]);
      var assetId = shot.primary_image_asset_id || shot.keyframe_asset_id;
      if (!assetId) {
        state.conceptImages[shot.id] = [];
        continue;
      }
      var task = state.projectImageTasks[assetId] || null;
      var asset = task && task.output_asset ? task.output_asset : null;
      var params = (task && task.params) || (asset && asset.metadata && asset.metadata.generation_params) || {};
      var isKeyframe = shot.keyframe_asset_id === assetId || (!shot.keyframe_asset_id && !!shot.primary_image_asset_id);
      state.conceptImages[shot.id] = [{
        id: assetId,
        assetId: assetId,
        shotId: shot.id,
        taskId: task ? task.id : null,
        url: '/api/assets/' + encodeURIComponent(assetId) + '/file',
        downloadUrl: '/api/assets/' + encodeURIComponent(assetId) + '/download',
        prompt: params.prompt || shot.keyframePrompt || shot.scene_description || '',
        modelLabel: (task && task.model_id) || '已生成图片',
        model: task ? task.model_id : '',
        seed: params.seed !== null && params.seed !== undefined ? params.seed : '—',
        width: params.width || '—',
        height: params.height || '—',
        params: params,
        metadata: (asset && asset.metadata) || {},
        generatedAt: task ? AIGV.formatTime(task.completed_at || task.created_at) : '—',
        colors: ['#1a2433', '#33465c'],
        isKeyframe: isKeyframe,
        isFavorite: !!(asset && asset.metadata && asset.metadata.favorite)
      }];
    }
  }

  function hydrateVideoResults() {
    state.videoResults = {};
    var shots = state.shots || [];
    for (var i = 0; i < shots.length; i++) {
      var shot = normalizeShot(shots[i]);
      if (!shot.video_asset_id) {
        continue;
      }
      var task = state.projectVideoTasks[shot.video_asset_id] || null;
      var params = (task && task.params) || {};
      state.videoResults[shot.id] = {
        id: 'video-' + shot.id,
        shotId: shot.id,
        taskId: task ? task.id : null,
        assetId: shot.video_asset_id,
        fileUrl: '/api/assets/' + encodeURIComponent(shot.video_asset_id) + '/file',
        downloadUrl: '/api/assets/' + encodeURIComponent(shot.video_asset_id) + '/download',
        model: task ? task.model_id : '',
        params: params,
        createdAt: task ? AIGV.formatTime(task.completed_at || task.created_at) : '—',
        status: 'completed',
        progress: 100
      };
    }
  }

  async function loadGenerationModels() {
    try {
      var imageModels = await api('/api/generation/models?task_type=image');
      state.generationModels.image = (imageModels && imageModels.items) || [];
      var videoModels = await api('/api/generation/models?task_type=video');
      state.generationModels.video = (videoModels && videoModels.items) || [];
    } catch (e) {
      state.generationModels = { image: [], video: [] };
    }
  }

  async function loadReferenceAssets() {
    try {
      var data = await api('/api/assets?asset_type=image&limit=50');
      state.referenceAssets = (data && data.items) || [];
      // A history hand-off may point at an asset outside the first page.
      if (state.selectedReferenceAssetId) {
        var present = state.referenceAssets.some(function (asset) {
          return asset.id === state.selectedReferenceAssetId;
        });
        if (!present) {
          try {
            var selected = await api('/api/assets/' + encodeURIComponent(state.selectedReferenceAssetId));
            if (selected) state.referenceAssets.unshift(selected);
          } catch (e) {
            state.selectedReferenceAssetId = '';
          }
        }
      }
    } catch (e) {
      state.referenceAssets = [];
    }
  }

  function availableModels(kind) {
    var models = (state.generationModels[kind] || []);
    return models.filter(function (model) { return !!model.available; });
  }

  function normalizeModelKey(key) {
    // The old Lite slot was replaced by Seedream Flash.
    return key === 'ark_seedream_lite' ? 'ark_seedream_flash' : key;
  }

  function modelOptionLabel(model) {
    var label = model.display_name || model.key;
    if (model.model_id) label += ' · ' + model.model_id;
    return label;
  }

  function findModel(kind, key) {
    var models = state.generationModels[kind] || [];
    key = normalizeModelKey(key);
    for (var i = 0; i < models.length; i += 1) {
      if (models[i].key === key) return models[i];
    }
    return null;
  }

  function selectedImageModelInfo() {
    var models = availableModels('image');
    if (!models.length) return null;
    var selected = findModel('image', state.selectedImageModel);
    if (selected && selected.available) {
      state.selectedImageModel = selected.key;
      return selected;
    }
    for (var i = 0; i < models.length; i += 1) {
      if (models[i].default) {
        state.selectedImageModel = models[i].key;
        return models[i];
      }
    }
    state.selectedImageModel = models[0].key;
    return models[0];
  }

  function selectedVideoModelInfo() {
    var models = availableModels('video');
    if (!models.length) return null;
    var selected = findModel('video', state.selectedVideoModel);
    if (selected && selected.available) {
      state.selectedVideoModel = selected.key;
      return selected;
    }
    for (var i = 0; i < models.length; i += 1) {
      if (models[i].default) {
        state.selectedVideoModel = models[i].key;
        return models[i];
      }
    }
    state.selectedVideoModel = models[0].key;
    return models[0];
  }

  async function loadProjects() {
    try {
      var data = await api('/api/creative/projects?limit=200');
      state.projects = (data && data.items) || [];
      if (state.newProjectDraft) {
        // A brand-new draft is being edited; don't replace it with an existing project.
        populateProjectSelector();
        return;
      }
      var restored = state.projectId && state.projects.some(function (item) {
        return item.id === state.projectId;
      });
      if (!restored) {
        state.projectId = state.projects.length ? state.projects[0].id : null;
      }
      populateProjectSelector();
      if (state.projectId) {
        await loadProjectFromBackend(state.projectId);
      } else {
        state.shots = [];
        updateProjectMetrics();
        renderCurrentModule();
      }
    } catch (e) {
      showToast('加载项目失败: ' + e.message, 'error');
    }
  }

  async function restoreActiveTasks() {
    if (state.currentImageTaskId) {
      resumeTask(state.currentImageTaskId, 'image');
    }
    if (state.currentVideoTaskId) {
      resumeTask(state.currentVideoTaskId, 'video');
    }
    resumeWorkflowTasks();
  }

  async function loadWorkflow(projectId) {
    if (!projectId) return null;
    try {
      var workflow = await api('/api/creative/projects/' + encodeURIComponent(projectId) + '/workflow');
      if (state.projectId !== projectId) return null;
      state.workflow = workflow;
      state.finalVideo = workflow.final_video || null;
      var steps = workflow.steps || [];
      state.stepsCompleted = [false, false, false, false, false, false];
      for (var i = 0; i < steps.length; i++) {
        state.stepsCompleted[steps[i].step - 1] = !!steps[i].complete;
      }
      if (workflow.timeline) {
        state.timeline.version = workflow.timeline.version || 0;
      }
      updateFlowNav();
      updatePreviewPanel(state.activeStep);
      return workflow;
    } catch (e) {
      return null;
    }
  }

  async function loadTtsVoices() {
    try {
      var data = await api('/api/creative/tts/voices');
      state.ttsVoices = (data && data.items) || [];
      state.defaultVoiceId = data && data.default_voice_id;
      if (!state.narrationForm.voiceId ||
          !state.ttsVoices.some(function (voice) { return voice.id === state.narrationForm.voiceId && voice.available; })) {
        state.narrationForm.voiceId = state.defaultVoiceId || '';
      }
    } catch (e) {
      state.ttsVoices = [];
    }
  }

  async function loadAudioLibrary() {
    if (!state.projectId) return;
    try {
      var results = await Promise.all([
        api('/api/assets?asset_type=audio&audio_role=music&limit=100'),
        api('/api/assets?asset_type=audio&audio_role=sfx&limit=100'),
        api('/api/creative/audio/presets?role=music').catch(function () { return { items: [] }; }),
        api('/api/creative/audio/presets?role=sfx').catch(function () { return { items: [] }; })
      ]);
      state.audioAssets.music = (results[0] && results[0].items) || [];
      state.audioAssets.sfx = (results[1] && results[1].items) || [];
      state.audioPresets.music = (results[2] && results[2].items) || [];
      state.audioPresets.sfx = (results[3] && results[3].items) || [];
    } catch (e) {
      state.audioAssets = { music: [], sfx: [] };
    }
  }

  async function loadShotAudio(shotId) {
    if (!shotId) return null;
    try {
      var data = await api('/api/creative/shots/' + encodeURIComponent(shotId) + '/audio');
      state.shotAudio[shotId] = data;
      return data;
    } catch (e) {
      return null;
    }
  }

  async function loadShotVideos(shotId) {
    if (!shotId) return null;
    try {
      var data = await api('/api/creative/shots/' + encodeURIComponent(shotId) + '/videos');
      state.shotVideoVersions[shotId] = data;
      return data;
    } catch (e) {
      return null;
    }
  }

  async function loadTimeline(ensure) {
    if (!state.projectId) return null;
    var projectId = state.projectId;
    state.timeline.loading = true;
    try {
      var url = '/api/creative/projects/' + encodeURIComponent(projectId) + '/timeline' + (ensure ? '?ensure=1' : '');
      var data = await api(url);
      if (state.projectId !== projectId) return null;
      state.timeline.tracks = data.tracks || [];
      state.timeline.version = data.timeline_version || 0;
      state.timeline.duration_s = data.duration_s || 0;
      state.timeline.initialized = !!data.initialized;
      state.timeline.warnings = data.warnings || [];
      state.timeline.dirty = false;
      return data;
    } catch (e) {
      state.timeline.warnings = [e.message || '时间线加载失败'];
      return null;
    } finally {
      state.timeline.loading = false;
    }
  }

  function resumeWorkflowTasks() {
    var tasks = (state.workflow && state.workflow.active_tasks) || [];
    if (!state.projectId) return;
    var projectId = state.projectId;
    var flags = {
      tts: 'ttsInProgress',
      compose: 'composeInProgress',
      refine: 'refineInProgress',
      export: 'exportInProgress'
    };
    tasks.forEach(function (task) {
      if (!task || !task.id || state.workflowPollTaskIds[task.id]) return;
      if (['tts', 'compose', 'refine', 'export'].indexOf(task.task_type) < 0) return;
      state.workflowPollTaskIds[task.id] = true;
      state[flags[task.task_type]] = true;
      if (task.task_type === 'tts') {
        state.shotAudio = {};
        state.shotAudioLoaded = {};
      }
      if (task.task_type === 'refine') {
        state.shotVideoVersions = {};
        state.shotVideoVersionsLoaded = {};
      }
      pollTask(task.id, null, { projectId: projectId, treatCancelledAsError: true }).then(function () {
        delete state.workflowPollTaskIds[task.id];
        if (state.projectId !== projectId) return;
        state[flags[task.task_type]] = false;
        var work = reloadShotsAndHydrate();
        if (task.task_type === 'export') {
          work = work.then(function () {
            return api('/api/creative/tasks/' + encodeURIComponent(task.id));
          }).then(function (detail) {
            state.exportArtifacts = (detail && detail.artifacts) || [];
            state.exportDownloadUrl = '/api/creative/tasks/' + encodeURIComponent(task.id) + '/export/download';
          });
        }
        if (task.task_type === 'compose') {
          work = work.then(function () {
            if (!state.timeline.dirty) return loadTimeline(false);
          });
        }
        return work.then(function () {
          if (state.projectId !== projectId) return;
          if (task.task_type === 'tts' && state.activeStep === 4) renderModule4();
          if (task.task_type === 'refine' && state.activeStep === 5) renderModule5();
          if ((task.task_type === 'compose' || task.task_type === 'export') && state.activeStep === 6) {
            renderModule6();
          }
        });
      }).catch(function (error) {
        delete state.workflowPollTaskIds[task.id];
        if (state.projectId === projectId) state[flags[task.task_type]] = false;
      });
    });
  }

  function clearTaskId(kind) {
    if (kind === 'image') state.currentImageTaskId = null;
    if (kind === 'video') state.currentVideoTaskId = null;
    saveToLocalStorage();
  }

  function resumeTask(taskId, kind) {
    api('/api/creative/tasks/' + encodeURIComponent(taskId)).then(function (task) {
      if (!task) {
        clearTaskId(kind);
        return;
      }
      if (task.status === 'queued' || task.status === 'submitting' || task.status === 'running') {
        if (kind === 'image') {
          state.imageGenInProgress = true;
        } else {
          state.videoGenInProgress = true;
          state.videoGenStage = task.stage || task.provider_status || '生成中...';
        }
        renderCurrentModule();
        pollTask(taskId, function (progress, stage) {
          if (kind === 'video') {
            state.videoGenStage = stage || '生成中...';
            if (state.activeStep === 3) renderModule3();
          }
        }).then(function (finalTask) {
          finishGeneration(kind, finalTask);
        }).catch(function (error) {
          finishGenerationFailure(kind, error);
        });
        return;
      }
      if (task.status === 'succeeded') {
        finishGeneration(kind, task);
      } else {
        clearTaskId(kind);
      }
    }).catch(function () {
      clearTaskId(kind);
    });
  }

  async function reloadShotsAndHydrate() {
    if (!state.projectId) return;
    var projectId = state.projectId;
    var shots = await api('/api/creative/projects/' + projectId + '/shots');
    if (state.projectId !== projectId) return;
    state.shots = shots || [];
    await loadProjectTasks();
    hydrateConceptImages();
    hydrateVideoResults();
    await loadWorkflow(state.projectId);
    updateFlowNav();
    updateProjectMetrics();
  }

  async function loadProjectTasks() {
    state.projectImageTasks = {};
    state.projectVideoTasks = {};
    if (!state.projectId) return;
    try {
      var imageTasks = await api('/api/generation/tasks?task_type=image&project_id=' +
        encodeURIComponent(state.projectId) + '&limit=100');
      (imageTasks.items || []).forEach(function (task) {
        if (task.output_asset_id) state.projectImageTasks[task.output_asset_id] = task;
      });
      var videoTasks = await api('/api/generation/tasks?task_type=video&project_id=' +
        encodeURIComponent(state.projectId) + '&limit=100');
      (videoTasks.items || []).forEach(function (task) {
        if (task.output_asset_id) state.projectVideoTasks[task.output_asset_id] = task;
      });
    } catch (e) {
      // History is supplementary; generation itself still works without it.
    }
  }

  function finishGeneration(kind, finalTask) {
    if (!finalTask) {
      clearTaskId(kind);
      return;
    }
    if (finalTask.status === 'cancelled') {
      if (kind === 'image') {
        state.imageGenInProgress = false;
      } else {
        state.videoGenInProgress = false;
        state.videoProgress = 0;
        state.videoGenStage = '';
      }
      clearTaskId(kind);
      reloadShotsAndHydrate().then(function () {
        renderCurrentModule();
      });
      showToast('任务已取消', 'info');
      return;
    }
    clearTaskId(kind);
    reloadShotsAndHydrate().then(function () {
      if (kind === 'image') {
        state.imageGenInProgress = false;
        showToast('概念图生成完成', 'success');
      } else {
        state.videoGenInProgress = false;
        state.videoProgress = 100;
        state.videoGenStage = '完成';
        showToast('视频生成完成', 'success');
      }
      renderCurrentModule();
    }).catch(function (error) {
      if (kind === 'image') state.imageGenInProgress = false;
      else state.videoGenInProgress = false;
      showToast('结果加载失败: ' + error.message, 'error');
      renderCurrentModule();
    });
  }

  function finishGenerationFailure(kind, error) {
    if (error && error.name === 'AbortError') {
      if (kind === 'image') state.imageGenInProgress = false;
      else {
        state.videoGenInProgress = false;
        state.videoProgress = 0;
        state.videoGenStage = '';
      }
      return;
    }
    // Keep the task id for resumable/unknown states; clear only terminal ones.
    var terminal = error && (error.taskStatus === 'failed' || error.taskStatus === 'needs_review');
    if (terminal || !error || !error.taskStatus) {
      clearTaskId(kind);
    }
    if (kind === 'image') {
      state.imageGenInProgress = false;
    } else {
      state.videoGenInProgress = false;
      state.videoProgress = 0;
      state.videoGenStage = '';
    }
    var message = error && error.message ? error.message : '生成失败';
    if (isProviderConfigError(error) || message.indexOf('尚未接入') >= 0) {
      showToast('生成模型未配置，请前往 API 配置页填写 Provider 密钥（去配置 API: /api-settings）', 'warning');
    } else if (message.indexOf('需要人工确认') >= 0) {
      showToast(message, 'warning');
    } else {
      showToast((kind === 'image' ? '图片生成失败: ' : '视频生成失败: ') + message, 'error');
    }
    renderCurrentModule();
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

    // New project button
    if (els.btnNewProject) {
      els.btnNewProject.addEventListener('click', function() {
        showConfirmDialog('新建项目', '当前未保存的编辑内容将被清空，确定新建项目吗？', '新建', startNewProject);
      });
    }

    // Save button
    if (els.btnSaveProject) {
      els.btnSaveProject.addEventListener('click', function() {
        if (!state.projectId) {
          if (state.project) {
            createProjectFromForm();
          } else {
            saveToLocalStorage();
            showToast('本地偏好已保存', 'success');
          }
          return;
        }
        var form = state.requirementsForm;
        api('/api/creative/projects/' + encodeURIComponent(state.projectId), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: form.projectName || (state.project && state.project.name) || '未命名项目',
            description: form.description,
            concept: form.theme,
            requirements: form
          })
        }).then(function (project) {
          state.project = project;
          state.activeProject = project;
          saveToLocalStorage();
          showToast('项目已保存', 'success');
        }).catch(function (error) {
          showToast('保存失败: ' + error.message, 'error');
        });
      });
    }

    // Rename project button
    if (els.btnRenameProject) {
      els.btnRenameProject.addEventListener('click', renameActiveProject);
    }

    // Delete project button
    if (els.btnDeleteProject) {
      els.btnDeleteProject.addEventListener('click', deleteActiveProject);
    }

    // Reset button
    if (els.btnResetProject) {
      els.btnResetProject.addEventListener('click', function() {
        showConfirmDialog('重置项目', '确定要重置所有进度吗？此操作不可撤销。', '重置', function() {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        state.projectId = null;
        state.project = null;
        state.newProjectDraft = false;
        state.shots = [];
        state.activeProjectId = null;
        state.activeProject = null;
        state.activeStep = 1;
        state.stepsCompleted = [false, false, false, false, false, false];
        state.activeShotIndex = 0;
        state.conceptImages = {};
        state.videoResults = {};
        state.timeline = {
          version: 0, tracks: [], duration_s: 0, initialized: false,
          warnings: [], saveState: '', dirty: false, loading: false
        };
        state.shotAudio = {};
        state.shotAudioLoaded = {};
        state.shotVideoVersions = {};
        state.shotVideoVersionsLoaded = {};
        state.selectedVideoShotId = null;
        state.selectedVideoAssetId = null;
        state.finalVideo = null;
        state.workflow = null;
        state.exportTree = null;
        state.analysisInProgress = false;
        state.analysisStage = '';
        state.imageGenInProgress = false;
        state.videoGenInProgress = false;
        state.videoGenStage = '';
        state.videoProgress = 0;
        state.videoCancelRequested = false;
        state.narrationForm = { voiceId: state.defaultVoiceId || '', speechRate: 1.0, volume: 1.0, musicVolume: 0.3 };
        state.filterParams = { brightness: 100, contrast: 100, saturation: 100, blur: 0, hueRotate: 0, exposure: 0, sharpen: 0 };
        state.aiBatchInProgress = false;
        state.outputForm = { platformId: '', format: 'MP4', resolution: '720p', fps: 30, bitrate: '15Mbps', subtitleMode: 'none', keepSourceAudio: true, musicDucking: false, loudnessNormalize: true, crf: 20, audioBitrate: '192k' };
        state.exportInProgress = false;
        state.exportArtifacts = null;
        state.tasks = {};
        state.exportDownloadUrl = null;
        state.exportManifest = null;
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
    window.addEventListener('beforeunload', function () {
      if (state.timeline.dirty) saveTimelineNow({ keepalive: true });
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden && state.timeline.dirty) flushTimelineSave();
    });
  }

  function defaultRequirementsForm() {
    return {
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
    };
  }

  function startNewProject() {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    state.projectId = null;
    state.project = {
      id: null,
      name: '',
      status: 'draft',
      description: '',
      genre: '',
      concept: '',
      requirements: null,
      creative_brief: null,
      settings: null
    };
    state.newProjectDraft = true;
    state.activeProjectId = null;
    state.activeProject = null;
    state.activeStep = 1;
    state.activeShotIndex = 0;
    state.stepsCompleted = [false, false, false, false, false, false];
    state.shots = [];
    state.conceptImages = {};
    state.videoResults = {};
    state.projectImageTasks = {};
    state.projectVideoTasks = {};
    state.timeline = {
      version: 0, tracks: [], duration_s: 0, initialized: false,
      warnings: [], saveState: '', dirty: false, loading: false
    };
    state.timelineSaving = false;
    state.timelineSaveQueued = false;
    state.timelineSavePromise = null;
    state.timelineRevision = 0;
    state.shotAudio = {};
    state.shotAudioLoaded = {};
    state.shotVideoVersions = {};
    state.shotVideoVersionsLoaded = {};
    state.finalVideo = null;
    state.workflow = null;
    state.exportDownloadUrl = null;
    state.exportArtifacts = null;
    state.exportManifest = null;
    state.composeInProgress = false;
    state.refineInProgress = false;
    state.ttsInProgress = false;
    state.exportInProgress = false;
    state.analysisInProgress = false;
    state.analysisStage = '';
    state.analysisError = '';
    state.analysisNeedsConfig = false;
    state.requirementsForm = defaultRequirementsForm();
    populateProjectSelector();
    renderCurrentModule();
    updateFlowNav();
    updatePreviewPanel(state.activeStep);
    updateProjectMetrics();
    showToast('已新建项目草稿，填写需求后点击"分析需求"或"保存"', 'info');
  }

  function projectPayloadFromForm() {
    var form = state.requirementsForm;
    return {
      name: (form.projectName || '').trim() || '未命名项目',
      description: form.description,
      genre: form.style || 'cinematic',
      concept: form.theme,
      requirements: form
    };
  }

  function adoptCreatedProject(project) {
    state.projectId = project.id;
    state.project = project;
    state.newProjectDraft = false;
    state.activeProjectId = project.id;
    state.activeProject = project;
    state.projects.unshift(project);
    populateProjectSelector();
    saveToLocalStorage();
  }

  function createProjectFromForm() {
    api('/api/creative/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(projectPayloadFromForm())
    }).then(function (project) {
      adoptCreatedProject(project);
      renderCurrentModule();
      updateProjectMetrics();
      showToast('项目已保存', 'success');
    }).catch(function (error) {
      showToast('保存失败: ' + error.message, 'error');
    });
  }

  function renameActiveProject() {
    if (!state.projectId || !state.project) {
      showToast('请先选择一个项目', 'warning');
      return;
    }
    var projectId = state.projectId;
    var currentName = state.project.name || '';
    showPromptDialog('重命名项目', '输入新的项目名称。', currentName, '保存', function (name) {
      api('/api/creative/projects/' + encodeURIComponent(projectId), {
        method: 'PUT',
        body: { name: name }
      }).then(function (project) {
        state.project = project;
        state.activeProject = project;
        for (var i = 0; i < state.projects.length; i++) {
          if (state.projects[i].id === project.id) {
            state.projects[i] = project;
            break;
          }
        }
        state.requirementsForm.projectName = project.name || '';
        populateProjectSelector();
        renderCurrentModule();
        updateProjectMetrics();
        saveToLocalStorage();
        showToast('项目已重命名', 'success');
      }).catch(function (error) {
        showToast('重命名失败: ' + error.message, 'error');
      });
    });
  }

  function deleteActiveProject() {
    if (!state.projectId || !state.project) {
      showToast('请先选择一个项目', 'warning');
      return;
    }
    var projectId = state.projectId;
    var projectName = state.project.name || '未命名项目';
    showConfirmDialog(
      '删除项目',
      '确定删除项目「' + projectName + '」吗？该项目的分镜、生成任务和导出记录将一并删除，此操作不可恢复。',
      '删除',
      function () {
        api('/api/creative/projects/' + encodeURIComponent(projectId), {
          method: 'DELETE'
        }).then(function () {
          state.projects = state.projects.filter(function (item) {
            return item.id !== projectId;
          });
          state.projectId = null;
          state.project = null;
          state.activeProjectId = null;
          state.activeProject = null;
          state.newProjectDraft = false;
          state.activeShotIndex = 0;
          state.shots = [];
          state.conceptImages = {};
          state.videoResults = {};
          state.projectImageTasks = {};
          state.projectVideoTasks = {};
          state.stepsCompleted = [false, false, false, false, false, false];
          state.requirementsForm = defaultRequirementsForm();
          if (state.projects.length) {
            switchProject(state.projects[0].id);
          } else {
            populateProjectSelector();
            renderCurrentModule();
            updateFlowNav();
            updatePreviewPanel(state.activeStep);
            updateProjectMetrics();
            saveToLocalStorage();
          }
          showToast('项目已删除', 'success');
        }).catch(function (error) {
          showToast('删除失败: ' + error.message, 'error');
        });
      }
    );
  }

  function switchProject(id) {
    abortAllPolls();
    flushTimelineSave();
    state.activeProjectId = id || null;
    state.newProjectDraft = false;
    state.activeShotIndex = 0;
    state.timeline = {
      version: 0, tracks: [], duration_s: 0, initialized: false,
      warnings: [], saveState: '', dirty: false, loading: false
    };
    state.timelineSaving = false;
    state.timelineSaveQueued = false;
    state.timelineSavePromise = null;
    state.timelineRevision = 0;
    state.shotAudio = {};
    state.shotAudioLoaded = {};
    state.shotVideoVersions = {};
    state.shotVideoVersionsLoaded = {};
    state.selectedVideoShotId = null;
    state.selectedVideoAssetId = null;
    state.finalVideo = null;
    state.workflow = null;
    state.audioAssets = { music: [], sfx: [] };
    state.audioPresets = { music: [], sfx: [] };
    state.composeProgress = 0;
    state.composeStage = '';
    state.composeInProgress = false;
    state.refineInProgress = false;
    state.ttsInProgress = false;
    state.exportInProgress = false;
    state.currentImageTaskId = null;
    state.currentVideoTaskId = null;
    state.analysisTaskId = null;
    state.exportTree = null;
    state.exportDownloadUrl = null;
    state.exportManifest = null;
    if (!id) {
      state.projectId = null;
      state.project = null;
      state.activeProject = null;
      state.shots = [];
      state.conceptImages = {};
      state.videoResults = {};
      state.stepsCompleted = [false, false, false, false, false, false];
      populateProjectSelector();
      renderCurrentModule();
      updateFlowNav();
      updatePreviewPanel(state.activeStep);
      updateProjectMetrics();
      return;
    }
    return loadProjectFromBackend(id).then(function () {
      populateProjectSelector();
      renderCurrentModule();
      updateFlowNav();
      updatePreviewPanel(state.activeStep);
      updateProjectMetrics();
      saveToLocalStorage();
    });
  }

  async function loadProjectFromBackend(projectId) {
    state.projectLoadToken = (state.projectLoadToken || 0) + 1;
    var loadToken = state.projectLoadToken;
    try {
      var project = await api('/api/creative/projects/' + projectId);
      var shots = await api('/api/creative/projects/' + projectId + '/shots');
      if (loadToken !== state.projectLoadToken) return;
      state.project = project;
      state.projectId = projectId;
      state.activeProjectId = projectId;
      state.activeProject = project;
      state.shots = shots || [];
      state.exportTree = null;
      state.exportDownloadUrl = null;
      state.exportManifest = null;
      state.timeline = {
        version: 0, tracks: [], duration_s: 0, initialized: false,
        warnings: [], saveState: '', dirty: false, loading: false
      };
      state.shotAudio = {};
      state.shotAudioLoaded = {};
      state.shotVideoVersions = {};
      state.shotVideoVersionsLoaded = {};
      state.selectedVideoShotId = null;
      state.selectedVideoAssetId = null;
      state.finalVideo = null;
      state.workflow = null;
      state.exportArtifacts = null;
      await loadProjectTasks();
      hydrateConceptImages();
      state.videoResults = {};
      hydrateVideoResults();
      await loadWorkflow(projectId);
      if (loadToken !== state.projectLoadToken) return;
      resumeWorkflowTasks();
      // Update form fields
      if (project) {
        state.requirementsForm.projectName = project.name || '';
      }
    } catch (e) {
      showToast('加载项目失败: ' + e.message, 'error');
    }
  }

  async function switchStep(n) {
    if (n < 1 || n > 6) return;
    if (state.activeStep === 4 && n !== 4) {
      await flushTimelineSave();
      if (state.timeline.dirty) {
        showToast('时间线尚未保存，请先处理保存失败/冲突', 'error');
        return;
      }
    }
    state.activeStep = n;
    updateFlowNav();
    renderCurrentModule();
    updatePreviewPanel(n);
    if (n === 4 && state.projectId) {
      loadTimeline(true).then(function () {
        return loadAudioLibrary();
      }).then(function () {
        if (state.activeStep === 4) renderCurrentModule();
      });
    } else if (n === 6 && state.projectId) {
      Promise.all([loadWorkflow(state.projectId), loadTimeline(false)]).then(function () {
        if (state.activeStep === 6) renderCurrentModule();
      });
    }
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
    var shots = state.shots || [];
    var totalDuration = 0;
    for (var i = 0; i < shots.length; i++) {
      totalDuration += (shots[i].duration_s || shots[i].duration || 0);
    }
    var videoCount = 0;
    for (var j = 0; j < shots.length; j++) {
      if (shots[j].video_asset_id) videoCount++;
    }
    var projectStatusLabels = {
      draft: '草稿', analyzing: '分析中', ready: '已就绪',
      in_progress: '制作中', completed: '已完成', archived: '已归档'
    };
    var projectStatus = project.status || 'draft';
    var html = '';
    html += '<div class="metric-item"><span class="metric-label">分镜数</span><span class="metric-value">' + shots.length + '</span></div>';
    html += '<div class="metric-item"><span class="metric-label">总时长</span><span class="metric-value">' + Math.round(totalDuration) + 's</span></div>';
    html += '<div class="metric-item"><span class="metric-label">已出视频镜头</span><span class="metric-value">' + videoCount + '</span></div>';
    html += '<div class="metric-item"><span class="metric-label">状态</span><span class="metric-value status-badge status-' + escapeHtml(projectStatus) + '">' + escapeHtml(projectStatusLabels[projectStatus] || projectStatus) + '</span></div>';
    els.projectMetrics.innerHTML = html;
  }

  function updatePreviewPanel(stepNum) {
    var labels = ['', '需求与分镜', '概念图生成', '视频生成', '配音与素材', '单镜头试调', '最终成片与导出'];
    var descriptions = [
      '',
      '填写创作需求，AI 分析并生成分镜。至少确认 1 个分镜后才能进入概念图。',
      '为已确认分镜生成 1 张概念图并设为关键帧；历史图可在素材库查看。',
      '基于关键帧生成真实视频，可取消、播放和下载。',
      '真实 Piper 配音、上传音乐/音效、可编辑多轨时间线；所有编辑保存到服务器并参与最终合成。',
      '选择具体分镜做真实 FFmpeg 精修，保留原视频并可选择精修版用于成片。',
      '从已保存时间线合成包含画面/旁白/音乐/音效/字幕的 MP4，同时可导出 ZIP 素材包。'
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
        var timelineTracks = state.timeline.tracks || [];
        var videoCount4 = 0;
        var narrationCount4 = 0;
        for (var ti = 0; ti < timelineTracks.length; ti++) {
          var role4 = (timelineTracks[ti].track || {}).role;
          if (role4 === 'video') videoCount4 = (timelineTracks[ti].clips || []).length;
          if (role4 === 'narration') narrationCount4 = (timelineTracks[ti].clips || []).length;
        }
        html += '<p>视频轨: <strong>' + videoCount4 + '</strong> 片段</p>';
        html += '<p>配音轨: <strong>' + narrationCount4 + '</strong> 片段</p>';
        html += '<p>时间线版本: <strong>' + (state.timeline.version || 0) + '</strong></p>';
        break;
      }
      case 5: {
        var fp = state.filterParams;
        html += '<p>亮度: ' + fp.brightness + '% | 对比度: ' + fp.contrast + '% | 饱和度: ' + fp.saturation + '%</p>';
        if (state.shotVideoVersions && state.selectedVideoShotId) {
          var versions5 = state.shotVideoVersions[state.selectedVideoShotId];
          html += '<p>视频版本: <strong>' + (versions5 && versions5.items ? versions5.items.length : 0) + '</strong></p>';
        }
        break;
      }
      case 6: {
        html += '<p>分辨率: <strong>' + escapeHtml(state.outputForm.resolution) + '</strong></p>';
        html += '<p>帧率: <strong>' + escapeHtml(String(state.outputForm.fps)) + ' FPS</strong></p>';
        html += '<p>最终成片: <strong>' + (state.finalVideo ? '已生成' : '未生成') + '</strong></p>';
        html += '<p>素材包: <strong>' + (state.exportDownloadUrl ? '已生成' : '未生成') + '</strong></p>';
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
      // "ready" means a generated asset exists; keep it in the workflow so a
      // successfully generated shot does not disappear from later steps.
      if (shots[i].status === 'confirmed' || shots[i].status === 'ready') {
        result.push(shots[i]);
      }
    }
    return result;
  }

  function getWorkflowShot() {
    var shots = getConfirmedShots();
    if (shots.length && state.activeShotIndex < shots.length) {
      return shots[state.activeShotIndex];
    }
    return getActiveShot();
  }

  // ---------------------------------------------------------------
  // MODULE 1: Requirements & Storyboard
  // ---------------------------------------------------------------

  function renderModule1() {
    var project = getActiveProject();
    if (!project) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-icon">&#128196;</div><p>请选择一个项目，或点击右上角「新建项目」开始创作</p></div>';
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

    // Persistent analysis error (toasts are transient and cannot contain links).
    if (state.analysisError) {
      html += '<div class="analysis-error card" role="alert">';
      html += '  <p class="history-task-error">' + escapeHtml(state.analysisError) + '</p>';
      if (state.analysisNeedsConfig) {
        html += '  <p class="field-hint">LLM 服务尚未配置或凭据不可用，请先 ' +
          '<a class="field-hint-link" href="/api-settings">去配置 API</a> 填写 LLM API Key。</p>';
      }
      html += '</div>';
    }

    // Shot cards
    html += '<div class="shot-cards-section">';
    html += '  <h3>分镜脚本 <span class="badge">' + getShotsForActiveProject().length + '</span></h3>';
    html += '  <div class="shot-cards-grid" id="shot-cards-grid">';
    html += renderShotCardsHTML();
    html += '  </div>';
    if (state.stepsCompleted[0]) {
      html += '  <div class="form-actions"><button class="btn btn-primary" id="btn-next-module2">下一步：概念图</button></div>';
    } else if (getShotsForActiveProject().length) {
      html += '  <p class="field-hint">请至少点击一个分镜的“确认分镜”，才能进入概念图步骤。</p>';
    }
    html += '</div>';

    els.studioContentPanel.innerHTML = html;

    // Bind form listeners
    bindRequirementFormListeners();
    var nextModule2 = $('btn-next-module2');
    if (nextModule2) nextModule2.addEventListener('click', function () { switchStep(2); });

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
    state.analysisError = '';
    state.analysisNeedsConfig = false;
    renderModule1();

    (async function() {
      try {
        // Step 1: Create project via API if not already created
        if (!state.projectId) {
          state.analysisStage = '正在创建项目...';
          renderModule1();

          var project = await api('/api/creative/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(projectPayloadFromForm())
          });

          adoptCreatedProject(project);
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
        state.analysisTaskId = taskId;
        saveToLocalStorage();
        await pollTask(taskId, function(progress, stage) {
          state.analysisStage = stage || '正在分析...';
          renderModule1();
        });
        state.analysisTaskId = null;
        saveToLocalStorage();

        // Step 4: Load shots from backend
        state.analysisStage = '正在加载分镜...';
        var shots = await api('/api/creative/projects/' + state.projectId + '/shots');
        state.shots = shots || [];

        hydrateConceptImages();
        hydrateVideoResults();
        await loadWorkflow(state.projectId);
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
        state.analysisError = (e && e.message) || '需求分析失败';
        state.analysisNeedsConfig = isProviderConfigError(e);
        if (state.analysisNeedsConfig) {
          showToast('LLM 服务未配置，请先配置 LLM API Key（去配置 API: /api-settings）', 'warning');
        } else {
          showToast('分析失败: ' + e.message, 'error');
        }
        renderModule1();
      }
    })();
  }

  function sleepWithSignal(ms, signal) {
    return new Promise(function (resolve, reject) {
      var onAbort = null;
      var timer = setTimeout(function () {
        if (onAbort) signal.removeEventListener('abort', onAbort);
        resolve();
      }, ms);
      if (!signal) return;
      if (signal.aborted) {
        clearTimeout(timer);
        var aborted = new Error('轮询已取消');
        aborted.name = 'AbortError';
        reject(aborted);
        return;
      }
      onAbort = function () {
        clearTimeout(timer);
        var error = new Error('轮询已取消');
        error.name = 'AbortError';
        reject(error);
      };
      signal.addEventListener('abort', onAbort, { once: true });
    });
  }

  function abortPoll(taskId) {
    var controller = state.pollAbortControllers[taskId];
    if (controller) {
      controller.abort();
      delete state.pollAbortControllers[taskId];
    }
  }

  function abortAllPolls() {
    Object.keys(state.pollAbortControllers).forEach(function (taskId) {
      abortPoll(taskId);
    });
    state.workflowPollTaskIds = {};
  }

  // Poll a task until completion. Adaptive interval, visibility-aware, abortable.
  async function pollTask(taskId, onProgress, options) {
    options = options || {};
    var controller = options.signal ? null : new AbortController();
    var signal = options.signal || controller.signal;
    if (controller) state.pollAbortControllers[taskId] = controller;
    var projectId = options.projectId || state.projectId;
    var maxMs = options.maxMs || 2 * 60 * 60 * 1000;
    var started = Date.now();
    var delay = 1000;
    var lastSignature = '';
    var networkRetries = 0;
    try {
      while (Date.now() - started < maxMs) {
        if (signal.aborted) {
          var aborted = new Error('轮询已取消');
          aborted.name = 'AbortError';
          throw aborted;
        }
        var hidden = typeof document !== 'undefined' && document.hidden;
        await sleepWithSignal(hidden ? 15000 : delay, signal);
        if (signal.aborted) continue;
        var task;
        try {
          task = await api('/api/creative/tasks/' + encodeURIComponent(taskId), { signal: signal });
          networkRetries = 0;
        } catch (requestError) {
          if (requestError && requestError.name === 'AbortError') throw requestError;
          if (requestError && requestError.status === 0 && networkRetries < 3) {
            networkRetries += 1;
            delay = 3000;
            continue;
          }
          throw requestError;
        }
        if (state.projectId !== projectId) {
          var switched = new Error('项目已切换');
          switched.name = 'AbortError';
          throw switched;
        }
        var stage = task.stage || task.provider_status || task.status;
        var signature = [task.status, stage, task.progress].join('|');
        if (onProgress && signature !== lastSignature) {
          lastSignature = signature;
          onProgress(task.progress || 0, stage, task);
        }
        if (task.status === 'succeeded' || task.status === 'failed' ||
            task.status === 'cancelled' || task.status === 'needs_review') {
          if (task.status === 'cancelled' && options.treatCancelledAsError) {
            var cancelledError = new Error('任务已取消');
            cancelledError.taskStatus = 'cancelled';
            throw cancelledError;
          }
          if (task.status === 'failed' || task.status === 'needs_review') {
            var error = new Error(task.error_message || (task.status === 'failed' ? '任务执行失败' : '任务需要人工确认'));
            error.taskStatus = task.status;
            throw error;
          }
          return task;
        }
        delay = Date.now() - started < 30000 ? 2000 : 5000;
      }
      var timeoutError = new Error('任务仍在运行，请刷新页面后继续查看');
      timeoutError.taskStatus = 'running';
      throw timeoutError;
    } finally {
      if (state.pollAbortControllers[taskId] === controller) {
        delete state.pollAbortControllers[taskId];
      }
    }
  }

  function shotTypeLabel(value) {
    var labels = {
      'close-up': '特写',
      'close_up': '特写',
      'medium-shot': '中景',
      'medium': '中景',
      'wide-shot': '全景',
      'wide': '全景',
      'establishing': '建立镜头',
      'detail': '细节',
      'tracking': '跟拍',
      'macro': '微距',
      'aerial': '航拍',
      'orbit': '环绕'
    };
    return labels[value] || labels[String(value || '').toLowerCase()] || value || '—';
  }

  function shotStatusMeta(status) {
    var value = String(status || '').toLowerCase();
    if (value === 'confirmed') return { className: 'status-confirmed', label: '已确认' };
    if (value === 'ready') return { className: 'status-ready', label: '已生成（待确认）' };
    if (value === 'failed') return { className: 'status-failed', label: '生成失败' };
    if (value.indexOf('generating') === 0 || value === 'analyzing' || value === 'running') {
      return { className: 'status-generating', label: '生成中' };
    }
    return { className: 'status-draft', label: '草稿' };
  }

  function renderShotCardsHTML() {
    var shots = getNormalizedShots();
    if (!shots || shots.length === 0) {
      return '<div class="empty-state">点击"分析需求"生成分镜脚本</div>';
    }

    var html = '';
    for (var i = 0; i < shots.length; i++) {
      var shot = shots[i];
      var statusMeta = shotStatusMeta(shot.status);
      var confirmLabel = shot.status === 'confirmed' ? '取消确认' : '确认分镜';

      html += '<div class="shot-card" data-shot-id="' + escapeHtml(shot.shotId) + '">';
      html += '  <div class="shot-number-badge">' + shot.number + '</div>';
      html += '  <div class="shot-content">';
      html += '    <div class="shot-card-title" data-editable="title">' + escapeHtml(shot.title) + '</div>';
      html += '    <div class="shot-card-meta">';
      html += '      <span class="meta-chip">' + shot.duration + 's</span>';
      html += '      <span class="meta-chip">' + escapeHtml(shotTypeLabel(shot.shotType)) + '</span>';
      html += '    </div>';
      html += '    <div class="shot-desc">' + escapeHtml(shot.sceneDesc || '') + '</div>';
      html += '    <div class="shot-status-badge ' + statusMeta.className + '">' + statusMeta.label + '</div>';
      html += '  </div>';
      html += '  <div class="shot-actions">';
      html += '    <button class="btn-icon btn-edit-shot" title="编辑" data-action="edit">&#9998;</button>';
      html += '    <button class="btn-icon btn-copy-shot" title="复制" data-action="copy">&#128203;</button>';
      html += '    <button class="btn-icon btn-delete-shot" title="删除" data-action="delete">&#128465;</button>';
      html += '    <button class="btn-icon btn-move-up" title="上移" data-action="move-up">&#9650;</button>';
      html += '    <button class="btn-icon btn-move-down" title="下移" data-action="move-down">&#9660;</button>';
      html += '    <button class="btn-outline btn-sm btn-confirm-shot" data-action="confirm">' + confirmLabel + '</button>';
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
      if (shots[i].shotId === shotId || shots[i].id === shotId) {
        return normalizeShot(shots[i]);
      }
    }
    return null;
  }

  function findShotIndex(shotId) {
    var shots = getShotsForActiveProject();
    for (var i = 0; i < shots.length; i++) {
      if (shots[i].shotId === shotId || shots[i].id === shotId) return i;
    }
    return -1;
  }

  function shotUpdatePayload(shot) {
    return {
      scene_title: shot.title,
      duration_s: shot.duration,
      shot_type: shot.shotType,
      camera_movement: shot.cameraMove,
      dialogue: shot.narration,
      prompt_en: shot.keyframePrompt,
      negative_prompt: shot.negativePrompt
    };
  }

  function refreshShotsFromBackend() {
    return reloadShotsAndHydrate().then(function () {
      renderCurrentModule();
    });
  }

  function handleEditShot(shotId) {
    var shot = findShotById(shotId);
    if (!shot) return;

    showEditShotDialog(shot, function() {
      api('/api/creative/shots/' + encodeURIComponent(shot.id), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(shotUpdatePayload(shot))
      }).then(function () {
        saveToLocalStorage();
        return refreshShotsFromBackend();
      }).then(function () {
        updatePreviewPanel(state.activeStep);
        showToast('分镜已更新', 'success');
      }).catch(function (error) {
        showToast('分镜更新失败: ' + error.message, 'error');
      });
    });
  }

  function handleCopyShot(shotId) {
    var shot = findShotById(shotId);
    if (!shot || !state.projectId) return;

    api('/api/creative/projects/' + encodeURIComponent(state.projectId) + '/shots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scene_title: (shot.title || '') + ' (副本)',
        scene_description: shot.sceneDesc || '',
        shot_type: shot.shotType || 'medium-shot',
        duration_s: shot.duration || 5,
        camera_movement: shot.cameraMove || '',
        dialogue: shot.narration || '',
        prompt_cn: shot.prompt_cn || '',
        prompt_en: shot.keyframePrompt || '',
        negative_prompt: shot.negativePrompt || '',
        status: 'draft'
      })
    }).then(function () {
      return refreshShotsFromBackend();
    }).then(function () {
      showToast('分镜已复制', 'success');
    }).catch(function (error) {
      showToast('复制分镜失败: ' + error.message, 'error');
    });
  }

  function handleDeleteShot(shotId) {
    showConfirmDialog('删除分镜', '确定要删除该分镜吗？此操作会删除服务器上的分镜记录。', '删除', function() {
      api('/api/creative/shots/' + encodeURIComponent(shotId), {
        method: 'DELETE'
      }).then(function () {
        return refreshShotsFromBackend();
      }).then(function () {
        showToast('分镜已删除', 'info');
      }).catch(function (error) {
        showToast('删除分镜失败: ' + error.message, 'error');
      });
    });
  }

  function handleMoveShot(shotId, dir) {
    var shots = getShotsForActiveProject();
    var idx = findShotIndex(shotId);
    if (idx === -1 || !state.projectId) return;
    var newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= shots.length) return;

    var order = shots.map(function (item) { return item.id; });
    var moved = order.splice(idx, 1)[0];
    order.splice(newIdx, 0, moved);

    api('/api/creative/shots/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: state.projectId, ordered_ids: order })
    }).then(function () {
      return refreshShotsFromBackend();
    }).catch(function (error) {
      showToast('调整顺序失败: ' + error.message, 'error');
      refreshShotsFromBackend();
    });
  }

  function handleConfirmShot(shotId) {
    var shot = findShotById(shotId);
    if (!shot) return;
    var next = (shot.status === 'confirmed')
      ? (shot.primaryImageAssetId || shot.primary_image_asset_id ? 'ready' : 'draft')
      : 'confirmed';

    api('/api/creative/shots/' + encodeURIComponent(shot.id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next })
    }).then(function () {
      shot.status = next;
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
      showToast(next === 'confirmed' ? '分镜已确认' : '分镜已取消确认', 'info');
    }).catch(function (error) {
      shot.status = shot.status;
      showToast('分镜状态保存失败: ' + error.message, 'error');
    });
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

    var imageModels = state.generationModels.image || [];
    var currentImageModel = selectedImageModelInfo();
    var imageCaps = (currentImageModel && currentImageModel.capabilities) || {};

    // Prompt fields (negative prompt is hidden when the selected model rejects it)
    html += '<div class="prompt-fields card">';
    html += '  <div class="form-group"><label>正向提示词</label><textarea id="module2-keyframe-prompt" rows="2">' + escapeHtml(currentShot.keyframePrompt || '') + '</textarea></div>';
    if (imageCaps.supports_negative_prompt) {
      html += '  <div class="form-group"><label>负向提示词</label><textarea id="module2-negative-prompt" rows="2">' + escapeHtml(currentShot.negativePrompt || '') + '</textarea></div>';
    }
    html += '</div>';

    // Model selector (server-side registry; unconfigured models are disabled
    // with a reason instead of being silently hidden).
    html += '<div class="model-selector card">';
    html += '  <label>选择模型:</label>';
    html += '  <select id="module2-model">';
    if (!imageModels.length) {
      html += '    <option value="">尚未接入图片生成模型</option>';
    } else {
      for (var m = 0; m < imageModels.length; m++) {
        var modelItem = imageModels[m];
        var disabled = modelItem.available ? '' : ' disabled';
        var suffix = modelItem.available ? '' : '（未配置）';
        html += '    <option value="' + escapeHtml(modelItem.key) + '"' + disabled +
          (normalizeModelKey(state.selectedImageModel) === modelItem.key ? ' selected' : '') + '>' +
          escapeHtml(modelOptionLabel(modelItem) + suffix) + '</option>';
      }
    }
    html += '  </select>';
    if (imageCaps.sizes && imageCaps.sizes.length) {
      html += '  <label>尺寸:</label><select id="module2-size">';
      for (var si = 0; si < imageCaps.sizes.length; si += 1) {
        var sizeValue = imageCaps.sizes[si];
        html += '<option value="' + escapeHtml(sizeValue) + '"' +
          (sizeValue === imageCaps.default_size ? ' selected' : '') + '>' +
          escapeHtml(sizeValue === 'custom' ? '自定义（在 Prompt 中说明）' : sizeValue) + '</option>';
      }
      html += '</select>';
    }
    if (imageCaps.ratios && imageCaps.ratios.length) {
      html += '  <label>比例:</label><select id="module2-ratio">';
      for (var ri = 0; ri < imageCaps.ratios.length; ri += 1) {
        var ratioValue = imageCaps.ratios[ri];
        html += '<option value="' + escapeHtml(ratioValue) + '"' +
          (ratioValue === imageCaps.default_ratio ? ' selected' : '') + '>' +
          escapeHtml(ratioValue) + '</option>';
      }
      html += '</select>';
    }
    if (imageCaps.supports_seed) {
      html += '  <label>种子:</label><input id="module2-seed" type="number" min="0" placeholder="随机" />';
    }
    if (imageCaps.supports_watermark) {
      html += '  <label class="inline-check"><input id="module2-watermark" type="checkbox" /> 水印</label>';
    }
    if (imageCaps.supports_reference_image) {
      html += '  <label>参考图片:</label><select id="module2-reference">';
      var seenRefs = {};
      var currentImageAsset = currentShot.primary_image_asset_id || currentShot.keyframe_asset_id;
      html += '<option value="">不使用参考图</option>';
      if (currentImageAsset) {
        seenRefs[currentImageAsset] = true;
        html += '<option value="' + escapeHtml(currentImageAsset) + '"' +
          (state.selectedReferenceAssetId === currentImageAsset ? ' selected' : '') +
          '>当前分镜图片</option>';
      }
      for (var ra = 0; ra < state.referenceAssets.length; ra += 1) {
        var refAsset = state.referenceAssets[ra];
        if (seenRefs[refAsset.id]) continue;
        seenRefs[refAsset.id] = true;
        html += '<option value="' + escapeHtml(refAsset.id) + '"' +
          (state.selectedReferenceAssetId === refAsset.id ? ' selected' : '') + '>' +
          escapeHtml((refAsset.name || '图片') + ' · ' + AIGV.formatTime(refAsset.created_at)) + '</option>';
      }
      html += '  </select>';
      html += '  <label class="inline-check">上传参考图: <input id="module2-reference-file" type="file" accept="image/png,image/jpeg,image/webp" /></label>';
    }
    if (state.imageGenInProgress) {
      html += '  <button class="btn btn-primary" disabled><span class="spinner"></span> 生成中...</button>';
    } else {
      html += '  <button class="btn btn-primary" id="btn-generate-concept"' + (currentImageModel ? '' : ' disabled') + '>&#9889; 生成概念图</button>';
    }
    if (!currentImageModel) {
      html += '  <p class="field-hint">尚未配置可用的图片模型。请 <a class="field-hint-link" href="/api-settings">去配置 API</a>（ARK / OpenAI 图片），或启用 COMFYUI_ENABLED 与 COMFYUI_BASE_URL。</p>';
      var reasons = imageModels.filter(function (item) { return !item.available; });
      for (var rr = 0; rr < reasons.length; rr += 1) {
        html += '  <p class="field-hint">' + escapeHtml(reasons[rr].display_name) + '：' +
          escapeHtml(reasons[rr].unavailable_reason || '不可用') + '</p>';
      }
    }
    html += '</div>';

    // Concept images grid
    html += '<div class="concept-images-section">';
    html += renderConceptImagesHTML(shotId);
    html += '</div>';
    if (state.stepsCompleted[1]) {
      html += '<div class="form-actions"><button class="btn btn-primary" id="btn-next-module3">下一步：生成视频</button></div>';
    }

    els.studioContentPanel.innerHTML = html;

    // Bind shot selectors
    bindShotSelector();
    var nextModule3 = $('btn-next-module3');
    if (nextModule3) nextModule3.addEventListener('click', function () { switchStep(3); });

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

    // Model/capability driven controls
    var modelSel = $('module2-model');
    if (modelSel) {
      modelSel.addEventListener('change', function() {
        state.selectedImageModel = normalizeModelKey(modelSel.value);
        state.selectedReferenceAssetId = '';
        saveToLocalStorage();
        renderModule2();
      });
    }
    var refSel = $('module2-reference');
    if (refSel) {
      refSel.addEventListener('change', function() {
        state.selectedReferenceAssetId = refSel.value;
      });
    }
    var refFile = $('module2-reference-file');
    if (refFile) {
      refFile.addEventListener('change', function() {
        if (refFile.files && refFile.files[0]) uploadReferenceImage(refFile.files[0]);
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

  function uploadReferenceImage(file) {
    if (!file) return;
    if (['image/png', 'image/jpeg', 'image/webp'].indexOf(file.type) === -1) {
      showToast('参考图片仅支持 PNG/JPEG/WebP', 'warning');
      return;
    }
    var formData = new FormData();
    formData.append('file', file);
    formData.append('name', file.name.replace(/\.[^.]+$/, ''));
    api('/api/assets/upload', { method: 'POST', body: formData }).then(function(asset) {
      state.referenceAssets.unshift(asset);
      state.selectedReferenceAssetId = asset.id;
      renderModule2();
      showToast('参考图已上传并选中', 'success');
    }).catch(function(error) {
      showToast('参考图上传失败: ' + error.message, 'error');
    });
  }

  function handleGenerateConceptImage() {
    if (state.imageGenInProgress) return;
    var shot = getActiveShot();
    if (!shot) return;
    var model = selectedImageModelInfo();
    if (!model) {
      showToast('尚未配置可用的图片生成模型', 'warning');
      return;
    }
    var caps = model.capabilities || {};

    state.imageGenInProgress = true;
    renderModule2();

    (async function() {
      try {
        if (!state.projectId) {
          throw new Error('请先创建项目');
        }

        var modelEl = $('module2-model');
        var sizeEl = $('module2-size');
        var ratioEl = $('module2-ratio');
        var seedEl = $('module2-seed');
        var watermarkEl = $('module2-watermark');
        var referenceEl = $('module2-reference');
        var promptEl = $('module2-keyframe-prompt');
        var modelKey = modelEl ? modelEl.value : model.key;
        if (!modelKey) {
          throw new Error('尚未接入图片生成模型，请在服务器配置 Provider');
        }
        var payload = {
          model_key: modelKey,
          prompt: promptEl ? promptEl.value : shot.keyframePrompt
        };
        if (sizeEl && sizeEl.value) payload.size = sizeEl.value;
        if (ratioEl && ratioEl.value) payload.ratio = ratioEl.value;
        if (seedEl && seedEl.value !== '') payload.seed = parseInt(seedEl.value, 10);
        if (watermarkEl) payload.watermark = !!watermarkEl.checked;
        if (caps.supports_reference_image && referenceEl && referenceEl.value) {
          payload.reference_asset_id = referenceEl.value;
        }

        var task = await api('/api/creative/shots/' + shot.id + '/images', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        state.currentImageTaskId = task.id;
        saveToLocalStorage();

        var finalTask = await pollTask(task.id, function(progress, stage) {
          state.analysisStage = stage || '生成中...';
        });
        finishGeneration('image', finalTask);
      } catch (e) {
        finishGenerationFailure('image', e);
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
      var colors = img.colors && img.colors.length ? img.colors : ['#1a2433', '#33465c'];
      var gradient = 'linear-gradient(135deg, ' + colors.join(', ') + ')';
      var keyframeBadge = img.isKeyframe ? '<span class="keyframe-badge">&#9733; 关键帧</span>' : '';
      var favClass = img.isFavorite ? 'fav-active' : '';
      var label = 'Image ' + (i + 1);
      var thumbStyle = img.url
        ? 'background-image: url(' + JSON.stringify(img.url) + '); background-size: cover; background-position: center;'
        : 'background: ' + gradient + ';';

      html += '<div class="concept-image-card" data-image-id="' + escapeHtml(img.id) + '">';
      html += '  <div class="concept-image-thumb" style="' + thumbStyle + '">';
      if (!img.url) {
        html += '    <div class="concept-overlay">';
        html += '      <svg viewBox="0 0 64 64" width="48" height="48" fill="rgba(255,255,255,0.6)">';
        html += '        <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.8)" stroke-width="2" fill="none"/>';
        html += '        <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.5)"/>';
        html += '        <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.4)"/>';
        html += '        <rect x="14" y="40" width="12" height="2" rx="1" fill="rgba(255,255,255,0.3)"/>';
        html += '      </svg>';
        html += '    </div>';
      }
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
      html += '    <span class="meta-chip">' + escapeHtml(img.modelLabel || img.model || '生成图片') + '</span>';
      html += '    <span class="meta-chip">#' + escapeHtml(String(img.seed || '—')) + '</span>';
      html += '  </div>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function bindConceptImageActions(shotId) {
    var container = els.studioContentPanel;
    if (!container) return;
    if (container.getAttribute('data-concept-actions-bound') === '1') return;
    container.setAttribute('data-concept-actions-bound', '1');

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
    var shotId = img.shotId || findImageContainerShotId(imageId);
    var images = state.conceptImages[shotId] || [];
    function applyLocal() {
      for (var i = 0; i < images.length; i++) {
        images[i].isKeyframe = (images[i].id === imageId);
      }
      for (var j = 0; j < state.shots.length; j++) {
        if (state.shots[j].id === shotId) {
          state.shots[j].keyframe_asset_id = img.assetId || img.id;
          break;
        }
      }
      saveToLocalStorage();
      renderModule2();
    }
    if (!img.assetId) {
      applyLocal();
      showToast('关键帧已设置', 'success');
      return;
    }
    api('/api/creative/shots/' + shotId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyframe_asset_id: img.assetId })
    }).then(function () {
      applyLocal();
      showToast('关键帧已设置', 'success');
    }).catch(function (e) {
      showToast('设置关键帧失败: ' + e.message, 'error');
    });
  }

  function handleFavoriteImage(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    var nextFavorite = !img.isFavorite;
    if (!img.assetId) {
      img.isFavorite = nextFavorite;
      renderModule2();
      return;
    }
    api('/api/assets/' + encodeURIComponent(img.assetId)).then(function(asset) {
      var metadata = Object.assign({}, (asset && asset.metadata) || {}, {
        favorite: nextFavorite
      });
      return api('/api/assets/' + encodeURIComponent(img.assetId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metadata: metadata })
      });
    }).then(function() {
      img.isFavorite = nextFavorite;
      img.metadata = Object.assign({}, img.metadata || {}, { favorite: nextFavorite });
      renderModule2();
      showToast(nextFavorite ? '已收藏' : '已取消收藏', 'info');
    }).catch(function(error) {
      showToast('收藏失败: ' + error.message, 'error');
    });
  }

  function handleViewImageLarge(imageId) {
    var img = findImageById(imageId);
    if (!img) return;
    var gradient = 'linear-gradient(135deg, ' + (img.colors || ['#1a2433', '#33465c']).join(', ') + ')';
    var imageHtml = img.url
      ? '<img src="' + escapeHtml(img.url) + '" alt="生成图片" style="width:100%; height:auto; border-radius:8px; display:block;" />'
      : '<div class="large-image" style="background: ' + gradient + '; width: 100%; aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center;">' +
        '<svg viewBox="0 0 64 64" width="96" height="96" fill="rgba(255,255,255,0.4)">' +
        '<rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.6)" stroke-width="2" fill="none"/>' +
        '<circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.3)"/>' +
        '<polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.3)"/></svg></div>';
    var html = '';
    html += '<div class="modal-overlay" id="image-modal">';
    html += '  <div class="modal-content modal-lg">';
    html += '    <button class="modal-close" id="modal-close-btn">&times;</button>';
    html += '    <div class="modal-body">';
    html += imageHtml;
    html += '      <div class="image-details">';
    html += '        <p><strong>提示词:</strong> ' + escapeHtml(img.prompt || '—') + '</p>';
    html += '        <p><strong>模型:</strong> ' + escapeHtml(img.modelLabel || img.model || '—') + '</p>';
    html += '        <p><strong>种子:</strong> ' + escapeHtml(String(img.seed === undefined ? '—' : img.seed)) + '</p>';
    html += '        <p><strong>分辨率:</strong> ' + escapeHtml(String(img.width || '—')) + 'x' + escapeHtml(String(img.height || '—')) + '</p>';
    html += '        <p><strong>关键帧:</strong> ' + (img.isKeyframe ? '是' : '否') + '</p>';
    html += '      </div>';
    if (img.downloadUrl) {
      html += '      <a class="btn btn-secondary" href="' + escapeHtml(img.downloadUrl) + '" target="_blank" rel="noopener">下载图片</a>';
    }
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
    var params = img.params || {};
    var rows = [
      ['模型', img.modelLabel || img.model || '—'],
      ['尺寸', (params.width || img.width || '—') + 'x' + (params.height || img.height || '—')],
      ['比例', params.ratio || '—'],
      ['种子', params.seed === null || params.seed === undefined ? '—' : params.seed],
      ['生成时间', img.generatedAt || '—']
    ];
    var rowsHtml = '';
    for (var i = 0; i < rows.length; i += 1) {
      rowsHtml += '<div class="param-row"><span class="param-label">' + escapeHtml(rows[i][0]) + '</span><span>' +
        escapeHtml(String(rows[i][1])) + '</span></div>';
    }
    var html = '';
    html += '<div class="modal-overlay" id="params-modal">';
    html += '  <div class="modal-content">';
    html += '    <button class="modal-close" id="params-close-btn">&times;</button>';
    html += '    <h3>生成参数</h3>';
    html += '    <div class="params-table">';
    html += rowsHtml;
    html += '      <div class="param-row"><span class="param-label">正向提示词</span><span class="param-prompt">' + escapeHtml(img.prompt || '—') + '</span></div>';
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
    var img = findImageById(imageId);
    if (!img) return;
    showConfirmDialog('删除概念图', '确定要删除该概念图吗？如果它仍被分镜引用，服务器会拒绝删除。', '删除', function() {
      if (!img.assetId) {
        var shotId = findImageContainerShotId(imageId);
        if (!shotId) return;
        var images = state.conceptImages[shotId] || [];
        for (var i = 0; i < images.length; i++) {
          if (images[i].id === imageId) { images.splice(i, 1); break; }
        }
        if (images.length === 0) delete state.conceptImages[shotId];
        saveToLocalStorage();
        renderModule2();
        return;
      }
      api('/api/assets/' + encodeURIComponent(img.assetId), { method: 'DELETE' })
        .then(function() {
          showToast('图片已删除', 'success');
          return reloadShotsAndHydrate();
        })
        .then(function() {
          renderModule2();
        })
        .catch(function(error) {
          showToast((error && error.message) || '删除失败', 'error');
        });
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

    var keyframeColors = keyframe.colors && keyframe.colors.length ? keyframe.colors : ['#1a2433', '#33465c'];
    var gradient = 'linear-gradient(135deg, ' + keyframeColors.join(', ') + ')';
    var keyframeStyle = keyframe.url
      ? 'background-image: url(' + JSON.stringify(keyframe.url) + '); background-size: cover; background-position: center;'
      : 'background: ' + gradient + ';';
    var existingVideo = shotId && state.videoResults[shotId] ? state.videoResults[shotId] : null;

    var html = '';
    html += '<div class="module-header">';
    html += '  <h2 class="module-title">视频生成</h2>';
    html += '</div>';

    // Keyframe display
    html += '<div class="keyframe-display card">';
    html += '  <h4>关键帧</h4>';
    html += '  <div class="keyframe-preview" style="' + keyframeStyle + ' aspect-ratio: 16/9; border-radius: 8px; display: flex; align-items: center; justify-content: center;">';
    if (!keyframe.url) {
      html += '    <svg viewBox="0 0 64 64" width="64" height="64" fill="rgba(255,255,255,0.4)">';
      html += '      <rect x="8" y="12" width="48" height="40" rx="4" stroke="rgba(255,255,255,0.6)" stroke-width="2" fill="none"/>';
      html += '      <circle cx="24" cy="28" r="6" fill="rgba(255,255,255,0.3)"/>';
      html += '      <polygon points="30,38 38,32 46,38 46,46 30,46" fill="rgba(255,255,255,0.3)"/>';
      html += '    </svg>';
    }
    html += '  </div>';
    html += '  <p class="keyframe-prompt">' + escapeHtml(keyframe.prompt) + '</p>';
    html += '</div>';

    // Video params form (capability driven)
    var videoModels = state.generationModels.video || [];
    var currentVideoModel = selectedVideoModelInfo();
    var videoCaps = (currentVideoModel && currentVideoModel.capabilities) || {};
    html += '<div class="video-params card">';
    html += '  <h4>视频参数</h4>';
    html += '  <div class="form-grid">';
    html += '    <div class="form-group"><label>模型</label><select id="vparam-model">';
    if (!videoModels.length) {
      html += '      <option value="">尚未接入视频生成模型</option>';
    } else {
      for (var vmi = 0; vmi < videoModels.length; vmi++) {
        var videoModel = videoModels[vmi];
        html += '      <option value="' + escapeHtml(videoModel.key) + '"' +
          (videoModel.available ? '' : ' disabled') +
          (normalizeModelKey(state.selectedVideoModel) === videoModel.key ? ' selected' : '') + '>' +
          escapeHtml(modelOptionLabel(videoModel) + (videoModel.available ? '' : '（未配置）')) + '</option>';
      }
    }
    html += '    </select></div>';
    if (videoCaps.ratios && videoCaps.ratios.length) {
      html += '    <div class="form-group"><label>比例</label><select id="vparam-ratio">';
      for (var vri = 0; vri < videoCaps.ratios.length; vri += 1) {
        var videoRatio = videoCaps.ratios[vri];
        html += '<option value="' + escapeHtml(videoRatio) + '"' +
          (videoRatio === '16:9' || (vri === 0 && videoCaps.ratios.indexOf('16:9') === -1) ? ' selected' : '') +
          '>' + escapeHtml(videoRatio) + '</option>';
      }
      html += '    </select></div>';
    }
    if (videoCaps.durations && videoCaps.durations.length) {
      html += '    <div class="form-group"><label>时长</label><select id="vparam-duration">';
      for (var vdi = 0; vdi < videoCaps.durations.length; vdi += 1) {
        var videoDuration = videoCaps.durations[vdi];
        html += '<option value="' + escapeHtml(String(videoDuration)) + '"' +
          (videoDuration === 5 || (vdi === 0 && videoCaps.durations.indexOf(5) === -1) ? ' selected' : '') +
          '>' + escapeHtml(String(videoDuration)) + 's</option>';
      }
      html += '    </select></div>';
    }
    if (videoCaps.resolutions && videoCaps.resolutions.length) {
      html += '    <div class="form-group"><label>分辨率</label><select id="vparam-resolution">';
      for (var vsi = 0; vsi < videoCaps.resolutions.length; vsi += 1) {
        var videoResolution = videoCaps.resolutions[vsi];
        html += '<option value="' + escapeHtml(videoResolution) + '"' +
          (videoResolution === '720p' ? ' selected' : '') + '>' + escapeHtml(videoResolution) + '</option>';
      }
      html += '    </select></div>';
    }
    if (videoCaps.supports_audio) {
      html += '    <div class="form-group"><label><input type="checkbox" id="vparam-audio"' +
        (videoCaps.default_audio ? ' checked' : '') + ' /> 生成音频</label></div>';
    }
    if (videoCaps.supports_seed) {
      html += '    <div class="form-group"><label>种子</label><input id="vparam-seed" type="number" min="0" placeholder="随机" /></div>';
    }
    html += '  </div>';
    if (!currentVideoModel) {
      html += '  <p class="field-hint">尚未配置可用的视频模型。请 <a class="field-hint-link" href="/api-settings">去配置 API</a>（ARK / Seedance / Luma）。</p>';
      var videoReasons = videoModels.filter(function (item) { return !item.available; });
      for (var vrr = 0; vrr < videoReasons.length; vrr += 1) {
        html += '  <p class="field-hint">' + escapeHtml(videoReasons[vrr].display_name) + '：' +
          escapeHtml(videoReasons[vrr].unavailable_reason || '不可用') + '</p>';
      }
    } else if (!videoCaps.supports_reference_image) {
      html += '  <p class="field-hint">当前模型不支持参考图，将按文本 Prompt 生成视频。</p>';
    }

    // Generate / Status. Providers rarely expose a numeric percentage, so the
    // UI shows the real stage and an indeterminate bar instead of fake progress.
    if (state.videoGenInProgress) {
      html += '  <div class="video-progress">';
      html += '    <div class="progress-bar"><div class="progress-fill progress-indeterminate"></div></div>';
      html += '    <p class="progress-label">' + escapeHtml(state.videoGenStage || '生成中...') + '</p>';
      html += '    <button class="btn btn-danger" id="btn-cancel-video">取消生成</button>';
      html += '  </div>';
    } else if (existingVideo && existingVideo.status === 'completed' && existingVideo.fileUrl) {
      html += '  <div class="video-result">';
      html += '    <video src="' + escapeHtml(existingVideo.fileUrl) + '" controls playsinline style="width:100%; aspect-ratio:16/9; border-radius:8px; background:#000;"></video>';
      html += '    <p class="field-hint">' + escapeHtml(existingVideo.model || '') +
        (existingVideo.createdAt ? ' · ' + escapeHtml(existingVideo.createdAt) : '') + '</p>';
      html += '    <div class="video-actions">';
      html += '      <a class="btn btn-secondary" href="' + escapeHtml(existingVideo.downloadUrl || existingVideo.fileUrl) + '" target="_blank" rel="noopener">下载视频</a>';
      html += '      <button class="btn btn-secondary" id="btn-regenerate-video">重新生成</button>';
      html += '    </div>';
      html += '  </div>';
    } else {
      html += '  <div class="form-actions">';
      html += '    <button class="btn btn-primary" id="btn-generate-video"' + (currentVideoModel ? '' : ' disabled') + '>&#127916; 生成视频</button>';
      html += '  </div>';
    }
    html += '</div>';
    if (state.stepsCompleted[2]) {
      html += '<div class="form-actions">' +
        '<button class="btn btn-primary" id="btn-next-module4">下一步：配音与素材</button>' +
        '<button class="btn btn-secondary" id="btn-next-module6">直接导出素材包</button></div>';
    }

    els.studioContentPanel.innerHTML = html;

    // Bind range sliders
    bindVideoRangeSliders();
    var nextModule4 = $('btn-next-module4');
    if (nextModule4) nextModule4.addEventListener('click', function () { switchStep(4); });
    var nextModule6 = $('btn-next-module6');
    if (nextModule6) nextModule6.addEventListener('click', function () { switchStep(6); });

    var videoModelSelect = $('vparam-model');
    if (videoModelSelect) {
      videoModelSelect.addEventListener('change', function() {
        state.selectedVideoModel = normalizeModelKey(videoModelSelect.value);
        saveToLocalStorage();
        renderModule3();
      });
    }

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
    var shot = getWorkflowShot();
    if (!shot) return;
    var model = selectedVideoModelInfo();
    if (!model) {
      showToast('尚未配置可用的视频生成模型（去配置 API: /api-settings）', 'warning');
      return;
    }
    var caps = model.capabilities || {};

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

        var modelEl = $('vparam-model');
        var ratioEl = $('vparam-ratio');
        var durationEl = $('vparam-duration');
        var resolutionEl = $('vparam-resolution');
        var audioEl = $('vparam-audio');
        var seedEl = $('vparam-seed');
        var modelKey = modelEl ? modelEl.value : model.key;
        if (!modelKey) {
          throw new Error('尚未接入视频生成模型，请在服务器配置 Provider');
        }
        var images = state.conceptImages[shot.id] || [];
        var keyframe = null;
        for (var k = 0; k < images.length; k++) {
          if (images[k].isKeyframe) { keyframe = images[k]; break; }
        }
        var referenceAssetId = shot.keyframe_asset_id || shot.keyframeAssetId ||
          (keyframe && keyframe.assetId) || shot.primary_image_asset_id || null;

        var payload = {
          model_key: modelKey,
          prompt: shot.keyframePrompt || shot.prompt_en || shot.prompt_cn || ''
        };
        if (ratioEl && ratioEl.value) payload.ratio = ratioEl.value;
        if (durationEl && durationEl.value) payload.duration_s = parseInt(durationEl.value, 10);
        if (resolutionEl && resolutionEl.value) payload.resolution = resolutionEl.value;
        if (audioEl && caps.supports_audio) payload.generate_audio = !!audioEl.checked;
        if (seedEl && seedEl.value !== '' && caps.supports_seed) {
          payload.seed = parseInt(seedEl.value, 10);
        }
        if (caps.supports_reference_image && referenceAssetId) {
          payload.reference_asset_id = referenceAssetId;
        }

        var task = await api('/api/creative/shots/' + shot.id + '/videos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        state.currentVideoTaskId = task.id;
        saveToLocalStorage();

        var finalTask = await pollTask(task.id, function(progress, stage) {
          state.videoGenStage = stage || '生成中...';
          if (state.activeStep === 3) renderModule3();
        });
        finishGeneration('video', finalTask);
      } catch (e) {
        finishGenerationFailure('video', e);
      }
    })();
  }

  function handleCancelVideo() {
    state.videoCancelRequested = true;
    if (!state.currentVideoTaskId) {
      showToast('没有正在运行的任务', 'info');
      return;
    }
    showToast('正在取消...', 'info');
    api('/api/creative/tasks/' + state.currentVideoTaskId + '/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    }).then(function () {
      showToast('取消请求已提交', 'info');
    }).catch(function (e) {
      showToast('取消失败: ' + e.message, 'error');
    });
  }

  function handleRegenerateVideo() {
    var shot = getWorkflowShot();
    if (!shot) return;
    if (state.videoResults[shot.shotId]) {
      delete state.videoResults[shot.shotId];
    }
    saveToLocalStorage();
    handleGenerateVideo();
  }

  // ---------------------------------------------------------------
  // MODULE 4: Multimodal Enhancement
  // ---------------------------------------------------------------

  function renderModule4() {
    if (!state.projectId) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-state"><p class="empty-title">请先选择或创建项目</p></div></div>';
      return;
    }
    var shots = state.shots || [];
    var html = '';
    html += '<div class="module-header"><h2 class="module-title">配音与素材</h2></div>';
    html += '<div class="warning-stack"><div class="warning-item">' +
      '真实能力：Piper 中文配音、真实音频上传、可编辑多轨时间线与 FFmpeg 成片合成。所有修改保存到服务器。' +
      '</div></div>';
    if (!shots.length) {
      html += '<div class="module-empty"><div class="empty-state"><p class="empty-title">还没有分镜</p>' +
        '<p class="empty-desc">请先在第 01–03 步生成并确认分镜视频。</p></div></div>';
      els.studioContentPanel.innerHTML = html;
      return;
    }

    html += renderNarrationPanelHTML(shots);
    html += renderAudioLibraryPanelHTML('music');
    html += renderAudioLibraryPanelHTML('sfx');
    html += renderTimelineEditorHTML();
    html += '<div class="form-actions"><button class="btn btn-secondary" id="btn-module4-preview-refine">下一步：单镜头试调（可选）</button>' +
      '<button class="btn btn-primary" id="btn-module4-final">进入最终成片与导出</button></div>';
    els.studioContentPanel.innerHTML = html;
    bindModule4Events();

    (state.shots || []).forEach(function (shot) {
      state.shotAudioLoaded = state.shotAudioLoaded || {};
      if (state.shotAudioLoaded[shot.id]) return;
      state.shotAudioLoaded[shot.id] = true;
      loadShotAudio(shot.id).then(function () {
        if (state.activeStep === 4) renderModule4();
      });
    });
  }

  function voiceOptionsHTML() {
    var html = '';
    if (!state.ttsVoices.length) {
      html += '<option value="">没有可用的 TTS 音色</option>';
      return html;
    }
    for (var i = 0; i < state.ttsVoices.length; i++) {
      var voice = state.ttsVoices[i];
      var selected = state.narrationForm.voiceId === voice.id ? ' selected' : '';
      html += '<option value="' + escapeHtml(voice.id) + '"' + selected +
        (voice.available ? '' : ' disabled') + '>' +
        escapeHtml(voice.label || voice.id) +
        (voice.available ? '' : '（不可用：' + escapeHtml(voice.unavailable_reason || '') + '）') +
        '</option>';
    }
    return html;
  }

  function renderNarrationPanelHTML(shots) {
    var html = '';
    html += '<div class="enhance-section card"><h3>真实配音</h3>';
    html += '<div class="form-grid">';
    html += '<div class="form-group"><label>音色</label><select id="tts-voice-select">' + voiceOptionsHTML() + '</select></div>';
    html += '<div class="form-group"><label>语速: <span id="tts-rate-label">' +
      Number(state.narrationForm.speechRate || 1).toFixed(1) + 'x</span></label>' +
      '<input type="range" id="tts-rate" min="0.5" max="2.0" step="0.1" value="' +
      (state.narrationForm.speechRate || 1) + '" /></div>';
    html += '<div class="form-group"><label>音量: <span id="tts-volume-label">' +
      Number(state.narrationForm.volume == null ? 1 : state.narrationForm.volume).toFixed(1) + '</span></label>' +
      '<input type="range" id="tts-volume" min="0" max="2" step="0.1" value="' +
      (state.narrationForm.volume == null ? 1 : state.narrationForm.volume) + '" /></div>';
    html += '</div>';
    if (!state.ttsVoices.some(function (voice) { return voice.available; })) {
      html += '<div class="warning-item">当前没有可用的真实音色。请安装 Piper 模型并配置 data/tts_voices.json；未安装的音色不会显示为可生成。</div>';
    }

    for (var i = 0; i < shots.length; i++) {
      var shot = shots[i];
      var audio = state.shotAudio[shot.id] || null;
      var currentId = audio ? audio.current_audio_asset_id : shot.audio_asset_id;
      var options = (audio && audio.audio_options) || shot.audio_options || {};
      var duration = audio && audio.audio_duration_s;
      if (duration == null) duration = shot.audio_duration_s;
      html += '<div class="audio-shot-card" data-shot-id="' + escapeHtml(shot.id) + '">';
      html += '<div class="audio-shot-head"><strong>' + escapeHtml(shot.scene_title || ('镜头 ' + shot.sequence_no)) + '</strong>';
      html += '<span class="meta-chip">' + (currentId ? '已有配音' : '无配音') + '</span></div>';
      html += '<textarea class="audio-dialogue-input" data-dialogue-shot="' + escapeHtml(shot.id) + '" rows="2">' +
        escapeHtml(shot.dialogue || '') + '</textarea>';
      if (currentId) {
        html += '<div class="audio-current">';
        html += '<audio controls preload="none" src="/api/assets/' + encodeURIComponent(currentId) + '/file"></audio>';
        html += '<div class="audio-meta">' + escapeHtml(options.voice_label || options.voice_id || '已保存配音') +
          (duration ? ' · ' + Number(duration).toFixed(2) + 's' : '') + '</div>';
        html += '<a class="btn btn-secondary btn-sm" href="/api/assets/' + encodeURIComponent(currentId) + '/download">下载</a>';
        html += '</div>';
      }
      html += '<div class="form-actions">';
      html += '<button class="btn btn-primary btn-sm" data-tts-shot="' + escapeHtml(shot.id) + '">生成配音</button>';
      if (currentId) {
        html += '<button class="btn btn-secondary btn-sm" data-audio-none="' + escapeHtml(shot.id) + '">设为无配音</button>';
      }
      html += '</div>';
      if (audio && audio.items && audio.items.length > 1) {
        html += '<details class="audio-history"><summary>历史配音（' + audio.items.length + '）</summary>';
        for (var h = 0; h < audio.items.length; h++) {
          var item = audio.items[h];
          var asset = item.asset || {};
          html += '<div class="audio-history-item">';
          html += '<span>' + escapeHtml(item.voice_label || item.voice_id || '配音') + ' · ' +
            Number(item.duration_s || asset.duration_s || 0).toFixed(2) + 's</span>';
          html += '<audio controls preload="none" src="' + escapeHtml(asset.file_url || '') + '"></audio>';
          html += '<button class="btn btn-secondary btn-sm" data-use-audio="' +
            escapeHtml(shot.id) + '|' + escapeHtml(asset.id || '') + '">使用</button>';
          html += '</div>';
        }
        html += '</details>';
      }
      html += '</div>';
    }
    html += '<div class="form-actions"><button class="btn btn-secondary" id="btn-batch-tts">为缺失配音的分镜批量生成</button></div>';
    html += '</div>';
    return html;
  }

  function renderAudioLibraryPanelHTML(role) {
    var label = role === 'music' ? '背景音乐' : '音效';
    var items = (state.audioAssets[role] || []).slice();
    var presets = (state.audioPresets[role] || []).slice();
    var html = '<div class="enhance-section card"><h3>' + label + '</h3>';
    html += '<div class="form-actions"><label class="btn btn-secondary btn-sm file-upload-label">上传' + label +
      '<input type="file" accept="audio/*" class="audio-upload-input" data-upload-role="' + role + '" /></label></div>';
    if (!items.length && !presets.length) {
      html += '<div class="empty-state compact"><p class="empty-desc">尚无已上传的' + label +
        '。系统预设音乐库为空（没有授权文件时不会伪造资源）。</p></div>';
    }
    var all = items.map(function (asset) { return { asset: asset, preset: false }; }).concat(
      presets.map(function (item) { return { asset: item.asset || item, preset: true }; })
    );
    for (var i = 0; i < all.length; i++) {
      var asset = all[i].asset || {};
      html += '<div class="audio-library-item" data-audio-id="' + escapeHtml(asset.id || '') + '">';
      html += '<div class="audio-library-info"><strong>' + escapeHtml(asset.name || '音频') + '</strong>';
      html += '<span class="field-hint">' + (asset.duration_s ? Number(asset.duration_s).toFixed(2) + 's' : '时长未知') +
        (all[i].preset ? ' · 系统预设' : '') + '</span></div>';
      html += '<audio controls preload="none" src="/api/assets/' + encodeURIComponent(asset.id || '') + '/file"></audio>';
      html += '<button class="btn btn-secondary btn-sm" data-add-audio="' + role + '|' +
        escapeHtml(asset.id || '') + '">添加到时间线</button>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderTimelineEditorHTML() {
    var html = '<div class="enhance-section card"><h3>多轨时间线</h3>';
    var saveLabel = state.timeline.saveState || (state.timeline.dirty ? '有未保存修改' : '已保存');
    html += '<div class="timeline-toolbar"><span class="meta-chip">版本 ' + (state.timeline.version || 0) + '</span>';
    html += '<span class="meta-chip">总时长 ' + Number(state.timeline.duration_s || 0).toFixed(2) + 's</span>';
    html += '<span class="timeline-save-state" id="timeline-save-state">' + escapeHtml(saveLabel) + '</span>';
    html += '<button class="btn btn-secondary btn-sm" id="btn-timeline-reload">重新加载</button>';
    html += '<button class="btn btn-secondary btn-sm" id="btn-timeline-sync">同步分镜视频</button>';
    html += '<button class="btn btn-primary btn-sm" id="btn-timeline-save">立即保存</button></div>';
    if (state.timeline.loading) {
      html += '<div class="empty-state compact"><p class="empty-desc">时间线加载中…</p></div></div>';
      return html;
    }
    if (!state.timeline.tracks.length) {
      html += '<div class="empty-state compact"><p class="empty-desc">还没有时间线。初始化会根据已保存视频的真实时长创建视频/配音/字幕轨，已编辑的时间线不会被覆盖。</p>';
      html += '<button class="btn btn-primary" id="btn-timeline-init">初始化时间线</button></div></div>';
      return html;
    }
    var total = Math.max(Number(state.timeline.duration_s) || 0, 1);
    var order = ['video', 'narration', 'music', 'sfx', 'subtitle'];
    var labels = { video: '视频轨', narration: '配音轨', music: '音乐轨', sfx: '音效轨', subtitle: '字幕轨' };
    for (var o = 0; o < order.length; o++) {
      var role = order[o];
      var trackEntry = null;
      for (var t = 0; t < state.timeline.tracks.length; t++) {
        var track = state.timeline.tracks[t].track || {};
        if ((track.role || track.track_type) === role) {
          trackEntry = state.timeline.tracks[t];
          break;
        }
      }
      html += '<div class="timeline-track" data-track="' + role + '">';
      html += '<div class="timeline-track-label">' + labels[role] + '</div>';
      html += '<div class="timeline-track-content">';
      var clips = trackEntry ? (trackEntry.clips || []) : [];
      for (var c = 0; c < clips.length; c++) {
        var clip = clips[c];
        var left = Math.min(100, Math.max(0, (Number(clip.start_time || 0) / total) * 100));
        var width = Math.min(100 - left, Math.max(0.5, (Number(clip.duration_s || 0) / total) * 100));
        var selectedClass = state.timeline.selectedClipId === clip.id ? ' selected' : '';
        var mutedClass = clip.muted ? ' muted' : '';
        var text = clip.subtitle_text || clip.name || role;
        html += '<div class="timeline-block ' + role + mutedClass + selectedClass +
          '" data-clip-id="' + escapeHtml(clip.id) + '" data-track-role="' + role +
          '" style="left:' + left.toFixed(3) + '%;width:' + width.toFixed(3) + '%;" title="' +
          escapeHtml(String(clip.start_time)) + 's / ' + escapeHtml(String(clip.duration_s)) + 's">';
        html += '<span class="block-label">' + escapeHtml(text) + '</span>';
        html += '<span class="block-time">' + Number(clip.start_time || 0).toFixed(2) + 's</span>';
        html += '</div>';
      }
      html += '</div></div>';
    }
    html += '<div class="timeline-inspector" id="timeline-inspector">' + renderTimelineInspectorHTML() + '</div>';
    if (state.timeline.warnings && state.timeline.warnings.length) {
      html += '<div class="warning-stack">';
      state.timeline.warnings.forEach(function (warning) {
        html += '<div class="warning-item">' + escapeHtml(warning) + '</div>';
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function findSelectedTimelineClip() {
    if (!state.timeline.selectedClipId) return null;
    for (var t = 0; t < state.timeline.tracks.length; t++) {
      var clips = state.timeline.tracks[t].clips || [];
      for (var c = 0; c < clips.length; c++) {
        if (clips[c].id === state.timeline.selectedClipId) {
          return { clip: clips[c], track: state.timeline.tracks[t] };
        }
      }
    }
    return null;
  }

  function renderTimelineInspectorHTML() {
    var found = findSelectedTimelineClip();
    if (!found) return '<p class="field-hint">点击时间线片段可编辑起点、时长、裁剪、音量、淡入淡出和字幕文本。</p>';
    var clip = found.clip;
    var role = (found.track.track || {}).role;
    var html = '<h4>片段属性</h4><div class="form-grid">';
    html += '<div class="form-group"><label>开始(s)</label><input type="number" id="clip-start" min="0" step="0.01" value="' + Number(clip.start_time || 0) + '" /></div>';
    html += '<div class="form-group"><label>时长(s)</label><input type="number" id="clip-duration" min="0.01" step="0.01" value="' + Number(clip.duration_s || 0) + '" /></div>';
    html += '<div class="form-group"><label>入点(s)</label><input type="number" id="clip-trim-in" min="0" step="0.01" value="' + Number(clip.trim_in || 0) + '" /></div>';
    html += '<div class="form-group"><label>音量</label><input type="number" id="clip-volume" min="0" max="2" step="0.05" value="' + Number(clip.volume == null ? 1 : clip.volume) + '" /></div>';
    html += '<div class="form-group"><label>淡入(s)</label><input type="number" id="clip-fade-in" min="0" step="0.05" value="' + Number(clip.fade_in || 0) + '" /></div>';
    html += '<div class="form-group"><label>淡出(s)</label><input type="number" id="clip-fade-out" min="0" step="0.05" value="' + Number(clip.fade_out || 0) + '" /></div>';
    if (role === 'subtitle') {
      html += '<div class="form-group" style="grid-column:1/-1"><label>字幕文本</label><textarea id="clip-subtitle" rows="2">' + escapeHtml(clip.subtitle_text || '') + '</textarea></div>';
    }
    if (role === 'video') {
      html += '<div class="form-group" style="grid-column:1/-1"><label class="batch-checkbox"><input type="checkbox" id="clip-source-audio"' +
        (clip.source_audio_enabled ? ' checked' : '') + ' /><span class="batch-label">保留该镜头的原视频声音</span></label></div>';
    }
    html += '</div><div class="form-actions">';
    html += '<button class="btn btn-primary btn-sm" id="btn-clip-apply">应用修改</button>';
    html += '<button class="btn btn-secondary btn-sm" id="btn-clip-mute">' + (clip.muted ? '取消静音' : '静音') + '</button>';
    html += '<button class="btn btn-secondary btn-sm" id="btn-clip-delete">删除片段</button>';
    html += '</div>';
    return html;
  }

  function bindModule4Events() {
    var panel = els.studioContentPanel;
    var voiceSelect = $('tts-voice-select');
    if (voiceSelect) {
      voiceSelect.addEventListener('change', function () {
        state.narrationForm.voiceId = voiceSelect.value;
        saveToLocalStorage();
      });
    }
    var rate = $('tts-rate');
    if (rate) {
      rate.addEventListener('input', function () {
        state.narrationForm.speechRate = parseFloat(rate.value);
        var label = $('tts-rate-label');
        if (label) label.textContent = state.narrationForm.speechRate.toFixed(1) + 'x';
        saveToLocalStorage();
      });
    }
    var volume = $('tts-volume');
    if (volume) {
      volume.addEventListener('input', function () {
        state.narrationForm.volume = parseFloat(volume.value);
        var label = $('tts-volume-label');
        if (label) label.textContent = state.narrationForm.volume.toFixed(1);
        saveToLocalStorage();
      });
    }
    Array.prototype.forEach.call(panel.querySelectorAll('[data-dialogue-shot]'), function (input) {
      input.addEventListener('change', function () {
        persistShotDialogue(input.getAttribute('data-dialogue-shot'), input.value);
      });
    });
    Array.prototype.forEach.call(panel.querySelectorAll('[data-tts-shot]'), function (button) {
      button.addEventListener('click', function () {
        handleGenerateShotTTS(button.getAttribute('data-tts-shot'));
      });
    });
    var batch = $('btn-batch-tts');
    if (batch) batch.addEventListener('click', handleBatchTTS);
    Array.prototype.forEach.call(panel.querySelectorAll('[data-audio-none]'), function (button) {
      button.addEventListener('click', function () {
        handleAudioSelection(button.getAttribute('data-audio-none'), null);
      });
    });
    Array.prototype.forEach.call(panel.querySelectorAll('[data-use-audio]'), function (button) {
      button.addEventListener('click', function () {
        var parts = String(button.getAttribute('data-use-audio')).split('|');
        handleAudioSelection(parts[0], parts[1]);
      });
    });
    Array.prototype.forEach.call(panel.querySelectorAll('.audio-upload-input'), function (input) {
      input.addEventListener('change', function () {
        if (input.files && input.files[0]) {
          handleAudioUpload(input.getAttribute('data-upload-role'), input.files[0]);
        }
      });
    });
    Array.prototype.forEach.call(panel.querySelectorAll('[data-add-audio]'), function (button) {
      button.addEventListener('click', function () {
        var parts = String(button.getAttribute('data-add-audio')).split('|');
        handleAddAudioClip(parts[0], parts[1]);
      });
    });
    var init = $('btn-timeline-init');
    if (init) init.addEventListener('click', handleInitializeTimeline);
    var reload = $('btn-timeline-reload');
    if (reload) reload.addEventListener('click', handleTimelineReload);
    var sync = $('btn-timeline-sync');
    if (sync) sync.addEventListener('click', handleTimelineSync);
    var save = $('btn-timeline-save');
    if (save) save.addEventListener('click', saveTimelineNow);
    Array.prototype.forEach.call(panel.querySelectorAll('[data-clip-id]'), function (block) {
      block.addEventListener('click', function (event) {
        if (state.timelineDragging) return;
        if (event.target.closest('button')) return;
        state.timeline.selectedClipId = block.getAttribute('data-clip-id');
        renderModule4();
      });
      block.addEventListener('pointerdown', function (event) {
        if (event.target.closest('button') || event.button !== 0) return;
        var found = null;
        for (var ti = 0; ti < state.timeline.tracks.length; ti++) {
          var clips = state.timeline.tracks[ti].clips || [];
          for (var ci = 0; ci < clips.length; ci++) {
            if (clips[ci].id === block.getAttribute('data-clip-id')) {
              found = clips[ci];
              break;
            }
          }
          if (found) break;
        }
        if (!found) return;
        var content = block.parentElement;
        var rect = content.getBoundingClientRect();
        var total = Math.max(Number(state.timeline.duration_s) || 0, 1);
        var startX = event.clientX;
        var originalStart = Number(found.start_time || 0);
        var maxStart = Math.max(0, total - Number(found.duration_s || 0));
        state.timelineDragging = true;
        block.classList.add('dragging');
        block.setPointerCapture(event.pointerId);
        function onMove(moveEvent) {
          if (!rect.width) return;
          var delta = ((moveEvent.clientX - startX) / rect.width) * total;
          var raw = Math.max(0, Math.min(maxStart, originalStart + delta));
          var snapped = Math.round(raw * 2) / 2;
          found.start_time = snapped;
          block.style.left = ((snapped / total) * 100).toFixed(3) + '%';
        }
        function onUp() {
          block.removeEventListener('pointermove', onMove);
          block.removeEventListener('pointerup', onUp);
          block.removeEventListener('pointercancel', onUp);
          block.classList.remove('dragging');
          state.timelineDragging = false;
          markTimelineDirty();
          saveTimelineNow();
        }
        block.addEventListener('pointermove', onMove);
        block.addEventListener('pointerup', onUp);
        block.addEventListener('pointercancel', onUp);
      });
    });
    var apply = $('btn-clip-apply');
    if (apply) apply.addEventListener('click', applyTimelineClipEdit);
    var mute = $('btn-clip-mute');
    if (mute) mute.addEventListener('click', toggleSelectedClipMute);
    var del = $('btn-clip-delete');
    if (del) del.addEventListener('click', deleteSelectedClip);
    var nextRefine = $('btn-module4-preview-refine');
    if (nextRefine) nextRefine.addEventListener('click', function () { flushTimelineSave(); switchStep(5); });
    var nextFinal = $('btn-module4-final');
    if (nextFinal) nextFinal.addEventListener('click', function () { flushTimelineSave(); switchStep(6); });
  }

  function persistShotDialogue(shotId, text) {
    return api('/api/creative/shots/' + encodeURIComponent(shotId), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dialogue: text })
    }).then(function (shot) {
      for (var i = 0; i < state.shots.length; i++) {
        if (state.shots[i].id === shotId) state.shots[i].dialogue = text;
      }
      return shot;
    }).catch(function (error) {
      showToast('旁白保存失败: ' + error.message, 'error');
      throw error;
    });
  }

  function handleGenerateShotTTS(shotId) {
    if (state.ttsInProgress) return;
    var shot = (state.shots || []).filter(function (item) { return item.id === shotId; })[0];
    if (!shot) return;
    var textarea = els.studioContentPanel.querySelector('[data-dialogue-shot="' + shotId + '"]');
    var text = textarea ? textarea.value.trim() : (shot.dialogue || '').trim();
    if (!text) {
      showToast('请先填写旁白文案', 'warning');
      return;
    }
    if (!state.narrationForm.voiceId) {
      showToast('没有可用的真实音色，请先安装并配置 Piper 音色', 'warning');
      return;
    }
    state.ttsInProgress = true;
    var projectId = state.projectId;
    persistShotDialogue(shotId, text).then(function () {
      return api('/api/creative/shots/' + encodeURIComponent(shotId) + '/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: 'piper',
          voice_id: state.narrationForm.voiceId,
          text: text,
          speech_rate: state.narrationForm.speechRate,
          volume: state.narrationForm.volume,
          client_request_id: 'tts-' + shotId + '-' + Date.now()
        })
      });
    }).then(function (task) {
      showToast('配音任务已创建', 'info');
      return pollTask(task.id, null, { projectId: projectId, treatCancelledAsError: true });
    }).then(function () {
      if (state.projectId !== projectId) return;
      state.shotAudioLoaded[shotId] = false;
      return loadShotAudio(shotId).then(function () {
        return reloadShotsAndHydrate();
      }).then(function () {
        if (!state.timeline.dirty) return loadTimeline(false);
      });
    }).then(function () {
      state.ttsInProgress = false;
      if (state.projectId === projectId) {
        if (state.activeStep === 4) renderModule4();
        showToast('配音已生成，时间线已同步', 'success');
      }
    }).catch(function (error) {
      state.ttsInProgress = false;
      if (error && error.name === 'AbortError') return;
      if (state.projectId === projectId && state.activeStep === 4) renderModule4();
      showToast('配音失败: ' + (error.message || '未知错误'), 'error');
    });
  }

  function handleBatchTTS() {
    if (state.ttsInProgress || !state.projectId) return;
    if (!state.narrationForm.voiceId) {
      showToast('没有可用的真实音色', 'warning');
      return;
    }
    var projectId = state.projectId;
    state.ttsInProgress = true;
    api('/api/creative/projects/' + encodeURIComponent(projectId) + '/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'missing',
        provider: 'piper',
        voice_id: state.narrationForm.voiceId,
        speech_rate: state.narrationForm.speechRate,
        volume: state.narrationForm.volume,
        client_request_id: 'tts-batch-' + Date.now()
      })
    }).then(function (task) {
      showToast('批量配音任务已创建', 'info');
      return pollTask(task.id, null, { projectId: projectId, treatCancelledAsError: true });
    }).then(function () {
      if (state.projectId !== projectId) return;
      state.shotAudio = {};
      state.shotAudioLoaded = {};
      return reloadShotsAndHydrate();
    }).then(function () {
      if (!state.timeline.dirty) return loadTimeline(false);
    }).then(function () {
      state.ttsInProgress = false;
      if (state.projectId === projectId) {
        if (state.activeStep === 4) renderModule4();
        showToast('批量配音已完成，时间线已同步', 'success');
      }
    }).catch(function (error) {
      state.ttsInProgress = false;
      if (error && error.name === 'AbortError') return;
      showToast('批量配音失败: ' + (error.message || '未知错误'), 'error');
    });
  }

  function handleAudioSelection(shotId, assetId) {
    var projectId = state.projectId;
    api('/api/creative/shots/' + encodeURIComponent(shotId) + '/audio/selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId || null })
    }).then(function () {
      state.shotAudioLoaded[shotId] = false;
      return loadShotAudio(shotId);
    }).then(function () {
      return reloadShotsAndHydrate();
    }).then(function () {
      if (!state.timeline.dirty) return loadTimeline(false);
    }).then(function () {
      if (state.projectId === projectId && state.activeStep === 4) renderModule4();
    }).catch(function (error) {
      showToast('配音选择失败: ' + error.message, 'error');
    });
  }

  function handleAudioUpload(role, file) {
    var form = new FormData();
    form.append('file', file);
    form.append('asset_type', 'audio');
    form.append('audio_role', role);
    form.append('name', file.name.replace(/\.[^.]+$/, ''));
    api('/api/assets/upload', { method: 'POST', body: form }).then(function () {
      showToast('音频已上传', 'success');
      return loadAudioLibrary();
    }).then(function () {
      if (state.activeStep === 4) renderModule4();
    }).catch(function (error) {
      showToast('音频上传失败: ' + error.message, 'error');
    });
  }

  function handleAddAudioClip(role, assetId) {
    if (!state.timeline.tracks.length) {
      showToast('请先初始化时间线', 'warning');
      return;
    }
    var asset = null;
    var pool = role === 'music' ? state.audioAssets.music.concat(state.audioPresets.music.map(function (item) { return item.asset || item; }))
      : state.audioAssets.sfx.concat(state.audioPresets.sfx.map(function (item) { return item.asset || item; }));
    for (var i = 0; i < pool.length; i++) {
      if (pool[i].id === assetId) { asset = pool[i]; break; }
    }
    if (!asset) return;
    var trackEntry = ensureTimelineTrack(role);
    var duration = Number(asset.duration_s) || Number(state.timeline.duration_s) || 3;
    var start = 0;
    var baseDuration = role === 'music'
      ? Math.max(Number(state.timeline.duration_s) || duration, 0.5)
      : duration;
    if (role === 'sfx') {
      start = Math.max(0, Number(state.timeline.duration_s || 0) * 0 - 0);
    }
    var clip = {
      id: 'local-' + role + '-' + Date.now(),
      shot_id: null,
      asset_id: asset.id,
      name: asset.name || role,
      start_time: start,
      duration_s: baseDuration,
      trim_in: 0,
      trim_out: Math.min(duration, baseDuration),
      volume: role === 'music' ? 0.3 : 1.0,
      muted: false,
      source_audio_enabled: true,
      fade_in: role === 'music' ? 0.5 : 0,
      fade_out: role === 'music' ? 0.5 : 0,
      subtitle_text: null,
      properties: role === 'music' && duration < baseDuration ? { loop: true } : {}
    };
    trackEntry.clips = trackEntry.clips || [];
    trackEntry.clips.push(clip);
    trackEntry.clips.sort(function (a, b) { return (a.start_time || 0) - (b.start_time || 0); });
    state.timeline.selectedClipId = clip.id;
    markTimelineDirty();
    renderModule4();
    showToast('已加入时间线，正在保存', 'info');
  }

  function findTimelineTrack(role) {
    for (var i = 0; i < state.timeline.tracks.length; i++) {
      var track = state.timeline.tracks[i].track || {};
      if ((track.role || track.track_type) === role) return state.timeline.tracks[i];
    }
    return null;
  }

  function ensureTimelineTrack(role) {
    var existing = findTimelineTrack(role);
    if (existing) return existing;
    var names = { video: '主视频轨', narration: '配音轨', music: '音乐轨', sfx: '音效轨', subtitle: '字幕轨' };
    var types = { video: 'video', narration: 'audio', music: 'audio', sfx: 'audio', subtitle: 'subtitle' };
    var entry = {
      track: {
        name: names[role] || role,
        track_type: types[role] || 'audio',
        role: role,
        sequence_no: state.timeline.tracks.length,
        settings: {}
      },
      clips: []
    };
    state.timeline.tracks.push(entry);
    return entry;
  }

  function syncNarrationClipForShot(shotId) {
    var shot = (state.shots || []).filter(function (item) { return item.id === shotId; })[0];
    if (!shot || !state.timeline.tracks.length) return Promise.resolve();
    var narration = ensureTimelineTrack('narration');
    if (!shot.audio_asset_id) {
      var kept = [];
      for (var r = 0; r < (narration.clips || []).length; r++) {
        if (narration.clips[r].shot_id !== shotId) kept.push(narration.clips[r]);
      }
      narration.clips = kept;
      markTimelineDirty();
      return saveTimelineNow();
    }
    var videoClip = null;
    var videoTrack = findTimelineTrack('video');
    if (videoTrack) {
      for (var i = 0; i < (videoTrack.clips || []).length; i++) {
        if (videoTrack.clips[i].shot_id === shotId) { videoClip = videoTrack.clips[i]; break; }
      }
    }
    var duration = Number(shot.audio_duration_s) || 1;
    var start = videoClip ? Number(videoClip.start_time || 0) : 0;
    var existing = null;
    for (var c = 0; c < (narration.clips || []).length; c++) {
      if (narration.clips[c].shot_id === shotId) { existing = narration.clips[c]; break; }
    }
    if (existing) {
      existing.asset_id = shot.audio_asset_id;
      existing.duration_s = duration;
      existing.trim_out = duration;
    } else {
      narration.clips = narration.clips || [];
      narration.clips.push({
        id: 'local-narration-' + shotId,
        shot_id: shotId,
        asset_id: shot.audio_asset_id,
        name: (shot.scene_title || '镜头') + ' 配音',
        start_time: start,
        duration_s: duration,
        trim_in: 0,
        trim_out: duration,
        volume: 1.0,
        muted: false,
        source_audio_enabled: true,
        fade_in: 0,
        fade_out: 0,
        subtitle_text: null,
        properties: {}
      });
      narration.clips.sort(function (a, b) { return (a.start_time || 0) - (b.start_time || 0); });
    }
    markTimelineDirty();
    return saveTimelineNow();
  }

  function handleInitializeTimeline() {
    loadTimeline(true).then(function (data) {
      if (data) {
        state.timeline.selectedClipId = null;
        renderModule4();
        showToast(data.initialized ? '时间线已初始化' : '已加载现有时间线', 'success');
      } else {
        showToast('时间线初始化失败', 'error');
      }
    });
  }

  function handleTimelineReload() {
    loadTimeline(false).then(function () {
      renderModule4();
      showToast('时间线已重新加载', 'info');
    });
  }

  function handleTimelineSync() {
    if (!state.projectId) return;
    var projectId = state.projectId;
    api('/api/creative/projects/' + encodeURIComponent(projectId) + '/timeline/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    }).then(function (data) {
      if (state.projectId !== projectId) return;
      state.timeline.tracks = data.tracks || [];
      state.timeline.version = data.timeline_version || 0;
      state.timeline.duration_s = data.duration_s || 0;
      state.timeline.dirty = false;
      state.timeline.saveState = '已保存';
      state.timeline.selectedClipId = null;
      renderModule4();
      showToast('分镜视频已同步到时间线，请重新合成', 'success');
    }).catch(function (error) {
      showToast('同步时间线失败: ' + error.message, 'error');
    });
  }

  function markTimelineDirty() {
    state.timeline.dirty = true;
    state.timelineRevision += 1;
    state.timeline.saveState = '有未保存修改';
    scheduleTimelineSave();
  }

  function scheduleTimelineSave() {
    if (state.timelineSaveTimer) clearTimeout(state.timelineSaveTimer);
    state.timelineSaveTimer = setTimeout(function () {
      saveTimelineNow();
    }, 800);
  }

  async function flushTimelineSave(options) {
    options = options || {};
    if (state.timelineSaveTimer) {
      clearTimeout(state.timelineSaveTimer);
      state.timelineSaveTimer = null;
    }
    if (state.timelineSaving && state.timelineSavePromise) {
      try { await state.timelineSavePromise; } catch (e) {}
    }
    if (state.timeline.dirty) {
      await saveTimelineNow({ keepalive: !!options.keepalive });
    }
  }

  function saveTimelineNow(options) {
    options = options || {};
    if (!state.projectId || state.timeline.loading) return Promise.resolve();
    if (state.timelineSaving) {
      state.timelineSaveQueued = true;
      return state.timelineSavePromise || Promise.resolve();
    }
    state.timelineSaving = true;
    state.timeline.saveState = '保存中…';
    var revision = state.timelineRevision;
    var saveState = $('timeline-save-state');
    if (saveState) saveState.textContent = '保存中…';
    var projectId = state.projectId;
    var promise = api('/api/creative/projects/' + encodeURIComponent(projectId) + '/timeline', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        timeline_version: state.timeline.version,
        tracks: state.timeline.tracks
      }),
      keepalive: !!options.keepalive
    }).then(function (data) {
      if (state.projectId !== projectId) return;
      state.timeline.version = data.timeline_version || state.timeline.version;
      if (revision === state.timelineRevision) {
        state.timeline.tracks = data.tracks || [];
        state.timeline.duration_s = data.duration_s || 0;
        state.timeline.dirty = false;
        state.timeline.saveState = '已保存';
        state.timeline.selectedClipId = null;
      } else {
        // Edits arrived while this save was in flight. Keep the local state
        // and save the newer revision with the server-issued version.
        state.timeline.dirty = true;
        state.timeline.saveState = '有未保存修改';
        state.timelineSaveQueued = true;
      }
      if (state.activeStep === 4) renderModule4();
    }).catch(function (error) {
      if (state.projectId !== projectId) return;
      if (error && error.status === 409) {
        state.timeline.saveState = '版本冲突';
        showToast('时间线已被其他窗口修改，正在重新加载', 'warning');
        loadTimeline(false).then(function () {
          if (state.activeStep === 4) renderModule4();
        });
      } else {
        state.timeline.saveState = '保存失败';
        state.timeline.dirty = true;
        showToast('时间线保存失败: ' + error.message, 'error');
        if (state.activeStep === 4) renderModule4();
      }
    }).finally(function () {
      state.timelineSaving = false;
      state.timelineSavePromise = null;
      if (state.timelineSaveQueued) {
        state.timelineSaveQueued = false;
        scheduleTimelineSave();
      }
    });
    state.timelineSavePromise = promise;
    return promise;
  }

  function applyTimelineClipEdit() {
    var found = findSelectedTimelineClip();
    if (!found) return;
    var clip = found.clip;
    var fields = {
      start_time: parseFloat(($('clip-start') || {}).value),
      duration_s: parseFloat(($('clip-duration') || {}).value),
      trim_in: parseFloat(($('clip-trim-in') || {}).value),
      volume: parseFloat(($('clip-volume') || {}).value),
      fade_in: parseFloat(($('clip-fade-in') || {}).value),
      fade_out: parseFloat(($('clip-fade-out') || {}).value)
    };
    for (var key in fields) {
      if (!isFinite(fields[key]) || fields[key] < 0) {
        showToast('片段参数必须是非负数字', 'warning');
        return;
      }
    }
    if (fields.duration_s <= 0) {
      showToast('片段时长必须大于 0', 'warning');
      return;
    }
    for (var k in fields) clip[k] = fields[k];
    clip.trim_out = fields.trim_in + fields.duration_s;
    var subtitle = $('clip-subtitle');
    if (subtitle) clip.subtitle_text = subtitle.value;
    var sourceAudio = $('clip-source-audio');
    if (sourceAudio) clip.source_audio_enabled = sourceAudio.checked;
    markTimelineDirty();
    saveTimelineNow();
  }

  function toggleSelectedClipMute() {
    var found = findSelectedTimelineClip();
    if (!found) return;
    found.clip.muted = !found.clip.muted;
    markTimelineDirty();
    saveTimelineNow();
  }

  function deleteSelectedClip() {
    var found = findSelectedTimelineClip();
    if (!found) return;
    var clips = found.track.clips || [];
    for (var i = 0; i < clips.length; i++) {
      if (clips[i].id === found.clip.id) {
        clips.splice(i, 1);
        break;
      }
    }
    state.timeline.selectedClipId = null;
    markTimelineDirty();
    saveTimelineNow();
  }

  // ---------------------------------------------------------------
  // MODULE 5: Human-AI Refinement
  // ---------------------------------------------------------------

  function renderModule5() {
    if (!state.projectId) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-state"><p class="empty-title">请先选择或创建项目</p></div></div>';
      return;
    }
    var candidates = (state.shots || []).filter(function (shot) {
      return shot.video_asset_id || shot.selected_video_asset_id;
    });
    var html = '<div class="module-header"><h2 class="module-title">单镜头试调（可选）</h2></div>';
    html += '<div class="warning-stack"><div class="warning-item">' +
      '此步骤可选。左侧播放真实原始/精修视频，右侧使用同源视频加 CSS 滤镜做快速预览；' +
      '实际导出由后端 FFmpeg 生成，CSS 预览不是已生成文件。' +
      '</div></div>';
    if (!candidates.length) {
      html += '<div class="module-empty"><div class="empty-state"><p class="empty-title">还没有可精修的视频</p>' +
        '<p class="empty-desc">请先在步骤 03 生成分镜视频。</p></div></div>';
      els.studioContentPanel.innerHTML = html;
      return;
    }

    var selectedShot = null;
    for (var s = 0; s < candidates.length; s++) {
      if (candidates[s].id === state.selectedVideoShotId) { selectedShot = candidates[s]; break; }
    }
    html += '<div class="shot-selector-bar">';
    for (var c = 0; c < candidates.length; c++) {
      var candidate = candidates[c];
      html += '<button class="selector-chip' + (selectedShot && candidate.id === selectedShot.id ? ' active' : '') +
        '" data-refine-shot="' + escapeHtml(candidate.id) + '">' +
        escapeHtml(candidate.scene_title || ('镜头 ' + candidate.sequence_no)) + '</button>';
    }
    html += '</div>';

    if (!selectedShot) {
      html += '<div class="empty-state compact"><p class="empty-desc">请选择一个分镜开始调试。没有选中分镜时不会自动猜测目标镜头。</p></div>';
      els.studioContentPanel.innerHTML = html;
      bindRefineShotSelector();
      return;
    }

    var versions = state.shotVideoVersions[selectedShot.id] || null;
    if (!versions && !state.shotVideoVersionsLoaded) state.shotVideoVersionsLoaded = {};
    if (!versions && !state.shotVideoVersionsLoaded[selectedShot.id]) {
      state.shotVideoVersionsLoaded[selectedShot.id] = true;
      loadShotVideos(selectedShot.id).then(function () {
        if (state.activeStep === 5) renderModule5();
      });
    }
    var items = versions && versions.items ? versions.items : [];
    var selectedAssetId = state.selectedVideoAssetId ||
      (versions && versions.selected_video_asset_id) ||
      selectedShot.selected_video_asset_id || selectedShot.video_asset_id;
    var selectedItem = null;
    for (var v = 0; v < items.length; v++) {
      if (items[v].asset && items[v].asset.id === selectedAssetId) { selectedItem = items[v]; break; }
    }
    if (!selectedItem && items.length) selectedItem = items[0];
    var videoUrl = selectedItem && selectedItem.asset ? selectedItem.asset.file_url :
      '/api/assets/' + encodeURIComponent(selectedAssetId) + '/file';

    html += '<div class="filter-preview-note field-hint">当前预览：' +
      escapeHtml(selectedItem ? (selectedItem.label || selectedItem.source) : '分镜视频') + '</div>';
    html += '<div class="comparison-layout">';
    html += '<div class="compare-panel"><h4>原始视频</h4>';
    html += '<video id="refine-original" class="refine-video" controls preload="metadata" src="' + escapeHtml(videoUrl) + '"></video>';
    html += '</div>';
    html += '<div class="compare-panel"><h4>CSS 快速预览 <span class="demo-badge">非导出文件</span></h4>';
    html += '<video id="refine-preview" class="refine-video" controls preload="metadata" src="' + escapeHtml(videoUrl) + '" style="filter:' + getFilterStyleString() + '"></video>';
    html += '</div></div>';

    html += '<div class="filter-controls card"><h4>真实 FFmpeg 滤镜</h4><div class="filter-grid">';
    html += '<div class="filter-item"><label>亮度: <span id="fp-brightness-val">' + state.filterParams.brightness + '</span>%</label><input type="range" class="filter-slider" data-param="brightness" min="0" max="200" value="' + state.filterParams.brightness + '" /></div>';
    html += '<div class="filter-item"><label>对比度: <span id="fp-contrast-val">' + state.filterParams.contrast + '</span>%</label><input type="range" class="filter-slider" data-param="contrast" min="0" max="200" value="' + state.filterParams.contrast + '" /></div>';
    html += '<div class="filter-item"><label>饱和度: <span id="fp-saturation-val">' + state.filterParams.saturation + '</span>%</label><input type="range" class="filter-slider" data-param="saturation" min="0" max="200" value="' + state.filterParams.saturation + '" /></div>';
    html += '<div class="filter-item"><label>色相: <span id="fp-hueRotate-val">' + state.filterParams.hueRotate + '</span>°</label><input type="range" class="filter-slider" data-param="hueRotate" min="-180" max="180" value="' + state.filterParams.hueRotate + '" /></div>';
    html += '<div class="filter-item"><label>模糊: <span id="fp-blur-val">' + state.filterParams.blur + '</span></label><input type="range" class="filter-slider" data-param="blur" min="0" max="10" step="0.5" value="' + state.filterParams.blur + '" /></div>';
    html += '<div class="filter-item"><label>锐化: <span id="fp-sharpen-val">' + state.filterParams.sharpen + '</span></label><input type="range" class="filter-slider" data-param="sharpen" min="0" max="5" step="0.1" value="' + state.filterParams.sharpen + '" /></div>';
    html += '<div class="filter-item"><label>曝光: <span id="fp-exposure-val">' + state.filterParams.exposure + '</span></label><input type="range" class="filter-slider" data-param="exposure" min="-2" max="2" step="0.1" value="' + state.filterParams.exposure + '" /></div>';
    html += '<div class="filter-item"><label>输出分辨率</label><select id="refine-scale"><option value="">保持原尺寸</option><option value="720p">1280×720</option><option value="1080p">1920×1080</option></select></div>';
    html += '<div class="filter-item"><label>帧率</label><select id="refine-fps"><option value="">保持原帧率</option><option value="24">24 FPS</option><option value="30">30 FPS</option></select></div>';
    html += '</div></div>';

    html += '<div class="ai-batch card"><h4>AI 增强（未接入）</h4>';
    html += '<p class="field-hint">当前版本只提供确定性 FFmpeg 调色，不接入视频扩散/超分模型；以下能力未接入，不会返回模拟成功。</p>';
    html += '<div class="ai-batch-grid">';
    ['模糊修复', '超分辨率', '细节增强', '帧扩展'].forEach(function (label) {
      html += '<label class="batch-checkbox disabled"><input type="checkbox" disabled /><span class="batch-label">' + label + '</span><span class="batch-desc">未接入</span></label>';
    });
    html += '</div></div>';

    html += '<div class="form-actions">';
    html += '<button class="btn btn-primary" id="btn-generate-refine"' + (state.refineInProgress ? ' disabled' : '') + '>' +
      (state.refineInProgress ? '精修任务运行中…' : '生成精修视频') + '</button>';
    html += '<button class="btn btn-secondary" id="btn-refine-use-original">恢复原始版用于成片</button>';
    if (selectedItem && selectedItem.is_refined) {
      html += '<button class="btn btn-secondary" id="btn-refine-use-current">使用当前精修版用于成片</button>';
    }
    html += '</div>';
    if (state.refineInProgress) {
      html += '<div class="progress-bar"><div class="progress-fill progress-animate"></div></div>';
    }

    html += '<div class="form-actions"><button class="btn btn-primary" id="btn-module5-final">进入最终成片与导出</button></div>';

    if (items.length) {
      html += '<div class="video-versions card"><h4>分镜视频版本</h4>';
      for (var vi = 0; vi < items.length; vi++) {
        var item = items[vi];
        var asset = item.asset || {};
        html += '<div class="video-version-item' + (item.is_selected ? ' selected' : '') + '">';
        html += '<span>' + escapeHtml(item.label || item.source || '视频') +
          (item.is_refined ? ' · 精修' : '') + (item.is_selected ? ' · 当前使用' : '') + '</span>';
        html += '<video controls preload="none" src="' + escapeHtml(asset.file_url || '') + '"></video>';
        html += '<a class="btn btn-secondary btn-sm" href="' + escapeHtml(asset.download_url || '#') + '">下载</a>';
        html += '<button class="btn btn-secondary btn-sm" data-preview-video="' + escapeHtml(asset.id || '') + '">预览</button>';
        html += '<button class="btn btn-primary btn-sm" data-select-video="' + escapeHtml(asset.id || '') + '">用于成片</button>';
        html += '</div>';
      }
      html += '</div>';
    }

    els.studioContentPanel.innerHTML = html;
    bindRefineShotSelector();
    bindFilterSliders();
    bindRefinePreviewSync();
    bindRefineActions();
    if (!state.shotVideoVersionsLoaded[selectedShot.id]) {
      state.shotVideoVersionsLoaded[selectedShot.id] = true;
      loadShotVideos(selectedShot.id).then(function () {
        if (state.activeStep === 5) renderModule5();
      });
    }
  }

  function bindRefineShotSelector() {
    Array.prototype.forEach.call(els.studioContentPanel.querySelectorAll('[data-refine-shot]'), function (button) {
      button.addEventListener('click', function () {
        state.selectedVideoShotId = button.getAttribute('data-refine-shot');
        state.selectedVideoAssetId = null;
        state.shotVideoVersionsLoaded = state.shotVideoVersionsLoaded || {};
        renderModule5();
      });
    });
  }

  function getFilterStyleString() {
    var fp = state.filterParams;
    var brightnessPct = Number(fp.brightness || 100) + Number(fp.exposure || 0) * 10;
    var parts = [];
    parts.push('brightness(' + brightnessPct + '%)');
    parts.push('contrast(' + Number(fp.contrast || 100) + '%)');
    parts.push('saturate(' + Number(fp.saturation || 100) + '%)');
    if (Number(fp.hueRotate || 0) !== 0) parts.push('hue-rotate(' + Number(fp.hueRotate) + 'deg)');
    if (Number(fp.blur || 0) > 0) parts.push('blur(' + Number(fp.blur) + 'px)');
    return parts.join(' ');
  }

  function bindFilterSliders() {
    Array.prototype.forEach.call(els.studioContentPanel.querySelectorAll('.filter-slider'), function (slider) {
      slider.addEventListener('input', function () {
        var param = slider.getAttribute('data-param');
        state.filterParams[param] = parseFloat(slider.value);
        var label = $('fp-' + param + '-val');
        if (label) {
          var suffix = param === 'hueRotate' ? '°' : (param === 'blur' || param === 'sharpen' || param === 'exposure') ? '' : '%';
          label.textContent = state.filterParams[param] + suffix;
        }
        var preview = $('refine-preview');
        if (preview) preview.style.filter = getFilterStyleString();
        saveToLocalStorage();
      });
    });
  }

  function bindRefinePreviewSync() {
    var original = $('refine-original');
    var preview = $('refine-preview');
    if (!original || !preview) return;
    var syncing = false;
    function sync(from, to, action) {
      if (syncing) return;
      syncing = true;
      if (action === 'play') {
        to.currentTime = from.currentTime;
        var promise = to.play();
        if (promise && promise.catch) promise.catch(function () {});
      } else if (action === 'pause') {
        to.pause();
        to.currentTime = from.currentTime;
      } else {
        if (Math.abs(to.currentTime - from.currentTime) > 0.3) to.currentTime = from.currentTime;
      }
      setTimeout(function () { syncing = false; }, 0);
    }
    original.addEventListener('play', function () { sync(original, preview, 'play'); });
    preview.addEventListener('play', function () { sync(preview, original, 'play'); });
    original.addEventListener('pause', function () { sync(original, preview, 'pause'); });
    preview.addEventListener('pause', function () { sync(preview, original, 'pause'); });
    original.addEventListener('seeked', function () { sync(original, preview, 'seek'); });
    preview.addEventListener('seeked', function () { sync(preview, original, 'seek'); });
  }

  function buildRefineFilters() {
    var fp = state.filterParams;
    var filters = {};
    if (Number(fp.brightness) !== 100) filters.brightness = (Number(fp.brightness) - 100) / 100;
    if (Number(fp.contrast) !== 100) filters.contrast = Number(fp.contrast) / 100;
    if (Number(fp.saturation) !== 100) filters.saturation = Number(fp.saturation) / 100;
    if (Number(fp.hueRotate || 0) !== 0) filters.hue = Number(fp.hueRotate);
    if (Number(fp.blur || 0) > 0) filters.blur = Number(fp.blur);
    if (Number(fp.sharpen || 0) > 0) filters.sharpen = Number(fp.sharpen);
    if (Number(fp.exposure || 0) !== 0) filters.exposure = Number(fp.exposure);
    var scale = $('refine-scale');
    if (scale && scale.value) {
      filters.scale = scale.value === '1080p' ? { width: 1920, height: 1080 } : { width: 1280, height: 720 };
    }
    var fps = $('refine-fps');
    if (fps && fps.value) filters.fps = parseInt(fps.value, 10);
    return filters;
  }

  function bindRefineActions() {
    var generate = $('btn-generate-refine');
    if (generate) generate.addEventListener('click', handleRefineGenerate);
    Array.prototype.forEach.call(els.studioContentPanel.querySelectorAll('[data-preview-video]'), function (button) {
      button.addEventListener('click', function () {
        state.selectedVideoAssetId = button.getAttribute('data-preview-video');
        renderModule5();
      });
    });
    Array.prototype.forEach.call(els.studioContentPanel.querySelectorAll('[data-select-video]'), function (button) {
      button.addEventListener('click', function () {
        handleVideoSelection(button.getAttribute('data-select-video'));
      });
    });
    var original = $('btn-refine-use-original');
    if (original) original.addEventListener('click', function () {
      var shot = (state.shots || []).filter(function (item) { return item.id === state.selectedVideoShotId; })[0];
      if (shot && shot.video_asset_id) handleVideoSelection(shot.video_asset_id);
    });
    var current = $('btn-refine-use-current');
    if (current) current.addEventListener('click', function () {
      if (state.selectedVideoAssetId) handleVideoSelection(state.selectedVideoAssetId);
    });
    var nextFinal = $('btn-module5-final');
    if (nextFinal) nextFinal.addEventListener('click', function () { switchStep(6); });
  }

  function handleRefineGenerate() {
    if (state.refineInProgress || !state.projectId || !state.selectedVideoShotId) {
      if (!state.selectedVideoShotId) showToast('请先选择一个分镜', 'warning');
      return;
    }
    var filters = buildRefineFilters();
    if (!Object.keys(filters).length) {
      showToast('请至少调整一个画面参数', 'warning');
      return;
    }
    var projectId = state.projectId;
    var shotId = state.selectedVideoShotId;
    var inputAssetId = state.selectedVideoAssetId;
    var versions = state.shotVideoVersions[shotId];
    if (!inputAssetId && versions) inputAssetId = versions.selected_video_asset_id;
    if (!inputAssetId) {
      var shot = (state.shots || []).filter(function (item) { return item.id === shotId; })[0];
      inputAssetId = shot && (shot.selected_video_asset_id || shot.video_asset_id);
    }
    if (!inputAssetId) {
      showToast('没有可精修的视频版本', 'warning');
      return;
    }
    state.refineInProgress = true;
    state.refineProgress = 0;
    renderModule5();
    api('/api/creative/projects/' + encodeURIComponent(projectId) + '/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        shot_id: shotId,
        input_asset_id: inputAssetId,
        filters: filters,
        client_request_id: 'refine-' + shotId + '-' + Date.now()
      })
    }).then(function (task) {
      return pollTask(task.id, function (progress) {
        state.refineProgress = progress || 0;
      }, { projectId: projectId, treatCancelledAsError: true });
    }).then(function () {
      if (state.projectId !== projectId) return;
      state.shotVideoVersionsLoaded[shotId] = false;
      return loadShotVideos(shotId).then(reloadShotsAndHydrate);
    }).then(function () {
      state.refineInProgress = false;
      if (state.projectId === projectId) {
        if (state.activeStep === 5) renderModule5();
        showToast('精修视频已生成，可在版本列表中选择用于成片', 'success');
      }
    }).catch(function (error) {
      state.refineInProgress = false;
      if (error && error.name === 'AbortError') return;
      if (state.projectId === projectId && state.activeStep === 5) renderModule5();
      showToast('精修失败: ' + (error.message || '未知错误'), 'error');
    });
  }

  function handleVideoSelection(assetId) {
    if (!state.selectedVideoShotId || !assetId) return;
    var projectId = state.projectId;
    var shotId = state.selectedVideoShotId;
    api('/api/creative/shots/' + encodeURIComponent(shotId) + '/video-selection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId })
    }).then(function (result) {
      state.selectedVideoAssetId = assetId;
      return Promise.all([
        loadShotVideos(shotId),
        reloadShotsAndHydrate(),
        result.timeline_updated && !state.timeline.dirty ? loadTimeline(false) : Promise.resolve()
      ]).then(function () {
        return result;
      });
    }).then(function (result) {
      if (state.projectId !== projectId) return;
      if (state.activeStep === 5) renderModule5();
      showToast(result.timeline_updated ? '视频版本已选择，时间线已更新，请重新合成' : '视频版本已选择', 'success');
    }).catch(function (error) {
      showToast('切换视频版本失败: ' + error.message, 'error');
    });
  }

  // ---------------------------------------------------------------
  // MODULE 6: Output Adaptation
  // ---------------------------------------------------------------

  function renderModule6() {
    if (!state.projectId) {
      els.studioContentPanel.innerHTML = '<div class="module-empty"><div class="empty-state"><p class="empty-title">请先选择或创建项目</p></div></div>';
      return;
    }
    var html = '<div class="module-header"><h2 class="module-title">最终成片与导出</h2></div>';
    html += '<div class="warning-stack"><div class="warning-item">' +
      '最终 MP4 由已保存的时间线真实合成，包含画面、配音、背景音乐、音效和可选字幕；' +
      '素材包 ZIP 同时保留分镜原片、音频、字幕和 manifest。' +
      '</div></div>';

    var timelineReady = state.timeline.tracks.some(function (item) {
      var track = item.track || {};
      return (track.role === 'video' || track.track_type === 'video') &&
        (item.clips || []).some(function (clip) { return !clip.muted; });
    });
    var final = state.finalVideo;
    var output = state.outputForm;

    html += '<div class="export-section card"><h4>导出参数</h4><div class="form-grid">';
    html += '<div class="form-group"><label>分辨率</label><select id="out-resolution"><option value="720p"' + (output.resolution === '720p' ? ' selected' : '') + '>720p（1280×720）</option><option value="1080p"' + (output.resolution === '1080p' ? ' selected' : '') + '>1080p（1920×1080）</option></select></div>';
    html += '<div class="form-group"><label>帧率</label><select id="out-fps"><option value="24"' + (Number(output.fps) === 24 ? ' selected' : '') + '>24 FPS</option><option value="25"' + (Number(output.fps) === 25 ? ' selected' : '') + '>25 FPS</option><option value="30"' + (Number(output.fps) === 30 ? ' selected' : '') + '>30 FPS</option></select></div>';
    html += '<div class="form-group"><label>字幕</label><select id="out-subtitle-mode">' +
      '<option value="none"' + (output.subtitleMode === 'none' ? ' selected' : '') + '>不封装字幕</option>' +
      '<option value="mov_text"' + (output.subtitleMode === 'mov_text' ? ' selected' : '') + '>封装 SRT 字幕轨</option>' +
      '<option value="burn"' + (output.subtitleMode === 'burn' ? ' selected' : '') + '>烧录字幕（依赖中文字体）</option>' +
      '</select></div>';
    html += '<div class="form-group"><label>画质 CRF</label><select id="out-crf">' +
      ['18', '20', '23', '26', '28'].map(function (value) {
        return '<option value="' + value + '"' + (String(output.crf) === value ? ' selected' : '') + '>CRF ' + value + '</option>';
      }).join('') + '</select></div>';
    html += '</div><div class="form-grid">';
    html += '<label class="batch-checkbox"><input type="checkbox" id="out-keep-source-audio"' + (output.keepSourceAudio ? ' checked' : '') + ' /><span class="batch-label">保留原视频声音</span></label>';
    html += '<label class="batch-checkbox"><input type="checkbox" id="out-music-ducking"' + (output.musicDucking ? ' checked' : '') + ' /><span class="batch-label">有旁白时自动降低音乐（sidechain）</span></label>';
    html += '<label class="batch-checkbox"><input type="checkbox" id="out-loudness-normalize"' + (output.loudnessNormalize ? ' checked' : '') + ' /><span class="batch-label">响度归一化</span></label>';
    html += '</div>';
    html += '<p class="field-hint">时间线版本 ' + (state.timeline.version || 0) + ' · 总时长 ' +
      Number(state.timeline.duration_s || 0).toFixed(2) + 's。修改时间线后需要重新合成。</p>';
    if (!timelineReady) {
      html += '<div class="warning-item">时间线还没有视频片段，暂时不能合成。请先在步骤 04 初始化并保存时间线。</div>';
    }
    html += '<div class="form-actions">';
    html += '<button class="btn btn-primary" id="btn-compose-final"' + (state.composeInProgress || !timelineReady ? ' disabled' : '') + '>' +
      (state.composeInProgress ? '正在合成…' : (final ? '重新合成最终视频' : '生成最终视频（MP4）')) + '</button>';
    html += '<button class="btn btn-secondary" id="btn-export-package"' + (state.exportInProgress ? ' disabled' : '') + '>' +
      (state.exportInProgress ? '正在打包…' : '导出项目素材包（ZIP）') + '</button>';
    html += '</div>';
    if (state.composeInProgress) {
      html += '<div class="progress-bar"><div class="progress-fill" style="width:' + Math.max(2, Number(state.composeProgress) || 0) + '%"></div></div>';
      html += '<p class="progress-label">' + escapeHtml(state.composeStage || '合成中…') + '</p>';
    }
    html += '</div>';

    html += '<div class="final-video card"><h4>最终成片</h4>';
    if (!final) {
      html += '<div class="empty-state compact"><p class="empty-desc">还没有最终成片。合成成功后，刷新或重新登录仍可在这里查看，不需要重新调用图片/视频 API。</p></div>';
    } else {
      var asset = final.asset || {};
      html += '<video class="final-video-player" controls preload="metadata" src="' + escapeHtml(asset.file_url || '') + '"></video>';
      html += '<div class="final-video-meta">';
      html += '<span class="meta-chip">时长 ' + Number(final.duration_s || 0).toFixed(2) + 's</span>';
      html += '<span class="meta-chip">' + escapeHtml(String(final.width || '—')) + '×' + escapeHtml(String(final.height || '—')) + '</span>';
      html += '<span class="meta-chip">' + escapeHtml(String(final.fps || '—')) + ' FPS</span>';
      html += '<span class="meta-chip">' + formatFileSize(final.file_size || 0) + '</span>';
      html += '<span class="meta-chip">时间线 v' + escapeHtml(String(final.timeline_version || 0)) + '</span>';
      if (!final.up_to_date) {
        html += '<span class="meta-chip chip-warning">时间线已修改，需重新合成</span>';
      }
      html += '</div>';
      html += '<div class="form-actions">';
      html += '<a class="btn btn-primary" href="' + escapeHtml(final.download_url || '#') + '">下载 MP4</a>';
      if (final.subtitle_asset_id) {
        html += '<a class="btn btn-secondary" href="/api/assets/' + encodeURIComponent(final.subtitle_asset_id) + '/download">下载字幕</a>';
      }
      if (state.exportDownloadUrl) {
        html += '<a class="btn btn-secondary" href="' + escapeHtml(state.exportDownloadUrl) + '">下载 ZIP 素材包</a>';
      }
      html += '</div>';
    }
    html += '</div>';

    html += '<div class="export-tree card"><h4>最近一次素材包</h4>';
    if (state.exportInProgress) {
      html += '<p class="field-hint">正在生成真实 ZIP 文件…</p>';
    } else if (state.exportDownloadUrl) {
      html += '<p class="field-hint">ZIP 已生成，包含 final/videos/audio/images/subtitles/manifest.json/project.json（只打包实际存在的文件）。</p>';
      html += '<a class="btn btn-primary" href="' + escapeHtml(state.exportDownloadUrl) + '">下载 ZIP 素材包</a>';
      if (state.exportArtifacts && state.exportArtifacts.length) {
        html += '<ul class="export-artifact-list">';
        state.exportArtifacts.forEach(function (artifact) {
          html += '<li>' + escapeHtml(artifact.name || '文件') + ' · ' + formatFileSize(artifact.file_size || 0) + '</li>';
        });
        html += '</ul>';
      }
    } else {
      html += '<p class="field-hint">尚未导出素材包。ZIP 与最终 MP4 是两个独立操作，可以同时保留。</p>';
    }
    html += '</div>';

    els.studioContentPanel.innerHTML = html;
    bindModule6Events();
  }

  function bindModule6Events() {
    ['out-resolution', 'out-fps', 'out-subtitle-mode', 'out-crf'].forEach(function (id) {
      var element = $(id);
      if (!element) return;
      element.addEventListener('change', function () {
        if (id === 'out-resolution') state.outputForm.resolution = element.value;
        if (id === 'out-fps') state.outputForm.fps = parseInt(element.value, 10);
        if (id === 'out-subtitle-mode') state.outputForm.subtitleMode = element.value;
        if (id === 'out-crf') state.outputForm.crf = parseInt(element.value, 10);
        saveToLocalStorage();
      });
    });
    var keep = $('out-keep-source-audio');
    if (keep) keep.addEventListener('change', function () {
      state.outputForm.keepSourceAudio = keep.checked;
      saveToLocalStorage();
    });
    var duck = $('out-music-ducking');
    if (duck) duck.addEventListener('change', function () {
      state.outputForm.musicDucking = duck.checked;
      saveToLocalStorage();
    });
    var loud = $('out-loudness-normalize');
    if (loud) loud.addEventListener('change', function () {
      state.outputForm.loudnessNormalize = loud.checked;
      saveToLocalStorage();
    });
    var compose = $('btn-compose-final');
    if (compose) compose.addEventListener('click', handleComposeFinalVideo);
    var exportBtn = $('btn-export-package');
    if (exportBtn) exportBtn.addEventListener('click', handleExportPackage);
  }

  async function handleComposeFinalVideo() {
    if (state.composeInProgress || !state.projectId) return;
    if (state.timeline.dirty) {
      await flushTimelineSave();
      if (state.timeline.dirty) {
        showToast('时间线尚未保存，无法开始合成', 'error');
        return;
      }
    }
    var output = state.outputForm;
    var projectId = state.projectId;
    state.composeInProgress = true;
    state.composeProgress = 1;
    state.composeStage = '提交合成任务…';
    renderModule6();
    api('/api/creative/projects/' + encodeURIComponent(projectId) + '/compose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolution: output.resolution,
        fps: Number(output.fps) || 30,
        crf: Number(output.crf) || 20,
        subtitle_mode: output.subtitleMode || 'none',
        keep_source_audio: !!output.keepSourceAudio,
        music_ducking: !!output.musicDucking,
        loudness_normalize: output.loudnessNormalize !== false,
        timeline_version: state.timeline.version,
        client_request_id: 'compose-' + projectId + '-' + Date.now()
      })
    }).then(function (task) {
      showToast('合成任务已创建', 'info');
      return pollTask(task.id, function (progress, stage) {
        state.composeProgress = progress || 0;
        state.composeStage = stage || '合成中…';
        if (state.activeStep === 6) {
          var fill = els.studioContentPanel.querySelector('.progress-fill');
          if (fill) fill.style.width = Math.max(2, Number(progress) || 0) + '%';
          var label = els.studioContentPanel.querySelector('.progress-label');
          if (label) label.textContent = state.composeStage;
        }
      }, { projectId: projectId, treatCancelledAsError: true, maxMs: 3 * 60 * 60 * 1000 });
    }).then(function () {
      if (state.projectId !== projectId) return;
      var loads = [loadWorkflow(projectId)];
      if (state.activeStep === 6 && !state.timeline.dirty) loads.push(loadTimeline(false));
      return Promise.all(loads);
    }).then(function () {
      state.composeInProgress = false;
      state.composeProgress = 100;
      if (state.projectId === projectId) {
        var workflow = state.workflow || {};
        state.finalVideo = workflow.final_video || null;
        if (state.activeStep === 6) renderModule6();
        showToast('最终视频已合成并保存', 'success');
      }
    }).catch(function (error) {
      state.composeInProgress = false;
      if (error && error.name === 'AbortError') return;
      if (state.projectId === projectId && state.activeStep === 6) renderModule6();
      showToast('合成失败: ' + (error.message || '未知错误'), 'error');
    });
  }

  function handleExportPackage() {
    if (state.exportInProgress || !state.projectId) return;
    var projectId = state.projectId;
    state.exportInProgress = true;
    renderModule6();
    api('/api/creative/projects/' + encodeURIComponent(projectId) + '/exports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_request_id: 'export-' + projectId + '-' + Date.now() })
    }).then(function (task) {
      return pollTask(task.id, null, { projectId: projectId, treatCancelledAsError: true }).then(function () {
        return api('/api/creative/tasks/' + encodeURIComponent(task.id));
      }).then(function (detail) {
        state.exportArtifacts = (detail && detail.artifacts) || [];
        state.exportDownloadUrl = '/api/creative/tasks/' + encodeURIComponent(task.id) + '/export/download';
      });
    }).then(function () {
      state.exportInProgress = false;
      if (state.projectId === projectId) {
        if (state.activeStep === 6) renderModule6();
        showToast('素材包 ZIP 已生成', 'success');
      }
    }).catch(function (error) {
      state.exportInProgress = false;
      if (error && error.name === 'AbortError') return;
      if (state.projectId === projectId && state.activeStep === 6) renderModule6();
      showToast('导出失败: ' + (error.message || '未知错误'), 'error');
    });
  }

  function formatFileSize(bytes) {
    bytes = Number(bytes) || 0;
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + 'MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + 'GB';
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
