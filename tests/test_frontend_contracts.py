# -*- coding: utf-8 -*-
"""Static frontend contracts for the quick workbench and history delete.

These are regression guards, not a substitute for browser testing.
"""
from __future__ import absolute_import

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return handle.read()


def test_workbench_uses_real_generation_pipeline():
    app_js = _read("web/app.js")
    index_html = _read("web/index.html")
    assert "/api/generation/videos" in app_js
    assert "/api/generation/tasks/" in app_js
    assert "/api/jobs" not in app_js
    assert "encodeURI(result.video_url)" not in app_js
    assert "readiness-banner" in index_html
    assert "cancel-btn" in index_html
    assert "job-result" in index_html
    assert "output_asset" in app_js


def test_history_has_task_delete_action():
    assets_js = _read("web/assets.js")
    assert "history-delete-task" in assets_js
    assert "/api/generation/tasks/" in assets_js
    assert "deleteGenerationTask" in assets_js


def test_creative_studio_capability_note_is_compact_and_has_no_demo_label():
    html = _read("web/creative-studio.html")
    assert "已接入能力" in html
    assert "真实任务链路" in html
    assert "最终 MP4" in html
    assert "多轨时间线" in html
    assert "演示" not in html
    assert "已连接" not in html
    assert "实时预览" not in html


def test_creative_studio_modules_use_real_media_apis():
    js = _read("web/creative-studio.js")
    assert "vp-001" not in js
    assert "/api/creative/tts/voices" in js
    assert "/audio/selection" in js
    assert "/timeline" in js
    assert "timeline_version" in js
    assert "/video-selection" in js
    assert "/compose" in js
    assert "AbortController" in js
    assert "CSS 快速预览" in js
    assert "未接入" in js
    assert "renderExportTreeHTML" not in js


def test_creative_studio_does_not_attach_persistent_listeners_per_render():
    js = _read("web/creative-studio.js")
    assert "function bindEffectsForm" not in js
    assert "function bindTimelineEvents" not in js
    assert "data-concept-actions-bound" in js


def test_compute_platform_ai_model_tab_contract():
    html = _read("web/compute-platform.html")
    js = _read("web/ark-admin.js")
    compute_js = _read("web/compute-platform.js")
    assert "cp-ai-tab-btn" in html
    assert 'id="tab-ai-models"' in html
    assert "ark-usage-days" in html
    assert "ark-local-metrics" in html
    assert "ark-official-model-table" in html
    assert "/api/admin/ark/usage/summary" in js
    assert "/api/admin/ark/usage/sync" in js
    assert "/api/admin/ark/status" in js
    assert "official_api" in js
    assert "AIGVArk.activate" in compute_js
    assert "AIGVArk.isAdmin" in compute_js
    assert "AIGV_DEMO_DATA" not in js


def test_internal_billing_is_labelled_as_estimate():
    html = _read("web/compute-platform.html")
    js = _read("web/compute-platform.js")
    assert "内部 GPU / 渲染核算" in html
    assert "不代表火山引擎官方账单" in html
    assert "内部核算累计" in js
    assert "非火山官方账单" in js
    assert "内部核算余额（非火山账户）" in js
