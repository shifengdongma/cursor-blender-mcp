# -*- coding: utf-8 -*-
"""
Node Agent — lightweight HTTP server exposing system metrics.
Run: python3 agent/node_agent.py
Environment:
  NODE_AGENT_PORT   — listen port (default 8100)
  NODE_AGENT_TOKEN  — Bearer token for auth (required, except /health)
"""
from __future__ import absolute_import

import logging
import os
import sys
import time

# Ensure the project root is on the path so we can import backend.monitoring
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from flask import Flask, jsonify, request
from backend.monitoring.local_collector import MetricsCollector, _check_nvidia_smi, _get_psutil

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[node-agent] %(levelname)s %(message)s')

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

COLLECTOR = MetricsCollector()
NODE_AGENT_TOKEN = os.environ.get('NODE_AGENT_TOKEN', '')
PORT = int(os.environ.get('NODE_AGENT_PORT', '8100'))


def _check_token():
    """Validate Bearer token. Returns True if valid or token not configured."""
    if not NODE_AGENT_TOKEN:
        return True
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:] == NODE_AGENT_TOKEN
    return False


def _error(msg, status_code=401):
    return jsonify({'success': False, 'error': 'unauthorized', 'message': msg}), status_code


@app.route('/health', methods=['GET'])
def health():
    """Basic health check — no auth required."""
    return jsonify({'status': 'ok', 'timestamp': int(time.time())})


@app.route('/metrics', methods=['GET'])
def metrics():
    """Return current system metrics. Requires Bearer token."""
    if not _check_token():
        return _error('Missing or invalid token')
    data = COLLECTOR.collect()
    return jsonify({'success': True, 'data': data})


@app.route('/capabilities', methods=['GET'])
def capabilities():
    """Return node hardware capabilities. Requires Bearer token."""
    if not _check_token():
        return _error('Missing or invalid token')

    has_gpu = _check_nvidia_smi()
    psu = _get_psutil()

    gpu_type = None
    if has_gpu:
        try:
            import subprocess
            r = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=5
            )
            gpu_type = r.stdout.strip().split('\n')[0].strip() if r.stdout.strip() else None
        except Exception:
            gpu_type = None

    cpu_cores = None
    memory_mb = None
    disk_gb = None
    if psu:
        try:
            cpu_cores = psu.cpu_count(logical=False)
            memory_mb = int(psu.virtual_memory().total / (1024 * 1024))
            disk_usage = psu.disk_usage('/')
            disk_gb = int(disk_usage.total / (1024 * 1024 * 1024))
        except (OSError, AttributeError):
            pass

    return jsonify({
        'success': True,
        'data': {
            'gpu': has_gpu,
            'gpu_type': gpu_type,
            'cpu_cores': cpu_cores,
            'memory_mb': memory_mb,
            'disk_gb': disk_gb,
        }
    })


if __name__ == '__main__':
    logger.info("Node Agent starting on port %d", PORT)
    app.run(host='0.0.0.0', port=PORT, debug=False)
