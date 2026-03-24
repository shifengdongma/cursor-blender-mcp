from __future__ import absolute_import

import json
import logging
import os
import threading
import time
import uuid

from .blender_adapter import BlenderAdapterError, BlenderExecutionAdapter
from .provider_router import ProviderRouter


# 配置日志
logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def _empty_result():
    return {
        "prompt_bundle": None,
        "knowledge_hits": [],
        "asset_bundle": None,
        "artifacts": None,
        "provider_result": {
            "display_model": None,
            "execution_provider": None,
            "route_mode": None,
            "job_id": None,
            "create": None,
            "done": None,
            "status": None,
        },
        "video_url": None,
        "warnings": [],
    }


def build_initial_result(preview):
    preview = preview or {}
    result = _empty_result()
    result["prompt_bundle"] = preview.get("prompt_bundle")
    result["knowledge_hits"] = preview.get("knowledge_hits") or []
    result["asset_bundle"] = preview.get("asset_bundle")
    result["warnings"] = preview.get("warnings") or []
    result["provider_result"].update(
        {
            "display_model": preview.get("display_model"),
            "execution_provider": preview.get("execution_provider"),
            "route_mode": preview.get("route_mode"),
            "status": "not_submitted",
        }
    )
    return result


class JobStore(object):
    """
    单机内存索引 + 落盘 JSON。
    - jobs/<job_id>/job.json：主记录
    - jobs/<job_id>/scene_spec.json：输入
    - jobs/<job_id>/artifacts.json：Blender 导出产物（可选）
    """

    def __init__(self, jobs_dir):
        self.jobs_dir = jobs_dir
        os.makedirs(self.jobs_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs = {}

    def _job_dir(self, job_id):
        return os.path.join(self.jobs_dir, job_id)

    def _job_path(self, job_id):
        return os.path.join(self._job_dir(job_id), "job.json")

    def create(self, payload, initial_result=None):
        job_id = str(uuid.uuid4())
        d = self._job_dir(job_id)
        os.makedirs(d, exist_ok=True)

        job = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
            "result": initial_result or _empty_result(),
            "payload": payload,
        }
        self._write(job_id, job)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            return job

        path = self._job_path(job_id)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            job = json.load(f)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def update(self, job_id, patch):
        job = self.get(job_id)
        if not job:
            return None
        job.update(patch)
        job["updated_at"] = _now()
        self._write(job_id, job)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def _write(self, job_id, job):
        d = self._job_dir(job_id)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "job.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._job_path(job_id))

    def write_file(self, job_id, filename, content):
        d = self._job_dir(job_id)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def job_file_path(self, job_id, filename):
        return os.path.join(self._job_dir(job_id), filename)


def _to_float(v, default_value):
    try:
        return float(v)
    except Exception:
        return float(default_value)


def _to_int(v, default_value):
    try:
        return int(float(v))
    except Exception:
        return int(default_value)


def _normalize_target(value, fallback):
    if isinstance(value, list) and len(value) == 3:
        return [
            _to_float(value[0], fallback[0]),
            _to_float(value[1], fallback[1]),
            _to_float(value[2], fallback[2]),
        ]
    return fallback


