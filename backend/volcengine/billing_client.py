# -*- coding: utf-8 -*-
"""Read-only Volcengine Billing Center OpenAPI client.

Official amounts are decimal strings.  They are parsed with ``Decimal`` and
returned as canonical strings; floats are never used for official money.
"""
from __future__ import absolute_import

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .client import VolcengineAPIError, VolcengineHTTPClient

BILLING_VERSION = '2022-01-01'
BILLING_SERVICE = 'billing'
BILLING_HOST = 'billing.volcengineapi.com'
BEIJING_TZ = timezone(timedelta(hours=8))

_AMOUNT_FIELDS = set([
    'OriginalBillAmount', 'PreferentialBillAmount', 'DiscountBillAmount',
    'CouponAmount', 'PayableAmount', 'PaidAmount', 'UnpaidAmount',
    'RoundAmount', 'RoundBillAmount', 'CreditCarriedAmount',
    'SettleTax', 'SettlePretaxRealValue', 'SettlePosttaxAmount',
    'SettlePretaxAmount', 'PosttaxAmount', 'PretaxAmount', 'Tax',
    'SettleRealValue', 'RealValue', 'PretaxRealValue',
    'SavingPlanOriginalAmount', 'PreTaxPayableAmount',
    'SettlePayableAmount', 'SettlePreTaxPayableAmount',
    'PointDeductAmount', 'CouponDeductionAmount', 'MarketPrice',
    'SavingPlanDeductionDiscountAmount',
    'SavingPlanDeductionDiscountTotalAmount', 'Price',
    'DiscountBizUnitPrice', 'SplitItemAmount', 'Count', 'UsageAmount',
])


def parse_decimal(value):
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def decimal_text(value, places=None):
    parsed = parse_decimal(value)
    if parsed is None:
        return None
    if places is not None:
        parsed = parsed.quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)
    return format(parsed, 'f')


def sum_decimals(values):
    total = Decimal('0')
    for value in values or []:
        parsed = parse_decimal(value)
        if parsed is not None:
            total += parsed
    return total


def normalize_amounts(row):
    if not isinstance(row, dict):
        return {}
    normalized = dict(row)
    for key in _AMOUNT_FIELDS:
        if key in normalized:
            normalized[key] = decimal_text(normalized[key])
    return normalized


def _validate_bill_period(value):
    try:
        parsed = datetime.strptime(str(value), '%Y-%m')
    except (TypeError, ValueError):
        raise VolcengineAPIError('invalid_param', 'BillPeriod 格式应为 YYYY-MM')
    current = datetime.now(BEIJING_TZ)
    months_back = (current.year - parsed.year) * 12 + (current.month - parsed.month)
    if months_back < 0 or months_back > 24:
        raise VolcengineAPIError(
            'invalid_param', 'BillPeriod 只能查询当前月或最近 24 个月'
        )
    return parsed.strftime('%Y-%m')


def _validate_limit(value, default=300):
    try:
        limit = int(value if value is not None else default)
    except (TypeError, ValueError):
        raise VolcengineAPIError('invalid_param', 'Limit 必须为整数')
    if limit < 1 or limit > 300:
        raise VolcengineAPIError('invalid_param', 'Limit 必须在 1 到 300 之间')
    return limit


def _validate_offset(value):
    try:
        offset = int(value or 0)
    except (TypeError, ValueError):
        raise VolcengineAPIError('invalid_param', 'Offset 必须为整数')
    if offset < 0:
        raise VolcengineAPIError('invalid_param', 'Offset 不能为负数')
    return offset


def _product_values(value):
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item]
    return [item.strip() for item in str(value).split(',') if item.strip()] or None


def _split_dimension(value):
    if not value:
        return None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError):
            pass
    return value


