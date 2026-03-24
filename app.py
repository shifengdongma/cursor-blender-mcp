from __future__ import absolute_import

import json
import logging
import os
import traceback

from flask import Flask, jsonify, request, send_from_directory, send_file

from backend.asset_service import get_asset_service
from backend.catalog_service import CatalogService
from backend.config import Config
from backend.database import get_database
from backend.jobs import JobStore, build_initial_result, start_job_worker
from backend.prompt_doc_service import get_prompt_doc_service
from backend.prompt_engine import PromptOrchestrator


# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    app = Flask(__name__, static_folder=None)
    cfg = config_class()

    job_store = JobStore(cfg.JOBS_DIR)
    catalog_service = CatalogService(cfg.CATALOG_PATH)
    prompt_orchestrator = PromptOrchestrator(catalog_service)

    web_root = os.path.join(os.path.dirname(__file__), "web")

    @app.route("/", methods=["GET"])
    def index():
        """
        返回简单的前端页面。
        """
        return send_from_directory(web_root, "index.html")

    @app.route("/web/<path:filename>", methods=["GET"])
    def web_static(filename):
        """
        提供前端静态资源：JS/CSS。
        """
        return send_from_directory(web_root, filename)

    @app.route("/api/bootstrap", methods=["GET"])
    def bootstrap():
        """
        返回申报演示版工作台初始化数据。
        """
        return jsonify(catalog_service.bootstrap_payload())

    @app.route("/api/prompt/preview", methods=["POST"])
    def preview_prompt():
        """
        根据场馆、模型、资产与用户输入生成 Prompt 预览。
        """
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            payload = {}
        return jsonify(prompt_orchestrator.preview(payload)), 200

    @app.route("/api/jobs", methods=["POST"])
    def create_job():
        """
        创建一个新任务。

        请求体（JSON）示例：
        {
          "title": "demo",
          "duration_s": 4,
          "fps": 24,
          "camera_move_type": "orbit",
          "camera_radius_m": 6.0,
          "camera_height_m": 1.6,
          "camera_target": [0, 0, 1.2],
          "environment_hint": "historic baroque opera house interior",
          "lighting_hint": "atmospheric volumetric lighting, warm golden tones",
          "style_anchor": "High-fidelity architectural visualization, cinematic still, 8k"
        }
        """
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            payload = {}

        preview = prompt_orchestrator.preview(payload)
        job = job_store.create(payload, build_initial_result(preview))
        start_job_worker(job_store, job["id"], cfg, prompt_orchestrator)

        return jsonify(job), 201

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        """
        查询任务状态。
        """
        job = job_store.get(job_id)
        if not job:
            return jsonify({"error": "job_not_found"}), 404
        return jsonify(job)

    @app.route("/api/health", methods=["GET"])
    def health():
        """
        简单健康检查。
        """
        return jsonify({"status": "ok"}), 200

    # === Asset API Endpoints ===

    @app.route("/api/assets", methods=["GET"])
    def list_assets():
        """
        获取资产列表。

        Query Parameters:
            asset_type: 资产类型过滤 (glb, image, prompt_doc)
            venue_type: 场馆类型过滤
            limit: 返回数量限制 (default: 100)
            offset: 分页偏移 (default: 0)
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset_type = request.args.get("asset_type")
        venue_type = request.args.get("venue_type")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        assets = asset_service.list_assets(
            asset_type=asset_type,
            venue_type=venue_type,
            limit=limit,
            offset=offset
        )
        total = asset_service.count_assets(asset_type=asset_type, venue_type=venue_type)

        return jsonify({
            "assets": [a.to_dict() for a in assets],
            "total": total,
            "limit": limit,
            "offset": offset
        })

    @app.route("/api/assets/<asset_id>", methods=["GET"])
    def get_asset(asset_id):
        """
        获取单个资产详情。
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        asset = asset_service.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "asset_not_found"}), 404
        return jsonify(asset.to_dict())

    @app.route("/api/assets", methods=["POST"])
    def create_asset():
        """
        创建新资产。

        Request Body (JSON):
            name: 资产名称
            asset_type: 资产类型 (glb, image, prompt_doc)
            venue_type: 场馆类型 (可选)
            description: 描述 (可选)
            metadata: 元数据 (可选)
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}

        name = data.get("name")
        asset_type = data.get("asset_type", "glb")

        if not name:
            return jsonify({"error": "name_required"}), 400

        asset = asset_service.create_asset(
            name=name,
            asset_type=asset_type,
            venue_type=data.get("venue_type"),
            description=data.get("description"),
            metadata=data.get("metadata")
        )

        return jsonify(asset.to_dict()), 201

    @app.route("/api/assets/<asset_id>", methods=["PUT"])
    def update_asset(asset_id):
        """
        更新资产信息。
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}

        asset = asset_service.update_asset(asset_id, **data)
        if not asset:
            return jsonify({"error": "asset_not_found"}), 404

        return jsonify(asset.to_dict())

    @app.route("/api/assets/<asset_id>", methods=["DELETE"])
    def delete_asset(asset_id):
        """
        删除资产。
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        success = asset_service.delete_asset(asset_id)
        if not success:
            return jsonify({"error": "asset_not_found"}), 404
        return jsonify({"success": True})

    @app.route("/api/assets/upload", methods=["POST"])
    def upload_asset():
        """
        上传资产文件。

        Form Data:
            file: 文件
            name: 资产名称
            asset_type: 资产类型 (glb, image, prompt_doc)
            venue_type: 场馆类型 (可选)
            description: 描述 (可选)
        """
        asset_service = get_asset_service(cfg.DATA_DIR)

        if "file" not in request.files:
            return jsonify({"error": "no_file"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "no_filename"}), 400

        name = request.form.get("name") or os.path.splitext(file.filename)[0]
        asset_type = request.form.get("asset_type", "glb")
        venue_type = request.form.get("venue_type")
        description = request.form.get("description")

        # Store file
        rel_path, file_size = asset_service.store_file(file, asset_type, venue_type)

        # Create asset record
        asset = asset_service.create_asset(
            name=name,
            asset_type=asset_type,
            venue_type=venue_type,
            file_path=rel_path,
            file_size=file_size,
            description=description
        )

        return jsonify(asset.to_dict()), 201

    @app.route("/api/assets/<asset_id>/download", methods=["GET"])
    def download_asset(asset_id):
        """
        下载资产文件。
        """
        asset_service = get_asset_service(cfg.DATA_DIR)
        file_path = asset_service.get_file_path(asset_id)

        if not file_path or not os.path.exists(file_path):
            return jsonify({"error": "file_not_found"}), 404

        return send_file(file_path, as_attachment=True)

    @app.route("/data/assets/<path:filename>", methods=["GET"])
    def serve_asset_file(filename):
        """
        提供资产文件静态服务，用于前端预览GLB/图片等文件。
        """
        asset_path = os.path.join(cfg.DATA_DIR, "assets", filename)
        if not os.path.exists(asset_path):
            return jsonify({"error": "file_not_found"}), 404
        return send_file(asset_path)

    # === Prompt Document API Endpoints ===

    @app.route("/api/prompts/documents", methods=["GET"])
    def list_prompt_documents():
        """
        获取 Prompt 文档列表。

        Query Parameters:
            category: 分类过滤 (venue, shot, lighting, style)
            limit: 返回数量限制 (default: 100)
            offset: 分页偏移 (default: 0)
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        category = request.args.get("category")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        docs = prompt_service.list_documents(
            category=category,
            limit=limit,
            offset=offset
        )
        total = prompt_service.count_documents(category=category)

        return jsonify({
            "documents": [d.to_dict() for d in docs],
            "total": total,
            "limit": limit,
            "offset": offset
        })

    @app.route("/api/prompts/documents/<doc_id>", methods=["GET"])
    def get_prompt_document(doc_id):
        """
        获取单个 Prompt 文档。
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        doc = prompt_service.get_document(doc_id)
        if not doc:
            return jsonify({"error": "document_not_found"}), 404
        return jsonify(doc.to_dict())

    @app.route("/api/prompts/documents", methods=["POST"])
    def create_prompt_document():
        """
        创建 Prompt 文档。

        Request Body (JSON):
            title: 文档标题
            category: 分类
            content: Prompt 内容
            keywords: 关键词
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}

        title = data.get("title")
        if not title:
            return jsonify({"error": "title_required"}), 400

        doc = prompt_service.create_document(
            title=title,
            category=data.get("category"),
            content=data.get("content"),
            keywords=data.get("keywords")
        )

        return jsonify(doc.to_dict()), 201

    @app.route("/api/prompts/documents/<doc_id>", methods=["PUT"])
    def update_prompt_document(doc_id):
        """
        更新 Prompt 文档。
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            data = {}

        doc = prompt_service.update_document(doc_id, **data)
        if not doc:
            return jsonify({"error": "document_not_found"}), 404

        return jsonify(doc.to_dict())

    @app.route("/api/prompts/documents/<doc_id>", methods=["DELETE"])
    def delete_prompt_document(doc_id):
        """
        删除 Prompt 文档。
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        success = prompt_service.delete_document(doc_id)
        if not success:
            return jsonify({"error": "document_not_found"}), 404
        return jsonify({"success": True})

    @app.route("/api/prompts/categories", methods=["GET"])
    def get_prompt_categories():
        """
        获取 Prompt 文档分类列表。
        """
        prompt_service = get_prompt_doc_service(cfg.DATA_DIR)
        categories = prompt_service.get_categories()
        return jsonify(categories)

    # === Assets Page Route ===

    @app.route("/assets", methods=["GET"])
    def assets_page():
        """
        资产库页面。
        """
        return send_from_directory(web_root, "assets.html")

    @app.errorhandler(400)
    def bad_request(error):
        """处理 400 错误"""
        logger.warning("Bad request: %s", str(error))
        return jsonify({"error": "bad_request", "message": str(error)}), 400

    @app.errorhandler(404)
    def not_found(error):
        """处理 404 错误"""
        return jsonify({"error": "not_found", "message": "资源未找到"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """处理 500 错误"""
        logger.error("Internal error: %s\n%s", str(error), traceback.format_exc())
        return jsonify({"error": "internal_error", "message": "服务器内部错误"}), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        """全局异常处理"""
        logger.error("Unhandled exception: %s\n%s", str(error), traceback.format_exc())
        return jsonify({"error": "server_error", "message": str(error)}), 500

    return app


if __name__ == "__main__":
    cfg = Config()
    app = create_app(Config)
    host = cfg.HOST
    port = cfg.PORT
    # 兼容 Python 3.6，避免使用新参数
    app.run(host=host, port=port, debug=False)
