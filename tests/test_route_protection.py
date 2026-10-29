# -*- coding: utf-8 -*-
"""Route matrix: every non-public route requires authentication."""
from __future__ import absolute_import

import re

import pytest

from tests import support

PUBLIC_API = {
    "/api/auth/status",
    "/api/auth/csrf",
    "/api/auth/login",
    "/api/auth/register",
    "/api/health",
}
PUBLIC_PAGES = {"/login", "/register"}


def _fill_rule(rule):
    return re.sub(r"<[^>]+>", "x", rule)


def test_all_non_public_routes_reject_anonymous_access(app):
    client = app.test_client()
    token = support.csrf(client)
    checked = 0
    for rule in app.url_map.iter_rules():
        path = _fill_rule(rule.rule)
        if not path.startswith("/") or path.startswith("/web/"):
            continue
        if path in PUBLIC_API or path in PUBLIC_PAGES:
            continue
        methods = sorted(method for method in rule.methods if method in ("GET", "POST", "PUT", "PATCH", "DELETE"))
        if not methods:
            continue
        method = "GET" if "GET" in methods else methods[0]
        headers = support.auth_headers(token) if method != "GET" else {}
        response = client.open(path, method=method, json={} if method != "GET" else None, headers=headers)
        checked += 1
        if path.startswith("/api/"):
            assert response.status_code == 401, (method, path, response.status_code, response.data[:200])
        else:
            assert response.status_code == 302, (method, path, response.status_code)
            assert "/login" in response.headers.get("Location", "")
    assert checked > 50
