# -*- coding: utf-8 -*-
"""Shared provider HTTP error parsing and safe Chinese error mapping."""
from __future__ import absolute_import

import re

from .base import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUncertain,
    scrub_secret,
)

_REQUEST_ID_RE = re.compile(
    r"(?i)\brequest[\s_-]*id\s*[:：]\s*([A-Za-z0-9._:-]{1,128})"
)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_REQUEST_ID_HEADERS = ("x-request-id", "x-ark-request-id", "x-tt-logid", "request-id")


def _json_payload(response):
    try:
        value = response.json()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _error_object(payload):
    error = payload.get("error")
    if isinstance(error, dict):
        return error
    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("error")
        if isinstance(nested, dict):
            return nested
    return {}


def _safe_request_id(value, min_length=1):
    value = str(value or "").strip()
    if len(value) < min_length:
        return None
    return value if _SAFE_ID_RE.match(value) else None


def extract_request_id(response, payload=None):
    headers = getattr(response, "headers", None) or {}
    lowered = {}
    try:
        lowered = {str(key).lower(): value for key, value in headers.items()}
    except Exception:
        lowered = {}
    for name in _REQUEST_ID_HEADERS:
        candidate = _safe_request_id(lowered.get(name))
        if candidate:
            return candidate
    payload = payload if isinstance(payload, dict) else _json_payload(response)
    error = _error_object(payload)
    candidate = _safe_request_id(
        error.get("request_id")
        or payload.get("request_id")
        or error.get("requestId")
    )
    if candidate:
        return candidate
    text = " ".join(
        str(value or "")
        for value in (error.get("message"), payload.get("message"), getattr(response, "text", ""))
    )
    match = _REQUEST_ID_RE.search(text)
    return _safe_request_id(match.group(1), min_length=8) if match else None


def _retry_after(response):
    headers = getattr(response, "headers", None) or {}
    try:
        lowered = {str(key).lower(): value for key, value in headers.items()}
    except Exception:
        return None
    raw = lowered.get("retry-after")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def extract_error_details(response, api_key):
    payload = _json_payload(response)
    error = _error_object(payload)
    upstream = error.get("message") or error.get("msg")
    if not upstream:
        upstream = payload.get("message") or getattr(response, "text", "") or ""
    upstream = scrub_secret(str(upstream)[:500], api_key)
    code = error.get("code") or error.get("type") or ""
    code = str(code).strip()[:120] or None
    return {
        "status_code": int(getattr(response, "status_code", 0) or 0),
        "provider_code": code,
        "request_id": extract_request_id(response, payload),
        "retry_after_s": _retry_after(response),
        "upstream_message": upstream,
    }


def _looks_like_model_not_activated(provider_code, message):
    text = "{0} {1}".format(provider_code or "", message or "").lower()
    markers = (
        "modelnotopen",
        "not activated",
        "activate the model",
        "model service is not activated",
        "模型未开通",
        "未开通该模型",
        "未开通",
    )
    return any(marker in text for marker in markers)


def _looks_like_model_not_found(provider_code, message):
    text = "{0} {1}".format(provider_code or "", message or "").lower()
    markers = (
        "modelnotfound",
        "invalidendpointormodel",
        "model not found",
        "does not exist",
        "model does not exist",
        "模型不存在",
        "无可用模型",
    )
    return any(marker in text for marker in markers)


def _with_request_id(message, request_id):
    if not request_id:
        return message
    return "{0}（请求 ID: {1}）".format(message, request_id)


def provider_http_error(response, api_key, provider_label, model_id=None,
                        uncertain_error_type="submission_uncertain"):
    """Build a mapped provider exception for a failed HTTP response.

    Returns ``None`` for successful (2xx) responses.  Adapters raise the
    returned exception themselves so their existing control flow stays intact.
    """
    details = extract_error_details(response, api_key)
    status = details["status_code"]
    if status < 300:
        return None
    provider_code = details["provider_code"]
    request_id = details["request_id"]
    upstream = details["upstream_message"]
    retry_after = details["retry_after_s"]
    kwargs = {
        "status_code": status,
        "provider_code": provider_code,
        "request_id": request_id,
        "model_id": model_id,
        "retry_after_s": retry_after,
    }

    if 300 <= status < 400:
        return ProviderRejected(
            "{0} 返回重定向（HTTP {1}），已拒绝跟随".format(provider_label, status),
            error_type="provider_redirect_rejected", **kwargs
        )
    # Ark reports an unactivated model as HTTP 404 with error.code
    # ModelNotOpen, so classify activation/model-ID errors before the generic
    # status mapping.
    if status in (400, 404):
        if _looks_like_model_not_activated(provider_code, upstream):
            message = (
                "{0} 账户未开通模型 {1}，请在火山方舟控制台开通该模型，"
                "或在生成页面改选已开通的模型后重试".format(
                    provider_label, model_id or "（当前配置）"
                )
            )
            if upstream:
                message += "；详情：{0}".format(upstream)
            return ProviderRejected(
                _with_request_id(message, request_id),
                error_type="model_not_activated", **kwargs
            )
        if _looks_like_model_not_found(provider_code, upstream):
            message = (
                "{0} 模型 ID 不存在或不可用：{1}，请检查方舟控制台模型 ID 与 "
                "Base URL 区域是否一致".format(provider_label, model_id or "（当前配置）")
            )
            if upstream:
                message += "；详情：{0}".format(upstream)
            return ProviderRejected(
                _with_request_id(message, request_id),
                error_type="model_not_found", **kwargs
            )
    if status == 400:
        message = "{0} 拒绝请求：{1}".format(
            provider_label, upstream or "HTTP 400"
        )
        return ProviderRejected(
            _with_request_id(message, request_id),
            error_type="provider_rejected", **kwargs
        )
    if status in (401, 403):
        if status == 401:
            message = "{0} API Key 无效或已过期（HTTP 401）".format(provider_label)
            error_type = "provider_auth_error"
        else:
            message = "{0} API Key 无权限访问该资源或账户受限（HTTP 403）".format(provider_label)
            error_type = "provider_permission_denied"
        if upstream:
            message += "；详情：{0}".format(upstream)
        return ProviderAuthError(
            _with_request_id(message, request_id),
            error_type=error_type, **kwargs
        )
    if status == 404:
        message = (
            "{0} 接口路径不存在（HTTP 404），请检查 Base URL 是否为 "
            "https://ark.cn-beijing.volces.com/api/v3".format(provider_label)
        )
        return ProviderRejected(
            _with_request_id(message, request_id),
            error_type="provider_endpoint_not_found", **kwargs
        )
    if status == 429:
        message = "{0} 请求过于频繁（HTTP 429）".format(provider_label)
        if retry_after is not None:
            message += "，请 {0} 秒后重试".format(retry_after)
        return ProviderRateLimited(
            _with_request_id(message, request_id),
            error_type="provider_rate_limited", **kwargs
        )
    if status >= 500:
        message = "{0} 服务暂时不可用（HTTP {1}），请稍后重试".format(
            provider_label, status
        )
        return ProviderUncertain(
            _with_request_id(message, request_id),
            error_type=uncertain_error_type, **kwargs
        )
    return ProviderRejected(
        _with_request_id(
            "{0} 返回未知状态（HTTP {1}）".format(provider_label, status),
            request_id,
        ),
        error_type="provider_rejected", **kwargs
    )
