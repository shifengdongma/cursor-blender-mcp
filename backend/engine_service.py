from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import EngineProfile


class EngineService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def list_engines(self):
        rows = self.db.fetch_all('SELECT * FROM engine_profiles ORDER BY created_at ASC')
        return [EngineProfile.from_row(row).to_dict() for row in rows]

    def get_engine(self, engine_type):
        row = self.db.fetch_one('SELECT * FROM engine_profiles WHERE engine_type = ? ORDER BY created_at ASC LIMIT 1', (engine_type,))
        item = EngineProfile.from_row(row)
        return item.to_dict() if item else None

    def preview_session(self, payload):
        return self.create_session('preview-job', payload)

    def create_session(self, job_id, payload):
        engine_type = payload.get('engine_target') or 'blender_anchor'
        engine = self.get_engine(engine_type)
        render_mode = payload.get('render_mode') or (engine or {}).get('render_mode') or 'cinematic'
        return {
            'job_id': job_id,
            'engine_type': engine_type,
            'display_name': (engine or {}).get('display_name') or engine_type,
            'render_mode': render_mode,
            'session_status': 'prepared',
            'session_id': 'engine-{0}'.format(job_id[:8]),
            'low_latency_ready': engine_type == 'steamvr_stream' or payload.get('stream_profile') == 'low_latency',
            'preview_link': '/demo/engine/{0}'.format(job_id),
            'artifacts': [
                {'label': 'render_manifest.json', 'status': 'ready'},
                {'label': 'frame_preview.png', 'status': 'placeholder'},
            ],
            'metadata': (engine or {}).get('metadata') or {},
            'created_at': int(time.time()),
        }


def get_engine_service(data_dir=None):
    return EngineService(data_dir)
