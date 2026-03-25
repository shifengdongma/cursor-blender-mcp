from __future__ import absolute_import

import json
import logging
import os
import threading
import time
import uuid

from .blender_adapter import BlenderAdapterError, BlenderExecutionAdapter
from .billing_service import get_billing_service
from .engine_service import get_engine_service
from .ops_service import get_ops_service
from .provider_router import ProviderRouter
from .rights_service import get_rights_service
from .scheduler_service import get_scheduler_service
from .stream_service import get_stream_service

logger = logging.getLogger(__name__)


def _now():
    return int(time.time())


def _normalize_text(value, default_value=""):
    if value is None:
        return default_value
    return str(value).strip()


def _normalize_optional_text(value):
    text = _normalize_text(value, "")
    return text or None


def _normalize_choice(raw_value, allowed_values, default_value):
    value = _normalize_text(raw_value, default_value)
    if not value:
        return default_value
    if value in allowed_values:
        return value
    return default_value


JOB_STAGE_ORDER = [
    "queued",
    "knowledge_ready",
    "rights_validated",
    "resource_scheduling",
    "blender_exporting",
    "provider_submitted",
    "provider_running",
    "streaming",
    "billing_recorded",
    "succeeded",
    "error",
]

TERMINAL_STAGES = ("succeeded", "error")


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
        "rights_result": None,
        "schedule_result": None,
        "engine_session": None,
        "stream_session": None,
        "billing_result": None,
        "monitor_summary": None,
        "ops_events": [],
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


def _provider_execution_allowed(preview):
    execution_provider = (preview or {}).get("execution_provider") or ""
    route_mode = (preview or {}).get("route_mode") or "native"
    provider_name = str(execution_provider).strip().lower()
    if route_mode == "preview-only":
        return False
    return provider_name not in ("", "preview_only", "placeholder")


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


def normalize_job_payload(payload):
    payload = payload or {}
    normalized = dict(payload)
    normalized["title"] = _normalize_text(payload.get("title") or "文创 AIGV 任务", "文创 AIGV 任务")[:80]
    normalized["venue_type"] = _normalize_optional_text(payload.get("venue_type"))
    normalized["ai_model"] = _normalize_optional_text(payload.get("ai_model"))
    normalized["asset_id"] = _normalize_optional_text(payload.get("asset_id"))
    normalized["tenant_id"] = _normalize_optional_text(payload.get("tenant_id"))
    normalized["user_id"] = _normalize_optional_text(payload.get("user_id"))
    normalized["project_id"] = _normalize_optional_text(payload.get("project_id"))
    normalized["engine_target"] = _normalize_choice(
        payload.get("engine_target"),
        ("blender_anchor", "ue5_cloud", "unity_cloud", "steamvr_stream"),
        "blender_anchor",
    )
    normalized["render_mode"] = _normalize_choice(
        payload.get("render_mode"),
        ("cinematic", "interactive", "vr_walkthrough"),
        "cinematic",
    )
    normalized["stream_profile"] = _normalize_choice(
        payload.get("stream_profile"),
        ("low_latency", "balanced", "showcase"),
        "balanced",
    )
    normalized["usage_scope"] = _normalize_choice(
        payload.get("usage_scope"),
        ("internal_demo", "client_review", "public_showcase"),
        "internal_demo",
    )
    shot_value = _normalize_optional_text(payload.get("shot_type") or payload.get("camera_move_type"))
    if shot_value:
        normalized["shot_type"] = shot_value
        normalized["camera_move_type"] = shot_value
    else:
        normalized["shot_type"] = None
        normalized["camera_move_type"] = None
    normalized["duration_s"] = max(1, _to_int(payload.get("duration_s") or 6, 6))
    normalized["fps"] = max(8, _to_int(payload.get("fps") or 24, 24))
    normalized["workflow_mode"] = _normalize_choice(
        payload.get("workflow_mode"),
        ("text_to_video", "hybrid_image_to_video"),
        "text_to_video",
    )
    for field_name in [
        "environment_hint",
        "lighting_hint",
        "style_anchor",
        "subject_hint",
        "dynamics_hint",
        "negative_prompt",
    ]:
        normalized[field_name] = _normalize_optional_text(payload.get(field_name))
    normalized["camera_radius_m"] = _to_float(payload.get("camera_radius_m") or 6.0, 6.0)
    normalized["camera_height_m"] = _to_float(payload.get("camera_height_m") or 1.6, 1.6)
    if payload.get("camera_target") is not None:
        normalized["camera_target"] = _normalize_target(payload.get("camera_target"), [0.0, 0.0, 1.2])
    return normalized


