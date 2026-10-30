# -*- coding: utf-8 -*-
"""Non-billing provider connectivity probes.

The probe distinguishes three independent facts:

* network reachability (an HTTP response was received),
* key authentication (the service accepted the bearer token),
* model availability (only a real generation call can prove this).

A 200 response is treated as key verification only when it contains a
recognisable model list.  Anything else is explicitly reported as
"无法通过此方式验证".
"""
from __future__ import absolute_import

import requests

from .providers.errors import extract_error_details

_PROVIDERS_WITH_MODELS = {"llm", "ark", "openai_image"}
_NETWORK_ONLY_PROVIDERS = {"atlas_seedance", "luma"}
_PROVIDER_LABELS = {
    "llm": "大语言模型接口",
    "ark": "火山方舟",
    "openai_image": "OpenAI 图片接口",
    "atlas_seedance": "Atlas Cloud",
    "luma": "Luma",
}
_DEFAULT_TIMEOUT = (3, 8)


def _extract_model_ids(payload):
    items = None
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("data", "models", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
            if isinstance(value, dict):
                nested = value.get("items") or value.get("data")
                if isinstance(nested, list):
                    items = nested
                    break
    if not isinstance(items, list):
        return None
    model_ids = []
    for item in items:
        if isinstance(item, str) and item.strip():
            model_ids.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        value = item.get("id") or item.get("model") or item.get("name")
        if isinstance(value, dict):
            value = value.get("id")
        if isinstance(value, str) and value.strip():
            model_ids.append(value.strip())
    return model_ids or None


def _base_result(provider, base_url):
    return {
        "provider": provider,
        "base_url": base_url,
        "network": {
            "reachable": False,
            "status_code": None,
            "message": "尚未发起请求",
        },
        "key": {
            "status": "unknown",
            "provider_code": None,
            "provider_request_id": None,
            "retry_after_s": None,
            "message": "未验证",
        },
        "model": {
            "status": "untested",
            "model_id": None,
            "listed": None,
            "message": "未进行真实调用，无法判断模型是否可调用",
        },
        "reachable": False,
        "verified": False,
        "message": "",
    }


def _network_only_probe(provider, base_url, timeout):
    result = _base_result(provider, base_url)
    label = _PROVIDER_LABELS.get(provider, provider)
    try:
        response = requests.get(
            base_url,
            headers={"Accept": "application/json"},
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException:
        result["network"]["message"] = "无法连接到该 API 端点，请检查 Base URL 或网络。"
        result["message"] = result["network"]["message"]
        return result
    status = int(getattr(response, "status_code", 0) or 0)
    result["network"].update({
        "reachable": True,
        "status_code": status,
        "message": "网络可达（HTTP {0}）".format(status),
    })
    result["reachable"] = True
    result["key"].update({
        "status": "unsupported",
        "message": "该服务未提供非计费密钥验证接口，无法通过此方式验证",
    })
    result["message"] = (
        "{0} 网络可达（HTTP {1}）；该服务未提供非计费密钥验证接口，"
        "无法通过此方式验证密钥。请使用“真实调用测试”确认模型可用性。"
    ).format(label, status)
    return result


def probe_credential(provider, base_url, api_key, model_id=None, timeout=None):
    """Probe a credential without generating billable content."""
    timeout = timeout or _DEFAULT_TIMEOUT
    base_url = (base_url or "").rstrip("/")
    provider = (provider or "").strip().lower()
    if provider in _NETWORK_ONLY_PROVIDERS or provider not in _PROVIDERS_WITH_MODELS:
        return _network_only_probe(provider, base_url, timeout)

    result = _base_result(provider, base_url)
    label = _PROVIDER_LABELS.get(provider, provider)
    result["model"]["model_id"] = model_id
    headers = {
        "Authorization": "Bearer {0}".format(api_key),
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            base_url + "/models",
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException:
        result["network"]["message"] = "无法连接到该 API 端点，请检查 Base URL 或网络。"
        result["message"] = result["network"]["message"]
        return result

    status = int(getattr(response, "status_code", 0) or 0)
    result["network"].update({
        "reachable": True,
        "status_code": status,
        "message": "API 端点可达（HTTP {0}）".format(status),
    })
    result["reachable"] = True
    details = extract_error_details(response, api_key)
    result["key"].update({
        "provider_code": details.get("provider_code"),
        "provider_request_id": details.get("request_id"),
        "retry_after_s": details.get("retry_after_s"),
    })

    if status == 200:
        try:
            payload = response.json()
        except Exception:
            payload = None
        model_ids = _extract_model_ids(payload)
        if model_ids:
            result["key"].update({
                "status": "verified",
                "message": "密钥鉴权通过（仅证明 Key 被接受）",
            })
            result["verified"] = True
            if model_id:
                listed = model_id in model_ids
                result["model"].update({
                    "status": "listed" if listed else "not_listed",
                    "listed": listed,
                    "message": (
                        "模型 ID 出现在可见模型列表中（不代表已开通）"
                        if listed
                        else "模型 ID 未出现在可见模型列表中；列表可能不完整，请用真实调用确认"
                    ),
                })
            else:
                result["model"]["message"] = "未指定模型，无法判断模型是否列出"
            result["message"] = (
                "密钥验证通过（仅证明鉴权成功，不代表模型可调用）；"
                "请使用“真实调用测试”验证具体模型是否开通。"
            )
            return result
        result["key"]["message"] = (
            "服务返回 HTTP 200，但响应不是可识别的模型列表，无法通过此方式验证"
        )
    elif status in (401, 403):
        result["key"].update({
            "status": "rejected",
            "message": (
                "API Key 无效或已过期（HTTP 401）"
                if status == 401
                else "API Key 无权限或账户受限（HTTP 403）"
            ),
        })
    elif status in (404, 405):
        result["key"].update({
            "status": "unsupported",
            "message": "该服务未提供可用的 /models 接口（HTTP {0}），无法通过此方式验证".format(status),
        })
    elif status == 429:
        retry_after = result["key"].get("retry_after_s")
        message = "请求被限流（HTTP 429），无法完成密钥验证"
        if retry_after is not None:
            message += "，请 {0} 秒后重试".format(retry_after)
        result["key"].update({"status": "unknown", "message": message})
    elif 300 <= status < 400:
        result["key"].update({
            "status": "unknown",
            "message": "端点返回重定向（HTTP {0}），已拒绝跟随，无法通过此方式验证".format(status),
        })
    elif status >= 500:
        result["key"].update({
            "status": "unknown",
            "message": "服务端故障（HTTP {0}），无法完成密钥验证".format(status),
        })
    else:
        result["key"].update({
            "status": "unknown",
            "message": "服务返回 HTTP {0}，无法完成密钥验证".format(status),
        })

    result["message"] = "{0}：{1}".format(label, result["key"]["message"])
    if result["key"]["status"] == "unsupported":
        result["message"] += "。请使用“真实调用测试”确认模型可用性。"
    return result