class VolcengineBillingClient(object):
    def __init__(self, cfg, http_client=None):
        self.cfg = cfg
        self.http = http_client or VolcengineHTTPClient(
            cfg.VOLCENGINE_ACCESS_KEY_ID,
            cfg.VOLCENGINE_SECRET_ACCESS_KEY,
            timeout_s=getattr(cfg, 'VOLCENGINE_SYNC_TIMEOUT_S', 20),
            max_retries=getattr(cfg, 'VOLCENGINE_SYNC_MAX_RETRIES', 2),
        )
        self.region = getattr(cfg, 'VOLCENGINE_BILLING_REGION', 'cn-north-1')

    def _call(self, action, body):
        return self.http.post_json(
            BILLING_HOST, action, BILLING_VERSION, body,
            region=self.region, service=BILLING_SERVICE,
        )

    def _list_result(self, payload):
        result = payload.get('Result') or {}
        warning = None
        if isinstance(result, list):
            items = result
            total = len(items)
            limit = None
            offset = None
        elif isinstance(result, dict):
            warning = result.get('Warning')
            items = (
                result.get('List') or result.get('BillList') or
                result.get('BillDetailList') or result.get('Records') or []
            )
            total = result.get('Total')
            limit = result.get('Limit')
            offset = result.get('Offset')
        else:
            raise VolcengineAPIError('invalid_response', '账单接口返回结构无效')
        if not isinstance(items, list):
            raise VolcengineAPIError('invalid_response', '账单列表结构无效')
        metadata = payload.get('ResponseMetadata') or {}
        return {
            'items': [normalize_amounts(item) for item in items if isinstance(item, dict)],
            'total': int(total) if total is not None else -1,
            'limit': limit,
            'offset': offset,
            'warning': warning,
            'request_id': metadata.get('RequestId'),
        }

    def list_bill_overview_by_prod(self, bill_period, limit=300, offset=0,
                                   product=None, need_record_num=1,
                                   ignore_zero=1):
        body = {
            'BillPeriod': _validate_bill_period(bill_period),
            'Limit': _validate_limit(limit),
            'Offset': _validate_offset(offset),
            'NeedRecordNum': 1 if need_record_num else 0,
            'IgnoreZero': 1 if ignore_zero else 0,
        }
        product_values = _product_values(product)
        if product_values:
            body['Product'] = product_values
        payload = self._call('ListBillOverviewByProd', body)
        return self._list_result(payload)

    def list_bill(self, bill_period, limit=300, offset=0, product=None,
                  pay_status=None, need_record_num=1, ignore_zero=1):
        body = {
            'BillPeriod': _validate_bill_period(bill_period),
            'Limit': _validate_limit(limit),
            'Offset': _validate_offset(offset),
            'NeedRecordNum': 1 if need_record_num else 0,
            'IgnoreZero': 1 if ignore_zero else 0,
        }
        product_values = _product_values(product)
        if product_values:
            body['Product'] = product_values
        if pay_status:
            body['PayStatus'] = pay_status
        payload = self._call('ListBill', body)
        return self._list_result(payload)

    def list_bill_detail(self, bill_period, limit=300, offset=0,
                         product=None, expense_date=None, group_period=2,
                         need_record_num=1, ignore_zero=1):
        body = {
            'BillPeriod': _validate_bill_period(bill_period),
            'Limit': _validate_limit(limit),
            'Offset': _validate_offset(offset),
            'NeedRecordNum': 1 if need_record_num else 0,
            'IgnoreZero': 1 if ignore_zero else 0,
            'GroupPeriod': int(group_period if group_period is not None else 2),
        }
        product_values = _product_values(product)
        if product_values:
            body['Product'] = product_values
        if expense_date:
            try:
                datetime.strptime(str(expense_date), '%Y-%m-%d')
            except (TypeError, ValueError):
                raise VolcengineAPIError('invalid_param', 'ExpenseDate 格式应为 YYYY-MM-DD')
            body['ExpenseDate'] = str(expense_date)
        payload = self._call('ListBillDetail', body)
        return self._list_result(payload)

    def list_split_bill_detail(self, bill_period, limit=300, offset=0,
                               product=None, split_dimension=None,
                               group_period=2, expense_date=None,
                               need_record_num=1, ignore_zero=1):
        body = {
            'BillPeriod': _validate_bill_period(bill_period),
            'Limit': _validate_limit(limit),
            'Offset': _validate_offset(offset),
            'NeedRecordNum': 1 if need_record_num else 0,
            'IgnoreZero': 1 if ignore_zero else 0,
            'GroupPeriod': int(group_period if group_period is not None else 2),
        }
        product_values = _product_values(product)
        if product_values:
            body['Product'] = product_values
        dimension = _split_dimension(split_dimension)
        if dimension:
            body['SplitDimension'] = dimension
        if expense_date:
            try:
                datetime.strptime(str(expense_date), '%Y-%m-%d')
            except (TypeError, ValueError):
                raise VolcengineAPIError('invalid_param', 'ExpenseDate 格式应为 YYYY-MM-DD')
            body['ExpenseDate'] = str(expense_date)
        payload = self._call('ListSplitBillDetail', body)
        return self._list_result(payload)

    def query_balance_acct(self):
        payload = self._call('QueryBalanceAcct', {})
        result = payload.get('Result') or {}
        if not isinstance(result, dict):
            raise VolcengineAPIError('invalid_response', 'QueryBalanceAcct 返回结构无效')
        normalized = normalize_amounts(result)
        metadata = payload.get('ResponseMetadata') or {}
        normalized['_request_id'] = metadata.get('RequestId')
        return normalized
