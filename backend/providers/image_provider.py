# -*- coding: utf-8 -*-
"""
ComfyUI image generation provider.
"""
from __future__ import absolute_import

import json
import logging
import os
import time
import uuid

import requests

from .base import BaseImageProvider, ProviderError

logger = logging.getLogger(__name__)


class ComfyUIProvider(BaseImageProvider):
    """ComfyUI image generation provider via REST API."""

    def __init__(self, base_url, workflow_file=None):
        self.base_url = (base_url or "").rstrip("/")
        self.workflow_file = workflow_file

    def _load_workflow(self):
        """Load workflow JSON from file."""
        if self.workflow_file and os.path.exists(self.workflow_file):
            with open(self.workflow_file, "r") as f:
                return json.load(f)
        # Default minimal workflow
        return self._default_workflow()

    def _default_workflow(self):
        """Return a minimal text-to-image workflow."""
        return {
            "3": {"class_type": "KSampler", "inputs": {"seed": -1, "steps": 20, "cfg": 7.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 576, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]}},
        }

    def _inject_params(self, workflow, prompt, negative_prompt, seed, width, height, quantity):
        """Inject generation parameters into ComfyUI workflow JSON."""
        wf = json.loads(json.dumps(workflow))  # deep copy

        for node_id, node in wf.items():
            class_type = node.get("class_type", "")

            if class_type == "KSampler":
                if seed >= 0:
                    node["inputs"]["seed"] = seed
                else:
                    node["inputs"]["seed"] = int(time.time() * 1000) % 2147483647

            elif class_type == "CLIPTextEncode":
                title = node.get("_meta", {}).get("title") if isinstance(node.get("_meta"), dict) else None
                if title == "CLIP Text Encode (Negative)":
                    node["inputs"]["text"] = negative_prompt or ""
                else:
                    node["inputs"]["text"] = prompt or ""

            elif class_type == "EmptyLatentImage":
                node["inputs"]["width"] = width
                node["inputs"]["height"] = height
                node["inputs"]["batch_size"] = quantity

        return wf

    def submit_generation(self, prompt, negative_prompt=None, seed=-1,
                          width=1024, height=576, quantity=1):
        """Submit image generation to ComfyUI."""
        if not self.base_url:
            raise ProviderError("ComfyUI base URL not configured", error_type="comfyui_not_configured")

        workflow = self._load_workflow()
        injected = self._inject_params(workflow, prompt, negative_prompt, seed, width, height, quantity)

        payload = {"prompt": injected}

        url = "{0}/prompt".format(self.base_url)
        try:
            r = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.ConnectionError:
            raise ProviderError("Cannot connect to ComfyUI at {0}".format(self.base_url), error_type="comfyui_connection_error")
        except requests.exceptions.Timeout:
            raise ProviderError("ComfyUI request timed out", error_type="comfyui_timeout")
        except Exception as e:
            raise ProviderError("ComfyUI error: {0}".format(str(e)), error_type="comfyui_unknown_error")

        if r.status_code >= 400:
            raise ProviderError(
                "ComfyUI returned {0}: {1}".format(r.status_code, r.text[:500]),
                error_type="comfyui_server_error",
            )

        data = r.json() or {}
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ProviderError("ComfyUI response missing prompt_id", error_type="comfyui_invalid_response")

        return prompt_id

    def poll_generation(self, prompt_id):
        """Poll ComfyUI generation status via history endpoint."""
        url = "{0}/history/{1}".format(self.base_url, prompt_id)
        try:
            r = requests.get(url, timeout=10)
        except Exception as e:
            raise ProviderError("ComfyUI poll error: {0}".format(str(e)), error_type="comfyui_poll_error")

        if r.status_code >= 400:
            raise ProviderError(
                "ComfyUI history returned {0}".format(r.status_code),
                error_type="comfyui_history_error",
            )

        return r.json() or {}

    def wait_until_done(self, prompt_id, timeout_s=600, poll_interval_s=3):
        """Poll ComfyUI until generation completes."""
        start = time.time()
        while time.time() - start < timeout_s:
            history = self.poll_generation(prompt_id)
            if history and prompt_id in history:
                return history[prompt_id]
            time.sleep(poll_interval_s)

        raise ProviderError("ComfyUI generation timed out after {0}s".format(timeout_s), error_type="comfyui_timeout")

    def download_results(self, prompt_id, output_dir, max_bytes=None):
        """Synchronous compatibility helper: wait, then download."""
        history_entry = self.wait_until_done(prompt_id)
        return self.download_results_from_history(
            history_entry, output_dir, max_bytes=max_bytes
        )

    def download_results_from_history(self, history_entry, output_dir, max_bytes=None):
        """Download images described by a completed ComfyUI history entry.

        The worker calls this after polling, so no blocking wait is involved.
        Filenames are never trusted: a UUID-based name is generated locally and
        the payload is checked for an image magic header and size limit.
        """
        outputs = (history_entry or {}).get("outputs") or {}
        file_paths = []
        max_bytes = max_bytes or 200 * 1024 * 1024

        os.makedirs(output_dir, exist_ok=True)

        for _node_id, node_outputs in outputs.items():
            images = (node_outputs or {}).get("images") or []
            for img_info in images:
                filename = os.path.basename(str(img_info.get("filename") or ""))
                if not filename:
                    continue
                view_url = "{0}/view".format(self.base_url)
                params = {
                    "filename": filename,
                    "subfolder": img_info.get("subfolder", ""),
                    "type": img_info.get("type", "output"),
                }
                try:
                    response = requests.get(
                        view_url, params=params, timeout=60, stream=True
                    )
                except requests.exceptions.RequestException as exc:
                    raise ProviderError(
                        "ComfyUI 下载失败: {0}".format(str(exc)[:200]),
                        error_type="comfyui_download_error",
                    )
                if response.status_code != 200:
                    response.close()
                    continue

                chunks = []
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        response.close()
                        raise ProviderError(
                            "ComfyUI 图片超过大小限制", error_type="comfyui_file_too_large"
                        )
                    chunks.append(chunk)
                response.close()
                raw = b"".join(chunks)
                if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                    extension = ".png"
                elif raw.startswith(b"\xff\xd8\xff"):
                    extension = ".jpg"
                elif len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                    extension = ".webp"
                else:
                    raise ProviderError(
                        "ComfyUI 返回了非图片内容",
                        error_type="comfyui_invalid_file",
                    )
                out_path = os.path.join(output_dir, uuid.uuid4().hex + extension)
                with open(out_path, "wb") as handle:
                    handle.write(raw)
                file_paths.append(out_path)

        return file_paths
