#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deprecated compatibility wrapper for the v2 auth migration.

Use scripts/migrate_auth_v2.py instead.  This wrapper keeps the old behaviour
(apply with backup) for operators who already have it in runbooks.
"""
from __future__ import absolute_import

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.migrate_auth_v2 import migrate_users_json


def main():
    data_dir = os.environ.get('DATA_DIR', './data')
    print("DEPRECATED: use scripts/migrate_auth_v2.py")
    result = migrate_users_json(data_dir=data_dir, apply=True, backup=True)
    stats = result.get('stats') or {}
    print("  Imported: {0}".format(stats.get('imported', 0)))
    print("  Updated:  {0}".format(stats.get('updated', 0)))
    print("  Skipped:  {0}".format(stats.get('skipped', 0)))
    print("  Errors:   {0}".format(stats.get('errors', 0)))
    return 0 if not stats.get('errors') else 1


if __name__ == '__main__':
    sys.exit(main())
