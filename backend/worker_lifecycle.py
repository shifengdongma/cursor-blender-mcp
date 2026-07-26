# -*- coding: utf-8 -*-
"""
Worker Lifecycle Manager for AIGV Studio.
Graceful startup/shutdown, orphan detection, cleanup.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import atexit
import logging
import os
import signal
import threading
import time

from .database import get_database

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class WorkerManager(object):
    """Manage worker lifecycle: start, stop, graceful shutdown, orphan detection."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._workers = []
        self._shutting_down = False
        self._shutdown_timeout = 30
        self._lock = threading.Lock()

    def register_worker(self, worker_name, start_fn, stop_fn=None):
        """Register a named worker with start/stop functions."""
        self._workers.append({
            'name': worker_name,
            'start_fn': start_fn,
            'stop_fn': stop_fn,
        })

    def start_all(self):
        """Start all registered workers."""
        self._detect_orphans()

        for worker in self._workers:
            try:
                logger.info("Starting worker: %s", worker['name'])
                worker['start_fn']()
            except Exception as e:
                logger.error("Failed to start worker %s: %s", worker['name'], str(e))

        # Register shutdown handlers
        atexit.register(self.shutdown_all)
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._signal_handler)
            except (ValueError, AttributeError):
                pass  # Signal handler not available

    def shutdown_all(self):
        """Gracefully shut down all workers."""
        if self._shutting_down:
            return

        self._shutting_down = True
        logger.info("Starting graceful shutdown...")

        for worker in self._workers:
            try:
                if worker['stop_fn']:
                    logger.info("Stopping worker: %s", worker['name'])
                    worker['stop_fn']()
            except Exception as e:
                logger.error("Error stopping worker %s: %s", worker['name'], str(e))

        # Wait for running jobs to complete
        self._wait_for_running_jobs()

        # Mark orphaned jobs
        self._mark_orphaned_jobs()

        # Cleanup temp files
        self._cleanup_temp_files()

        logger.info("Graceful shutdown complete")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received signal %s, initiating shutdown", signum)
        self.shutdown_all()

    def _detect_orphans(self):
        """Detect orphaned jobs on startup (status=running but process dead)."""
        try:
            rows = self.db.fetch_all(
                "SELECT id, status FROM render_jobs WHERE status = 'running'"
            )
            for row in rows:
                logger.warning("Found orphaned render job on startup: %s", row['id'])
                self.db.update('render_jobs', {
                    'status': 'failed',
                    'error_message': 'orphaned_on_startup',
                    'updated_at': _now(),
                }, 'id = ?', (row['id'],))
        except Exception as e:
            logger.warning("Failed to detect orphans: %s", str(e))

    def _wait_for_running_jobs(self, timeout=None):
        """Wait for running jobs to complete during shutdown."""
        timeout = timeout or self._shutdown_timeout
        start = _now()
        while _now() - start < timeout:
            try:
                running = self.db.count('render_jobs', "status = 'running'")
                if running == 0:
                    break
                time.sleep(1)
            except Exception:
                break

    def _mark_orphaned_jobs(self):
        """Mark jobs that are still running as failed (orphaned)."""
        try:
            rows = self.db.fetch_all(
                "SELECT id FROM render_jobs WHERE status = 'running'"
            )
            for row in rows:
                self.db.update('render_jobs', {
                    'status': 'failed',
                    'error_message': 'worker_shutdown',
                    'updated_at': _now(),
                }, 'id = ?', (row['id'],))
        except Exception as e:
            logger.warning("Failed to mark orphaned jobs: %s", str(e))

    def _cleanup_temp_files(self):
        """Clean up temporary files on shutdown."""
        temp_dirs = [
            os.path.join(self.data_dir, 'temp'),
            os.path.join(self.data_dir, 'cache'),
        ]
        for temp_dir in temp_dirs:
            if not os.path.isdir(temp_dir):
                continue
            try:
                for filename in os.listdir(temp_dir):
                    filepath = os.path.join(temp_dir, filename)
                    try:
                        if os.path.isfile(filepath):
                            os.remove(filepath)
                    except OSError:
                        pass
            except OSError:
                pass


_worker_manager = None


def get_worker_manager(data_dir=None):
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager(data_dir)
    return _worker_manager
