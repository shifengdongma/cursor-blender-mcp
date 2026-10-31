# -*- coding: utf-8 -*-
"""Tests for official bill sync, currency/Decimal safety and attribution."""
from __future__ import absolute_import

import time
from types import SimpleNamespace

import pytest

from backend.volcengine.billing_sync_service import VolcengineBillingService
from backend.volcengine.client import VolcengineAPIError
from backend.volcengine.store import get_sync_status


def _cfg(split=None):
    return SimpleNamespace(
        VOLCENGINE_BILLING_ENABLED=True,
        VOLCENGINE_ACCESS_KEY_ID='AK',
        VOLCENGINE_SECRET_ACCESS_KEY='SK',
        VOLCENGINE_BILLING_REGION='cn-north-1',
        VOLCENGINE_BILLING_SYNC_INTERVAL_S=86400,
        VOLCENGINE_ARK_BILL_PRODUCT_FILTER='ark_bd,Doubao-Seedream',
        VOLCENGINE_ARK_BILL_SPLIT_DIMENSION=split or '',
        AUDIT_ENABLED=False,
        DATA_DIR='.',
    )


def _overview(product='Doubao-Seedream', amount='1.20', currency='CNY'):
    return {
        'BillPeriod': '2026-10', 'Product': product, 'ProductZh': product,
        'BillingMode': '2', 'BillCategoryParent': 'consume', 'Currency': currency,
        'OriginalBillAmount': '1.30', 'PreferentialBillAmount': '0.10',
        'DiscountBillAmount': amount, 'CouponAmount': '0.00',
        'PayableAmount': amount, 'PaidAmount': '0.00', 'UnpaidAmount': amount,
    }


def _detail(model='Doubao-Seedream-5.0-flash', product='Doubao-Seedream',
            amount='1.20', currency='CNY', unit='张'):
    return {
        'BillPeriod': '2026-10', 'BillDetailId': 'Detail-' + model,
        'Product': product, 'ProductZh': product, 'ConfigName': model,
        'ChargeItemCode': 'charge-' + model, 'InstanceNo': 'instance-1',
        'ExpenseDate': '2026-10-30', 'Count': '1', 'Unit': unit,
        'Currency': currency, 'OriginalBillAmount': '1.30',
        'PreferentialBillAmount': '0.10', 'DiscountBillAmount': amount,
        'PayableAmount': amount, 'PaidAmount': '0.00', 'UnpaidAmount': amount,
    }


class FakeBillingClient(object):
    def __init__(self, overview=None, bill=None, detail=None, split=None,
                 balance=None, split_error=None, overview_error=None):
        self.overview = overview if overview is not None else [_overview()]
        self.bill = bill if bill is not None else [
            {'BillPeriod': '2026-10', 'BillID': 'Bill1', 'PayStatus': 'Unsettle',
             'Currency': 'CNY', 'PayableAmount': '1.20'}
        ]
        self.detail = detail if detail is not None else [
            _detail(),
            _detail('Doubao-Seedance-2.0', 'ark_bd', '2.00', 'CNY', '千tokens'),
        ]
        self.split = split or []
        self.balance = balance or {
            'AccountID': 2100, 'AvailableBalance': '77.01', 'CashBalance': '80.00',
            'CreditLimit': '0.00', 'FreezeAmount': '2.99', 'ArrearsBalance': '0.00',
            'Currency': 'CNY',
        }
        self.split_error = split_error
        self.overview_error = overview_error
        self.calls = []

    def list_bill_overview_by_prod(self, period, limit=300, offset=0, product=None):
        self.calls.append(('overview', period, offset))
        if self.overview_error:
            raise self.overview_error
        rows = self.overview if offset == 0 else []
        return {'items': rows, 'total': len(self.overview), 'warning': None}

    def list_bill(self, period, limit=300, offset=0, product=None):
        self.calls.append(('bill', period, offset))
        rows = self.bill if offset == 0 else []
        return {'items': rows, 'total': len(self.bill), 'warning': None}

    def list_bill_detail(self, period, limit=300, offset=0, product=None,
                         group_period=2, expense_date=None):
        self.calls.append(('detail', period, offset))
        rows = self.detail if offset == 0 else []
        return {'items': rows, 'total': len(self.detail), 'warning': None}

    def list_split_bill_detail(self, period, limit=300, offset=0, product=None,
                               split_dimension=None, group_period=2,
                               expense_date=None):
        self.calls.append(('split', period, offset))
        if self.split_error:
            raise self.split_error
        rows = self.split if offset == 0 else []
        return {'items': rows, 'total': len(self.split), 'warning': None}

    def query_balance_acct(self):
        return dict(self.balance)


