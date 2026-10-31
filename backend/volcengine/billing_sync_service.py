# -*- coding: utf-8 -*-
"""Official Volcengine billing sync, balance and reconciliation."""
from __future__ import absolute_import

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ..database import get_database
from ..model_ids import ARK_MODEL_IDS
from .billing_client import (
    VolcengineBillingClient,
    decimal_text,
    normalize_amounts,
    parse_decimal,
)
from .client import VolcengineAPIError
from .store import (
    BALANCE_SYNC_KEY,
    BILLING_SYNC_KEY,
    claim_sync,
    finish_sync,
    get_sync_status,
    insert_balance_snapshot,
    latest_balance,
    now,
    upsert_bill_snapshot,
)

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))
OFFICIAL_SOURCE = 'volcengine_billing'
KNOWN_MODEL_IDS = sorted(set(ARK_MODEL_IDS.values()), key=len, reverse=True)


def _normalize_model_text(value):
    text = str(value or '').lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def _model_aliases():
    aliases = []
    for model_id in KNOWN_MODEL_IDS:
        normalized = _normalize_model_text(model_id)
        candidates = {normalized}
        # Official bill ConfigName often omits the date suffix, e.g.
        # "Doubao-Seedream-5.0-flash" vs "doubao-seedream-5-0-flash-260915".
        match = re.match(r'^(.*)-\d{6}$', normalized)
        if match:
            candidates.add(match.group(1))
        for alias in candidates:
            if alias:
                aliases.append((alias, model_id))
    return sorted(aliases, key=lambda item: len(item[0]), reverse=True)


MODEL_ALIASES = _model_aliases()


def _current_period():
    return datetime.now(BEIJING_TZ).strftime('%Y-%m')


def _previous_period(period=None):
    if period:
        parsed = datetime.strptime(period, '%Y-%m')
    else:
        parsed = datetime.now(BEIJING_TZ)
    first = parsed.replace(day=1)
    previous = first - timedelta(days=1)
    return previous.strftime('%Y-%m')


def _month_bounds(period):
    parsed = datetime.strptime(period, '%Y-%m')
    start = parsed.replace(day=1, tzinfo=BEIJING_TZ)
    if parsed.month == 12:
        following = parsed.replace(year=parsed.year + 1, month=1, day=1, tzinfo=BEIJING_TZ)
    else:
        following = parsed.replace(month=parsed.month + 1, day=1, tzinfo=BEIJING_TZ)
    return int(start.timestamp()), int(following.timestamp())


