from __future__ import absolute_import

import json
import logging
import os
import time
import traceback

from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory, send_file, session

from backend.asset_service import AssetServiceError, get_asset_service
from backend.access import can_read_asset, can_write_asset
from backend.auth_service import AuthError, AuthService
from backend.catalog_service import CatalogService
from backend.config import Config
from backend.cloud_routes import register_cloud_routes
from backend.control_plane_routes import register_control_plane_routes
from backend.creative_routes import register_creative_routes
from backend.demo_seed_service import seed_demo_data
from backend.http_utils import (
    ApiError,
    api_error,
    api_success,
    parse_json_body,
    parse_pagination,
    require_fields,
)
from backend.jobs import JobStore, build_initial_result, normalize_job_payload, start_job_worker
from backend.prompt_doc_service import get_prompt_doc_service
from backend.prompt_engine import PromptOrchestrator
from backend.csrf import generate_csrf_token, get_csrf_token
from backend.database import get_database, init_database
from backend.auth_middleware import admin_required, has_permission, is_admin
from backend.profile_routes import register_profile_routes
from backend.provider_routes import register_provider_routes
from backend.admin_routes import register_admin_routes
from backend.generation_routes import register_generation_routes
from backend.web_security import install_security, safe_redirect_target
from backend.rate_limiter import rate_limit
from backend.request_context import request_context_middleware


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _workspace_project_id(user):
    if not user:
        return None
    project_id = "workspace_{0}".format(user.get("id"))
    row = get_database().fetch_one("SELECT id FROM projects WHERE id = ?", (project_id,))
    return row["id"] if row else None


def _job_allowed(job, user, cfg):
    if not job or not user:
        return False
    if is_admin(user):
        return True
    owner = job.get("owner_user_id")
    if owner:
        return owner == user.get("id")
    # Legacy jobs created before ownership tracking are demo/admin-only.
    return bool(cfg.DEMO_MODE)


def _audit(cfg, action, user=None, target_type=None, target_id=None, result="success", metadata=None):
    if not cfg.AUDIT_ENABLED:
        return None
    try:
        from backend.audit_service import get_audit_service
        user = user or {}
        return get_audit_service(cfg.DATA_DIR).record_audit(
            user_id=user.get("id"),
            tenant_id=user.get("tenant_id"),
            project_id=None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            metadata=metadata,
            request_id=getattr(g, "request_id", None),
        )
    except Exception as exc:
        logger.warning("Audit event failed: %s", str(exc))
        return None


def _json_success(data=None, message=None, status_code=200, details=None):
    payload, status_code = api_success(
        data=data,
        message=message,
        status_code=status_code,
        details=details,
    )
    return jsonify(payload), status_code


def _json_error(code, message, status_code=400, details=None):
    payload, status_code = api_error(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
    )
    return jsonify(payload), status_code


def _check_dependencies(cfg):
    """Check external dependency availability."""
    import time

    def _check_db():
        try:
            start = time.time()
            from backend.database import get_database
            db = get_database(os.path.join(cfg.DATA_DIR, 'aigv.db'))
            db.fetch_one('SELECT 1')
            latency = (time.time() - start) * 1000.0
            return {'status': 'available', 'latency_ms': round(latency, 2)}
        except Exception as e:
            return {'status': 'unavailable', 'error': str(e)}

    def _check_blender():
        import shutil
        available = bool(shutil.which(cfg.BLENDER_BIN))
        return {'status': 'configured' if cfg.ENABLE_BLENDER_EXPORT else 'disabled',
                'available': available}

    def _check_ffmpeg():
        import shutil
        ffmpeg_ok = bool(shutil.which(cfg.FFMPEG_BIN))
        ffprobe_ok = bool(shutil.which(cfg.FFPROBE_BIN))
        return {'status': 'configured', 'ffmpeg_available': ffmpeg_ok,
                'ffprobe_available': ffprobe_ok}

    def _check_provider(name, has_key):
        return {'status': 'configured', 'api_key_valid': bool(has_key)} if has_key else {'status': 'unavailable'}

    return {
        'database': _check_db(),
        'blender': _check_blender(),
        'ffmpeg': _check_ffmpeg(),
        'seedance': _check_provider('seedance', cfg.SEEDANCE_API_KEY),
        'luma': _check_provider('luma', cfg.LUMA_API_KEY),
        'llm': _check_provider('llm', cfg.LLM_API_KEY),
        'comfyui': {'status': 'available' if cfg.has_comfyui_configured() else 'unavailable'},
        'piper': {'status': 'available' if cfg.has_piper_configured() else 'unavailable'},
        'aliyun': {'status': 'available' if cfg.ALIYUN_ACCESS_KEY else 'unavailable'},
        'tencent': {'status': 'available' if cfg.TENCENT_SECRET_ID else 'unavailable'},
    }


