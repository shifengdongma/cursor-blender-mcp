/**
 * AIGV Studio Asset Library Frontend
 * Vanilla JS implementation for asset management
 */

(function() {
  'use strict';

  // State
  var currentTab = 'models';
  var currentPage = 1;
  var totalPages = 1;
  var pageSize = 12;
  var searchQuery = '';
  var venueFilter = '';
  var assetDatePreset = 'all';
  var assetDateFrom = '';
  var assetDateTo = '';
  var assetSort = 'newest';
  var historyType = '';
  var historyStatus = '';
  var historyDatePreset = 'all';
  var historyDateFrom = '';
  var historyDateTo = '';
  var historySort = 'newest';
  var historyTaskMap = {};
  var currentAssetsById = {};

  // Monotonic request sequence: only the latest request may render.
  var loadSeq = 0;

  // 3D preview state
  var AUTO_PREVIEW_MAX_BYTES = 8 * 1024 * 1024;
  var PREVIEW_LOAD_TIMEOUT_MS = 90000;
  var loadedPreviewAssetIds = {};
  var previewObserver = null;
  var previewLoadTimers = {};

  // Extension -> asset type whitelist (mirrors backend/asset_service.py)
  var ALLOWED_EXTENSIONS = {
    'glb': 'glb', 'gltf': 'glb', 'obj': 'glb', 'fbx': 'glb', 'stl': 'glb',
    'blend': 'glb', 'dae': 'glb', '3ds': 'glb', 'ply': 'glb',
    'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image',
    'gif': 'image', 'svg': 'image', 'bmp': 'image', 'tiff': 'image',
    'tif': 'image', 'ico': 'image', 'heic': 'image', 'avif': 'image',
    'mp4': 'video', 'mov': 'video', 'avi': 'video', 'webm': 'video',
    'mkv': 'video', 'flv': 'video', 'm4v': 'video', 'mpeg': 'video',
    'mpg': 'video', 'wmv': 'video',
    'mp3': 'audio', 'wav': 'audio', 'ogg': 'audio', 'flac': 'audio',
    'aac': 'audio', 'm4a': 'audio', 'wma': 'audio', 'opus': 'audio',
    'pdf': 'document', 'doc': 'document', 'docx': 'document', 'xls': 'document',
    'xlsx': 'document', 'ppt': 'document', 'pptx': 'document', 'txt': 'document',
    'md': 'document', 'csv': 'document', 'rtf': 'document', 'odt': 'document',
    'json': 'document', 'xml': 'document', 'yaml': 'document', 'yml': 'document',
    'zip': 'archive', 'rar': 'archive', '7z': 'archive', 'tar': 'archive',
    'gz': 'archive', 'bz2': 'archive', 'xz': 'archive'
  };

  // Toast notification system
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

  // DOM Elements
  var assetGrid = document.getElementById('asset-grid');
  var pagination = document.getElementById('pagination');
  var searchInput = document.getElementById('search-input');
  var venueFilterSelect = document.getElementById('venue-filter');
  var uploadBtn = document.getElementById('upload-btn');
  var uploadModal = document.getElementById('upload-modal');
  var modalClose = document.getElementById('modal-close');
  var cancelUpload = document.getElementById('cancel-upload');
  var uploadForm = document.getElementById('upload-form');
  var uploadZone = document.getElementById('upload-zone');
  var fileInput = document.getElementById('file-input');
  var uploadFileMeta = document.getElementById('upload-file-meta');
  var historyFilterBar = document.getElementById('history-filter-bar');
  var historyTypeFilter = document.getElementById('history-type-filter');
  var historyStatusFilter = document.getElementById('history-status-filter');
  var historyDatePresetSelect = document.getElementById('history-date-preset');
  var historyDateFromInput = document.getElementById('history-date-from');
  var historyDateToInput = document.getElementById('history-date-to');
  var historySortSelect = document.getElementById('history-sort');
  var historyRefreshBtn = document.getElementById('history-refresh');
  var assetFilterControls = document.getElementById('asset-filter-controls');
  var assetDatePresetSelect = document.getElementById('asset-date-preset');
  var assetDateRange = document.getElementById('asset-date-range');
  var assetDateFromInput = document.getElementById('asset-date-from');
  var assetDateToInput = document.getElementById('asset-date-to');
  var assetSortSelect = document.getElementById('asset-sort');
  var clearFiltersBtn = document.getElementById('clear-filters');
  var searchBox = document.querySelector('.toolbar-search');
  var editAssetModal = document.getElementById('edit-asset-modal');
  var editAssetForm = document.getElementById('edit-asset-form');
  var editAssetIdInput = document.getElementById('edit-asset-id');
  var editAssetNameInput = document.getElementById('edit-asset-name');
  var editAssetVenueSelect = document.getElementById('edit-asset-venue');
  var editAssetDescInput = document.getElementById('edit-asset-desc');
  var editAssetVisibilitySelect = document.getElementById('edit-asset-visibility');
  var editAssetTypeLabel = document.getElementById('edit-asset-type');
  var editAssetSizeLabel = document.getElementById('edit-asset-size');
  var editAssetCloseBtn = document.getElementById('edit-asset-close');
  var editAssetCancelBtn = document.getElementById('edit-asset-cancel');
  var editAssetSaveBtn = document.getElementById('edit-asset-save');

  // Tab buttons
  var tabBtns = document.querySelectorAll('.tab-btn');

  // Initialize
  document.addEventListener('DOMContentLoaded', init);

  function init() {
    // Tab navigation
    tabBtns.forEach(function(btn) {
      btn.addEventListener('click', function() {
        var tab = this.dataset.tab;
        switchTab(tab);
      });
    });

    // Search with debounce
    if (searchInput) {
      var searchTimeout;
      searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(function() {
          searchQuery = searchInput.value.trim();
          if (currentTab === 'history') return;
          currentPage = 1;
          requestAssets();
        }, 300);
      });
    }

    // Venue filter
    if (venueFilterSelect) {
      venueFilterSelect.addEventListener('change', function() {
        venueFilter = this.value;
        currentPage = 1;
        requestAssets();
      });
    }

    // Asset date / sort filters
    if (assetDatePresetSelect) {
      assetDatePresetSelect.addEventListener('change', function() {
        applyAssetDatePreset(this.value);
        currentPage = 1;
        requestAssets();
      });
    }
    if (assetDateFromInput) {
      assetDateFromInput.addEventListener('change', function() {
        assetDateFrom = this.value;
        if (!validateAssetDateRange()) return;
        currentPage = 1;
        requestAssets();
      });
    }
    if (assetDateToInput) {
      assetDateToInput.addEventListener('change', function() {
        assetDateTo = this.value;
        if (!validateAssetDateRange()) return;
        currentPage = 1;
        requestAssets();
      });
    }
    if (assetSortSelect) {
      assetSortSelect.addEventListener('change', function() {
        assetSort = this.value || 'newest';
        currentPage = 1;
        requestAssets();
      });
    }
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', resetAssetFilters);
    }

    // Generation history filters
    if (historyTypeFilter) {
      historyTypeFilter.addEventListener('change', function() {
        historyType = this.value;
        currentPage = 1;
        requestAssets();
      });
    }
    if (historyStatusFilter) {
      historyStatusFilter.addEventListener('change', function() {
        historyStatus = this.value;
        currentPage = 1;
        requestAssets();
      });
    }
    if (historyDatePresetSelect) {
      historyDatePresetSelect.addEventListener('change', function() {
        applyHistoryDatePreset(this.value);
        currentPage = 1;
        requestAssets();
      });
    }
    if (historyDateFromInput) {
      historyDateFromInput.addEventListener('change', function() {
        historyDateFrom = this.value;
        markHistoryPresetCustom();
        if (!validateHistoryDateRange()) return;
        currentPage = 1;
        requestAssets();
      });
    }
    if (historyDateToInput) {
      historyDateToInput.addEventListener('change', function() {
        historyDateTo = this.value;
        markHistoryPresetCustom();
        if (!validateHistoryDateRange()) return;
        currentPage = 1;
        requestAssets();
      });
    }
    if (historySortSelect) {
      historySortSelect.addEventListener('change', function() {
        historySort = this.value || 'newest';
        currentPage = 1;
        requestAssets();
      });
    }
    if (historyRefreshBtn) {
      historyRefreshBtn.addEventListener('click', function() {
        currentPage = 1;
        requestAssets();
      });
    }

    // Upload modal
    if (uploadBtn) {
      uploadBtn.addEventListener('click', function() {
        openModal();
      });
    }

    if (modalClose) {
      modalClose.addEventListener('click', closeModal);
    }

    if (cancelUpload) {
      cancelUpload.addEventListener('click', closeModal);
    }

    // Close modal on overlay click
    if (uploadModal) {
      uploadModal.addEventListener('click', function(e) {
        if (e.target === uploadModal) {
          closeModal();
        }
      });
    }

    // Edit asset modal
    if (editAssetCloseBtn) {
      editAssetCloseBtn.addEventListener('click', closeEditAssetModal);
    }
    if (editAssetCancelBtn) {
      editAssetCancelBtn.addEventListener('click', closeEditAssetModal);
    }
    if (editAssetModal) {
      editAssetModal.addEventListener('click', function(e) {
        if (e.target === editAssetModal) {
          closeEditAssetModal();
        }
      });
    }
    if (editAssetForm) {
      editAssetForm.addEventListener('submit', handleEditAssetSave);
    }

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
      if (e.key !== 'Escape') return;
      if (editAssetModal && editAssetModal.classList.contains('active')) {
        closeEditAssetModal();
        return;
      }
      if (uploadModal && uploadModal.classList.contains('active')) {
        closeModal();
      }
    });

    // File upload with drag and drop
    if (uploadZone) {
      uploadZone.addEventListener('click', function() {
        fileInput.click();
      });

      uploadZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadZone.classList.add('dragover');
      });

      uploadZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
      });

      uploadZone.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
          fileInput.files = e.dataTransfer.files;
          updateFileName();
        }
      });
    }

    if (fileInput) {
      fileInput.addEventListener('change', updateFileName);
    }

    // Upload form
    if (uploadForm) {
      uploadForm.addEventListener('submit', handleUpload);
    }

    // Scroll to top button
    initScrollToTop();

    // Initial load (supports /assets?tab=history links from the profile page)
    var initialTab = new URLSearchParams(window.location.search).get('tab');
    if (initialTab && document.querySelector('.tab-btn[data-tab="' + initialTab + '"]')) {
      switchTab(initialTab);
    } else {
      requestAssets();
    }
    loadSummary();
  }

  function initScrollToTop() {
    var scrollBtn = document.createElement('button');
    scrollBtn.className = 'scroll-indicator';
    scrollBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>';
    scrollBtn.onclick = function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    document.body.appendChild(scrollBtn);

    window.addEventListener('scroll', function() {
      if (window.scrollY > 300) {
        scrollBtn.classList.add('visible');
      } else {
        scrollBtn.classList.remove('visible');
      }
    });
  }

  function switchTab(tab) {
    currentTab = tab;
    currentPage = 1;

    // Update tab buttons with animation
    tabBtns.forEach(function(btn) {
      var isActive = btn.dataset.tab === tab;
      btn.classList.toggle('active', isActive);

      if (isActive) {
        btn.style.transform = 'scale(1.05)';
        setTimeout(function() {
          btn.style.transform = '';
        }, 150);
      }
    });

    // Venue filter applies to all/models/images only.
    if (venueFilterSelect) {
      var showVenueFilter = (tab === 'all' || tab === 'models' || tab === 'images');
      venueFilterSelect.style.display = showVenueFilter ? 'block' : 'none';
      if (!showVenueFilter) {
        venueFilter = '';
        venueFilterSelect.value = '';
      }
    }
    if (historyFilterBar) {
      historyFilterBar.hidden = tab !== 'history';
    }
    if (searchBox) {
      searchBox.style.display = tab === 'history' ? 'none' : '';
    }
    updateAssetFilterVisibility();

    // Load immediately: request sequence invalidates any in-flight response.
    requestAssets();
  }

  function isAssetTab(tab) {
    return tab !== 'prompts' && tab !== 'history';
  }

  function updateAssetFilterVisibility() {
    var showAssetFilters = isAssetTab(currentTab);
    if (assetFilterControls) {
      assetFilterControls.style.display = showAssetFilters ? '' : 'none';
    }
    if (assetDateRange) {
      assetDateRange.hidden = !showAssetFilters || assetDatePreset !== 'custom';
    }
  }

  function getAssetTypeForTab() {
    switch (currentTab) {
      case 'models':
        return 'glb';
      case 'images':
        return 'image';
      case 'videos':
        return 'video';
      case 'audio':
        return 'audio';
      case 'documents':
        return 'document';
      case 'archives':
        return 'archive';
      case 'all':
        return '';
      case 'prompts':
        return 'prompt_doc';
      default:
        return '';
    }
  }

  function getResponseData(payload) {
    if (payload && payload.success === false) {
      throw new Error(payload.message || payload.error || '请求失败');
    }
    if (payload && typeof payload === 'object' && payload.data !== undefined) {
      return payload.data;
    }
    return payload;
  }

  function pad2(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function formatLocalDate(date) {
    return date.getFullYear() + '-' + pad2(date.getMonth() + 1) + '-' + pad2(date.getDate());
  }

  // Quick presets are inclusive local-date windows.
  function computePresetRange(preset) {
    if (preset === 'all') {
      return { from: '', to: '' };
    }
    if (preset === 'custom') {
      return null;
    }
    var today = new Date();
    var from = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (preset === '7d') {
      from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6);
    } else if (preset === '30d') {
      from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29);
    }
    return { from: formatLocalDate(from), to: formatLocalDate(today) };
  }

  function applyAssetDatePreset(preset) {
    assetDatePreset = preset || 'all';
    var range = computePresetRange(assetDatePreset);
    if (range) {
      assetDateFrom = range.from;
      assetDateTo = range.to;
    }
    if (assetDateFromInput) assetDateFromInput.value = assetDateFrom;
    if (assetDateToInput) assetDateToInput.value = assetDateTo;
    if (assetDateRange) {
      assetDateRange.hidden = !isAssetTab(currentTab) || assetDatePreset !== 'custom';
    }
  }

  function isDateRangeValid(from, to) {
    return !(from && to && from > to);
  }

  function resetAssetDateControls() {
    assetDatePreset = 'all';
    if (assetDatePresetSelect) assetDatePresetSelect.value = 'all';
    assetDateFrom = '';
    assetDateTo = '';
    if (assetDateFromInput) assetDateFromInput.value = '';
    if (assetDateToInput) assetDateToInput.value = '';
    if (assetDateRange) assetDateRange.hidden = true;
  }

  // An inverted range must never block a request: reset it to 全部时间,
  // notify once, and let the request proceed with matching content.
  function sanitizeAssetDateRange() {
    resetAssetDateControls();
    showToast('开始日期不能晚于结束日期', 'warning');
  }

  function resetHistoryDateControls() {
    historyDatePreset = 'all';
    if (historyDatePresetSelect) historyDatePresetSelect.value = 'all';
    historyDateFrom = '';
    historyDateTo = '';
    if (historyDateFromInput) historyDateFromInput.value = '';
    if (historyDateToInput) historyDateToInput.value = '';
  }

  function sanitizeHistoryDateRange() {
    resetHistoryDateControls();
    showToast('开始日期不能晚于结束日期', 'warning');
  }

  function validateAssetDateRange() {
    if (!isDateRangeValid(assetDateFrom, assetDateTo)) {
      showToast('开始日期不能晚于结束日期', 'warning');
      return false;
    }
    return true;
  }

  function markHistoryPresetCustom() {
    historyDatePreset = 'custom';
    if (historyDatePresetSelect) historyDatePresetSelect.value = 'custom';
  }

  function applyHistoryDatePreset(preset) {
    historyDatePreset = preset || 'all';
    if (historyDatePreset === 'custom') return;
    var range = computePresetRange(historyDatePreset);
    historyDateFrom = range.from;
    historyDateTo = range.to;
    if (historyDateFromInput) historyDateFromInput.value = historyDateFrom;
    if (historyDateToInput) historyDateToInput.value = historyDateTo;
  }

  function validateHistoryDateRange() {
    if (!isDateRangeValid(historyDateFrom, historyDateTo)) {
      showToast('开始日期不能晚于结束日期', 'warning');
      return false;
    }
    return true;
  }

  function hasActiveAssetFilters() {
    return Boolean(searchQuery) || Boolean(venueFilter) ||
      Boolean(assetDateFrom) || Boolean(assetDateTo) || assetSort !== 'newest';
  }

  function resetAssetFilters() {
    searchQuery = '';
    if (searchInput) searchInput.value = '';
    venueFilter = '';
    if (venueFilterSelect) venueFilterSelect.value = '';
    resetAssetDateControls();
    assetSort = 'newest';
    if (assetSortSelect) assetSortSelect.value = 'newest';
    currentPage = 1;
    requestAssets();
  }

  function requestAssets() {
    if (currentTab === 'history') {
      loadGenerationHistory();
      return;
    }
    if (!assetGrid) return;

    // An inverted range must not block tab switches or filter changes; reset
    // it to 全部时间 and continue so the rendered content always matches the tab.
    if (isAssetTab(currentTab) && !isDateRangeValid(assetDateFrom, assetDateTo)) {
      sanitizeAssetDateRange();
    }

    var seq = ++loadSeq;
    var tab = currentTab;
    resetPreviewState();

    // Skeleton is owned by the newest request only; older responses are dropped.
    assetGrid.innerHTML = renderSkeletons();
    assetGrid.style.opacity = '1';

    var endpoint = tab === 'prompts' ? '/api/prompts/documents' : '/api/assets';
    var params = new URLSearchParams();
    params.append('limit', pageSize);
    params.append('offset', (currentPage - 1) * pageSize);

    if (tab !== 'prompts') {
      var assetType = getAssetTypeForTab();
      if (assetType) {
        params.append('asset_type', assetType);
      }
      if (venueFilter) {
        params.append('venue_type', venueFilter);
      }
      if (searchQuery) {
        params.append('q', searchQuery);
      }
      if (assetDateFrom) {
        params.append('created_after', assetDateFrom);
      }
      if (assetDateTo) {
        params.append('created_before', assetDateTo);
      }
      params.append('sort', assetSort || 'newest');
    }

    window.AIGV.api(endpoint + '?' + params.toString())
      .then(function(responseData) {
        if (seq !== loadSeq) return;
        responseData = responseData || {};
        var items = responseData.items || [];
        var filteredItems = tab === 'prompts' ? filterItems(items) : items;
        if (tab === 'prompts') {
          renderPromptDocuments(filteredItems);
        } else {
          renderAssets(filteredItems);
        }
        var totalItems = typeof responseData.total === 'number' ? responseData.total : items.length;
        totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
        if (currentPage > totalPages) {
          currentPage = totalPages;
        }
        renderPagination();
      })
      .catch(function(error) {
        if (seq !== loadSeq) return;
        console.error('Error loading assets:', error);
        assetGrid.innerHTML = '<div class="empty-state-container"><p class="empty-desc">加载失败，请重试</p></div>';
        showToast(error && error.message ? error.message : '加载失败，请检查网络连接', 'error');
      });
  }

  function loadGenerationHistory() {
    if (!assetGrid) return;
    if (!isDateRangeValid(historyDateFrom, historyDateTo)) {
      sanitizeHistoryDateRange();
    }

    var seq = ++loadSeq;
    resetPreviewState();
    assetGrid.innerHTML = renderSkeletons();
    assetGrid.style.opacity = '1';

    var params = new URLSearchParams();
    params.append('limit', pageSize);
    params.append('offset', (currentPage - 1) * pageSize);
    if (historyType) params.append('task_type', historyType);
    if (historyStatus) params.append('status', historyStatus);
    if (historyDateFrom) params.append('date_from', historyDateFrom);
    if (historyDateTo) params.append('date_to', historyDateTo);
    params.append('sort', historySort || 'newest');

    window.AIGV.api('/api/generation/tasks?' + params.toString())
      .then(function(responseData) {
        if (seq !== loadSeq) return;
        responseData = responseData || {};
        var items = responseData.items || [];
        var totalItems = typeof responseData.total === 'number' ? responseData.total : items.length;
        totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
        if (currentPage > totalPages) {
          currentPage = totalPages;
          loadGenerationHistory();
          return;
        }
        renderGenerationTasks(items);
        renderPagination();
      })
      .catch(function(error) {
        if (seq !== loadSeq) return;
        console.error('Error loading generation history:', error);
        assetGrid.innerHTML =
          '<div class="empty-state-container"><h3 class="empty-title">生成历史加载失败</h3>' +
          '<p class="empty-desc">' + escapeHtml((error && error.message) || '请稍后重试') + '</p>' +
          '<button type="button" class="btn-outline" onclick="document.getElementById(\'history-refresh\').click()">重试</button></div>';
        showToast((error && error.message) || '生成历史加载失败', 'error');
      });
  }

  function loadSummary() {
    window.AIGV.api('/api/assets/summary').then(function(summary) {
      var nodes = document.querySelectorAll('#stats-row .stat-number');
      if (nodes.length >= 3) {
        nodes[0].textContent = summary.models || 0;
        nodes[1].textContent = summary.prompt_documents || 0;
        nodes[2].textContent = summary.venue_presets || 0;
      }
    }).catch(function() {
      var nodes = document.querySelectorAll('#stats-row .stat-number');
      for (var i = 0; i < nodes.length; i += 1) nodes[i].textContent = '—';
    });
  }

  function getSearchableText(item) {
    return [
      item && item.name,
      item && item.title,
      item && item.description,
      item && item.content,
      item && item.keywords,
      item && getVenueLabel(item.venue_type),
      item && getCategoryLabel(item.category)
    ].join(' ').toLowerCase();
  }

  function filterItems(items) {
    var keyword = (searchQuery || '').toLowerCase();
    if (!keyword) return items;
    return (items || []).filter(function(item) {
      return getSearchableText(item).indexOf(keyword) !== -1;
    });
  }

  function renderSkeletons() {
    var count = 6;
    var html = '';
    for (var i = 0; i < count; i++) {
      html += '\
        <div class="library-asset-card skeleton-wrapper">\
          <div class="asset-preview skeleton skeleton-image"></div>\
          <div class="asset-info">\
            <div class="skeleton skeleton-title"></div>\
            <div class="skeleton skeleton-text"></div>\
            <div class="skeleton skeleton-text" style="width: 80%;"></div>\
          </div>\
        </div>';
    }
    return html;
  }

  function cacheAssetsById(assets) {
    currentAssetsById = {};
    (assets || []).forEach(function(asset) {
      if (asset && asset.id) {
        currentAssetsById[asset.id] = asset;
      }
    });
  }

  function renderAssets(assets) {
    resetPreviewState();
    cacheAssetsById(assets);
    if (!assets.length) {
      if (hasActiveAssetFilters()) {
        assetGrid.innerHTML =
          '<div class="empty-state-container">' +
          '<svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">' +
          '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>' +
          '<h3 class="empty-title">没有符合条件的素材</h3>' +
          '<p class="empty-desc">尝试调整关键词、场馆、时间范围或排序。</p>' +
          '<button type="button" class="btn-outline" id="empty-clear-filters">清除筛选</button>' +
          '</div>';
        var emptyClearBtn = assetGrid.querySelector('#empty-clear-filters');
        if (emptyClearBtn) {
          emptyClearBtn.addEventListener('click', resetAssetFilters);
        }
      } else {
        assetGrid.innerHTML = '\
          <div class="empty-state-container">\
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
              <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>\
            </svg>\
            <h3 class="empty-title">暂无资产</h3>\
            <p class="empty-desc">点击上方按钮上传资产</p>\
          </div>';
      }
      return;
    }

    var html = '';
    assets.forEach(function(asset, index) {
      html += '<div class="library-asset-card card-enter" style="animation-delay: ' + (index * 0.05) + 's;">';
      html += renderAssetCard(asset);
      html += '</div>';
    });
    assetGrid.innerHTML = html;

    // Attach event handlers with delegation
    attachAssetEventHandlers();
    setupAssetPreviews();
  }

  function attachAssetEventHandlers() {
    document.querySelectorAll('.asset-btn.delete').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var id = this.dataset.id;
        deleteAsset(id);
      });
    });

    document.querySelectorAll('.asset-btn.edit').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        openEditAssetModal(this.dataset.id);
      });
    });

    document.querySelectorAll('.asset-btn.download').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var id = this.dataset.id;
        downloadAsset(id);
      });
    });
  }

  function renderAssetCard(asset) {
    var previewHtml = renderPreview(asset);
    var assetTypeLabel = getAssetTypeLabel(asset.asset_type);
    var venueLabel = getVenueLabel(asset.venue_type);
    var createdAtLabel = asset.created_at && window.AIGV && window.AIGV.formatTime
      ? window.AIGV.formatTime(asset.created_at)
      : '';
    var editButton = asset.can_edit
      ? '<button class="asset-btn edit" data-id="' + escapeHtml(asset.id) + '" data-tooltip="编辑素材">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>\
            编辑\
          </button>'
      : '';
    var actionsClass = 'asset-actions' + (asset.can_edit ? ' asset-actions-edit' : '');

    return '\
      <div class="asset-preview">\
        ' + previewHtml + '\
        <span class="asset-type-badge">' + escapeHtml(assetTypeLabel) + '</span>\
      </div>\
      <div class="asset-info">\
        <h3>' + escapeHtml(asset.name) + '</h3>\
        <p>' + escapeHtml(asset.description || '暂无描述') + '</p>\
        <div class="asset-meta-info">\
          ' + (venueLabel ? '<span class="meta-tag meta-tag-venue">' + escapeHtml(venueLabel) + '</span>' : '') + '\
          ' + (asset.file_size ? '<span class="meta-tag">' + escapeHtml(formatFileSize(asset.file_size)) + '</span>' : '') + '\
          ' + (asset.asset_kind ? '<span class="meta-tag">' + escapeHtml(asset.asset_kind) + '</span>' : '') + '\
        </div>\
        ' + (createdAtLabel ? '<div class="asset-created-at">上传于 ' + escapeHtml(createdAtLabel) + '</div>' : '') + '\
        <div class="' + actionsClass + '">\
          ' + editButton + '\
          <button class="asset-btn primary download" data-id="' + escapeHtml(asset.id) + '" data-tooltip="下载资产">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\
            下载\
          </button>\
          <button class="asset-btn delete" data-id="' + escapeHtml(asset.id) + '" data-tooltip="删除资产">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>\
            删除\
          </button>\
        </div>\
      </div>';
  }

  function renderPreview(asset) {
    var fileUrl = asset.file_url ? escapeHtml(asset.file_url) : '';
    if (asset.asset_type === 'glb') {
      return renderModelPreview(asset);
    } else if (asset.asset_type === 'image' && fileUrl) {
      return '<img src="' + fileUrl + '" alt="' + escapeHtml(asset.name || '') + '" loading="lazy" onload="this.classList.add(\'loaded\')" />';
    } else if (asset.asset_type === 'video' && fileUrl) {
      return '<video src="' + fileUrl + '" controls></video>';
    } else if (asset.asset_type === 'audio' && fileUrl) {
      return '<audio src="' + fileUrl + '" controls></audio>';
    } else {
      return '\
        <svg class="placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
          <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>\
        </svg>';
    }
  }

  function modelPlaceholderIcon() {
    return '\
      <svg class="placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">\
        <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>\
      </svg>';
  }

  function isPreviewableAsset(asset) {
    if (!asset) return false;
    if (asset.previewable === true) return true;
    if (asset.previewable === false) return false;
    return asset.asset_type === 'glb' && asset.file_ext === 'glb';
  }

  function isLargePreviewAsset(asset) {
    return typeof asset.file_size === 'number' && asset.file_size > AUTO_PREVIEW_MAX_BYTES;
  }

  function assetDownloadUrl(asset) {
    if (asset && asset.download_url) return asset.download_url;
    return '/api/assets/' + encodeURIComponent((asset && asset.id) || '') + '/download';
  }

  function renderModelPreview(asset) {
    var assetId = escapeHtml(asset.id);
    var downloadUrl = asset.file_url ? escapeHtml(assetDownloadUrl(asset)) : '';

    if (!isPreviewableAsset(asset)) {
      var reason = asset.preview_reason || '该格式不支持在线预览，请下载查看';
      var extLabel = asset.file_ext ? String(asset.file_ext).toUpperCase() : '3D';
      return '\
        <div class="asset-preview-unavailable" data-asset-id="' + assetId + '">\
          <svg class="placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">\
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>\
            <polyline points="14 2 14 8 20 8"/>\
          </svg>\
          <span class="preview-format-chip">' + escapeHtml(extLabel) + '</span>\
          <p class="preview-unavailable-text">' + escapeHtml(reason) + '</p>\
          ' + (downloadUrl ? '<a class="preview-download-link" href="' + downloadUrl + '">下载文件</a>' : '') + '\
        </div>';
    }

    if (!asset.file_url) {
      return modelPlaceholderIcon();
    }

    if (isLargePreviewAsset(asset)) {
      return '\
        <div class="asset-preview-stage asset-preview-stage-manual" data-asset-id="' + assetId + '" data-preview-state="manual">\
          <div class="asset-preview-placeholder">\
            ' + modelPlaceholderIcon() + '\
            <span class="preview-size-chip">' + escapeHtml(formatFileSize(asset.file_size || 0)) + '</span>\
            <button type="button" class="asset-preview-load-btn">点击加载 3D 预览</button>\
          </div>\
        </div>';
    }

    return '\
      <div class="asset-preview-stage" data-asset-id="' + assetId + '" data-preview-state="auto">\
        <div class="asset-preview-placeholder asset-preview-placeholder-auto">\
          ' + modelPlaceholderIcon() + '\
          <span class="preview-load-hint">3D 预览待加载</span>\
        </div>\
      </div>';
  }

  function setupAssetPreviews() {
    if (!assetGrid) return;
    var pending = [];
    var stages = assetGrid.querySelectorAll('.asset-preview-stage[data-asset-id]');
    stages.forEach(function(container) {
      var assetId = container.getAttribute('data-asset-id');
      var asset = currentAssetsById[assetId];
      if (!asset || !asset.file_url) return;
      if (container.getAttribute('data-preview-state') === 'manual') {
        bindDeferredPreview(container, asset);
        return;
      }
      if (loadedPreviewAssetIds[assetId]) {
        createModelViewer(container, asset.file_url, assetId);
      } else if (typeof window.IntersectionObserver === 'function') {
        pending.push(container);
      } else {
        createModelViewer(container, asset.file_url, assetId);
      }
    });

    if (!pending.length) return;
    previewObserver = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (!entry.isIntersecting) return;
        var container = entry.target;
        previewObserver.unobserve(container);
        if (!container.isConnected) return;
        if (container.getAttribute('data-preview-state') !== 'auto') return;
        var assetId = container.getAttribute('data-asset-id');
        var asset = currentAssetsById[assetId];
        if (!asset || !asset.file_url) return;
        createModelViewer(container, asset.file_url, assetId);
      });
    }, { threshold: 0.01 });
    pending.forEach(function(container) {
      previewObserver.observe(container);
    });
  }

  function bindDeferredPreview(container, asset) {
    var button = container.querySelector('.asset-preview-load-btn');
    if (!button) return;
    button.addEventListener('click', function(e) {
      e.preventDefault();
      e.stopPropagation();
      createModelViewer(container, asset.file_url, asset.id);
    });
  }

  function clearPreviewTimer(assetId) {
    if (previewLoadTimers[assetId]) {
      clearTimeout(previewLoadTimers[assetId]);
      delete previewLoadTimers[assetId];
    }
  }

  function resetPreviewState() {
    if (previewObserver) {
      previewObserver.disconnect();
      previewObserver = null;
    }
    Object.keys(previewLoadTimers).forEach(function(assetId) {
      clearTimeout(previewLoadTimers[assetId]);
    });
    previewLoadTimers = {};
  }

  function createModelViewer(container, src, assetId, attempt) {
    if (!container || !src || !container.isConnected) return;
    clearPreviewTimer(assetId);
    var token = 'pv-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    var loadSrc = src;
    if (attempt) {
      // model-viewer caches failed loads per URL; bust it so retry actually re-fetches.
      loadSrc += (loadSrc.indexOf('?') === -1 ? '?' : '&') +
        '_retry=' + attempt + '-' + Date.now().toString(36);
    }
    container.setAttribute('data-preview-token', token);
    container.setAttribute('data-preview-state', 'loading');
    container.innerHTML = '\
      <div class="asset-preview-overlay asset-preview-overlay-loading">\
        <span class="preview-spinner" aria-hidden="true"></span>\
        <div class="preview-progress"><div class="preview-progress-bar"></div></div>\
        <span class="preview-progress-text">加载中 0%</span>\
      </div>';
    var overlay = container.querySelector('.asset-preview-overlay-loading');
    var progressBar = container.querySelector('.preview-progress-bar');
    var progressText = container.querySelector('.preview-progress-text');

    function isCurrent() {
      return container.getAttribute('data-preview-token') === token;
    }

    var viewer = document.createElement('model-viewer');
    viewer.setAttribute('camera-controls', '');
    viewer.setAttribute('touch-action', 'pan-y');
    viewer.setAttribute('interaction-prompt', 'none');
    viewer.setAttribute('alt', '');
    viewer.addEventListener('mouseover', function() {
      viewer.setAttribute('auto-rotate', '');
    });
    viewer.addEventListener('mouseout', function() {
      viewer.removeAttribute('auto-rotate');
    });
    viewer.addEventListener('progress', function(event) {
      if (!isCurrent()) return;
      var detail = event.detail || {};
      var progress = typeof detail.totalProgress === 'number' ? detail.totalProgress : 0;
      var percent = Math.max(0, Math.min(100, Math.round(progress * 100)));
      if (progressBar) progressBar.style.width = percent + '%';
      if (progressText) progressText.textContent = '加载中 ' + percent + '%';
    });
    viewer.addEventListener('load', function() {
      if (!isCurrent()) return;
      clearPreviewTimer(assetId);
      loadedPreviewAssetIds[assetId] = true;
      container.setAttribute('data-preview-state', 'loaded');
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    viewer.addEventListener('error', function() {
      if (!isCurrent()) return;
      showPreviewError(container, assetId, src, '预览加载失败，点击重试/下载', attempt);
    });

    container.appendChild(viewer);
    previewLoadTimers[assetId] = setTimeout(function() {
      delete previewLoadTimers[assetId];
      if (container.getAttribute('data-preview-state') === 'loaded') return;
      showPreviewError(container, assetId, src, '预览加载超时，点击重试/下载', attempt);
    }, PREVIEW_LOAD_TIMEOUT_MS);

    // The element upgrades asynchronously; setting src before that is supported.
    viewer.setAttribute('src', loadSrc);
  }

  function showPreviewError(container, assetId, src, message, attempt) {
    clearPreviewTimer(assetId);
    container.removeAttribute('data-preview-token');
    container.setAttribute('data-preview-state', 'error');
    container.innerHTML = '\
      <div class="asset-preview-overlay asset-preview-overlay-error">\
        <svg class="preview-error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">\
          <circle cx="12" cy="12" r="9"/>\
          <line x1="12" y1="7.5" x2="12" y2="13"/>\
          <line x1="12" y1="16.5" x2="12.01" y2="16.5"/>\
        </svg>\
        <p class="preview-error-text">' + escapeHtml(message) + '</p>\
        <div class="preview-error-actions">\
          <button type="button" class="asset-preview-retry">重试</button>\
          <a class="asset-preview-download" href="/api/assets/' + encodeURIComponent(assetId) + '/download">下载</a>\
        </div>\
      </div>';
    var retryButton = container.querySelector('.asset-preview-retry');
    if (retryButton) {
      retryButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        createModelViewer(container, src, assetId, (attempt || 0) + 1);
      });
    }
  }

  function renderPromptDocuments(documents) {
    if (!documents.length) {
      assetGrid.innerHTML = '\
        <div class="empty-state-container">\
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>\
            <polyline points="14 2 14 8 20 8"/>\
            <line x1="16" y1="13" x2="8" y2="13"/>\
            <line x1="16" y1="17" x2="8" y2="17"/>\
          </svg>\
          <h3 class="empty-title">暂无Prompt文档</h3>\
          <p class="empty-desc">从知识库导入或手动创建</p>\
        </div>';
      return;
    }

    var html = '';
    documents.forEach(function(doc, index) {
      var category = doc.category || '';
      // Categories are admin-supplied: keep the CSS token strictly alnum and
      // escape the attribute/label (both are rendered into HTML).
      var categoryToken = String(category || 'other').replace(/[^a-zA-Z0-9_-]/g, '') || 'other';
      var categoryClass = 'category-' + categoryToken;
      html += '\
        <div class="prompt-doc-card card-enter ' + categoryClass + '" style="animation-delay: ' + (index * 0.05) + 's;">\
          <div class="doc-header">\
            <h3 class="doc-title">' + escapeHtml(doc.title) + '</h3>\
            <span class="doc-category" data-category="' + escapeHtml(category) + '">' + escapeHtml(getCategoryLabel(category)) + '</span>\
          </div>\
          <div class="doc-content">' + escapeHtml(doc.content || '') + '</div>\
          ' + (doc.keywords ? '\
            <div class="doc-keywords">\
              ' + renderKeywords(doc.keywords) + '\
            </div>' : '') + '\
        </div>';
    });
    assetGrid.innerHTML = html;
  }

  function renderKeywords(keywords) {
    if (!keywords) return '';
    var keywordList = keywords.split(',').map(function(k) { return k.trim(); }).filter(function(k) { return k; });
    return keywordList.map(function(k) {
      return '<span class="meta-tag meta-tag-keyword">' + escapeHtml(k) + '</span>';
    }).join('');
  }

  function taskStatusMeta(status) {
    var map = {
      queued: { label: '排队中', className: 'task-status-queued' },
      submitting: { label: '提交中', className: 'task-status-running' },
      running: { label: '生成中', className: 'task-status-running' },
      succeeded: { label: '已完成', className: 'task-status-succeeded' },
      failed: { label: '失败', className: 'task-status-failed' },
      cancelled: { label: '已取消', className: 'task-status-cancelled' },
      needs_review: { label: '待人工确认', className: 'task-status-review' }
    };
    return map[status] || { label: status || '未知', className: 'task-status-queued' };
  }

  function renderTaskParams(params) {
    params = params || {};
    var rows = [];
    var labels = [
      ['model_key', '模型'], ['size', '尺寸'], ['ratio', '比例'],
      ['duration_s', '时长(秒)'], ['resolution', '分辨率'], ['seed', '随机种子'],
      ['generate_audio', '生成音频'], ['watermark', '水印']
    ];
    labels.forEach(function(pair) {
      var value = params[pair[0]];
      if (value === undefined || value === null || value === '') return;
      if (typeof value === 'boolean') value = value ? '是' : '否';
      rows.push('<div class="history-param-row"><span>' + pair[1] + '</span><strong>' + escapeText(value) + '</strong></div>');
    });
    var prompt = params.prompt ? '<p class="history-param-prompt">' + escapeText(params.prompt) + '</p>' : '';
    return '<details class="history-params"><summary>生成参数</summary>' + prompt +
      (rows.length ? '<div class="history-param-grid">' + rows.join('') + '</div>' : '') + '</details>';
  }

  function escapeText(value) {
    return window.AIGV && window.AIGV.escapeHtml
      ? window.AIGV.escapeHtml(value)
      : escapeHtml(String(value == null ? '' : value));
  }

  function renderGenerationTasks(tasks) {
    historyTaskMap = {};
    if (!tasks.length) {
      assetGrid.innerHTML = '\
        <div class="empty-state-container">\
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
            <circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>\
          </svg>\
          <h3 class="empty-title">还没有生成记录</h3>\
          <p class="empty-desc">可以用快速生成创建一条视频，或在项目工作流中制作多镜头项目。</p>\
          <div class="action-buttons">\
            <a class="btn-primary" href="/">快速生成</a>\
            <a class="btn-outline" href="/creative-studio">项目工作流</a>\
          </div>\
        </div>';
      return;
    }
    var html = '';
    tasks.forEach(function(task, index) {
      historyTaskMap[task.id] = task;
      html += '<div class="library-asset-card task-history-card card-enter" style="animation-delay: ' + (index * 0.04) + 's;">';
      html += renderGenerationCard(task);
      html += '</div>';
    });
    assetGrid.innerHTML = html;
    attachHistoryEventHandlers();
  }

  function renderGenerationCard(task) {
    var meta = taskStatusMeta(task.status);
    var asset = task.output_asset;
    var params = task.params || {};
    var fileUrl = asset ? '/api/assets/' + encodeURIComponent(asset.id) + '/file' : '';
    var preview = '';
    if (task.task_type === 'video' && fileUrl) {
      preview = '<video src="' + escapeText(fileUrl) + '" controls preload="metadata"></video>';
    } else if (task.task_type === 'image' && fileUrl) {
      preview = '<img src="' + escapeText(fileUrl) + '" alt="' + escapeText(params.prompt || '生成图片') + '" loading="lazy" />';
    } else {
      preview = '<div class="history-task-placeholder ' + meta.className + '">' + escapeText(meta.label) + '</div>';
    }

    var prompt = params.prompt || '（无 Prompt）';
    var created = window.AIGV.formatTime(task.created_at);
    var completed = task.completed_at ? window.AIGV.formatTime(task.completed_at) : '';
    var model = task.model_id || params.model_key || '';
    var error = '';
    if (task.status === 'failed' || task.status === 'needs_review') {
      var failureText = task.error_message || '生成失败';
      if (task.error_code) failureText = '[' + task.error_code + '] ' + failureText;
      error = '<p class="history-task-error">' + escapeText(failureText) + '</p>';
    }

    var active = task.status === 'queued' || task.status === 'submitting' || task.status === 'running';
    var actions = '';
    if (asset) {
      actions += '<button class="asset-btn primary history-download" data-id="' + escapeText(asset.id) + '">下载</button>';
      if (task.task_type === 'image') {
        actions += '<button class="asset-btn history-use-image" data-asset-id="' + escapeText(asset.id) + '">用此图生成视频</button>';
      }
      actions += '<button class="asset-btn delete history-delete" data-id="' + escapeText(asset.id) + '">删除作品</button>';
    }
    if (active) {
      actions += '<button class="asset-btn history-cancel" data-task-id="' + escapeText(task.id) + '">取消任务</button>';
    }
    if (task.status === 'succeeded' || task.status === 'failed') {
      actions += '<button class="asset-btn history-regenerate" data-task-id="' + escapeText(task.id) + '">重新生成</button>';
    }
    var artifacts = task.artifacts || [];
    var hasArtifactAsset = artifacts.some(function (artifact) {
      return !!(artifact && artifact.asset_id);
    });
    if (!asset && !hasArtifactAsset &&
        (task.status === 'failed' || task.status === 'cancelled')) {
      actions += '<button class="asset-btn delete history-delete-task" data-task-id="' +
        escapeText(task.id) + '">删除记录</button>';
    }

    return '\
      <div class="asset-preview">\
        ' + preview + '\
        <span class="asset-type-badge">' + (task.task_type === 'video' ? '视频' : '图片') + '</span>\
      </div>\
      <div class="asset-info">\
        <div class="history-task-head">\
          <h3>' + escapeText(prompt.length > 64 ? prompt.slice(0, 64) + '…' : prompt) + '</h3>\
          <span class="task-status-chip ' + meta.className + '">' + escapeText(meta.label) + '</span>\
        </div>\
        <p class="history-task-meta">' + escapeText(model) + ' · 创建 ' + escapeText(created) +
          (completed ? ' · 完成 ' + escapeText(completed) : '') + '</p>\
        ' + error + renderTaskParams(params) + '\
        <div class="asset-actions history-task-actions">' + actions + '</div>\
      </div>';
  }

  function attachHistoryEventHandlers() {
    document.querySelectorAll('.history-download').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        window.location.href = '/api/assets/' + encodeURIComponent(this.dataset.id) + '/download';
      });
    });
    document.querySelectorAll('.history-delete').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        deleteAsset(this.dataset.id);
      });
    });
    document.querySelectorAll('.history-cancel').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        cancelGenerationTask(this.dataset.taskId);
      });
    });
    document.querySelectorAll('.history-delete-task').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        deleteGenerationTask(this.dataset.taskId);
      });
    });
    document.querySelectorAll('.history-use-image').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        window.location.href = '/creative-studio?reference_asset_id=' +
          encodeURIComponent(this.dataset.assetId);
      });
    });
    document.querySelectorAll('.history-regenerate').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        regenerateTask(this.dataset.taskId);
      });
    });
  }

  function cancelGenerationTask(taskId) {
    showConfirmDialog('取消生成任务', '取消后任务将停止，已经产生的费用不会退回。确定继续？', '取消任务', function() {
      window.AIGV.api('/api/generation/tasks/' + encodeURIComponent(taskId) + '/cancel', {
        method: 'POST'
      }).then(function() {
        showToast('取消请求已提交', 'info');
        requestAssets();
      }).catch(function(error) {
        showToast((error && error.message) || '取消失败', 'error');
      });
    });
  }

  function deleteGenerationTask(taskId) {
    showConfirmDialog(
      '删除生成记录',
      '仅删除本地生成记录，已产生的费用不会退回；若失败任务仍保留第三方任务 ID，会尽力请求取消。确定删除？',
      '删除记录',
      function() {
        if (currentPage > 1 && Object.keys(historyTaskMap).length === 1) {
          currentPage -= 1;
        }
        window.AIGV.api('/api/generation/tasks/' + encodeURIComponent(taskId), {
          method: 'DELETE'
        }).then(function() {
          showToast('生成记录已删除', 'success');
          requestAssets();
        }).catch(function(error) {
          if (error && error.status === 404) {
            showToast('记录已不存在，正在刷新', 'info');
            requestAssets();
            return;
          }
          showToast((error && error.message) || '删除失败，请重试', 'error');
        });
      }
    );
  }

  function regenerateTask(taskId) {
    var task = historyTaskMap[taskId];
    if (!task) return;
    var params = task.params || {};
    if (!params.model_key) {
      showToast('该任务缺少模型信息，无法重新生成', 'warning');
      return;
    }
    var payload = { model_key: params.model_key, prompt: params.prompt };
    var endpoint = '/api/generation/images';
    if (task.task_type === 'video') {
      endpoint = '/api/generation/videos';
      payload.ratio = params.ratio;
      payload.duration_s = params.duration_s;
      payload.resolution = params.resolution;
      payload.generate_audio = params.generate_audio;
    } else {
      payload.size = params.size;
      payload.ratio = params.ratio;
      if (params.seed !== null && params.seed !== undefined) payload.seed = params.seed;
    }
    if (params.reference_asset_id) payload.reference_asset_id = params.reference_asset_id;
    window.AIGV.api(endpoint, { method: 'POST', body: payload })
      .then(function() {
        showToast('已重新提交生成任务', 'success');
        requestAssets();
      })
      .catch(function(error) {
        showToast((error && error.message) || '重新生成失败', 'error');
      });
  }

  function renderPagination() {
    if (!pagination || totalPages <= 1) {
      if (pagination) pagination.innerHTML = '';
      return;
    }

    var html = '';

    // Previous button
    html += '<button class="page-btn" data-page="' + (currentPage - 1) + '" ' + (currentPage <= 1 ? 'disabled' : '') + '>&laquo; 上一页</button>';

    // Page numbers
    var startPage = Math.max(1, currentPage - 2);
    var endPage = Math.min(totalPages, currentPage + 2);

    if (startPage > 1) {
      html += '<button class="page-btn" data-page="1">1</button>';
      if (startPage > 2) {
        html += '<span style="padding: 0 var(--space-sm); color: var(--text-muted);">...</span>';
      }
    }

    for (var i = startPage; i <= endPage; i++) {
      html += '<button class="page-btn ' + (i === currentPage ? 'active' : '') + '" data-page="' + i + '">' + i + '</button>';
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        html += '<span style="padding: 0 var(--space-sm); color: var(--text-muted);">...</span>';
      }
      html += '<button class="page-btn" data-page="' + totalPages + '">' + totalPages + '</button>';
    }

    // Next button
    html += '<button class="page-btn" data-page="' + (currentPage + 1) + '" ' + (currentPage >= totalPages ? 'disabled' : '') + '>下一页 &raquo;</button>';

    pagination.innerHTML = html;

    // Attach event handlers
    pagination.querySelectorAll('.page-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        if (this.disabled) return;
        currentPage = parseInt(this.dataset.page);
        requestAssets();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  }

  function openModal() {
    if (uploadModal) {
      uploadModal.classList.add('active');
      uploadModal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
      setTimeout(function() {
        var nameInput = document.getElementById('asset-name');
        if (nameInput) nameInput.focus();
      }, 100);
    }
  }

  function closeModal() {
    if (uploadModal) {
      uploadModal.classList.remove('active');
      uploadModal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    }
    if (uploadZone) {
      uploadZone.classList.remove('dragover', 'has-file', 'is-uploading');
    }
    if (uploadFileMeta) {
      uploadFileMeta.hidden = true;
      uploadFileMeta.textContent = '';
    }
    if (uploadForm) {
      uploadForm.reset();
    }
  }

  function openEditAssetModal(id) {
    if (!editAssetModal || !editAssetForm) return;
    var asset = currentAssetsById[id];
    if (!asset) {
      showToast('未找到该素材的最新数据，请刷新后重试', 'warning');
      return;
    }
    if (!asset.can_edit) {
      showToast('共享素材仅所有者可编辑', 'warning');
      return;
    }
    var typeText = getAssetTypeLabel(asset.asset_type);
    if (asset.file_ext) {
      typeText += ' · ' + String(asset.file_ext).toUpperCase();
    }
    editAssetIdInput.value = asset.id;
    editAssetNameInput.value = asset.name || '';
    editAssetDescInput.value = asset.description || '';
    editAssetVenueSelect.value = asset.venue_type || '';
    editAssetVisibilitySelect.value = asset.visibility === 'shared' ? 'shared' : 'private';
    editAssetTypeLabel.textContent = typeText;
    editAssetSizeLabel.textContent = formatFileSize(asset.file_size || 0);
    editAssetSaveBtn.disabled = false;
    editAssetSaveBtn.textContent = '保存';
    editAssetModal.classList.add('active');
    editAssetModal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    setTimeout(function() {
      editAssetNameInput.focus();
      editAssetNameInput.select();
    }, 100);
  }

  function closeEditAssetModal() {
    if (!editAssetModal) return;
    editAssetModal.classList.remove('active');
    editAssetModal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (editAssetForm) {
      editAssetForm.reset();
    }
    if (editAssetSaveBtn) {
      editAssetSaveBtn.disabled = false;
      editAssetSaveBtn.textContent = '保存';
    }
  }

  function handleEditAssetSave(e) {
    e.preventDefault();
    var id = editAssetIdInput ? editAssetIdInput.value : '';
    if (!id) return;
    var name = (editAssetNameInput.value || '').trim();
    if (!name) {
      showToast('请输入素材名称', 'warning');
      editAssetNameInput.focus();
      return;
    }
    var payload = {
      name: name,
      description: editAssetDescInput.value || '',
      venue_type: editAssetVenueSelect.value || '',
      visibility: editAssetVisibilitySelect.value || 'private'
    };
    var originalText = editAssetSaveBtn.textContent;
    editAssetSaveBtn.disabled = true;
    editAssetSaveBtn.textContent = '保存中...';
    window.AIGV.api('/api/assets/' + encodeURIComponent(id), {
      method: 'PUT',
      body: payload
    }).then(function(updated) {
      if (updated && updated.id) {
        currentAssetsById[updated.id] = updated;
      }
      closeEditAssetModal();
      showToast('素材已更新', 'success');
      requestAssets();
      loadSummary();
    }).catch(function(error) {
      showToast((error && error.message) || '保存失败，请重试', 'error');
    }).finally(function() {
      editAssetSaveBtn.disabled = false;
      editAssetSaveBtn.textContent = originalText;
    });
  }

  function renderUploadFileMeta(file) {
    if (!uploadFileMeta) return;
    if (!file) {
      uploadFileMeta.hidden = true;
      uploadFileMeta.textContent = '';
      return;
    }
    uploadFileMeta.hidden = false;
    uploadFileMeta.innerHTML = '<strong>' + escapeHtml(file.name) + '</strong><br />' + formatFileSize(file.size || 0);
  }

  function updateFileName() {
    if (fileInput.files.length) {
      var file = fileInput.files[0];
      var nameInput = document.getElementById('asset-name');
      if (nameInput && !nameInput.value) {
        nameInput.value = file.name.replace(/\.[^/.]+$/, '');
      }

      if (uploadZone) {
        uploadZone.classList.add('has-file');
      }
      renderUploadFileMeta(file);

      // Auto-detect asset type
      var typeSelect = document.getElementById('asset-type');
      if (typeSelect) {
        var ext = file.name.split('.').pop().toLowerCase();
        var detectedType = ALLOWED_EXTENSIONS[ext];
        if (detectedType) {
          typeSelect.value = detectedType;
        } else {
          showToast('不支持的文件格式: .' + ext, 'warning');
        }
      }

      showToast('已选择文件: ' + file.name, 'info');
    } else {
      if (uploadZone) {
        uploadZone.classList.remove('has-file');
      }
      renderUploadFileMeta(null);
    }
  }

  function handleUpload(e) {
    e.preventDefault();

    if (!fileInput.files.length) {
      showToast('请选择文件', 'warning');
      return;
    }

    // Pre-validate extension before upload (backend remains authoritative)
    var uploadFileName = fileInput.files[0].name;
    var uploadExt = uploadFileName.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS[uploadExt]) {
      showToast('不支持的文件格式: .' + uploadExt, 'error');
      return;
    }

    var formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('name', document.getElementById('asset-name').value);
    formData.append('asset_type', document.getElementById('asset-type').value);
    formData.append('venue_type', document.getElementById('asset-venue').value);
    formData.append('description', document.getElementById('asset-desc').value);

    // Show loading state
    var submitBtn = uploadForm.querySelector('button[type="submit"]');
    var originalText = submitBtn.textContent;
    submitBtn.textContent = '上传中...';
    submitBtn.disabled = true;

    if (uploadZone) {
      uploadZone.classList.add('is-uploading');
    }

    window.AIGV.api('/api/assets/upload', {
      method: 'POST',
      body: formData
    })
      .then(function() {
        showToast('上传成功!', 'success');
        closeModal();
        requestAssets();
        loadSummary();
      })
      .catch(function(error) {
        console.error('Upload error:', error);
        showToast((error && error.message) || '上传失败，请重试', 'error');
      })
      .finally(function() {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
        if (uploadZone) {
          uploadZone.classList.remove('is-uploading');
        }
      });
  }

  function deleteAsset(id) {
    showConfirmDialog('删除资产', '确定要删除这个资产吗？此操作无法撤销。', '删除', function() {
      window.AIGV.api('/api/assets/' + encodeURIComponent(id), {
        method: 'DELETE'
      }).then(function() {
        showToast('删除成功', 'success');
        requestAssets();
        loadSummary();
      }).catch(function(error) {
        console.error('Delete error:', error);
        showToast((error && error.message) || '删除失败，请重试', 'error');
      });
    });
  }

  function downloadAsset(id) {
    showToast('开始下载...', 'info');
    window.location.href = '/api/assets/' + id + '/download';
  }

  // Utility functions
  function escapeHtml(text) {
    if (!text) return '';
    return String(text).replace(/[&<>"']/g, function(ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[ch];
    });
  }

  // Custom confirm dialog (replaces browser native confirm())
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

    function onKeyDown(e) {
      if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKeyDown); }
      if (e.key === 'Enter') { confirmBtn.click(); document.removeEventListener('keydown', onKeyDown); }
    }
    document.addEventListener('keydown', onKeyDown);

    setTimeout(function() { confirmBtn.focus(); }, 50);
  }

  function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB'];
    var i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
      bytes /= 1024;
      i++;
    }
    return bytes.toFixed(1) + ' ' + units[i];
  }

  function getAssetTypeLabel(type) {
    var labels = {
      'glb': '3D模型',
      'image': '图片',
      'video': '视频',
      'audio': '音频',
      'document': '文档',
      'archive': '压缩包',
      'prompt_doc': 'Prompt文档',
      'spatial_anchor': '空间锚点',
      'prompt_only': '纯文本'
    };
    return labels[type] || type;
  }

  function getVenueLabel(type) {
    var labels = {
      'grand_theater': '大剧院',
      'modern_gallery': '现代画廊',
      'ancient_museum': '古典博物馆',
      'concert_hall': '音乐厅'
    };
    return labels[type] || '';
  }

  function getCategoryLabel(category) {
    var labels = {
      'venue': '场馆',
      'shot': '镜头',
      'lighting': '光影',
      'style': '风格',
      'subject': '主体',
      'dynamics': '动态',
      'environment': '环境'
    };
    return labels[category] || category || '其他';
  }
})();