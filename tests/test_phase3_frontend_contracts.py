# -*- coding: utf-8 -*-
"""Static contracts for the external compute link and frontend audit preview."""
from __future__ import absolute_import

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return handle.read()


def test_compute_title_is_safe_external_link():
    html = _read("web/compute-platform.html")
    lower = html.lower()
    assert "https://itomp.bigbit.cn:5500/resource/public/group" in html
    assert html.count("itomp.bigbit.cn") == 1
    assert 'class="compute-external-link"' in html
    assert 'target="_blank"' in html
    assert "noopener" in html and "noreferrer" in html
    assert "云算力支撑平台" in html
    assert "password" not in lower
    assert "passwd" not in lower
    assert "autologin" not in lower
    assert "auto-login" not in lower
    assert "credentials" not in lower
    assert "token=" not in lower
    url_line = next(
        line for line in html.splitlines() if "itomp.bigbit.cn" in line
    )
    assert "@" not in url_line
    assert "?" not in url_line


def test_external_link_uses_inherited_title_style():
    css = _read("web/styles.css")
    assert ".compute-external-link" in css
    assert "color: inherit" in css
    assert "text-decoration: none" in css
    assert "focus-visible" in css


def test_audit_card_is_a_sibling_below_preview_not_inside_preview_body():
    html = _read("web/creative-studio.html")
    assert 'class="studio-side-column"' in html
    preview_index = html.index('id="studio-preview-panel"')
    preview_body_index = html.index('id="preview-body"')
    audit_index = html.index('id="content-audit-card"')
    assert preview_index < preview_body_index < audit_index
    assert "敏感内容过滤：关键内容审核" in html
    assert 'id="audit-status"' in html
    assert 'id="audit-keyword-list"' in html
    assert 'id="audit-keyword-count"' in html
    assert 'id="audit-keyword-input"' in html
    assert 'id="audit-add-keyword"' in html
    assert 'id="audit-text"' in html
    assert 'id="audit-run"' in html
    assert 'id="audit-clear"' in html
    assert 'id="audit-result"' in html
    assert 'data-audit-source="requirements"' in html
    assert 'data-audit-source="shots"' in html
    assert 'data-audit-source="prompt"' in html
    assert 'data-audit-source="narration"' in html
    assert "当前提供关键词审核预览，正式生成内容的服务端审核尚未接入。" in html
    assert "演示" not in html
    assert "实时预览" not in html


def test_audit_scripts_load_in_order():
    html = _read("web/creative-studio.html")
    creative_index = html.index("/web/creative-studio.js")
    core_index = html.index("/web/content-audit-core.js")
    ui_index = html.index("/web/content-audit.js")
    session_index = html.index("/web/session-nav.js")
    assert creative_index < core_index < ui_index < session_index


def test_audit_frontend_has_no_backend_calls_or_unsafe_html():
    ui = _read("web/content-audit.js")
    core = _read("web/content-audit-core.js")
    for source in (ui, core):
        assert "fetch(" not in source
        assert "/api/" not in source
        assert "innerHTML" not in source
        assert "Math.random" not in source
        assert "new RegExp" not in source
    assert "sessionStorage" in ui
    assert "textContent" in ui
    assert "document.createTextNode" in ui
    assert "DEFAULT_KEYWORDS" in ui
    assert "未授权素材" in ui
    assert "涉密资料" in ui
    assert "个人身份信息" in ui
    assert "indexOf" in core


def test_audit_sidebar_layout_styles_exist():
    css = _read("web/styles.css")
    assert ".studio-side-column" in css
    assert ".studio-side-column .studio-preview-panel" in css
    assert ".studio-side-column > .studio-preview-panel" in css
    assert "flex: 0 0 auto" in css
    assert ".content-audit-card" in css
    assert ".content-audit-status.is-pending" in css
    assert ".content-audit-status.is-passed" in css
    assert ".content-audit-status.is-found" in css
    assert ".audit-result-preview mark" in css
    assert "@media (max-width: 1024px)" in css
