# -*- coding: utf-8 -*-
"""Blender render task runner with progress tracking, cancel support, and FFmpeg."""
from __future__ import absolute_import

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

BLENDER_TIMEOUT = 300


class BlenderRunnerError(RuntimeError):
    pass


# ── Legacy function (backward compat) ──

def run_blender_export(blender_bin, spec_path, out_dir, timeout=None):
    if timeout is None:
        timeout = BLENDER_TIMEOUT
    task = BlenderRenderTask(blender_bin, spec_path, out_dir, mode='export', timeout=timeout)
    task.execute(spec_path)
    return task.result()


# ── New Render Task Class ──

class BlenderRenderTask(object):
    """Encapsulates a single Blender render execution.

    Modes: preview_frame, thumbnail_sequence, final_image, final_animation.

    Progress is tracked via BLENDER_PROGRESS:N lines on stdout.
    """

    MODES = ('preview_frame', 'thumbnail_sequence', 'final_image', 'final_animation', 'export')

    def __init__(self, blender_bin, spec_path, out_dir, mode='export',
                 timeout=None, input_spec=None, config=None):
        self.blender_bin = blender_bin
        self.spec_path = spec_path
        self.out_dir = out_dir
        self.mode = mode if mode in self.MODES else 'export'
        self.timeout = timeout or BLENDER_TIMEOUT
        self.input_spec = input_spec or {}
        self.config = config or {}

        self._process = None
        self._progress = 0
        self._status = 'pending'  # pending / running / succeeded / failed / cancelled
        self._error = None
        self._result = None
        self._cancel_event = threading.Event()
        self._progress_callback = None
        self._stdout_lines = []
        self._stderr_lines = []

        os.makedirs(self.out_dir, exist_ok=True)

    @property
    def progress(self):
        return self._progress

    @property
    def status(self):
        return self._status

    def set_progress_callback(self, cb):
        """Set a callable to receive progress updates: cb(progress_0_100)."""
        self._progress_callback = cb

    def execute(self, input_spec=None, progress_callback=None):
        """Execute the Blender render. Returns True on success."""
        if input_spec:
            self.input_spec = input_spec
        if progress_callback:
            self._progress_callback = progress_callback

        # Write input spec to file for the Blender script
        spec_data = dict(self.input_spec)
        spec_data['mode'] = self.mode
        spec_data['output_dir'] = self.out_dir

        if self.spec_path:
            with open(self.spec_path, 'w', encoding='utf-8') as f:
                json.dump(spec_data, f, ensure_ascii=False)

        script_path = os.path.join(os.path.dirname(__file__), "..", "blender", "blender_batch.py")
        script_path = os.path.abspath(script_path)

        cmd = [
            self.blender_bin, "-b", "-P", script_path, "--",
            "--spec", self.spec_path,
            "--out", self.out_dir,
            "--mode", self.mode,
        ]

        logger.info("Starting Blender render: %s", " ".join(cmd))

        self._status = 'running'
        start_time = time.time()

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Read stdout line by line for progress
            for line in iter(self._process.stdout.readline, ''):
                if self._cancel_event.is_set():
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                    self._status = 'cancelled'
                    self._error = 'Task cancelled by user'
                    return False

                self._stdout_lines.append(line)
                line_stripped = line.strip()

                # Parse BLENDER_PROGRESS:N
                if line_stripped.startswith('BLENDER_PROGRESS:'):
                    try:
                        pct = int(line_stripped.split(':')[1])
                        self._progress = min(100, max(0, pct))
                        if self._progress_callback:
                            self._progress_callback(self._progress)
                    except (ValueError, IndexError):
                        pass

                logger.debug("Blender stdout: %s", line_stripped)

            # Capture stderr
            self._stderr_lines = self._process.stderr.read().splitlines()

            returncode = self._process.wait(timeout=10)

            if returncode != 0:
                self._status = 'failed'
                self._error = self._stderr_lines[-3:] if self._stderr_lines else ['Unknown error']
                logger.error("Blender failed with exit code %d", returncode)
                return False

            # Run FFmpeg composition for final_animation mode
            if self.mode == 'final_animation':
                self._compose_video()

            self._status = 'succeeded'
            self._progress = 100
            return True

        except FileNotFoundError:
            self._status = 'failed'
            self._error = ['Blender executable not found: {0}'.format(self.blender_bin)]
            return False
        except subprocess.TimeoutExpired:
            self._status = 'failed'
            self._error = ['Execution timed out after {0}s'.format(self.timeout)]
            return False
        except Exception as e:
            self._status = 'failed'
            self._error = [str(e)[:500]]
            return False
        finally:
            # Write log files
            log_dir = os.path.join(self.out_dir, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'stdout.log'), 'w', encoding='utf-8') as f:
                f.writelines(self._stdout_lines)
            with open(os.path.join(log_dir, 'stderr.log'), 'w', encoding='utf-8') as f:
                f.writelines(self._stderr_lines)

    def cancel(self):
        """Cancel a running render."""
        if self._process and self._process.poll() is None:
            self._cancel_event.set()
            logger.info("Cancellation requested for Blender task")

    def _compose_video(self):
        """Compose frame sequence into MP4 using FFmpeg."""
        frame_pattern = os.path.join(self.out_dir, 'frame_%04d.png')
        output_video = os.path.join(self.out_dir, 'output.mp4')
        fps = self.input_spec.get('fps', 24)

        ffmpeg = self.config.get('FFMPEG_BIN', 'ffmpeg')
        cmd = [
            ffmpeg, '-y', '-framerate', str(fps), '-i', frame_pattern,
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', output_video
        ]
        logger.info("Composing video: %s", " ".join(cmd))
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception as e:
            logger.warning("FFmpeg composition failed: %s", e)

    def result(self):
        """Get the result artifacts dict."""
        artifacts_path = os.path.join(self.out_dir, "artifacts.json")
        if os.path.exists(artifacts_path):
            with open(artifacts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            'status': self._status,
            'output_dir': self.out_dir,
            'error': self._error,
        }
