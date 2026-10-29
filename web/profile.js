(function (global) {
  'use strict';

  var profile = null;
  var toastContainer = document.getElementById('profile-toast-container');

  function $(id) { return document.getElementById(id); }

  function showToast(message, type) {
    if (!toastContainer) return;
    var toast = document.createElement('div');
    toast.className = 'toast ' + (type === 'error' ? 'toast-error' : 'toast-success');
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3200);
  }

  function roleLabel(role) {
    return role === 'admin' ? '平台管理员' : '普通用户';
  }

  function statusLabel(status) {
    return status === 'active' ? '正常' : '已禁用';
  }

  function typeLabel(type) {
    return ({ image: '图片', video: '视频', storyboard: '分镜', tts: '配音', compose: '合成', refine: '精修', export: '导出' })[type] || type;
  }

  function renderAvatar(user) {
    var img = $('profile-avatar');
    var fallback = $('profile-avatar-fallback');
    if (!img || !fallback) return;
    if (user && user.avatar_url) {
      img.src = user.avatar_url;
      img.hidden = false;
      fallback.hidden = true;
    } else {
      img.hidden = true;
      fallback.hidden = false;
      fallback.textContent = ((user && (user.nickname || user.username)) || '?').trim().slice(0, 1).toUpperCase();
    }
  }

  function renderStats(stats) {
    var container = $('profile-stats');
    if (!container) return;
    container.textContent = '';
    var cards = [
      ['任务总数', stats.tasks_total, '全部生成任务'],
      ['已完成图片', stats.images_completed, '图片生成成功'],
      ['已完成视频', stats.videos_completed, '视频生成成功'],
      ['运行中', stats.tasks_running, '排队/提交/运行'],
      ['我的项目', stats.projects, '创意项目'],
      ['我的素材', stats.assets, '私有素材']
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

  function renderRecent(tasks) {
    var container = $('profile-recent-list');
    if (!container) return;
    container.textContent = '';
    if (!tasks || !tasks.length) {
      var empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = '还没有生成记录，去创意工作台开始第一个项目吧。';
      container.appendChild(empty);
      var emptyLink = document.createElement('a');
      emptyLink.className = 'btn-outline btn-sm';
      emptyLink.href = '/assets?tab=history';
      emptyLink.textContent = '查看生成历史';
      container.appendChild(emptyLink);
      return;
    }
    var allLink = document.createElement('a');
    allLink.className = 'btn-outline btn-sm profile-history-link';
    allLink.href = '/assets?tab=history';
    allLink.textContent = '查看全部生成历史';
    container.appendChild(allLink);
    tasks.forEach(function (task) {
      var row = document.createElement('div');
      row.className = 'profile-recent-item';

      var main = document.createElement('div');
      main.className = 'profile-recent-main';
      var title = document.createElement('strong');
      title.textContent = typeLabel(task.task_type) + ' · ' + (task.status || 'unknown');
      var meta = document.createElement('span');
      meta.className = 'profile-recent-meta';
      meta.textContent = AIGV.formatTime(task.created_at) + (task.completed_at ? ' 完成于 ' + AIGV.formatTime(task.completed_at) : '');
      main.appendChild(title);
      main.appendChild(meta);

      var action = document.createElement('div');
      if (task.output_asset_id) {
        var link = document.createElement('a');
        link.className = 'btn-outline btn-sm';
        link.href = '/api/assets/' + encodeURIComponent(task.output_asset_id) + '/file';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = '查看结果';
        action.appendChild(link);
      } else if (task.error_message) {
        var err = document.createElement('span');
        err.className = 'profile-recent-error';
        err.textContent = task.error_message;
        action.appendChild(err);
      }

      row.appendChild(main);
      row.appendChild(action);
      container.appendChild(row);
    });
  }

  function fillProfile(data) {
    profile = data;
    var title = $('profile-title');
    var subtitle = $('profile-subtitle');
    if (title) title.textContent = data.nickname || data.username || '个人中心';
    if (subtitle) subtitle.textContent = '@' + (data.username || '');
    var roleBadge = $('profile-role-badge');
    if (roleBadge) {
      roleBadge.textContent = roleLabel(data.role);
      roleBadge.className = 'cp-badge ' + (data.role === 'admin' ? 'cp-badge-success' : 'cp-badge-muted');
    }
    var statusBadge = $('profile-status-badge');
    if (statusBadge) {
      statusBadge.textContent = statusLabel(data.status);
      statusBadge.className = 'cp-badge ' + (data.status === 'active' ? 'cp-badge-success' : 'cp-badge-danger');
    }
    var meta = $('profile-meta');
    if (meta) {
      meta.textContent = '';
      var lines = [
        ['注册时间', AIGV.formatTime(data.created_at)],
        ['最近登录', AIGV.formatTime(data.last_login_at)],
        ['邮箱', data.email || '未填写']
      ];
      lines.forEach(function (line) {
        var item = document.createElement('div');
        item.className = 'profile-meta-item';
        var label = document.createElement('span');
        label.textContent = line[0];
        var value = document.createElement('strong');
        value.textContent = line[1];
        item.appendChild(label);
        item.appendChild(value);
        meta.appendChild(item);
      });
    }
    var username = $('profile-username');
    var nickname = $('profile-nickname');
    var email = $('profile-email');
    var bio = $('profile-bio');
    if (username) username.value = data.username || '';
    if (nickname) nickname.value = data.nickname || '';
    if (email) email.value = data.email || '';
    if (bio) bio.value = data.bio || '';
    renderAvatar(data);
    renderStats(data.stats || {});
    renderRecent((data.stats || {}).recent_tasks || []);
  }

  function loadProfile() {
    return AIGV.api('/api/user/profile').then(fillProfile).catch(function (error) {
      showToast(error.message || '加载个人资料失败', 'error');
    });
  }

  function handleProfileSubmit(event) {
    event.preventDefault();
    var body = {
      nickname: $('profile-nickname').value.trim(),
      email: $('profile-email').value.trim(),
      bio: $('profile-bio').value.trim()
    };
    AIGV.api('/api/user/profile', { method: 'PATCH', body: body }).then(function (data) {
      showToast('个人资料已更新', 'success');
      fillProfile(Object.assign({}, profile || {}, data, { stats: (profile || {}).stats }));
    }).catch(function (error) {
      showToast(error.message || '保存失败', 'error');
    });
  }

  function handlePasswordSubmit(event) {
    event.preventDefault();
    var current = $('current-password').value;
    var next = $('new-password').value;
    var confirm = $('confirm-new-password').value;
    if (!current || !next) {
      showToast('请填写当前密码和新密码', 'error');
      return;
    }
    if (next.length < 8) {
      showToast('新密码至少需要 8 位字符', 'error');
      return;
    }
    if (next !== confirm) {
      showToast('两次输入的新密码不一致', 'error');
      return;
    }
    AIGV.api('/api/user/password', {
      method: 'PUT',
      body: { current_password: current, new_password: next, confirm_password: confirm }
    }).then(function () {
      showToast('密码已修改，正在返回登录页...', 'success');
      setTimeout(function () { global.location.href = '/login'; }, 900);
    }).catch(function (error) {
      showToast(error.message || '修改密码失败', 'error');
    });
  }

  function handleAvatarChange() {
    var input = $('avatar-input');
    if (!input || !input.files || !input.files[0]) return;
    var file = input.files[0];
    if (file.size > 2 * 1024 * 1024) {
      showToast('头像不能超过 2 MB', 'error');
      return;
    }
    if (['image/png', 'image/jpeg', 'image/webp'].indexOf(file.type) === -1) {
      showToast('头像仅支持 PNG/JPEG/WebP', 'error');
      return;
    }
    var formData = new FormData();
    formData.append('file', file);
    AIGV.api('/api/user/avatar', { method: 'POST', body: formData }).then(function (data) {
      showToast('头像已更新', 'success');
      if (profile) profile.avatar_url = data.avatar_url;
      renderAvatar(profile || {});
    }).catch(function (error) {
      showToast(error.message || '头像上传失败', 'error');
    });
  }

  function handleAvatarDelete() {
    AIGV.api('/api/user/avatar', { method: 'DELETE' }).then(function () {
      if (profile) profile.avatar_url = null;
      renderAvatar(profile || {});
      showToast('头像已移除', 'success');
    }).catch(function (error) {
      showToast(error.message || '移除头像失败', 'error');
    });
  }

  function init() {
    var profileForm = $('profile-form');
    var passwordForm = $('password-form');
    var avatarInput = $('avatar-input');
    var avatarDelete = $('avatar-delete');
    if (profileForm) profileForm.addEventListener('submit', handleProfileSubmit);
    if (passwordForm) passwordForm.addEventListener('submit', handlePasswordSubmit);
    if (avatarInput) avatarInput.addEventListener('change', handleAvatarChange);
    if (avatarDelete) avatarDelete.addEventListener('click', handleAvatarDelete);
    loadProfile();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
