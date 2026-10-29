# -*- coding: utf-8 -*-
"""Personal profile, password and avatar API."""
from __future__ import absolute_import

import io
import os
import time
import uuid

from flask import g, request, send_file, send_from_directory, session

try:  # Pillow is pinned in requirements.txt; keep startup resilient if absent.
    from PIL import Image
except ImportError:  # pragma: no cover - exercised only in minimal installs
    Image = None

from .auth_service import AuthError
from .database import get_database
from .http_utils import ApiError, parse_json_body, require_fields
from .models import GenerationTask

_ALLOWED_AVATAR_TYPES = {
    "png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "webp": ("image/webp", lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
}


def _avatar_root(cfg):
    return os.path.realpath(os.path.join(cfg.DATA_DIR, "profile_avatars"))


def _resolve_avatar(cfg, rel_path):
    if not rel_path:
        return None
    root = _avatar_root(cfg)
    candidate = os.path.realpath(os.path.join(cfg.DATA_DIR, rel_path))
    if candidate != root and not candidate.startswith(root + os.sep):
        return None
    return candidate


def _avatar_url(user):
    if not user or not user.get("avatar_path"):
        return None
    version = user.get("updated_at") or user.get("created_at") or 0
    return "/api/user/avatar?t={0}".format(version)


def _validate_avatar_image(raw, detected_ext):
    """Decode the image and confirm its real format matches the magic bytes.

    Returns the normalised extension, or None when the file is truncated,
    mislabelled or unreasonably large.  When Pillow is unavailable we still
    reject obviously truncated payloads (missing IEND/EOI, too short).
    """
    if Image is None:
        if len(raw) < 32:
            return None
        if detected_ext == "png" and b"IEND" not in raw[-32:]:
            return None
        if detected_ext == "jpg" and not raw.rstrip(b"\x00").endswith(b"\xff\xd9"):
            return None
        if detected_ext == "webp":
            if len(raw) < 30 or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
                return None
            declared = int.from_bytes(raw[4:8], "little") + 8
            if declared > len(raw) + 2:
                return None
        return detected_ext
    format_map = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
    try:
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            actual_ext = format_map.get((image.format or "").upper())
            image.verify()
    except Exception:
        return None
    if actual_ext != detected_ext:
        return None
    if width < 1 or height < 1 or width > 4096 or height > 4096:
        return None
    if width * height > 16 * 1024 * 1024:
        return None
    return actual_ext


def _audit(cfg, action, user, target_type=None, target_id=None, result="success", metadata=None):
    if not getattr(cfg, "AUDIT_ENABLED", True):
        return None
    try:
        from .audit_service import get_audit_service
        get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=(user or {}).get("id"),
            tenant_id=(user or {}).get("tenant_id"),
            project_id=None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            metadata=metadata,
            request_id=getattr(g, "request_id", None),
        )
    except Exception:
        pass


def _profile_stats(user_id):
    db = get_database()
    base = (
        "FROM generation_tasks t LEFT JOIN creative_projects p "
        "ON p.id = t.creative_project_id "
        "WHERE (t.created_by = ? OR p.user_id = ?)"
    )
    params = (user_id, user_id)
    total = db.fetch_one("SELECT COUNT(*) AS cnt " + base, params)["cnt"]
    images = db.fetch_one(
        "SELECT COUNT(*) AS cnt " + base + " AND t.task_type = 'image' AND t.status = 'succeeded'",
        params,
    )["cnt"]
    videos = db.fetch_one(
        "SELECT COUNT(*) AS cnt " + base + " AND t.task_type = 'video' AND t.status = 'succeeded'",
        params,
    )["cnt"]
    running = db.fetch_one(
        "SELECT COUNT(*) AS cnt " + base + " AND t.status IN ('queued','submitting','running')",
        params,
    )["cnt"]
    failed = db.fetch_one(
        "SELECT COUNT(*) AS cnt " + base + " AND t.status IN ('failed','needs_review')",
        params,
    )["cnt"]
    projects = db.count("creative_projects", "user_id = ?", (user_id,))
    assets = db.count("assets", "owner_user_id = ?", (user_id,))
    recent_rows = db.fetch_all(
        "SELECT DISTINCT t.* " + base + " ORDER BY t.created_at DESC LIMIT 5",
        params,
    )
    recent = []
    for row in recent_rows:
        task = GenerationTask.from_row(row)
        if not task:
            continue
        recent.append(
            {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "stage": task.stage,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "output_asset_id": task.output_asset_id,
                "error_code": task.error_code,
                "error_message": task.error_message,
            }
        )
    return {
        "tasks_total": total,
        "images_completed": images,
        "videos_completed": videos,
        "tasks_running": running,
        "tasks_failed": failed,
        "projects": projects,
        "assets": assets,
        "recent_tasks": recent,
    }


