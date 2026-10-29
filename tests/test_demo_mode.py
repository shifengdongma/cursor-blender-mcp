# -*- coding: utf-8 -*-
"""Stage D: demo/production isolation."""
from __future__ import absolute_import

import json
import os

from backend.database import get_database
from scripts.cleanup_demo_data import main as cleanup_main
from tests import support


def test_demo_mode_false_does_not_seed(tmp_path):
    app = support.make_app(tmp_path, DEMO_MODE=False)
    try:
        db = get_database()
        assert db.count("tenants") == 0
        client = app.test_client()
        response = client.get("/web/runtime-config.js")
        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert '"demoMode": false' in body
        assert "SECRET_KEY" not in body
        demo_js = client.get("/web/aigv-demo-data.js").data.decode("utf-8")
        assert "window.AIGV_DEMO_DATA = null" in demo_js
        catalog = json.load(open(
            os.path.join(support.ROOT, "data", "catalog", "knowledge_base.json"),
            encoding="utf-8",
        ))
        for model in catalog["model_catalog"]:
            assert model["route_mode"] != "demo-route"
        # The current-user context must not expose the demo tenant/user list.
        user, _token = support.register_and_login(client, "demouser")
        context = client.get("/api/demo/context").get_json()["data"]
        assert context["tenant"]["id"] == "tenant_platform"
        assert context["user"]["id"] == user["id"]
    finally:
        support.reset_globals()


def test_demo_mode_true_seeds_and_cleanup_removes_only_known_rows(tmp_path):
    app = support.make_app(tmp_path, DEMO_MODE=True)
    try:
        db = get_database()
        assert db.fetch_one("SELECT id FROM tenants WHERE id = 'tenant_museum_group'")
        # Create a real auth account; cleanup must not remove it.
        client = app.test_client()
        support.register_and_login(client, "keepme")
        assert db.count("auth_users") == 1

        result = cleanup_main(["--data-dir", str(tmp_path), "--confirm"])
        assert result == 0
        assert db.fetch_one("SELECT id FROM tenants WHERE id = 'tenant_museum_group'") is None
        assert db.count("auth_users") == 1
    finally:
        support.reset_globals()


def test_demo_endpoints_are_restricted_when_disabled(tmp_path):
    app = support.make_app(tmp_path, DEMO_MODE=False)
    try:
        client = app.test_client()
        user, token = support.register_and_login(client, "normaldemo")
        # Normal users cannot select arbitrary demo contexts.
        response = client.post(
            "/api/demo/context/select",
            json={"tenant_id": "tenant_museum_group"},
            headers=support.auth_headers(token),
        )
        assert response.status_code == 403
    finally:
        support.reset_globals()
