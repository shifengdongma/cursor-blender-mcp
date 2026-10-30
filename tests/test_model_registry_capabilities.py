# -*- coding: utf-8 -*-
"""Model IDs, capability matrix, defaults, and override precedence."""
from __future__ import absolute_import

import pytest

from backend import generation_models, model_ids
from backend.credential_service import CredentialError, CredentialService
from backend.http_utils import ApiError
from backend.task_service import get_task_service
from tests import support

ARK_MODEL_IDS = {
    "ark_seedream_pro": "doubao-seedream-5-0-pro-260628",
    "ark_seedream_flash": "doubao-seedream-5-0-flash-260915",
    "ark_seedance_25": "doubao-seedance-2-5-260628",
    "ark_seedance_20": "doubao-seedance-2-0-260128",
    "ark_seedance_10_pro": "doubao-seedance-1-0-pro-250528",
}


def _cfg(app):
    return app.config["AIGV_CONFIG"]


def _ark_user(cfg, username="registry_user"):
    user = support.create_admin(cfg.DATA_DIR, username=username)
    service = CredentialService(cfg.DATA_DIR, cfg)
    service.upsert(
        user["id"],
        user.get("tenant_id"),
        "ark",
        api_key="ark-registry-test-key",
    )
    return user, service


def _item(cfg, key, user=None):
    item = generation_models.get_model(cfg, key, user=user)
    assert item is not None
    return item


def test_ark_model_ids_use_official_ids(app):
    for key, expected in ARK_MODEL_IDS.items():
        assert _item(_cfg(app), key)["model_id"] == expected
    assert model_ids.ARK_SEEDREAM_FLASH == ARK_MODEL_IDS["ark_seedream_flash"]


def test_lite_slot_is_replaced_by_flash_without_id_impersonation(app):
    cfg = _cfg(app)
    keys = [model["key"] for model in generation_models.MODELS]
    assert "ark_seedream_lite" not in keys
    assert "ark_seedream_flash" in keys

    aliased = generation_models.get_model(cfg, "ark_seedream_lite")
    assert aliased is not None
    assert aliased["key"] == "ark_seedream_flash"
    assert aliased["model_id"] == ARK_MODEL_IDS["ark_seedream_flash"]
    assert "lite-260128" not in aliased["model_id"]


def test_seedream_flash_and_pro_capabilities(app):
    cfg = _cfg(app)
    for key in ("ark_seedream_flash", "ark_seedream_pro"):
        caps = _item(cfg, key)["capabilities"]
        assert caps["sizes"] == ["1K", "1.5K", "2K"]
        assert caps["max_reference_images"] == 10
        assert caps["pixel_range"] == [921600, 4624220]
        assert caps["default_size"] == "2K"


def test_seedance_capabilities_match_documented_limits(app):
    cfg = _cfg(app)

    caps_25 = _item(cfg, "ark_seedance_25")["capabilities"]
    assert caps_25["duration_range"] == [4, 30]
    assert caps_25["max_reference_images"] == 30
    assert caps_25["supports_audio"] is True
    assert caps_25["default_audio"] is True
    assert caps_25["resolutions"] == ["480p", "720p", "1080p"]

    caps_20 = _item(cfg, "ark_seedance_20")["capabilities"]
    assert caps_20["duration_range"] == [4, 15]
    assert caps_20["max_reference_images"] == 9
    assert caps_20["supports_audio"] is True
    assert caps_20["default_audio"] is False

    caps_10 = _item(cfg, "ark_seedance_10_pro")["capabilities"]
    assert caps_10["duration_range"] == [2, 12]
    assert caps_10["max_reference_images"] == 2
    assert caps_10["reference_mode"] == "first_last_only"
    assert caps_10["supports_audio"] is False


def test_flash_is_default_image_model_when_ark_key_exists(app):
    cfg = _cfg(app)
    user, _service = _ark_user(cfg)
    items = generation_models.list_models(cfg, task_type="image", user=user)
    defaults = [item["key"] for item in items if item["available"] and item["default"]]
    assert defaults == ["ark_seedream_flash"]


def test_explicit_env_override_beats_registry(tmp_path):
    app = support.make_app(tmp_path, ARK_IMAGE_MODEL_FLASH="env-flash-model")
    cfg = _cfg(app)
    assert _item(cfg, "ark_seedream_flash")["model_id"] == "env-flash-model"
    assert _item(cfg, "ark_seedream_flash")["model_id_source"] == "env_override"


