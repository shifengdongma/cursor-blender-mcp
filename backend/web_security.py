# -*- coding: utf-8 -*-
"""Central web security guard: authentication, CSRF, session revalidation.

Registered once in create_app().  Route handlers still perform object-level
ownership checks; this guard ensures no route is accidentally anonymous.
"""
from __future__ import absolute_import

import logging
import os
import re
from datetime import timedelta
from urllib.parse import quote, urlsplit

from flask import g, jsonify, redirect, request, send_from_directory, session

from .auth_middleware import has_permission, is_admin
from .csrf import UNSAFE_METHODS, generate_csrf_token, get_csrf_token, validate_csrf_token
from .http_utils import api_error

logger = logging.getLogger(__name__)

_STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".otf", ".map", ".mp4", ".webm",
}

# Asset file/download responses may be cached; everything else under /api/
# stays no-store.  The URL carries ?v=<checksum> for invalidation on replace.
_ASSET_FILE_PATH_RE = re.compile(r"^/api/assets/[^/]+/(file|download)$")

_PUBLIC_EXACT = {
    ("GET", "/login"),
    ("HEAD", "/login"),
    ("GET", "/register"),
    ("HEAD", "/register"),
    ("GET", "/api/auth/status"),
    ("HEAD", "/api/auth/status"),
    ("GET", "/api/auth/csrf"),
    ("HEAD", "/api/auth/csrf"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/health"),
    ("HEAD", "/api/health"),
    ("GET", "/favicon.ico"),
}


def _is_api(path):
    return path.startswith("/api/")


def safe_redirect_target(target, default="/"):
    """Reject scheme-relative, absolute and backslash redirect targets."""
    if not target:
        return default
    target = str(target).strip()
    if "\\" in target or not target.startswith("/") or target.startswith("//"):
        return default
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return default
    if target.startswith("/api/"):
        return default
    return target


def _json_error(code, message, status_code):
    payload, status = api_error(code, message, status_code=status_code)
    return jsonify(payload), status


def _is_public_request(method, path):
    if (method, path) in _PUBLIC_EXACT:
        return True
    if path.startswith("/web/"):
        ext = os.path.splitext(path)[1].lower()
        return ext in _STATIC_EXTENSIONS
    return False


def _is_static_bypass(path):
    """A /web/*.html request must not bypass the protected page routes."""
    return path.startswith("/web/") and path.lower().endswith((".html", ".htm"))


def _forbidden_page(web_root):
    page = os.path.join(web_root, "403.html")
    if os.path.isfile(page):
        return send_from_directory(web_root, "403.html"), 403
    return "403 Forbidden", 403, {"Content-Type": "text/plain; charset=utf-8"}


def install_security(app, cfg, auth_service, web_root):
    """Install central auth/CSRF/session hooks on the Flask app."""
    if cfg.IS_PRODUCTION and not cfg.CSRF_ENABLED:
        raise RuntimeError("CSRF_ENABLED cannot be false in production")

    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(cfg.SESSION_SECURE)
    app.config["SESSION_COOKIE_NAME"] = "aigv_session"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=cfg.SESSION_LIFETIME_DAYS)

    if cfg.TRUST_PROXY:
        try:
            from werkzeug.middleware.proxy_fix import ProxyFix
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        except Exception:
            logger.warning("ProxyFix unavailable; TRUST_PROXY ignored")

    @app.before_request
    def _auth_and_csrf_guard():
        method = request.method.upper()
        path = request.path

        if method == "OPTIONS":
            return None

        if _is_static_bypass(path):
            return "404 Not Found", 404

        # Static JS/CSS/images are public, including login page assets.
        if path.startswith("/web/"):
            if not _is_public_request(method, path):
                return "404 Not Found", 404
            return None

        public = _is_public_request(method, path)
        user = None
        if session.get("auth_uid"):
            user = auth_service.load_current_user(
                session.get("auth_uid"), session.get("auth_session_version", 0)
            )
            if not user:
                # Disabled, deleted, or session_version revoked.
                session.clear()
            else:
                g.current_user = user

        # Authentication is checked before CSRF so anonymous calls to protected
        # APIs receive 401 (the session contract) instead of 403, and protected
        # pages redirect to the login form.  Login/register remain public and
        # are still CSRF-protected below.
        if not public and not user:
            if _is_api(path):
                return _json_error("unauthorized", "请先登录", 401)
            target = path
            if request.query_string:
                target += "?" + request.query_string.decode("utf-8", "replace")
            return redirect("/login?next=" + quote(target, safe="/?=&"))

        # CSRF applies to login/register too, but not to GET token/status.
        if cfg.CSRF_ENABLED and method in UNSAFE_METHODS:
            if not validate_csrf_token():
                return _json_error("csrf_invalid", "CSRF 令牌无效或缺失", 403)

        if public:
            return None

        # Page-level coarse permissions.  Route handlers keep object checks.
        if path in ("/compute-platform", "/compute-platform/hosts"):
            if not has_permission("view_compute", user=user):
                return _forbidden_page(web_root)
        if path.startswith("/admin"):
            if not is_admin(user):
                return _forbidden_page(web_root)

        return None

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/api/"):
            if (
                request.method == "GET"
                and response.status_code == 200
                and _ASSET_FILE_PATH_RE.match(request.path)
            ):
                response.headers["Cache-Control"] = "private, max-age=86400"
            else:
                response.headers["Cache-Control"] = "no-store"
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(413)
    def _request_too_large(error):
        if _is_api(request.path):
            return _json_error("payload_too_large", "上传内容超过大小限制", 413)
        return "413 Payload Too Large", 413

    return app
