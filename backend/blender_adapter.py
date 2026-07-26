from __future__ import absolute_import

from .blender_runner import BlenderRunnerError, run_blender_export


class BlenderAdapterError(RuntimeError):
    pass


class BlenderExecutionAdapter(object):
    def __init__(self, mode):
        self.mode = (mode or "local_batch").strip().lower()

    def export_scene(self, blender_bin, spec_path, out_dir):
        if self.mode == "local_batch":
            try:
                return run_blender_export(
                    blender_bin=blender_bin,
                    spec_path=spec_path,
                    out_dir=out_dir,
                )
            except BlenderRunnerError as e:
                raise BlenderAdapterError(str(e))

        if self.mode == "mcp_remote":
            raise BlenderAdapterError("已预留远端 MCP Blender 适配层，当前演示版未开启真实联调")

        raise BlenderAdapterError("不支持的 BLENDER_EXECUTION_MODE：{0}".format(self.mode))
