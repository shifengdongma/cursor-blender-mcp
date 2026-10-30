# -*- coding: utf-8 -*-
"""Per-user AI provider credential HTTP API and the API settings page.

The credential service owns encryption and validation; this module is a thin
transport layer.  Keys are never returned, logged, or written to audit
metadata.
"""
from __future__ import absolute_import

from urllib.parse import urlparse

from flask import g, request, send_from_directory

from . import generation_models, model_ids
from .credential_service import CredentialError, CredentialService
from .http_utils import ApiError, parse_json_body
from .provider_connectivity import probe_credential
from .provider_test_generation import run_generation_test
from .rate_limiter import rate_limit
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

    def _https_required_response():
        if not getattr(cfg, "CREDENTIAL_REQUIRE_HTTPS", False):
            return None
        if request.is_secure:
            return None
        return json_error(
            "https_required",
            "API Key 只能通过 HTTPS 传输；请使用 HTTPS 访问，或在反向代理中设置 "
            "X-Forwarded-Proto 并启用 TRUST_PROXY",
            status_code=403,
        )

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
        generation_models_catalog = generation_models.list_models(
            cfg, include_unavailable=True, user=_current_user()
        )
        return json_success(
            {
                "items": items,
                "catalog": catalog,
                "generation_models": generation_models_catalog,
            }
        )

    @app.route("/api/user/provider-credentials/<provider>", methods=["PUT"])
    def update_provider_credential(provider):
        blocked = _https_required_response()
        if blocked:
            return blocked
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
        blocked = _https_required_response()
        if blocked:
            return blocked
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

    def _probe_model_id(provider, effective, user):
        if provider == "ark":
            item = generation_models.get_model(
                cfg, model_ids.ARK_IMAGE_DEFAULT_KEY, user=user
            )
            return (item or {}).get("model_id")
        return effective.get("model")

    def _audit_test(user, provider, result, base_url=None, metadata=None):
        audit_metadata = _credential_metadata(provider, base_url)
        if metadata:
            audit_metadata.update(metadata)
        _audit(
            cfg, "provider_credential_test", user,
            target_type="provider_credential", target_id=provider,
            result=result, metadata=audit_metadata,
        )

    @app.route("/api/user/provider-credentials/<provider>/test", methods=["POST"])
    def test_provider_credential(provider):
        blocked = _https_required_response()
        if blocked:
            return blocked
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

        model_id = _probe_model_id(provider, effective, user)
        result = probe_credential(provider, base_url, api_key, model_id=model_id)
        if result.get("verified"):
            last_verified_at = service.mark_verified(user.get("id"), provider)
        else:
            row = service.get_record(user.get("id"), provider)
            last_verified_at = row.get("last_verified_at") if row else None
        result["last_verified_at"] = last_verified_at

        key_status = (result.get("key") or {}).get("status")
        if result.get("verified"):
            audit_result = "success"
        elif not result.get("reachable") or key_status == "rejected":
            audit_result = "failed"
        else:
            audit_result = "inconclusive"
        _audit_test(
            user, provider, audit_result, base_url,
            metadata={
                "network_status": (result.get("network") or {}).get("status_code"),
                "key_status": key_status,
                "model_status": (result.get("model") or {}).get("status"),
                "model_id": (result.get("model") or {}).get("model_id"),
                "provider_code": (result.get("key") or {}).get("provider_code"),
                "provider_request_id": (result.get("key") or {}).get("provider_request_id"),
            },
        )
        return json_success(result)

    @app.route(
        "/api/user/provider-credentials/<provider>/test-generation",
        methods=["POST"],
    )
    @rate_limit(max_requests=5, window_s=60)
    def test_provider_generation(provider):
        blocked = _https_required_response()
        if blocked:
            return blocked
        user = _current_user()
        body = parse_json_body(request)
        if body.get("confirm_billing") is not True:
            return json_error(
                "billing_confirmation_required",
                "真实调用会向第三方服务商发起付费请求，可能产生费用；"
                "请确认后携带 confirm_billing=true 再试",
                status_code=400,
            )
        model_key = body.get("model_key")
        if not isinstance(model_key, str) or not model_key.strip():
            return json_error("invalid_model", "缺少 model_key", status_code=400)
        try:
            result = run_generation_test(
                cfg, user, provider, model_key.strip(), service
            )
        except ApiError as exc:
            _audit(
                cfg, "provider_credential_test_generation", user,
                target_type="provider_credential", target_id=provider,
                result="failed",
                metadata={
                    "model_key": model_key,
                    "error_code": exc.code,
                    "cost_acknowledged": True,
                },
            )
            return json_error(exc.code, exc.message, status_code=exc.status_code,
                              details=exc.details)
        except CredentialError as exc:
            _audit(
                cfg, "provider_credential_test_generation", user,
                target_type="provider_credential", target_id=provider,
                result="failed",
                metadata={
                    "model_key": model_key,
                    "error_code": exc.code,
                    "cost_acknowledged": True,
                },
            )
            return json_error(exc.code, exc.message, status_code=exc.status_code,
                              details=exc.details)

        success = result.get("status") in ("succeeded", "accepted")
        _audit(
            cfg, "provider_credential_test_generation", user,
            target_type="provider_credential", target_id=provider,
            result="success" if success else "failed",
            metadata={
                "model_key": result.get("model_key"),
                "model_id": result.get("model_id"),
                "status": result.get("status"),
                "error_code": result.get("error_code"),
                "provider_code": result.get("provider_code"),
                "provider_request_id": result.get("provider_request_id"),
                "cost_acknowledged": True,
            },
        )
        return json_success(result)