def _job_response(job):
    if not job:
        raise ApiError("job_not_found", "任务不存在", status_code=404)
    return _json_success(job)


def _normalize_preview_payload(prompt_orchestrator, payload):
    normalized_payload = normalize_job_payload(payload)
    preview = prompt_orchestrator.preview(normalized_payload)
    prompt_bundle = dict(preview.get("prompt_bundle") or {})
    prompt_bundle["duration_s"] = normalized_payload.get("duration_s")
    preview["prompt_bundle"] = prompt_bundle
    return normalized_payload, preview


def _register_main_routes(app, web_root, catalog_service, prompt_orchestrator, job_store, cfg):
    @app.route("/web/runtime-config.js", methods=["GET"])
    def runtime_config_js():
        payload = {
            "appEnv": cfg.APP_ENV,
            "demoMode": bool(cfg.DEMO_MODE),
            "allowRegistration": bool(cfg.ALLOW_REGISTRATION),
        }
        body = "window.AIGV_RUNTIME = {0};\n".format(
            json.dumps(payload, ensure_ascii=False)
        )
        return Response(body, mimetype="application/javascript", headers={"Cache-Control": "no-store"})

    @app.route("/", methods=["GET"])
    def index():
        return send_from_directory(web_root, "index.html")

    @app.route("/creative-studio", methods=["GET"])
    def creative_studio():
        return send_from_directory(web_root, "creative-studio.html")

    @app.route("/compute-platform", methods=["GET"])
    def compute_platform():
        return send_from_directory(web_root, "compute-platform.html")

    @app.route("/compute-platform/hosts", methods=["GET"])
    def compute_platform_hosts():
        return send_from_directory(web_root, "cloud-hosts.html")

    @app.route("/web/<path:filename>", methods=["GET"])
    def web_static(filename):
        return send_from_directory(web_root, filename)

    @app.route("/api/bootstrap", methods=["GET"])
    def bootstrap():
        return _json_success(catalog_service.bootstrap_payload())

    @app.route("/api/prompt/preview", methods=["POST"])
    def preview_prompt():
        payload = parse_json_body(request)
        _, preview = _normalize_preview_payload(prompt_orchestrator, payload)
        return _json_success(preview)

    @app.route("/api/jobs", methods=["POST"])
    @rate_limit(max_requests=30, window_s=60)
    def create_job():
        user = g.current_user
        payload = parse_json_body(request)
        normalized_payload, preview = _normalize_preview_payload(prompt_orchestrator, payload)
        # Identity is always derived from the session, never from the payload.
        normalized_payload["user_id"] = user.get("id")
        normalized_payload["tenant_id"] = user.get("tenant_id")
        normalized_payload["project_id"] = _workspace_project_id(user)
        job = job_store.create(
            normalized_payload,
            build_initial_result(preview),
            owner_user_id=user.get("id"),
        )
        start_job_worker(job_store, job["id"], cfg, prompt_orchestrator)
        _audit(cfg, "job_create", user=user, target_type="job", target_id=job["id"])
        return _json_success(job, message="任务已创建", status_code=201)

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        job = job_store.get(job_id)
        if not job:
            raise ApiError("job_not_found", "任务不存在", status_code=404)
        if not _job_allowed(job, g.current_user, cfg):
            raise ApiError("forbidden", "无权访问该任务", status_code=403)
        return _json_success(job)

    @app.route("/api/health", methods=["GET"])
    def health():
        return _json_success({"status": "ok"})

    @app.route("/api/health/dependencies", methods=["GET"])
    @admin_required
    def health_dependencies():
        deps = _check_dependencies(cfg)
        return _json_success(deps)


