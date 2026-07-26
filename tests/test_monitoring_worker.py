# -*- coding: utf-8 -*-
"""
Tests for MonitoringWorker: lifecycle, metric collection, probes.
"""
from __future__ import absolute_import

import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.monitoring_service import MonitoringWorker


class TestMonitoringWorker:
    """Test monitoring worker lifecycle and operations."""

    def test_worker_creation(self, test_db):
        """Test that monitoring worker can be created."""
        worker = MonitoringWorker(
            interval_s=5,
            monitor_targets='',
            storage_targets='',
        )
        worker.db = test_db
        assert worker is not None
        assert worker._running is False

    def test_worker_start_stop(self, test_db):
        """Test that worker starts and stops gracefully."""
        worker = MonitoringWorker(
            interval_s=1,
            monitor_targets='',
            storage_targets='',
        )
        worker.db = test_db
        worker.start()
        time.sleep(0.5)
        assert worker._running is True
        worker.stop()
        time.sleep(0.5)
        # After stop, running should be False (thread may take a moment)
        assert worker._running is False

    def test_latest_data_structure(self, test_db):
        """Test that latest_data has expected structure."""
        worker = MonitoringWorker(
            interval_s=5,
            monitor_targets='',
            storage_targets='',
        )
        worker.db = test_db
        data = worker.get_latest_data()
        assert 'links' in data
        assert 'samples' in data
        assert 'storage' in data
        assert 'agents' in data
        assert 'cycle_count' in data