def test_sync_writes_levels_balance_and_is_idempotent(test_db):
    client = FakeBillingClient()
    service = VolcengineBillingService(_cfg(), db=test_db, client=client)
    result = service.sync_billing(bill_period='2026-10')
    assert result['status'] == 'success'
    assert result['claimed'] is True
    assert result['counts'] == {'overview': 1, 'bill': 1, 'detail': 2, 'split': 0}
    assert result['split_status'] == 'not_configured'
    assert result['balance']['status'] == 'success'
    levels = {
        row['record_level']: row['n'] for row in test_db.fetch_all(
            'SELECT record_level, COUNT(*) AS n FROM volcengine_bill_snapshots '
            'GROUP BY record_level'
        )
    }
    assert levels == {'overview': 1, 'bill': 1, 'detail': 2}
    balance = test_db.fetch_one('SELECT * FROM volcengine_balance_snapshots')
    assert balance['available_balance'] == '77.01'
    assert balance['currency'] == 'CNY'
    status = get_sync_status(test_db, 'ark_billing')
    assert status['status'] == 'success'
    last_success = status['last_success_at']
    assert last_success

    service.sync_billing(bill_period='2026-10')
    assert test_db.count('volcengine_bill_snapshots') == 4
    assert get_sync_status(test_db, 'ark_billing')['last_success_at'] >= last_success


def test_sync_failure_keeps_previous_snapshots(test_db):
    client = FakeBillingClient()
    service = VolcengineBillingService(_cfg(), db=test_db, client=client)
    service.sync_billing(bill_period='2026-10')
    before = get_sync_status(test_db, 'ark_billing')
    count = test_db.count('volcengine_bill_snapshots')
    client.overview_error = VolcengineAPIError('network', 'network down')
    with pytest.raises(VolcengineAPIError):
        service.sync_billing(bill_period='2026-10')
    after = get_sync_status(test_db, 'ark_billing')
    assert after['status'] == 'failed'
    assert after['error_category'] == 'network'
    assert after['last_success_at'] == before['last_success_at']
    assert test_db.count('volcengine_bill_snapshots') == count


def test_sync_lock_and_split_not_enabled(test_db):
    split_error = VolcengineAPIError(
        'invalid_param',
        'RequestInvalid [The current account has not enabled split bill capability. No data is available.]',
    )
    client = FakeBillingClient(split_error=split_error)
    service = VolcengineBillingService(_cfg(split='{"ark_bd":"apikey_id"}'), db=test_db, client=client)
    result = service.sync_billing(bill_period='2026-10', include_split=True)
    assert result['status'] == 'success'
    assert result['split_status'] == 'not_enabled'

    test_db.execute(
        "UPDATE volcengine_sync_status SET status='running', running_since=? "
        "WHERE sync_key='ark_billing'",
        (int(time.time()),),
    )
    locked = service.sync_billing(bill_period='2026-10')
    assert locked['claimed'] is False


def test_balance_failure_does_not_fail_bill_sync(test_db):
    class BalanceFailClient(FakeBillingClient):
        def query_balance_acct(self):
            raise VolcengineAPIError('no_permission', 'denied')

    service = VolcengineBillingService(_cfg(), db=test_db, client=BalanceFailClient())
    result = service.sync_billing(bill_period='2026-10')
    assert result['status'] == 'success'
    assert result['balance']['status'] == 'failed'
    assert result['balance']['category'] == 'no_permission'
    assert get_sync_status(test_db, 'ark_billing')['status'] == 'success'
    assert get_sync_status(test_db, 'ark_balance')['status'] == 'failed'