def _detach_generated_asset(asset_id):
    """Remove a deleted generated asset from task result pointers/artifacts."""
    db = get_database()
    rows = db.fetch_all(
        "SELECT id, result_payload, output_asset_id FROM generation_tasks "
        "WHERE output_asset_id = ? OR result_payload LIKE ?",
        (asset_id, "%{0}%".format(asset_id)),
    )
    for row in rows:
        try:
            payload = json.loads(row.get("result_payload") or "{}")
        except (TypeError, ValueError):
            payload = {}
        asset_ids = [
            item for item in (payload.get("asset_ids") or []) if item != asset_id
        ]
        output_asset_id = payload.get("output_asset_id")
        if output_asset_id == asset_id:
            output_asset_id = asset_ids[0] if asset_ids else None
        payload["asset_ids"] = asset_ids
        payload["output_asset_id"] = output_asset_id
        db.update(
            "generation_tasks",
            {
                "result_payload": json.dumps(payload, ensure_ascii=False),
                "output_asset_id": output_asset_id,
                "updated_at": int(time.time()),
            },
            "id = ?",
            (row["id"],),
        )
    db.delete("task_artifacts", "asset_id = ?", (asset_id,))


def _register_asset_routes(app, web_root, cfg):
    @app.route("/api/assets/summary", methods=["GET"])
    def assets_summary():
        user = g.current_user
        asset_service = get_asset_service(cfg.DATA_DIR)
        admin = is_admin(user)
        owner = None if admin else user.get("id")
        include_shared = not admin
        tenant_id = None if admin else user.get("tenant_id")

        def count(asset_type=None):
            return asset_service.count_assets(
                asset_type=asset_type,
                owner_user_id=owner,
                include_shared=include_shared,
                tenant_id=tenant_id,
            )

        db = get_database()
        prompt_docs = db.count("prompt_documents")
        venue_presets = db.count("venue_presets")
        return _json_success(
            {
                "models": count("glb") + count("spatial_anchor"),
                "images": count("image"),
                "videos": count("video"),
                "audio": count("audio"),
                "documents": count("document"),
                "archives": count("archive"),
                "prompt_documents": prompt_docs,
                "venue_presets": venue_presets,
                "total": count(),
            }
        )

    @app.route("/api/assets", methods=["GET"])
    def list_assets():
        asset_service = get_asset_service(cfg.DATA_DIR)
        pagination = parse_pagination(request)
        asset_type = request.args.get("asset_type")
        venue_type = request.args.get("venue_type")
        q = request.args.get("q")
        user = g.current_user
        admin = is_admin(user)
        owner = None if admin else user.get("id")
        include_shared = not admin
        tenant_id = None if admin else user.get("tenant_id")

        assets = asset_service.list_assets(
            asset_type=asset_type,
            venue_type=venue_type,
            limit=pagination.limit,
            offset=pagination.offset,
            owner_user_id=owner,
            include_shared=include_shared,
            tenant_id=tenant_id,
            q=q,
        )
        total = asset_service.count_assets(
            asset_type=asset_type,
            venue_type=venue_type,
            owner_user_id=owner,
            include_shared=include_shared,
            tenant_id=tenant_id,
            q=q,
        )

        return _json_success(
            {
                "items": [
                    asset_service.public_dict(a, include_owner=admin, viewer=user)
                    for a in assets
                ],
                "total": total,
                "limit": pagination.limit,
                "offset": pagination.offset,
            }
        )

    @app.route("/api/assets/<asset_id>", methods=["GET"])
    def get_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        if not can_read_asset(asset, g.current_user, demo_mode=cfg.DEMO_MODE):
            raise ApiError("forbidden", "无权访问该资产", status_code=403)
        return _json_success(
            asset_service.public_dict(
                asset,
                include_owner=is_admin(g.current_user),
                viewer=g.current_user,
            )
        )

    @app.route("/api/assets", methods=["POST"])
    def create_asset():
        asset_service = get_asset_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        require_fields(data, ["name"])
        user = g.current_user
        asset_type = data.get("asset_type", "glb")
        if asset_type not in asset_service.ALLOWED_EXTENSIONS and asset_type not in ("prompt_doc", "spatial_anchor"):
            raise ApiError("invalid_asset_type", "不支持的资产类型", status_code=400)
        try:
            asset = asset_service.create_asset(
                name=data.get("name"),
                asset_type=asset_type,
                venue_type=data.get("venue_type"),
                description=data.get("description"),
                metadata=data.get("metadata"),
                owner_user_id=user.get("id"),
                tenant_id=user.get("tenant_id"),
            )
        except AssetServiceError as exc:
            raise ApiError("invalid_asset", str(exc), status_code=400)
        return _json_success(asset_service.public_dict(asset), message="资产已创建", status_code=201)

    @app.route("/api/assets/<asset_id>", methods=["PUT"])
    def update_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        if not can_write_asset(asset, g.current_user):
            raise ApiError("forbidden", "无权修改该资产", status_code=403)
        data = parse_json_body(request)
        try:
            asset = asset_service.update_asset(asset_id, **data)
        except AssetServiceError as exc:
            raise ApiError("invalid_asset_update", str(exc), status_code=400)
        _audit(
            cfg,
            "asset_update",
            user=g.current_user,
            target_type="asset",
            target_id=asset_id,
            metadata={
                "fields": sorted(
                    set(data.keys())
                    & {"name", "description", "venue_type", "visibility", "metadata"}
                )
            },
        )
        return _json_success(
            asset_service.public_dict(asset, viewer=g.current_user),
            message="资产已更新",
        )

    @app.route("/api/assets/<asset_id>", methods=["DELETE"])
    def delete_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        if not can_write_asset(asset, g.current_user):
            raise ApiError("forbidden", "无权删除该资产", status_code=403)
        breakdown = asset_service.asset_reference_breakdown(asset_id)
        hard_references = (
            breakdown["shots"] + breakdown["timeline"] + breakdown["active_tasks"]
        )
        if hard_references:
            raise ApiError(
                "asset_in_use",
                "资产仍被项目、时间线或运行中的任务引用，不能删除",
                status_code=409,
                details={"references": breakdown},
            )
        metadata = asset.metadata or {}
        if breakdown["artifacts"]:
            # A generated work is referenced by its own artifact; deleting the
            # work must clean that artifact instead of permanently blocking it.
            if metadata.get("source") != "generation":
                raise ApiError(
                    "asset_in_use",
                    "资产仍被任务引用，不能删除",
                    status_code=409,
                    details={"references": breakdown},
                )
            _detach_generated_asset(asset_id)
        asset_service.delete_asset(asset_id)
        _audit(cfg, "asset_delete", user=g.current_user, target_type="asset", target_id=asset_id)
        return _json_success({"deleted": True}, message="资产已删除")

    @app.route("/api/assets/upload", methods=["POST"])
    def upload_asset():
        asset_service = get_asset_service(cfg.DATA_DIR)

        if "file" not in request.files:
            raise ApiError("no_file", "缺少上传文件", status_code=400)

        file = request.files["file"]
        if not file.filename:
            raise ApiError("no_filename", "上传文件名不能为空", status_code=400)

        name = request.form.get("name") or os.path.splitext(file.filename)[0]
        asset_type = asset_service.classify_filename(file.filename)
        if asset_type is None:
            raise ApiError(
                "unsupported_file_type",
                "不支持的文件格式",
                status_code=400,
                details={"allowed_extensions": asset_service.allowed_extensions_list()},
            )
        submitted_type = (request.form.get("asset_type") or "").strip()
        if submitted_type and submitted_type != asset_type:
            raise ApiError(
                "asset_type_mismatch",
                "所选资产类型与文件扩展名不一致",
                status_code=400,
                details={"detected": asset_type, "submitted": submitted_type},
            )
        venue_type = request.form.get("venue_type")
        description = request.form.get("description")
        user = g.current_user

        try:
            rel_path, file_size, checksum = asset_service.store_file(
                file,
                asset_type,
                venue_type,
                max_bytes=cfg.MAX_ASSET_UPLOAD_MB * 1024 * 1024,
            )
            asset = asset_service.create_asset(
                name=name,
                asset_type=asset_type,
                venue_type=venue_type,
                file_path=rel_path,
                file_size=file_size,
                description=description,
                owner_user_id=user.get("id"),
                tenant_id=user.get("tenant_id"),
                checksum_sha256=checksum,
            )
        except AssetServiceError as exc:
            raise ApiError("invalid_upload", str(exc), status_code=400)

        return _json_success(
            asset_service.public_dict(asset, viewer=user),
            message="资产上传成功",
            status_code=201,
        )

    @app.route("/api/assets/<asset_id>/file", methods=["GET"])
    def serve_asset_file(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        if not can_read_asset(asset, g.current_user, demo_mode=cfg.DEMO_MODE):
            raise ApiError("forbidden", "无权访问该资产", status_code=403)
        file_path = asset_service.get_file_path_for_asset(asset)
        if not file_path or not os.path.isfile(file_path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)
        inline_types = ("image", "video", "audio", "glb", "spatial_anchor")
        return send_file(
            file_path,
            as_attachment=asset.asset_type not in inline_types,
            conditional=True,
        )

    @app.route("/api/assets/<asset_id>/download", methods=["GET"])
    def download_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        if not can_read_asset(asset, g.current_user, demo_mode=cfg.DEMO_MODE):
            raise ApiError("forbidden", "无权访问该资产", status_code=403)
        file_path = asset_service.get_file_path_for_asset(asset)
        if not file_path or not os.path.isfile(file_path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)
        return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))

    @app.route("/assets", methods=["GET"])
    def assets_page():
        return send_from_directory(web_root, "assets.html")


