# -*- coding: utf-8 -*-
"""Signed HTTP client and normalized errors for Volcengine OpenAPI."""
from __future__ import absolute_import

import json
import logging
import time

import requests

from .auth import _norm_query, sign_headers

logger = logging.getLogger(__name__)

ERROR_CATEGORIES = set([
    'unconfigured', 'disabled', 'unauthorized', 'no_permission',
    'throttled', 'invalid_param', 'network', 'invalid_response', 'sync_error',
])


class VolcengineAPIError(Exception):
    """A sanitized error from the Volcengine management API."""

    def __init__(self, category, message, code=None, status_code=None,
                 retryable=False, request_id=None):
        if category not in ERROR_CATEGORIES:
            category = 'sync_error'
        self.category = category
        self.code = str(code)[:120] if code else None
        self.status_code = status_code
        self.retryable = bool(retryable)
        self.request_id = str(request_id)[:120] if request_id else None
        super(VolcengineAPIError, self).__init__(str(message)[:500])

    def to_dict(self):
        return {
            'category': self.category,
            'code': self.code,
            'message': str(self)[:500],
            'status_code': self.status_code,
            'request_id': self.request_id,
        }


def _error_fields(payload):
    if not isinstance(payload, dict):
        return None, None, None
    metadata = payload.get('ResponseMetadata') or {}
    error = metadata.get('Error')
    if not isinstance(error, dict):
        error = payload.get('error') if isinstance(payload.get('error'), dict) else {}
    code = error.get('Code') or error.get('code') or payload.get('code')
    message = error.get('Message') or error.get('message') or payload.get('message')
    request_id = metadata.get('RequestId') or payload.get('request_id')
    if code or message:
        return code, message, request_id
    return None, None, request_id


def _categorize(status_code, code, message):
    text = '{0} {1}'.format(code or '', message or '').lower()
    if status_code == 401 or any(value in text for value in (
        'invalidauthorization', 'invalidaccesskey', 'signature', 'unauthorized',
        'invalidauthorization',
    )):
        return 'unauthorized'
    if status_code == 403 or any(value in text for value in (
        'accessdenied', 'forbidden', 'nopermission', 'no permission',
        'permission denied',
    )):
        return 'no_permission'
    if status_code == 429 or any(value in text for value in (
        'throttl', 'ratelimit', 'rate limit', 'toomanyrequests',
        'requestlimitexceeded', 'quota',
    )):
        return 'throttled'
    if 400 <= status_code < 500 or any(value in text for value in (
        'invalidparameter', 'missingparameter', 'requestinvalid',
        'invalidparameter',
    )):
        return 'invalid_param'
    return 'sync_error'


class VolcengineHTTPClient(object):
    """Small signed POST client with throttling and bounded retries.

    The client deliberately exposes no Authorization/AK/SK attributes in
    errors or logs.  Tests inject ``session``, ``sleeper`` and ``clock``.
    """

    def __init__(self, access_key, secret_key, timeout_s=20, max_retries=2,
                 session=None, sleeper=None, clock=None, qps_interval_s=0.25,
                 user_agent='AIGV-Studio/1.0'):
        self._access_key = access_key or ''
        self._secret_key = secret_key or ''
        self.timeout_s = max(5, int(timeout_s or 20))
        self.max_retries = max(0, int(max_retries or 0))
        self.session = session or requests.Session()
        self.sleeper = sleeper or time.sleep
        self.clock = clock or time.monotonic
        self.qps_interval_s = max(0.0, float(qps_interval_s or 0.0))
        self.user_agent = user_agent
        self._last_request_at = None

    def ensure_configured(self):
        if not self._access_key or not self._secret_key:
            raise VolcengineAPIError(
                'unconfigured',
                '未配置火山引擎管理 AK/SK，官方用量与账单不可用',
            )

    def _wait_for_slot(self):
        now = self.clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < self.qps_interval_s:
                self.sleeper(self.qps_interval_s - elapsed)
                now = self.clock()
        self._last_request_at = now

    def _retry_delay(self, attempt, response=None):
        retry_after = None
        if response is not None:
            try:
                retry_after = response.headers.get('Retry-After')
            except Exception:
                retry_after = None
        if retry_after:
            try:
                return max(0.0, min(30.0, float(retry_after)))
            except (TypeError, ValueError):
                pass
        return min(15.0, (attempt + 1) * 1.0)

    def post_json(self, host, action, version, body, region, service,
                  timeout_s=None, max_retries=None):
        """POST one OpenAPI action and return the parsed JSON payload."""
        self.ensure_configured()
        timeout_s = int(timeout_s or self.timeout_s)
        max_retries = self.max_retries if max_retries is None else max(0, int(max_retries))
        body_text = json.dumps(body or {}, ensure_ascii=False, separators=(',', ':'))
        query = {'Action': action, 'Version': version}
        url = 'https://{0}/?{1}'.format(host, _norm_query(query))

        last_error = None
        for attempt in range(max_retries + 1):
            headers = sign_headers(
                'POST', host, '/', query, body_text,
                self._access_key, self._secret_key, region, service,
            )
            headers['User-Agent'] = self.user_agent
            self._wait_for_slot()
            response = None
            try:
                response = self.session.post(
                    url, headers=headers, data=body_text.encode('utf-8'),
                    timeout=(5, timeout_s), allow_redirects=False,
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    raise VolcengineAPIError(
                        'invalid_response',
                        '火山引擎 OpenAPI 返回重定向，已拒绝跟随',
                        status_code=response.status_code,
                    )
                try:
                    payload = response.json() or {}
                except ValueError:
                    payload = {}
                code, message, request_id = _error_fields(payload)
                if response.status_code >= 400 or code:
                    category = _categorize(
                        response.status_code, code,
                        message or response.text[:300],
                    )
                    last_error = VolcengineAPIError(
                        category,
                        message or '火山引擎 OpenAPI 请求失败',
                        code=code,
                        status_code=response.status_code,
                        retryable=category in ('throttled', 'sync_error', 'network'),
                        request_id=request_id,
                    )
                    if last_error.retryable and attempt < max_retries:
                        self.sleeper(self._retry_delay(attempt, response))
                        continue
                    raise last_error
                if not isinstance(payload, dict):
                    raise VolcengineAPIError(
                        'invalid_response',
                        '火山引擎 OpenAPI 返回非对象 JSON',
                        status_code=response.status_code,
                    )
                return payload
            except VolcengineAPIError:
                raise
            except requests.exceptions.Timeout:
                last_error = VolcengineAPIError(
                    'network', '火山引擎 OpenAPI 请求超时', retryable=True
                )
                if attempt < max_retries:
                    self.sleeper(self._retry_delay(attempt))
                    continue
                raise last_error
            except requests.exceptions.ConnectionError as exc:
                last_error = VolcengineAPIError(
                    'network',
                    '火山引擎 OpenAPI 连接失败: {0}'.format(str(exc)[:200]),
                    retryable=True,
                )
                if attempt < max_retries:
                    self.sleeper(self._retry_delay(attempt))
                    continue
                raise last_error
            except requests.exceptions.RequestException as exc:
                last_error = VolcengineAPIError(
                    'network',
                    '火山引擎 OpenAPI 请求失败: {0}'.format(str(exc)[:200]),
                    retryable=True,
                )
                if attempt < max_retries:
                    self.sleeper(self._retry_delay(attempt))
                    continue
                raise last_error
        raise last_error or VolcengineAPIError('sync_error', '火山引擎 OpenAPI 请求失败')
