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
    assert "演示" not in html
    assert "已连接" not in html
    assert "实时预览" not in html
