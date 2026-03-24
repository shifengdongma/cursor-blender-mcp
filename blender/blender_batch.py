"""
在无头 Blender 中运行的批处理脚本。

调用方式（由后端触发）：

blender -b -P blender_batch.py -- --spec /path/to/scene_spec.json --out /path/to/out_dir

- 根据 scene_spec.json 创建简单场景（地面 + 主体占位 + 相机）。
- 按照 spec 中的 camera_move 生成关键帧（orbit/dolly）。
- 导出 GLB 场景文件和相机路径 JSON。
- 在 out_dir 下写入 artifacts.json，供后端读取。
"""

from __future__ import absolute_import

import json
import math
import os
import sys

import bpy
from mathutils import Vector


def _parse_args(argv):
    """
    解析 Blender 传入的自定义参数（位于 -- 之后）。
    """
    spec_path = None
    out_dir = None

    i = 0
    length = len(argv)
    while i < length:
        arg = argv[i]
        if arg == "--spec" and i + 1 < length:
            spec_path = argv[i + 1]
            i += 2
            continue
        if arg == "--out" and i + 1 < length:
            out_dir = argv[i + 1]
            i += 2
            continue

        i += 1

    if not spec_path or not out_dir:
        raise RuntimeError("Missing --spec or --out arguments")

    return spec_path, out_dir


def _load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_default_scene():
    """
    移除默认立方体/灯光/相机，使用全新场景。
    """
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _build_assets(spec):
    """
    根据 spec["assets"] 创建基础几何体。
    仅使用 PoC 级别的 plane / cube。
    """
    assets = spec.get("assets") or []
    for item in assets:
        kind = (item.get("kind") or "").lower()
        name = item.get("name") or "Object"
        loc = item.get("location") or [0.0, 0.0, 0.0]
        rot = item.get("rotation_euler") or [0.0, 0.0, 0.0]
        scale = item.get("scale") or [1.0, 1.0, 1.0]

        if kind == "plane":
            bpy.ops.mesh.primitive_plane_add(location=loc, rotation=rot)
        elif kind == "cube":
            bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
        else:
            # 其它类型暂不处理
            continue

        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale


def _create_camera(spec):
    """
    创建相机物体并设为场景活动相机。
    """
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    return cam_obj


def _look_at(obj, target):
    """
    让 obj 朝向 target（世界坐标）。
    """
    direction = Vector(target) - obj.location
    if direction.length == 0.0:
        return
    rot_quat = direction.to_track_quat("-Z", "Y")
    obj.rotation_euler = rot_quat.to_euler()


