#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migrate users from JSON file (data/users.json) to SQLite (auth_users table).
Idempotent - skips already-migrated users.
"""

from __future__ import absolute_import

import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.auth_service import AuthService


def main():
    data_dir = os.environ.get('DATA_DIR', './data')

    print("=" * 50)
    print("Auth Users Migration: JSON -> SQLite")
    print("=" * 50)
    print()

    users_path = os.path.join(data_dir, 'users.json')
    if not os.path.exists(users_path):
        print("No users.json found at: {0}".format(users_path))
        print("Nothing to migrate.")
        return 0

    print("Source: {0}".format(os.path.abspath(users_path)))
    print("Target: {0}".format(os.path.join(data_dir, 'aigv.db')))

    # Load JSON users for preview
    with open(users_path, 'r', encoding='utf-8') as f:
        users = json.load(f)

    print()
    print("JSON users found: {0}".format(len(users)))
    for uid, user in users.items():
        print("  - {0} ({1})".format(user.get('username', 'unknown'), uid[:8]))

    print()
    print("Starting migration...")

    auth_service = AuthService(data_dir)
    stats = auth_service.migrate_json_users()

    print()
    print("Migration Summary:")
    print("  Total in JSON:  {0}".format(stats.get('total', 0)))
    print("  Migrated:       {0}".format(stats.get('migrated', 0)))
    print("  Skipped:        {0}".format(stats.get('skipped', 0)))
    print("  Errors:         {0}".format(stats.get('errors', 0)))
    print()
    print("Migration complete.")

    return 0 if stats.get('errors', 0) == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
