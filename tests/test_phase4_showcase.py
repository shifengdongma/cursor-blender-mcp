# -*- coding: utf-8 -*-
"""Compute platform showcase contracts and real-data isolation checks."""
from __future__ import absolute_import

import json
import os

from tests import support

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return handle.read()


def _runtime_config(client):
    body = client.get("/web/runtime-config.js").get_data(as_text=True)
    payload = body.split("=", 1)[1].strip().rstrip(";")
    return json.loads(payload)


def test_runtime_config_compute_showcase_default_and_override(tmp_path):
    default_app = support.make_app(tmp_path)
    assert _runtime_config(default_app.test_client())["computeShowcase"] is False

    showcase_app = support.make_app(tmp_path, COMPUTE_SHOWCASE_MODE=True)
    assert _runtime_config(showcase_app.test_client())["computeShowcase"] is True


def test_compute_html_loads_showcase_modules_and_containers():
    html = _read("web/compute-platform.html")
    assert "compute-showcase-data.js" in html
    assert "compute-adapters.js" in html
    assert "compute-charts.js" in html
    assert "compute-scheduling.js" in html
    assert html.index("compute-showcase-data.js") < html.index("/web/compute-platform.js")
    assert 'id="cp-film-showcase"' in html
    assert 'id="cp-arch-showcase"' in html
    assert 'id="cp-game-showcase"' in html
    assert 'id="sd-topology"' in html
    assert 'id="sd-event-timeline"' in html
    assert 'id="sd-playback-btn"' in html
    assert 'id="sd-reset-scenario-btn"' in html
    assert 'id="sd-simulate-btn"' in html
    assert "展示场景" not in html
    assert "非实时采集" not in html


def test_compute_js_uses_internal_source_marker_and_cleanup():
    js = _read("web/compute-platform.js")
    assert "data-source" in js
    assert "state.sceneSource" in js
    assert "Math.random" not in js
    assert "monitoringPollInterval = setInterval" not in js
    assert "stopNetworkPlayback" in js
    assert "resetNetworkScenario" in js
    assert "advanceScheduleState" in js
    assert "cleanupFilmResources" in js
    assert "cleanupArchitectureResources" in js
    assert "cleanupGamingResources" in js
    assert "showcaseMode" in js
    assert "scenarioMode" in js
    assert "AIGV_COMPUTE_SHOWCASE" in js
    assert "展示场景" not in js
    assert "非实时采集" not in js


def test_showcase_data_is_local_and_has_expected_scene_shape():
    js = _read("web/compute-showcase-data.js")
    assert "source: 'showcase'" in js
    assert "Math.random" not in js
    assert "Date.now" not in js
    assert "setInterval" not in js
    assert "http://" not in js
    assert "https://" not in js
    assert "/web/assets/showcase/" in js

    manifest_paths = [
        "web/assets/showcase/film-museum.svg",
        "web/assets/showcase/film-theater.svg",
        "web/assets/showcase/film-gallery.svg",
        "web/assets/showcase/film-concert.svg",
        "web/assets/showcase/arch-before.svg",
        "web/assets/showcase/arch-after.svg",
        "web/assets/showcase/arch-industrial.svg",
        "web/assets/showcase/gaming-hall.svg",
        "web/assets/showcase/placeholder.svg",
    ]
    for rel_path in manifest_paths:
        assert os.path.isfile(os.path.join(ROOT, rel_path)), rel_path
        assert os.path.getsize(os.path.join(ROOT, rel_path)) > 200, rel_path


def test_showcase_data_does_not_reference_official_billing_modules():
    showcase = _read("web/compute-showcase-data.js")
    ark = _read("web/ark-admin.js")
    compute = _read("web/compute-platform.js")
    assert "AIGV_DEMO_DATA" not in ark
    assert "AIGV_COMPUTE_SHOWCASE" not in ark
    assert "AIGVArk.renderBilling" in compute
    assert "ark-billing-section" in _read("web/compute-platform.html")
    assert "/api/admin/ark" not in showcase
    assert "/api/billing" not in showcase
    assert "volcengine/" not in showcase
