# -*- coding: utf-8 -*-
"""Tests for LLM Provider (with mocked HTTP)."""
from __future__ import absolute_import

import json
import pytest
from unittest.mock import patch, MagicMock

from backend.providers.llm_provider import LLMProvider, _strip_markdown_fences
from backend.providers.base import ProviderError

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["name", "count"],
}


class TestStripMarkdownFences(object):

    def test_strip_json_fence(self):
        text = '```json\n{"a": 1}\n```'
        assert _strip_markdown_fences(text) == '{"a": 1}'

    def test_strip_plain_fence(self):
        text = '```\n{"a": 1}\n```'
        assert _strip_markdown_fences(text) == '{"a": 1}'

    def test_no_fence(self):
        text = '{"a": 1}'
        assert _strip_markdown_fences(text) == '{"a": 1}'

    def test_empty(self):
        assert _strip_markdown_fences("") == ""
        assert _strip_markdown_fences(None) is None


class TestLLMProvider(object):

    def make_provider(self, api_key="test-key"):
        return LLMProvider(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            model_name="gpt-4o",
        )

    def make_mock_response(self, content):
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": content_str}}],
        }
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        return resp

    def test_successful_generation(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            mock_post.return_value = self.make_mock_response({"name": "test", "count": 42})
            result = provider.generate_structured("system", "user", SCHEMA)
            assert result == {"name": "test", "count": 42}

    def test_missing_key(self):
        provider = self.make_provider(api_key="")
        with pytest.raises(ProviderError) as exc:
            provider.generate_structured("system", "user", SCHEMA)
        assert "missing_key" in str(exc.value.error_type) or "missing" in str(exc.value)

    def test_invalid_json_response(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            mock_post.return_value = self.make_mock_response("not valid json {{{")
            with pytest.raises(ProviderError) as exc:
                provider.generate_structured("system", "user", SCHEMA)
            assert "invalid_json" in str(exc.value.error_type) or "Invalid" in str(exc.value)

    def test_markdown_fence_stripped(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            content = '```json\n{"name": "x", "count": 1}\n```'
            mock_post.return_value = self.make_mock_response(content)
            result = provider.generate_structured("system", "user", SCHEMA)
            assert result == {"name": "x", "count": 1}

    def test_schema_validation_missing_field(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            mock_post.return_value = self.make_mock_response({"name": "only"})
            with pytest.raises(ProviderError) as exc:
                provider.generate_structured("system", "user", SCHEMA)
            assert "schema" in str(exc.value.error_type) or "Missing" in str(exc.value)

    def test_http_500_retry(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            # First call returns 500, second succeeds
            fail_resp = MagicMock()
            fail_resp.status_code = 500
            fail_resp.text = "Internal Server Error"
            success_resp = self.make_mock_response({"name": "ok", "count": 1})
            mock_post.side_effect = [fail_resp, success_resp]

            result = provider.generate_structured("system", "user", SCHEMA)
            assert result == {"name": "ok", "count": 1}
            assert mock_post.call_count == 2

    def test_http_400_no_retry(self):
        provider = self.make_provider()
        with patch("backend.providers.llm_provider.requests.post") as mock_post:
            fail_resp = MagicMock()
            fail_resp.status_code = 400
            fail_resp.text = "Bad Request"
            mock_post.return_value = fail_resp

            with pytest.raises(ProviderError):
                provider.generate_structured("system", "user", SCHEMA)
            assert mock_post.call_count == 1
