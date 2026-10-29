# -*- coding: utf-8 -*-
"""User credentials flowing through the model registry and provider factory."""
from __future__ import absolute_import

import pytest

from backend import generation_models, generation_service
from backend.credential_service import CredentialService
from backend.http_utils import ApiError
from backend.models import GenerationTask
from backend.providers.openai_image import OpenAIImageProvider
from backend.task_service import get_task_service
from tests import support

IMAGE_MODEL_KEY = "openai_gpt_image_1"
CUSTOM_BASE_URL = "https://93.184.216.34/v1"


def _service(app):
    cfg = app.config["AIGV_CONFIG"]
    return CredentialService(cfg.DATA_DIR, cfg), cfg


def _user(cfg, username):
    return support.create_admin(cfg.DATA_DIR, username=username)


def _image_model(cfg, user):
    return next(
        item
        for item in generation_models.list_models(cfg, task_type="image", user=user)
        if item["key"] == IMAGE_MODEL_KEY
    )


def test_user_credential_makes_openai_image_available(app):
    svc, cfg = _service(app)
    user = _user(cfg, "openai_available")

    item = _image_model(cfg, user)
    assert item["available"] is False
    assert item["unavailable_reason"]
    assert item["credential_source"] is None
    assert item["configure_url"] == "/api-settings"

    svc.upsert(
        user["id"], user.get("tenant_id"), "openai_image",
        api_key="sk-user-openai-4242",
    )

    item = _image_model(cfg, user)
    assert item["available"] is True
    assert item["unavailable_reason"] is None
    assert item["credential_source"] == "user"
    assert "configure_url" not in item

    svc.delete(user["id"], "openai_image")
    assert _image_model(cfg, user)["available"] is False


def test_provider_factory_uses_user_key_and_base_url(app):
    svc, cfg = _service(app)
    user = _user(cfg, "openai_factory")
    svc.upsert(
        user["id"], user.get("tenant_id"), "openai_image",
        api_key="sk-user-factory-7777",
        base_url=CUSTOM_BASE_URL,
        model="gpt-image-1-mini",
    )

    provider = generation_service._provider_for_task(
        cfg,
        GenerationTask(
            created_by=user["id"],
            provider="openai_image",
            model_id="gpt-image-1-mini",
            params={
                "model_key": IMAGE_MODEL_KEY,
                "credential_source": "user",
            },
        ),
    )
    assert isinstance(provider, OpenAIImageProvider)
    assert provider.api_key == "sk-user-factory-7777"
    assert provider.base_url == CUSTOM_BASE_URL
    assert provider.model_id == "gpt-image-1-mini"


def test_task_snapshots_credential_source(app):
    svc, cfg = _service(app)
    user = _user(cfg, "openai_snapshot")
    svc.upsert(
        user["id"], user.get("tenant_id"), "openai_image",
        api_key="sk-user-snapshot-1",
        model="gpt-image-1-mini",
    )
    task_service = get_task_service(cfg.DATA_DIR)

    task = generation_service.create_generation_task(
        cfg,
        task_service,
        user,
        "image",
        IMAGE_MODEL_KEY,
        {"prompt": "a quiet gallery", "size": "1K"},
    )
    assert task.provider == "openai_image"
    assert task.params["credential_source"] == "user"
    assert task.model_id == "gpt-image-1-mini"

    # Later credential edits must not change the snapshotted task.
    svc.delete(user["id"], "openai_image")
    stored = task_service.get_task(task.id)
    assert stored.params["credential_source"] == "user"
    assert stored.model_id == "gpt-image-1-mini"


def test_pinned_user_credential_missing_fails_the_factory_with_api_error(app):
    svc, cfg = _service(app)
    user = _user(cfg, "openai_pinned")
    svc.upsert(
        user["id"], user.get("tenant_id"), "openai_image",
        api_key="sk-user-pinned-3",
    )
    task = GenerationTask(
        created_by=user["id"],
        provider="openai_image",
        model_id="gpt-image-1",
        params={"model_key": IMAGE_MODEL_KEY, "credential_source": "user"},
    )
    svc.delete(user["id"], "openai_image")

    with pytest.raises(ApiError) as exc:
        generation_service._provider_for_task(cfg, task)
    assert exc.value.code == "provider_credential_missing"
    assert exc.value.details == {"configure_url": "/api-settings"}


def test_missing_user_credential_for_custom_base_url_blocks_task(app):
    svc, cfg = _service(app)
    user = _user(cfg, "openai_nokey")
    svc.upsert(
        user["id"], user.get("tenant_id"), "openai_image",
        api_key="sk-user-temp-2",
        base_url=CUSTOM_BASE_URL,
    )
    # Simulate a row whose ciphertext can no longer be decrypted/used while a
    # custom (non-platform) base URL remains configured.
    svc.db.update(
        "provider_credentials",
        {"api_key_ciphertext": None},
        "user_id = ? AND provider = ?",
        (user["id"], "openai_image"),
    )
    task_service = get_task_service(cfg.DATA_DIR)

    with pytest.raises(ApiError) as exc:
        generation_service.create_generation_task(
            cfg,
            task_service,
            user,
            "image",
            IMAGE_MODEL_KEY,
            {"prompt": "a quiet gallery", "size": "1K"},
        )
    assert exc.value.code == "provider_not_configured"
    assert exc.value.status_code == 400
    assert exc.value.details == {"configure_url": "/api-settings"}
    assert task_service.list_tasks(created_by=user["id"])["items"] == []


def _resolver(ip):
    import socket as _socket

    def resolve(host, port, type=None, *args, **kwargs):
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (ip, port))]

    return resolve


def test_user_base_url_is_revalidated_before_factory_and_fails_closed(app, monkeypatch):
    import socket

    svc, cfg = _service(app)
    user = _user(cfg, "rebind_factory")
    monkeypatch.setattr(socket, "getaddrinfo", _resolver("93.184.216.34"))
    svc.upsert(
        user["id"],
        user.get("tenant_id"),
        "openai_image",
        api_key="sk-rebind-9001",
        base_url="https://rebind.example/v1",
        model="gpt-image-1",
    )

    # DNS now resolves the same host to the private network.
    monkeypatch.setattr(socket, "getaddrinfo", _resolver("10.0.0.5"))
    task = GenerationTask(
        created_by=user["id"],
        provider="openai_image",
        model_id="gpt-image-1",
        params={"model_key": IMAGE_MODEL_KEY, "credential_source": "user"},
    )
    with pytest.raises(ApiError) as exc:
        generation_service._provider_for_task(cfg, task)
    assert exc.value.code == "provider_credential_missing"
    assert exc.value.details == {"configure_url": "/api-settings"}
    assert "Base URL" in exc.value.message
