# -*- coding: utf-8 -*-
"""Tests for the read-only Volcengine usage client and HTTP/signing wrapper."""
from __future__ import absolute_import

import json
from types import SimpleNamespace

import pytest
import requests

from backend.volcengine.client import VolcengineAPIError, VolcengineHTTPClient
from backend.volcengine.usage_client import VolcengineUsageClient


def _cfg():
    return SimpleNamespace(
        VOLCENGINE_ACCESS_KEY_ID='AK',
        VOLCENGINE_SECRET_ACCESS_KEY='SK',
        VOLCENGINE_ARK_REGION='cn-beijing',
        VOLCENGINE_ARK_PROJECT='default',
        VOLCENGINE_SYNC_TIMEOUT_S=20,
        VOLCENGINE_SYNC_MAX_RETRIES=0,
    )


class FakeUsageHTTP(object):
    def __init__(self, payloads):
        self.payloads = list(payloads) if isinstance(payloads, list) else [payloads]
        self.calls = []

    def post_json(self, host, action, version, body, region, service, **kwargs):
        self.calls.append({
            'host': host, 'action': action, 'version': version,
            'body': body, 'region': region, 'service': service,
        })
        return self.payloads.pop(0)


def test_inference_usage_parses_dynamic_fields():
    payload = {
        'ResponseMetadata': {'RequestId': 'req-1'},
        'Result': {
            'Fields': [
                {'Name': 'AccountID', 'Type': 'BIGINT'},
                {'Name': 'ModelName', 'Type': 'STRING'},
                {'Name': 'ApikeyID', 'Type': 'STRING'},
                {'Name': 'InputTokens', 'Type': 'BIGINT'},
                {'Name': 'OutputTokens', 'Type': 'BIGINT'},
                {'Name': 'TotalTokens', 'Type': 'BIGINT'},
                {'Name': 'ReqCnt', 'Type': 'BIGINT'},
                {'Name': 'ImageCount', 'Type': 'BIGINT'},
                {'Name': 'Day', 'Type': 'DATE'},
            ],
            'Data': [[
                '2100', 'doubao-seedream', 'apikey-1',
                '12', 34, 46, 2, 1, '2026-10-31',
            ]],
            'DataCount': 1,
        },
    }
    http = FakeUsageHTTP(payload)
    client = VolcengineUsageClient(_cfg(), http_client=http)
    result = client.get_inference_usage('2026-10-29', '2026-10-31')
    assert result['rows'] == [{
        'AccountID': 2100,
        'ModelName': 'doubao-seedream',
        'ApikeyID': 'apikey-1',
        'InputTokens': 12,
        'OutputTokens': 34,
        'TotalTokens': 46,
        'ReqCnt': 2,
        'ImageCount': 1,
        'Day': '2026-10-31',
    }]
    assert result['request_id'] == 'req-1'
    assert result['query_interval'] == 'Day'
    call = http.calls[0]
    assert call['host'] == 'ark.cn-beijing.volcengineapi.com'
    assert call['action'] == 'GetInferenceUsage'
    assert call['version'] == '2024-01-01'
    assert call['region'] == 'cn-beijing'
    assert call['service'] == 'ark'
    assert call['body']['StartTime'] == '2026-10-29'
    assert call['body']['EndTime'] == '2026-10-31'


def test_inference_usage_empty_and_dict_rows():
    empty_http = FakeUsageHTTP({'Result': {'Fields': [], 'Data': []}})
    client = VolcengineUsageClient(_cfg(), http_client=empty_http)
    result = client.get_inference_usage('2026-10-29', '2026-10-31', filters=None)
    assert result['rows'] == []

    dict_http = FakeUsageHTTP({'Result': {'Fields': [], 'Data': [{'Day': '2026-10-31'}]}})
    client = VolcengineUsageClient(_cfg(), http_client=dict_http)
    result = client.get_inference_usage('2026-10-29', '2026-10-31')
    assert result['rows'] == [{'Day': '2026-10-31'}]


def test_dimension_filters_and_invalid_dates():
    http = FakeUsageHTTP({'Result': {'Fields': [], 'Data': []}})
    client = VolcengineUsageClient(_cfg(), http_client=http)
    filters = client.dimension_filters()
    assert filters == [
        {'Key': 'ApikeyID', 'Values': []},
        {'Key': 'ModelName', 'Values': []},
    ]
    client.get_inference_usage('2026-10-29', '2026-10-31', filters=filters)
    assert http.calls[-1]['body']['Filters'] == filters
    with pytest.raises(VolcengineAPIError) as exc:
        client.get_inference_usage('2026/10/29', '2026-10-31')
    assert exc.value.category == 'invalid_param'
    with pytest.raises(VolcengineAPIError):
        client.get_inference_usage('2026-10-31', '2026-10-29')