def _register_prompt_doc_routes(app, cfg):
    @app.route("/api/prompts/documents", methods=["GET"])
    def list_prompt_documents():
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        pagination = parse_pagination(request)
        category = request.args.get("category")

        docs = prompt_service.list_documents(
            category=category,
            limit=pagination.limit,
            offset=pagination.offset,
        )
        total = prompt_service.count_documents(category=category)

        return _json_success(
            {
                "items": [d.to_dict() for d in docs],
                "total": total,
                "limit": pagination.limit,
                "offset": pagination.offset,
            }
        )

    @app.route("/api/prompts/documents/<doc_id>", methods=["GET"])
    def get_prompt_document(doc_id):
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        doc = prompt_service.get_document(doc_id)
        if not doc:
            raise ApiError("document_not_found", "Prompt 文档不存在", status_code=404)
        return _json_success(doc.to_dict())

    @app.route("/api/prompts/documents", methods=["POST"])
    @admin_required
    def create_prompt_document():
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        require_fields(data, ["title"])

        doc = prompt_service.create_document(
            title=data.get("title"),
            category=data.get("category"),
            content=data.get("content"),
            keywords=data.get("keywords"),
        )
        return _json_success(doc.to_dict(), message="Prompt 文档已创建", status_code=201)

    @app.route("/api/prompts/documents/<doc_id>", methods=["PUT"])
    @admin_required
    def update_prompt_document(doc_id):
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        doc = prompt_service.update_document(doc_id, **data)
        if not doc:
            raise ApiError("document_not_found", "Prompt 文档不存在", status_code=404)
        return _json_success(doc.to_dict(), message="Prompt 文档已更新")

    @app.route("/api/prompts/documents/<doc_id>", methods=["DELETE"])
    @admin_required
    def delete_prompt_document(doc_id):
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        success = prompt_service.delete_document(doc_id)
        if not success:
            raise ApiError("document_not_found", "Prompt 文档不存在", status_code=404)
        return _json_success({"deleted": True}, message="Prompt 文档已删除")

    @app.route("/api/prompts/categories", methods=["GET"])
    def get_prompt_categories():
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        return _json_success(prompt_service.get_categories())


