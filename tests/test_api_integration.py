# -*- coding: utf-8 -*-
"""In-process end-to-end smoke test: auth -> project -> generation -> download."""
from __future__ import absolute_import

from backend import generation_service
from backend.generation_worker import GenerationWorker
from backend.providers.mock_provider import MockImageProvider
from backend.task_service import get_task_service
from tests import support


def test_authenticated_generation_end_to_end(tmp_path, monkeypatch):
    from tests.support import make_app, reset_globals

    app = make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=100,
        DAILY_VIDEO_LIMIT=100,
    )
    try:
        client = app.test_client()
        user, token = support.register_and_login(client, "e2euser")

        # Protected page and bootstrap are available after login.
        assert client.get("/creative-studio").status_code == 200
        bootstrap = client.get("/api/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.get_json()["success"] is True

        project = client.post(
            "/api/creative/projects",
            json={"name": "E2E project"},
            headers=support.auth_headers(token),
        ).get_json()["data"]

        shot = client.post(
            "/api/creative/projects/{0}/shots".format(project["id"]),
            json={"scene_title": "Opening", "duration_s": 5},
            headers=support.auth_headers(token),
        ).get_json()["data"]

        provider = MockImageProvider()
        monkeypatch.setattr(
            generation_service, "_provider_for_task", lambda cfg, task: provider
        )
        response = client.post(
            "/api/creative/shots/{0}/images".format(shot["id"]),
            json={"model_key": "ark_seedream_pro", "prompt": "end to end"},
            headers=support.auth_headers(token),
        )
        assert response.status_code == 201, response.get_json()
        task_id = response.get_json()["data"]["id"]

        cfg = app.config["AIGV_CONFIG"]
        worker = GenerationWorker(get_task_service(cfg.DATA_DIR), cfg)
        assert worker.run_once() is True

        task = client.get("/api/generation/tasks/{0}".format(task_id)).get_json()["data"]
        assert task["status"] == "succeeded"
        assert task["output_asset_id"]
        assert task["params"]["prompt"] == "end to end"

        asset_response = client.get(
            "/api/assets/{0}/download".format(task["output_asset_id"])
        )
        assert asset_response.status_code == 200
        assert len(asset_response.data) > 0

        shots = client.get(
            "/api/creative/projects/{0}/shots".format(project["id"])
        ).get_json()["data"]
        assert shots[0]["primary_image_asset_id"] == task["output_asset_id"]
        assert shots[0]["status"] == "ready"

        # Another user cannot read the generated asset or task.
        other = app.test_client()
        support.register_and_login(other, "e2eother")
        assert other.get(
            "/api/generation/tasks/{0}".format(task_id)
        ).status_code == 403
        assert other.get(
            "/api/assets/{0}/download".format(task["output_asset_id"])
        ).status_code == 403
    finally:
        reset_globals()
