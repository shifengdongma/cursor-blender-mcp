# -*- coding: utf-8 -*-
"""
Rate Limiter: In-memory sliding window rate limiting for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import logging
import threading
import time
from collections import defaultdict

from flask import request

from .http_utils import api_error

logger = logging.getLogger(__name__)


class RateLimiter(object):
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._windows = defaultdict(list)
        self._lock = threading.Lock()

    def _clean_window(self, key, window_s):
        """Remove expired entries from sliding window."""
        now = time.time()
        cutoff = now - window_s
        with self._lock:
            self._windows[key] = [t for t in self._windows.get(key, []) if t > cutoff]

    def check_rate_limit(self, key, max_requests, window_s):
        """
        Check if request should be rate limited.
        Returns True if allowed, False if rate limited.
        """
        now = time.time()
        with self._lock:
            # Clean old entries
            cutoff = now - window_s
            self._windows[key] = [t for t in self._windows.get(key, []) if t > cutoff]

            current_count = len(self._windows[key])

            if current_count >= max_requests:
                oldest = self._windows[key][0] if self._windows[key] else now
                retry_after = int(window_s - (now - oldest)) + 1
                return False, retry_after

            self._windows[key].append(now)
            return True, 0

    def get_usage(self, key, window_s):
        """Get current usage count for a key."""
        with self._lock:
            cutoff = time.time() - window_s
            self._windows[key] = [t for t in self._windows.get(key, []) if t > cutoff]
            return len(self._windows[key])


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(max_requests, window_s, key_func=None):
    """
    Decorator for Flask routes to apply rate limiting.

    Args:
        max_requests: Maximum requests allowed in the window
        window_s: Sliding window size in seconds
        key_func: Function that takes request and returns a key string.
                  Defaults to client IP.
    """
    def decorator(f):
        def wrapped(*args, **kwargs):
            if key_func:
                key = key_func(request) if callable(key_func) else str(key_func)
            else:
                # ProxyFix (when TRUST_PROXY is enabled) already rewrites
                # remote_addr from trusted headers.  Never trust a raw
                # X-Forwarded-For supplied by the client.
                key = 'ip:' + (request.remote_addr or 'unknown')

            endpoint_key = request.endpoint or 'unknown'
            full_key = '{0}:{1}'.format(endpoint_key, key)

            allowed, retry_after = _rate_limiter.check_rate_limit(full_key, max_requests, window_s)

            if not allowed:
                from flask import jsonify
                payload, code = api_error(
                    'rate_limited',
                    '请求过于频繁，请在 {0} 秒后重试'.format(retry_after),
                    status_code=429,
                    details={'retry_after': retry_after}
                )
                return jsonify(payload), code

            return f(*args, **kwargs)
        wrapped.__name__ = f.__name__
        return wrapped
    return decorator
