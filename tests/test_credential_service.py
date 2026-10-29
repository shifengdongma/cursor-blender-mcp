# -*- coding: utf-8 -*-
"""Per-user provider credential storage, encryption and resolution."""
from __future__ import absolute_import

import pytest

from backend.credential_service import CredentialError, CredentialService
from backend.task_service import get_task_service
from tests import support


def _service(app):
    cfg = app.config["AIGV_CONFIG"]
    return CredentialService(cfg.DATA_DIR, cfg), cfg


def test_roundtrip_encrypts_and_masks(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="creduser")

    svc.upsert(
        user["id"], user.get("tenant_id"), "llm",
        api_key="sk-secret-1234",
        base_url="https://93.184.216.34/v1",
        model="gpt-4o-mini",
    )

    row = svc.get_record(user["id"], "llm")
    assert row is not None
    assert "sk-secret-1234" not in row["api_key_ciphertext"]
    assert row["api_key_ciphertext"].startswith("v1:")

    public = svc.list_public(user["id"])[0]
    assert public["has_key"] is True
    assert public["key_last4"] == "1234"
    assert "api_key" not in public
    assert "api_key_ciphertext" not in public

    effective = svc.effective(user["id"], "llm", cfg)
    assert effective["api_key"] == "sk-secret-1234"
    assert effective["base_url"] == "https://93.184.216.34/v1"
    assert effective["model"] == "gpt-4o-mini"
    assert effective["source"] == "user"
    assert effective["credential_id"] == row["id"]


