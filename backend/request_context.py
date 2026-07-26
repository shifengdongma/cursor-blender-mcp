# -*- coding: utf-8 -*-
"""
Request Context Middleware for AIGV Studio.
Generates request IDs and tracks request context.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import functools
import logging
import uuid

from flask import g, request

logger = logging.getLogger(__name__)


def generate_request_id():
    """Generate a unique request ID."""
    return uuid.uuid4().hex[:12]


def request_context_middleware(app):
    """Register request ID middleware on Flask app."""
    @app.before_request
    def set_request_context():
        g.request_id = generate_request_id()
        g.request_start = __import__('time').time()

    @app.after_request
    def add_request_id_header(response):
        request_id = getattr(g, 'request_id', None)
        if request_id:
            response.headers['X-Request-ID'] = request_id

        # Log request timing
        start = getattr(g, 'request_start', None)
        if start:
            duration_ms = (__import__('time').time() - start) * 1000.0
            if duration_ms > 1000:  # Log slow requests
                logger.warning("Slow request: %s %s took %.0fms [rid=%s]",
                               request.method, request.path, duration_ms, request_id)

        return response
