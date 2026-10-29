# -*- coding: utf-8 -*-
"""Encrypted per-user AI provider credentials.

Keys are encrypted with Fernet before they touch SQLite.  Public helpers
never return plaintext key material; ``effective`` is the only place that
decrypts, and callers must not log its result.
"""
from __future__ import absolute_import

import base64
import copy
import hashlib
import ipaddress
import json
import logging
import os
import socket
import time
import uuid
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from .database import get_database

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {
    "", "placeholder", "your_api_key", "your-api-key", "your key",
    "changeme", "change-me", "none", "null",
}

_PROVIDER_NAMES = {
    "llm": "大语言模型",
    "ark": "火山方舟",
    "openai_image": "OpenAI 图片",
    "atlas_seedance": "Atlas Cloud Seedance",
    "luma": "Luma Dream Machine",
}

_LENGTH_LIMITS = {"api_key": 4096, "base_url": 512, "model": 256}


def _now():
    return int(time.time())


def _key_present(value):
    if not isinstance(value, str):
        return False
    return value.strip().lower() not in _PLACEHOLDER_VALUES


class CredentialError(RuntimeError):
    """Credential/configuration failure with an API-safe code."""

    def __init__(self, code, message, status_code=400, details=None):
        RuntimeError.__init__(self, message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


PROVIDER_CATALOG = [
    {
        "provider": "llm",
        "name": "大语言模型（OpenAI 兼容）",
        "protocol": "openai_compatible",
        "description": "用于分镜分析、脚本生成。支持 OpenAI、DeepSeek、通义千问、Kimi、智谱等兼容 /chat/completions 的服务。",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "requires_key": True,
        "docs_url": "https://platform.openai.com/api-keys",
        "presets": [
            {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"},
            {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
            {"label": "通义千问（兼容模式）", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
            {"label": "Moonshot / Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
            {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-plus"},
        ],
    },
    {
        "provider": "ark",
        "name": "火山方舟（Seedream / Seedance）",
        "protocol": "volcengine_ark",
        "description": "图片使用 Seedream，视频使用 Seedance。模型 ID 需与方舟控制台已开通的模型一致。",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": None,
        "requires_key": True,
        "docs_url": "https://console.volcengine.com/ark",
        "model_fields": [
            {"key": "ark_seedream_pro", "label": "Seedream Pro 模型 ID", "default": "doubao-seedream-5-0-pro-260628"},
            {"key": "ark_seedream_lite", "label": "Seedream Lite 模型 ID", "default": "doubao-seedream-5-0-lite-260128"},
            {"key": "ark_seedance_25", "label": "Seedance 2.5 模型 ID", "default": "doubao-seedance-2-5-260628"},
            {"key": "ark_seedance_20", "label": "Seedance 2.0 模型 ID", "default": "doubao-seedance-2-0-260128"},
            {"key": "ark_seedance_10_pro", "label": "Seedance 1.0 Pro 模型 ID", "default": "doubao-seedance-1-0-pro-250528"},
        ],
    },
    {
        "provider": "openai_image",
        "name": "OpenAI 图片",
        "protocol": "openai_images",
        "description": "OpenAI Images API（gpt-image-1 / DALL·E）。",
        "default_base_url": "https://api.openai.com/v1",
        "default_model": "gpt-image-1",
        "requires_key": True,
        "docs_url": "https://platform.openai.com/docs/guides/images",
    },
    {
        "provider": "atlas_seedance",
        "name": "Atlas Cloud Seedance",
        "protocol": "atlas_seedance",
        "description": "旧版 Atlas Cloud 兼容通道，仅视频。",
        "default_base_url": "https://api.atlascloud.ai/api/v1",
        "default_model": "bytedance/seedance-v1.5-pro/text-to-video",
        "requires_key": True,
        "docs_url": "https://atlascloud.ai",
    },
    {
        "provider": "luma",
        "name": "Luma Dream Machine",
        "protocol": "luma",
        "description": "Luma 视频生成通道。",
        "default_base_url": "https://api.lumalabs.ai/dream-machine/v1",
        "default_model": "ray-2",
        "requires_key": True,
        "docs_url": "https://lumalabs.ai/dream-machine",
    },
]

_CATALOG_BY_PROVIDER = {item["provider"]: item for item in PROVIDER_CATALOG}


class CredentialService(object):
    def __init__(self, data_dir=None, config=None):
        self.config = config
        self.data_dir = (
            data_dir
            or getattr(config, "DATA_DIR", None)
            or os.environ.get("DATA_DIR", "./data")
        )
        self.db = get_database(os.path.join(self.data_dir, "aigv.db"))

    # ── Configuration helpers ──

    def _config(self, cfg=None):
        if cfg is not None:
            return cfg
        if self.config is not None:
            return self.config
        from .config import Config
        return Config()

    def _fernet(self, cfg):
        raw = (
            getattr(cfg, "CREDENTIAL_ENCRYPTION_KEY", "")
            or getattr(cfg, "SECRET_KEY", "")
            or ""
        ).encode("utf-8")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))

    def _encrypt(self, value, cfg):
        return "v1:" + self._fernet(cfg).encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt(self, token, cfg):
        if not token:
            return None, None
        try:
            value = token[3:] if token.startswith("v1:") else token
            return self._fernet(cfg).decrypt(value.encode("ascii")).decode("utf-8"), None
        except (InvalidToken, ValueError, TypeError, UnicodeError):
            logger.warning("Provider credential decryption failed; credential must be re-saved")
            return None, "credential_unreadable"

    @staticmethod
    def _normalise_base_url(value):
        if value is None:
            return None
        value = str(value).strip()
        return value.rstrip("/") or None

    def _platform_credentials(self, provider, cfg):
        if provider == "llm":
            key, base_url, model = cfg.LLM_API_KEY, cfg.LLM_BASE_URL, cfg.LLM_MODEL_NAME
        elif provider == "ark":
            key, base_url, model = cfg.ARK_API_KEY, cfg.ARK_BASE_URL, None
        elif provider == "openai_image":
            key = getattr(cfg, "OPENAI_API_KEY", "")
            base_url = getattr(cfg, "OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = getattr(cfg, "OPENAI_IMAGE_MODEL", "gpt-image-1")
        elif provider == "atlas_seedance":
            key, base_url, model = cfg.SEEDANCE_API_KEY, cfg.SEEDANCE_BASE_URL, cfg.SEEDANCE_MODEL_NAME
        elif provider == "luma":
            key = cfg.LUMA_API_KEY
            base_url = cfg.LUMA_BASE_URL
            model = getattr(cfg, "LUMA_MODEL_NAME", "ray-2")
        else:
            raise CredentialError("invalid_provider", "不支持的 Provider: {0}".format(provider), 400)

        return {
            "api_key": key if _key_present(key) else "",
            "base_url": self._normalise_base_url(base_url) or "",
            "model": model or None,
            "model_overrides": {},
            "source": "platform" if _key_present(key) else None,
            "credential_id": None,
        }

    # ── Validation ──

    def validate_base_url(self, url, cfg=None, resolver=None):
        cfg = self._config(cfg)
        raw = (url or "").strip()
        if not raw:
            raise CredentialError("invalid_base_url", "Base URL 不能为空", 400)
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        allow_http = bool(getattr(cfg, "ALLOW_INSECURE_PROVIDER_URLS", False))
        if scheme != "https" and not (allow_http and scheme == "http"):
            raise CredentialError("invalid_base_url", "Base URL 必须使用 HTTPS", 400)
        if parsed.username or parsed.password or parsed.fragment:
            raise CredentialError("invalid_base_url", "Base URL 不能包含用户信息或片段", 400)
        host = parsed.hostname
        if not host:
            raise CredentialError("invalid_base_url", "Base URL 缺少主机名", 400)
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError:
            raise CredentialError("invalid_base_url", "Base URL 端口无效", 400)

        addresses = []
        try:
            addresses.append(ipaddress.ip_address(host.split("%")[0]))
        except ValueError:
            resolve = resolver or socket.getaddrinfo
            try:
                infos = resolve(host, port, type=socket.SOCK_STREAM)
            except OSError:
                raise CredentialError("invalid_base_url", "Base URL 主机无法解析", 400)
            for info in infos:
                try:
                    addresses.append(ipaddress.ip_address(str(info[4][0]).split("%")[0]))
                except (ValueError, IndexError):
                    continue
        if not addresses:
            raise CredentialError("invalid_base_url", "Base URL 主机无法解析", 400)
        if not all(address.is_global for address in addresses):
            raise CredentialError("invalid_base_url", "Base URL 不能指向内网、回环或保留地址", 400)
        return self._normalise_base_url(raw)

    # ── CRUD ──

    def get_record(self, user_id, provider):
        if not user_id:
            return None
        return self.db.fetch_one(
            "SELECT * FROM provider_credentials WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )

    def _validate_provider(self, provider):
        if provider not in _CATALOG_BY_PROVIDER:
            raise CredentialError("invalid_provider", "不支持的 Provider: {0}".format(provider), 400)

    def _validate_model_overrides(self, overrides):
        if overrides is None:
            return None
        if not isinstance(overrides, dict):
            raise CredentialError("invalid_model_overrides", "model_overrides 必须是对象", 400)
        cleaned = {}
        for key, value in overrides.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise CredentialError("invalid_model_overrides", "model_overrides 的键和值必须是字符串", 400)
            key = key.strip()
            value = value.strip()
            if not key or len(key) > 80 or len(value) > _LENGTH_LIMITS["model"]:
                raise CredentialError("invalid_model_overrides", "model_overrides 内容不合法", 400)
            if value:
                cleaned[key] = value
        return cleaned

    def upsert(self, user_id, tenant_id, provider, api_key=None, base_url=None,
               model=None, model_overrides=None, is_active=None, clear_key=False):
        self._validate_provider(provider)
        cfg = self._config()
        existing = self.get_record(user_id, provider)

        if clear_key:
            ciphertext = None
        elif api_key is not None and str(api_key).strip():
            key_value = str(api_key).strip()
            if len(key_value) > _LENGTH_LIMITS["api_key"]:
                raise CredentialError("invalid_api_key", "API Key 过长", 400)
            if _key_present(key_value):
                ciphertext = self._encrypt(key_value, cfg)
            else:
                # 占位符一律视为未配置：等同未提交 api_key，保留已有密钥。
                ciphertext = existing.get("api_key_ciphertext") if existing else None
        elif existing:
            ciphertext = existing.get("api_key_ciphertext")
        else:
            ciphertext = None

        if base_url is None:
            final_base_url = existing.get("base_url") if existing else None
        else:
            final_base_url = self._normalise_base_url(base_url)
            if final_base_url:
                final_base_url = self.validate_base_url(final_base_url, cfg)

        if model is None:
            final_model = existing.get("model") if existing else None
        else:
            final_model = str(model).strip() or None
            if final_model and len(final_model) > _LENGTH_LIMITS["model"]:
                raise CredentialError("invalid_model", "模型 ID 过长", 400)

        if model_overrides is None:
            final_overrides = existing.get("model_overrides") if existing else "{}"
        else:
            cleaned = self._validate_model_overrides(model_overrides) or {}
            final_overrides = json.dumps(cleaned, ensure_ascii=False, sort_keys=True)

        if is_active is None:
            final_active = int(existing.get("is_active", 1)) if existing else 1
        else:
            final_active = 1 if is_active else 0

        user_key, _ = self._decrypt(ciphertext, cfg) if ciphertext else (None, None)
        if not _key_present(user_key):
            user_key = None
        platform = self._platform_credentials(provider, cfg)
        if final_base_url and final_base_url != platform.get("base_url"):
            if not user_key:
                raise CredentialError(
                    "user_key_required",
                    "自定义 Base URL 时必须同时填写你自己的 API Key",
                    400,
                )

        now = _now()
        data = {
            "tenant_id": tenant_id,
            "base_url": final_base_url,
            "model": final_model,
            "api_key_ciphertext": ciphertext,
            "model_overrides": final_overrides,
            "is_active": final_active,
            "updated_at": now,
        }
        if existing:
            self.db.update(
                "provider_credentials",
                data,
                "user_id = ? AND provider = ?",
                (user_id, provider),
            )
            credential_id = existing["id"]
        else:
            credential_id = uuid.uuid4().hex
            data.update(
                {
                    "id": credential_id,
                    "user_id": user_id,
                    "provider": provider,
                    "created_at": now,
                }
            )
            self.db.insert("provider_credentials", data)
        return self._public_record(self.get_record(user_id, provider), cfg)

    def delete(self, user_id, provider):
        self._validate_provider(provider)
        return self.db.delete(
            "provider_credentials",
            "user_id = ? AND provider = ?",
            (user_id, provider),
        ) > 0

    # ── Resolution ──

    def effective(self, user_id, provider, cfg=None, prefer_source=None):
        cfg = self._config(cfg)
        platform = self._platform_credentials(provider, cfg)

        if prefer_source == "platform":
            return platform

        row = self.get_record(user_id, provider) if user_id else None
        if not row or not int(row.get("is_active", 1)):
            if prefer_source == "user":
                return {
                    "api_key": "",
                    "base_url": "",
                    "model": None,
                    "model_overrides": {},
                    "source": None,
                    "credential_id": None,
                }
            return platform

        user_key, decrypt_error = self._decrypt(row.get("api_key_ciphertext"), cfg)
        if not _key_present(user_key):
            user_key = None
        try:
            overrides = json.loads(row.get("model_overrides") or "{}")
        except (ValueError, TypeError):
            overrides = {}
        user_base_url = row.get("base_url") or None
        final_base_url = user_base_url or platform.get("base_url") or ""
        final_model = row.get("model") or platform.get("model")

        if decrypt_error:
            return {
                "api_key": "",
                "base_url": final_base_url,
                "model": final_model,
                "model_overrides": overrides,
                "source": None,
                "credential_id": row.get("id"),
                "error": decrypt_error,
            }

        if user_base_url and user_base_url != platform.get("base_url") and not user_key:
            raise CredentialError(
                "user_key_required",
                "自定义 Base URL 时必须同时填写你自己的 API Key",
                400,
            )

        api_key = user_key or platform.get("api_key") or ""
        source = "user" if user_key else ("platform" if platform.get("api_key") else None)
        if prefer_source == "user" and not user_key:
            source = None
            api_key = ""
        return {
            "api_key": api_key,
            "base_url": final_base_url,
            "model": final_model,
            "model_overrides": overrides,
            "source": source,
            "credential_id": row.get("id"),
        }

    def has_provider(self, user_id, provider, cfg=None):
        try:
            effective = self.effective(user_id, provider, cfg)
        except CredentialError as exc:
            return False, exc.message
        if effective.get("error") == "credential_unreadable":
            return False, "API 密钥无法解密，请在 API 配置页重新保存"
        if effective.get("source"):
            return True, None
        name = _PROVIDER_NAMES.get(provider, provider)
        return False, "请在 API 配置页填写 {0} 密钥".format(name)

    def has_llm(self, user_id, cfg=None):
        return self.has_provider(user_id, "llm", cfg)

    def has_active_tasks(self, user_id, provider):
        if not user_id:
            return False
        if provider == "llm":
            condition = "task_type = 'storyboard'"
            params = ()
        elif provider == "ark":
            condition = "provider IN ('ark_seedream', 'ark_seedance')"
            params = ()
        else:
            condition = "provider = ?"
            params = (provider,)
        row = self.db.fetch_one(
            "SELECT COUNT(*) AS total FROM generation_tasks "
            "WHERE created_by = ? AND status IN ('queued', 'submitting', 'running') "
            "AND " + condition,
            (user_id,) + params,
        )
        return bool(row and int(row.get("total") or 0) > 0)

    # ── Public serialisation ──

    @staticmethod
    def _load_overrides(value):
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _public_record(self, row, cfg):
        if not row:
            return None
        cfg = self._config(cfg)
        user_key, decrypt_error = self._decrypt(row.get("api_key_ciphertext"), cfg)
        if decrypt_error:
            stored_key = bool(row.get("api_key_ciphertext"))
        else:
            stored_key = _key_present(user_key)
        try:
            source = self.effective(row["user_id"], row["provider"], cfg).get("source")
        except CredentialError:
            source = None
        return {
            "provider": row.get("provider"),
            "base_url": row.get("base_url"),
            "model": row.get("model"),
            "model_overrides": self._load_overrides(row.get("model_overrides")),
            "has_key": stored_key,
            "key_last4": (user_key[-4:] if _key_present(user_key) else None),
            "key_unreadable": bool(decrypt_error),
            "source": source,
            "is_active": bool(row.get("is_active", 1)),
            "last_verified_at": row.get("last_verified_at"),
            "updated_at": row.get("updated_at"),
        }

    def list_public(self, user_id, cfg=None):
        rows = self.db.fetch_all(
            "SELECT * FROM provider_credentials WHERE user_id = ? ORDER BY provider",
            (user_id,),
        )
        return [self._public_record(row, cfg) for row in rows]

    def catalog(self, cfg=None):
        cfg = self._config(cfg)
        items = copy.deepcopy(PROVIDER_CATALOG)
        for item in items:
            try:
                platform = self._platform_credentials(item["provider"], cfg)
                item["platform_available"] = bool(platform.get("api_key"))
            except CredentialError:
                item["platform_available"] = False
        return items
