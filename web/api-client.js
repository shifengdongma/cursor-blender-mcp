(function (global) {
  'use strict';

  var AIGV = global.AIGV || {};
  var unsafeMethods = ['POST', 'PUT', 'PATCH', 'DELETE'];
  var csrfPromise = null;
  var currentUser = null;
  var runtime = global.AIGV_RUNTIME || { appEnv: 'development', demoMode: false, allowRegistration: true };

  function ApiError(message, status, code, details) {
    this.name = 'ApiError';
    this.message = message || '请求失败';
    this.status = status || 0;
    this.code = code || 'request_failed';
    this.details = details || null;
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  function isAuthPage() {
    return global.location.pathname === '/login' || global.location.pathname === '/register';
  }

  function loginRedirect() {
    var next = global.location.pathname + global.location.search;
    global.location.href = '/login?next=' + encodeURIComponent(next);
  }

  function parsePayload(response) {
    var contentType = response.headers.get('content-type') || '';
    if (contentType.indexOf('application/json') >= 0) {
      return response.json().catch(function () { return null; });
    }
    return response.text().then(function (text) {
      return { message: text };
    });
  }

  function ensureCsrf(force) {
    if (!force && AIGV._csrfToken) return Promise.resolve(AIGV._csrfToken);
    if (!force && csrfPromise) return csrfPromise;
    csrfPromise = fetch('/api/auth/csrf', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return parsePayload(response).then(function (payload) {
        if (!response.ok || !payload || payload.success === false || !payload.data) {
          throw new ApiError((payload && payload.message) || '无法获取 CSRF 令牌', response.status,
            (payload && payload.error) || 'csrf_unavailable');
        }
        AIGV._csrfToken = payload.data.csrf_token;
        return AIGV._csrfToken;
      });
    }).finally(function () { csrfPromise = null; });
    return csrfPromise;
  }

  function setCsrfToken(token) {
    AIGV._csrfToken = token || null;
  }

  function buildOptions(method, options) {
    options = options || {};
    var headers = Object.assign({ 'Accept': 'application/json' }, options.headers || {});
    var body = options.body;
    if (body !== undefined && body !== null && typeof body === 'object' &&
        !(global.FormData && body instanceof global.FormData) &&
        !(global.Blob && body instanceof global.Blob)) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    if (unsafeMethods.indexOf(method) >= 0 && AIGV._csrfToken) {
      headers['X-CSRF-Token'] = AIGV._csrfToken;
    }
    return {
      method: method,
      headers: headers,
      credentials: 'same-origin',
      body: body === undefined ? null : body
    };
  }

  async function api(path, options) {
    options = options || {};
    var method = (options.method || 'GET').toUpperCase();
    var unsafe = unsafeMethods.indexOf(method) >= 0;
    if (unsafe) await ensureCsrf(false);

    var response;
    try {
      response = await fetch(path, buildOptions(method, options));
    } catch (error) {
      throw new ApiError('网络连接失败，请稍后重试', 0, 'network_error');
    }
    var payload = await parsePayload(response);

    if (response.status === 403 && payload && payload.error === 'csrf_invalid' &&
        unsafe && !options._csrfRetried) {
      await ensureCsrf(true);
      return api(path, Object.assign({}, options, { _csrfRetried: true }));
    }

    if (response.status === 401 && !isAuthPage() && !options.noRedirect) {
      loginRedirect();
    }

    if (!response.ok || (payload && payload.success === false)) {
      throw new ApiError(
        (payload && (payload.message || payload.error)) || ('请求失败: ' + response.status),
        response.status,
        (payload && payload.error) || 'request_failed',
        payload && payload.details
      );
    }

    if (payload && typeof payload === 'object' && payload.success !== undefined) {
      return payload.data;
    }
    return payload;
  }

  function getCurrentUser(force) {
    if (currentUser && !force) return Promise.resolve(currentUser);
    return api('/api/auth/status', { noRedirect: true }).then(function (data) {
      currentUser = data && data.user ? data.user : null;
      if (currentUser) {
        currentUser.capabilities = (data && data.capabilities) || {};
      }
      return currentUser;
    });
  }

  function logout() {
    return api('/api/auth/logout', { method: 'POST' }).then(function () {
      setCsrfToken(null);
      currentUser = null;
      global.location.href = '/login';
    });
  }

  function formatTime(ts) {
    if (ts === null || ts === undefined || ts === '') return '—';
    var date = new Date(Number(ts) * 1000);
    if (isNaN(date.getTime())) return '—';
    try {
      return date.toLocaleString('zh-CN', { hour12: false });
    } catch (e) {
      return date.toISOString();
    }
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[ch];
    });
  }

  AIGV.ApiError = ApiError;
  AIGV.api = api;
  AIGV.ensureCsrf = ensureCsrf;
  AIGV.setCsrfToken = setCsrfToken;
  AIGV.getCurrentUser = getCurrentUser;
  AIGV.logout = logout;
  AIGV.formatTime = formatTime;
  AIGV.escapeHtml = escapeHtml;
  AIGV.runtime = runtime;
  AIGV.isAuthPage = isAuthPage;

  global.AIGV = AIGV;
})(window);
