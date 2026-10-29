# -*- coding: utf-8 -*-
"""Stage A: legacy users.json migration."""
from __future__ import absolute_import

import json
import os
import sqlite3
import time

from werkzeug.security import generate_password_hash

from backend.auth_service import AuthService
from scripts.migrate_auth_v2 import migrate_users_json
from tests.support import reset_globals


def _legacy_db(path, existing_username="olduser"):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE auth_users ("
        "id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT, "
        "password_hash TEXT NOT NULL, tenant_id TEXT, user_id TEXT, "
        "is_active INTEGER DEFAULT 1, last_login_at INTEGER, "
        "failed_login_count INTEGER DEFAULT 0, locked_until INTEGER, "
        "created_at INTEGER, updated_at INTEGER)"
    )
    now = int(time.time())
    conn.execute(
        "INSERT INTO auth_users (id, username, email, password_hash, is_active, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 1, ?, ?)",
        ("legacy-existing", existing_username, "old@example.com",
         generate_password_hash("old-password-123", method="pbkdf2:sha256"), now, now),
    )
    conn.commit()
    conn.close()


def test_migrates_json_accounts_with_backup_and_no_admin(tmp_path):
    reset_globals()
    db_path = tmp_path / "aigv.db"
    _legacy_db(db_path)
    users = {
        "json-pbkdf2": {
            "id": "json-pbkdf2", "username": "jsonpbkdf2", "email": "p@example.com",
            "password_hash": generate_password_hash("json-pass-1", method="pbkdf2:sha256"),
            "created_at": "",
        },
        "json-scrypt": {
            "id": "json-scrypt", "username": "jsonscrypt", "email": "s@example.com",
            "password_hash": generate_password_hash("json-pass-2"),
            "created_at": "",
        },
    }
    users_path = tmp_path / "users.json"
    users_path.write_text(json.dumps(users), encoding="utf-8")

    result = migrate_users_json(str(tmp_path), apply=True, backup=True)
    assert result["applied"] is True
    assert result["stats"]["errors"] == 0
    assert result["stats"]["imported"] == 2
    assert not users_path.exists()
    assert list((tmp_path / "backups").glob("aigv-before-auth-migration-*.db"))
    assert list((tmp_path / "backups").glob("users-before-auth-migration-*.json"))

    service = AuthService(str(tmp_path))
    assert service.authenticate("olduser", "old-password-123")["ok"] is True
    assert service.authenticate("jsonpbkdf2", "json-pass-1")["ok"] is True
    assert service.authenticate("jsonscrypt", "json-pass-2")["ok"] is True
    assert service.db.count("auth_users") == 3
    assert service.db.count("users") == 3
    assert service.db.count("projects") == 3
    assert service.db.count("project_memberships") == 3
    assert service.db.fetch_one("SELECT COUNT(*) AS c FROM auth_users WHERE role='admin'")["c"] == 0
    for name in ("olduser", "jsonpbkdf2", "jsonscrypt"):
        user = service.get_user_by_username(name)
        assert user["role"] == "user"
        assert user["tenant_id"] == "tenant_platform"
        assert user["user_id"] == user["id"]


def test_disabled_legacy_account_stays_disabled(tmp_path):
    reset_globals()
    db_path = tmp_path / "aigv.db"
    _legacy_db(db_path)
    users_path = tmp_path / "users.json"
    users_path.write_text(json.dumps({
        "legacy-disabled": {
            "id": "legacy-disabled",
            "username": "legacyoff",
            "password_hash": generate_password_hash("json-pass-3", method="pbkdf2:sha256"),
            "is_active": False,
        }
    }), encoding="utf-8")

    result = migrate_users_json(str(tmp_path), apply=True, backup=False)
    assert result["applied"] is True
    service = AuthService(str(tmp_path))
    user = service.get_user_by_username("legacyoff")
    assert user["status"] == "disabled"
    assert user["is_active"] is False
    auth = service.authenticate("legacyoff", "json-pass-3")
    assert auth["ok"] is False
    assert auth["error_code"] == "account_disabled"


def test_conflicting_usernames_stop_migration(tmp_path):
    reset_globals()
    db_path = tmp_path / "aigv.db"
    _legacy_db(db_path, existing_username="dupe")
    users_path = tmp_path / "users.json"
    users_path.write_text(json.dumps({
        "different-id": {
            "id": "different-id", "username": "DUPE",
            "password_hash": generate_password_hash("password123", method="pbkdf2:sha256"),
        }
    }), encoding="utf-8")

    result = migrate_users_json(str(tmp_path), apply=True, backup=False)
    assert result["applied"] is False
    assert result["report"]["conflicts"]
    assert users_path.exists()
