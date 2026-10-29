#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove known demo-seeded rows from an existing database.

Dry-run by default.  Requires --confirm to execute; makes a SQLite backup
first.  Never deletes auth_users or arbitrary user-created data.
"""
from __future__ import absolute_import

import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DEMO_IDS = {
    "tenants": ["tenant_museum_group"],
    "users": ["user_curator_01", "user_pm_01"],
    "projects": ["project_mid_demo"],
    "project_memberships": ["membership_owner_demo", "membership_pm_demo"],
    "resources": ["resource_local_a10", "resource_cloud_a100", "resource_edge_l40"],
    "engine_profiles": [
        "engine_blender_anchor", "engine_ue5_cloud",
        "engine_unity_cloud", "engine_steamvr_stream",
    ],
    "asset_rights": ["rights_gallery_modern", "rights_theater_stage", "rights_museum_warning"],
    "asset_provenance_events": ["prov_gallery_1", "prov_gallery_2", "prov_warning_1"],
    "billing_accounts": ["billing_demo_primary"],
}

DELETE_ORDER = [
    "asset_provenance_events",
    "asset_rights",
    "billing_accounts",
    "project_memberships",
    "resources",
    "engine_profiles",
    "projects",
    "users",
    "tenants",
]


def _backup(db_path, data_dir):
    backup_dir = os.path.join(data_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    target = os.path.join(
        backup_dir, "aigv-before-demo-cleanup-{0}.db".format(time.strftime("%Y%m%d-%H%M%S"))
    )
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


def _counts(db_path):
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        counts = {}
        for table, ids in DEMO_IDS.items():
            try:
                placeholders = ",".join("?" for _ in ids)
                counts[table] = conn.execute(
                    "SELECT COUNT(*) FROM {0} WHERE id IN ({1})".format(table, placeholders),
                    tuple(ids),
                ).fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = 0
        return counts
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remove known AIGV demo data rows.")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--confirm", action="store_true", help="actually delete rows (default: dry-run)")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)

    db_path = os.path.join(args.data_dir, "aigv.db")
    counts = _counts(db_path)
    print("Demo rows found:")
    for table in DELETE_ORDER:
        print("  {0}: {1}".format(table, counts.get(table, 0)))
    if not args.confirm:
        print("Dry-run only. Re-run with --confirm after reviewing the counts.")
        return 0

    if os.path.exists(db_path) and not args.no_backup:
        print("Backup: {0}".format(_backup(db_path, args.data_dir)))

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            # Events may reference the demo tenant/project and would otherwise
            # block FK-protected deletes.
            try:
                conn.execute(
                    "DELETE FROM ops_events WHERE tenant_id = ? OR project_id = ?",
                    ("tenant_museum_group", "project_mid_demo"),
                )
            except sqlite3.OperationalError:
                pass
            for table in DELETE_ORDER:
                ids = DEMO_IDS.get(table, [])
                if not ids:
                    continue
                placeholders = ",".join("?" for _ in ids)
                try:
                    conn.execute(
                        "DELETE FROM {0} WHERE id IN ({1})".format(table, placeholders),
                        tuple(ids),
                    )
                except sqlite3.OperationalError:
                    continue
                except sqlite3.IntegrityError as exc:
                    print(
                        "  skipped {0}: {1}".format(table, exc),
                        file=sys.stderr,
                    )
                    continue
    finally:
        conn.close()
    print("Demo rows removed. Auth users and real user data were not touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
