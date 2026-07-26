#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database initialization script for AIGV Studio.
Creates database schema and optionally seeds initial data.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database, get_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def init_database(db_path, force=False):
    """
    Initialize the database schema.

    Args:
        db_path: Path to SQLite database file
        force: If True, recreate database even if it exists
    """
    # Check if database exists
    if os.path.exists(db_path):
        if force:
            logger.info("Removing existing database: %s", db_path)
            os.remove(db_path)
        else:
            logger.info("Database already exists: %s", db_path)
            return

    # Create database
    logger.info("Creating database: %s", db_path)
    db = Database(db_path)

    # Verify tables
    tables = db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [t['name'] for t in tables]
    logger.info("Created tables: %s", ', '.join(table_names))

    # Create asset directories
    data_dir = os.path.dirname(db_path)
    create_asset_directories(data_dir)

    logger.info("Database initialization complete.")


def create_asset_directories(data_dir):
    """
    Create asset storage directories.

    Args:
        data_dir: Base data directory
    """
    directories = [
        'assets/models/theater',
        'assets/models/gallery',
        'assets/models/museum',
        'assets/models/concert',
        'assets/images/textures',
        'assets/images/previews',
        'assets/images/references',
        'assets/prompts/venues',
        'assets/prompts/shots',
        'assets/prompts/styles',
    ]

    for rel_path in directories:
        full_path = os.path.join(data_dir, rel_path)
        if not os.path.exists(full_path):
            os.makedirs(full_path, exist_ok=True)
            logger.info("Created directory: %s", full_path)


def main():
    parser = argparse.ArgumentParser(
        description='Initialize AIGV Studio database'
    )
    parser.add_argument(
        '--db-path',
        default=None,
        help='Path to SQLite database file (default: ./data/aigv.db)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force recreate database if it exists'
    )

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        data_dir = os.environ.get('DATA_DIR', './data')
        db_path = os.path.join(data_dir, 'aigv.db')

    init_database(db_path, force=args.force)


if __name__ == '__main__':
    main()