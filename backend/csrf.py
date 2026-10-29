# -*- coding: utf-8 -*-
"""Session-backed CSRF tokens.

The central guard in backend/web_security.py enforces CSRF for every unsafe
method, including login/register/logout.  This module deliberately has no
dependency on Config so it cannot silently read a different configuration.
"""
from __future__ import absolute_import

import functools
import hmac
import uuid

from flask import jsonify, request, session

from .http_utils import api_error

UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def generate_csrf_token():
    """Rotate and return the session CSRF token."""
    token = uuid.uuid4().hex
    session["_csrf_token"] = token
    return token


def get_csrf_token():
    """Get the current token, generating one if needed."""
    token = session.get("_csrf_token")
    if not token:
        token = generate_csrf_token()
    return token


def extract_csrf_token(req=None):
    req = req or request
    token = req.headers.get("X-CSRF-Token") or req.headers.get("X-CSRFToken")
    if token:
        return token
    token = req.form.get("_csrf_token")
    if token:
        return token
    if req.is_json:
        payload = req.get_json(silent=True) or {}
        if isinstance(payload, dict):
            return payload.get("_csrf_token")
    return None


def validate_csrf_token(token=None, req=None):
    req = req or request
    token = token or extract_csrf_token(req)
    expected = session.get("_csrf_token")
    if not token or not expected:
        return False
    return hmac.compare_digest(str(token), str(expected))


def csrf_required(f):
    """Decorator kept for compatibility; the central guard is authoritative."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if request.method in UNSAFE_METHODS and not validate_csrf_token():
            payload, code = api_error("csrf_invalid", "CSRF 令牌无效或缺失", status_code=403)
            return jsonify(payload), code
        return f(*args, **kwargs)

    return decorated
