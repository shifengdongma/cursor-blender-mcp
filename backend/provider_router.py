from __future__ import absolute_import

import logging

from . import generation_models, model_ids
from .credential_service import CredentialError, CredentialService
from .provider_factory import create_provider as build_provider

# 配置日志
logger = logging.getLogger(__name__)


class ProviderRoutingError(RuntimeError):
    def __init__(self, message, error_type="routing_error", status_code=None,
                 provider_code=None, request_id=None, model_id=None):
        RuntimeError.__init__(self, message)
        self.error_type = error_type
        self.status_code = status_code
        self.provider_code = provider_code
        self.request_id = request_id
        self.model_id = model_id


class ProviderRouter(object):
    def __init__(self, cfg, user_id=None, model_key=None, model_id=None,
                 credential_source=None, request_payload=None):
        self.cfg = cfg
        self.user_id = user_id
        self.model_key = model_key
        self.model_id = model_id
        self.credential_source = credential_source
        self.request_payload = dict(request_payload or {})

    # ── Credential / model resolution ──

    def _user(self):
        return {"id": self.user_id} if self.user_id else None

    def _registry_key(self, provider_name):
        if self.model_key:
            return self.model_key
        return {
            "ark_seedance": model_ids.ARK_VIDEO_DEFAULT_KEY,
            "seedance": "atlas_seedance_default",
            "luma": "luma_default",
        }.get(provider_name)

    def _registry_model(self, provider_name):
        key = self._registry_key(provider_name)
        if not key:
            return None
        return generation_models.get_model(
            self.cfg, key, include_unavailable=True, user=self._user()
        )

    def _resolve_model_id(self, provider_name):
        if self.model_id:
            return self.model_id
        model = self._registry_model(provider_name)
        if model and model.get("model_id"):
            return model["model_id"]
        if provider_name == "ark_seedance":
            return getattr(self.cfg, "ARK_VIDEO_MODEL", "") or None
        if provider_name == "seedance":
            return getattr(self.cfg, "SEEDANCE_MODEL_NAME", None)
        if provider_name == "luma":
            return getattr(self.cfg, "LUMA_MODEL_NAME", "ray-2")
        return None

    def _resolve_credentials(self, provider_name):
        if provider_name == "ark_seedance":
            credential_provider = "ark"
            label = "Ark"
            platform_key = self.cfg.ARK_API_KEY
            platform_base = self.cfg.ARK_BASE_URL
        elif provider_name == "seedance":
            credential_provider = "atlas_seedance"
            label = "Seedance"
            platform_key = self.cfg.SEEDANCE_API_KEY
            platform_base = self.cfg.SEEDANCE_BASE_URL
        elif provider_name == "luma":
            credential_provider = "luma"
            label = "Luma"
            platform_key = self.cfg.LUMA_API_KEY
            platform_base = self.cfg.LUMA_BASE_URL
        else:
            raise ProviderRoutingError(
                "未知执行通道：{0}".format(provider_name),
                error_type="unsupported_provider",
            )

        if self.user_id:
            service = CredentialService(self.cfg.DATA_DIR, self.cfg)
            try:
                effective = service.effective(
                    self.user_id,
                    credential_provider,
                    self.cfg,
                    prefer_source=self.credential_source,
                )
            except CredentialError as exc:
                raise ProviderRoutingError(
                    exc.message or "Provider 凭据不可用",
                    error_type="provider_credential_missing",
                    status_code=exc.status_code,
                )
            api_key = effective.get("api_key") or ""
            base_url = effective.get("base_url") or ""
            if not api_key or not effective.get("source"):
                raise ProviderRoutingError(
                    "任务使用的 {0} 凭据已不可用，请在 API 配置页（/api-settings）重新配置".format(
                        credential_provider
                    ),
                    error_type="provider_credential_missing",
                )
            if effective.get("source") == "user":
                try:
                    base_url = service.validate_base_url(base_url, self.cfg)
                except CredentialError:
                    raise ProviderRoutingError(
                        "任务使用的 Base URL 未通过安全校验，请在 API 配置页重新配置",
                        error_type="provider_credential_missing",
                    )
            return api_key, base_url

        if not platform_key:
            raise ProviderRoutingError(
                "未配置 {0} API Key，请在 /api-settings 配置个人密钥".format(label),
                error_type="provider_credential_missing",
            )
        return platform_key, platform_base

    # ── Provider construction ──

    def create_provider(self, execution_provider):
        provider_name = (execution_provider or "").strip().lower()

        if provider_name in ("preview_only", "placeholder", ""):
            raise ProviderRoutingError(
                "所选模型仅用于申报展示，当前演示版未配置真实执行通道",
                error_type="preview_only",
            )
        if provider_name not in ("seedance", "ark_seedance", "luma"):
            raise ProviderRoutingError(
                "未知执行通道：{0}".format(provider_name),
                error_type="unsupported_provider",
            )

        api_key, base_url = self._resolve_credentials(provider_name)
        model_id = self._resolve_model_id(provider_name)
        if not model_id:
            raise ProviderRoutingError(
                "未找到 {0} 的模型 ID，请检查模型配置".format(provider_name),
                error_type="model_not_configured",
            )
        factory_name = {
            "seedance": "atlas_seedance",
            "ark_seedance": "ark_seedance",
            "luma": "luma",
        }[provider_name]
        return build_provider(
            self.cfg, factory_name, api_key, base_url, model_id
        )

    def _build_generation_request(self, provider_name, prompt_bundle, duration_s,
                                  payload=None, caps=None):
        prompt_bundle = prompt_bundle or {}
        payload = payload if payload is not None else self.request_payload
        caps = caps or {}
        try:
            duration = int(payload.get("duration_s") or duration_s or 5)
        except (TypeError, ValueError):
            duration = int(duration_s or 5)
        aspect_ratio = payload.get("ratio") or payload.get("aspect_ratio") or "16:9"
        resolution = payload.get("resolution") or "720p"
        duration_range = caps.get("duration_range")
        if duration_range:
            duration = max(int(duration_range[0]), min(int(duration_range[1]), duration))
        allowed_resolutions = caps.get("resolutions") or []
        if allowed_resolutions and resolution not in allowed_resolutions:
            resolution = "720p" if "720p" in allowed_resolutions else allowed_resolutions[0]
        allowed_ratios = caps.get("ratios") or []
        if allowed_ratios and aspect_ratio not in allowed_ratios:
            aspect_ratio = "16:9" if "16:9" in allowed_ratios else allowed_ratios[0]
        requested_audio = payload.get("generate_audio")
        if not caps.get("supports_audio"):
            generate_audio = None
        elif requested_audio is not None:
            generate_audio = bool(requested_audio)
        else:
            generate_audio = bool(caps.get("default_audio"))
        seed = payload.get("seed") if caps.get("supports_seed", True) else None
        watermark = bool(payload.get("watermark", False))

        if provider_name == "ark_seedance":
            return {
                "prompt": prompt_bundle.get("prompt"),
                "negative_prompt": prompt_bundle.get("negative_prompt"),
                "reference_image_urls": [],
                "reference_image_roles": [],
                "aspect_ratio": aspect_ratio,
                "duration_s": duration,
                "resolution": resolution,
                "generate_audio": generate_audio,
                "watermark": watermark,
                "seed": seed,
            }
        if provider_name == "seedance":
            return {
                "prompt": prompt_bundle.get("prompt"),
                "negative_prompt": prompt_bundle.get("negative_prompt"),
                "keyframe_urls": [],
                "aspect_ratio": aspect_ratio,
                "duration_s": duration,
                "resolution": resolution,
                "generate_audio": generate_audio,
                "seed": seed,
            }
        if provider_name == "luma":
            return {
                "prompt": prompt_bundle.get("prompt"),
                "negative_prompt": prompt_bundle.get("negative_prompt"),
                "keyframe_urls": [],
                "aspect_ratio": aspect_ratio,
                "duration_s": duration,
                "resolution": resolution,
            }
        raise ProviderRoutingError(
            "未知执行通道：{0}".format(provider_name),
            error_type="unsupported_provider",
        )

    def submit_generation(self, execution_provider, prompt_bundle, duration_s,
                          schedule_result=None, engine_session=None):
        provider_name = (execution_provider or "").strip().lower()
        logger.info("Submitting generation to provider: %s", provider_name)
        if schedule_result:
            logger.info("Schedule context for provider %s: %s", provider_name, schedule_result.get("pool_type"))
        if engine_session:
            logger.info("Engine session for provider %s: %s", provider_name, engine_session.get("engine_type"))

        model = self._registry_model(provider_name)
        caps = (model or {}).get("capabilities") or {}
        request_data = self._build_generation_request(
            provider_name, prompt_bundle, duration_s,
            payload=self.request_payload, caps=caps,
        )
        provider = self.create_provider(provider_name)

        try:
            created = provider.create_generation(**request_data)
        except Exception as exc:
            raise ProviderRoutingError(
                str(exc),
                error_type=getattr(exc, "error_type", "submission_failed"),
                status_code=getattr(exc, "status_code", None),
                provider_code=getattr(exc, "provider_code", None),
                request_id=getattr(exc, "request_id", None),
                model_id=getattr(exc, "model_id", None),
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
