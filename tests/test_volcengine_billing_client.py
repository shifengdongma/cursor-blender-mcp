# -*- coding: utf-8 -*-
"""Tests for the read-only Volcengine billing client and Decimal helpers."""
from __future__ import absolute_import

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.volcengine.billing_client import (
    VolcengineBillingClient,
    decimal_text,
    normalize_amounts,
    parse_decimal,
    sum_decimals,
)
from backend.volcengine.client import VolcengineAPIError


def _cfg():
    return SimpleNamespace(
        VOLCENGINE_ACCESS_KEY_ID='AK',
        VOLCENGINE_SECRET_ACCESS_KEY='SK',
        VOLCENGINE_BILLING_REGION='cn-north-1',
        VOLCENGINE_SYNC_TIMEOUT_S=20,
        VOLCENGINE_SYNC_MAX_RETRIES=0,
    )


class FakeBillingHTTP(object):
    def __init__(self, payloads):
        self.payloads = list(payloads) if isinstance(payloads, list) else [payloads]
        self.calls = []

    def post_json(self, host, action, version, body, region, service, **kwargs):
        self.calls.append({
            'host': host, 'action': action, 'version': version,
            'body': body, 'region': region, 'service': service,
        })
        return self.payloads.pop(0)


def _overview_payload():
    return {
        'ResponseMetadata': {'RequestId': 'req-overview'},
        'Result': {
            'List': [
                {
                    'BillPeriod': '2026-10', 'Product': 'Doubao-Seedream',
                    'ProductZh': '豆包图像创作模型', 'BillingMode': '2',
                    'BillCategoryParent': 'consume', 'Currency': 'CNY',
                    'OriginalBillAmount': '1.2300', 'PreferentialBillAmount': '0.0300',
                    'RoundBillAmount': '0.0000', 'DiscountBillAmount': '1.2000',
                    'CouponAmount': '0.00', 'PayableAmount': '1.2000',
                    'PaidAmount': '0.00', 'UnpaidAmount': '1.2000',
                },
            ],
            'Total': 1, 'Limit': 300, 'Offset': 0,
        },
    }


def test_decimal_helpers_are_exact():
    assert parse_decimal('0.1') + parse_decimal('0.2') == Decimal('0.3')
    assert sum_decimals(['0.1', '0.2', None, 'bad']) == Decimal('0.3')
    assert decimal_text(Decimal('1.2300')) == '1.2300'
    assert decimal_text('1.235', places=2) == '1.24'
    normalized = normalize_amounts({
        'OriginalBillAmount': '1.2300', 'Product': 'ark_bd', 'Count': '40',
    })
    assert normalized['OriginalBillAmount'] == '1.2300'
    assert normalized['Count'] == '40'
    assert normalized['Product'] == 'ark_bd'


def test_overview_bill_detail_and_split_calls_are_signed_with_expected_bodies():
    overview_http = FakeBillingHTTP(_overview_payload())
    client = VolcengineBillingClient(_cfg(), http_client=overview_http)
    result = client.list_bill_overview_by_prod(
        '2026-10', product='ark_bd,Doubao-Seedream'
    )
    assert result['items'][0]['PayableAmount'] == '1.2000'
    assert result['total'] == 1
    call = overview_http.calls[0]
    assert call['host'] == 'billing.volcengineapi.com'
    assert call['action'] == 'ListBillOverviewByProd'
    assert call['version'] == '2022-01-01'
    assert call['region'] == 'cn-north-1'
    assert call['service'] == 'billing'
    assert call['body']['BillPeriod'] == '2026-10'
    assert call['body']['Product'] == ['ark_bd', 'Doubao-Seedream']
    assert call['body']['NeedRecordNum'] == 1
    assert call['body']['IgnoreZero'] == 1

    detail_http = FakeBillingHTTP({'Result': {'List': [], 'Total': 0}})
    client = VolcengineBillingClient(_cfg(), http_client=detail_http)
    client.list_bill_detail(
        '2026-10', limit=10, offset=20, expense_date='2026-10-30',
        group_period=2,
    )
    body = detail_http.calls[0]['body']
    assert body['GroupPeriod'] == 2
    assert body['ExpenseDate'] == '2026-10-30'
    assert body['Limit'] == 10
    assert body['Offset'] == 20

    split_http = FakeBillingHTTP({'Result': {'List': [], 'Total': 0}})
    client = VolcengineBillingClient(_cfg(), http_client=split_http)
    client.list_split_bill_detail(
        '2026-10', split_dimension={'ark_bd': 'apikey_id'}, group_period=2,
    )
    split_body = split_http.calls[0]['body']
    assert split_body['SplitDimension'] == '{"ark_bd":"apikey_id"}'
    assert json.loads(split_body['SplitDimension']) == {'ark_bd': 'apikey_id'}


def test_bill_list_and_balance_normalization():
    http = FakeBillingHTTP([
        {'Result': {'List': [{'BillID': 'Bill1', 'PayStatus': 'CompletedSettle',
                              'PayableAmount': '10.00', 'Currency': 'CNY'}],
                    'Total': 1}},
        {'Result': {'AccountID': 2100, 'AvailableBalance': '77.0100',
                    'Currency': 'CNY', 'ArrearsBalance': '0.00'}},
    ])
    client = VolcengineBillingClient(_cfg(), http_client=http)
    bill = client.list_bill('2026-10')
    assert bill['items'][0]['PayStatus'] == 'CompletedSettle'
    assert bill['items'][0]['PayableAmount'] == '10.00'
    balance = client.query_balance_acct()
    assert balance['AvailableBalance'] == '77.0100'
    assert balance['Currency'] == 'CNY'
    assert balance['_request_id'] is None


def test_invalid_period_limit_and_date_are_rejected():
    client = VolcengineBillingClient(_cfg(), http_client=FakeBillingHTTP({}))
    with pytest.raises(VolcengineAPIError) as exc:
        client.list_bill_overview_by_prod('2026/10')
    assert exc.value.category == 'invalid_param'
    with pytest.raises(VolcengineAPIError):
        client.list_bill_overview_by_prod('2026-10', limit=301)
    with pytest.raises(VolcengineAPIError):
        client.list_bill_detail('2026-10', expense_date='10/30/2026')
    with pytest.raises(VolcengineAPIError):
        client.list_bill_overview_by_prod('2024-01')  # older than 24 months
