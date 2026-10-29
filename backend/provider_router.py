from __future__ import absolute_import

import logging


# 配置日志
logger = logging.getLogger(__name__)


class ProviderRoutingError(RuntimeError):
    def __init__(self, message, error_type="routing_error"):
        RuntimeError.__init__(self, message)
        self.error_type = error_type


class ProviderRouter(object):
    def __init__(self, cfg):
        self.cfg = cfg

    def create_provider(self, execution_provider):
        provider_name = (execution_provider or "").strip().lower()

        if provider_name == "seedance":
            if not self.cfg.SEEDANCE_API_KEY:
                raise ProviderRoutingError("未配置 Seedance API Key", error_type="missing_api_key")
            try:
                from .providers.seedance import SeedanceProvider
            except ImportError:
                raise ProviderRoutingError(
                    "缺少 Seedance 依赖，请先安装 requests 并配置运行环境",
                    error_type="provider_import_error",
                )

            return SeedanceProvider(
                api_key=self.cfg.SEEDANCE_API_KEY,
                base_url=self.cfg.SEEDANCE_BASE_URL,
                model_name=getattr(self.cfg, "SEEDANCE_MODEL_NAME", None),
            )

        if provider_name == "ark_seedance":
            if not self.cfg.ARK_API_KEY:
                raise ProviderRoutingError("未配置 Ark API Key", error_type="missing_api_key")
            from .providers.volcengine_video import VolcengineVideoProvider
            return VolcengineVideoProvider(
                api_key=self.cfg.ARK_API_KEY,
                base_url=self.cfg.ARK_BASE_URL,
                model_id=self.cfg.ARK_VIDEO_MODEL,
                timeout_s=self.cfg.ARK_REQUEST_TIMEOUT_S,
            )

        if provider_name == "luma":
            if not self.cfg.LUMA_API_KEY:
                raise ProviderRoutingError("未配置 Luma API Key", error_type="missing_api_key")
            try:
                from .providers.luma import LumaProvider
            except ImportError:
                raise ProviderRoutingError(
                    "缺少 Luma 依赖，请先安装 requests 并配置运行环境",
                    error_type="provider_import_error",
                )

            return LumaProvider(
                api_key=self.cfg.LUMA_API_KEY,
                base_url=self.cfg.LUMA_BASE_URL,
            )

        if provider_name in ("preview_only", "placeholder", ""):
            raise ProviderRoutingError(
                "所选模型仅用于申报展示，当前演示版未配置真实执行通道",
                error_type="preview_only",
            )

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name), error_type="unsupported_provider")

    def _build_generation_request(self, provider_name, prompt_bundle, duration_s):
        prompt_bundle = prompt_bundle or {}
        common = {
            "prompt": prompt_bundle.get("prompt"),
            "negative_prompt": prompt_bundle.get("negative_prompt"),
            "keyframe_urls": [],
            "aspect_ratio": "16:9",
        }

        if provider_name in ("seedance", "ark_seedance"):
            common["duration_s"] = duration_s
            common["resolution"] = "720p"
            return common

        if provider_name == "luma":
            return common

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name), error_type="unsupported_provider")

    def submit_generation(self, execution_provider, prompt_bundle, duration_s, schedule_result=None, engine_session=None):
        provider_name = (execution_provider or "").strip().lower()
        logger.info("Submitting generation to provider: %s", provider_name)
        if schedule_result:
            logger.info("Schedule context for provider %s: %s", provider_name, schedule_result.get("pool_type"))
        if engine_session:
            logger.info("Engine session for provider %s: %s", provider_name, engine_session.get("engine_type"))
        provider = self.create_provider(provider_name)
        request_data = self._build_generation_request(provider_name, prompt_bundle, duration_s)

        try:
            created = provider.create_generation(**request_data)
        except Exception as exc:
            raise ProviderRoutingError(
                "执行通道提交失败：{0}".format(str(exc)),
                error_type="submission_failed",
            )

        if provider_name == "seedance":
            provider_job_id = ((created.get("data") or {}).get("id"))
            logger.info("Seedance job created: %s", provider_job_id)
            return provider, created, provider_job_id

        if provider_name == "ark_seedance":
            provider_job_id = created.get("id") or (created.get("data") or {}).get("id")
            logger.info("Ark Seedance job created: %s", provider_job_id)
            return provider, created, provider_job_id

        if provider_name == "luma":
            provider_job_id = created.get("id") or created.get("generation_id")
            logger.info("Luma job created: %s", provider_job_id)
            return provider, created, provider_job_id

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name), error_type="unsupported_provider")

    def wait_until_done(self, execution_provider, provider, provider_job_id):
        provider_name = (execution_provider or "").strip().lower()

        try:
            if provider_name == "seedance":
                return provider.wait_until_done(
                    prediction_id=provider_job_id,
                    timeout_s=900,
                    poll_interval_s=5,
                )

            if provider_name == "ark_seedance":
                return provider.wait_until_done(
                    task_id=provider_job_id,
                    timeout_s=900,
                    poll_interval_s=5,
                )

            if provider_name == "luma":
                return provider.wait_until_done(
                    generation_id=provider_job_id,
                    timeout_s=900,
                    poll_interval_s=5,
                )
        except Exception as exc:
            raise ProviderRoutingError(
                "执行通道运行失败：{0}".format(str(exc)),
                error_type="execution_failed",
            )

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name), error_type="unsupported_provider")
