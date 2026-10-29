(function (global) {
  'use strict';

  var elForm = document.getElementById('auth-form');
  var elMessage = document.getElementById('auth-message');
  var isLogin = global.location.pathname.indexOf('register') === -1;
  var submitButton = elForm ? elForm.querySelector('button[type="submit"]') : null;
  var pending = false;

  function showMessage(message, type) {
    if (!elMessage) return;
    elMessage.textContent = message;
    elMessage.className = 'auth-message ' + (type === 'error' ? 'error' : 'success');
    elMessage.style.display = 'block';
  }

  function hideMessage() {
    if (!elMessage) return;
    elMessage.style.display = 'none';
    elMessage.className = 'auth-message';
  }

  function valueOf(id) {
    var element = document.getElementById(id);
    return element ? element.value.trim() : '';
  }

  function rawValueOf(id) {
    var element = document.getElementById(id);
    return element ? element.value : '';
  }

  function validEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function requestedNext() {
    return new URLSearchParams(global.location.search).get('next') || '';
  }

  function safeNext() {
    var next = requestedNext() || '/';
    if (!next || next.charAt(0) !== '/' || next.charAt(1) === '/' || next.indexOf('\\') !== -1 || next.indexOf('/api/') === 0) {
      return '/';
    }
    return next;
  }

  function validate() {
    hideMessage();
    var username = valueOf('username');
    var password = rawValueOf('password');
    var email = valueOf('email');

    if (!username) {
      showMessage('请输入用户名', 'error');
      document.getElementById('username').focus();
      return false;
    }
    if (!password) {
      showMessage('请输入密码', 'error');
      document.getElementById('password').focus();
      return false;
    }
    if (isLogin) return true;

    var nickname = valueOf('nickname');
    if (!nickname) {
      showMessage('请输入昵称', 'error');
      document.getElementById('nickname').focus();
      return false;
    }
    if (email && !validEmail(email)) {
      showMessage('请输入有效的邮箱地址', 'error');
      document.getElementById('email').focus();
      return false;
    }
    if (password.length < 8) {
      showMessage('密码至少需要 8 位字符', 'error');
      document.getElementById('password').focus();
      return false;
    }
    if (password.length > 128) {
      showMessage('密码不能超过 128 位字符', 'error');
      document.getElementById('password').focus();
      return false;
    }
    var confirmPassword = rawValueOf('confirm_password');
    if (!confirmPassword) {
      showMessage('请确认密码', 'error');
      document.getElementById('confirm_password').focus();
      return false;
    }
    if (password !== confirmPassword) {
      showMessage('两次输入的密码不一致', 'error');
      return false;
    }
    var terms = document.getElementById('terms_accepted');
    if (!terms || !terms.checked) {
      showMessage('请先同意用户协议', 'error');
      if (terms) terms.focus();
      return false;
    }
    return true;
  }

  function setPending(nextPending) {
    pending = nextPending;
    if (!submitButton) return;
    submitButton.disabled = nextPending;
    submitButton.textContent = nextPending ? (isLogin ? '登录中...' : '注册中...') : (isLogin ? '登录' : '注册');
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (pending || !validate()) return;

    setPending(true);
    try {
      var body = {
        username: valueOf('username'),
        password: rawValueOf('password')
      };
      var nextTarget = requestedNext();
      if (nextTarget) {
        body.next = nextTarget;
      }
      if (!isLogin) {
        body.nickname = valueOf('nickname');
        body.email = valueOf('email');
        body.confirm_password = rawValueOf('confirm_password');
        body.terms_accepted = true;
      }

      var data = await global.AIGV.api(isLogin ? '/api/auth/login' : '/api/auth/register', {
        method: 'POST',
        body: body,
        noRedirect: true
      });
      if (data && data.csrf_token) {
        global.AIGV.setCsrfToken(data.csrf_token);
      }
      showMessage(isLogin ? '登录成功，正在跳转...' : '注册成功，正在跳转...', 'success');
      setTimeout(function () {
        var target = data && data.redirect_to ? data.redirect_to : safeNext();
        global.location.href = target || '/';
      }, 500);
    } catch (error) {
      var message = error && error.message ? error.message : '请求失败，请稍后重试';
      if (error && error.code === 'account_locked' && error.details && error.details.retry_after) {
        message = '账户暂时锁定，请在 ' + error.details.retry_after + ' 秒后重试';
      }
      showMessage(message, 'error');
      setPending(false);
    }
  }

  if (elForm) {
    elForm.addEventListener('submit', handleSubmit);
  }

  if (global.AIGV && global.AIGV.runtime && global.AIGV.runtime.allowRegistration === false) {
    var registerLink = document.querySelector('.auth-footer a[href="/register"]');
    if (registerLink) {
      var footer = registerLink.parentNode;
      footer.textContent = '当前未开放公开注册';
    }
  }

  // Warm the CSRF token so the first submit does not race a cold session.
  if (global.AIGV && global.AIGV.ensureCsrf) {
    global.AIGV.ensureCsrf(false).catch(function () {});
  }
})(window);
