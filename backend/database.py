# -*- coding: utf-8 -*-
"""
SQLite database connection and ORM wrapper for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger(__name__)


def _now():
    """Return current timestamp as integer."""
    return int(time.time())


class DatabaseError(RuntimeError):
    """Custom database error."""
    pass


class Database(object):
    """
    SQLite database wrapper with thread-safe connection handling.
    Provides basic CRUD operations for AIGV Studio.
    """

    def __init__(self, db_path):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._local = threading.local()

        # Ensure directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Initialize database schema
        self._init_schema()

    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.conn.execute('PRAGMA foreign_keys = ON')
        return self._local.conn

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Assets table (3D models, images, prompt documents)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                venue_type TEXT,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                description TEXT,
                metadata TEXT,
                thumbnail_path TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Prompt documents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompt_documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT,
                content TEXT,
                keywords TEXT,
                source_file TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Venue presets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS venue_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                default_environment TEXT,
                default_lighting TEXT,
                default_style TEXT,
                camera_defaults TEXT,
                negative_prompt_parts TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Model configs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_configs (
                id TEXT PRIMARY KEY,
                display_model TEXT NOT NULL,
                execution_provider TEXT,
                route_mode TEXT,
                status TEXT,
                description TEXT,
                style_hint TEXT,
                recommended INTEGER DEFAULT 0,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Job history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS job_history (
                id TEXT PRIMARY KEY,
                status TEXT,
                stage TEXT,
                payload TEXT,
                result TEXT,
                error TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_venue ON assets(venue_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_prompts_category ON prompt_documents(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_history(status)')

        conn.commit()
        logger.info("Database schema initialized at %s", self.db_path)

    def execute(self, query, params=None):
        """
        Execute a query and return affected row count.

        Args:
            query: SQL query string
            params: Query parameters tuple or list

        Returns:
            int: Number of affected rows
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount

    def execute_many(self, query, params_list):
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples

        Returns:
            int: Number of affected rows
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount

    def fetch_one(self, query, params=None):
        """
        Execute a query and fetch one result.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            dict: Result row as dictionary or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def fetch_all(self, query, params=None):
        """
        Execute a query and fetch all results.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            list: List of result dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def insert(self, table, data):
        """
        Insert a row into a table.

        Args:
            table: Table name
            data: Dictionary of column values

        Returns:
            int: Number of affected rows
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        query = 'INSERT INTO {0} ({1}) VALUES ({2})'.format(table, columns, placeholders)
        return self.execute(query, tuple(data.values()))

    def update(self, table, data, where_clause, where_params=None):
        """
        Update rows in a table.

        Args:
            table: Table name
            data: Dictionary of column values to update
            where_clause: WHERE clause (without 'WHERE')
            where_params: Parameters for WHERE clause

        Returns:
            int: Number of affected rows
        """
        set_clause = ', '.join(['{0} = ?'.format(k) for k in data.keys()])
        query = 'UPDATE {0} SET {1} WHERE {2}'.format(table, set_clause, where_clause)
        params = tuple(data.values()) + (where_params or ())
        return self.execute(query, params)

    def delete(self, table, where_clause, where_params=None):
        """
        Delete rows from a table.

        Args:
            table: Table name
            where_clause: WHERE clause (without 'WHERE')
            where_params: Parameters for WHERE clause

        Returns:
            int: Number of affected rows
        """
        query = 'DELETE FROM {0} WHERE {1}'.format(table, where_clause)
        return self.execute(query, where_params)

    def count(self, table, where_clause=None, where_params=None):
        """
        Count rows in a table.

        Args:
            table: Table name
            where_clause: Optional WHERE clause
            where_params: Parameters for WHERE clause

        Returns:
            int: Row count
        """
        if where_clause:
            query = 'SELECT COUNT(*) as cnt FROM {0} WHERE {1}'.format(table, where_clause)
            row = self.fetch_one(query, where_params)
        else:
            query = 'SELECT COUNT(*) as cnt FROM {0}'.format(table)
            row = self.fetch_one(query)
        return row['cnt'] if row else 0

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# Global database instance
_db_instance = None


def get_database(db_path=None):
    """
    Get or create the global database instance.

    Args:
        db_path: Path to database file (only used on first call)

    Returns:
        Database: Global database instance
    """
    global _db_instance
    if _db_instance is None:
        if db_path is None:
            # Default path
            data_dir = os.environ.get('DATA_DIR', './data')
            db_path = os.path.join(data_dir, 'aigv.db')
        _db_instance = Database(db_path)
    return _db_instance


def reset_database():
    """Reset the global database instance (for testing)."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
    _db_instance = None