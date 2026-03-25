from __future__ import absolute_import

import copy
import json
import os


class CatalogError(RuntimeError):
    pass


class CatalogService(object):
    def __init__(self, catalog_path):
        self.catalog_path = catalog_path
        self._cache = None

    def _load_catalog(self):
        if self._cache is not None:
            return self._cache

        if not self.catalog_path:
            raise CatalogError("CATALOG_PATH 未配置")

        path = os.path.abspath(self.catalog_path)
        if not os.path.exists(path):
            raise CatalogError("未找到知识库文件：{0}".format(path))

        with open(path, "r", encoding="utf-8") as f:
            self._cache = json.load(f)
        return self._cache

    def reload(self):
        self._cache = None
        return self._load_catalog()

    def bootstrap_payload(self):
        data = self._load_catalog()
        return {
            "project_metrics": copy.deepcopy(data.get("project_metrics") or []),
            "model_catalog": copy.deepcopy(data.get("model_catalog") or []),
            "venue_catalog": copy.deepcopy(data.get("venue_catalog") or []),
            "asset_catalog": copy.deepcopy(data.get("asset_catalog") or []),
            "workflow_tips": copy.deepcopy(data.get("workflow_tips") or []),
            "shot_catalog": copy.deepcopy(data.get("shot_catalog") or []),
            "lexicon_catalog": copy.deepcopy(data.get("lexicon_catalog") or []),
            "engine_catalog": copy.deepcopy(data.get("engine_catalog") or []),
            "resource_pool_catalog": copy.deepcopy(data.get("resource_pool_catalog") or []),
            "stream_profile_catalog": copy.deepcopy(data.get("stream_profile_catalog") or []),
            "rights_template_catalog": copy.deepcopy(data.get("rights_template_catalog") or []),
            "demo_tenant_catalog": copy.deepcopy(data.get("demo_tenant_catalog") or []),
        }

    def get_rules(self):
        data = self._load_catalog()
        return copy.deepcopy(data.get("knowledge_rules") or {})

    def list_models(self):
        return self.bootstrap_payload().get("model_catalog") or []

    def list_venues(self):
        return self.bootstrap_payload().get("venue_catalog") or []

    def list_assets(self):
        return self.bootstrap_payload().get("asset_catalog") or []

    def list_shots(self):
        return self.bootstrap_payload().get("shot_catalog") or []

    def get_default_model(self):
        models = self.list_models()
        for item in models:
            if item.get("recommended"):
                return item
        return models[0] if models else None

    def get_default_venue(self):
        venues = self.list_venues()
        for item in venues:
            if item.get("recommended"):
                return item
        return venues[0] if venues else None

    def get_text_only_asset(self):
        for item in self.list_assets():
            if item.get("id") == "text_only":
                return item
        return None

    def get_default_asset_for_venue(self, venue_id):
        assets = self.list_assets()
        for item in assets:
            if item.get("venue_type") == venue_id and item.get("recommended"):
                return item
        for item in assets:
            if item.get("venue_type") == venue_id:
                return item
        return self.get_text_only_asset()

    @staticmethod
    def _find_by_id(items, item_id):
        if not item_id:
            return None
        for item in items:
            if item.get("id") == item_id:
                return copy.deepcopy(item)
        return None

    def get_model(self, model_id):
        return self._find_by_id(self.list_models(), model_id)

    def get_venue(self, venue_id):
        return self._find_by_id(self.list_venues(), venue_id)

    def get_asset(self, asset_id):
        return self._find_by_id(self.list_assets(), asset_id)

    def get_shot(self, shot_id):
        return self._find_by_id(self.list_shots(), shot_id)
