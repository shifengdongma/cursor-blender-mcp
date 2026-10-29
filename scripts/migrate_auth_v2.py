#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-time migration of legacy users.json + auth_users into the v2 schema.

Usage:
    python3 scripts/migrate_auth_v2.py                 # dry-run / preflight
    python3 scripts/migrate_auth_v2.py --apply         # backup + migrate
    python3 scripts/migrate_auth_v2.py --data-dir ./data --apply

This script never promotes anyone to platform admin.  Existing JSON accounts
(including accounts named "admin") are imported with role="user".  Create the
first real admin separately with scripts/create_admin.py.
"""
from __future__ import absolute_import

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _now():
    return int(time.time())


def _backup_database(db_path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = os.path.join(backup_dir, "aigv-before-auth-migration-{0}.db".format(stamp))
    source = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


def _backup_users_json(users_path, backup_dir):
    if not os.path.exists(users_path):
        return None
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = os.path.join(backup_dir, "users-before-auth-migration-{0}.json".format(stamp))
    shutil.copy2(users_path, target)
    return target


def _load_json_users(users_path):
    if not os.path.exists(users_path):
        return {}
    try:
        with open(users_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise SystemExit("Cannot read users.json: {0}".format(exc))
    if not isinstance(data, dict):
        raise SystemExit("users.json must be a JSON object keyed by user id")
    return data


def _created_at(value):
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return _now()


def _preflight(db_path, json_users):
    """Read-only preflight. Returns (report, fatal)."""
    report = {
        "json_accounts": len(json_users),
        "db_accounts": 0,
        "conflicts": [],
        "warnings": [],
    }
    if not os.path.exists(db_path):
        report["warnings"].append("database does not exist yet; a fresh v2 database will be created")
        return report, False

    source = sqlite3.connect(db_path)
    source.row_factory = sqlite3.Row
    try:
        try:
            rows = source.execute(
                "SELECT id, username, email FROM auth_users"
            ).fetchall()
        except sqlite3.OperationalError:
            report["warnings"].append("auth_users table does not exist yet; it will be created")
            rows = []
        report["db_accounts"] = len(rows)
        by_username = {}
        by_email = {}
        for row in rows:
            name = (row["username"] or "").strip().lower()
            if name:
                if name in by_username:
                    report["conflicts"].append(
                        "duplicate username in auth_users: {0}".format(row["username"])
                    )
                by_username[name] = row["id"]
            email = (row["email"] or "").strip().lower()
            if email:
                if email in by_email:
                    report["conflicts"].append(
                        "duplicate email in auth_users: {0}".format(row["email"])
                    )
                by_email[email] = row["id"]

        json_names = {}
        json_emails = {}
        for uid, user in json_users.items():
            if not isinstance(user, dict):
                report["conflicts"].append("invalid JSON user record: {0}".format(uid))
                continue
            username = (user.get("username") or "").strip()
            email = (user.get("email") or "").strip()
            if not username:
                report["conflicts"].append("JSON account missing username: {0}".format(uid))
                continue
            lower_name = username.lower()
            if lower_name in json_names:
                report["conflicts"].append(
                    "duplicate username in users.json: {0}".format(username)
                )
            json_names[lower_name] = uid
            if email:
                lower_email = email.lower()
                if lower_email in json_emails:
                    report["conflicts"].append(
                        "duplicate email in users.json: {0}".format(email)
                    )
                json_emails[lower_email] = uid
                if lower_email in by_email and by_email[lower_email] != uid:
                    report["conflicts"].append(
                        "email already belongs to another auth user: {0}".format(email)
                    )
            if lower_name in by_username and by_username[lower_name] != uid:
                report["conflicts"].append(
                    "username already exists in SQLite with a different id: {0}".format(username)
                )
            if not (user.get("password_hash") or "").startswith(("pbkdf2:", "scrypt:")):
                report["warnings"].append(
                    "unrecognised password hash format for {0}; record will be imported but login needs an upgrade".format(username)
                )
    finally:
        source.close()
    return report, bool(report["conflicts"])


def _migrate(db, json_users, report):
    from backend.database import get_database  # noqa: F401  (db already initialised)
    from backend.identity_service import ensure_platform_tenant, provision_business_identity

    tenant_id = os.environ.get("PLATFORM_TENANT_ID", "tenant_platform")
    stats = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "provisioned": 0,
        "errors": 0,
    }

    with db.transaction() as cursor:
        ensure_platform_tenant(cursor, tenant_id)

        # First, normalise/link existing SQLite accounts.
        cursor.execute("SELECT * FROM auth_users")
        for row in cursor.fetchall():
            user_id = row["id"]
            changes = []
            params = []
            if not row["nickname"]:
                changes.append("nickname = ?")
                params.append(row["username"])
            if not row["role"]:
                changes.append("role = 'user'")
            if not row["status"]:
                changes.append("status = ?")
                params.append("active" if row["is_active"] else "disabled")
            if row["session_version"] is None:
                changes.append("session_version = 0")
            if not row["tenant_id"]:
                changes.append("tenant_id = ?")
                params.append(tenant_id)
            if not row["user_id"]:
                changes.append("user_id = ?")
                params.append(user_id)
            if changes:
                changes.append("updated_at = ?")
                params.append(_now())
                params.append(user_id)
                cursor.execute(
                    "UPDATE auth_users SET {0} WHERE id = ?".format(", ".join(changes)),
                    tuple(params),
                )
                stats["updated"] += 1
            provision_business_identity(
                cursor,
                auth_user_id=user_id,
                username=row["username"],
                nickname=row["nickname"] or row["username"],
                tenant_id=tenant_id,
            )
            stats["provisioned"] += 1

        # Import JSON-only accounts.  Existing SQLite records are authoritative.
        for uid, user in json_users.items():
            if not isinstance(user, dict):
                stats["errors"] += 1
                continue
            username = (user.get("username") or "").strip()
            if not username:
                stats["errors"] += 1
                continue
            email = (user.get("email") or "").strip()
            password_hash = user.get("password_hash") or ""
            if not password_hash:
                stats["errors"] += 1
                report["warnings"].append("skipped JSON account without password hash: {0}".format(username))
                continue

            cursor.execute(
                "SELECT id FROM auth_users WHERE username = ? COLLATE NOCASE",
                (username,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                stats["skipped"] += 1
                continue
            if email:
                cursor.execute(
                    "SELECT id FROM auth_users WHERE email = ? COLLATE NOCASE",
                    (email,),
                )
                if cursor.fetchone() is not None:
                    stats["skipped"] += 1
                    report["warnings"].append(
                        "skipped JSON account because email is already used: {0}".format(username)
                    )
                    continue

            user_id = uid or str(uuid.uuid4())
            created = _created_at(user.get("created_at"))
            # Preserve a legacy disabled flag instead of silently enabling the
            # account.  Imported accounts are always ordinary users; platform
            # admin rights must be granted explicitly after migration.
            legacy_active = bool(user.get("is_active", user.get("active", True)))
            legacy_status = str(user.get("status") or "").lower()
            if legacy_status in ("disabled", "active"):
                is_active = 1 if legacy_status == "active" else 0
            else:
                is_active = 1 if legacy_active else 0
            status = "active" if is_active else "disabled"
            try:
                cursor.execute(
                    "INSERT INTO auth_users "
                    "(id, username, email, password_hash, tenant_id, user_id, is_active, "
                    " role, status, session_version, nickname, failed_login_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'user', ?, 0, ?, 0, ?, ?)",
                    (
                        user_id,
                        username,
                        email,
                        password_hash,
                        tenant_id,
                        user_id,
                        is_active,
                        status,
                        username,
                        created,
                        _now(),
                    ),
                )
                provision_business_identity(
                    cursor,
                    auth_user_id=user_id,
                    username=username,
                    nickname=username,
                    tenant_id=tenant_id,
                )
                stats["imported"] += 1
                stats["provisioned"] += 1
            except sqlite3.IntegrityError as exc:
                stats["errors"] += 1
                report["warnings"].append(
                    "could not import {0}: {1}".format(username, exc)
                )
    return stats


def migrate_users_json(data_dir=None, apply=False, backup=True, users_path=None):
    data_dir = data_dir or os.environ.get("DATA_DIR", "./data")
    db_path = os.path.join(data_dir, "aigv.db")
    users_path = users_path or os.path.join(data_dir, "users.json")
    json_users = _load_json_users(users_path)
    report, fatal = _preflight(db_path, json_users)

    print("Auth migration preflight")
    print("  database: {0}".format(db_path))
    print("  users.json: {0} ({1} accounts)".format(users_path, len(json_users)))
    print("  SQLite auth_users: {0}".format(report["db_accounts"]))
    for warning in report["warnings"]:
        print("  WARNING: {0}".format(warning))
    for conflict in report["conflicts"]:
        print("  CONFLICT: {0}".format(conflict))

    if fatal:
        print("Migration stopped: resolve conflicts before applying.")
        return {"report": report, "stats": None, "applied": False}
    if not apply:
        print("Dry-run only. Use --apply to create a backup and migrate.")
        return {"report": report, "stats": None, "applied": False}

    os.makedirs(data_dir, exist_ok=True)
    if backup:
        backup_dir = os.path.join(data_dir, "backups")
        if os.path.exists(db_path):
            print("  backup DB: {0}".format(_backup_database(db_path, backup_dir)))
        print("  backup users.json: {0}".format(_backup_users_json(users_path, backup_dir) or "not present"))

    # Importing get_database initialises the v2 schema (incremental ALTERs).
    from backend.database import get_database, reset_database

    reset_database()
    db = get_database(db_path)
    stats = _migrate(db, json_users, report)

    if os.path.exists(users_path):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        migrated_path = "{0}.migrated.{1}".format(users_path, stamp)
        os.replace(users_path, migrated_path)
        print("  users.json archived to: {0}".format(migrated_path))

    print("Migration complete")
    for key, value in stats.items():
        print("  {0}: {1}".format(key, value))
    return {"report": report, "stats": stats, "applied": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Migrate legacy auth accounts into SQLite v2 schema.")
    parser.add_argument("--apply", action="store_true", help="apply migration after backup")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--no-backup", action="store_true", help="skip backups (not recommended)")
    args = parser.parse_args(argv)
    result = migrate_users_json(
        data_dir=args.data_dir,
        apply=args.apply,
        backup=not args.no_backup,
    )
    if result.get("report", {}).get("conflicts"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
