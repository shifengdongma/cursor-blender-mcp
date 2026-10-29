# -*- coding: utf-8 -*-
"""Tests for ComfyUI Image Provider (with mocked HTTP)."""
from __future__ import absolute_import

import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from backend.providers.image_provider import ComfyUIProvider
from backend.providers.base import ProviderError


class TestComfyUIProvider(object):

    def make_provider(self, base_url="http://127.0.0.1:8188"):
        return ComfyUIProvider(base_url=base_url)

    def test_submit_generation(self):
        provider = self.make_provider()
        with patch("backend.providers.image_provider.requests.post") as mock_post:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"prompt_id": "abc-123"}
            mock_post.return_value = resp

            prompt_id = provider.submit_generation("a beautiful sunset")
            assert prompt_id == "abc-123"

    def test_submit_no_base_url(self):
        provider = ComfyUIProvider(base_url="")
        with pytest.raises(ProviderError) as exc:
            provider.submit_generation("test")
        assert "not_configured" in str(exc.value.error_type) or "not configured" in str(exc.value)

    def test_submit_connection_error(self):
        provider = self.make_provider()
        with patch("backend.providers.image_provider.requests.post") as mock_post:
            import requests
            mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
            with pytest.raises(ProviderError) as exc:
                provider.submit_generation("test")
            assert "connection" in str(exc.value.error_type).lower()

    def test_poll_generation(self):
        provider = self.make_provider()
        with patch("backend.providers.image_provider.requests.get") as mock_get:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"abc-123": {"status": "completed"}}
            mock_get.return_value = resp

            history = provider.poll_generation("abc-123")
            assert "abc-123" in history

    def test_wait_until_done(self):
        provider = self.make_provider()
        with patch.object(provider, "poll_generation") as mock_poll:
            mock_poll.return_value = {"abc-123": {"outputs": []}}
            result = provider.wait_until_done("abc-123", timeout_s=5, poll_interval_s=0.1)
            assert "outputs" in result

    def test_workflow_injection(self):
        provider = self.make_provider()
        injected = provider._inject_params(
            provider._default_workflow(),
            prompt="test prompt",
            negative_prompt="ugly",
            seed=12345,
            width=512,
            height=512,
            quantity=1,
        )
        # Check KSampler seed was injected
        for node_id, node in injected.items():
            if node["class_type"] == "KSampler":
                assert "seed" in node["inputs"]
                assert node["inputs"]["seed"] == 12345
            if node["class_type"] == "EmptyLatentImage":
                assert node["inputs"]["width"] == 512
                assert node["inputs"]["height"] == 512

    def test_download_results(self, provider=None):
        if provider is None:
            provider = self.make_provider()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(provider, "wait_until_done") as mock_wait:
                mock_wait.return_value = {
                    "outputs": {
                        "9": {
                            "images": [
                                {"filename": "test_00001_.png", "subfolder": "", "type": "output"}
                            ]
                        }
                    }
                }

                with patch("backend.providers.image_provider.requests.get") as mock_get:
                    resp = MagicMock()
                    resp.status_code = 200
                    resp.iter_content.return_value = [b"\x89PNG\r\n\x1a\n" + b"0" * 128]
                    mock_get.return_value = resp

                    files = provider.download_results("test", tmpdir)
                    assert len(files) == 1
                    # Server-supplied filenames are never trusted.
                    assert files[0].endswith(".png")
                    assert os.path.isfile(files[0])

    def test_download_rejects_non_image(self):
        provider = self.make_provider()
        with tempfile.TemporaryDirectory() as tmpdir:
            entry = {
                "outputs": {
                    "9": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}
                }
            }
            with patch("backend.providers.image_provider.requests.get") as mock_get:
                resp = MagicMock()
                resp.status_code = 200
                resp.iter_content.return_value = [b"<html>not an image</html>"]
                mock_get.return_value = resp
                with pytest.raises(ProviderError):
                    provider.download_results_from_history(entry, tmpdir)
