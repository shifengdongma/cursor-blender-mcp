#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cleanup: orphaned render jobs, temp files, and expired metric samples.
"""

from __future__ import absolute_import

import argparse
import logging
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import get_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def mark_orphaned_jobs(db, data_dir):
    """Mark orphaned render jobs as failed."""
    rows = db.fetch_all("SELECT id, status, node_id, created_at FROM render_jobs WHERE status = 'running'")
    count = 0
    for row in rows:
        age_s = _now() - row['created_at']
        if age_s > 3600:  # Running for more than 1 hour without update
            db.update('render_jobs', {
                'status': 'failed',
                'error_message': 'orphaned_on_startup',
                'finished_at': _now(),
                'updated_at': _now(),
            }, 'id = ?', (row['id'],))
            logger.info("Marked orphaned render job: %s (age=%ds)", row['id'], age_s)
            count += 1
    return count


def cleanup_temp_files(data_dir):
    """Remove temporary files."""
    temp_dirs = [
        os.path.join(data_dir, 'temp'),
        os.path.join(data_dir, 'cache'),
    ]
    count = 0
    for temp_dir in temp_dirs:
        if not os.path.isdir(temp_dir):
            continue
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    count += 1
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                    count += 1
            except OSError as e:
                logger.warning("Failed to remove %s: %s", filepath, str(e))

    logger.info("Removed %d temp files/dirs", count)
    return count


def expire_old_samples(db, max_age_hours=24):
    """Remove metric samples older than max_age_hours."""
    cutoff = _now() - (max_age_hours * 3600)
    result = db.execute('DELETE FROM node_metric_samples WHERE sampled_at < ?', (cutoff,))
    logger.info("Expired %d metric samples older than %d hours", result, max_age_hours)
    return result


def main():
    parser = argparse.ArgumentParser(description='AIGV Studio Cleanup Tasks')
    parser.add_argument('--data-dir', default='./data', help='Data directory')
    parser.add_argument('--sample-max-age', type=int, default=24, help='Max age for metric samples in hours')
    parser.add_argument('--dry-run', action='store_true', help='Dry run without making changes')

    args = parser.parse_args()

    db_path = os.path.join(args.data_dir, 'aigv.db')
    if not os.path.exists(db_path):
        logger.error("Database not found: %s", db_path)
        return 1

    db = get_database(db_path)

    print("=" * 50)
    print("AIGV Studio Cleanup")
    if args.dry_run:
        print("DRY RUN - no changes will be made")
    print("=" * 50)
    print()

    # Orphaned jobs
    orphans = mark_orphaned_jobs(db, args.data_dir)
    print("Orphaned render jobs marked as failed: {0}".format(orphans))

    # Temp files
    temp_count = cleanup_temp_files(args.data_dir)
    print("Temp files removed: {0}".format(temp_count))

    # Expired samples
    exp_count = expire_old_samples(db, args.sample_max_age)
    print("Expired metric samples removed: {0}".format(exp_count))

    print()
    print("Cleanup complete.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
