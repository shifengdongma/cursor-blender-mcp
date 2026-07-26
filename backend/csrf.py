# -*- coding: utf-8 -*-
"""
CSRF Protection for AIGV Studio.
Generates tokens, provides validation decorator.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import functools
import logging
import os
import uuid

from flask import g, request, session

from .http_utils import api_error

logger = logging.getLogger(__name__)


def generate_csrf_token():
    """Generate a CSRF token and store in session."""
    token = uuid.uuid4().hex
    session['_csrf_token'] = token
    return token


def get_csrf_token():
    """Get current CSRF token from session, generating if needed."""
    token = session.get('_csrf_token')
    if not token:
        token = generate_csrf_token()
    return token


def csrf_required(f):
    """Decorator to require CSRF token on state-changing requests."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # Skip CSRF check if disabled via config
        try:
            from .config import Config
            cfg = Config()
            if not cfg.CSRF_ENABLED:
                return f(*args, **kwargs)
        except Exception:
            pass

        # Only check POST, PUT, DELETE, PATCH
        if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return f(*args, **kwargs)

        token = (request.headers.get('X-CSRF-Token') or
                 request.form.get('_csrf_token') or
                 (request.get_json(silent=True) or {}).get('_csrf_token'))

        session_token = session.get('_csrf_token')

        if not token or not session_token or token != session_token:
            payload, code = api_error('csrf_invalid', 'CSRF 令牌无效或缺失', status_code=403)
            from flask import jsonify
            return jsonify(payload), code

        return f(*args, **kwargs)
    return decorated
