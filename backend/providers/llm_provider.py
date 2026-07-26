# -*- coding: utf-8 -*-
"""
OpenAI-compatible LLM provider for structured JSON generation.
"""
from __future__ import absolute_import

import json
import logging
import re
import time

import requests

from .base import BaseLLMProvider, ProviderError, validate_json_schema

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text):
    """Remove ```json ... ``` fences from LLM response."""
    if not text:
        return text
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    match = re.match(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


class LLMProvider(BaseLLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(self, api_key, base_url, model_name="gpt-4o"):
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name

    def _headers(self):
        return {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

    def _call_with_retry(self, payload, max_retries=2, timeout_s=60):
        """Call LLM API with retry on network/5xx errors."""
        url = "{0}/chat/completions".format(self.base_url)
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                r = requests.post(url, headers=self._headers(), json=payload, timeout=timeout_s)
                if r.status_code < 400:
                    return r.json()
                # 4xx errors: no retry
                if 400 <= r.status_code < 500:
                    raise ProviderError(
                        "LLM API returned {0}: {1}".format(r.status_code, r.text[:500]),
                        error_type="llm_client_error",
                    )
                # 5xx errors: retry
                last_error = ProviderError(
                    "LLM API returned {0}: {1}".format(r.status_code, r.text[:500]),
                    error_type="llm_server_error",
                )
            except requests.exceptions.Timeout:
                last_error = ProviderError("LLM API request timed out", error_type="llm_timeout")
            except requests.exceptions.ConnectionError as e:
                last_error = ProviderError("LLM API connection error: {0}".format(str(e)), error_type="llm_connection_error")
            except ProviderError:
                raise
            except Exception as e:
                last_error = ProviderError("LLM API error: {0}".format(str(e)), error_type="llm_unknown_error")

            if attempt < max_retries:
                wait = (attempt + 1) * 2
                logger.warning("LLM API retry %d/%d after %ds", attempt + 1, max_retries, wait)
                time.sleep(wait)

        raise last_error if last_error else ProviderError("LLM API call failed", error_type="llm_unknown_error")

    def generate_structured(self, system_prompt, user_prompt, schema):
        """
        Generate structured JSON from LLM with schema validation.

        Args:
            system_prompt: System instruction string
            user_prompt: User query string
            schema: Expected JSON schema dict with 'required' and 'properties'

        Returns:
            dict: Parsed JSON response
        """
        if not self.api_key:
            raise ProviderError("LLM API key not configured", error_type="llm_missing_key")

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
        }

        result = self._call_with_retry(payload)

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("LLM response missing choices[0].message.content", error_type="llm_invalid_response")

        # Strip markdown fences
        cleaned = _strip_markdown_fences(content)

        try:
            data = json.loads(cleaned)
        except (ValueError, TypeError):
            raise ProviderError(
                "LLM returned invalid JSON: {0}...".format(cleaned[:200]),
                error_type="llm_invalid_json",
            )

        # Validate against schema
        errors = validate_json_schema(data, schema)
        if errors:
            raise ProviderError(
                "LLM response validation failed: {0}".format("; ".join(errors)),
                error_type="llm_schema_validation_error",
            )

        return data