def _animate_camera(camera, spec):
    """
    按照 camera_move 配置为相机打关键帧。
    支持：
    - orbit：围绕目标点做一圈 360 度环绕
    - dolly_in：从远处缓慢推近目标
    - crane_up：保持取景方向，沿 Z 轴缓慢抬升
    - tracking：平视横向跟拍
    - fpv：对角线穿梭
    - macro_pan：近距离微距横移
    - low_angle_glide：低机位贴地滑行
    """
    scene = bpy.context.scene
    move = spec.get("camera_move") or {}

    move_type = (move.get("type") or "orbit").strip()
    fps = int(spec.get("fps") or 24)
    frame_count = int(spec.get("frame_count") or (fps * 4))
    radius = float(move.get("radius_m") or 6.0)
    height = float(move.get("height_m") or 1.6)
    target = move.get("target") or [0.0, 0.0, 1.2]

    # 帧范围设置（从 1 开始）
    scene.frame_start = 1
    scene.frame_end = frame_count
    scene.render.fps = fps

    # 动画过程
    for i in range(frame_count):
        frame = i + 1
        t = float(i) / float(max(1, frame_count - 1))

        if move_type == "dolly_in":
            # 沿着 Y 轴方向从远到近推进
            start_dist = radius
            end_dist = radius * 0.3
            dist = start_dist + (end_dist - start_dist) * t
            camera.location.x = target[0]
            camera.location.y = target[1] - dist
            camera.location.z = target[2] + height
        elif move_type == "crane_up":
            camera.location.x = target[0] + radius * 0.25
            camera.location.y = target[1] - radius * 0.85
            camera.location.z = target[2] + (height * 0.4) + (radius * 0.9 * t)
        elif move_type == "tracking":
            span = radius * 2.0
            camera.location.x = target[0] - radius + (span * t)
            camera.location.y = target[1] - radius * 0.45
            camera.location.z = target[2] + height
        elif move_type == "fpv":
            camera.location.x = target[0] - radius + (radius * 2.0 * t)
            camera.location.y = target[1] - radius + (radius * 2.0 * t)
            camera.location.z = target[2] + (height * 0.8) + (height * 0.4 * t)
        elif move_type == "macro_pan":
            camera.location.x = target[0] - radius * 0.35 + (radius * 0.7 * t)
            camera.location.y = target[1] - radius * 0.22
            camera.location.z = target[2] + height * 0.4
        elif move_type == "low_angle_glide":
            camera.location.x = target[0] - radius * 0.5 + (radius * t)
            camera.location.y = target[1] - radius * 0.95
            camera.location.z = max(0.25, target[2] + height * 0.15)
        else:
            # 默认做 360 度环绕
            angle = 2.0 * math.pi * t
            camera.location.x = target[0] + radius * math.cos(angle)
            camera.location.y = target[1] + radius * math.sin(angle)
            camera.location.z = target[2] + height

        _look_at(camera, target)

        scene.frame_set(frame)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)


def _export_outputs(spec, out_dir, camera):
    """
    导出 GLB 和相机路径 JSON，并写入 artifacts.json。
    """
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    scene_glb_name = "scene.glb"
    scene_glb_path = os.path.join(out_dir, scene_glb_name)

    # 导出 GLB（包含场景几何 + 相机）
    bpy.ops.export_scene.gltf(
        filepath=scene_glb_path,
        export_format="GLB",
        export_cameras=True,
        export_lights=False,
        export_materials="NONE",
    )

    # 导出相机路径（逐帧位置和欧拉角）
    cam_path_name = "camera_path.json"
    cam_path_path = os.path.join(out_dir, cam_path_name)
    scene = bpy.context.scene
    fps = scene.render.fps
    frame_start = scene.frame_start
    frame_end = scene.frame_end

    frames = []
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        loc = list(camera.location)
        rot = list(camera.rotation_euler)
        frames.append(
            {
                "frame": frame,
                "time_s": float(frame - frame_start) / float(max(1, fps)),
                "location": [float(loc[0]), float(loc[1]), float(loc[2])],
                "rotation_euler": [float(rot[0]), float(rot[1]), float(rot[2])],
            }
        )

    with open(cam_path_path, "w", encoding="utf-8") as f:
        json.dump(frames, f, ensure_ascii=False, indent=2)

    artifacts = {
        "scene_glb": scene_glb_name,
        "camera_path": cam_path_name,
        "fps": fps,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "resolution": spec.get("resolution"),
        "title": spec.get("title"),
    }

    artifacts_path = os.path.join(out_dir, "artifacts.json")
    with open(artifacts_path, "w", encoding="utf-8") as f:
        json.dump(artifacts, f, ensure_ascii=False, indent=2)


def main():
    # Blender 启动时 argv 形如：
    # [..., 'blender', '-b', '-P', 'blender_batch.py', '--', '--spec', '...', '--out', '...']
    argv = sys.argv
    if "--" in argv:
        custom_argv = argv[argv.index("--") + 1 :]
    else:
        custom_argv = []

    spec_path, out_dir = _parse_args(custom_argv)
    spec = _load_spec(spec_path)

    _clean_default_scene()
    _build_assets(spec)
    camera = _create_camera(spec)
    _animate_camera(camera, spec)
    _export_outputs(spec, out_dir, camera)


if __name__ == "__main__":
    main()
