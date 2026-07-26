# -*- coding: utf-8 -*-
"""
Storage Monitor: Disk usage tracking for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import logging
import os
import time

try:
    import shutil
except ImportError:
    shutil = None

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


class StorageMonitor(object):
    """Monitor disk usage across configured storage targets."""

    def __init__(self, storage_targets=''):
        """
        Initialize with comma-separated storage targets.
        Format: "label|path,label|path"
        """
        self.targets = []
        if storage_targets and storage_targets.strip():
            for item in storage_targets.split(','):
                parts = item.strip().split('|')
                if len(parts) >= 2:
                    self.targets.append({
                        'label': parts[0].strip(),
                        'path': parts[1].strip(),
                    })
        else:
            # Default targets
            self.targets = [
                {'label': 'data', 'path': './data'},
                {'label': 'work', 'path': './data/work'},
                {'label': 'jobs', 'path': './data/jobs'},
                {'label': 'assets', 'path': './data/assets'},
            ]

        self._prev_disk_counters = None
        self._prev_sample_time = None

    def collect(self):
        """Collect storage metrics for all targets."""
        targets = []
        seen_devices = {}  # st_dev -> first target label
        total_total = 0
        total_used = 0
        total_free = 0

        for target in self.targets:
            label = target['label']
            path = target['path']

            try:
                if not os.path.exists(path):
                    logger.debug("Storage target path not found: %s", path)
                    targets.append({
                        'label': label, 'path': path,
                        'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0,
                        'usage_pct': 0.0, 'is_writable': False, 'file_count': 0,
                        'exists': False, 'error': 'path_not_found',
                    })
                    continue

                # Get disk usage
                if shutil:
                    usage = shutil.disk_usage(path)
                    total_bytes = usage.total
                    used_bytes = usage.used
                    free_bytes = usage.free
                else:
                    # Fallback: use os.statvfs
                    st = os.statvfs(path)
                    total_bytes = st.f_frsize * st.f_blocks
                    free_bytes = st.f_frsize * st.f_bavail
                    used_bytes = total_bytes - free_bytes

                usage_pct = round((used_bytes / float(total_bytes)) * 100.0, 2) if total_bytes > 0 else 0.0
                is_writable = os.access(path, os.W_OK)

                # Count files (limit depth to prevent slowdown)
                file_count = 0
                try:
                    for _ in os.listdir(path):
                        file_count += 1
                except OSError:
                    pass

                # Detect same-device targets
                try:
                    st_dev = os.stat(path).st_dev
                    same_device_label = seen_devices.get(st_dev)
                    if same_device_label is not None:
                        logger.debug("Path '%s' shares device with '%s', skipping capacity count", label, same_device_label)
                    else:
                        seen_devices[st_dev] = label
                        total_total += total_bytes
                        total_used += used_bytes
                        total_free += free_bytes
                except OSError:
                    total_total += total_bytes
                    total_used += used_bytes
                    total_free += free_bytes

                targets.append({
                    'label': label, 'path': path,
                    'total_bytes': total_bytes, 'used_bytes': used_bytes,
                    'free_bytes': free_bytes, 'usage_pct': usage_pct,
                    'is_writable': is_writable, 'file_count': file_count,
                    'exists': True, 'error': None,
                })

            except Exception as e:
                logger.warning("Failed to collect storage for %s: %s", label, str(e))
                targets.append({
                    'label': label, 'path': path,
                    'total_bytes': 0, 'used_bytes': 0, 'free_bytes': 0,
                    'usage_pct': 0.0, 'is_writable': False, 'file_count': 0,
                    'exists': os.path.exists(path) if path else False,
                    'error': str(e),
                })

        # Calculate read/write bytes from delta
        read_bps = 0
        write_bps = 0
        now = _now()

        if psutil:
            try:
                current_counters = psutil.disk_io_counters()
                if current_counters and self._prev_disk_counters and self._prev_sample_time:
                    delta_t = now - self._prev_sample_time
                    if delta_t > 0:
                        read_bps = int((current_counters.read_bytes - self._prev_disk_counters.read_bytes) / delta_t)
                        write_bps = int((current_counters.write_bytes - self._prev_disk_counters.write_bytes) / delta_t)
                self._prev_disk_counters = current_counters
                self._prev_sample_time = now
            except Exception:
                pass

        total_usage_pct = round((total_used / float(total_total)) * 100.0, 2) if total_total > 0 else 0.0

        return {
            'targets': targets,
            'summary': {
                'total_bytes': total_total,
                'used_bytes': total_used,
                'free_bytes': total_free,
                'usage_pct': total_usage_pct,
                'read_bps': read_bps,
                'write_bps': write_bps,
            },
            'collected_at': now,
        }
