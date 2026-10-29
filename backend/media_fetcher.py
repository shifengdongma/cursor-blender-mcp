# -*- coding: utf-8 -*-
"""Safe download of provider result URLs.

Prevents SSRF, redirect abuse, unbounded disk writes and content-type spoofing.
Only provider-returned URLs are ever passed here; user-supplied URLs are never
accepted by the API.
"""
from __future__ import absolute_import

import ipaddress
import os
import socket
import uuid
from urllib.parse import urljoin, urlsplit

import requests


class MediaFetchError(RuntimeError):
    def __init__(self, message, code="download_error"):
        RuntimeError.__init__(self, message)
        self.code = code


_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_VIDEO_TYPES = {"video/mp4", "video/webm", "application/octet-stream", "binary/octet-stream"}


def _resolve_host(host, port):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise MediaFetchError("无法解析下载域名: {0}".format(exc), "dns_error")
    addresses = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise MediaFetchError("下载域名没有可用地址", "dns_error")
    return addresses


def validate_url(url, allowed_private_hosts=None):
    allowed_private_hosts = set(allowed_private_hosts or [])
    try:
        parts = urlsplit(url)
    except ValueError:
        raise MediaFetchError("无效的下载 URL", "invalid_url")
    if parts.scheme not in ("http", "https"):
        raise MediaFetchError("下载 URL 必须使用 http/https", "invalid_url")
    if parts.username or parts.password:
        raise MediaFetchError("下载 URL 不能包含凭据", "invalid_url")
    host = parts.hostname
    if not host:
        raise MediaFetchError("下载 URL 缺少域名", "invalid_url")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise MediaFetchError("下载 URL 端口无效", "invalid_url")
    if port not in (80, 443):
        raise MediaFetchError("下载 URL 端口不受支持", "invalid_url")
    if parts.scheme == "http" and host not in allowed_private_hosts:
        raise MediaFetchError("外部结果下载必须使用 HTTPS", "invalid_url")

    for address in _resolve_host(host, port):
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise MediaFetchError("下载域名解析结果无效", "dns_error")
        if ip.is_global:
            continue
        if host in allowed_private_hosts:
            continue
        raise MediaFetchError("下载 URL 指向非公网地址", "ssrf_blocked")
    return parts


def _matches_magic(kind, header):
    if kind == "image":
        return (
            header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"\xff\xd8\xff")
            or (len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        )
    if kind == "video":
        return (
            (len(header) >= 12 and header[4:8] == b"ftyp")
            or header.startswith(b"\x1aE\xdf\xa3")
        )
    return True


def _extension(kind, content_type, header):
    if kind == "image":
        if header.startswith(b"\x89PNG"):
            return ".png"
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if len(header) >= 12 and header[:4] == b"RIFF":
            return ".webp"
    if kind == "video":
        if len(header) >= 12 and header[4:8] == b"ftyp":
            return ".mp4"
        if header.startswith(b"\x1aE\xdf\xa3"):
            return ".webm"
    return ".bin"


def download_url(url, dest_dir, kind="video", max_bytes=500 * 1024 * 1024,
                 timeout_s=180, allowed_private_hosts=None):
    """Download a provider URL to dest_dir; returns the local file path."""
    current = url
    os.makedirs(dest_dir, exist_ok=True)
    for _ in range(4):
        validate_url(current, allowed_private_hosts=allowed_private_hosts)
        try:
            response = requests.get(
                current, stream=True, allow_redirects=False, timeout=timeout_s
            )
        except requests.exceptions.RequestException as exc:
            raise MediaFetchError("下载失败: {0}".format(str(exc)[:200]), "download_failed")

        try:
            if 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                if not location:
                    raise MediaFetchError("下载重定向缺少目标", "redirect_invalid")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise MediaFetchError(
                    "下载返回 HTTP {0}".format(response.status_code), "download_http_error"
                )

            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            allowed_types = _IMAGE_TYPES if kind == "image" else _VIDEO_TYPES
            if content_type and content_type not in allowed_types:
                raise MediaFetchError(
                    "下载内容类型不允许: {0}".format(content_type), "invalid_content_type"
                )

            temp_name = "{0}.part".format(uuid.uuid4().hex)
            temp_path = os.path.join(dest_dir, temp_name)
            total = 0
            header = b""
            try:
                with open(temp_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            raise MediaFetchError("下载文件超过大小限制", "file_too_large")
                        if len(header) < 16:
                            header += chunk[:16 - len(header)]
                        handle.write(chunk)
                if total == 0:
                    raise MediaFetchError("下载文件为空", "empty_file")
                if not _matches_magic(kind, header):
                    raise MediaFetchError("下载文件类型校验失败", "invalid_file_magic")
                final_path = os.path.join(dest_dir, uuid.uuid4().hex + _extension(kind, content_type, header))
                os.replace(temp_path, final_path)
                return final_path
            except Exception:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
                raise
        finally:
            response.close()
    raise MediaFetchError("下载重定向次数过多", "too_many_redirects")
