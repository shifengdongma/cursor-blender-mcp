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
from contextlib import contextmanager

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

    def _ensure_column(self, cursor, table, col_name, col_type):
        """Add a column to a table if it doesn't already exist."""
        try:
            cursor.execute('SELECT {0} FROM {1} LIMIT 1'.format(col_name, table))
        except sqlite3.OperationalError:
            cursor.execute('ALTER TABLE {0} ADD COLUMN {1} {2}'.format(table, col_name, col_type))

    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys and sane contention defaults per connection.
            self._local.conn.execute('PRAGMA foreign_keys = ON')
            self._local.conn.execute('PRAGMA busy_timeout = 5000')
            try:
                self._local.conn.execute('PRAGMA journal_mode = WAL')
            except sqlite3.OperationalError:
                logger.warning("Could not enable WAL mode for %s", self.db_path)
        return self._local.conn

    def _init_schema(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Enable WAL mode for better concurrent read/write performance
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA busy_timeout=5000')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT,
                applied_at INTEGER
            )
        ''')
        cursor.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (1, "baseline_schema", _now()),
        )

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

        # ── Cloud Compute Tables (Phase 2) ──

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cloud_accounts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                provider_type TEXT NOT NULL,
                name TEXT NOT NULL,
                region_list TEXT,
                enabled INTEGER DEFAULT 1,
                config_metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compute_nodes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                provider_type TEXT,
                external_id TEXT,
                node_name TEXT NOT NULL,
                host_name TEXT,
                ip_address TEXT,
                region TEXT,
                zone TEXT,
                cluster_name TEXT,
                cpu_cores INTEGER DEFAULT 0,
                memory_mb INTEGER DEFAULT 0,
                disk_gb INTEGER DEFAULT 0,
                gpu_type TEXT,
                gpu_count INTEGER DEFAULT 0,
                gpu_memory_mb INTEGER DEFAULT 0,
                status TEXT DEFAULT 'online',
                schedulable INTEGER DEFAULT 1,
                last_heartbeat_at INTEGER,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS node_metric_samples (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                sampled_at INTEGER NOT NULL,
                cpu_percent REAL,
                memory_percent REAL,
                gpu_percent REAL,
                gpu_memory_percent REAL,
                gpu_temperature REAL,
                disk_read_bps REAL,
                disk_write_bps REAL,
                network_rx_bps REAL,
                network_tx_bps REAL,
                latency_ms REAL,
                packet_loss_percent REAL,
                running_tasks INTEGER DEFAULT 0,
                metadata TEXT,
                FOREIGN KEY (node_id) REFERENCES compute_nodes(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS render_jobs (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                project_id TEXT,
                node_id TEXT,
                engine_type TEXT DEFAULT 'blender_anchor',
                asset_id TEXT,
                status TEXT DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                input_spec TEXT,
                output_dir TEXT,
                output_files TEXT,
                error_message TEXT,
                started_at INTEGER,
                finished_at INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (project_id) REFERENCES projects(id),
                FOREIGN KEY (node_id) REFERENCES compute_nodes(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduler_policies (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                name TEXT NOT NULL,
                policy_type TEXT,
                scoring_weights TEXT,
                rules TEXT,
                enabled INTEGER DEFAULT 1,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_checks (
                id TEXT PRIMARY KEY,
                target_type TEXT,
                target_id TEXT,
                status TEXT DEFAULT 'ok',
                latency_ms REAL,
                error_message TEXT,
                checked_at INTEGER,
                created_at INTEGER
            )
        ''')

        # Cloud compute indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_compute_nodes_status ON compute_nodes(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_compute_nodes_tenant ON compute_nodes(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_metrics_node ON node_metric_samples(node_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_metrics_sampled ON node_metric_samples(node_id, sampled_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_render_jobs_project ON render_jobs(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_health_checks_target ON health_checks(target_type, target_id)')

        # Migration: add new columns to billing_usage_records if they don't exist
        self._ensure_column(cursor, 'billing_usage_records', 'render_job_id', 'TEXT')
        self._ensure_column(cursor, 'billing_usage_records', 'node_id', 'TEXT')
        self._ensure_column(cursor, 'billing_usage_records', 'provider', 'TEXT')
        self._ensure_column(cursor, 'billing_usage_records', 'usage_seconds', 'REAL')
        self._ensure_column(cursor, 'billing_usage_records', 'unit_price', 'REAL')

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

        # ── Phase 3: Alerting & Task Management Tables ──

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_rules (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                rule_type TEXT NOT NULL,
                target_type TEXT,
                metric_name TEXT,
                operator TEXT,
                threshold REAL,
                duration_s INTEGER DEFAULT 30,
                severity TEXT DEFAULT 'warning',
                enabled INTEGER DEFAULT 1,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                rule_id TEXT,
                target_type TEXT,
                target_id TEXT,
                metric_name TEXT,
                current_value REAL,
                threshold_value REAL,
                status TEXT DEFAULT 'open',
                severity TEXT DEFAULT 'warning',
                first_triggered_at INTEGER,
                last_triggered_at INTEGER,
                recovered_at INTEGER,
                closed_at INTEGER,
                acknowledged_by TEXT,
                closed_by TEXT,
                notes TEXT,
                metadata TEXT,
                created_at INTEGER,
                updated_at INTEGER,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_events (
                id TEXT PRIMARY KEY,
                alert_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user_id TEXT,
                message TEXT,
                metadata TEXT,
                created_at INTEGER,
                FOREIGN KEY (alert_id) REFERENCES alerts(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_attempts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                attempt_number INTEGER DEFAULT 1,
                node_id TEXT,
                allocation_id TEXT,
                status TEXT DEFAULT 'pending',
                started_at INTEGER,
                finished_at INTEGER,
                error_message TEXT,
                metadata TEXT,
                created_at INTEGER,
                FOREIGN KEY (job_id) REFERENCES job_history(id),
                FOREIGN KEY (node_id) REFERENCES compute_nodes(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                tenant_id TEXT,
                user_id TEXT,
                is_active INTEGER DEFAULT 1,
                last_login_at INTEGER,
                failed_login_count INTEGER DEFAULT 0,
                locked_until INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                nickname TEXT,
                avatar_path TEXT,
                bio TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                session_version INTEGER NOT NULL DEFAULT 0,
                terms_accepted_at INTEGER
            )
        ''')

        # Per-user AI provider credentials.  Key material is encrypted by
        # backend.credential_service; this table never stores plaintext.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS provider_credentials (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tenant_id TEXT,
                provider TEXT NOT NULL,
                base_url TEXT,
                model TEXT,
                api_key_ciphertext TEXT,
                model_overrides TEXT,
                is_active INTEGER DEFAULT 1,
                last_verified_at INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                UNIQUE(user_id, provider)
            )
        ''')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_provider_credentials_user '
            'ON provider_credentials(user_id)'
        )

        # Incremental migrations for existing databases (never rebuild tables).
        self._ensure_column(cursor, 'auth_users', 'nickname', 'TEXT')
        self._ensure_column(cursor, 'auth_users', 'avatar_path', 'TEXT')
        self._ensure_column(cursor, 'auth_users', 'bio', 'TEXT')
        self._ensure_column(cursor, 'auth_users', 'role', "TEXT NOT NULL DEFAULT 'user'")
        self._ensure_column(cursor, 'auth_users', 'status', "TEXT NOT NULL DEFAULT 'active'")
        self._ensure_column(cursor, 'auth_users', 'session_version', 'INTEGER NOT NULL DEFAULT 0')
        self._ensure_column(cursor, 'auth_users', 'terms_accepted_at', 'INTEGER')
        self._ensure_column(cursor, 'assets', 'owner_user_id', 'TEXT')
        self._ensure_column(cursor, 'assets', 'tenant_id', 'TEXT')
        self._ensure_column(cursor, 'assets', 'visibility', "TEXT DEFAULT 'private'")
        self._ensure_column(cursor, 'assets', 'checksum_sha256', 'TEXT')
        self._ensure_column(cursor, 'storyboard_shots', 'keyframe_asset_id', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'provider', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'model_id', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'provider_job_id', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'provider_status', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'attempt_count', 'INTEGER DEFAULT 0')
        self._ensure_column(cursor, 'generation_tasks', 'max_attempts', 'INTEGER DEFAULT 3')
        self._ensure_column(cursor, 'generation_tasks', 'next_retry_at', 'INTEGER')
        self._ensure_column(cursor, 'generation_tasks', 'lease_expires_at', 'INTEGER')
        self._ensure_column(cursor, 'generation_tasks', 'lease_owner', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'submission_uncertain', 'INTEGER DEFAULT 0')
        self._ensure_column(cursor, 'generation_tasks', 'submission_started_at', 'INTEGER')
        self._ensure_column(cursor, 'generation_tasks', 'poll_error_count', 'INTEGER DEFAULT 0')
        self._ensure_column(cursor, 'generation_tasks', 'last_polled_at', 'INTEGER')
        self._ensure_column(cursor, 'generation_tasks', 'output_asset_id', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'client_request_id', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'cost_estimate', 'REAL')
        self._ensure_column(cursor, 'generation_tasks', 'currency', 'TEXT')
        self._ensure_column(cursor, 'generation_tasks', 'cancel_requested', 'INTEGER DEFAULT 0')
        self._ensure_column(cursor, 'ops_events', 'actor_user_id', 'TEXT')
        self._ensure_column(cursor, 'ops_events', 'request_id', 'TEXT')

        # Normalise legacy auth status/nickname values.
        cursor.execute(
            "UPDATE auth_users SET nickname = username "
            "WHERE nickname IS NULL OR TRIM(nickname) = ''"
        )
        cursor.execute(
            "UPDATE auth_users SET status = CASE WHEN is_active = 0 THEN 'disabled' ELSE 'active' END "
            "WHERE status IS NULL OR TRIM(status) = ''"
        )
        cursor.execute(
            "UPDATE auth_users SET role = 'user' WHERE role IS NULL OR TRIM(role) = ''"
        )
        cursor.execute(
            "UPDATE auth_users SET session_version = 0 WHERE session_version IS NULL"
        )
        cursor.execute(
            "UPDATE assets SET visibility = 'shared' "
            "WHERE owner_user_id IS NULL AND (visibility IS NULL OR visibility = 'private')"
        )

        # Phase 3 indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_rules_tenant ON alert_rules(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_rules_type ON alert_rules(rule_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_target ON alerts(target_type, target_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alert_events_alert ON alert_events(alert_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_attempts_job ON task_attempts(job_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auth_users_username ON auth_users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auth_users_tenant ON auth_users(tenant_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auth_users_role_status ON auth_users(role, status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets(owner_user_id, asset_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_assets_visibility ON assets(visibility)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_creative_projects_user ON creative_projects(user_id, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_created_by ON generation_tasks(created_by, created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_due ON generation_tasks(status, next_retry_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_provider_job ON generation_tasks(provider_job_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_gen_tasks_lease ON generation_tasks(lease_expires_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ops_actor_time ON ops_events(actor_user_id, created_at)')

        # Case-insensitive uniqueness.  These are best-effort here so an old
        # database with case-only duplicates can still start; the migration
        # script reports conflicts before creating the final indexes.
        try:
            cursor.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_username_nocase '
                'ON auth_users(username COLLATE NOCASE)'
            )
        except sqlite3.IntegrityError:
            logger.warning("auth_users has case-insensitive username duplicates; migration required")
        try:
            cursor.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_email_nocase '
                "ON auth_users(email COLLATE NOCASE) "
                "WHERE email IS NOT NULL AND TRIM(email) <> ''"
            )
        except sqlite3.IntegrityError:
            logger.warning("auth_users has case-insensitive email duplicates; migration required")
        try:
            cursor.execute(
                'CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_tasks_idempotency '
                'ON generation_tasks(created_by, client_request_id) '
                'WHERE client_request_id IS NOT NULL AND client_request_id <> \'\''
            )
        except sqlite3.IntegrityError:
            logger.warning("generation_tasks has duplicate client_request_id values")

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

    @contextmanager
    def transaction(self):
        """Run multiple statements atomically on the current thread connection.

        Usage:
            with db.transaction() as cursor:
                cursor.execute(...)

        Do not call db.insert/db.update inside this block; they take the same
        non-reentrant lock.  Use the yielded cursor directly.
        """
        with self._lock:
            conn = self._get_connection()
            if conn.in_transaction:
                conn.rollback()
            cursor = conn.cursor()
            try:
                cursor.execute('BEGIN IMMEDIATE')
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

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

    def execute_with_retry(self, query, params=None, max_retries=3):
        """Execute a query with retry on database locked error."""
        for attempt in range(max_retries):
            try:
                return self.execute(query, params)
            except sqlite3.OperationalError as e:
                if 'locked' in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise

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


def init_database(data_dir=None):
    """Initialise the process-wide database for an application data directory.

    The app factory must call this before constructing services.  Creating two
    apps with different data directories in one process is rejected to avoid
    accidentally writing to the wrong tenant database.
    """
    data_dir = data_dir or os.environ.get('DATA_DIR', './data')
    db_path = os.path.join(data_dir, 'aigv.db')
    global _db_instance
    if _db_instance is not None:
        if os.path.abspath(_db_instance.db_path) != os.path.abspath(db_path):
            raise RuntimeError(
                "Database already initialised at {0} (requested {1}); "
                "call reset_database() between app factories".format(
                    _db_instance.db_path, db_path
                )
            )
        return _db_instance
    return get_database(db_path)


def reset_database():
    """Reset the global database instance (for testing)."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
    _db_instance = None