def test_task_and_request_usage():
    http = FakeUsageHTTP([
        {'Result': {'TaskID': 'cgt-1', 'APIKeyID': 'apikey-1',
                    'OutputTokens': 100, 'BillingStatus': 'normal'}},
        {'Result': {'Records': [
            {'RequestID': 'req-1', 'InputTokens': 10, 'OutputTokens': 2},
            {'RequestID': 'req-1', 'InputTokens': 3, 'OutputTokens': 1},
        ]}},
    ])
    client = VolcengineUsageClient(_cfg(), http_client=http)
    task = client.get_inference_task_usage('cgt-1')
    assert task['APIKeyID'] == 'apikey-1'
    assert http.calls[-1]['action'] == 'GetInferenceTaskUsage'
    records = client.get_inference_request_usage('req-1', '2026-10-31 10:00:00')
    assert len(records) == 2
    assert http.calls[-1]['action'] == 'GetInferenceRequestUsage'
    with pytest.raises(VolcengineAPIError):
        client.get_inference_task_usage('')
    with pytest.raises(VolcengineAPIError):
        client.get_inference_request_usage('req-1', '2026-10-31 10:30:00')


class FakeResponse(object):
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError('not json')
        return self._payload


class FakeSession(object):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.last_headers = None

    def post(self, url, headers=None, data=None, timeout=None, allow_redirects=None):
        self.calls.append({
            'url': url, 'headers': dict(headers or {}), 'data': data,
            'timeout': timeout, 'allow_redirects': allow_redirects,
        })
        self.last_headers = dict(headers or {})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _http_client(session, max_retries=0):
    sleeps = []
    client = VolcengineHTTPClient(
        'AK', 'SK', session=session, sleeper=lambda seconds: sleeps.append(seconds),
        clock=lambda: 0, qps_interval_s=0, max_retries=max_retries,
    )
    return client, sleeps


def test_http_client_error_normalization_and_no_secret_leak():
    cases = [
        (403, {'ResponseMetadata': {'Error': {'Code': 'AccessDenied', 'Message': 'denied'}}}, 'no_permission'),
        (429, {'ResponseMetadata': {'Error': {'Code': 'Throttling', 'Message': 'slow down'}}}, 'throttled'),
        (400, {'ResponseMetadata': {'Error': {'Code': 'InvalidParameter', 'Message': 'bad'}}}, 'invalid_param'),
        (401, {'ResponseMetadata': {'Error': {'Code': 'InvalidAuthorization', 'Message': 'bad auth'}}}, 'unauthorized'),
        (200, {'ResponseMetadata': {'Error': {'Code': 'InternalError', 'Message': 'boom'}}}, 'sync_error'),
    ]
    for status, payload, category in cases:
        session = FakeSession([FakeResponse(status, payload)])
        client, _ = _http_client(session)
        with pytest.raises(VolcengineAPIError) as exc:
            client.post_json(
                'ark.cn-beijing.volcengineapi.com', 'GetInferenceUsage',
                '2024-01-01', {}, 'cn-beijing', 'ark',
            )
        assert exc.value.category == category
        assert 'SK' not in str(exc.value)
        assert 'SK' not in session.last_headers.get('Authorization', '')
        assert session.last_headers['X-Date']
        assert session.last_headers['X-Content-Sha256']


def test_http_client_retries_throttle_and_server_errors():
    session = FakeSession([
        FakeResponse(429, {'ResponseMetadata': {'Error': {
            'Code': 'Throttling', 'Message': 'slow'}}}, headers={'Retry-After': '0'}),
        FakeResponse(200, {'ResponseMetadata': {'RequestId': 'ok'}, 'Result': {'ok': True}}),
    ])
    client, sleeps = _http_client(session, max_retries=1)
    payload = client.post_json(
        'ark.cn-beijing.volcengineapi.com', 'GetInferenceUsage',
        '2024-01-01', {'x': 1}, 'cn-beijing', 'ark',
    )
    assert payload['Result'] == {'ok': True}
    assert len(session.calls) == 2
    assert sleeps

    retry_session = FakeSession([
        requests.exceptions.Timeout(),
        FakeResponse(200, {'Result': {'ok': True}}),
    ])
    client, _ = _http_client(retry_session, max_retries=1)
    payload = client.post_json(
        'ark.cn-beijing.volcengineapi.com', 'GetInferenceUsage',
        '2024-01-01', {}, 'cn-beijing', 'ark',
    )
    assert payload['Result'] == {'ok': True}


def test_http_client_rejects_redirect_and_missing_credentials():
    session = FakeSession([FakeResponse(302, {}, headers={'Location': 'https://evil'})])
    client, _ = _http_client(session)
    with pytest.raises(VolcengineAPIError) as exc:
        client.post_json(
            'ark.cn-beijing.volcengineapi.com', 'GetInferenceUsage',
            '2024-01-01', {}, 'cn-beijing', 'ark',
        )
    assert exc.value.category == 'invalid_response'

    empty = VolcengineHTTPClient('', '', session=FakeSession([]))
    with pytest.raises(VolcengineAPIError) as exc:
        empty.post_json(
            'ark.cn-beijing.volcengineapi.com', 'GetInferenceUsage',
            '2024-01-01', {}, 'cn-beijing', 'ark',
        )
    assert exc.value.category == 'unconfigured'