def _snapshot_key(*parts):
    raw = '|'.join(str(part or '') for part in parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _metadata(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _value(row, *names):
    for name in names:
        if isinstance(row, dict) and row.get(name) is not None:
            return row.get(name)
    return None


def _amount(row, *names):
    return decimal_text(_value(row, *names))


def _currency(row):
    return _value(row, 'Currency', 'CurrencySettlement') or 'CNY'


def _settlement_currency(row):
    return _value(row, 'CurrencySettlement', 'Currency') or _currency(row)


def _api_key_id(row):
    direct = _value(row, 'ApiKeyID', 'ApikeyID', 'APIKeyID', 'apikey_id')
    if direct:
        return str(direct)
    tag = _value(row, 'Tag')
    if tag:
        try:
            parsed = json.loads(tag) if isinstance(tag, str) else tag
            if isinstance(parsed, dict):
                for key in ('apikey_id', 'ApiKeyID', 'APIKeyID'):
                    values = parsed.get(key)
                    if isinstance(values, list) and values:
                        return str(values[0])
                    if values:
                        return str(values)
        except (TypeError, ValueError):
            pass
    for name in ('SplitItemID', 'ResourceID'):
        value = _value(row, name)
        if value and str(value) not in ('-', '0'):
            return str(value)
    return None


def _row_snapshot(row, period, level):
    expense_date = _value(row, 'ExpenseDate')
    if not expense_date:
        expense_time = _value(row, 'ExpenseTime')
        if expense_time and str(expense_time) != '-':
            expense_date = str(expense_time)[:10]
    bill_detail_id = _value(row, 'BillDetailId')
    split_bill_detail_id = _value(row, 'SplitBillDetailId')
    official_bill_id = _value(row, 'BillID')
    product = _value(row, 'Product')
    config_name = _value(row, 'ConfigName')
    charge_item = _value(row, 'ChargeItemCode')
    instance_no = _value(row, 'InstanceNo')
    currency = _currency(row)
    if level == 'overview':
        key = _snapshot_key(
            'overview', period, product, _value(row, 'BillingMode'),
            _value(row, 'BillCategoryParent'), currency,
            _value(row, 'PayerID'), _value(row, 'OwnerID'),
        )
    elif level == 'bill':
        key = _snapshot_key(
            'bill', period, official_bill_id, product,
            _value(row, 'BillingMode'), _value(row, 'BillCategoryParent'),
            currency, _value(row, 'PayStatus'),
        )
    elif level == 'split':
        key = _snapshot_key(
            'split', period, split_bill_detail_id, official_bill_id,
            bill_detail_id, product, config_name, charge_item,
            expense_date, currency, _value(row, 'SplitItemID'),
        )
    else:
        key = _snapshot_key(
            'detail', period, bill_detail_id, official_bill_id, product,
            config_name, charge_item, expense_date, currency, instance_no,
            _value(row, 'Count'), _value(row, 'OriginalBillAmount'),
        )
    return {
        'snapshot_key': key,
        'record_level': level,
        'provider_account_ref': _value(row, 'PayerID', 'OwnerID'),
        'bill_period': _value(row, 'BillPeriod') or period,
        'expense_date': expense_date,
        'group_period': 2 if level in ('detail', 'split') else 0,
        'product': product,
        'product_zh': _value(row, 'ProductZh'),
        'config_name': config_name,
        'charge_item_code': charge_item,
        'official_bill_id': official_bill_id,
        'bill_detail_id': bill_detail_id,
        'split_bill_detail_id': split_bill_detail_id,
        'pay_status': _value(row, 'PayStatus'),
        'bill_category': _value(row, 'BillCategory', 'BillCategoryParent'),
        'billing_mode': _value(row, 'BillingMode'),
        'currency': currency,
        'settlement_currency': _settlement_currency(row),
        'settlement_type': _value(row, 'SettlementType'),
        'usage_amount': decimal_text(
            _value(row, 'Count', 'SplitItemAmount', 'UsageAmount')
        ),
        'usage_unit': _value(row, 'Unit'),
        'original_amount': _amount(row, 'OriginalBillAmount'),
        'preferential_amount': _amount(row, 'PreferentialBillAmount'),
        'discount_amount': _amount(row, 'DiscountBillAmount'),
        'coupon_amount': _amount(row, 'CouponAmount', 'CouponDeductionAmount'),
        'payable_amount': _amount(row, 'PayableAmount'),
        'paid_amount': _amount(row, 'PaidAmount'),
        'unpaid_amount': _amount(row, 'UnpaidAmount'),
        'settlement_amount': _amount(
            row, 'SettlePayableAmount', 'SettlePosttaxAmount', 'SettlePretaxAmount'
        ),
        'resource_id': _value(row, 'ResourceID'),
        'instance_no': instance_no,
        'split_item_id': _value(row, 'SplitItemID'),
        'split_item_name': _value(row, 'SplitItemName'),
        'split_item_ratio': decimal_text(_value(row, 'SplitItemRatio')),
        'api_key_resource_id': _api_key_id(row),
        'raw_payload': json.dumps(row, ensure_ascii=False),
        'synced_at': now(),
        'updated_at': now(),
    }


def _audit(cfg, actor, result, details):
    if not getattr(cfg, 'AUDIT_ENABLED', True):
        return
    try:
        from ..audit_service import get_audit_service
        get_audit_service(getattr(cfg, 'DATA_DIR', './data')).record_audit(
            user_id=(actor or {}).get('id'),
            tenant_id=(actor or {}).get('tenant_id'),
            project_id=None,
            action='admin_ark_sync' if actor else 'volcengine_sync',
            target_type='volcengine_sync',
            target_id=BILLING_SYNC_KEY,
            result=result,
            metadata=details,
        )
    except Exception:
        pass


def _totals_by_currency(rows, fields):
    groups = {}
    for row in rows:
        currency = row.get('currency') or 'CNY'
        group = groups.setdefault(currency, {
            field: Decimal('0') for field in fields
        })
        for field in fields:
            parsed = parse_decimal(row.get(field))
            if parsed is not None:
                group[field] += parsed
    result = []
    for currency, values in sorted(groups.items()):
        item = {'currency': currency}
        for field, value in values.items():
            item[field] = decimal_text(value)
        result.append(item)
    return result


class VolcengineBillingService(object):
    def __init__(self, cfg, db=None, client=None):
        self.cfg = cfg
        self.db = db or get_database()
        self.client = client or VolcengineBillingClient(cfg)

    def billing_enabled(self):
        return bool(getattr(self.cfg, 'VOLCENGINE_BILLING_ENABLED', False))

    def credentials_configured(self):
        return bool(
            getattr(self.cfg, 'VOLCENGINE_ACCESS_KEY_ID', '')
            and getattr(self.cfg, 'VOLCENGINE_SECRET_ACCESS_KEY', '')
        )

    def product_filter(self):
        return (getattr(self.cfg, 'VOLCENGINE_ARK_BILL_PRODUCT_FILTER', '') or '').strip()

    def split_dimension(self):
        return (getattr(self.cfg, 'VOLCENGINE_ARK_BILL_SPLIT_DIMENSION', '') or '').strip()

    def status(self):
        billing = get_sync_status(self.db, BILLING_SYNC_KEY) or {}
        balance = get_sync_status(self.db, BALANCE_SYNC_KEY) or {}
        interval = int(getattr(self.cfg, 'VOLCENGINE_BILLING_SYNC_INTERVAL_S', 86400) or 86400)
        last = billing.get('last_success_at')
        stale = True
        if last:
            stale = (now() - int(last)) > max(interval * 2, 3600)
        billing_meta = _metadata(billing.get('metadata'))
        split_status = billing_meta.get('split_status') or (
            'not_configured' if not self.split_dimension() else 'not_synced'
        )
        return {
            'has_credentials': self.credentials_configured(),
            'billing_enabled': self.billing_enabled(),
            'balance_enabled': self.billing_enabled(),
            'billing_region': getattr(self.cfg, 'VOLCENGINE_BILLING_REGION', 'cn-north-1'),
            'product_filter': self.product_filter() or None,
            'product_filter_applied': bool(self.product_filter()),
            'split_dimension_configured': bool(self.split_dimension()),
            'split_status': split_status,
            'sync': {'ark_billing': billing, 'ark_balance': balance},
            'last_synced_at': last,
            'last_balance_synced_at': balance.get('last_success_at'),
            'is_stale': stale,
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账单（费用中心）',
            'is_estimated': False,
        }

    # ── sync ──
    def sync_billing(self, bill_period=None, actor=None, include_split=None):
        if not self.billing_enabled():
            finish_sync(
                self.db, BILLING_SYNC_KEY, 'disabled', error_category='disabled',
                error_code='billing_disabled', error_message='VOLCENGINE_BILLING_ENABLED=false',
            )
            raise VolcengineAPIError('disabled', '火山引擎官方账单未启用')
        if not self.credentials_configured():
            finish_sync(
                self.db, BILLING_SYNC_KEY, 'unconfigured', error_category='unconfigured',
                error_code='missing_credentials', error_message='未配置管理 AK/SK',
            )
            raise VolcengineAPIError('unconfigured', '未配置火山引擎管理 AK/SK')
        stale_seconds = max(3600, int(getattr(self.cfg, 'VOLCENGINE_BILLING_SYNC_INTERVAL_S', 86400) or 86400))
        if not claim_sync(self.db, BILLING_SYNC_KEY, stale_seconds=stale_seconds):
            return {'status': 'running', 'claimed': False}
        if bill_period:
            periods = [str(bill_period)]
        else:
            current = _current_period()
            periods = [_previous_period(current), current]
        include_split = (
            bool(self.split_dimension()) if include_split is None else bool(include_split)
        )
        if include_split and not self.split_dimension():
            include_split = False
        totals = {'overview': 0, 'bill': 0, 'detail': 0, 'split': 0}
        truncated = []
        split_status = 'not_configured' if not include_split else 'pending'
        try:
            for period in periods:
                counts = self._sync_period(period, include_split)
                for key in totals:
                    totals[key] += counts.get(key, 0)
                truncated.extend(counts.get('truncated') or [])
                if counts.get('split_status'):
                    split_status = counts['split_status']
            balance_result = {'status': 'skipped'}
            try:
                balance_result = self.sync_balance(actor=actor)
            except VolcengineAPIError as exc:
                balance_result = {'status': 'failed', 'category': exc.category}
            metadata = {
                'periods': periods,
                'counts': totals,
                'truncated': truncated,
                'split_status': split_status,
                'balance': balance_result,
                'product_filter': self.product_filter() or None,
                'product_filter_applied': bool(self.product_filter()),
            }
            finish_sync(
                self.db, BILLING_SYNC_KEY, 'success',
                records_processed=sum(totals.values()),
                last_period=','.join(periods),
                metadata=metadata, success=True,
            )
            _audit(self.cfg, actor, 'success', {
                'scope': 'billing', 'periods': periods, 'counts': totals,
                'truncated': truncated, 'split_status': split_status,
            })
            return {
                'status': 'success', 'claimed': True, 'periods': periods,
                'counts': totals, 'truncated': truncated,
                'split_status': split_status, 'balance': balance_result,
                'product_filter': self.product_filter() or None,
            }
        except Exception as exc:
            category = getattr(exc, 'category', 'sync_error')
            finish_sync(
                self.db, BILLING_SYNC_KEY, 'failed', error_category=category,
                error_code=getattr(exc, 'code', None),
                error_message=str(exc)[:500], last_period=','.join(periods),
            )
            _audit(self.cfg, actor, 'failed', {
                'scope': 'billing', 'periods': periods,
                'error_category': category,
                'error_code': getattr(exc, 'code', None),
            })
            raise

    def _sync_period(self, period, include_split):
        counts = {'overview': 0, 'bill': 0, 'detail': 0, 'split': 0, 'truncated': []}
        product = self.product_filter() or None
        overview = self._sync_pages(
            lambda offset: self.client.list_bill_overview_by_prod(
                period, limit=300, offset=offset, product=product
            ),
            'overview', period,
        )
        counts['overview'] = overview['count']
        if overview['truncated']:
            counts['truncated'].append('{0}:overview'.format(period))
        bill = self._sync_pages(
            lambda offset: self.client.list_bill(
                period, limit=300, offset=offset, product=product
            ),
            'bill', period,
        )
        counts['bill'] = bill['count']
        if bill['truncated']:
            counts['truncated'].append('{0}:bill'.format(period))
        detail = self._sync_pages(
            lambda offset: self.client.list_bill_detail(
                period, limit=300, offset=offset, product=product,
                group_period=2,
            ),
            'detail', period,
        )
        counts['detail'] = detail['count']
        if detail['truncated']:
            counts['truncated'].append('{0}:detail'.format(period))
        if include_split:
            try:
                split = self._sync_pages(
                    lambda offset: self.client.list_split_bill_detail(
                        period, limit=300, offset=offset, product=product,
                        split_dimension=self.split_dimension(), group_period=2,
                    ),
                    'split', period,
                )
                counts['split'] = split['count']
                counts['split_status'] = 'success'
                if split['truncated']:
                    counts['truncated'].append('{0}:split'.format(period))
            except VolcengineAPIError as exc:
                # Split attribution is optional; the account bill sync itself
                # remains valid.  Surface the category to the UI.
                message = str(exc).lower()
                if 'has not enabled split bill' in message or 'no data is available' in message:
                    counts['split_status'] = 'not_enabled'
                else:
                    counts['split_status'] = exc.category
                logger.info('Split bill sync unavailable: %s/%s', exc.category, exc.code)
        return counts

    def _sync_pages(self, fetch_page, level, period, max_pages=10):
        offset = 0
        count = 0
        pages = 0
        total = -1
        while pages < max_pages:
            page = fetch_page(offset)
            items = page.get('items') or []
            for row in items:
                upsert_bill_snapshot(self.db, _row_snapshot(row, period, level))
            count += len(items)
            pages += 1
            try:
                total = int(page.get('total'))
            except (TypeError, ValueError):
                total = -1
            if not items or len(items) < 300:
                break
            offset += len(items)
            if total >= 0 and offset >= total:
                break
        truncated = total >= 0 and count < total
        return {'count': count, 'truncated': truncated, 'total': total}

    def sync_balance(self, actor=None):
        if not self.billing_enabled():
            finish_sync(
                self.db, BALANCE_SYNC_KEY, 'disabled', error_category='disabled',
                error_code='billing_disabled', error_message='VOLCENGINE_BILLING_ENABLED=false',
            )
            raise VolcengineAPIError('disabled', '火山引擎官方账单未启用')
        if not self.credentials_configured():
            finish_sync(
                self.db, BALANCE_SYNC_KEY, 'unconfigured', error_category='unconfigured',
                error_code='missing_credentials', error_message='未配置管理 AK/SK',
            )
            raise VolcengineAPIError('unconfigured', '未配置火山引擎管理 AK/SK')
        if not claim_sync(self.db, BALANCE_SYNC_KEY, stale_seconds=1800):
            return {'status': 'running', 'claimed': False}
        try:
            result = self.client.query_balance_acct()
            snapshot = {
                'provider_account_ref': str(result.get('AccountID') or 'unknown'),
                'account_id': str(result.get('AccountID') or '') or None,
                'balance': decimal_text(result.get('AvailableBalance')),
                'available_balance': decimal_text(result.get('AvailableBalance')),
                'cash_balance': decimal_text(result.get('CashBalance')),
                'credit_limit': decimal_text(result.get('CreditLimit')),
                'freeze_amount': decimal_text(result.get('FreezeAmount')),
                'arrears_balance': decimal_text(result.get('ArrearsBalance')),
                'currency': result.get('Currency') or 'CNY',
                'raw_payload': json.dumps(normalize_amounts(result), ensure_ascii=False),
                'synced_at': now(),
                'updated_at': now(),
            }
            insert_balance_snapshot(self.db, snapshot)
            finish_sync(
                self.db, BALANCE_SYNC_KEY, 'success', records_processed=1,
                metadata={'account_id': snapshot['account_id']}, success=True,
            )
            return {'status': 'success', 'claimed': True, 'balance': snapshot['available_balance']}
        except Exception as exc:
            category = getattr(exc, 'category', 'sync_error')
            finish_sync(
                self.db, BALANCE_SYNC_KEY, 'failed', error_category=category,
                error_code=getattr(exc, 'code', None),
                error_message=str(exc)[:500],
            )
            raise

    # ── read-only views ──
    def _billing_rows(self, period, levels=None):
        if levels:
            placeholders = ','.join('?' for _ in levels)
            return self.db.fetch_all(
                'SELECT * FROM volcengine_bill_snapshots WHERE bill_period = ? '
                'AND record_level IN ({0}) ORDER BY expense_date ASC, id ASC'.format(
                    placeholders
                ),
                tuple([period] + list(levels)),
            )
        return self.db.fetch_all(
            'SELECT * FROM volcengine_bill_snapshots WHERE bill_period = ? '
            'ORDER BY expense_date ASC, id ASC',
            (period,),
        )

    def _period_totals(self, period):
        rows = self._billing_rows(period, ('overview',))
        basis = 'overview'
        if not rows:
            rows = self._billing_rows(period, ('bill',))
            basis = 'bill'
        if not rows:
            rows = self._billing_rows(period, ('detail', 'split'))
            basis = 'detail'
        fields = (
            'original_amount', 'preferential_amount', 'discount_amount',
            'coupon_amount', 'payable_amount', 'paid_amount', 'unpaid_amount',
            'settlement_amount',
        )
        return {
            'has_data': bool(rows),
            'basis': basis,
            'row_count': len(rows),
            'totals_by_currency': _totals_by_currency(rows, fields),
        }

    def summary(self, bill_period=None):
        current = bill_period or _current_period()
        previous = _previous_period(current)
        current_totals = self._period_totals(current)
        previous_totals = self._period_totals(previous)
        bill_status_rows = self._billing_rows(previous, ('bill',))
        pay_status_counts = {}
        for row in bill_status_rows:
            status = row.get('pay_status') or '未标注'
            pay_status_counts[status] = pay_status_counts.get(status, 0) + 1
        settled = bool(
            pay_status_counts and
            set(pay_status_counts.keys()) <= {'CompletedSettle', '已结清'}
        )
        balance = latest_balance(self.db)
        billing_status = get_sync_status(self.db, BILLING_SYNC_KEY) or {}
        balance_status = get_sync_status(self.db, BALANCE_SYNC_KEY) or {}
        currencies = sorted(set(
            [item.get('currency') for item in current_totals['totals_by_currency']] +
            [item.get('currency') for item in previous_totals['totals_by_currency']]
        ))
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账单（费用中心）',
            'is_estimated': False,
            'last_synced_at': billing_status.get('last_success_at'),
            'billing_period': current,
            'currency': currencies[0] if len(currencies) == 1 else None,
            'current_month': {
                'period': current,
                'partial': True,
                'has_data': current_totals['has_data'],
                'basis': current_totals['basis'],
                'row_count': current_totals['row_count'],
                'totals_by_currency': current_totals['totals_by_currency'],
            },
            'previous_month': {
                'period': previous,
                'has_data': previous_totals['has_data'],
                'basis': previous_totals['basis'],
                'row_count': previous_totals['row_count'],
                'totals_by_currency': previous_totals['totals_by_currency'],
                'pay_status_counts': pay_status_counts,
                'settled': settled,
                'settled_label': '已结清' if settled else '未完成结算或未出账',
            },
            'balance': {
                'has_data': bool(balance),
                'account_id': balance.get('account_id') if balance else None,
                'available_balance': balance.get('available_balance') if balance else None,
                'cash_balance': balance.get('cash_balance') if balance else None,
                'credit_limit': balance.get('credit_limit') if balance else None,
                'freeze_amount': balance.get('freeze_amount') if balance else None,
                'arrears_balance': balance.get('arrears_balance') if balance else None,
                'currency': balance.get('currency') if balance else 'CNY',
                'synced_at': balance.get('synced_at') if balance else None,
                'status': balance_status.get('status'),
                'source_label': '火山引擎官方账户余额',
            },
            'balance_status': balance_status,
            'billing_status': billing_status,
            'product_filter': self.product_filter() or None,
            'product_filter_applied': bool(self.product_filter()),
            'split_dimension_configured': bool(self.split_dimension()),
            'split_status': (
                _metadata(billing_status.get('metadata')).get('split_status') or
                ('not_configured' if not self.split_dimension() else 'not_synced')
            ),
            'is_stale': self.status().get('is_stale'),
            'notes': [
                '当月账单为部分数据，未出账/未结算金额不代表最终账单。',
                '上月完整账单通常在次月 2 日 12:00 后生成；在此之前可能不完整。',
                '不同币种、原价/优惠/应付/已付/结算金额分别展示，不跨口径相加。',
            ],
        }

    def model_breakdown(self, bill_period=None):
        period = bill_period or _current_period()
        rows = self._billing_rows(period, ('detail', 'split'))
        groups = {}
        for row in rows:
            text = _normalize_model_text(' '.join(str(row.get(field) or '') for field in (
                'config_name', 'product_zh', 'product', 'charge_item_code',
                'instance_no', 'resource_id', 'raw_payload',
            )))
            matched = None
            for alias, model_id in MODEL_ALIASES:
                if alias and alias in text:
                    matched = model_id
                    break
            model_label = matched or '未归属模型'
            config = row.get('config_name') or row.get('split_item_name') or row.get('product_zh')
            key = (model_label, config or '', row.get('currency') or 'CNY',
                   row.get('charge_item_code') or '', row.get('usage_unit') or '')
            item = groups.setdefault(key, {
                'model_id': matched,
                'model_label': model_label,
                'usage_type': self._usage_type(matched),
                'config_name': config,
                'charge_item_code': row.get('charge_item_code'),
                'usage_unit': row.get('usage_unit'),
                'currency': row.get('currency') or 'CNY',
                'row_count': 0,
                'usage_amount': Decimal('0'),
                'original_amount': Decimal('0'),
                'payable_amount': Decimal('0'),
                'settlement_amount': Decimal('0'),
                'unattributed': matched is None,
            })
            item['row_count'] += 1
            item['usage_amount'] += parse_decimal(row.get('usage_amount')) or Decimal('0')
            item['original_amount'] += parse_decimal(row.get('original_amount')) or Decimal('0')
            item['payable_amount'] += parse_decimal(row.get('payable_amount')) or Decimal('0')
            item['settlement_amount'] += parse_decimal(row.get('settlement_amount')) or Decimal('0')
        items = []
        for item in groups.values():
            item['usage_amount'] = decimal_text(item['usage_amount'])
            item['original_amount'] = decimal_text(item['original_amount'])
            item['payable_amount'] = decimal_text(item['payable_amount'])
            item['settlement_amount'] = decimal_text(item['settlement_amount'])
            items.append(item)
        items.sort(
            key=lambda item: parse_decimal(item.get('payable_amount')) or Decimal('0'),
            reverse=True,
        )
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账单（按官方配置/计费项）',
            'is_estimated': False,
            'last_synced_at': (get_sync_status(self.db, BILLING_SYNC_KEY) or {}).get('last_success_at'),
            'billing_period': period,
            'currency': None,
            'has_data': bool(items),
            'items': items,
            'product_filter': self.product_filter() or None,
            'notes': [
                '只有官方配置/计费项能匹配已知模型时才归入模型；否则标记未归属模型。',
                '官方配置名称可能因账号/计费项不同而变化，不对未匹配项猜测归属。',
                '金额按币种分组；不支持跨币种合计。',
            ],
        }

    @staticmethod
    def _usage_type(model_id):
        if not model_id:
            return None
        if 'seedream' in model_id:
            return '图片生成'
        if 'seedance' in model_id:
            return '视频生成'
        return '文本生成'

    def daily_trend(self, bill_period=None):
        period = bill_period or _current_period()
        rows = self._billing_rows(period, ('detail', 'split'))
        groups = {}
        for row in rows:
            date = row.get('expense_date') or period
            currency = row.get('currency') or 'CNY'
            key = (date, currency)
            item = groups.setdefault(key, {
                'expense_date': date,
                'currency': currency,
                'payable_amount': Decimal('0'),
                'original_amount': Decimal('0'),
                'usage_amount': Decimal('0'),
                'row_count': 0,
            })
            item['row_count'] += 1
            item['payable_amount'] += parse_decimal(row.get('payable_amount')) or Decimal('0')
            item['original_amount'] += parse_decimal(row.get('original_amount')) or Decimal('0')
            item['usage_amount'] += parse_decimal(row.get('usage_amount')) or Decimal('0')
        items = []
        for key in sorted(groups.keys()):
            item = groups[key]
            item['payable_amount'] = decimal_text(item['payable_amount'])
            item['original_amount'] = decimal_text(item['original_amount'])
            item['usage_amount'] = decimal_text(item['usage_amount'])
            items.append(item)
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账单（ExpenseDate）',
            'is_estimated': False,
            'last_synced_at': (get_sync_status(self.db, BILLING_SYNC_KEY) or {}).get('last_success_at'),
            'billing_period': period,
            'currency': None,
            'has_data': bool(items),
            'items': items,
            'notes': ['按官方 ExpenseDate 与币种汇总，不跨币种相加。'],
        }

    def user_attribution(self, bill_period=None):
        period = bill_period or _current_period()
        rows = self._billing_rows(period, ('split',))
        groups = {}
        for row in rows:
            key_id = row.get('api_key_resource_id')
            currency = row.get('currency') or 'CNY'
            key = (key_id or '', currency)
            item = groups.setdefault(key, {
                'api_key_resource_id': key_id,
                'currency': currency,
                'payable_amount': Decimal('0'),
                'row_count': 0,
            })
            item['row_count'] += 1
            item['payable_amount'] += parse_decimal(row.get('payable_amount')) or Decimal('0')
        items = []
        attributed = {}
        unallocated = {}
        for (key_id, currency), item in groups.items():
            users = []
            if key_id:
                user_rows = self.db.fetch_all(
                    "SELECT DISTINCT user_id FROM ai_model_usage_records "
                    "WHERE api_key_resource_id = ? AND user_id IS NOT NULL",
                    (key_id,),
                )
                users = [row.get('user_id') for row in user_rows if row.get('user_id')]
            user_display = None
            status = 'unallocated'
            if len(users) == 1:
                status = 'attributed'
                user = self.db.fetch_one(
                    'SELECT id, username, nickname FROM auth_users WHERE id = ?',
                    (users[0],),
                )
                if user:
                    username = user.get('username') or ''
                    nickname = user.get('nickname') or ''
                    user_display = nickname + (
                        '（' + username + '）' if nickname and nickname != username else ''
                    )
                    user_display = user_display or username
                else:
                    user_display = '已删除用户'
            elif len(users) > 1:
                status = 'shared'
            item['status'] = status
            item['user_id'] = users[0] if len(users) == 1 else None
            item['user_display'] = user_display
            item['shared_user_count'] = len(users)
            item['payable_amount'] = decimal_text(item['payable_amount'])
            items.append(item)
            amount = parse_decimal(item['payable_amount']) or Decimal('0')
            target = attributed if status == 'attributed' else unallocated
            target[currency] = (target.get(currency) or Decimal('0')) + amount
        items.sort(
            key=lambda item: parse_decimal(item.get('payable_amount')) or Decimal('0'),
            reverse=True,
        )
        billing_status = get_sync_status(self.db, BILLING_SYNC_KEY) or {}
        split_status = _metadata(billing_status.get('metadata')).get('split_status')
        notes = [
            '只有官方分账维度成功返回且 API Key 资源 ID 能唯一映射到 AIGV 用户时才归属。',
            '共享 Key 或无法映射的官方金额保持未分摊，不按任务次数平均。',
            '未配置分账维度时，官方费用全部保持未归属。',
        ]
        if split_status == 'not_enabled':
            notes.insert(0, '当前火山引擎账号未开通分账账单能力，官方费用保持未归属。')
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方分账账单（按 API Key 资源 ID）',
            'is_estimated': False,
            'last_synced_at': billing_status.get('last_success_at'),
            'billing_period': period,
            'currency': None,
            'has_data': bool(items),
            'split_status': split_status,
            'items': items,
            'attributed_totals': [
                {'currency': currency, 'payable_amount': decimal_text(value)}
                for currency, value in sorted(attributed.items())
            ],
            'unallocated_totals': [
                {'currency': currency, 'payable_amount': decimal_text(value)}
                for currency, value in sorted(unallocated.items())
            ],
            'notes': notes,
        }

    def reconciliation(self, bill_period=None):
        period = bill_period or _current_period()
        totals = self._period_totals(period)
        attribution = self.user_attribution(period)
        official_by_currency = [
            {
                'currency': item.get('currency'),
                'payable_amount': item.get('payable_amount'),
            }
            for item in totals.get('totals_by_currency', [])
        ]
        attributed_by_currency = attribution.get('attributed_totals') or []
        official_map = {}
        for item in official_by_currency:
            official_map[item.get('currency') or 'CNY'] = (
                parse_decimal(item.get('payable_amount')) or Decimal('0')
            )
        attributed_map = {}
        for item in attributed_by_currency:
            attributed_map[item.get('currency') or 'CNY'] = (
                parse_decimal(item.get('payable_amount')) or Decimal('0')
            )
        unallocated_map = {}
        negative_attribution = False
        for currency in set(official_map.keys()) | set(attributed_map.keys()):
            value = official_map.get(currency, Decimal('0')) - attributed_map.get(currency, Decimal('0'))
            if value < 0:
                negative_attribution = True
                value = Decimal('0')
            unallocated_map[currency] = value
        unallocated_by_currency = [
            {'currency': currency, 'payable_amount': decimal_text(value)}
            for currency, value in sorted(unallocated_map.items())
        ]
        notes = [
            '官方金额与本地任务次数不是同一口径；本页不将任务次数换算成金额。',
            '差异可能来自出账延迟、免费额度、优惠券/折扣、账号内其他应用、共享 Key、计费规则差异、失败/取消请求收费、无法归属服务。',
            '未配置分账或无法唯一映射的官方金额保持未归属，不强行对齐。',
            '当月数据为部分数据；上月账单在次月 2 日 12:00 后才可能完整。',
        ]
        if negative_attribution:
            notes.append('可归属金额暂时大于已同步官方金额，可能因分账与账单更新时点不同，已按 0 显示未归属金额。')
        start, end = _month_bounds(period)
        local_tasks = self.db.fetch_one(
            "SELECT COUNT(*) AS task_count FROM generation_tasks "
            "WHERE created_at >= ? AND created_at < ? "
            "AND provider IN ('ark_seedream','ark_seedance')",
            (start, end),
        ) or {}
        local_usage = self.db.fetch_one(
            "SELECT COUNT(DISTINCT task_id) AS task_count, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM ai_model_usage_records WHERE recorded_at >= ? AND recorded_at < ? "
            "AND provider IN ('ark_seedream','ark_seedance')",
            (start, end),
        ) or {}
        currencies = totals.get('totals_by_currency') or []
        currency = currencies[0].get('currency') if len(currencies) == 1 else None
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '官方账单与 AIGV 本地记录对账',
            'is_estimated': False,
            'last_synced_at': (get_sync_status(self.db, BILLING_SYNC_KEY) or {}).get('last_success_at'),
            'billing_period': period,
            'currency': currency,
            'official': {
                'has_data': totals.get('has_data'),
                'basis': totals.get('basis'),
                'totals_by_currency': totals.get('totals_by_currency'),
                'payable_by_currency': official_by_currency,
                # A single convenience value is only provided when the
                # official rows use exactly one currency.
                'payable_amount': (
                    official_by_currency[0]['payable_amount']
                    if len(official_by_currency) == 1 else None
                ),
            },
            'attributed': {
                'has_data': attribution.get('has_data'),
                'attributed_totals': attribution.get('attributed_totals'),
                'unallocated_totals': attribution.get('unallocated_totals'),
                'attributed_by_currency': attributed_by_currency,
                'payable_amount': (
                    attributed_by_currency[0]['payable_amount']
                    if len(attributed_by_currency) == 1 else None
                ),
            },
            'unallocated_by_currency': unallocated_by_currency,
            'local': {
                'ark_task_count': int(local_tasks.get('task_count') or 0),
                'usage_task_count': int(local_usage.get('task_count') or 0),
                'input_tokens': int(local_usage.get('input_tokens') or 0),
                'output_tokens': int(local_usage.get('output_tokens') or 0),
                'total_tokens': int(local_usage.get('total_tokens') or 0),
                'image_count': int(local_usage.get('image_count') or 0),
            },
            'notes': notes,
        }

    def details(self, bill_period=None, level='detail', limit=50, offset=0):
        period = bill_period or _current_period()
        level = level if level in ('overview', 'bill', 'detail', 'split') else 'detail'
        limit = max(1, min(300, int(limit or 50)))
        offset = max(0, int(offset or 0))
        where = 'bill_period = ? AND record_level = ?'
        params = (period, level)
        rows = self.db.fetch_all(
            'SELECT * FROM volcengine_bill_snapshots WHERE {0} '
            'ORDER BY expense_date DESC, id DESC LIMIT ? OFFSET ?'.format(where),
            params + (limit, offset),
        )
        total = self.db.count('volcengine_bill_snapshots', where, params)
        items = []
        for row in rows:
            item = dict(row)
            try:
                item['raw_payload'] = json.loads(item.get('raw_payload') or '{}')
            except (TypeError, ValueError):
                pass
            items.append(item)
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账单明细',
            'is_estimated': False,
            'last_synced_at': (get_sync_status(self.db, BILLING_SYNC_KEY) or {}).get('last_success_at'),
            'billing_period': period,
            'currency': None,
            'level': level,
            'items': items,
            'total': total,
            'limit': limit,
            'offset': offset,
        }

    def balance(self):
        balance = latest_balance(self.db)
        status = get_sync_status(self.db, BALANCE_SYNC_KEY) or {}
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方账户余额',
            'is_estimated': False,
            'last_synced_at': status.get('last_success_at'),
            'billing_period': None,
            'currency': balance.get('currency') if balance else 'CNY',
            'has_data': bool(balance),
            'account_id': balance.get('account_id') if balance else None,
            'available_balance': balance.get('available_balance') if balance else None,
            'cash_balance': balance.get('cash_balance') if balance else None,
            'credit_limit': balance.get('credit_limit') if balance else None,
            'freeze_amount': balance.get('freeze_amount') if balance else None,
            'arrears_balance': balance.get('arrears_balance') if balance else None,
            'synced_at': balance.get('synced_at') if balance else None,
            'sync_status': status,
        }