def _normalize_preview(preview, payload):
    normalized_preview = dict(preview or {})
    prompt_bundle = dict(normalized_preview.get("prompt_bundle") or {})
    prompt_bundle["duration_s"] = payload.get("duration_s")
    normalized_preview["prompt_bundle"] = prompt_bundle
    return normalized_preview


def _set_job_state(job_store, job_id, result, stage, status, error=None):
    return job_store.update(job_id, {"status": status, "stage": stage, "error": error, "result": result})


def _complete_preview_only_job(job_store, job_id, preview, result):
    result["provider_result"] = {
        "display_model": preview.get("display_model"),
        "execution_provider": preview.get("execution_provider"),
        "route_mode": preview.get("route_mode"),
        "job_id": None,
        "create": None,
        "done": None,
        "status": "preview_only",
        "error_type": None,
    }
    return _set_job_state(job_store, job_id, result, "succeeded", "succeeded")


def _finalize_provider_result(result, preview, execution_provider, created, provider_job_id):
    result["provider_result"] = {
        "display_model": preview.get("display_model"),
        "execution_provider": execution_provider,
        "route_mode": preview.get("route_mode"),
        "job_id": provider_job_id,
        "create": created,
        "done": None,
        "status": "submitted",
        "error_type": None,
    }


class JobStore(object):
    def __init__(self, jobs_dir):
        self.jobs_dir = jobs_dir
        if not os.path.exists(self.jobs_dir):
            os.makedirs(self.jobs_dir)
        self._lock = threading.Lock()
        self._jobs = {}

    def _job_dir(self, job_id):
        return os.path.join(self.jobs_dir, job_id)

    def _job_path(self, job_id):
        return os.path.join(self._job_dir(job_id), "job.json")

    def create(self, payload, initial_result=None):
        job_id = str(uuid.uuid4())
        d = self._job_dir(job_id)
        if not os.path.exists(d):
            os.makedirs(d)
        normalized_payload = normalize_job_payload(payload)
        job = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
            "result": initial_result or _empty_result(),
            "payload": normalized_payload,
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
        with open(path, "r") as f:
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
        if not os.path.exists(d):
            os.makedirs(d)
        tmp = os.path.join(d, "job.json.tmp")
        with open(tmp, "w") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        os.rename(tmp, self._job_path(job_id))

    def write_file(self, job_id, filename, content):
        d = self._job_dir(job_id)
        if not os.path.exists(d):
            os.makedirs(d)
        path = os.path.join(d, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def job_file_path(self, job_id, filename):
        return os.path.join(self._job_dir(job_id), filename)


def _default_geometry_for_venue(venue_type):
    return [{"kind": "plane", "name": venue_type or "Ground", "location": [0, 0, 0], "rotation_euler": [0, 0, 0], "scale": [10, 10, 1]}]


def _build_scene_spec(user_input, prompt_bundle, asset_bundle):
    duration_s = _to_float(user_input.get("duration_s") or 6.0, 6.0)
    fps = max(8, _to_int(user_input.get("fps") or 24, 24))
    frame_count = max(24, int(duration_s * fps))
    camera_defaults = (prompt_bundle or {}).get("camera_defaults") or {}
    return {
        "title": (user_input.get("title") or "demo").strip()[:80],
        "venue_type": (prompt_bundle or {}).get("venue_id") or user_input.get("venue_type") or "",
        "workflow_mode": (prompt_bundle or {}).get("workflow_mode") or user_input.get("workflow_mode") or "text_to_video",
        "fps": fps,
        "resolution": [768, 432],
        "frame_count": frame_count,
        "camera_move": {
            "type": user_input.get("camera_move_type") or user_input.get("shot_type") or (prompt_bundle or {}).get("camera_move_type") or "orbit",
            "duration_s": duration_s,
            "radius_m": _to_float(user_input.get("camera_radius_m") or camera_defaults.get("radius_m") or 6.0, 6.0),
            "height_m": _to_float(user_input.get("camera_height_m") or camera_defaults.get("height_m") or 1.6, 1.6),
            "target": _normalize_target(user_input.get("camera_target"), camera_defaults.get("target") or [0.0, 0.0, 1.2]),
        },
        "assets": (asset_bundle or {}).get("placeholder_geometry") or _default_geometry_for_venue(user_input.get("venue_type")),
    }


def start_job_worker(job_store, job_id, cfg, prompt_orchestrator):
    def _run():
        result = None
        try:
            job = job_store.get(job_id)
            if not job:
                return
            payload = normalize_job_payload(job.get("payload") or {})
            preview = _normalize_preview(prompt_orchestrator.preview(payload), payload)
            result = build_initial_result(preview)
            rights_service = get_rights_service(cfg.DATA_DIR)
            scheduler_service = get_scheduler_service(cfg.DATA_DIR)
            engine_service = get_engine_service(cfg.DATA_DIR)
            stream_service = get_stream_service()
            billing_service = get_billing_service(cfg.DATA_DIR)
            ops_service = get_ops_service(cfg.DATA_DIR)

            _set_job_state(job_store, job_id, result, "knowledge_ready", "running")
            job_store.write_file(job_id, "prompt_bundle.json", json.dumps(preview.get("prompt_bundle") or {}, ensure_ascii=False, indent=2))
            job_store.write_file(job_id, "knowledge_hits.json", json.dumps(preview.get("knowledge_hits") or [], ensure_ascii=False, indent=2))
            job_store.write_file(job_id, "asset_bundle.json", json.dumps(preview.get("asset_bundle") or {}, ensure_ascii=False, indent=2))

            rights_result = rights_service.validate_asset_rights(payload.get("asset_id"), payload.get("usage_scope"), payload.get("tenant_id"))
            rights_snapshot = rights_service.build_job_snapshot(job_id, payload.get("asset_id"), payload.get("tenant_id"), payload.get("project_id"), payload.get("user_id"), rights_result)
            result["rights_result"] = rights_result
            job_store.write_file(job_id, "rights_snapshot.json", json.dumps(rights_snapshot, ensure_ascii=False, indent=2))
            result["ops_events"].append(ops_service.record_event(payload.get("tenant_id"), payload.get("project_id"), job_id, "rights_validated", "info", rights_result.get("message"), rights_result))
            _set_job_state(job_store, job_id, result, "rights_validated", "running")

            schedule_result = scheduler_service.allocate(job_id, payload, persist=True)
            result["schedule_result"] = schedule_result
            job_store.write_file(job_id, "scheduler_decision.json", json.dumps(schedule_result, ensure_ascii=False, indent=2))
            result["ops_events"].append(ops_service.record_event(payload.get("tenant_id"), payload.get("project_id"), job_id, "resource_scheduling", "info", schedule_result.get("reason"), schedule_result))
            _set_job_state(job_store, job_id, result, "resource_scheduling", "running")

            engine_session = engine_service.create_session(job_id, payload)
            result["engine_session"] = engine_session
            job_store.write_file(job_id, "render_session.json", json.dumps(engine_session, ensure_ascii=False, indent=2))

            prompt_bundle = preview.get("prompt_bundle") or {}
            asset_bundle = preview.get("asset_bundle") or {}
            workflow_mode = preview.get("workflow_mode") or "text_to_video"
            scene_spec = _build_scene_spec(payload, prompt_bundle, asset_bundle)
            scene_spec_path = job_store.write_file(job_id, "scene_spec.json", json.dumps(scene_spec, ensure_ascii=False, indent=2))

            artifacts = {"status": "skipped", "reason": "当前工作流无需 Blender 空间导出"}
            should_export = cfg.ENABLE_BLENDER_EXPORT and workflow_mode == "hybrid_image_to_video" and asset_bundle.get("id") != "text_only"
            if should_export:
                _set_job_state(job_store, job_id, result, "blender_exporting", "running")
                try:
                    blender_adapter = BlenderExecutionAdapter(cfg.BLENDER_EXECUTION_MODE)
                    artifacts = blender_adapter.export_scene(blender_bin=cfg.BLENDER_BIN, spec_path=scene_spec_path, out_dir=os.path.join(cfg.JOBS_DIR, job_id))
                    artifacts["status"] = "exported"
                except BlenderAdapterError as e:
                    artifacts = {"status": "warning", "error": str(e)}
                    result["warnings"].append(str(e))
            result["artifacts"] = artifacts
            job_store.write_file(job_id, "artifacts.json", json.dumps(artifacts or {}, ensure_ascii=False, indent=2))

            stream_session = stream_service.create_session(job_id, payload, engine_session)
            result["stream_session"] = stream_session
            job_store.write_file(job_id, "stream_session.json", json.dumps(stream_session, ensure_ascii=False, indent=2))

            monitor_ticks = scheduler_service.build_monitor_ticks(job_id, schedule_result, stream_session, count=3)
            result["monitor_summary"] = {"latest": monitor_ticks[-1], "ticks": monitor_ticks}
            job_store.write_file(job_id, "monitor_ticks.json", json.dumps(monitor_ticks, ensure_ascii=False, indent=2))

            if not _provider_execution_allowed(preview):
                billing_result = billing_service.build_job_billing(job_id, payload, schedule_result, stream_session)
                result["billing_result"] = billing_result
                job_store.write_file(job_id, "billing_snapshot.json", json.dumps(billing_result, ensure_ascii=False, indent=2))
                _complete_preview_only_job(job_store, job_id, preview, result)
                return

            fps = int(scene_spec.get("fps") or 24)
            frame_count = int(scene_spec.get("frame_count") or (fps * 4))
            duration_s = max(1, int(frame_count / float(max(1, fps))))
            _set_job_state(job_store, job_id, result, "provider_submitted", "running")
            router = ProviderRouter(cfg)
            execution_provider = preview.get("execution_provider")
            provider, created, provider_job_id = router.submit_generation(execution_provider=execution_provider, prompt_bundle=prompt_bundle, duration_s=duration_s, schedule_result=schedule_result, engine_session=engine_session)
            _finalize_provider_result(result, preview, execution_provider, created, provider_job_id)
            _set_job_state(job_store, job_id, result, "provider_running", "running")
            done = router.wait_until_done(execution_provider=execution_provider, provider=provider, provider_job_id=provider_job_id)
            video_url = provider.extract_video_url(done)
            provider_status = provider.extract_status(done)
            result["provider_result"]["done"] = done
            result["provider_result"]["status"] = provider_status
            result["video_url"] = video_url
            job_store.write_file(job_id, "provider_result.json", json.dumps(result["provider_result"], ensure_ascii=False, indent=2))
            _set_job_state(job_store, job_id, result, "streaming", "running")

            billing_result = billing_service.build_job_billing(job_id, payload, schedule_result, stream_session)
            result["billing_result"] = billing_result
            job_store.write_file(job_id, "billing_snapshot.json", json.dumps(billing_result, ensure_ascii=False, indent=2))
            _set_job_state(job_store, job_id, result, "billing_recorded", "running")

            if video_url:
                _set_job_state(job_store, job_id, result, "succeeded", "succeeded")
                return
            _set_job_state(job_store, job_id, result, "error", "error", error="Provider 未返回可用视频地址")
        except Exception as e:
            logger.exception("Job %s failed with exception: %s", job_id, str(e))
            if result is None:
                result = _empty_result()
            _set_job_state(job_store, job_id, result, "error", "error", error=str(e))

    t = threading.Thread(target=_run)
    t.daemon = True
    t.start()
