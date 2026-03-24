from __future__ import absolute_import

import json
import logging
import os
import traceback

from flask import Flask, jsonify, request, send_from_directory

from backend.catalog_service import CatalogService
from backend.config import Config
from backend.jobs import JobStore, build_initial_result, start_job_worker
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
