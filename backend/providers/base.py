# -*- coding: utf-8 -*-
"""
Abstract base classes for creative production providers.
"""
from __future__ import absolute_import

import json


def scrub_secret(text, secret):
    """Return ``text`` with a bearer secret redacted.

    Provider error bodies are surfaced to the task record and worker logs; a
    reflecting proxy can echo the ``Authorization`` header into that body, so
    every adapter must scrub its own key before building an error message.
    """
    if text is None:
        return ""
    text = str(text)
    secret = str(secret or "")
    if secret:
        text = text.replace(secret, "***")
    return text


def is_redirect(status_code):
    """True for HTTP redirects.  Provider calls must never follow them."""
    try:
        return 300 <= int(status_code) < 400
    except (TypeError, ValueError):
        return False


class ProviderError(RuntimeError):
    """Base error for all provider failures.

    ``request_id``/``provider_code``/``status_code`` are safe diagnostic fields
    that may be persisted with a task.  They never contain credentials.
    """
    def __init__(self, message, error_type="provider_error", status_code=None,
                 provider_code=None, request_id=None, model_id=None,
                 retry_after_s=None):
        RuntimeError.__init__(self, message)
        self.error_type = error_type
        self.status_code = status_code
        self.provider_code = provider_code
        self.request_id = request_id
        self.model_id = model_id
        self.retry_after_s = retry_after_s


class ProviderAuthError(ProviderError):
    def __init__(self, message, error_type="provider_auth_error", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class ProviderRateLimited(ProviderError):
    def __init__(self, message, error_type="provider_rate_limited", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class ProviderRejected(ProviderError):
    def __init__(self, message, error_type="provider_rejected", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class ProviderUncertain(ProviderError):
    """The request may have reached the provider; never auto-resubmit."""
    def __init__(self, message, error_type="submission_uncertain", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class ProviderPollError(ProviderError):
    def __init__(self, message, error_type="provider_poll_error", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class ProviderDownloadError(ProviderError):
    def __init__(self, message, error_type="provider_download_error", **kwargs):
        ProviderError.__init__(self, message, error_type=error_type, **kwargs)


class GenerationRequest(object):
    """Provider-agnostic generation request."""

    def __init__(self, task_type, provider, model_id, prompt, negative_prompt=None,
                 width=None, height=None, aspect_ratio=None, duration_s=None,
                 resolution=None, reference_images=None, seed=None,
                 user_id=None, project_id=None, extra=None):
        self.task_type = task_type
        self.provider = provider
        self.model_id = model_id
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.width = width
        self.height = height
        self.aspect_ratio = aspect_ratio
        self.duration_s = duration_s
        self.resolution = resolution
        self.reference_images = reference_images or []
        self.seed = seed
        self.user_id = user_id
        self.project_id = project_id
        self.extra = extra or {}


class GenerationResult(object):
    """Normalised provider result.  Remote URLs are transient only."""

    def __init__(self, provider, status, provider_job_id=None, progress=None,
                 output_urls=None, error_code=None, error_message=None,
                 raw=None, provider_status=None):
        self.provider = provider
        self.status = status
        self.provider_job_id = provider_job_id
        self.progress = progress
        self.output_urls = output_urls or []
        self.error_code = error_code
        self.error_message = error_message
        self.raw = raw
        self.provider_status = provider_status


class BaseLLMProvider(object):
    """Abstract base for LLM (OpenAI-compatible) providers."""

    def generate_structured(self, system_prompt, user_prompt, schema):
        """
        Generate structured JSON output from LLM.

        Args:
            system_prompt: System instruction string
            user_prompt: User query string
            schema: Expected JSON schema dict with 'required' and 'properties'

        Returns:
            dict: Parsed JSON response validated against schema
        """
        raise NotImplementedError


class BaseImageProvider(object):
    """Abstract base for image generation providers (e.g., ComfyUI)."""

    def submit_generation(self, prompt, negative_prompt=None, seed=-1,
                          width=1024, height=576, quantity=1):
        """Submit an image generation job. Returns a provider-specific job ID."""
        raise NotImplementedError

    def poll_generation(self, prompt_id):
        """Poll image generation status. Returns status dict."""
        raise NotImplementedError

    def wait_until_done(self, prompt_id, timeout_s=600, poll_interval_s=3):
        """Poll until generation completes or fails."""
        raise NotImplementedError

    def download_results(self, prompt_id, output_dir):
        """Download generated images. Returns list of file paths."""
        raise NotImplementedError


class BaseTTSProvider(object):
    """Abstract base for TTS providers (e.g., Piper)."""

    def synthesize(self, text, voice_id, output_path):
        """
        Synthesize text to speech audio.

        Args:
            text: Text to synthesize
            voice_id: Voice/model identifier
            output_path: Path to save the audio file

        Returns:
            dict: {output_path, duration_s, format}
        """
        raise NotImplementedError


def validate_json_schema(data, schema, path=""):
    """
    Validate that data conforms to a JSON schema.

    Args:
        data: Parsed JSON dict
        schema: Schema dict with at least 'properties' and optionally 'required'
        path: Current validation path for error messages

    Returns:
        list: List of error messages, empty if valid
    """
    errors = []
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    if not isinstance(data, dict):
        return ["Expected JSON object at {0}".format(path or "$")]

    for key in required:
        if key not in data or data[key] is None:
            errors.append("Missing required field: {0}{1}".format(path_prefix(path), key))

    for key, prop_schema in properties.items():
        if key in data and data[key] is not None:
            prop_type = prop_schema.get("type")
            value = data[key]
            if prop_type == "string" and not isinstance(value, str):
                errors.append("{0}{1}: expected string, got {2}".format(path_prefix(path), key, type(value).__name__))
            elif prop_type == "number" and not isinstance(value, (int, float)):
                errors.append("{0}{1}: expected number, got {2}".format(path_prefix(path), key, type(value).__name__))
            elif prop_type == "integer" and not isinstance(value, int):
                errors.append("{0}{1}: expected integer, got {2}".format(path_prefix(path), key, type(value).__name__))
            elif prop_type == "boolean" and not isinstance(value, bool):
                errors.append("{0}{1}: expected boolean, got {2}".format(path_prefix(path), key, type(value).__name__))
            elif prop_type == "array":
                if not isinstance(value, list):
                    errors.append("{0}{1}: expected array, got {2}".format(path_prefix(path), key, type(value).__name__))
                elif "items" in prop_schema:
                    items_schema = prop_schema["items"]
                    for i, item in enumerate(value):
                        item_path = "{0}.{1}[{2}]".format(path, key, i)
                        if items_schema.get("type") == "object":
                            errors.extend(validate_json_schema(item, items_schema, item_path))
            elif prop_type == "object" and isinstance(value, dict):
                sub_path = "{0}.{1}".format(path, key) if path else key
                errors.extend(validate_json_schema(value, prop_schema, sub_path))

    # Check for enum constraints
    enum_values = schema.get("enum")
    if enum_values and data not in enum_values:
        errors.append("{0}: value must be one of {1}".format(path_prefix(path)[:-2] if path else "$", json.dumps(enum_values)))

    return errors


def path_prefix(path):
    if path:
        return "{0}.".format(path)
    return ""
