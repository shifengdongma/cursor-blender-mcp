"""
Blender 内部运行的 MCP 服务器入口。

运行环境假设：
- Ubuntu 22.04/24.04 + NVIDIA GPU + Blender 4.x
- 已在 Blender 绑定的 Python 解释器中安装：mcp、fastmcp、numpy、opencv-python、pydantic 等

主要能力：
- 列出场景物体（数据驱动）
- 在 Blender 进程内执行 Python 代码（run_python_script）
- 针对少量必须使用 bpy.ops 的操作，封装 robust_operator_execution（带上下文伪造）
- capture_viewport：基于 GPUOffScreen 离屏渲染视口并返回 Base64 JPEG
"""

from __future__ import absolute_import

import base64
import traceback

import bpy
import gpu
import bgl
import cv2
import numpy as np
from mcp.server.fastmcp import FastMCP

from .server_transport import hijacker


# 在任何 Blender 日志输出之前优先劫持 stdout，避免污染 MCP JSON 流
hijacker.hijack()


def get_view3d_context():
    """
    上下文伪造工厂：
    在 headless + Xvfb 环境下，为 bpy.ops 构造一个近似的 VIEW_3D 上下文字典。
    """
    context = bpy.context
    for window in context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        return {
                            "window": window,
                            "screen": screen,
                            "area": area,
                            "region": region,
                            "scene": context.scene,
                            "layer": context.view_layer,
                        }
    return None


mcp = FastMCP("BlenderCloudAgent")


@mcp.tool()
def list_scene_objects() -> str:
    """
    返回当前三维场景中所有物体的基本信息（类型、位置、旋转）。
    建议仅用于调试与结构确认。
    """
    data = {}
    for obj in bpy.data.objects:
        data[obj.name] = {
            "type": obj.type,
            "location": [round(c, 3) for c in obj.location],
            "rotation": [round(c, 3) for c in obj.rotation_euler],
        }
    return str(data)


@mcp.tool()
def run_python_script(code: str) -> str:
    """
    在 Blender 进程内执行一段 Python 代码。

    使用建议：
    - 遵循数据驱动原则：优先通过 bpy.data.* 修改对象/材质参数。
    - 避免调用高风险模块（os、subprocess 等），企业环境可在此处增加 AST 白名单校验。
    """
    try:
        exec(code, globals())
        bpy.context.view_layer.update()
        return "Script executed successfully and dependency graph updated."
    except Exception as e:
        error_msg = "Execution Error: {0}\n{1}".format(e, traceback.format_exc())
        return error_msg


@mcp.tool()
def robust_operator_execution(object_name: str, operator_code: str) -> str:
    """
    通过上下文伪造安全地执行依赖 VIEW_3D 上下文的 bpy.ops 操作。

    参数：
    - object_name: 需要被设为活动对象的名称
    - operator_code: 在 with 上下文中执行的 Python 代码字符串，例如：
        "bpy.ops.mesh.subdivide(number_cuts=2)"
    """
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return "Error: Object '{0}' not found.".format(object_name)

    bpy.context.view_layer.objects.active = obj
    ctx_override = get_view3d_context()
    if not ctx_override:
        return "Fatal: Failed to fabricate View3D context in headless mode."

    try:
        with bpy.context.temp_override(**ctx_override):
            exec(operator_code, globals(), locals())
        return "Contextual operator executed successfully."
    except Exception as e:
        return "Operator execution failure: {0}".format(e)


@mcp.tool()
def capture_viewport(width: int = 1024, height: int = 768) -> str:
    """
    使用 GPUOffScreen 离屏渲染当前相机视角，并以 Base64 JPEG 字符串返回。

    典型用途：
    - Cursor / VLM 读取当前场景布光、构图与遮挡关系，形成视觉反馈闭环。
    """
    context = bpy.context
    scene = context.scene
    camera = scene.camera
    if camera is None:
        return "Error: Scene lacks an active camera."

    offscreen = gpu.types.GPUOffScreen(width, height)

    depsgraph = context.evaluated_depsgraph_get()
    view_matrix = camera.matrix_world.inverted()
    projection_matrix = camera.calc_matrix_camera(depsgraph, x=width, y=height)

    with offscreen.bind():
        bgl.glClear(
            bgl.GL_COLOR_BUFFER_BIT | bgl.GL_DEPTH_BUFFER_BIT
        )
        offscreen.draw_view3d(
            scene=scene,
            view_layer=context.view_layer,
            view3d=context.space_data if hasattr(context, "space_data") else None,
            region=context.region if hasattr(context, "region") else None,
            view_matrix=view_matrix,
            projection_matrix=projection_matrix,
            do_color_management=True,
        )

        buffer = bgl.Buffer(bgl.GL_BYTE, width * height * 4)
        bgl.glReadPixels(
            0, 0, width, height, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer
        )

    image_np = np.frombuffer(buffer, dtype=np.uint8).reshape(
        (height, width, 4)
    )
    image_np = np.flipud(image_np)

    ok, buffer_jpg = cv2.imencode(".jpg", image_np)
    if not ok:
        return "Error: Failed to encode viewport as JPEG."

    b64_str = base64.b64encode(buffer_jpg).decode("utf-8")
    return "data:image/jpeg;base64,{0}".format(b64_str)


if __name__ == "__main__":
    # FastMCP 默认使用 Stdio 作为传输层。
    # 若需要将 JSON 输出改为使用 hijacker.mcp_pipe_fd，可参考 mcp.python-sdk 的自定义 Transport 接口。
    mcp.run()

