# -*- coding: utf-8 -*-
"""Tests for Creative API routes."""
from __future__ import absolute_import

import json
import os
import tempfile

import pytest
from flask import Flask, g

from backend import asset_service, creative_project_service
from backend import storyboard_service, task_service, timeline_service
from backend.creative_routes import register_creative_routes
from backend.database import get_database, reset_database
from backend.http_utils import ApiError


def _json_success(data=None, message=None, status_code=200, details=None):
    from flask import jsonify
    from backend.http_utils import api_success
    payload, code = api_success(data=data, message=message, status_code=status_code, details=details)
    return jsonify(payload), code


def _json_error(code, message, status_code=400, details=None):
    from flask import jsonify
    from backend.http_utils import api_error
    payload, sc = api_error(code=code, message=message, status_code=status_code, details=details)
    return jsonify(payload), sc


class FakeConfig(object):
    DATA_DIR = tempfile.mkdtemp(prefix="aigv_test_")
    DEMO_MODE = False
    LLM_API_KEY = "test-llm-key"
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_MODEL_NAME = "gpt-4o"
    COMFYUI_BASE_URL = "http://127.0.0.1:8188"
    COMFYUI_WORKFLOW_FILE = ""
    PIPER_BIN = "piper"
    PIPER_MODEL_PATH = "./model.onnx"
    FFPROBE_BIN = "ffprobe"
    FFMPEG_BIN = "ffmpeg"
    SEEDANCE_API_KEY = "test-seedance-key"
    SEEDANCE_BASE_URL = "https://api.atlascloud.ai/api/v1"
    LUMA_API_KEY = ""
    LUMA_BASE_URL = ""

    @staticmethod
    def has_valid_llm_key():
        return True

    @staticmethod
    def has_comfyui_configured():
        return True

    @staticmethod
    def has_piper_configured():
        return True

    @staticmethod
    def has_ffmpeg_configured():
        return True

    @staticmethod
    def has_valid_api_key():
        return True


