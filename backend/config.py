import logging
import os


# 配置日志
logger = logging.getLogger(__name__)


def _to_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v, default=0):
    """将环境变量转换为整数"""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default


class Config(object):
    DATA_DIR = os.environ.get("DATA_DIR", "./data")
    JOBS_DIR = os.path.join(DATA_DIR, "jobs")
    CATALOG_PATH = os.environ.get("CATALOG_PATH", os.path.join(DATA_DIR, "catalog", "knowledge_base.json"))

    # Luma（可选，保留以便后续切换）
    LUMA_API_KEY = os.environ.get("LUMA_API_KEY", "")
    LUMA_BASE_URL = os.environ.get("LUMA_BASE_URL", "https://api.lumalabs.ai/dream-machine/v1")

    # Seedance / Atlas Cloud
    SEEDANCE_API_KEY = os.environ.get("SEEDANCE_API_KEY", "")
    SEEDANCE_BASE_URL = os.environ.get("SEEDANCE_BASE_URL", "https://api.atlascloud.ai/api/v1")
    SEEDANCE_MODEL_NAME = os.environ.get(
        "SEEDANCE_MODEL_NAME",
        "bytedance/seedance-v1.5-pro/text-to-video",
    )

    BLENDER_BIN = os.environ.get("BLENDER_BIN", "blender")
    ENABLE_BLENDER_EXPORT = _to_bool(os.environ.get("ENABLE_BLENDER_EXPORT", "true"), default=True)
    BLENDER_EXECUTION_MODE = os.environ.get("BLENDER_EXECUTION_MODE", "local_batch")

    # ── Creative Production Pipeline ──
    # LLM (OpenAI-compatible)
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o")

    # ComfyUI Image Generation
    COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    COMFYUI_WORKFLOW_FILE = os.environ.get("COMFYUI_WORKFLOW_FILE", "./data/workflows/comfyui_default.json")

    # Piper TTS
    PIPER_BIN = os.environ.get("PIPER_BIN", "piper")
    PIPER_MODEL_PATH = os.environ.get("PIPER_MODEL_PATH", "./data/tts_models/zh_CN-huayan-medium.onnx")

    # FFmpeg
    FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")

    # ── Cloud Provider Credentials (env-only, NEVER stored in DB) ──
    ALIYUN_ACCESS_KEY = os.environ.get("ALIYUN_ACCESS_KEY", "")
    ALIYUN_ACCESS_SECRET = os.environ.get("ALIYUN_ACCESS_SECRET", "")
    ALIYUN_REGION_ID = os.environ.get("ALIYUN_REGION_ID", "cn-hangzhou")

    TENCENT_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
    TENCENT_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
    TENCENT_REGION = os.environ.get("TENCENT_REGION", "ap-guangzhou")

    VMWARE_HOST = os.environ.get("VMWARE_HOST", "")
    VMWARE_USER = os.environ.get("VMWARE_USER", "")
    VMWARE_PASSWORD = os.environ.get("VMWARE_PASSWORD", "")

    GENERIC_REST_URL = os.environ.get("GENERIC_REST_URL", "")
    GENERIC_REST_TOKEN = os.environ.get("GENERIC_REST_TOKEN", "")

    # ── Node Agent ──
    NODE_AGENT_URLS = os.environ.get("NODE_AGENT_URLS", "")
    NODE_AGENT_TOKEN = os.environ.get("NODE_AGENT_TOKEN", "")
    NODE_POLL_INTERVAL_S = _to_int(os.environ.get("NODE_POLL_INTERVAL_S"), default=30)

    # ── Billing ──
    GPU_UNIT_PRICE_CNY = _to_int(os.environ.get("GPU_UNIT_PRICE_CNY"), default=120)
    ENGINE_UNIT_PRICE_CNY = _to_int(os.environ.get("ENGINE_UNIT_PRICE_CNY"), default=80)
    STREAM_UNIT_PRICE_CNY = _to_int(os.environ.get("STREAM_UNIT_PRICE_CNY"), default=40)
    GPU_PRICE_MAP = os.environ.get("GPU_PRICE_MAP", "A100:150,A10:80,L40:120")

    # ── Monitoring & Alerting ──
    MONITOR_TARGETS = os.environ.get("MONITOR_TARGETS", "")
    MONITOR_INTERVAL_S = _to_int(os.environ.get("MONITOR_INTERVAL_S"), default=5)
    MONITOR_TIMEOUT_S = _to_int(os.environ.get("MONITOR_TIMEOUT_S"), default=3)
    STORAGE_TARGETS = os.environ.get("STORAGE_TARGETS", "")
    ENABLE_MONITORING_WORKER = _to_bool(os.environ.get("ENABLE_MONITORING_WORKER"), default=True)
    ALERT_RULES_FILE = os.environ.get("ALERT_RULES_FILE", "")

    # ── Security & Stability ──
    LOGIN_RATE_LIMIT = _to_int(os.environ.get("LOGIN_RATE_LIMIT"), default=10)
    CSRF_ENABLED = _to_bool(os.environ.get("CSRF_ENABLED"), default=True)
    SESSION_SECURE = _to_bool(os.environ.get("SESSION_SECURE"), default=False)
    AUDIT_ENABLED = _to_bool(os.environ.get("AUDIT_ENABLED"), default=True)
    SQLITE_WAL_MODE = _to_bool(os.environ.get("SQLITE_WAL_MODE"), default=True)

    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())

    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _to_int(os.environ.get("PORT"), default=8000)

    def __init__(self):
        """初始化时验证关键配置"""
        self._validate_config()

    def _validate_config(self):
        """验证配置是否有效"""
        warnings = []

        # 检查 API Key 配置
        if not self.SEEDANCE_API_KEY and not self.LUMA_API_KEY:
            warnings.append("警告：未配置任何视频生成 API Key，任务将无法执行")

        # 检查数据目录
        if not os.path.exists(self.DATA_DIR):
            logger.info("数据目录不存在，将自动创建: %s", self.DATA_DIR)
            try:
                os.makedirs(self.DATA_DIR, exist_ok=True)
            except OSError as e:
                warnings.append("无法创建数据目录: {0}".format(str(e)))

        # 检查知识库文件
        if not os.path.exists(self.CATALOG_PATH):
            warnings.append("知识库文件不存在: {0}".format(self.CATALOG_PATH))

        # 检查 Blender（如果启用）
        if self.ENABLE_BLENDER_EXPORT:
            if self.BLENDER_BIN == "blender":
                # 使用系统 PATH 中的 blender
                pass
            elif not os.path.exists(self.BLENDER_BIN):
                warnings.append("Blender 可执行文件不存在: {0}".format(self.BLENDER_BIN))

        for warning in warnings:
            logger.warning(warning)

    def has_valid_api_key(self):
        """检查是否配置了有效的 API Key"""
        return bool(self.SEEDANCE_API_KEY or self.LUMA_API_KEY)

    def has_valid_llm_key(self):
        """检查是否配置了有效的 LLM API Key"""
        return bool(self.LLM_API_KEY)

    def has_comfyui_configured(self):
        """检查是否配置了 ComfyUI"""
        return bool(self.COMFYUI_BASE_URL)

    def has_piper_configured(self):
        """检查是否配置了 Piper TTS"""
        return bool(self.PIPER_BIN) and bool(self.PIPER_MODEL_PATH)

    def has_ffmpeg_configured(self):
        """检查是否配置了 FFmpeg"""
        return bool(self.FFMPEG_BIN)

    def has_blender_configured(self):
        """Check if Blender is available."""
        import shutil
        return bool(shutil.which(self.BLENDER_BIN))