def _register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return _json_error(
            error.code,
            error.message,
            status_code=error.status_code,
            details=error.details,
        )

    @app.errorhandler(400)
    def bad_request(error):
        logger.warning("Bad request: %s", str(error))
        return _json_error("bad_request", "请求无效", status_code=400)

    @app.errorhandler(403)
    def forbidden(error):
        if request.path.startswith("/api/"):
            return _json_error("forbidden", "没有访问权限", status_code=403)
        return "403 Forbidden", 403, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return _json_error("not_found", "资源未找到", status_code=404)
        return "404 Not Found", 404, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal error: %s\n%s", str(error), traceback.format_exc())
        if request.path.startswith("/api/"):
            return _json_error("internal_error", "服务器内部错误", status_code=500)
        return "500 Internal Server Error", 500, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(Exception)
    def handle_exception(error):
        if isinstance(error, ApiError):
            return _json_error(error.code, error.message, status_code=error.status_code, details=error.details)
        logger.error("Unhandled exception: %s\n%s", str(error), traceback.format_exc())
        if request.path.startswith("/api/"):
            return _json_error("server_error", "服务器内部错误", status_code=500)
        return "500 Internal Server Error", 500, {"Content-Type": "text/plain; charset=utf-8"}


def _register_auth_routes(app, cfg, web_root):
    auth_service = AuthService(cfg.DATA_DIR, cfg)

    def _start_session(user, session_version):
        session.clear()
        session["auth_uid"] = user["id"]
        session["auth_session_version"] = int(session_version or 0)
        session.permanent = True
        return generate_csrf_token()

    @app.route("/login", methods=["GET"])
    def login_page():
        if getattr(g, "current_user", None):
            return redirect("/")
        return send_from_directory(web_root, "login.html")

    @app.route("/register", methods=["GET"])
    def register_page():
        if getattr(g, "current_user", None):
            return redirect("/")
        return send_from_directory(web_root, "register.html")

    @app.route("/api/auth/csrf", methods=["GET"])
    def auth_csrf():
        return _json_success({"csrf_token": get_csrf_token()})

    @app.route("/api/auth/login", methods=["POST"])
    @rate_limit(max_requests=cfg.LOGIN_RATE_LIMIT, window_s=60)
    def auth_login():
        payload = parse_json_body(request)
        require_fields(payload, ["username", "password"])
        username = payload.get("username")
        password = payload.get("password")
        redirect_to = safe_redirect_target(payload.get("next"))

        result = auth_service.authenticate(username, password)
        if not result.get("ok"):
            _audit(
                cfg,
                "login_failed",
                user=None,
                metadata={"username": str(username)[:80]},
                result="failed",
            )
            return _json_error(
                result.get("error_code") or "invalid_credentials",
                result.get("message") or "用户名或密码错误",
                status_code=result.get("status_code", 401),
                details=result.get("details"),
            )

        user = result["user"]
        token = _start_session(user, result.get("session_version", 0))
        _audit(cfg, "login", user=user)
        return _json_success(
            {
                "user": auth_service.public_user(user),
                "csrf_token": token,
                "redirect_to": redirect_to,
            },
            message="登录成功",
        )

    @app.route("/api/auth/register", methods=["POST"])
    @rate_limit(max_requests=cfg.REGISTER_RATE_LIMIT, window_s=60)
    def auth_register():
        if not cfg.ALLOW_REGISTRATION:
            return _json_error("registration_closed", "当前未开放公开注册", status_code=403)

        payload = parse_json_body(request)
        require_fields(payload, ["username", "password", "confirm_password"])
        redirect_to = safe_redirect_target(payload.get("next"))
        password = payload.get("password") or ""
        if password != (payload.get("confirm_password") or ""):
            return _json_error("password_mismatch", "两次输入的密码不一致", status_code=400)
        if not payload.get("terms_accepted"):
            return _json_error("terms_required", "请先同意用户协议", status_code=400)

        try:
            user = auth_service.register_user(
                username=payload.get("username"),
                password=password,
                email=payload.get("email", ""),
                nickname=payload.get("nickname"),
                terms_accepted=True,
                role="user",
            )
        except AuthError as exc:
            return _json_error(exc.code, exc.message, status_code=exc.status_code, details=exc.details)

        token = _start_session(user, user.get("session_version", 0))
        _audit(cfg, "user_register", user=user)
        return _json_success(
            {
                "user": auth_service.public_user(user),
                "csrf_token": token,
                "redirect_to": redirect_to,
            },
            message="注册成功",
            status_code=201,
        )

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        user = getattr(g, "current_user", None)
        session.clear()
        _audit(cfg, "logout", user=user)
        return _json_success(None, message="已退出登录")

    @app.route("/api/auth/status", methods=["GET"])
    def auth_status():
        user = getattr(g, "current_user", None)
        return _json_success(
            {
                "logged_in": bool(user),
                "user": auth_service.public_user(user) if user else None,
                "capabilities": {
                    "is_admin": is_admin(user),
                    "view_compute": has_permission("view_compute", user=user),
                },
                "allow_registration": bool(cfg.ALLOW_REGISTRATION),
                "demo_mode": bool(cfg.DEMO_MODE),
            }
        )


