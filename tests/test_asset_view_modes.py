# -*- coding: utf-8 -*-
"""Sensitive content library is a client-side view over the same asset library."""
from __future__ import absolute_import

from tests import support


def test_anonymous_sensitive_view_redirects_to_login(client):
    response = client.get("/assets?view=sensitive")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_sensitive_view_serves_the_same_asset_page(client):
    support.register_and_login(client, "sensitive_viewer")
    library = client.get("/assets")
    sensitive = client.get("/assets?view=sensitive")
    assert library.status_code == 200
    assert sensitive.status_code == 200
    assert library.data == sensitive.data

    html = sensitive.get_data(as_text=True)
    assert 'id="back-to-library"' in html
    assert "/assets?view=sensitive" in html
    assert "多模态素材库容量" in html
    assert 'data-tab="documents"' in html
    assert 'data-tab="prompts"' not in html


def test_sensitive_view_uses_client_whitelist_and_no_new_data_api(client):
    support.register_and_login(client, "sensitive_contract")
    assets_js = open("web/assets.js", encoding="utf-8").read()
    assert "applyViewMode" in assets_js
    assert "requested === 'sensitive'" in assets_js
    assert "statsRow.classList.toggle('is-hidden', sensitive)" in assets_js
    assert "document.title = sensitive" in assets_js
    assert "/api/sensitive" not in assets_js
    assert "sensitive_assets" not in assets_js

    # Query parameters never alter the underlying asset APIs.
    summary_before = client.get("/api/assets/summary").get_json()["data"]
    documents_before = client.get("/api/assets/documents").get_json()["data"]
    client.get("/assets?view=sensitive")
    summary_after = client.get("/api/assets/summary").get_json()["data"]
    documents_after = client.get("/api/assets/documents").get_json()["data"]
    assert summary_before == summary_after
    assert documents_before == documents_after


def test_unknown_view_falls_back_to_library(client):
    support.register_and_login(client, "unknown_view")
    response = client.get("/assets?view=not-a-view")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="page-title"' in html
    assert 'data-stat="documents"' in html