def test_user_override_beats_explicit_env(tmp_path):
    app = support.make_app(
        tmp_path,
        ARK_IMAGE_MODEL_FLASH="env-flash-model",
        ALLOW_INSECURE_PROVIDER_URLS=False,
    )
    cfg = _cfg(app)
    user, service = _ark_user(cfg, "override_user")
    service.upsert(
        user["id"],
        user.get("tenant_id"),
        "ark",
        model_overrides={"ark_seedream_flash": "user-flash-model"},
    )
    item = _item(cfg, "ark_seedream_flash", user=user)
    assert item["model_id"] == "user-flash-model"
    assert item["model_id_source"] == "user_override"


def test_model_registry_defaults_win_when_env_is_unset(app):
    cfg = _cfg(app)
    assert getattr(cfg, "ARK_IMAGE_MODEL", "") == ""
    assert getattr(cfg, "ARK_IMAGE_MODEL_FLASH", "") == ""
    assert _item(cfg, "ark_seedream_flash")["model_id_source"] == "registry"


def test_unknown_or_obsolete_model_override_keys_are_rejected(app):
    cfg = _cfg(app)
    user, service = _ark_user(cfg, "override_reject")
    with pytest.raises(CredentialError) as exc:
        service.upsert(
            user["id"],
            user.get("tenant_id"),
            "ark",
            model_overrides={"ark_seedream_lite": "doubao-seedream-5-0-lite-260128"},
        )
    assert exc.value.code == "invalid_model_overrides"


def test_credential_catalog_matches_registry_ids(app):
    cfg = _cfg(app)
    catalog = CredentialService(cfg.DATA_DIR, cfg).catalog(cfg)
    ark = next(item for item in catalog if item["provider"] == "ark")
    fields = {field["key"]: field["default"] for field in ark["model_fields"]}
    assert fields == ARK_MODEL_IDS


def _ark_task_payload(**extra):
    payload = {"prompt": "a quiet gallery interior", "size": "1K", "ratio": "1:1"}
    payload.update(extra)
    return payload


def test_seedance_10_pro_rejects_audio_and_excess_references(app):
    cfg = _cfg(app)
    user, _service = _ark_user(cfg, "caps_10_pro")
    task_service = get_task_service(cfg.DATA_DIR)

    with pytest.raises(ApiError) as audio_exc:
        generation_models.get_model(cfg, "ark_seedance_10_pro", user=user)
        from backend import generation_service
        generation_service.create_generation_task(
            cfg, task_service, user, "video", "ark_seedance_10_pro",
            {"prompt": "stage", "duration_s": 5, "resolution": "720p",
             "ratio": "16:9", "generate_audio": True},
        )
    assert audio_exc.value.code == "invalid_params"
    assert "音频" in audio_exc.value.message

    with pytest.raises(ApiError) as count_exc:
        from backend import generation_service
        generation_service.create_generation_task(
            cfg, task_service, user, "video", "ark_seedance_10_pro",
            {"prompt": "stage", "duration_s": 5, "resolution": "720p",
             "ratio": "16:9", "reference_asset_ids": ["a", "b", "c"]},
        )
    assert count_exc.value.code == "invalid_params"
    assert "参考" in count_exc.value.message


def test_seedance_20_accepts_audio_and_rejects_out_of_range_duration(app):
    cfg = _cfg(app)
    user, _service = _ark_user(cfg, "caps_20")
    task_service = get_task_service(cfg.DATA_DIR)
    from backend import generation_service

    task = generation_service.create_generation_task(
        cfg, task_service, user, "video", "ark_seedance_20",
        {"prompt": "stage", "duration_s": 12, "resolution": "720p",
         "ratio": "16:9", "generate_audio": True},
    )
    assert task.params["generate_audio"] is True
    assert task.model_id == ARK_MODEL_IDS["ark_seedance_20"]

    with pytest.raises(ApiError) as exc:
        generation_service.create_generation_task(
            cfg, task_service, user, "video", "ark_seedance_20",
            {"prompt": "stage", "duration_s": 16, "resolution": "720p",
             "ratio": "16:9"},
        )
    assert exc.value.code == "invalid_params"
    assert "时长" in exc.value.message
