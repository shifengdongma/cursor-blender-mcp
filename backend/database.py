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

        # Demo control plane tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT,
                tier TEXT,
                status TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                name TEXT NOT NULL,
                role TEXT,
                title TEXT,
                status TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                name TEXT NOT NULL,
                code TEXT,
                status TEXT,
                render_mode TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_memberships (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                user_id TEXT,
                tenant_id TEXT,
                role TEXT,
                permissions TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resources (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                node_name TEXT NOT NULL,
                pool_type TEXT,
                region TEXT,
                gpu_type TEXT,
                capacity_units INTEGER,
                queue_depth INTEGER,
                status TEXT,
                utilization_hint REAL,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS resource_allocations (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                resource_id TEXT,
                tenant_id TEXT,
                project_id TEXT,
                decision_reason TEXT,
                allocation_status TEXT,
                snapshot TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (resource_id) REFERENCES resources(id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS engine_profiles (
                id TEXT PRIMARY KEY,
                engine_type TEXT NOT NULL,
                display_name TEXT,
                render_mode TEXT,
                stream_mode TEXT,
                status TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_sessions (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                project_id TEXT,
                engine_profile_id TEXT,
                protocol TEXT,
                bitrate_mbps REAL,
                latency_ms INTEGER,
                fps INTEGER,
                preview_url TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (engine_profile_id) REFERENCES engine_profiles(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_rights (
                id TEXT PRIMARY KEY,
                asset_id TEXT,
                tenant_id TEXT,
                license_type TEXT,
                source_name TEXT,
                approval_status TEXT,
                usage_scope TEXT,
                expires_at INTEGER,
                restrictions TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS asset_provenance_events (
                id TEXT PRIMARY KEY,
                asset_id TEXT,
                tenant_id TEXT,
                event_type TEXT,
                event_summary TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS billing_accounts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                project_id TEXT,
                plan_name TEXT,
                balance REAL,
                currency TEXT,
                status TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS billing_usage_records (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                tenant_id TEXT,
                project_id TEXT,
                amount REAL,
                currency TEXT,
                usage_type TEXT,
                usage_units REAL,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ops_events (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                project_id TEXT,
                job_id TEXT,
                event_type TEXT,
                severity TEXT,
                message TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_venue ON assets(venue_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_prompts_category ON prompt_documents(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_history(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_tenant ON projects(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_resources_status ON resources(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_job ON resource_allocations(job_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stream_job ON stream_sessions(job_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_rights_asset ON asset_rights(asset_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_provenance_asset ON asset_provenance_events(asset_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_billing_project ON billing_usage_records(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ops_project ON ops_events(project_id)')

        # ── Creative Production Tables ──

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS creative_projects (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                project_id TEXT,
                user_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'draft',
                genre TEXT,
                target_duration INTEGER DEFAULT 0,
                concept TEXT,
                requirements TEXT,
                creative_brief TEXT,
                settings TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS storyboard_shots (
                id TEXT PRIMARY KEY,
                creative_project_id TEXT NOT NULL,
                sequence_no INTEGER DEFAULT 0,
                scene_title TEXT,
                scene_description TEXT,
                shot_type TEXT,
                duration_s REAL DEFAULT 0,
                dialogue TEXT,
                voice_id TEXT,
                camera_movement TEXT,
                lighting_mood TEXT,
                environment_detail TEXT,
                character_action TEXT,
                visual_style TEXT,
                prompt_cn TEXT,
                prompt_en TEXT,
                negative_prompt TEXT,
                primary_image_asset_id TEXT,
                video_asset_id TEXT,
                audio_asset_id TEXT,
                srt_path TEXT,
                video_url TEXT,
                status TEXT DEFAULT 'pending',
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generation_tasks (
                id TEXT PRIMARY KEY,
                creative_project_id TEXT,
                task_type TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                stage TEXT,
                progress INTEGER DEFAULT 0,
                params TEXT,
                result_payload TEXT,
                error_code TEXT,
                error_message TEXT,
                target_shot_id TEXT,
                target_asset_id TEXT,
                claimed_at INTEGER,
                completed_at INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                created_by TEXT,
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id),
                FOREIGN KEY (target_shot_id) REFERENCES storyboard_shots(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                creative_project_id TEXT,
                name TEXT NOT NULL,
                artifact_type TEXT,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                asset_id TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (task_id) REFERENCES generation_tasks(id),
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timeline_tracks (
                id TEXT PRIMARY KEY,
                creative_project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                track_type TEXT,
                sequence_no INTEGER DEFAULT 0,
                settings TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timeline_clips (
                id TEXT PRIMARY KEY,
                track_id TEXT,
                creative_project_id TEXT,
                shot_id TEXT,
                asset_id TEXT,
                name TEXT,
                start_time REAL DEFAULT 0,
                duration_s REAL DEFAULT 0,
                trim_in REAL DEFAULT 0,
                trim_out REAL,
                properties TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (track_id) REFERENCES timeline_tracks(id),
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id),
                FOREIGN KEY (shot_id) REFERENCES storyboard_shots(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS export_packages (
                id TEXT PRIMARY KEY,
                creative_project_id TEXT,
                task_id TEXT,
                format TEXT DEFAULT 'zip',
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                manifest TEXT,
                download_url TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                created_by TEXT,
                FOREIGN KEY (creative_project_id) REFERENCES creative_projects(id),
                FOREIGN KEY (task_id) REFERENCES generation_tasks(id)
            )
        ''')

        # Creative production indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_creative_projects_tenant ON creative_projects(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_creative_projects_status ON creative_projects(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_storyboard_shots_project ON storyboard_shots(creative_project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_storyboard_shots_sequence ON storyboard_shots(creative_project_id, sequence_no)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_project ON generation_tasks(creative_project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_type ON generation_tasks(task_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_status ON generation_tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_artifacts_task ON task_artifacts(task_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_export_packages_project ON export_packages(creative_project_id)')

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