# -*- coding: utf-8 -*-
"""Task 7: asset date/sort filters and generation-history sorting."""
from __future__ import absolute_import

from datetime import datetime

from backend.database import get_database
from backend.generation_routes import _parse_date
from backend.task_service import get_task_service
from tests import support


def _local_timestamp(day, time_of_day="00:00:00"):
    """Server-local timestamp for a wall-clock date, matching API semantics."""
    return int(datetime.strptime(day + " " + time_of_day, "%Y-%m-%d %H:%M:%S").timestamp())


def _create_asset(client, token, name):
    response = client.post(
        "/api/assets",
        json={"name": name},
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["id"]


def _set_asset_created_at(asset_id, timestamp):
    get_database().update(
        "assets",
        {"created_at": timestamp, "updated_at": timestamp},
        "id = ?",
        (asset_id,),
    )


def _list_assets(client, **params):
    query = "&".join("{0}={1}".format(key, value) for key, value in params.items())
    url = "/api/assets" + ("?" + query if query else "")
    response = client.get(url)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def _ids(data):
    return [item["id"] for item in data["items"]]


def test_asset_date_and_sort_filters(client, tmp_path):
    _, token = support.register_and_login(client, "assetfilters")
    asset_29 = _create_asset(client, token, "bravo")
    asset_30a = _create_asset(client, token, "Alpha")
    asset_30b = _create_asset(client, token, "charlie")
    _set_asset_created_at(asset_29, _local_timestamp("2026-10-29", "10:00:00"))
    _set_asset_created_at(asset_30a, _local_timestamp("2026-10-30", "00:00:00"))
    _set_asset_created_at(asset_30b, _local_timestamp("2026-10-30", "23:59:59"))

    # created_after uses the local start of day (00:00:00 inclusive).
    data = _list_assets(client, created_after="2026-10-30")
    assert data["total"] == 2
    assert set(_ids(data)) == {asset_30a, asset_30b}

    # created_before uses the local end of day (23:59:59 inclusive).
    data = _list_assets(client, created_before="2026-10-29")
    assert _ids(data) == [asset_29]

    data = _list_assets(client, created_before="2026-10-30")
    assert data["total"] == 3
    assert set(_ids(data)) == {asset_29, asset_30a, asset_30b}

    # Both bounds at once: only the 30th's rows.
    data = _list_assets(client, created_after="2026-10-30", created_before="2026-10-30")
    assert _ids(data) == [asset_30b, asset_30a]

    assert _ids(_list_assets(client, sort="newest")) == [asset_30b, asset_30a, asset_29]
    assert _ids(_list_assets(client, sort="oldest")) == [asset_29, asset_30a, asset_30b]
    # Case-insensitive name ordering: Alpha, bravo, charlie.
    assert _ids(_list_assets(client, sort="name")) == [asset_30a, asset_29, asset_30b]
    # Default remains newest-first.
    assert _ids(_list_assets(client)) == [asset_30b, asset_30a, asset_29]


def test_asset_invalid_sort_and_range(client):
    support.register_and_login(client, "assetbadfilters")

    response = client.get("/api/assets?sort=evil")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"

    # Raw SQL fragments must never be accepted as sort values.
    response = client.get("/api/assets?sort=name%20DESC")
    assert response.status_code == 400

    response = client.get("/api/assets?created_after=2026-10-30&created_before=2026-10-29")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"

    response = client.get("/api/assets?created_after=not-a-date")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"


def test_generation_date_is_local_time(client):
    expected = int(datetime.strptime("2026-10-30", "%Y-%m-%d").timestamp())
    assert _parse_date("2026-10-30") == expected
    assert _parse_date("2026-10-30", end_of_day=True) == expected + 86399
    # Unix timestamps pass through unchanged.
    assert _parse_date(str(expected)) == expected
    assert _parse_date("") is None
    assert _parse_date(None) is None


def test_generation_sort_oldest(client):
    user, _ = support.register_and_login(client, "tasksort")
    service = get_task_service()
    older = service.create_task(None, "image", created_by=user["id"])
    newer = service.create_task(None, "image", created_by=user["id"])
    get_database().update(
        "generation_tasks",
        {"created_at": 1000, "updated_at": 1000},
        "id = ?",
        (older.id,),
    )
    get_database().update(
        "generation_tasks",
        {"created_at": 2000, "updated_at": 2000},
        "id = ?",
        (newer.id,),
    )

    response = client.get("/api/generation/tasks?sort=oldest")
    assert response.status_code == 200, response.get_json()
    assert _ids(response.get_json()["data"]) == [older.id, newer.id]

    response = client.get("/api/generation/tasks?sort=newest")
    assert response.status_code == 200, response.get_json()
    assert _ids(response.get_json()["data"]) == [newer.id, older.id]

    response = client.get("/api/generation/tasks?sort=evil")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"

    response = client.get("/api/generation/tasks?date_from=2026-10-30&date_to=2026-10-29")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_params"
