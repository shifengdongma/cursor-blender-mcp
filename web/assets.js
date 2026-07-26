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
  var isLoading = false;

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
          currentPage = 1;
          loadAssets();
        }, 300);
      });
    }

    // Venue filter
    if (venueFilterSelect) {
      venueFilterSelect.addEventListener('change', function() {
        venueFilter = this.value;
        currentPage = 1;
        loadAssets();
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

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && uploadModal && uploadModal.classList.contains('active')) {
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

    // Initial load
    loadAssets();
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

    // Update filter visibility
    if (venueFilterSelect) {
      venueFilterSelect.style.display = tab === 'prompts' ? 'none' : 'block';
    }

    // Load content with fade effect
    if (assetGrid) {
      assetGrid.style.opacity = '0';
      setTimeout(function() {
        loadAssets();
      }, 150);
    } else {
      loadAssets();
    }
  }

  function getAssetTypeForTab() {
    switch (currentTab) {
      case 'models':
        return 'glb';
      case 'images':
        return 'image';
      case 'prompts':
        return 'prompt_doc';
      default:
        return 'glb';
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

  function loadAssets() {
    if (!assetGrid || isLoading) return;

    isLoading = true;

    // Show loading skeleton
    assetGrid.innerHTML = renderSkeletons();
    assetGrid.style.opacity = '1';

    var endpoint = currentTab === 'prompts' ? '/api/prompts/documents' : '/api/assets';
    var params = new URLSearchParams();
    params.append('limit', pageSize);
    params.append('offset', (currentPage - 1) * pageSize);

    if (currentTab !== 'prompts') {
      params.append('asset_type', getAssetTypeForTab());
      if (venueFilter) {
        params.append('venue_type', venueFilter);
      }
    }

    fetch(endpoint + '?' + params.toString())
      .then(function(response) {
        if (!response.ok) {
          throw new Error('Network response was not ok');
        }
        return response.json();
      })
      .then(function(data) {
        isLoading = false;
        var responseData = getResponseData(data) || {};
        var items = responseData.items || [];
        var filteredItems = filterItems(items);
        if (currentTab === 'prompts') {
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
        isLoading = false;
        console.error('Error loading assets:', error);
        assetGrid.innerHTML = '<div class="empty-state-container"><p class="empty-desc">加载失败，请重试</p></div>';
        showToast('加载失败，请检查网络连接', 'error');
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

  function renderAssets(assets) {
    if (!assets.length) {
      assetGrid.innerHTML = '\
        <div class="empty-state-container">\
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
            <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>\
          </svg>\
          <h3 class="empty-title">暂无资产</h3>\
          <p class="empty-desc">点击上方按钮上传资产</p>\
        </div>';
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
  }

  function attachAssetEventHandlers() {
    document.querySelectorAll('.asset-btn.delete').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var id = this.dataset.id;
        deleteAsset(id);
      });
    });

    document.querySelectorAll('.asset-btn.download').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var id = this.dataset.id;
        downloadAsset(id);
      });
    });

    // Add hover effect for model-viewer
    document.querySelectorAll('model-viewer').forEach(function(mv) {
      mv.addEventListener('mouseover', function() {
        this.setAttribute('auto-rotate', '');
      });
      mv.addEventListener('mouseout', function() {
        this.removeAttribute('auto-rotate');
      });
    });
  }

  function renderAssetCard(asset) {
    var previewHtml = renderPreview(asset);
    var assetTypeLabel = getAssetTypeLabel(asset.asset_type);
    var venueLabel = getVenueLabel(asset.venue_type);

    return '\
      <div class="asset-preview">\
        ' + previewHtml + '\
        <span class="asset-type-badge">' + assetTypeLabel + '</span>\
      </div>\
      <div class="asset-info">\
        <h3>' + escapeHtml(asset.name) + '</h3>\
        <p>' + escapeHtml(asset.description || '暂无描述') + '</p>\
        <div class="asset-meta-info">\
          ' + (venueLabel ? '<span class="meta-tag meta-tag-venue">' + venueLabel + '</span>' : '') + '\
          ' + (asset.file_size ? '<span class="meta-tag">' + formatFileSize(asset.file_size) + '</span>' : '') + '\
          ' + (asset.asset_kind ? '<span class="meta-tag">' + escapeHtml(asset.asset_kind) + '</span>' : '') + '\
        </div>\
        <div class="asset-actions">\
          <button class="asset-btn primary download" data-id="' + asset.id + '" data-tooltip="下载资产">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>\
            下载\
          </button>\
          <button class="asset-btn delete" data-id="' + asset.id + '" data-tooltip="删除资产">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>\
            删除\
          </button>\
        </div>\
      </div>';
  }

  function renderPreview(asset) {
    if (asset.asset_type === 'glb' && asset.file_path) {
      return '<model-viewer src="/data/assets/' + asset.file_path + '" camera-controls touch-action="pan-y" interaction-prompt="none"></model-viewer>';
    } else if (asset.asset_type === 'image' && asset.file_path) {
      return '<img src="/data/assets/' + asset.file_path + '" alt="' + escapeHtml(asset.name) + '" loading="lazy" onload="this.classList.add(\'loaded\')" />';
    } else {
      return '\
        <svg class="placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">\
          <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>\
        </svg>';
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
      var categoryClass = 'category-' + (doc.category || 'other');
      html += '\
        <div class="prompt-doc-card card-enter ' + categoryClass + '" style="animation-delay: ' + (index * 0.05) + 's;">\
          <div class="doc-header">\
            <h3 class="doc-title">' + escapeHtml(doc.title) + '</h3>\
            <span class="doc-category" data-category="' + (doc.category || '') + '">' + getCategoryLabel(doc.category) + '</span>\
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
        loadAssets();
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
        if (ext === 'glb' || ext === 'gltf') {
          typeSelect.value = 'glb';
        } else if (['png', 'jpg', 'jpeg', 'webp', 'gif'].indexOf(ext) !== -1) {
          typeSelect.value = 'image';
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

    fetch('/api/assets/upload', {
      method: 'POST',
      body: formData
    })
      .then(function(response) {
        return response.json();
      })
      .then(function(data) {
        getResponseData(data);
        showToast(((data && data.message) || '上传成功!'), 'success');
        closeModal();
        loadAssets();
      })
      .catch(function(error) {
        console.error('Upload error:', error);
        showToast('上传失败，请重试', 'error');
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

    fetch('/api/assets/' + id, {
      method: 'DELETE'
    })
      .then(function(response) {
        return response.json();
      })
      .then(function(data) {
        if (data.success || (data.data && data.data.deleted)) {
          showToast(((data && data.message) || '删除成功'), 'success');
          loadAssets();
        } else {
          showToast('删除失败: ' + (((data && data.message) || data.error) || '未知错误'), 'error');
        }
      })
      .catch(function(error) {
        console.error('Delete error:', error);
        showToast('删除失败，请重试', 'error');
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
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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