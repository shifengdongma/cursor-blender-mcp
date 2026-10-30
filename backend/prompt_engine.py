from __future__ import absolute_import

import copy


def _to_text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _split_terms(text):
    raw = _to_text(text)
    if not raw:
        return []
    normalized = raw.replace("；", ",").replace("，", ",").replace(";", ",")
    parts = []
    for item in normalized.split(","):
        cleaned = item.strip()
        if cleaned:
            parts.append(cleaned)
    return parts


def _dedupe_keep_order(items):
    seen = set()
    output = []
    for item in items:
        key = _to_text(item).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(_to_text(item))
    return output


def _join_fragments(items):
    return ", ".join([item for item in items if _to_text(item)])


class PromptOrchestrator(object):
    def __init__(self, catalog_service):
        self.catalog_service = catalog_service

    def _resolve_venue(self, payload):
        venue = self.catalog_service.get_venue(payload.get("venue_type"))
        if venue:
            return venue
        return self.catalog_service.get_default_venue() or {}

    def _resolve_model(self, payload):
        model = self.catalog_service.get_model(payload.get("ai_model"))
        if model:
            return model
        return self.catalog_service.get_default_model() or {}

    def _resolve_asset(self, payload, venue):
        asset_id = payload.get("asset_id")
        if asset_id:
            asset = self.catalog_service.get_asset(asset_id)
            if asset:
                return asset
        return self.catalog_service.get_default_asset_for_venue(venue.get("id")) or {}

    def _resolve_shot(self, payload, venue):
        shot_id = _to_text(payload.get("shot_type")) or _to_text(payload.get("camera_move_type"))
        shot = self.catalog_service.get_shot(shot_id)
        if shot:
            return shot
        shot = self.catalog_service.get_shot(venue.get("default_shot"))
        if shot:
            return shot
        shots = self.catalog_service.list_shots()
        return shots[0] if shots else {}

    def _build_negative_prompt(self, payload, venue, asset):
        rules = self.catalog_service.get_rules()
        items = []
        items.extend(rules.get("default_negative_prompt_parts") or [])
        items.extend(venue.get("negative_prompt_parts") or [])
        items.extend(asset.get("negative_prompt_parts") or [])
        items.extend(_split_terms(payload.get("negative_prompt")))
        return ", ".join(_dedupe_keep_order(items))

    def _build_warnings(self, model, asset, workflow_mode):
        warnings = []

        if model.get("route_mode") == "demo-route":
            warnings.append(
                "已选择 {display_model}，路由至 {execution_provider} 执行".format(
                    display_model=model.get("display_model") or model.get("id") or "展示模型",
                    execution_provider=model.get("execution_provider") or "默认通道",
                )
            )

        if model.get("route_mode") == "preview-only" or model.get("execution_provider") == "preview_only":
            warnings.append("所选模型当前未配置执行通道，仅支持预览")

        if workflow_mode == "hybrid_image_to_video" and asset.get("id") == "text_only":
            warnings.append("当前未绑定空间锚点资产，混合工作流将使用 Prompt 驱动模式")

        return warnings

    def _resolve_workflow_mode(self, payload, venue, asset):
        explicit_workflow = _to_text(payload.get("workflow_mode"))
        workflow_mode = explicit_workflow or asset.get("workflow_mode") or venue.get("workflow_recommendation") or "text_to_video"
        if asset.get("id") == "text_only" and not explicit_workflow:
            workflow_mode = "text_to_video"
        return workflow_mode

    def _build_prompt_modules(self, payload, venue, model, asset, shot, workflow_mode):
        subject = _to_text(payload.get("subject_hint")) or venue.get("default_subject") or ""
        dynamics = _to_text(payload.get("dynamics_hint")) or venue.get("default_dynamics") or ""
        environment = _to_text(payload.get("environment_hint")) or venue.get("default_environment") or ""
        lighting = _to_text(payload.get("lighting_hint")) or venue.get("default_lighting") or ""
        style_anchor = _to_text(payload.get("style_anchor")) or venue.get("default_style") or ""
        engine_target = _to_text(payload.get("engine_target")) or "blender_anchor"
        render_mode = _to_text(payload.get("render_mode")) or "cinematic"

        subject_parts = [subject]
        if workflow_mode == "hybrid_image_to_video" and asset.get("id") != "text_only":
            subject_parts.append(
                "using the {0} blockout as a spatial anchor".format(
                    asset.get("name") or asset.get("id") or "selected asset"
                )
            )

        style_parts = [style_anchor]
        if model.get("style_hint"):
            style_parts.append(model.get("style_hint"))
        if workflow_mode == "hybrid_image_to_video":
            style_parts.append("preserve structural proportions and keep architecture stable across frames")
        if payload.get("include_engine_context", True):
            style_parts.append("engine target {0}".format(engine_target))
            style_parts.append("render mode {0}".format(render_mode))

        return {
            "camera": shot.get("prompt") or venue.get("default_camera_prompt") or "Cinematic camera move",
            "subject": _join_fragments(subject_parts),
            "dynamics": dynamics,
            "environment": environment,
            "lighting": lighting,
            "style": _join_fragments(style_parts),
        }

    def _assemble_prompt(self, prompt_modules):
        ordered_values = [
            prompt_modules.get("camera"),
            prompt_modules.get("subject"),
            prompt_modules.get("dynamics"),
            prompt_modules.get("environment"),
            prompt_modules.get("lighting"),
            prompt_modules.get("style"),
        ]
        fragments = [item for item in ordered_values if _to_text(item)]
        return "{0}.".format(", ".join(fragments)) if fragments else ""

    def _build_execution_plan(self, model):
        execution_provider = model.get("execution_provider") or "seedance"
        display_model = model.get("display_model") or model.get("id")
        route_mode = model.get("route_mode") or "native"
        return {
            "execution_provider": execution_provider,
            "display_model": display_model,
            "route_mode": route_mode,
        }

    def _build_knowledge_hits(self, venue, shot, model, asset, workflow_mode):
        return [
            {
                "type": "venue",
                "id": venue.get("id"),
                "label": venue.get("name"),
                "reason": "载入场馆环境、光影与风格默认模板",
            },
            {
                "type": "shot",
                "id": shot.get("id"),
                "label": shot.get("label"),
                "reason": "采用镜头语言词库生成运镜模块",
            },
            {
                "type": "model",
                "id": model.get("id"),
                "label": model.get("display_model"),
                "reason": "按展示模型映射执行通道与风格提示",
            },
            {
                "type": "asset",
                "id": asset.get("id"),
                "label": asset.get("name"),
                "reason": "注入来料加工 / 扫描 / UE 资产元数据",
            },
            {
                "type": "workflow",
                "id": workflow_mode,
                "label": workflow_mode,
                "reason": "根据资产锚点与工作流策略决定生成路径",
            },
        ]

    def preview(self, payload):
        payload = copy.deepcopy(payload or {})

        venue = self._resolve_venue(payload)
        model = self._resolve_model(payload)
        asset = self._resolve_asset(payload, venue)
        shot = self._resolve_shot(payload, venue)

        workflow_mode = self._resolve_workflow_mode(payload, venue, asset)
        prompt_modules = self._build_prompt_modules(payload, venue, model, asset, shot, workflow_mode)
        prompt = self._assemble_prompt(prompt_modules)
        negative_prompt = self._build_negative_prompt(payload, venue, asset)
        execution_plan = self._build_execution_plan(model)
        warnings = self._build_warnings(model, asset, workflow_mode)
        knowledge_hits = self._build_knowledge_hits(venue, shot, model, asset, workflow_mode)

        return {
            "prompt_bundle": {
                "title": _to_text(payload.get("title")) or venue.get("hero_title") or "文创 AIGV 任务",
                "modules": prompt_modules,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "workflow_mode": workflow_mode,
                "shot_id": shot.get("id"),
                "camera_move_type": shot.get("camera_move_type") or shot.get("id") or venue.get("default_camera_move") or "orbit",
                "display_model": execution_plan.get("display_model"),
                "execution_provider": execution_plan.get("execution_provider"),
                "route_mode": execution_plan.get("route_mode"),
                "camera_defaults": copy.deepcopy(venue.get("camera_defaults") or {}),
                "venue_id": venue.get("id"),
                "venue_name": venue.get("name"),
            },
            "knowledge_hits": knowledge_hits,
            "workflow_mode": workflow_mode,
            "execution_provider": execution_plan.get("execution_provider"),
            "display_model": execution_plan.get("display_model"),
            "route_mode": execution_plan.get("route_mode"),
            "warnings": warnings,
            "asset_bundle": {
                "id": asset.get("id"),
                "name": asset.get("name"),
                "venue_type": asset.get("venue_type"),
                "workflow_mode": asset.get("workflow_mode"),
                "source_type": asset.get("source_type"),
                "description": asset.get("description"),
                "asset_kind": asset.get("asset_kind"),
                "file_format": asset.get("file_format"),
                "metadata": copy.deepcopy(asset.get("metadata") or {}),
                "placeholder_geometry": copy.deepcopy(asset.get("placeholder_geometry") or []),
                "showcase": asset.get("showcase", True),
            },
        }
