# -*- coding: utf-8 -*-
"""Generation history filters, admin scope and upload type validation."""
from __future__ import absolute_import

import base64
import io
import time

import pytest

from backend.database import get_database
from tests import support

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture
def app_with_generation(tmp_path):
    from tests.support import make_app, reset_globals
    application = make_app(
        tmp_path,
        ARK_API_KEY="test-ark-key",
        DAILY_IMAGE_LIMIT=100,
        DAILY_VIDEO_LIMIT=100,
    )
    yield application
    reset_globals()


def _token(client):
    return client.get("/api/auth/csrf").get_json()["data"]["csrf_token"]


def _create_image_task(client, token, prompt="history"):
    response = client.post(
        "/api/generation/images",
        json={"model_key": "ark_seedream_pro", "prompt": prompt},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 202, response.get_json()
    return response.get_json()["data"]["id"]


def test_upload_type_must_match_extension(app_with_generation):
    client = app_with_generation.test_client()
    support.register_and_login(client, "uploadtype")
    token = _token(client)

    response = client.post(
        "/api/assets/upload",
        data={
            "file": (io.BytesIO(PNG), "image.png"),
            "name": "wrong type",
            "asset_type": "video",
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "asset_type_mismatch"

    response = client.post(
        "/api/assets/upload",
        data={
            "file": (io.BytesIO(PNG), "image.png"),
            "name": "correct type",
            "asset_type": "image",
        },
        headers=support.auth_headers(token),
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["asset_type"] == "image"


def test_history_date_filters(app_with_generation):
    client = app_with_generation.test_client()
    user, _ = support.register_and_login(client, "datefilter")
    token = _token(client)
    task_id = _create_image_task(client, token, "dated task")
    old_timestamp = int(time.time()) - 5 * 86400
    get_database().update(
        "generation_tasks",
        {"created_at": old_timestamp, "updated_at": old_timestamp},
        "id = ?",
        (task_id,),
    )

    # Date filters are interpreted in server-local time (no tzinfo), so the
    # expected days must be computed in local time as well.
    today = time.strftime("%Y-%m-%d", time.localtime())
    old_day = time.strftime("%Y-%m-%d", time.localtime(old_timestamp))
    recent = client.get(
        "/api/generation/tasks?date_from={0}".format(today)
    ).get_json()["data"]
    assert recent["total"] == 0

    historical = client.get(
        "/api/generation/tasks?date_from={0}&date_to={0}".format(old_day)
    ).get_json()["data"]
    assert historical["total"] == 1
    assert historical["items"][0]["id"] == task_id

    invalid = client.get("/api/generation/tasks?date_from=not-a-date")
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "invalid_params"


def test_admin_scope_lists_all_tasks_with_creator(app_with_generation, tmp_path):
    user_client = app_with_generation.test_client()
    user, _ = support.register_and_login(user_client, "taskowner")
    token = _token(user_client)
    task_id = _create_image_task(user_client, token, "admin view")

    support.create_admin(tmp_path)
    admin_client = app_with_generation.test_client()
    support.login_and_token(admin_client, "rootadmin", "AdminPass12345")

    data = admin_client.get("/api/generation/tasks?scope=all").get_json()["data"]
    assert data["total"] == 1
    item = data["items"][0]
    assert item["id"] == task_id
    assert item["creator"]["username"] == "taskowner"

    # A normal user may request scope=all but only receives their own tasks.
    own = user_client.get("/api/generation/tasks?scope=all").get_json()["data"]
    assert own["total"] == 1
    assert "creator" not in own["items"][0]
