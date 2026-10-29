# -*- coding: utf-8 -*-
"""SQLite-backed authentication service.

This replaces the old SQLite + users.json dual-write path.  ``users.json`` is
only read by the one-time migration script; it is never an authentication
source at runtime.
"""
from __future__ import absolute_import

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from email.utils import parseaddr

from werkzeug.security import check_password_hash, generate_password_hash

from .database import get_database
from .identity_service import ensure_platform_tenant, provision_business_identity

logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r"^[\w一-鿿.\-]{3,32}$", re.UNICODE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_PASSWORD_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256")


def _now():
    return int(time.time())


class AuthError(RuntimeError):
    """Authentication/validation failure with an API-safe code."""

    def __init__(self, code, message, status_code=400, details=None):
        RuntimeError.__init__(self, message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def normalize_username(username):
    return (username or "").strip()


def normalize_email(email):
    return (email or "").strip()


def validate_username(username):
    username = normalize_username(username)
    if not username:
        raise AuthError("invalid_username", "用户名不能为空", 400)
    if not _USERNAME_RE.match(username):
        raise AuthError(
            "invalid_username",
            "用户名需为 3-32 位，可使用中文、字母、数字、下划线、点和短横线",
            400,
        )
    return username


def validate_nickname(nickname, username):
    nickname = (nickname or "").strip() or username
    if len(nickname) > 40:
        raise AuthError("invalid_nickname", "昵称不能超过 40 个字符", 400)
    if any(ord(ch) < 32 for ch in nickname):
        raise AuthError("invalid_nickname", "昵称包含非法字符", 400)
    return nickname


def validate_email(email):
    email = normalize_email(email)
    if not email:
        return ""
    if len(email) > 254:
        raise AuthError("invalid_email", "邮箱地址过长", 400)
    parsed = parseaddr(email)[1]
    if parsed != email or not _EMAIL_RE.match(email):
        raise AuthError("invalid_email", "请输入有效的邮箱地址", 400)
    return email


class AuthService(object):
    def __init__(self, data_dir=None, config=None):
        self.data_dir = data_dir or os.environ.get("DATA_DIR", "./data")
        self.db = get_database(os.path.join(self.data_dir, "aigv.db"))
        self.config = config
        self.users_path = os.path.join(self.data_dir, "users.json")  # migration only
        self.password_min = int(getattr(config, "PASSWORD_MIN_LENGTH", 8) or 8)
        self.password_max = int(getattr(config, "PASSWORD_MAX_LENGTH", 128) or 128)
        self.max_failures = int(getattr(config, "LOGIN_MAX_FAILURES", 5) or 5)
        self.lockout_seconds = int(getattr(config, "LOGIN_LOCKOUT_SECONDS", 900) or 900)
        self.platform_tenant_id = (
            getattr(config, "PLATFORM_TENANT_ID", None)
            or os.environ.get("PLATFORM_TENANT_ID", "tenant_platform")
        )

    # ── Lookups / serialisation ──

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None

    def _get_row_by_id(self, user_id):
        return self._row(self.db.fetch_one("SELECT * FROM auth_users WHERE id = ?", (user_id,)))

    def _get_row_by_username(self, username):
        return self._row(
            self.db.fetch_one(
                "SELECT * FROM auth_users WHERE username = ? COLLATE NOCASE",
                (normalize_username(username),),
            )
        )

    def _get_row_by_email(self, email):
        email = normalize_email(email)
        if not email:
            return None
        return self._row(
            self.db.fetch_one(
                "SELECT * FROM auth_users WHERE email = ? COLLATE NOCASE",
                (email,),
            )
        )

    @staticmethod
    def _safe_user(row, include_private=False):
        if not row:
            return None
        status = row.get("status") or ("active" if row.get("is_active", 1) else "disabled")
        result = {
            "id": row.get("id"),
            "username": row.get("username"),
            "email": row.get("email") or "",
            "nickname": row.get("nickname") or row.get("username"),
            "role": row.get("role") or "user",
            "status": status,
            "is_active": bool(row.get("is_active", 1)) and status == "active",
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_login_at": row.get("last_login_at"),
            "has_avatar": bool(row.get("avatar_path")),
            "tenant_id": row.get("tenant_id"),
            "user_id": row.get("user_id") or row.get("id"),
        }
        if include_private:
            result.update(
                {
                    "bio": row.get("bio") or "",
                    "avatar_path": row.get("avatar_path"),
                    "session_version": int(row.get("session_version") or 0),
                    "failed_login_count": int(row.get("failed_login_count") or 0),
                    "locked_until": row.get("locked_until"),
                }
            )
        return result

    @staticmethod
    def public_user(user):
        """Remove internal/session fields before returning a user over HTTP."""
        if not user:
            return None
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "nickname": user.get("nickname") or user.get("username"),
            "email": user.get("email") or "",
            "role": user.get("role") or "user",
            "status": user.get("status") or "active",
            "is_active": bool(user.get("is_active", True)),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "last_login_at": user.get("last_login_at"),
            "has_avatar": bool(user.get("has_avatar")),
            "tenant_id": user.get("tenant_id"),
            "user_id": user.get("user_id") or user.get("id"),
        }

    def get_user_by_username(self, username):
        return self._safe_user(self._get_row_by_username(username), include_private=True)

    def get_user(self, user_id):
        return self._safe_user(self._get_row_by_id(user_id), include_private=True)

    def get_user_by_email(self, email):
        return self._safe_user(self._get_row_by_email(email), include_private=True)

    def user_exists(self, username):
        return self._get_row_by_username(username) is not None

    def email_exists(self, email, exclude_user_id=None):
        row = self._get_row_by_email(email)
        if not row:
            return False
        return not exclude_user_id or row.get("id") != exclude_user_id

    # ── Validation ──

    def validate_password(self, password, username=None):
        password = password or ""
        if len(password) < self.password_min:
            raise AuthError(
                "weak_password",
                "密码至少需要 {0} 位字符".format(self.password_min),
                400,
            )
        if len(password) > self.password_max:
            raise AuthError(
                "invalid_password",
                "密码不能超过 {0} 位字符".format(self.password_max),
                400,
            )
        if username and password.lower() == username.lower():
            raise AuthError("weak_password", "密码不能与用户名相同", 400)
        return password

    # ── Registration / admin creation ──

    def register_user(self, username, password, email=None, nickname=None, terms_accepted=False, role="user"):
        return self._create_user(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            terms_accepted=terms_accepted,
            role=role,
            enforce_terms=True,
        )

    def create_user(self, username, password, email=None, nickname=None, role="user"):
        """Internal/admin creation path; never expose this via public registration."""
        return self._create_user(
            username=username,
            password=password,
            email=email,
            nickname=nickname,
            terms_accepted=True,
            role=role,
            enforce_terms=False,
        )

    def _create_user(self, username, password, email=None, nickname=None, terms_accepted=False, role="user", enforce_terms=False):
        username = validate_username(username)
        nickname = validate_nickname(nickname, username)
        email = validate_email(email)
        self.validate_password(password, username)
        if role not in ("user", "admin"):
            raise AuthError("invalid_role", "无效的平台角色", 400)
        if enforce_terms and not terms_accepted:
            raise AuthError("terms_required", "请先同意用户协议", 400)

        if self._get_row_by_username(username):
            raise AuthError("username_taken", "用户名已被占用", 409)
        if email and self._get_row_by_email(email):
            raise AuthError("email_taken", "邮箱已被使用", 409)

        user_id = str(uuid.uuid4())
        now = _now()
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        tenant_id = self.platform_tenant_id

        try:
            with self.db.transaction() as cursor:
                cursor.execute(
                    "SELECT id FROM auth_users WHERE username = ? COLLATE NOCASE",
                    (username,),
                )
                if cursor.fetchone() is not None:
                    raise AuthError("username_taken", "用户名已被占用", 409)
                if email:
                    cursor.execute(
                        "SELECT id FROM auth_users WHERE email = ? COLLATE NOCASE",
                        (email,),
                    )
                    if cursor.fetchone() is not None:
                        raise AuthError("email_taken", "邮箱已被使用", 409)

                ensure_platform_tenant(cursor, tenant_id)
                cursor.execute(
                    "INSERT INTO auth_users "
                    "(id, username, email, password_hash, tenant_id, user_id, is_active, "
                    " role, status, session_version, nickname, terms_accepted_at, "
                    " failed_login_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?, 'active', 0, ?, ?, 0, ?, ?)",
                    (
                        user_id,
                        username,
                        email,
                        password_hash,
                        tenant_id,
                        user_id,
                        role,
                        nickname,
                        now if terms_accepted else None,
                        now,
                        now,
                    ),
                )
                provision = provision_business_identity(
                    cursor,
                    auth_user_id=user_id,
                    username=username,
                    nickname=nickname,
                    tenant_id=tenant_id,
                )
                cursor.execute(
                    "UPDATE auth_users SET tenant_id = ?, user_id = ?, updated_at = ? WHERE id = ?",
                    (provision["tenant_id"], user_id, now, user_id),
                )
        except sqlite3.IntegrityError:
            raise AuthError("username_taken", "用户名或邮箱已被占用", 409)

        logger.info("Created auth user %s (role=%s)", username, role)
        return self._safe_user(self._get_row_by_id(user_id), include_private=True)

    # ── Authentication ──

    def authenticate(self, username, password):
        """Return a structured result; never raises for normal credential errors."""
        username = normalize_username(username)
        password = password or ""
        row = self._get_row_by_username(username)
        if not row:
            # Constant-ish work to avoid a trivial account-existence timing signal.
            check_password_hash(_DUMMY_PASSWORD_HASH, password)
            return {
                "ok": False,
                "error_code": "invalid_credentials",
                "message": "用户名或密码错误",
                "status_code": 401,
            }

        now = _now()
        if row.get("status") == "disabled" or not row.get("is_active", 1):
            return {
                "ok": False,
                "error_code": "account_disabled",
                "message": "账户已被禁用",
                "status_code": 403,
            }
        locked_until = row.get("locked_until")
        if locked_until and int(locked_until) > now:
            retry_after = int(locked_until) - now
            return {
                "ok": False,
                "error_code": "account_locked",
                "message": "账户暂时锁定，请稍后重试",
                "status_code": 423,
                "details": {"retry_after": retry_after},
            }

        if not check_password_hash(row.get("password_hash") or "", password):
            self._record_failed_login(row)
            return {
                "ok": False,
                "error_code": "invalid_credentials",
                "message": "用户名或密码错误",
                "status_code": 401,
            }

        self._record_successful_login(row)
        fresh = self._get_row_by_id(row["id"])
        return {
            "ok": True,
            "user": self._safe_user(fresh, include_private=True),
            "session_version": int(fresh.get("session_version") or 0),
        }

    def authenticate_user(self, username, password):
        """Backward-compatible wrapper used by older callers."""
        result = self.authenticate(username, password)
        return result.get("user") if result.get("ok") else None

    def load_current_user(self, user_id, session_version):
        """Load and revalidate a session user from the database."""
        if not user_id:
            return None
        row = self._get_row_by_id(user_id)
        if not row:
            return None
        if row.get("status") != "active" or not row.get("is_active", 1):
            return None
        if int(row.get("session_version") or 0) != int(session_version or 0):
            return None
        locked_until = row.get("locked_until")
        if locked_until and int(locked_until) > _now():
            return None
        return self._safe_user(row, include_private=True)

    def _record_failed_login(self, row):
        try:
            new_count = int(row.get("failed_login_count") or 0) + 1
            locked_until = row.get("locked_until")
            if new_count >= self.max_failures:
                locked_until = _now() + self.lockout_seconds
            self.db.update(
                "auth_users",
                {
                    "failed_login_count": new_count,
                    "locked_until": locked_until,
                    "updated_at": _now(),
                },
                "id = ?",
                (row["id"],),
            )
        except Exception as exc:
            logger.warning("Failed to record login failure: %s", str(exc))

    def _record_successful_login(self, row):
        try:
            self.db.update(
                "auth_users",
                {
                    "failed_login_count": 0,
                    "locked_until": None,
                    "last_login_at": _now(),
                    "updated_at": _now(),
                },
                "id = ?",
                (row["id"],),
            )
        except Exception as exc:
            logger.warning("Failed to record successful login: %s", str(exc))

    # ── Profile / password ──

    def update_profile(self, user_id, nickname=None, email=None, bio=None):
        row = self._get_row_by_id(user_id)
        if not row:
            raise AuthError("user_not_found", "用户不存在", 404)

        updates = {}
        if nickname is not None:
            updates["nickname"] = validate_nickname(nickname, row.get("username"))
        if email is not None:
            email = validate_email(email)
            if email and self.email_exists(email, exclude_user_id=user_id):
                raise AuthError("email_taken", "邮箱已被使用", 409)
            updates["email"] = email
        if bio is not None:
            bio = str(bio).strip()
            if len(bio) > 500:
                raise AuthError("invalid_bio", "个人简介不能超过 500 个字符", 400)
            updates["bio"] = bio

        if not updates:
            return self._safe_user(row, include_private=True)
        updates["updated_at"] = _now()
        try:
            self.db.update("auth_users", updates, "id = ?", (user_id,))
        except sqlite3.IntegrityError:
            raise AuthError("email_taken", "邮箱已被使用", 409)
        return self._safe_user(self._get_row_by_id(user_id), include_private=True)

    def set_avatar_path(self, user_id, avatar_path):
        self.db.update(
            "auth_users",
            {"avatar_path": avatar_path, "updated_at": _now()},
            "id = ?",
            (user_id,),
        )
        return self._safe_user(self._get_row_by_id(user_id), include_private=True)

    def change_password_for_user(self, user_id, old_password, new_password):
        row = self._get_row_by_id(user_id)
        if not row:
            raise AuthError("user_not_found", "用户不存在", 404)
        self.validate_password(new_password, row.get("username"))
        if not check_password_hash(row.get("password_hash") or "", old_password or ""):
            raise AuthError("invalid_current_password", "当前密码不正确", 400)
        if old_password == new_password:
            raise AuthError("same_password", "新密码不能与当前密码相同", 400)
        new_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
        self.db.update(
            "auth_users",
            {
                "password_hash": new_hash,
                "session_version": int(row.get("session_version") or 0) + 1,
                "updated_at": _now(),
            },
            "id = ?",
            (user_id,),
        )
        return True

    def change_password(self, username, old_password, new_password):
        """Backward-compatible username-based password change."""
        row = self._get_row_by_username(username)
        if not row:
            return False
        try:
            self.change_password_for_user(row["id"], old_password, new_password)
            return True
        except AuthError:
            return False

    def reset_password_for_user(self, user_id, new_password):
        """Operator/CLI recovery path. Never exposed through the web UI."""
        row = self._get_row_by_id(user_id)
        if not row:
            raise AuthError("user_not_found", "用户不存在", 404)
        self.validate_password(new_password, row.get("username"))
        self.db.update(
            "auth_users",
            {
                "password_hash": generate_password_hash(new_password, method="pbkdf2:sha256"),
                "session_version": int(row.get("session_version") or 0) + 1,
                "failed_login_count": 0,
                "locked_until": None,
                "updated_at": _now(),
            },
            "id = ?",
            (user_id,),
        )
        return True

    # ── Admin operations ──

    def count_active_admins(self, cursor=None):
        query = (
            "SELECT COUNT(*) AS cnt FROM auth_users "
            "WHERE role = 'admin' AND status = 'active' AND is_active = 1"
        )
        if cursor is not None:
            row = cursor.execute(query).fetchone()
        else:
            row = self.db.fetch_one(query)
        if row is None:
            return 0
        try:
            return int(row["cnt"])
        except (KeyError, IndexError, TypeError):
            return int(row[0])

    def admin_update_role(self, target_id, new_role, actor_id):
        if new_role not in ("admin", "user"):
            raise AuthError("invalid_role", "无效的平台角色", 400)
        if target_id == actor_id:
            raise AuthError("self_role_change", "不能修改自己的平台角色", 403)
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM auth_users WHERE id = ?", (target_id,))
            target = cursor.fetchone()
            if target is None:
                raise AuthError("user_not_found", "用户不存在", 404)
            if target["role"] == "admin" and new_role != "admin":
                if self.count_active_admins(cursor) <= 1:
                    raise AuthError("last_admin", "不能降级最后一个有效管理员", 409)
            cursor.execute(
                "UPDATE auth_users SET role = ?, session_version = session_version + 1, updated_at = ? WHERE id = ?",
                (new_role, _now(), target_id),
            )
        return self._safe_user(self._get_row_by_id(target_id), include_private=True)

    def admin_update_status(self, target_id, new_status, actor_id):
        if new_status not in ("active", "disabled"):
            raise AuthError("invalid_status", "无效的账户状态", 400)
        if target_id == actor_id:
            raise AuthError("self_status_change", "不能修改自己的账户状态", 403)
        with self.db.transaction() as cursor:
            cursor.execute("SELECT * FROM auth_users WHERE id = ?", (target_id,))
            target = cursor.fetchone()
            if target is None:
                raise AuthError("user_not_found", "用户不存在", 404)
            if new_status == "disabled" and target["role"] == "admin":
                if self.count_active_admins(cursor) <= 1:
                    raise AuthError("last_admin", "不能禁用最后一个有效管理员", 409)
            # Re-enabling an account must also release any temporary lockout,
            # otherwise the user still cannot log in until locked_until expires.
            clear_lock = (
                ", failed_login_count = 0, locked_until = NULL"
                if new_status == "active" else ""
            )
            cursor.execute(
                "UPDATE auth_users SET status = ?, is_active = ?, "
                "session_version = session_version + 1, updated_at = ?{0} WHERE id = ?".format(clear_lock),
                (new_status, 1 if new_status == "active" else 0, _now(), target_id),
            )
        return self._safe_user(self._get_row_by_id(target_id), include_private=True)

    def revoke_sessions(self, user_id):
        row = self._get_row_by_id(user_id)
        if not row:
            raise AuthError("user_not_found", "用户不存在", 404)
        self.db.update(
            "auth_users",
            {"session_version": int(row.get("session_version") or 0) + 1, "updated_at": _now()},
            "id = ?",
            (user_id,),
        )
        return True

    def admin_update_profile(self, target_id, nickname=None, email=None, bio=None):
        return self.update_profile(target_id, nickname=nickname, email=email, bio=bio)

    def list_users(self, q=None, role=None, status=None, limit=50, offset=0):
        conditions = []
        params = []
        if q:
            like = "%{0}%".format(q.strip())
            conditions.append(
                "(username LIKE ? OR nickname LIKE ? OR email LIKE ?)"
            )
            params.extend([like, like, like])
        if role in ("admin", "user"):
            conditions.append("role = ?")
            params.append(role)
        if status in ("active", "disabled"):
            conditions.append("status = ?")
            params.append(status)
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self.db.fetch_all(
            "SELECT * FROM auth_users WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?".format(where),
            tuple(params) + (int(limit), int(offset)),
        )
        total = self.db.count("auth_users", where, tuple(params))
        return {
            "items": [self._safe_user(row) for row in rows],
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
        }

    def admin_stats(self):
        def count(where="1=1", params=None):
            return self.db.count("auth_users", where, params)

        def task_count(where="1=1", params=None):
            return self.db.count("generation_tasks", where, params)

        return {
            "users": {
                "total": count(),
                "active": count("status = 'active' AND is_active = 1"),
                "disabled": count("status = 'disabled' OR is_active = 0"),
                "admins": count("role = 'admin' AND status = 'active' AND is_active = 1"),
            },
            "tasks": {
                "total": task_count(),
                "images": task_count("task_type = 'image'"),
                "videos": task_count("task_type = 'video'"),
                "succeeded": task_count("status = 'succeeded'"),
                "failed": task_count("status = 'failed'"),
                "running": task_count("status IN ('running', 'submitting')"),
                "queued": task_count("status = 'queued'"),
                "needs_review": task_count("status = 'needs_review'"),
            },
            "creative_projects": self.db.count("creative_projects"),
            "assets": self.db.count("assets"),
            "recent_users": [
                self._safe_user(row)
                for row in self.db.fetch_all(
                    "SELECT * FROM auth_users ORDER BY created_at DESC LIMIT 5"
                )
            ],
        }

    # ── Legacy migration helper (prefer scripts/migrate_auth_v2.py) ──

    def migrate_json_users(self):
        from scripts.migrate_auth_v2 import migrate_users_json

        return migrate_users_json(self.data_dir, apply=True)