@pytest.fixture
def app():
    """Create Flask test app with creative routes."""
    reset_database()

    # Create temp DB
    db_path = os.path.join(tempfile.mkdtemp(prefix="aigv_test_"), "test.db")
    get_database(db_path)

    # Insert FK records for creative projects
    import time
    now = int(time.time())
    get_database().execute("INSERT OR IGNORE INTO tenants (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                           ("t1", "Tenant 1", now, now))
    get_database().execute("INSERT OR IGNORE INTO users (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                           ("u1", "User 1", "t1", now, now))
    get_database().execute("INSERT OR IGNORE INTO projects (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                           ("p1", "Project 1", "t1", now, now))

    # Reset singletons
    creative_project_service._creative_project_service = None
    storyboard_service._storyboard_service = None
    task_service._task_service = None
    asset_service._asset_service = None
    timeline_service._timeline_service = None

    app = Flask(__name__)
    app.testing = True

    @app.before_request
    def _inject_test_user():
        g.current_user = {
            "id": "u1",
            "username": "u1",
            "nickname": "User 1",
            "role": "user",
            "status": "active",
            "tenant_id": "t1",
            "user_id": "u1",
        }

    register_creative_routes(app, FakeConfig(), _json_success, _json_error)

    # Register ApiError handler
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        payload, sc = _json_error(error.code, error.message, error.status_code, error.details)
        return payload, sc

    yield app

    reset_database()
    creative_project_service._creative_project_service = None
    storyboard_service._storyboard_service = None
    task_service._task_service = None
    asset_service._asset_service = None
    timeline_service._timeline_service = None


@pytest.fixture
def client(app):
    return app.test_client()


class TestCreativeRoutes(object):

    def test_create_project(self, client):
        resp = client.post("/api/creative/projects", json={"name": "测试项目"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["name"] == "测试项目"

    def test_create_project_missing_name(self, client):
        resp = client.post("/api/creative/projects", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False

    def test_list_projects(self, client):
        client.post("/api/creative/projects", json={"name": "P1"})
        client.post("/api/creative/projects", json={"name": "P2"})

        resp = client.get("/api/creative/projects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["total"] == 2

    def test_get_project(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "View"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.get("/api/creative/projects/{0}".format(pid))
        assert resp.status_code == 200
        assert resp.get_json()["data"]["name"] == "View"

    def test_get_nonexistent_project(self, client):
        resp = client.get("/api/creative/projects/nonexistent")
        assert resp.status_code == 404

    def test_update_project(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Old"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.put("/api/creative/projects/{0}".format(pid), json={"name": "New"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["name"] == "New"

    def test_update_project_with_requirements_object(self, client):
        """The Save button sends requirements/settings as nested objects."""
        create_resp = client.post("/api/creative/projects", json={"name": "Old"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.put("/api/creative/projects/{0}".format(pid), json={
            "name": "New",
            "description": "desc",
            "concept": "theme",
            "requirements": {"elements": "建筑", "duration": 60, "channels": ["官网"]},
        })
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["requirements"]["elements"] == "建筑"
        assert data["requirements"]["channels"] == ["官网"]

    def test_delete_project(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "ToDelete"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.delete("/api/creative/projects/{0}".format(pid))
        assert resp.status_code == 200

        get_resp = client.get("/api/creative/projects/{0}".format(pid))
        assert get_resp.status_code == 404

    def test_analyze_project(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Analyze"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.post("/api/creative/projects/{0}/analyze".format(pid), json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["data"]["task_type"] == "storyboard"

    def test_list_shots(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Shots"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.get("/api/creative/projects/{0}/shots".format(pid))
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data["data"], list)

    def test_add_shot(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "AddShot"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.post(
            "/api/creative/projects/{0}/shots".format(pid),
            json={"scene_title": "测试镜头", "duration_s": 5},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["data"]["scene_title"] == "测试镜头"

    def test_update_shot(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "UpdateShot"})
        pid = create_resp.get_json()["data"]["id"]
        shot_resp = client.post(
            "/api/creative/projects/{0}/shots".format(pid),
            json={"scene_title": "原始"},
        )
        shot_id = shot_resp.get_json()["data"]["id"]

        resp = client.put("/api/creative/shots/{0}".format(shot_id), json={"scene_title": "更新"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["scene_title"] == "更新"

    def test_delete_shot(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "DelShot"})
        pid = create_resp.get_json()["data"]["id"]
        shot_resp = client.post(
            "/api/creative/projects/{0}/shots".format(pid),
            json={"scene_title": "待删除"},
        )
        shot_id = shot_resp.get_json()["data"]["id"]

        resp = client.delete("/api/creative/shots/{0}".format(shot_id))
        assert resp.status_code == 200

    def test_get_task(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "TaskTest"})
        pid = create_resp.get_json()["data"]["id"]
        task_resp = client.post("/api/creative/projects/{0}/analyze".format(pid), json={})
        task_id = task_resp.get_json()["data"]["id"]

        resp = client.get("/api/creative/tasks/{0}".format(task_id))
        assert resp.status_code == 200
        assert resp.get_json()["data"]["task_type"] == "storyboard"

    def test_cancel_task(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "CancelTest"})
        pid = create_resp.get_json()["data"]["id"]
        task_resp = client.post("/api/creative/projects/{0}/analyze".format(pid), json={})
        task_id = task_resp.get_json()["data"]["id"]

        resp = client.post("/api/creative/tasks/{0}/cancel".format(task_id))
        assert resp.status_code == 200

    def test_reorder_shots(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Reorder"})
        pid = create_resp.get_json()["data"]["id"]
        s1 = client.post("/api/creative/projects/{0}/shots".format(pid), json={"scene_title": "First"})
        s2 = client.post("/api/creative/projects/{0}/shots".format(pid), json={"scene_title": "Second"})
        sid1 = s1.get_json()["data"]["id"]
        sid2 = s2.get_json()["data"]["id"]

        resp = client.post("/api/creative/shots/reorder", json={
            "project_id": pid,
            "ordered_ids": [sid2, sid1],
        })
        assert resp.status_code == 200

        shots_resp = client.get("/api/creative/projects/{0}/shots".format(pid))
        shots = shots_resp.get_json()["data"]
        assert shots[0]["id"] == sid2
        assert shots[0]["sequence_no"] == 1

    def test_get_nonexistent_task(self, client):
        resp = client.get("/api/creative/tasks/nonexistent")
        assert resp.status_code == 404

    def test_compose_endpoint(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Compose"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.post("/api/creative/projects/{0}/compose".format(pid), json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "timeline_has_no_video"

    def test_export_endpoint(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Export"})
        pid = create_resp.get_json()["data"]["id"]

        resp = client.post("/api/creative/projects/{0}/exports".format(pid), json={})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["data"]["task_type"] == "export"

    def test_timeline_save_load(self, client):
        create_resp = client.post("/api/creative/projects", json={"name": "Timeline"})
        pid = create_resp.get_json()["data"]["id"]

        # Save a subtitle-only timeline (valid without media assets).
        resp = client.put("/api/creative/projects/{0}/timeline".format(pid), json={
            "timeline_version": 0,
            "tracks": [
                {"name": "字幕", "track_type": "subtitle", "role": "subtitle",
                 "sequence_no": 0, "clips": [
                    {"name": "字幕 1", "start_time": 0, "duration_s": 2,
                     "subtitle_text": "测试字幕"}
                ]}
            ]
        })
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["data"]["saved"] is True
        assert resp.get_json()["data"]["timeline_version"] == 1

        # Load timeline
        resp = client.get("/api/creative/projects/{0}/timeline".format(pid))
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["track"]["name"] == "字幕"
        assert len(data["tracks"][0]["clips"]) == 1
        assert data["tracks"][0]["clips"][0]["subtitle_text"] == "测试字幕"