def _default_geometry_for_venue(venue_type):
    if venue_type == "grand_theater":
        return [
            {"kind": "plane", "name": "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [12, 12, 1]},
            {"kind": "cube", "name": "Stage", "location": [0, 1.2, 0.8], "rotation_euler": [0, 0, 0], "scale": [4, 2, 0.8]},
            {"kind": "cube", "name": "Audience", "location": [0, -3.0, 1.1], "rotation_euler": [0, 0, 0], "scale": [6.0, 2.0, 1.1]},
        ]

    if venue_type == "modern_gallery":
        return [
            {"kind": "plane", "name": "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [10, 10, 1]},
            {"kind": "cube", "name": "Pedestal", "location": [1.5, 0.0, 0.7], "rotation_euler": [0, 0, 0], "scale": [0.7, 0.7, 0.7]},
            {"kind": "cube", "name": "WallMass", "location": [-3.5, 0.0, 2.0], "rotation_euler": [0, 0, 0], "scale": [0.2, 4.0, 2.0]},
        ]

    if venue_type == "ancient_museum":
        return [
            {"kind": "plane", "name": "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [12, 12, 1]},
            {"kind": "cube", "name": "ExhibitPedestal", "location": [0.8, 1.2, 0.8], "rotation_euler": [0, 0, 0], "scale": [0.9, 0.9, 0.8]},
            {"kind": "cube", "name": "ColumnMass", "location": [-2.5, -0.5, 2.0], "rotation_euler": [0, 0, 0], "scale": [0.8, 0.8, 2.0]},
        ]

    if venue_type == "concert_hall":
        return [
            {"kind": "plane", "name": "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [11, 11, 1]},
            {"kind": "cube", "name": "CenterStage", "location": [0, 0, 0.5], "rotation_euler": [0, 0, 0], "scale": [2.4, 2.4, 0.5]},
            {"kind": "cube", "name": "SeatTerrace", "location": [0, -3.0, 1.0], "rotation_euler": [0, 0, 0], "scale": [5.4, 1.8, 1.0]},
        ]

    return [
        {"kind": "plane", "name": "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [10, 10, 1]},
        {"kind": "cube", "name": "Subject", "location": [0, 0, 1], "rotation_euler": [0, 0, 0], "scale": [1, 1, 1]},
    ]


def _build_scene_spec(user_input, prompt_bundle, asset_bundle):
    title = (user_input.get("title") or "demo").strip()[:80]
    duration_s = _to_float(user_input.get("duration_s") or 6.0, 6.0)
    fps = max(8, _to_int(user_input.get("fps") or 24, 24))
    frame_count = max(24, int(duration_s * fps))

    resolution = user_input.get("resolution") or [768, 432]
    if not (isinstance(resolution, list) and len(resolution) == 2):
        resolution = [768, 432]

    camera_defaults = (prompt_bundle or {}).get("camera_defaults") or {}
    fallback_target = camera_defaults.get("target") or [0.0, 0.0, 1.2]
    camera_move_type = (
        user_input.get("camera_move_type")
        or user_input.get("shot_type")
        or (prompt_bundle or {}).get("camera_move_type")
        or "orbit"
    )

    camera_move = {
        "type": str(camera_move_type).strip(),
        "duration_s": duration_s,
        "radius_m": _to_float(user_input.get("camera_radius_m") or camera_defaults.get("radius_m") or 6.0, 6.0),
        "height_m": _to_float(user_input.get("camera_height_m") or camera_defaults.get("height_m") or 1.6, 1.6),
        "target": _normalize_target(user_input.get("camera_target"), fallback_target),
    }

    venue_type = (prompt_bundle or {}).get("venue_id") or user_input.get("venue_type") or ""
    assets = (asset_bundle or {}).get("placeholder_geometry") or _default_geometry_for_venue(venue_type)
    modules = (prompt_bundle or {}).get("modules") or {}

    return {
        "title": title,
        "venue_type": venue_type,
        "workflow_mode": (prompt_bundle or {}).get("workflow_mode") or user_input.get("workflow_mode") or "text_to_video",
        "fps": fps,
        "resolution": [int(resolution[0]), int(resolution[1])],
        "frame_count": frame_count,
        "camera_move": camera_move,
        "assets": assets,
        "environment_hint": modules.get("environment") or user_input.get("environment_hint") or "",
        "lighting_hint": modules.get("lighting") or user_input.get("lighting_hint") or "",
        "style_anchor": modules.get("style") or user_input.get("style_anchor") or "",
        "subject_hint": modules.get("subject") or user_input.get("subject_hint") or "",
        "dynamics_hint": modules.get("dynamics") or user_input.get("dynamics_hint") or "",
        "source_asset": {
            "id": (asset_bundle or {}).get("id"),
            "name": (asset_bundle or {}).get("name"),
            "source_type": (asset_bundle or {}).get("source_type"),
            "metadata": (asset_bundle or {}).get("metadata") or {},
        },
    }


def start_job_worker(job_store, job_id, cfg, prompt_orchestrator):
    """
    在后台线程执行完整链路：
    - 生成 Prompt 预览与 knowledge_hits
    - （可选）Blender 导出空间约束资产
    - 调用视频生成 Provider 并轮询直到完成
    """

    def _run():
        result = None
        try:
            logger.info("Starting job worker for job_id=%s", job_id)
            job = job_store.get(job_id)
            if not job:
                logger.error("Job not found: %s", job_id)
                return

            payload = job.get("payload") or {}
            preview = prompt_orchestrator.preview(payload)
            result = build_initial_result(preview)

            job_store.update(
                job_id,
                {
                    "status": "running",
                    "stage": "knowledge_ready",
                    "result": result,
                },
            )

            job_store.write_file(
                job_id,
                "prompt_bundle.json",
                json.dumps(preview.get("prompt_bundle") or {}, ensure_ascii=False, indent=2),
            )
            job_store.write_file(
                job_id,
                "knowledge_hits.json",
                json.dumps(preview.get("knowledge_hits") or [], ensure_ascii=False, indent=2),
            )
            job_store.write_file(
                job_id,
                "asset_bundle.json",
                json.dumps(preview.get("asset_bundle") or {}, ensure_ascii=False, indent=2),
            )

            prompt_bundle = preview.get("prompt_bundle") or {}
            asset_bundle = preview.get("asset_bundle") or {}
            workflow_mode = preview.get("workflow_mode") or "text_to_video"

            scene_spec = _build_scene_spec(payload, prompt_bundle, asset_bundle)
            scene_spec_path = job_store.write_file(
                job_id,
                "scene_spec.json",
                json.dumps(scene_spec, ensure_ascii=False, indent=2),
            )

            artifacts = {
                "status": "skipped",
                "reason": "当前工作流无需 Blender 空间导出",
            }
            should_export = (
                cfg.ENABLE_BLENDER_EXPORT
                and workflow_mode == "hybrid_image_to_video"
                and asset_bundle.get("id") != "text_only"
            )

            if should_export:
                job_store.update(
                    job_id,
                    {
                        "status": "running",
                        "stage": "blender_exporting",
                        "result": result,
                    },
                )
                try:
                    blender_adapter = BlenderExecutionAdapter(cfg.BLENDER_EXECUTION_MODE)
                    artifacts = blender_adapter.export_scene(
                        blender_bin=cfg.BLENDER_BIN,
                        spec_path=scene_spec_path,
                        out_dir=os.path.join(cfg.JOBS_DIR, job_id),
                    )
                    artifacts["status"] = "exported"
                except BlenderAdapterError as e:
                    artifacts = {
                        "status": "warning",
                        "error": str(e),
                    }
                    result["warnings"].append(str(e))

            result["artifacts"] = artifacts
            job_store.write_file(
                job_id,
                "artifacts.json",
                json.dumps(artifacts or {}, ensure_ascii=False, indent=2),
            )

            fps = int(scene_spec.get("fps") or 24)
            frame_count = int(scene_spec.get("frame_count") or (fps * 4))
            duration_s = max(1, int(frame_count / float(max(1, fps))))

            job_store.update(
                job_id,
                {
                    "status": "running",
                    "stage": "provider_submitted",
                    "result": result,
                },
            )

            router = ProviderRouter(cfg)
            execution_provider = preview.get("execution_provider")
            provider, created, provider_job_id = router.submit_generation(
                execution_provider=execution_provider,
                prompt_bundle=prompt_bundle,
                duration_s=duration_s,
            )

            result["provider_result"] = {
                "display_model": preview.get("display_model"),
                "execution_provider": execution_provider,
                "route_mode": preview.get("route_mode"),
                "job_id": provider_job_id,
                "create": created,
                "done": None,
                "status": "submitted",
            }

            job_store.update(
                job_id,
                {
                    "status": "running",
                    "stage": "provider_running",
                    "result": result,
                },
            )

            done = router.wait_until_done(
                execution_provider=execution_provider,
                provider=provider,
                provider_job_id=provider_job_id,
            )
            video_url = provider.extract_video_url(done)
            provider_status = provider.extract_status(done)

            result["provider_result"]["done"] = done
            result["provider_result"]["status"] = provider_status
            result["video_url"] = video_url
            job_store.write_file(
                job_id,
                "provider_result.json",
                json.dumps(result["provider_result"], ensure_ascii=False, indent=2),
            )

            job_store.update(
                job_id,
                {
                    "status": "succeeded" if video_url else "error",
                    "stage": "succeeded" if video_url else "error",
                    "error": None if video_url else "Provider 未返回可用视频地址",
                    "result": result,
                },
            )
            logger.info(
                "Job %s completed with status: %s",
                job_id,
                "succeeded" if video_url else "error",
            )

        except Exception as e:
            logger.exception("Job %s failed with exception: %s", job_id, str(e))
            if result is None:
                result = _empty_result()
            job_store.update(
                job_id,
                {
                    "status": "error",
                    "stage": "error",
                    "error": str(e),
                    "result": result,
                },
            )

    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
