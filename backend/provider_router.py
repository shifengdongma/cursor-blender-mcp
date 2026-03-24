from __future__ import absolute_import

import logging


# 配置日志
logger = logging.getLogger(__name__)


class ProviderRoutingError(RuntimeError):
    pass


class ProviderRouter(object):
    def __init__(self, cfg):
        self.cfg = cfg

    def create_provider(self, execution_provider):
        provider_name = (execution_provider or "").strip().lower()

        if provider_name == "seedance":
            try:
                from .providers.seedance import SeedanceProvider
            except ImportError:
                raise ProviderRoutingError("缺少 Seedance 依赖，请先安装 requests 并配置运行环境")

            return SeedanceProvider(
                api_key=self.cfg.SEEDANCE_API_KEY,
                base_url=self.cfg.SEEDANCE_BASE_URL,
                model_name=getattr(self.cfg, "SEEDANCE_MODEL_NAME", None),
            )

        if provider_name == "luma":
            try:
                from .providers.luma import LumaProvider
            except ImportError:
                raise ProviderRoutingError("缺少 Luma 依赖，请先安装 requests 并配置运行环境")

            return LumaProvider(
                api_key=self.cfg.LUMA_API_KEY,
                base_url=self.cfg.LUMA_BASE_URL,
            )

        if provider_name in ("preview_only", "placeholder", ""):
            raise ProviderRoutingError("所选模型仅用于申报展示，当前演示版未配置真实执行通道")

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name))

    def submit_generation(self, execution_provider, prompt_bundle, duration_s):
        provider_name = (execution_provider or "").strip().lower()
        logger.info("Submitting generation to provider: %s", provider_name)
        provider = self.create_provider(provider_name)

        if provider_name == "seedance":
            created = provider.create_generation(
                prompt=prompt_bundle.get("prompt"),
                negative_prompt=prompt_bundle.get("negative_prompt"),
                keyframe_urls=[],
                aspect_ratio="16:9",
                duration_s=duration_s,
                resolution="720p",
            )
            provider_job_id = ((created.get("data") or {}).get("id"))
            logger.info("Seedance job created: %s", provider_job_id)
            return provider, created, provider_job_id

        if provider_name == "luma":
            created = provider.create_generation(
                prompt=prompt_bundle.get("prompt"),
                negative_prompt=prompt_bundle.get("negative_prompt"),
                keyframe_urls=[],
                aspect_ratio="16:9",
            )
            provider_job_id = created.get("id") or created.get("generation_id")
            logger.info("Luma job created: %s", provider_job_id)
            return provider, created, provider_job_id

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name))

    def wait_until_done(self, execution_provider, provider, provider_job_id):
        provider_name = (execution_provider or "").strip().lower()

        if provider_name == "seedance":
            return provider.wait_until_done(
                prediction_id=provider_job_id,
                timeout_s=900,
                poll_interval_s=5,
            )

        if provider_name == "luma":
            return provider.wait_until_done(
                generation_id=provider_job_id,
                timeout_s=900,
                poll_interval_s=5,
            )

        raise ProviderRoutingError("未知执行通道：{0}".format(provider_name))
