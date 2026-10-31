# -*- coding: utf-8 -*-
"""Deterministic tests for the Volcengine Signature V4 implementation."""
from __future__ import absolute_import

from datetime import datetime, timezone

import pytest

from backend.volcengine.auth import sign_headers

HOST = 'ark.cn-beijing.volcengineapi.com'
QUERY = {'Action': 'GetInferenceUsage', 'Version': '2024-01-01'}
BODY = (
    '{"StartTime":"2026-10-29","EndTime":"2026-10-31",'
    '"QueryInterval":"Day","ProjectName":"default"}'
)


def test_signing_is_deterministic_and_does_not_expose_secret():
    headers = sign_headers(
        'POST', HOST, '/', QUERY, BODY,
        'AKTESTEXAMPLE', 'SKTESTEXAMPLE', 'cn-beijing', 'ark',
        now=datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert headers['X-Date'] == '20261031T100000Z'
    assert headers['X-Content-Sha256'] == (
        '23417bf94e5880eae64d91cbca71db83ca41b4d3cdc3d8bd705141eaf11e6f88'
    )
    assert headers['Authorization'] == (
        'HMAC-SHA256 Credential=AKTESTEXAMPLE/20261031/cn-beijing/ark/request, '
        'SignedHeaders=content-type;host;x-content-sha256;x-date, '
        'Signature=a455bd7c4b0c98dced4417af6d6d58e54820911965146c0d780943941afc77db'
    )
    assert 'SKTESTEXAMPLE' not in headers['Authorization']
    assert headers['Content-Type'] == 'application/json'
    assert headers['Host'] == HOST


def test_body_or_region_changes_signature():
    base = sign_headers(
        'POST', HOST, '/', QUERY, BODY,
        'AK', 'SK', 'cn-beijing', 'ark',
        now=datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    )
    changed_body = sign_headers(
        'POST', HOST, '/', QUERY, BODY.replace('2026-10-29', '2026-10-30'),
        'AK', 'SK', 'cn-beijing', 'ark',
        now=datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    )
    changed_region = sign_headers(
        'POST', HOST, '/', QUERY, BODY,
        'AK', 'SK', 'cn-north-1', 'billing',
        now=datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc),
    )
    assert base['Authorization'] != changed_body['Authorization']
    assert base['Authorization'] != changed_region['Authorization']


def test_missing_credentials_are_rejected_without_secret_leak():
    with pytest.raises(ValueError) as exc:
        sign_headers('POST', HOST, '/', QUERY, BODY, '', 'SECRET', 'cn-beijing', 'ark')
    assert 'SECRET' not in str(exc.value)
    with pytest.raises(ValueError):
        sign_headers('POST', HOST, '/', QUERY, BODY, 'AK', '', 'cn-beijing', 'ark')
