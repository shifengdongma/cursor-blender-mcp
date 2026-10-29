# -*- coding: utf-8 -*-
"""CSRF token lifecycle through real HTTP routes."""
from __future__ import absolute_import

from tests import support


def test_csrf_endpoint_issues_and_accepts_token(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    token = response.get_json()["data"]["csrf_token"]
    assert isinstance(token, str)
    assert len(token) == 32

    # The same session token is returned until it is rotated.
    assert client.get("/api/auth/csrf").get_json()["data"]["csrf_token"] == token

    response = client.post(
        "/api/auth/register",
        json={
            "username": "csrfflow",
            "password": "password123",
            "confirm_password": "password123",
            "nickname": "CSRF",
            "terms_accepted": True,
        },
        headers=support.auth_headers(token),
    )
    assert response.status_code == 201


def test_missing_or_wrong_csrf_is_rejected(client):
    response = client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_invalid"

    token = support.csrf(client)
    response = client.post(
        "/api/auth/login",
        json={"username": "x", "password": "y"},
        headers=support.auth_headers(token + "tampered"),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "csrf_invalid"


def test_login_rotates_token(client):
    old = support.csrf(client)
    response = client.post(
        "/api/auth/register",
        json={
            "username": "rotateuser",
            "password": "password123",
            "confirm_password": "password123",
            "nickname": "Rotate",
            "terms_accepted": True,
        },
        headers=support.auth_headers(old),
    )
    new = response.get_json()["data"]["csrf_token"]
    assert new and new != old
    # The pre-login token is no longer valid for this session.
    assert client.post(
        "/api/auth/logout", headers=support.auth_headers(old)
    ).status_code == 403
    assert client.post(
        "/api/auth/logout", headers=support.auth_headers(new)
    ).status_code == 200
