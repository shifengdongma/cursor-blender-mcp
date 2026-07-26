from __future__ import absolute_import

import json
import logging
import os
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)


class AuthService(object):
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.users_path = os.path.join(data_dir, "users.json")
        os.makedirs(data_dir, exist_ok=True)

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

    def get_user_by_username(self, username):
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
        user = {
            "id": user_id,
            "username": username,
            "email": email or "",
            "password_hash": generate_password_hash(password),
            "created_at": os.environ.get("_AUTH_CREATED_AT_OVERRIDE", ""),
        }

        users[user_id] = user
        self._save_users(users)

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        }

    def authenticate_user(self, username, password):
        user = self.get_user_by_username(username)
        if not user:
            return None
        if not check_password_hash(user.get("password_hash", ""), password):
            return None

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user.get("email", ""),
        }
