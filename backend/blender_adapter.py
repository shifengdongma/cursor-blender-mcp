# -*- coding: utf-8 -*-
"""Blender execution adapter with cancel support and full input spec."""
from __future__ import absolute_import

import logging

from .blender_runner import BlenderRenderTask, BlenderRunnerError, run_blender_export

logger = logging.getLogger(__name__)


class BlenderAdapterError(RuntimeError):
    pass


class BlenderExecutionAdapter(object):
    def __init__(self, mode, config=None):
        self.mode = (mode or "local_batch").strip().lower()
        self.config = config or {}
        self._active_task = None

    def export_scene(self, blender_bin, spec_path, out_dir, input_spec=None):
        if self.mode == "local_batch":
            try:
                task = BlenderRenderTask(
                    blender_bin=blender_bin,
                    spec_path=spec_path,
                    out_dir=out_dir,
                    mode=input_spec.get('mode', 'export') if input_spec else 'export',
                    input_spec=input_spec or {},
                    config=self.config,
                )
                self._active_task = task
                task.execute(input_spec)
                self._active_task = None
                return task.result()
            except BlenderRunnerError as e:
                raise BlenderAdapterError(str(e))

        if self.mode == "mcp_remote":
            raise BlenderAdapterError("MCP remote mode not yet implemented")

        raise BlenderAdapterError("Unsupported BLENDER_EXECUTION_MODE: {0}".format(self.mode))

    def cancel_export(self):
        """Cancel the currently running export."""
        if self._active_task:
            self._active_task.cancel()
            self._active_task = None
