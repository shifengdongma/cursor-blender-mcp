(function (global) {
  'use strict';

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function initialOf(user) {
    var name = (user && (user.nickname || user.username)) || '?';
    return String(name).trim().slice(0, 1).toUpperCase();
  }

  function buildUserMenu(user) {
    var wrapper = document.createElement('div');
    wrapper.className = 'nav-user';

    var trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'nav-user-trigger';
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');

    var avatar = null;
    if (user.has_avatar) {
      avatar = document.createElement('img');
      avatar.className = 'nav-avatar';
      avatar.alt = '';
      avatar.src = '/api/user/avatar?t=' + Date.now();
      avatar.addEventListener('error', function () {
        if (avatar && avatar.parentNode) {
          avatar.parentNode.replaceChild(buildFallbackAvatar(user), avatar);
        }
      });
    } else {
      avatar = buildFallbackAvatar(user);
    }
    trigger.appendChild(avatar);

    var name = document.createElement('span');
    name.className = 'nav-user-name';
    name.textContent = user.nickname || user.username;
    trigger.appendChild(name);

    var chevron = document.createElement('span');
    chevron.className = 'nav-user-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    chevron.textContent = '▾';
    trigger.appendChild(chevron);

    var menu = document.createElement('div');
    menu.className = 'nav-user-menu';
    menu.setAttribute('role', 'menu');

    var apiSettings = document.createElement('a');
    apiSettings.href = '/api-settings';
    apiSettings.setAttribute('role', 'menuitem');
    apiSettings.textContent = 'API 配置';
    menu.appendChild(apiSettings);

    var profile = document.createElement('a');
    profile.href = '/profile';
    profile.setAttribute('role', 'menuitem');
    profile.textContent = '个人中心';
    menu.appendChild(profile);

    if (user.role === 'admin') {
      var admin = document.createElement('a');
      admin.href = '/admin/users';
      admin.setAttribute('role', 'menuitem');
      admin.textContent = '用户管理';
      menu.appendChild(admin);
    }

    var divider = document.createElement('div');
    divider.className = 'nav-user-divider';
    menu.appendChild(divider);

    var logout = document.createElement('button');
    logout.type = 'button';
    logout.className = 'nav-user-logout';
    logout.setAttribute('role', 'menuitem');
    logout.textContent = '退出登录';
    logout.addEventListener('click', function () {
      logout.disabled = true;
      logout.textContent = '正在退出...';
      global.AIGV.logout().catch(function () {
        logout.disabled = false;
        logout.textContent = '退出登录';
      });
    });
    menu.appendChild(logout);

    trigger.addEventListener('click', function (event) {
      event.stopPropagation();
      var open = wrapper.classList.toggle('is-open');
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);
    return wrapper;
  }

  function buildFallbackAvatar(user) {
    var fallback = document.createElement('span');
    fallback.className = 'nav-avatar nav-avatar-fallback';
    fallback.textContent = initialOf(user);
    return fallback;
  }

  ready(function () {
    if (global.AIGV.isAuthPage()) return;

    global.AIGV.getCurrentUser().then(function (user) {
      if (!user) {
        var next = global.location.pathname + global.location.search;
        global.location.href = '/login?next=' + encodeURIComponent(next);
        return;
      }

      var navLinks = document.querySelector('.nav-links');
      if (navLinks) {
        var loginLinks = navLinks.querySelectorAll('a[href="/login"]');
        for (var i = 0; i < loginLinks.length; i += 1) {
          loginLinks[i].parentNode.removeChild(loginLinks[i]);
        }
        // Compute features require an explicit permission; hide the entry
        // instead of sending ordinary users to a 403 page.
        var capabilities = user.capabilities || {};
        if (capabilities.view_compute === false) {
          var computeLinks = navLinks.querySelectorAll('a[href^="/compute-platform"]');
          for (var k = 0; k < computeLinks.length; k += 1) {
            computeLinks[k].parentNode.removeChild(computeLinks[k]);
          }
        }
        navLinks.appendChild(buildUserMenu(user));
      }

      if (global.AIGV.runtime && global.AIGV.runtime.demoMode) {
        var container = document.querySelector('.nav-container');
        if (container && !document.querySelector('.nav-demo-badge')) {
          var badge = document.createElement('span');
          badge.className = 'nav-demo-badge';
          badge.textContent = '演示模式';
          container.appendChild(badge);
        }
      }

      document.addEventListener('click', function () {
        var openMenus = document.querySelectorAll('.nav-user.is-open');
        for (var j = 0; j < openMenus.length; j += 1) {
          openMenus[j].classList.remove('is-open');
          var trigger = openMenus[j].querySelector('.nav-user-trigger');
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
        }
      });
    }).catch(function () {
      var next = global.location.pathname + global.location.search;
      global.location.href = '/login?next=' + encodeURIComponent(next);
    });
  });
})(window);
