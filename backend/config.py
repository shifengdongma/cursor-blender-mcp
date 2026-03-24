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