def test_upsert_preserves_key_when_omitted(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credkeep")

    svc.upsert(user["id"], user.get("tenant_id"), "llm", api_key="sk-keep-5678")
    svc.upsert(user["id"], user.get("tenant_id"), "llm", model="gpt-4o-mini")

    effective = svc.effective(user["id"], "llm", cfg)
    assert effective["api_key"] == "sk-keep-5678"
    assert effective["model"] == "gpt-4o-mini"


def test_custom_base_url_requires_user_key(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="crednokey")

    with pytest.raises(CredentialError) as exc:
        svc.upsert(
            user["id"], user.get("tenant_id"), "llm",
            base_url="https://93.184.216.34/v1",
        )
    assert exc.value.code == "user_key_required"
    assert exc.value.status_code == 400


def test_user_isolation_and_placeholder(app):
    svc, cfg = _service(app)
    user_a = support.create_admin(cfg.DATA_DIR, username="creda", email="creda@example.com")
    user_b = support.create_admin(cfg.DATA_DIR, username="credb", email="credb@example.com")

    svc.upsert(user_a["id"], user_a.get("tenant_id"), "llm", api_key="sk-a-0001")
    assert svc.effective(user_b["id"], "llm", cfg)["source"] is None

    cfg.LLM_API_KEY = "placeholder"
    assert svc.effective(user_b["id"], "llm", cfg)["source"] is None

    cfg.LLM_API_KEY = "platform-key"
    platform = svc.effective(user_b["id"], "llm", cfg)
    assert platform["api_key"] == "platform-key"
    assert platform["source"] == "platform"


@pytest.mark.parametrize(
    "placeholder",
    [
        "", "placeholder", " placeholder ", "PLACEHOLDER", "your_api_key",
        "your-api-key", "your key", "changeme", "change-me", "none", "null",
    ],
)
def test_user_supplied_placeholder_key_is_unconfigured(app, placeholder):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credplaceholder")
    cfg.LLM_API_KEY = "platform-key"

    svc.upsert(user["id"], user.get("tenant_id"), "llm", api_key=placeholder)

    row = svc.get_record(user["id"], "llm")
    assert row is not None
    assert row["api_key_ciphertext"] is None

    public = svc.list_public(user["id"], cfg)[0]
    assert public["has_key"] is False
    assert public["key_last4"] is None

    effective = svc.effective(user["id"], "llm", cfg)
    assert effective["api_key"] == "platform-key"
    assert effective["source"] == "platform"

    cfg.LLM_API_KEY = ""
    assert svc.effective(user["id"], "llm", cfg)["source"] is None


def test_placeholder_key_with_custom_base_url_is_rejected(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credplaceurl")

    with pytest.raises(CredentialError) as exc:
        svc.upsert(
            user["id"], user.get("tenant_id"), "llm",
            api_key="your_api_key",
            base_url="https://93.184.216.34/v1",
        )
    assert exc.value.code == "user_key_required"
    assert exc.value.status_code == 400
    assert svc.get_record(user["id"], "llm") is None


def _store_legacy_placeholder(svc, cfg, user, api_key="changeme", base_url=None):
    """Persist a placeholder key directly, simulating rows saved before normalisation."""
    svc.upsert(user["id"], user.get("tenant_id"), "llm")
    svc.db.update(
        "provider_credentials",
        {"api_key_ciphertext": svc._encrypt(api_key, cfg), "base_url": base_url},
        "user_id = ? AND provider = ?",
        (user["id"], "llm"),
    )


def test_stored_placeholder_key_is_unconfigured(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credlegacy")
    cfg.LLM_API_KEY = "platform-key"
    _store_legacy_placeholder(svc, cfg, user)

    public = svc.list_public(user["id"], cfg)[0]
    assert public["has_key"] is False
    assert public["key_last4"] is None

    effective = svc.effective(user["id"], "llm", cfg)
    assert effective["api_key"] == "platform-key"
    assert effective["source"] == "platform"

    cfg.LLM_API_KEY = ""
    assert svc.effective(user["id"], "llm", cfg)["source"] is None
    assert svc.has_provider(user["id"], "llm", cfg)[0] is False


def test_stored_placeholder_key_with_custom_base_url_requires_user_key(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credlegacyurl")
    cfg.LLM_API_KEY = "platform-key"
    _store_legacy_placeholder(
        svc, cfg, user, base_url="https://93.184.216.34/v1",
    )

    with pytest.raises(CredentialError) as exc:
        svc.effective(user["id"], "llm", cfg)
    assert exc.value.code == "user_key_required"

    # Saving over a legacy placeholder row must also refuse a custom base URL.
    with pytest.raises(CredentialError) as exc:
        svc.upsert(
            user["id"], user.get("tenant_id"), "llm",
            base_url="https://93.184.216.34/v1",
        )
    assert exc.value.code == "user_key_required"


def test_validate_base_url_rejects_private_and_http(app):
    svc, cfg = _service(app)

    with pytest.raises(CredentialError):
        svc.validate_base_url("https://127.0.0.1/v1", cfg)
    with pytest.raises(CredentialError):
        svc.validate_base_url("https://10.0.0.5/v1", cfg)
    with pytest.raises(CredentialError):
        svc.validate_base_url("http://93.184.216.34/v1", cfg)

    assert svc.validate_base_url("https://93.184.216.34/v1", cfg) == "https://93.184.216.34/v1"


def test_unreadable_ciphertext_does_not_fall_back(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credrotate")

    svc.upsert(user["id"], user.get("tenant_id"), "llm", api_key="sk-rotate-9999")
    cfg.LLM_API_KEY = "platform-key"
    cfg.SECRET_KEY = "rotated-secret-key"

    effective = svc.effective(user["id"], "llm", cfg)
    assert effective["source"] is None
    assert effective["api_key"] == ""
    assert effective.get("error") == "credential_unreadable"


def test_active_tasks_detection(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credtasks")
    task_service = get_task_service(cfg.DATA_DIR)

    storyboard = task_service.create_task(
        creative_project_id=None,
        task_type="storyboard",
        created_by=user["id"],
        status="queued",
    )
    video = task_service.create_task(
        creative_project_id=None,
        task_type="video",
        created_by=user["id"],
        provider="ark_seedance",
        status="running",
    )

    assert svc.has_active_tasks(user["id"], "llm") is True
    assert svc.has_active_tasks(user["id"], "ark") is True
    assert svc.has_active_tasks(user["id"], "luma") is False

    task_service.update_task(storyboard.id, status="succeeded")
    task_service.update_task(video.id, status="succeeded")
    assert svc.has_active_tasks(user["id"], "llm") is False
    assert svc.has_active_tasks(user["id"], "ark") is False


def test_ark_model_overrides_are_returned(app):
    svc, cfg = _service(app)
    user = support.create_admin(cfg.DATA_DIR, username="credark")

    svc.upsert(
        user["id"], user.get("tenant_id"), "ark",
        api_key="ark-key-1111",
        model_overrides={"ark_seedream_pro": "custom-image-model"},
    )
    effective = svc.effective(user["id"], "ark", cfg)
    assert effective["model_overrides"]["ark_seedream_pro"] == "custom-image-model"
