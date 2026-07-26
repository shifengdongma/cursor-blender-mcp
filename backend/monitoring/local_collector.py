# -*- coding: utf-8 -*-
"""Local metrics collector using psutil and nvidia-smi."""
from __future__ import absolute_import

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

# Lazy import of psutil — not required at module load so the server can start
# without it; metrics will simply show None for CPU/memory in that case.
_psutil = None


def _get_psutil():
    global _psutil
    if _psutil is None:
        try:
            import psutil
            _psutil = psutil
        except ImportError:
            logger.warning("psutil not installed — CPU/metrics unavailable")
            _psutil = False
    return _psutil if _psutil else None


_NVIDIA_SMI_CACHE = None  # True / False / None (not yet checked)


def _check_nvidia_smi():
    """Check if nvidia-smi is available. Result is cached."""
    global _NVIDIA_SMI_CACHE
    if _NVIDIA_SMI_CACHE is not None:
        return _NVIDIA_SMI_CACHE
    try:
        subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        _NVIDIA_SMI_CACHE = True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        _NVIDIA_SMI_CACHE = False
    return _NVIDIA_SMI_CACHE


def _collect_gpu_metrics():
    """Collect GPU metrics via nvidia-smi. Returns dict or None."""
    if not _check_nvidia_smi():
        return None

    try:
        result = subprocess.run(
            [
                'nvidia-smi',
                '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits',
            ],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        lines = result.stdout.strip().split('\n')
        gpu_percents = []
        gpu_mem_percents = []
        gpu_temps = []

        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 4:
                try:
                    gp = float(parts[0])
                    mu = float(parts[1])
                    mt = float(parts[2])
                    gt = float(parts[3])
                    gpu_percents.append(gp)
                    gpu_mem_percents.append((mu / mt * 100) if mt > 0 else 0)
                    gpu_temps.append(gt)
                except (ValueError, ZeroDivisionError):
                    continue

        if not gpu_percents:
            return None

        return {
            'gpu_percent': round(sum(gpu_percents) / len(gpu_percents), 1),
            'gpu_memory_percent': round(sum(gpu_mem_percents) / len(gpu_mem_percents), 1),
            'gpu_temperature': round(sum(gpu_temps) / len(gpu_temps), 1),
        }
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("nvidia-smi call failed: %s", e)
        return None


def _collect_disk_net_metrics(prev_sample=None):
    """Collect disk and network rate metrics using psutil.

    Returns IO counters and net counters. If prev_sample is provided,
    calculates bytes-per-second rates.
    """
    psu = _get_psutil()
    if not psu:
        return {}

    result = {}
    now = time.time()

    try:
        disk_io = psu.disk_io_counters()
        if disk_io and prev_sample and prev_sample.get('_disk_io'):
            elapsed = now - prev_sample.get('_sample_ts', now)
            if elapsed > 0:
                result['disk_read_bps'] = int((disk_io.read_bytes - prev_sample['_disk_io']['read_bytes']) / elapsed)
                result['disk_write_bps'] = int((disk_io.write_bytes - prev_sample['_disk_io']['write_bytes']) / elapsed)
        elif disk_io:
            result['disk_read_bps'] = 0
            result['disk_write_bps'] = 0
        result['_disk_io'] = {'read_bytes': disk_io.read_bytes, 'write_bytes': disk_io.write_bytes} if disk_io else None
    except (OSError, AttributeError) as e:
        logger.debug("disk_io_counters failed: %s", e)

    try:
        net_io = psu.net_io_counters()
        if net_io and prev_sample and prev_sample.get('_net_io'):
            elapsed = now - prev_sample.get('_sample_ts', now)
            if elapsed > 0:
                result['network_rx_bps'] = int((net_io.bytes_recv - prev_sample['_net_io']['bytes_recv']) / elapsed)
                result['network_tx_bps'] = int((net_io.bytes_sent - prev_sample['_net_io']['bytes_sent']) / elapsed)
        elif net_io:
            result['network_rx_bps'] = 0
            result['network_tx_bps'] = 0
        result['_net_io'] = {'bytes_recv': net_io.bytes_recv, 'bytes_sent': net_io.bytes_sent} if net_io else None
    except (OSError, AttributeError) as e:
        logger.debug("net_io_counters failed: %s", e)

    return result


class MetricsCollector(object):
    """Collects system metrics from the local machine.

    GPU metrics are collected via nvidia-smi. When no GPU is present,
    GPU fields return None (not 0, not fake values).
    """

    def __init__(self):
        self._prev_sample = None  # for calculating rate metrics

    def collect(self):
        """Collect current system metrics.

        Returns:
            dict with cpu_percent, memory_percent, gpu_percent (or None),
            gpu_memory_percent (or None), gpu_temperature (or None),
            disk_read_bps, disk_write_bps, network_rx_bps, network_tx_bps,
            latency_ms, packet_loss_percent, running_tasks, collected_at
        """
        psu = _get_psutil()

        metrics = {
            'cpu_percent': None,
            'memory_percent': None,
            'gpu_percent': None,
            'gpu_memory_percent': None,
            'gpu_temperature': None,
            'disk_read_bps': None,
            'disk_write_bps': None,
            'network_rx_bps': None,
            'network_tx_bps': None,
            'latency_ms': None,
            'packet_loss_percent': None,
            'running_tasks': 0,
            'collected_at': int(time.time()),
        }

        # CPU
        if psu:
            try:
                metrics['cpu_percent'] = round(psu.cpu_percent(interval=1), 1)
            except (OSError, AttributeError) as e:
                logger.debug("cpu_percent failed: %s", e)

        # Memory
        if psu:
            try:
                mem = psu.virtual_memory()
                metrics['memory_percent'] = round(mem.percent, 1)
            except (OSError, AttributeError) as e:
                logger.debug("virtual_memory failed: %s", e)

        # GPU
        gpu = _collect_gpu_metrics()
        if gpu:
            metrics.update(gpu)

        # Disk and Network (rate-based, needs previous sample)
        rate_metrics = _collect_disk_net_metrics(self._prev_sample)
        self._prev_sample = rate_metrics
        for key in ('disk_read_bps', 'disk_write_bps', 'network_rx_bps', 'network_tx_bps'):
            if key in rate_metrics:
                metrics[key] = rate_metrics[key]
        if '_sample_ts' not in rate_metrics:
            rate_metrics['_sample_ts'] = time.time()

        # Running tasks (psutil process count)
        if psu:
            try:
                metrics['running_tasks'] = len(psu.pids())
            except (OSError, AttributeError) as e:
                logger.debug("pids failed: %s", e)

        return metrics