def register_profile_routes(app, cfg, auth_service, web_root, json_success, json_error):
    @app.route("/profile", methods=["GET"])
    def profile_page():
        return send_from_directory(web_root, "profile.html")

    @app.route("/api/user/profile", methods=["GET"])
    def get_profile():
        fresh = auth_service.get_user(g.current_user.get("id"))
        if not fresh:
            session.clear()
            raise ApiError("unauthorized", "账户不存在或已失效，请重新登录", status_code=401)
        payload = auth_service.public_user(fresh)
        payload.update(
            {
                "bio": (fresh or {}).get("bio") or "",
                "avatar_url": _avatar_url(fresh),
                "stats": _profile_stats(g.current_user.get("id")),
            }
        )
        return json_success(payload)

    @app.route("/api/user/profile", methods=["PATCH"])
    def update_profile():
        data = parse_json_body(request)
        updates = {}
        for key in ("nickname", "email", "bio"):
            if key in data:
                updates[key] = data.get(key)
        try:
            fresh = auth_service.update_profile(g.current_user.get("id"), **updates)
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(cfg, "profile_update", g.current_user, target_type="user", target_id=g.current_user.get("id"))
        payload = auth_service.public_user(fresh)
        payload.update({"bio": fresh.get("bio") or "", "avatar_url": _avatar_url(fresh)})
        return json_success(payload, message="个人资料已更新")

    @app.route("/api/user/password", methods=["PUT"])
    def change_password():
        data = parse_json_body(request)
        require_fields(data, ["current_password", "new_password", "confirm_password"])
        if data.get("new_password") != data.get("confirm_password"):
            return json_error("password_mismatch", "两次输入的新密码不一致", status_code=400)
        try:
            auth_service.change_password_for_user(
                g.current_user.get("id"),
                data.get("current_password"),
                data.get("new_password"),
            )
        except AuthError as exc:
            return json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)
        _audit(cfg, "password_change", g.current_user, target_type="user", target_id=g.current_user.get("id"))
        session.clear()
        return json_success({"require_relogin": True}, message="密码已修改，请重新登录")

    @app.route("/api/user/avatar", methods=["GET"])
    def get_avatar():
        fresh = auth_service.get_user(g.current_user.get("id"))
        path = _resolve_avatar(cfg, (fresh or {}).get("avatar_path"))
        if not path or not os.path.isfile(path):
            raise ApiError("avatar_not_found", "未设置头像", status_code=404)
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        mimetype = _ALLOWED_AVATAR_TYPES.get(ext, ("application/octet-stream", None))[0]
        response = send_file(path, mimetype=mimetype, conditional=True)
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    @app.route("/api/user/avatar", methods=["POST"])
    def upload_avatar():
        if "file" not in request.files:
            return json_error("no_file", "缺少头像文件", status_code=400)
        uploaded = request.files["file"]
        max_bytes = cfg.MAX_AVATAR_UPLOAD_MB * 1024 * 1024
        raw = uploaded.read(max_bytes + 1)
        if not raw:
            return json_error("empty_file", "头像文件为空", status_code=400)
        if len(raw) > max_bytes:
            return json_error("file_too_large", "头像不能超过 {0} MB".format(cfg.MAX_AVATAR_UPLOAD_MB), status_code=413)
        detected = None
        for ext, (_mime, matcher) in _ALLOWED_AVATAR_TYPES.items():
            if matcher(raw):
                detected = ext
                break
        if not detected:
            return json_error("invalid_image", "头像仅支持 PNG/JPEG/WebP", status_code=400)
        detected = _validate_avatar_image(raw, detected)
        if not detected:
            return json_error("invalid_image", "头像文件损坏或格式不符", status_code=400)

        user_id = g.current_user.get("id")
        directory = os.path.join(cfg.DATA_DIR, "profile_avatars", user_id)
        os.makedirs(directory, exist_ok=True)
        filename = "{0}.{1}".format(uuid.uuid4(), detected)
        full_path = os.path.join(directory, filename)
        with open(full_path, "wb") as handle:
            handle.write(raw)
        rel_path = os.path.relpath(full_path, cfg.DATA_DIR)

        old = auth_service.get_user(user_id)
        old_path = _resolve_avatar(cfg, (old or {}).get("avatar_path"))
        fresh = auth_service.set_avatar_path(user_id, rel_path)
        if old_path and os.path.isfile(old_path) and os.path.realpath(old_path) != os.path.realpath(full_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        _audit(cfg, "avatar_update", g.current_user, target_type="user", target_id=user_id)
        return json_success(
            {"avatar_url": _avatar_url(fresh), "has_avatar": True},
            message="头像已更新",
        )

    @app.route("/api/user/avatar", methods=["DELETE"])
    def delete_avatar():
        user_id = g.current_user.get("id")
        fresh = auth_service.get_user(user_id)
        path = _resolve_avatar(cfg, (fresh or {}).get("avatar_path"))
        auth_service.set_avatar_path(user_id, None)
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
        _audit(cfg, "avatar_delete", g.current_user, target_type="user", target_id=user_id)
        return json_success({"deleted": True, "has_avatar": False}, message="头像已移除")
