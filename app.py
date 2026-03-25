from __future__ import absolute_import

import logging
import os
import traceback

from flask import Flask, jsonify, request, send_from_directory, send_file

from backend.asset_service import get_asset_service
from backend.catalog_service import CatalogService
from backend.config import Config
from backend.control_plane_routes import register_control_plane_routes
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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
    @app.route("/", methods=["GET"])
    def index():
        return send_from_directory(web_root, "index.html")

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
    def create_job():
        payload = parse_json_body(request)
        normalized_payload, preview = _normalize_preview_payload(prompt_orchestrator, payload)
        job = job_store.create(normalized_payload, build_initial_result(preview))
        start_job_worker(job_store, job["id"], cfg, prompt_orchestrator)
        return _json_success(job, message="任务已创建", status_code=201)

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        return _job_response(job_store.get(job_id))

    @app.route("/api/health", methods=["GET"])
    def health():
        return _json_success(
            {
                "status": "ok",
                "has_api_key": cfg.has_valid_api_key(),
                "blender_export_enabled": cfg.ENABLE_BLENDER_EXPORT,
                "persistence": "json-jobstore",
            }
        )


def _register_asset_routes(app, web_root, cfg):
    @app.route("/api/assets", methods=["GET"])
    def list_assets():
        asset_service = get_asset_service(cfg.DATA_DIR)
        pagination = parse_pagination(request)
        asset_type = request.args.get("asset_type")
        venue_type = request.args.get("venue_type")

        assets = asset_service.list_assets(
            asset_type=asset_type,
            venue_type=venue_type,
            limit=pagination.limit,
            offset=pagination.offset,
        )
        total = asset_service.count_assets(asset_type=asset_type, venue_type=venue_type)

        return _json_success(
            {
                "items": [a.to_dict() for a in assets],
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
        return _json_success(asset.to_dict())

    @app.route("/api/assets", methods=["POST"])
    def create_asset():
        asset_service = get_asset_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        require_fields(data, ["name"])

        asset = asset_service.create_asset(
            name=data.get("name"),
            asset_type=data.get("asset_type", "glb"),
            venue_type=data.get("venue_type"),
            description=data.get("description"),
            metadata=data.get("metadata"),
        )
        return _json_success(asset.to_dict(), message="资产已创建", status_code=201)

    @app.route("/api/assets/<asset_id>", methods=["PUT"])
    def update_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        asset = asset_service.update_asset(asset_id, **data)
        if not asset:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        return _json_success(asset.to_dict(), message="资产已更新")

    @app.route("/api/assets/<asset_id>", methods=["DELETE"])
    def delete_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        success = asset_service.delete_asset(asset_id)
        if not success:
            raise ApiError("asset_not_found", "资产不存在", status_code=404)
        return _json_success({"deleted": True}, message="资产已删除")

    @app.route("/api/assets/upload", methods=["POST"])
    def upload_asset():
        asset_service = get_asset_service(cfg.DATA_DIR)

        if "file" not in request.files:
            raise ApiError("no_file", "缺少上传文件", status_code=400)

        file = request.files["file"]
        if file.filename == "":
            raise ApiError("no_filename", "上传文件名不能为空", status_code=400)

        name = request.form.get("name") or os.path.splitext(file.filename)[0]
        asset_type = request.form.get("asset_type", "glb")
        venue_type = request.form.get("venue_type")
        description = request.form.get("description")

        rel_path, file_size = asset_service.store_file(file, asset_type, venue_type)
        asset = asset_service.create_asset(
            name=name,
            asset_type=asset_type,
            venue_type=venue_type,
            file_path=rel_path,
            file_size=file_size,
            description=description,
        )
        return _json_success(asset.to_dict(), message="资产上传成功", status_code=201)

    @app.route("/api/assets/<asset_id>/download", methods=["GET"])
    def download_asset(asset_id):
        asset_service = get_asset_service(cfg.DATA_DIR)
        file_path = asset_service.get_file_path(asset_id)

        if not file_path or not os.path.exists(file_path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)

        return send_file(file_path, as_attachment=True)

    @app.route("/data/assets/<path:filename>", methods=["GET"])
    def serve_asset_file(filename):
        asset_path = os.path.join(cfg.DATA_DIR, "assets", filename)
        if not os.path.exists(asset_path):
            raise ApiError("file_not_found", "文件不存在", status_code=404)
        return send_file(asset_path)

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
    def update_prompt_document(doc_id):
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        data = parse_json_body(request)
        doc = prompt_service.update_document(doc_id, **data)
        if not doc:
            raise ApiError("document_not_found", "Prompt 文档不存在", status_code=404)
        return _json_success(doc.to_dict(), message="Prompt 文档已更新")

    @app.route("/api/prompts/documents/<doc_id>", methods=["DELETE"])
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

    @app.errorhandler(404)
    def not_found(error):
        return _json_error("not_found", "资源未找到", status_code=404)

    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal error: %s\n%s", str(error), traceback.format_exc())
        return _json_error("internal_error", "服务器内部错误", status_code=500)

    @app.errorhandler(Exception)
    def handle_exception(error):
        logger.error("Unhandled exception: %s\n%s", str(error), traceback.format_exc())
        return _json_error("server_error", "服务器内部错误", status_code=500)


def create_app(config_class=Config):
    app = Flask(__name__, static_folder=None)
    cfg = config_class()

    seed_demo_data(cfg.DATA_DIR)
    job_store = JobStore(cfg.JOBS_DIR)
    catalog_service = CatalogService(cfg.CATALOG_PATH)
    prompt_orchestrator = PromptOrchestrator(catalog_service)
    web_root = os.path.join(os.path.dirname(__file__), "web")

    _register_main_routes(app, web_root, catalog_service, prompt_orchestrator, job_store, cfg)
    _register_asset_routes(app, web_root, cfg)
    _register_prompt_doc_routes(app, cfg)
    register_control_plane_routes(app, cfg, catalog_service, job_store, _json_success, _json_error)
    _register_error_handlers(app)

    return app


if __name__ == "__main__":
    cfg = Config()
    app = create_app(Config)
    host = cfg.HOST
    port = cfg.PORT
    app.run(host=host, port=port, debug=False)
