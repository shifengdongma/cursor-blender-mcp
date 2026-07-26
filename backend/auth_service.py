from __future__ import absolute_import

import json
import logging
import os
import time
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

from .database import get_database

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class AuthService(object):
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.users_path = os.path.join(data_dir, "users.json")
        os.makedirs(data_dir, exist_ok=True)
        self._db = None  # lazy init via _get_db()

    def _get_db(self):
        if self._db is None:
            self._db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        return self._db

    def _load_users(self):
        if not os.path.exists(self.users_path):
            return {}
        try:
            with open(self.users_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (IOError, ValueError):
            logger.warning("Failed to load users file, starting fresh")
            return {}

    def _save_users(self, users):
        with open(self.users_path, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    def _get_user_from_sqlite(self, username):
        """Get user from SQLite auth_users table."""
        try:
            db = self._get_db()
            row = db.fetch_one(
                'SELECT * FROM auth_users WHERE username = ?',
                (username,)
            )
            if row:
                return {
                    'id': row['id'],
                    'username': row['username'],
                    'email': row.get('email', ''),
                    'password_hash': row['password_hash'],
                    'is_active': bool(row.get('is_active', 1)),
                    'failed_login_count': row.get('failed_login_count', 0),
                    'locked_until': row.get('locked_until'),
                    'tenant_id': row.get('tenant_id'),
                    'user_id': row.get('user_id'),
                    'last_login_at': row.get('last_login_at'),
                }
        except Exception as e:
            logger.warning("SQLite auth lookup failed: %s, falling back to JSON", str(e))
        return None

    def _save_user_to_sqlite(self, user_id, username, password_hash, email=''):
        """Insert or update user in SQLite auth_users table."""
        try:
            db = self._get_db()
            existing = db.fetch_one(
                'SELECT id FROM auth_users WHERE username = ?',
                (username,)
            )
            now = _now()
            if existing:
                db.update('auth_users',
                          {'password_hash': password_hash, 'email': email, 'updated_at': now},
                          'id = ?', (existing['id'],))
            else:
                db.insert('auth_users', {
                    'id': user_id,
                    'username': username,
                    'email': email,
                    'password_hash': password_hash,
                    'is_active': 1,
                    'failed_login_count': 0,
                    'locked_until': None,
                    'created_at': now,
                    'updated_at': now,
                })
        except Exception as e:
            logger.warning("Failed to write auth user to SQLite: %s", str(e))

    def get_user_by_username(self, username):
        """Get user - try SQLite first, fall back to JSON."""
        user = self._get_user_from_sqlite(username)
        if user:
            return user
        # Fallback to JSON
        users = self._load_users()
        for user in users.values():
            if user.get("username") == username:
                return user
        return None

    def register_user(self, username, password, email=None):
        existing = self.get_user_by_username(username)
        if existing:
            return None

        users = self._load_users()
        user_id = str(uuid.uuid4())
        password_hash_val = generate_password_hash(password)
        user = {
            "id": user_id,
            "username": username,
            "email": email or "",
            "password_hash": password_hash_val,
            "created_at": os.environ.get("_AUTH_CREATED_AT_OVERRIDE", ""),
        }

        # Dual-write: JSON + SQLite
        users[user_id] = user
        self._save_users(users)
        self._save_user_to_sqlite(user_id, username, password_hash_val, email or '')

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        }

    def authenticate_user(self, username, password):
        """Authenticate with rate limiting - SQLite first, JSON fallback."""
        # Try SQLite first
        user = self._get_user_from_sqlite(username)
        if user:
            # Check if locked
            if user.get('locked_until') and user['locked_until'] > _now():
                logger.warning("Account locked for user: %s", username)
                return None
            if not user.get('is_active', True):
                return None
            if not check_password_hash(user.get("password_hash", ""), password):
                self._record_failed_login(username)
                return None
            self._record_successful_login(username)
            return {
                "id": user["id"],
                "username": user["username"],
                "email": user.get("email", ""),
            }

        # Fallback to JSON
        users = self._load_users()
        for uid, u in users.items():
            if u.get("username") == username:
                if not check_password_hash(u.get("password_hash", ""), password):
                    return None
                # Migrate to SQLite on successful JSON auth
                self._save_user_to_sqlite(
                    uid, username, u.get("password_hash", ""), u.get("email", "")
                )
                return {
                    "id": uid,
                    "username": u["username"],
                    "email": u.get("email", ""),
                }
        return None

    def _record_failed_login(self, username):
        """Record a failed login attempt."""
        try:
            db = self._get_db()
            row = db.fetch_one(
                'SELECT id, failed_login_count FROM auth_users WHERE username = ?',
                (username,)
            )
            if row:
                new_count = row['failed_login_count'] + 1
                locked_until = None
                if new_count >= 5:
                    locked_until = _now() + 300  # 5 minute lockout
                db.update('auth_users', {
                    'failed_login_count': new_count,
                    'locked_until': locked_until,
                    'updated_at': _now(),
                }, 'id = ?', (row['id'],))
        except Exception as e:
            logger.warning("Failed to record failed login: %s", str(e))

    def _record_successful_login(self, username):
        """Record a successful login."""
        try:
            db = self._get_db()
            row = db.fetch_one(
                'SELECT id FROM auth_users WHERE username = ?',
                (username,)
            )
            if row:
                db.update('auth_users', {
                    'failed_login_count': 0,
                    'locked_until': None,
                    'last_login_at': _now(),
                    'updated_at': _now(),
                }, 'id = ?', (row['id'],))
        except Exception as e:
            logger.warning("Failed to record successful login: %s", str(e))

    def change_password(self, username, old_password, new_password):
        """Change password with old password verification."""
        user = self._get_user_from_sqlite(username) or self.get_user_by_username(username)
        if not user:
            return False
        if not check_password_hash(user.get('password_hash', ''), old_password):
            return False
        if len(new_password) < 6:
            return False

        new_hash = generate_password_hash(new_password)

        # Update SQLite
        try:
            db = self._get_db()
            db.update('auth_users', {
                'password_hash': new_hash,
                'updated_at': _now(),
            }, 'username = ?', (username,))
        except Exception as e:
            logger.warning("Failed to update password in SQLite: %s", str(e))

        # Update JSON
        users = self._load_users()
        for uid, u in users.items():
            if u.get('username') == username:
                u['password_hash'] = new_hash
                self._save_users(users)
                break

        return True

    def migrate_json_users(self):
        """Migrate all users from JSON file to SQLite. Idempotent."""
        users = self._load_users()
        stats = {'total': 0, 'migrated': 0, 'skipped': 0, 'errors': 0}
        stats['total'] = len(users)

        for uid, user in users.items():
            username = user.get('username', '')
            if not username:
                stats['errors'] += 1
                continue
            try:
                existing = self._get_user_from_sqlite(username)
                if existing:
                    stats['skipped'] += 1
                    continue
                self._save_user_to_sqlite(
                    uid, username,
                    user.get('password_hash', ''),
                    user.get('email', ''),
                )
                stats['migrated'] += 1
            except Exception as e:
                logger.error("Failed to migrate user %s: %s", username, str(e))
                stats['errors'] += 1

        logger.info("Auth migration complete: %s", stats)
        return stats
