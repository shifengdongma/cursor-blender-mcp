(function () {
  var elForm = document.getElementById('auth-form');
  var elMessage = document.getElementById('auth-message');

  var isLogin = window.location.pathname.indexOf('register') === -1;

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

  function validate() {
    hideMessage();

    var username = document.getElementById('username');
    var password = document.getElementById('password');
    var email = document.getElementById('email');
    var confirmPassword = document.getElementById('confirm_password');

    if (!username || !username.value.trim()) {
      showMessage('请输入用户名', 'error');
      username.focus();
      return false;
    }

    if (email && !email.value.trim()) {
      showMessage('请输入邮箱地址', 'error');
      email.focus();
      return false;
    }

    if (email && email.value.trim()) {
      var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email.value.trim())) {
        showMessage('请输入有效的邮箱地址', 'error');
        email.focus();
        return false;
      }
    }

    if (!password || !password.value) {
      showMessage('请输入密码', 'error');
      password.focus();
      return false;
    }

    if (isLogin) return true;

    if (password.value.length < 6) {
      showMessage('密码至少需要6位字符', 'error');
      password.focus();
      return false;
    }

    if (!confirmPassword || !confirmPassword.value) {
      showMessage('请确认密码', 'error');
      confirmPassword.focus();
      return false;
    }

    if (password.value !== confirmPassword.value) {
      showMessage('两次输入的密码不一致', 'error');
      return false;
    }

    return true;
  }

  function getSubmitUrl() {
    return isLogin ? '/api/auth/login' : '/api/auth/register';
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!validate()) return;
    hideMessage();

    try {
      var body = {
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value
      };

      if (!isLogin) {
        var emailEl = document.getElementById('email');
        if (emailEl) body.email = emailEl.value.trim();
      }

      var res = await fetch(getSubmitUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      var data;
      var contentType = res.headers.get('content-type') || '';
      if (contentType.indexOf('application/json') >= 0) {
        data = await res.json();
      } else {
        data = { message: await res.text() };
      }

      if (!res.ok) {
        throw new Error(data.message || data.error || '请求失败');
      }

      if (data && data.success !== undefined && !data.success) {
        throw new Error(data.message || data.error || '操作失败');
      }

      showMessage(isLogin ? '登录成功，正在跳转...' : '注册成功，正在跳转...', 'success');

      setTimeout(function () {
        window.location.href = '/';
      }, 800);
    } catch (err) {
      showMessage(err.message, 'error');
    }
  }

  if (elForm) {
    elForm.addEventListener('submit', handleSubmit);
  }
})();
