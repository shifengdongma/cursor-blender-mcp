# -*- coding: utf-8 -*-
"""Capability-driven parameter enforcement in the generation chain."""
from __future__ import absolute_import

import json
import os

import pytest
import requests

from backend import generation_models, generation_service
from backend.asset_service import get_asset_service
from backend.database import get_database
from backend.http_utils import ApiError
from backend.providers.volcengine_video import VolcengineVideoProvider
from backend.task_service import get_task_service
from tests import support


class FakeResponse(object):
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = ""
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _caps(key):
    model = next(m for m in generation_models.MODELS if m["key"] == key)
    return model["capabilities"]


def test_reference_roles_are_model_and_count_aware():
    caps_25 = _caps("ark_seedance_25")
    assert generation_models.reference_image_roles(caps_25, 1) == ["first_frame"]
    assert generation_models.reference_image_roles(caps_25, 2) == [
        "first_frame", "last_frame",
    ]
    assert generation_models.reference_image_roles(caps_25, 3) == [
        "reference_image", "reference_image", "reference_image",
    ]

    caps_10 = _caps("ark_seedance_10_pro")
    assert generation_models.reference_image_roles(caps_10, 2) == [
        "first_frame", "last_frame",
    ]
    assert generation_models.reference_image_roles(caps_10, 3) is None


def test_video_provider_uses_supplied_roles(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.update(json)
        return FakeResponse(200, {"id": "task-roles"})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = VolcengineVideoProvider(
        "key", "https://ark.example/api/v3", "doubao-seedance-2-5-260628"
    )
    provider.create_generation(
        "prompt",
        reference_image_urls=["data:image/png;base64,aa", "data:image/png;base64,bb"],
        reference_image_roles=["first_frame", "last_frame"],
    )
    roles = [item.get("role") for item in captured["content"] if item.get("type") == "image_url"]
    assert roles == ["first_frame", "last_frame"]


def test_video_provider_omits_audio_when_false_or_none(monkeypatch):
    captured = []

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured.append(dict(json))
        return FakeResponse(200, {"id": "task-audio"})

    monkeypatch.setattr(requests, "post", fake_post)
    provider = VolcengineVideoProvider("key", "https://ark.example/api/v3", "model")
    provider.create_generation("prompt", generate_audio=None)
    provider.create_generation("prompt", generate_audio=False)
    assert "generate_audio" not in captured[0]
    assert captured[1]["generate_audio"] is False


def test_reference_data_urls_enforces_total_size(tmp_path):
    app = support.make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        MAX_REFERENCE_IMAGES_TOTAL_MB=1,
    )
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(cfg.DATA_DIR, username="reftotal")
    service = get_asset_service(cfg.DATA_DIR)
    ref_dir = os.path.join(service.assets_dir, "images", "references")
    os.makedirs(ref_dir, exist_ok=True)
    asset_ids = []
    for index in range(2):
        rel_path = os.path.join("images", "references", "ref{0}.png".format(index))
        with open(os.path.join(service.assets_dir, rel_path), "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + b"x" * (600 * 1024))
        asset = service.create_asset(
            name="ref{0}".format(index),
            asset_type="image",
            file_path=rel_path,
            file_size=600 * 1024,
            owner_user_id=user["id"],
            visibility="private",
        )
        asset_ids.append(asset.id)

    with pytest.raises(ApiError) as exc:
        generation_service._reference_data_urls(cfg, asset_ids, user)
    assert exc.value.code == "invalid_params"
    assert "总大小" in exc.value.message


def test_creative_image_route_forwards_ratio(tmp_path):
    app = support.make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=20,
        DAILY_VIDEO_LIMIT=5,
    )
    client = app.test_client()
    _user, token = support.register_and_login(client, "caproute")
    headers = support.auth_headers(token)
    project = client.post(
        "/api/creative/projects", json={"name": "Capability"}, headers=headers
    ).get_json()["data"]
    shot = client.post(
        "/api/creative/projects/{0}/shots".format(project["id"]),
        json={"scene_title": "Cap shot", "duration_s": 5},
        headers=headers,
    ).get_json()["data"]

    response = client.post(
        "/api/creative/shots/{0}/images".format(shot["id"]),
        json={
            "model_key": "ark_seedream_flash",
            "prompt": "gallery",
            "size": "1K",
            "ratio": "16:9",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    task_id = response.get_json()["data"]["id"]
    cfg = app.config["AIGV_CONFIG"]
    row = get_database(os.path.join(cfg.DATA_DIR, "aigv.db")).fetch_one(
        "SELECT params FROM generation_tasks WHERE id = ?", (task_id,)
    )
    params = json.loads(row["params"])
    assert params["ratio"] == "16:9"
    assert params["width"] > params["height"]


def test_creative_video_route_uses_model_audio_default(tmp_path):
    app = support.make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=20,
        DAILY_VIDEO_LIMIT=5,
    )
    client = app.test_client()
    _user, token = support.register_and_login(client, "capvideo")
    headers = support.auth_headers(token)
    project = client.post(
        "/api/creative/projects", json={"name": "Capability video"}, headers=headers
    ).get_json()["data"]
    shot = client.post(
        "/api/creative/projects/{0}/shots".format(project["id"]),
        json={"scene_title": "Cap video", "duration_s": 4},
        headers=headers,
    ).get_json()["data"]

    response = client.post(
        "/api/creative/shots/{0}/videos".format(shot["id"]),
        json={
            "model_key": "ark_seedance_25",
            "prompt": "stage",
            "ratio": "16:9",
            "duration_s": 4,
            "resolution": "480p",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    task_id = response.get_json()["data"]["id"]
    cfg = app.config["AIGV_CONFIG"]
    row = get_database(os.path.join(cfg.DATA_DIR, "aigv.db")).fetch_one(
        "SELECT params FROM generation_tasks WHERE id = ?", (task_id,)
    )
    params = json.loads(row["params"])
    assert params["generate_audio"] is True
