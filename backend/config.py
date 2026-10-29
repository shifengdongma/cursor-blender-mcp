import logging
import os
import secrets


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


def _to_float(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _load_env_file(path):
    """Load .env without overriding explicit environment variables.

    python-dotenv is used when available.  A tiny fallback parser keeps local
    development working in minimal installations (the project already relies on
    .env for provider keys).  Tests set AIGV_ENV=test and never load .env.
    """
    if os.environ.get("AIGV_ENV", "").strip().lower() == "test":
        return
    if not path or not os.path.isfile(path):
        return

    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(path, override=False)
        return
    except ImportError:
        pass
    except Exception:
        logger.warning("Failed to load .env via python-dotenv")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key or not key.replace("_", "").isalnum():
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ.setdefault(key, value)
    except OSError:
        logger.warning("Failed to read env file: %s", path)


_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_load_env_file(os.environ.get("ENV_FILE", os.path.join(_ROOT_DIR, ".env")))


_PLACEHOLDER_SECRETS = {
    "",
    "change-me",
    "change-me-to-a-random-secret-key",
    "changeme",
    "your-secret-key",
    "secret",
}


def _resolve_secret_key(data_dir, app_env):
    """Return a stable secret key.

    Production must provide SECRET_KEY explicitly.  Development gets a stable
    file-backed key so sessions survive restarts instead of silently changing
    every process start.
    """
    configured = (os.environ.get("SECRET_KEY") or "").strip()
    if configured and configured.lower() not in _PLACEHOLDER_SECRETS:
        if app_env in ("production", "prod") and len(configured) < 32:
            raise RuntimeError(
                "SECRET_KEY is too short for production (minimum 32 characters). "
                "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return configured

    if app_env in ("production", "prod"):
        raise RuntimeError(
            "SECRET_KEY is required in production. Generate one with: "
            "python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )

    secret_file = os.environ.get(
        "SECRET_KEY_FILE", os.path.join(data_dir or "./data", ".secret_key")
    )
    try:
        with open(secret_file, "r", encoding="utf-8") as handle:
            existing = handle.read().strip()
            if existing:
                return existing
    except OSError:
        pass

    generated = secrets.token_hex(32)
    try:
        directory = os.path.dirname(os.path.abspath(secret_file))
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(generated)
        logger.warning(
            "SECRET_KEY not configured; generated a persistent development key at %s",
            secret_file,
        )
    except FileExistsError:
        try:
            with open(secret_file, "r", encoding="utf-8") as handle:
                existing = handle.read().strip()
                if existing:
                    return existing
        except OSError:
            pass
    except OSError:
        logger.warning("Could not persist development SECRET_KEY; sessions may reset on restart")
    return generated


class Config(object):
    APP_ENV = os.environ.get("AIGV_ENV", os.environ.get("FLASK_ENV", "development")).strip().lower()
    IS_PRODUCTION = APP_ENV in ("production", "prod")

    DATA_DIR = os.environ.get("DATA_DIR", "./data")
    JOBS_DIR = os.path.join(DATA_DIR, "jobs")
    CATALOG_PATH = os.environ.get("CATALOG_PATH", os.path.join(DATA_DIR, "catalog", "knowledge_base.json"))
    PLATFORM_TENANT_ID = os.environ.get("PLATFORM_TENANT_ID", "tenant_platform")

    # ── Product / demo behaviour ──
    DEMO_MODE = _to_bool(os.environ.get("DEMO_MODE"), default=False)
    ALLOW_REGISTRATION = _to_bool(os.environ.get("ALLOW_REGISTRATION"), default=True)

    # Luma（可选，保留以便后续切换）
    LUMA_API_KEY = os.environ.get("LUMA_API_KEY", "")
    LUMA_BASE_URL = os.environ.get("LUMA_BASE_URL", "https://api.lumalabs.ai/dream-machine/v1")

    # Seedance / Atlas Cloud (legacy adapter; NOT the Volcengine Ark API)
    SEEDANCE_API_KEY = os.environ.get("SEEDANCE_API_KEY", "")
    SEEDANCE_BASE_URL = os.environ.get("SEEDANCE_BASE_URL", "https://api.atlascloud.ai/api/v1")
    SEEDANCE_MODEL_NAME = os.environ.get(
        "SEEDANCE_MODEL_NAME",
        "bytedance/seedance-v1.5-pro/text-to-video",
    )

    # Volcengine Ark (Seedream / Seedance direct API)
    ARK_API_KEY = os.environ.get("ARK_API_KEY", os.environ.get("VOLCENGINE_API_KEY", ""))
    ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    ARK_IMAGE_MODEL = os.environ.get("ARK_IMAGE_MODEL", "doubao-seedream-5-0-pro-260628")
    ARK_IMAGE_MODEL_LITE = os.environ.get("ARK_IMAGE_MODEL_LITE", "doubao-seedream-5-0-lite-260128")
    ARK_VIDEO_MODEL = os.environ.get("ARK_VIDEO_MODEL", "doubao-seedance-2-5-260628")
    ARK_VIDEO_MODEL_20 = os.environ.get("ARK_VIDEO_MODEL_20", "doubao-seedance-2-0-260128")
    ARK_VIDEO_MODEL_10_PRO = os.environ.get("ARK_VIDEO_MODEL_10_PRO", "doubao-seedance-1-0-pro-250528")
    ARK_REQUEST_TIMEOUT_S = _to_int(os.environ.get("ARK_REQUEST_TIMEOUT_S"), default=180)
    LUMA_MODEL_NAME = os.environ.get("LUMA_MODEL_NAME", "ray-2")

    BLENDER_BIN = os.environ.get("BLENDER_BIN", "blender")
    ENABLE_BLENDER_EXPORT = _to_bool(os.environ.get("ENABLE_BLENDER_EXPORT", "true"), default=True)
    BLENDER_EXECUTION_MODE = os.environ.get("BLENDER_EXECUTION_MODE", "local_batch")

    # ── Creative Production Pipeline ──
    # LLM (OpenAI-compatible)
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o")

    # OpenAI Images (user-level credentials may override these)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")

    # Per-user provider credentials
    CREDENTIAL_ENCRYPTION_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
    ALLOW_INSECURE_PROVIDER_URLS = _to_bool(
        os.environ.get("ALLOW_INSECURE_PROVIDER_URLS"), default=False
    )

    # ComfyUI Image Generation
    COMFYUI_BASE_URL = os.environ.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    COMFYUI_WORKFLOW_FILE = os.environ.get("COMFYUI_WORKFLOW_FILE", "./data/workflows/comfyui_default.json")
    COMFYUI_ENABLED = _to_bool(os.environ.get("COMFYUI_ENABLED"), default=False)

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
    ENABLE_MONITORING_WORKER = _to_bool(os.environ.get("ENABLE_MONITORING_WORKER"), default=False)
    ALERT_RULES_FILE = os.environ.get("ALERT_RULES_FILE", "")

    # ── Background workers ──
    START_TASK_WORKER = _to_bool(os.environ.get("START_TASK_WORKER"), default=False)
    GENERATION_WORKER_CONCURRENCY = max(1, _to_int(os.environ.get("GENERATION_WORKER_CONCURRENCY"), default=1))
    GENERATION_WORKER_POLL_INTERVAL_S = _to_float(os.environ.get("GENERATION_WORKER_POLL_INTERVAL_S"), default=2.0)
    GENERATION_TASK_LEASE_SECONDS = _to_int(os.environ.get("GENERATION_TASK_LEASE_SECONDS"), default=900)
    GENERATION_MAX_ATTEMPTS = max(1, _to_int(os.environ.get("GENERATION_MAX_ATTEMPTS"), default=3))
    GENERATION_POLL_INTERVAL_S = max(2, _to_int(os.environ.get("GENERATION_POLL_INTERVAL_S"), default=10))
    GENERATION_POLL_MAX_ERRORS = max(1, _to_int(os.environ.get("GENERATION_POLL_MAX_ERRORS"), default=8))
    GENERATION_DOWNLOAD_TIMEOUT_S = _to_int(os.environ.get("GENERATION_DOWNLOAD_TIMEOUT_S"), default=180)
    GENERATION_IMAGE_DEADLINE_S = _to_int(os.environ.get("GENERATION_IMAGE_DEADLINE_S"), default=1800)
    GENERATION_VIDEO_DEADLINE_S = _to_int(os.environ.get("GENERATION_VIDEO_DEADLINE_S"), default=7200)

    # ── Quotas / upload limits ──
    MAX_CONTENT_LENGTH = _to_int(os.environ.get("MAX_CONTENT_LENGTH"), default=200 * 1024 * 1024)
    MAX_ASSET_UPLOAD_MB = _to_int(os.environ.get("MAX_ASSET_UPLOAD_MB"), default=200)
    MAX_AVATAR_UPLOAD_MB = _to_int(os.environ.get("MAX_AVATAR_UPLOAD_MB"), default=2)
    MAX_GENERATION_DOWNLOAD_MB = _to_int(os.environ.get("MAX_GENERATION_DOWNLOAD_MB"), default=500)
    MAX_PROMPT_LENGTH = _to_int(os.environ.get("MAX_PROMPT_LENGTH"), default=4000)
    MAX_REFERENCE_IMAGE_MB = _to_int(os.environ.get("MAX_REFERENCE_IMAGE_MB"), default=10)
    MAX_CONCURRENT_TASKS_PER_USER = _to_int(os.environ.get("MAX_CONCURRENT_TASKS_PER_USER"), default=2)
    # Legacy creative tasks (storyboard/TTS/compose/refine/export) share one
    # worker thread; cap them per user so one account cannot starve the queue.
    MAX_ACTIVE_LEGACY_TASKS_PER_USER = max(
        1, _to_int(os.environ.get("MAX_ACTIVE_LEGACY_TASKS_PER_USER"), default=3)
    )
    DAILY_IMAGE_LIMIT = _to_int(os.environ.get("DAILY_IMAGE_LIMIT"), default=20)
    DAILY_VIDEO_LIMIT = _to_int(os.environ.get("DAILY_VIDEO_LIMIT"), default=5)

    # ── Security & stability ──
    LOGIN_RATE_LIMIT = _to_int(os.environ.get("LOGIN_RATE_LIMIT"), default=10)
    REGISTER_RATE_LIMIT = _to_int(os.environ.get("REGISTER_RATE_LIMIT"), default=3)
    LOGIN_MAX_FAILURES = _to_int(os.environ.get("LOGIN_MAX_FAILURES"), default=5)
    LOGIN_LOCKOUT_SECONDS = _to_int(os.environ.get("LOGIN_LOCKOUT_SECONDS"), default=900)
    PASSWORD_MIN_LENGTH = _to_int(os.environ.get("PASSWORD_MIN_LENGTH"), default=8)
    PASSWORD_MAX_LENGTH = _to_int(os.environ.get("PASSWORD_MAX_LENGTH"), default=128)
    CSRF_ENABLED = _to_bool(os.environ.get("CSRF_ENABLED"), default=True)
    SESSION_SECURE = _to_bool(os.environ.get("SESSION_SECURE"), default=IS_PRODUCTION)
    SESSION_LIFETIME_DAYS = _to_int(os.environ.get("SESSION_LIFETIME_DAYS"), default=7)
    TRUST_PROXY = _to_bool(os.environ.get("TRUST_PROXY"), default=False)
    AUDIT_ENABLED = _to_bool(os.environ.get("AUDIT_ENABLED"), default=True)
    SQLITE_WAL_MODE = _to_bool(os.environ.get("SQLITE_WAL_MODE"), default=True)

    SECRET_KEY = _resolve_secret_key(DATA_DIR, APP_ENV)

    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _to_int(os.environ.get("PORT"), default=8000)

    def __init__(self):
        """初始化时验证关键配置"""
        self._validate_config()

    def _validate_config(self):
        """验证配置是否有效"""
        warnings = []

        if not self.has_valid_api_key() and not self.ARK_API_KEY:
            warnings.append("警告：未配置任何视频生成 API Key，任务将无法执行")
        if self.IS_PRODUCTION and self.DEMO_MODE:
            warnings.append("警告：生产环境启用了 DEMO_MODE，页面会显示演示数据")
        if self.IS_PRODUCTION and not self.SESSION_SECURE:
            warnings.append("警告：生产环境 SESSION_SECURE=false，Cookie 可能通过 HTTP 传输")
        if self.IS_PRODUCTION and not self.CSRF_ENABLED:
            warnings.append("警告：生产环境 CSRF_ENABLED=false 不安全")

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
        """检查是否配置了可用的视频生成 API Key。"""
        return bool(self.ARK_API_KEY or self.SEEDANCE_API_KEY or self.LUMA_API_KEY)

    def has_image_provider(self):
        return bool(self.ARK_API_KEY or (self.COMFYUI_ENABLED and self.COMFYUI_BASE_URL))

    def has_ark_configured(self):
        return bool(self.ARK_API_KEY)

    def has_valid_llm_key(self):
        """检查是否配置了有效的 LLM API Key"""
        return bool(self.LLM_API_KEY)

    def has_comfyui_configured(self):
        """检查 ComfyUI 是否显式启用且配置了地址。"""
        return bool(self.COMFYUI_ENABLED and self.COMFYUI_BASE_URL)

    def has_piper_configured(self):
        """检查是否配置了 Piper TTS"""
        return bool(self.PIPER_BIN) and bool(self.PIPER_MODEL_PATH) and os.path.exists(self.PIPER_MODEL_PATH)

    def has_ffmpeg_configured(self):
        """检查是否配置了 FFmpeg"""
        import shutil
        return bool(shutil.which(self.FFMPEG_BIN))

    def has_blender_configured(self):
        """Check if Blender is available."""
        import shutil
        return bool(shutil.which(self.BLENDER_BIN))
