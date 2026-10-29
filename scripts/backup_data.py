#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a consistent SQLite backup plus catalog/job snapshots.

Never copies .env or provider credentials.  Assets are optional because they
can be large; pass ``--include-assets`` to archive data/assets as a tar.gz.

Usage:
    python3 scripts/backup_data.py --data-dir ./data --output ./backups
    python3 scripts/backup_data.py --include-assets
"""
from __future__ import absolute_import

import argparse
import os
import shutil
import sqlite3
import sys
import tarfile
import time


def _backup_sqlite(source, destination):
    src = sqlite3.connect(source)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _archive_tree(source_dir, archive_path):
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source_dir, arcname=os.path.basename(source_dir))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Back up AIGV Studio data")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    parser.add_argument("--output", default="./backups")
    parser.add_argument(
        "--include-assets", action="store_true",
        help="archive data/assets (can be large)",
    )
    args = parser.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir)
    db_path = os.path.join(data_dir, "aigv.db")
    if not os.path.isfile(db_path):
        print("Database not found: {0}".format(db_path), file=sys.stderr)
        return 2

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    dest = os.path.join(os.path.abspath(args.output), "aigv-backup-{0}".format(stamp))
    os.makedirs(dest, exist_ok=True)

    # SQLite's backup API produces a consistent snapshot even while the app is
    # running; copying a live .db file directly can capture a torn WAL state.
    _backup_sqlite(db_path, os.path.join(dest, "aigv.db"))

    for name in ("catalog", "jobs"):
        source = os.path.join(data_dir, name)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(dest, name))

    if args.include_assets:
        assets = os.path.join(data_dir, "assets")
        if os.path.isdir(assets):
            _archive_tree(assets, os.path.join(dest, "assets.tar.gz"))

    print("Backup written to: {0}".format(dest))
    print("Note: .env and provider API keys are intentionally not included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
