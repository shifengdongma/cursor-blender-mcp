# -*- coding: utf-8 -*-
"""Render service — manages render_jobs table and BlenderRenderTask lifecycle."""
from __future__ import absolute_import

import logging
import os
import threading
import time

from .config import Config
from .database import get_database
from .models import RenderJob, Asset, ComputeNode
from .blender_adapter import BlenderExecutionAdapter
from .ops_service import (
    get_ops_service,
    EVENT_RENDER_STARTED,
    EVENT_RENDER_SUCCEEDED,
    EVENT_RENDER_FAILED,
    EVENT_RENDER_CANCELLED,
    SEVERITY_INFO,
    SEVERITY_ERROR,
)

logger = logging.getLogger(__name__)

# Track active render tasks
_active_tasks = {}
_tasks_lock = threading.Lock()


class RenderService(object):
    """Manages render job lifecycle."""

    def __init__(self, data_dir=None, cfg=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.cfg = cfg or Config()
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._render_threads = {}

    # ── CRUD ──

    def create_render_job(self, tenant_id, project_id, node_id, engine_type,
                          asset_id, input_spec, output_dir=None):
        """Create a render job record and return it."""
        if not output_dir:
            job_id = RenderJob.__init__.__defaults__[0] if False else None
            output_dir = os.path.join(self.data_dir, 'renders', '{0}_{1}'.format(
                tenant_id or 'default', int(time.time())))
        os.makedirs(output_dir, exist_ok=True)

        job = RenderJob(
            tenant_id=tenant_id,
            project_id=project_id,
            node_id=node_id,
            engine_type=engine_type or 'blender_anchor',
            asset_id=asset_id,
            status=RenderJob.STATUS_PENDING,
            progress=0,
            input_spec=input_spec or {},
            output_dir=output_dir,
        )
        self.db.insert(RenderJob.TABLE_NAME, job.to_insert_params())
        logger.info("Created render job %s", job.id)
        return job.to_dict()

    def get_render_job(self, job_id):
        row = self.db.fetch_one('SELECT * FROM render_jobs WHERE id = ?', (job_id,))
        if not row:
            return None
        return RenderJob.from_row(row).to_dict()

    def list_render_jobs(self, tenant_id=None, project_id=None, status=None,
                         limit=50, offset=0):
        where_clauses = []
        params = []
        if tenant_id:
            where_clauses.append('tenant_id = ?')
            params.append(tenant_id)
        if project_id:
            where_clauses.append('project_id = ?')
            params.append(project_id)
        if status:
            where_clauses.append('status = ?')
            params.append(status)

        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
        query = 'SELECT * FROM render_jobs WHERE {0} ORDER BY created_at DESC LIMIT {1} OFFSET {2}'.format(
            where_sql, int(limit), int(offset))
        rows = self.db.fetch_all(query, tuple(params))
        total = self.db.count('render_jobs', where_sql, tuple(params))
        return {
            'items': [RenderJob.from_row(row).to_dict() for row in rows],
            'total': total,
            'limit': int(limit),
            'offset': int(offset),
        }

    # ── Lifecycle ──

    def start_render_job(self, job_id):
        """Start a render job in a background thread."""
        job = self.get_render_job(job_id)
        if not job:
            raise ValueError('Render job not found: {0}'.format(job_id))
        if job.get('status') not in (RenderJob.STATUS_PENDING, RenderJob.STATUS_FAILED):
            raise ValueError('Job cannot be started in status: {0}'.format(job.get('status')))

        # Mark as rendering
        now = int(time.time())
        self.db.update(
            RenderJob.TABLE_NAME,
            {'status': RenderJob.STATUS_RENDERING, 'started_at': now, 'updated_at': now},
            'id = ?',
            (job_id,)
        )

        # Start background thread
        thread = threading.Thread(
            target=self._run_render_background,
            args=(job_id,),
            daemon=True,
            name='render-job-{0}'.format(job_id[:8]),
        )
        self._render_threads[job_id] = thread
        thread.start()

        logger.info("Started render job %s in background", job_id)
        return self.get_render_job(job_id)

    def cancel_render_job(self, job_id):
        """Cancel a running render job."""
        job = self.get_render_job(job_id)
        if not job:
            raise ValueError('Render job not found: {0}'.format(job_id))

        if job.get('status') != RenderJob.STATUS_RENDERING:
            raise ValueError('Can only cancel running jobs')

        # Signal cancellation via the adapter
        with _tasks_lock:
            task = _active_tasks.pop(job_id, None)
        if task:
            task.cancel()

        now = int(time.time())
        self.db.update(
            RenderJob.TABLE_NAME,
            {'status': RenderJob.STATUS_CANCELLED, 'finished_at': now, 'updated_at': now},
            'id = ?',
            (job_id,)
        )

        ops = get_ops_service()
        ops.record_event(
            tenant_id=job.get('tenant_id'),
            project_id=job.get('project_id'),
            job_id=job_id,
            event_type=EVENT_RENDER_CANCELLED,
            severity=SEVERITY_INFO,
            message='Render job cancelled: {0}'.format(job_id),
        )

        return self.get_render_job(job_id)

    def _run_render_background(self, job_id):
        """Background render execution."""
        job = self.get_render_job(job_id)
        if not job:
            return

        ops = get_ops_service()
        ops.record_event(
            tenant_id=job.get('tenant_id'),
            project_id=job.get('project_id'),
            job_id=job_id,
            event_type=EVENT_RENDER_STARTED,
            severity=SEVERITY_INFO,
            message='Render job started: {0}'.format(job_id),
        )

        adapter = BlenderExecutionAdapter(
            mode=self.cfg.BLENDER_EXECUTION_MODE,
            config={
                'FFMPEG_BIN': self.cfg.FFMPEG_BIN,
            },
        )

        spec_path = os.path.join(job.get('output_dir', ''), 'scene_spec.json')
        input_spec = job.get('input_spec') or {}
        input_spec['mode'] = input_spec.get('render_mode', 'final_image')

        try:
            with _tasks_lock:
                _active_tasks[job_id] = adapter._active_task

            adapter.export_scene(
                blender_bin=self.cfg.BLENDER_BIN,
                spec_path=spec_path,
                out_dir=job.get('output_dir', ''),
                input_spec=input_spec,
            )

            now = int(time.time())
            output_files = {
                'dir': job.get('output_dir'),
                'artifacts': os.path.join(job.get('output_dir', ''), 'artifacts.json'),
            }
            # Check for FFmpeg output
            mp4 = os.path.join(job.get('output_dir', ''), 'output.mp4')
            if os.path.exists(mp4):
                output_files['video'] = mp4

            self.db.update(
                RenderJob.TABLE_NAME,
                {
                    'status': RenderJob.STATUS_SUCCEEDED,
                    'progress': 100,
                    'finished_at': now,
                    'updated_at': now,
                    'output_files': __import__('json').dumps(output_files, ensure_ascii=False),
                },
                'id = ?',
                (job_id,)
            )

            ops.record_event(
                tenant_id=job.get('tenant_id'),
                project_id=job.get('project_id'),
                job_id=job_id,
                event_type=EVENT_RENDER_SUCCEEDED,
                severity=SEVERITY_INFO,
                message='Render job succeeded: {0}'.format(job_id),
                metadata={'output_files': output_files},
            )

        except Exception as e:
            now = int(time.time())
            self.db.update(
                RenderJob.TABLE_NAME,
                {
                    'status': RenderJob.STATUS_FAILED,
                    'error_message': str(e)[:500],
                    'finished_at': now,
                    'updated_at': now,
                },
                'id = ?',
                (job_id,)
            )

            ops.record_event(
                tenant_id=job.get('tenant_id'),
                project_id=job.get('project_id'),
                job_id=job_id,
                event_type=EVENT_RENDER_FAILED,
                severity=SEVERITY_ERROR,
                message='Render job failed: {0}'.format(job_id),
                metadata={'error': str(e)[:500]},
            )

        finally:
            with _tasks_lock:
                _active_tasks.pop(job_id, None)

    def get_render_output(self, job_id, filename):
        """Serve a render output file."""
        job = self.get_render_job(job_id)
        if not job:
            raise ValueError('Render job not found')
        filepath = os.path.join(job.get('output_dir', ''), filename)
        if not os.path.exists(filepath):
            raise ValueError('File not found: {0}'.format(filename))
        return filepath


def get_render_service(data_dir=None, cfg=None):
    return RenderService(data_dir, cfg)
