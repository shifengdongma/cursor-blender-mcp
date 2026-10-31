# -*- coding: utf-8 -*-
"""Volcengine OpenAPI Signature V4 (HMAC-SHA256).

This is a small, dependency-free port of the official ``volc-sdk-python``
SignerV4 canonicalisation rules.  It is used only for the read-only Ark usage
and billing-center OpenAPI, never for inference calls.

References:
- https://github.com/volcengine/volc-sdk-python (auth/SignerV4.py, util/Util.py)
- Volcengine OpenAPI common parameters / signature documentation
"""
from __future__ import absolute_import

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote

ALGORITHM = 'HMAC-SHA256'
CONTENT_TYPE = 'application/json'


def _hmac_sha256(key, content):
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hmac.new(key, content, hashlib.sha256).digest()


def _sha256_hex(content):
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()


def _norm_uri(path):
    return quote(path or '/').replace('%2F', '/').replace('+', '%20')


def _norm_query(params):
    parts = []
    for key in sorted((params or {}).keys()):
        value = params[key]
        if isinstance(value, (list, tuple)):
            for item in value:
                parts.append(
                    '{0}={1}'.format(
                        quote(str(key), safe='-_.~'),
                        quote(str(item), safe='-_.~'),
                    )
                )
        else:
            parts.append(
                '{0}={1}'.format(
                    quote(str(key), safe='-_.~'),
                    quote(str(value), safe='-_.~'),
                )
            )
    return '&'.join(parts).replace('+', '%20')


def format_x_date(now=None):
    now = now or datetime.now(timezone.utc)
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        return now.strftime('%Y%m%dT%H%M%SZ')
    return str(now)


def sign_headers(method, host, path, query, body, access_key, secret_key,
                 region, service, now=None, extra_headers=None):
    """Return signed HTTP headers for one Volcengine OpenAPI request.

    ``body`` is the exact JSON string that will be sent.  The caller must send
    the same bytes and these headers.  The secret key never leaves this
    function and is never included in the returned headers or exceptions.
    """
    if not access_key or not secret_key:
        raise ValueError('missing_volcengine_management_credentials')
    if not host or not region or not service:
        raise ValueError('missing_volcengine_signing_scope')

    body_text = body if isinstance(body, str) else (body or b'').decode('utf-8')
    body_bytes = body_text.encode('utf-8')
    body_hash = _sha256_hex(body_bytes)

    x_date = format_x_date(now)
    short_date = x_date[:8]
    signed_headers_map = {
        'content-type': CONTENT_TYPE,
        'host': host,
        'x-content-sha256': body_hash,
        'x-date': x_date,
    }
    for key, value in (extra_headers or {}).items():
        lowered = str(key).lower()
        if lowered.startswith('x-') and lowered not in signed_headers_map:
            signed_headers_map[lowered] = str(value)

    signed_header_names = sorted(signed_headers_map.keys())
    signed_headers = ';'.join(signed_header_names)
    signed_str = ''.join(
        '{0}:{1}\n'.format(name, signed_headers_map[name])
        for name in signed_header_names
    )

    canonical_request = '\n'.join([
        method.upper(),
        _norm_uri(path or '/'),
        _norm_query(query),
        signed_str,
        signed_headers,
        body_hash,
    ])
    credential_scope = '{0}/{1}/{2}/request'.format(short_date, region, service)
    string_to_sign = '\n'.join([
        ALGORITHM,
        x_date,
        credential_scope,
        _sha256_hex(canonical_request),
    ])
    signing_key = _hmac_sha256(secret_key.encode('utf-8'), short_date)
    signing_key = _hmac_sha256(signing_key, region)
    signing_key = _hmac_sha256(signing_key, service)
    signing_key = _hmac_sha256(signing_key, 'request')
    signature = hmac.new(
        signing_key, string_to_sign.encode('utf-8'), hashlib.sha256
    ).hexdigest()

    headers = {
        'Host': host,
        'Content-Type': CONTENT_TYPE,
        'X-Date': x_date,
        'X-Content-Sha256': body_hash,
        'Authorization': (
            '{0} Credential={1}/{2}, SignedHeaders={3}, Signature={4}'
        ).format(ALGORITHM, access_key, credential_scope, signed_headers, signature),
    }
    for key, value in (extra_headers or {}).items():
        headers[key] = value
    return headers