def test_summary_model_breakdown_trend_and_currency_separation(test_db):
    client = FakeBillingClient(overview=[
        _overview('Doubao-Seedream', '1.20', 'CNY'),
        _overview('ark_bd', '2.00', 'CNY'),
        _overview('ark_bd', '3.00', 'USD'),
    ])
    service = VolcengineBillingService(_cfg(), db=test_db, client=client)
    service.sync_billing(bill_period='2026-10')
    summary = service.summary('2026-10')
    assert summary['current_month']['has_data'] is True
    assert len(summary['current_month']['totals_by_currency']) == 2
    assert summary['currency'] is None
    assert summary['balance']['currency'] == 'CNY'

    models = service.model_breakdown('2026-10')
    labels = {item['model_label'] for item in models['items']}
    assert 'doubao-seedream-5-0-flash-260915' in labels
    assert 'doubao-seedance-2-0-260128' in labels
    assert all(item['unattributed'] is False for item in models['items'])

    trend = service.daily_trend('2026-10')
    assert trend['has_data'] is True
    assert trend['items'][0]['expense_date'] == '2026-10-30'

    reconciliation = service.reconciliation('2026-10')
    assert reconciliation['official']['has_data'] is True
    # Two currencies must not be collapsed into one payable total.
    assert reconciliation['official']['payable_amount'] is None
    assert len(reconciliation['official']['payable_by_currency']) == 2
    assert len(reconciliation['unallocated_by_currency']) == 2


def test_user_attribution_only_when_key_maps_to_one_user(test_db):
    now = int(time.time())
    test_db.insert('auth_users', {
        'id': 'user-attr', 'username': 'alice', 'nickname': '爱丽丝',
        'password_hash': 'x', 'role': 'user', 'status': 'active',
        'created_at': now, 'updated_at': now,
    })
    test_db.insert('ai_model_usage_records', {
        'id': 'u-1', 'dedupe_key': 'u-1', 'provider': 'ark_seedance',
        'model_id': 'doubao-seedance-2-0', 'api_key_resource_id': 'apikey-1',
        'user_id': 'user-attr', 'usage_source': 'official_api',
        'recorded_at': now, 'created_at': now, 'updated_at': now,
    })
    split = [{
        'BillPeriod': '2026-10', 'SplitBillDetailId': 'Split1',
        'SplitItemID': 'apikey-1', 'Product': 'ark_bd',
        'Currency': 'CNY', 'PayableAmount': '1.00',
    }]
    client = FakeBillingClient(split=split)
    service = VolcengineBillingService(_cfg(split='{"ark_bd":"apikey_id"}'), db=test_db, client=client)
    service.sync_billing(bill_period='2026-10', include_split=True)
    attribution = service.user_attribution('2026-10')
    assert attribution['has_data'] is True
    assert attribution['items'][0]['status'] == 'attributed'
    assert attribution['items'][0]['user_display'] == '爱丽丝（alice）'
    assert attribution['attributed_totals'][0]['payable_amount'] == '1.00'
    reconciliation = service.reconciliation('2026-10')
    assert reconciliation['attributed']['payable_amount'] == '1.00'
    assert reconciliation['unallocated_by_currency'][0]['payable_amount'] == '0.20'

    # A second user on the same key makes the amount shared/unallocated.
    test_db.insert('auth_users', {
        'id': 'user-attr-2', 'username': 'bob', 'nickname': 'Bob',
        'password_hash': 'x', 'role': 'user', 'status': 'active',
        'created_at': now, 'updated_at': now,
    })
    test_db.insert('ai_model_usage_records', {
        'id': 'u-2', 'dedupe_key': 'u-2', 'provider': 'ark_seedance',
        'model_id': 'doubao-seedance-2-0', 'api_key_resource_id': 'apikey-1',
        'user_id': 'user-attr-2', 'usage_source': 'official_api',
        'recorded_at': now, 'created_at': now, 'updated_at': now,
    })
    attribution = service.user_attribution('2026-10')
    assert attribution['items'][0]['status'] == 'shared'
    assert attribution['attributed_totals'] == []
    assert attribution['unallocated_totals'][0]['payable_amount'] == '1.00'
    reconciliation = service.reconciliation('2026-10')
    assert reconciliation['attributed']['payable_amount'] is None
    assert reconciliation['unallocated_by_currency'][0]['payable_amount'] == '1.20'


def test_details_pagination(test_db):
    client = FakeBillingClient()
    service = VolcengineBillingService(_cfg(), db=test_db, client=client)
    service.sync_billing(bill_period='2026-10')
    result = service.details('2026-10', level='detail', limit=1, offset=0)
    assert result['total'] == 2
    assert len(result['items']) == 1
    assert result['items'][0]['payable_amount']
    assert isinstance(result['items'][0]['raw_payload'], dict)