def create_app(config_class=Config, overrides=None):
    app = Flask(__name__, static_folder=None)
    cfg = config_class()
    if overrides:
        for key, value in overrides.items():
            setattr(cfg, key, value)
    app.secret_key = cfg.SECRET_KEY
    app.config["AIGV_CONFIG"] = cfg

    # Request ID middleware must be installed before the security guard.
    request_context_middleware(app)

    # Initialise the process-wide DB before constructing services.
    init_database(cfg.DATA_DIR)

    web_root = os.path.join(os.path.dirname(__file__), "web")
    auth_service = AuthService(cfg.DATA_DIR, cfg)
    install_security(app, cfg, auth_service, web_root)

    # Demo data is opt-in only.  Production deployments must set DEMO_MODE=false.
    if cfg.DEMO_MODE:
        seed_demo_data(cfg.DATA_DIR)

    job_store = JobStore(cfg.JOBS_DIR)
    catalog_service = CatalogService(cfg.CATALOG_PATH)
    prompt_orchestrator = PromptOrchestrator(catalog_service)

    _register_main_routes(app, web_root, catalog_service, prompt_orchestrator, job_store, cfg)
    _register_auth_routes(app, cfg, web_root)
    register_profile_routes(app, cfg, auth_service, web_root, _json_success, _json_error)
    register_provider_routes(app, cfg, web_root, _json_success, _json_error)
    register_admin_routes(app, cfg, auth_service, web_root, _json_success, _json_error)
    _register_asset_routes(app, web_root, cfg)
    _register_prompt_doc_routes(app, cfg)
    register_control_plane_routes(app, cfg, catalog_service, job_store, _json_success, _json_error)
    register_cloud_routes(app, cfg, _json_success, _json_error)

    # Creative production routes
    from backend.task_service import get_task_service
    from backend.task_worker import start_task_worker

    register_creative_routes(app, cfg, _json_success, _json_error)
    register_generation_routes(app, cfg, _json_success, _json_error)

    # Never start background workers implicitly in a multi-process web server.
    if cfg.START_TASK_WORKER:
        from backend.generation_worker import start_generation_worker
        task_service = get_task_service(cfg.DATA_DIR)
        start_task_worker(task_service, cfg)
        start_generation_worker(task_service, cfg)

    if cfg.ENABLE_MONITORING_WORKER:
        from backend.monitoring_service import MonitoringWorker
        _monitoring_worker = MonitoringWorker(
            data_dir=cfg.DATA_DIR,
            interval_s=cfg.MONITOR_INTERVAL_S,
            timeout_s=cfg.MONITOR_TIMEOUT_S,
            monitor_targets=cfg.MONITOR_TARGETS,
            storage_targets=cfg.STORAGE_TARGETS,
            node_agent_urls=cfg.NODE_AGENT_URLS,
            node_agent_token=cfg.NODE_AGENT_TOKEN,
        )
        _monitoring_worker.start()

    _register_error_handlers(app)

    return app


if __name__ == "__main__":
    cfg = Config()
    app = create_app(Config)
    host = cfg.HOST
    port = cfg.PORT
    app.run(host=host, port=port, debug=False)
