# -*- coding: utf-8 -*-
"""Per-user AI provider credential HTTP API and the API settings page.

The credential service owns encryption and validation; this module is a thin
transport layer.  Keys are never returned, logged, or written to audit
metadata.
"""
from __future__ import absolute_import

from urllib.parse import urlparse

import requests
from flask import g, request, send_from_directory

from .credential_service import CredentialError, CredentialService
from .http_utils import parse_json_body

_TEST_TIMEOUT = (3, 8)
_ACTIVE_TASK_MESSAGE = "该 Provider 还有排队或运行中的任务，请等待任务结束或取消后再修改"

_UPDATE_FIELDS = (
    "api_key",
    "base_url",
    "model",
    "model_overrides",
    "is_active",
    "clear_key",
)


def _audit(cfg, action, user, target_type=None, target_id=None, result="success", metadata=None):
    if not getattr(cfg, "AUDIT_ENABLED", True):
        return None
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=(user or {}).get("id"),
            tenant_id=(user or {}).get("tenant_id"),
            project_id=None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            metadata=metadata,
            request_id=getattr(g, "request_id", None),
        )
    except Exception:
        pass


def _credential_metadata(provider, base_url=None):
    """Audit metadata for credential events: provider/base_url/host only."""
    metadata = {"provider": provider}
    if base_url:
        metadata["base_url"] = base_url
        try:
            metadata["host"] = urlparse(base_url).hostname
        except ValueError:
            metadata["host"] = None
    return metadata


def register_provider_routes(app, cfg, web_root, json_success, json_error):
    service = CredentialService(cfg.DATA_DIR, cfg)

    def _current_user():
        return getattr(g, "current_user", None) or {}

    @app.route("/api-settings", methods=["GET"])
    def api_settings_page():
        return send_from_directory(web_root, "api-settings.html")

    @app.route("/api/user/provider-credentials", methods=["GET"])
    def list_provider_credentials():
        catalog = service.catalog(cfg)
        platform_available = {
            entry.get("provider"): bool(entry.get("platform_available"))
            for entry in catalog
        }
        items = []
        for record in service.list_public(_current_user().get("id"), cfg):
            item = dict(record)
            item["platform_available"] = platform_available.get(item.get("provider"), False)
            items.append(item)
        return json_success({"items": items, "catalog": catalog})

    @app.route("/api/user/provider-credentials/<provider>", methods=["PUT"])
    def update_provider_credential(provider):
        user = _current_user()
        body = parse_json_body(request)
        payload = {key: body.get(key) for key in _UPDATE_FIELDS if key in body}
        try:
            if service.has_active_tasks(user.get("id"), provider):
                return json_error("active_tasks", _ACTIVE_TASK_MESSAGE, status_code=409)
            record = service.upsert(
                user.get("id"),
                user.get("tenant_id"),
                provider,
                **payload
            )
        except CredentialError as exc:
            _audit(
                cfg, "provider_credential_update", user,
                target_type="provider_credential", target_id=provider,
                result="failed", metadata=_credential_metadata(provider),
            )
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(
            cfg, "provider_credential_update", user,
            target_type="provider_credential", target_id=provider,
            metadata=_credential_metadata(provider, (record or {}).get("base_url")),
        )
        return json_success(record, message="API 配置已保存")

    @app.route("/api/user/provider-credentials/<provider>", methods=["DELETE"])
    def delete_provider_credential(provider):
        user = _current_user()
        try:
            if service.has_active_tasks(user.get("id"), provider):
                return json_error("active_tasks", _ACTIVE_TASK_MESSAGE, status_code=409)
            deleted = service.delete(user.get("id"), provider)
        except CredentialError as exc:
            _audit(
                cfg, "provider_credential_delete", user,
                target_type="provider_credential", target_id=provider,
                result="failed", metadata=_credential_metadata(provider),
            )
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(
            cfg, "provider_credential_delete", user,
            target_type="provider_credential", target_id=provider,
            metadata=_credential_metadata(provider),
        )
        return json_success(
            {"deleted": bool(deleted), "provider": provider},
            message="个人 API 配置已删除，将回退平台默认" if deleted else "没有可删除的个人配置",
        )

    def _run_reachability_check(provider, base_url, api_key):
        headers = {
            "Authorization": "Bearer {0}".format(api_key),
            "Accept": "application/json",
        }
        try:
            if provider == "llm":
                response = requests.get(
                    base_url + "/models",
                    headers=headers,
                    timeout=_TEST_TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                )
                status = response.status_code
                response.close()
                if status == 200:
                    return True, True, "连接成功，密钥验证通过"
                if status in (401, 403):
                    return True, False, "API 端点可达，但密钥未通过鉴权（HTTP {0}）".format(status)
                return (
                    True,
                    False,
                    "API 端点可达（HTTP {0}），该服务可能不支持 /models 接口；已完成可达性检查，未发起计费调用".format(status),
                )
            response = requests.head(
                base_url,
                headers=headers,
                timeout=_TEST_TIMEOUT,
                allow_redirects=False,
            )
            status = response.status_code
            response.close()
            if status in (401, 403):
                return True, False, "API 端点可达，但密钥未通过鉴权（HTTP {0}）".format(status)
            return True, False, "API 端点可达（HTTP {0}），未发起生成请求".format(status)
        except requests.RequestException:
            return False, False, "无法连接到该 API 端点，请检查 Base URL 或网络。"

    def _audit_test(user, provider, result, base_url=None):
        _audit(
            cfg, "provider_credential_test", user,
            target_type="provider_credential", target_id=provider,
            result=result, metadata=_credential_metadata(provider, base_url),
        )

    @app.route("/api/user/provider-credentials/<provider>/test", methods=["POST"])
    def test_provider_credential(provider):
        user = _current_user()
        try:
            effective = service.effective(user.get("id"), provider, cfg)
        except CredentialError as exc:
            _audit_test(user, provider, "failed")
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        if effective.get("error") == "credential_unreadable":
            _audit_test(user, provider, "failed")
            return json_error(
                "provider_not_configured",
                "API 密钥无法解密，请在 API 配置页重新保存后再测试",
                status_code=400,
            )
        api_key = effective.get("api_key") or ""
        if not effective.get("source") or not api_key:
            _audit_test(user, provider, "failed")
            return json_error("provider_not_configured", "该 Provider 尚未配置 API Key", status_code=400)
        try:
            # Re-resolve immediately before the outbound request to narrow the
            # DNS-rebinding window between save-time and test-time validation.
            base_url = service.validate_base_url(effective.get("base_url"), cfg)
        except CredentialError as exc:
            _audit_test(user, provider, "failed", effective.get("base_url"))
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)

        reachable, verified, message = _run_reachability_check(provider, base_url, api_key)
        _audit_test(user, provider, "success" if reachable else "failed", base_url)
        return json_success(
            {
                "provider": provider,
                "reachable": reachable,
                "verified": verified,
                "message": message,
            }
        )
