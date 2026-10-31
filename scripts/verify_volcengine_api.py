#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only smoke test for Volcengine Ark usage and Billing Center APIs.

Prints only status categories, row counts, field names and product codes.  It
never prints AK/SK, Authorization headers, full payloads or amount values.
"""
from __future__ import absolute_import

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import Config
from backend.volcengine.billing_client import VolcengineBillingClient
from backend.volcengine.client import VolcengineAPIError
from backend.volcengine.usage_client import VolcengineUsageClient


def _field_names(rows):
    if not rows:
        return []
    return sorted(rows[0].keys())


def _report(name, fn):
    try:
        result = fn()
        if isinstance(result, dict) and 'items' in result:
            print('{0}: ok items={1} total={2}'.format(
                name, len(result.get('items') or []), result.get('total')
            ))
            products = sorted(set(
                str(item.get('Product'))
                for item in (result.get('items') or [])
                if item.get('Product')
            ))
            if products:
                print('{0}: products={1}'.format(name, products[:30]))
            print('{0}: fields={1}'.format(name, _field_names(result.get('items') or [])))
        elif isinstance(result, dict) and 'rows' in result:
            print('{0}: ok rows={1} fields={2}'.format(
                name, len(result.get('rows') or []),
                [item.get('Name') for item in (result.get('fields') or [])],
            ))
        elif isinstance(result, dict):
            print('{0}: ok fields={1}'.format(name, sorted(result.keys())))
        elif isinstance(result, list):
            print('{0}: ok records={1}'.format(name, len(result)))
        else:
            print('{0}: ok'.format(name))
        return True
    except VolcengineAPIError as exc:
        print('{0}: error category={1} code={2} message={3}'.format(
            name, exc.category, exc.code, str(exc)[:240]
        ))
        return False
    except Exception as exc:
        print('{0}: unexpected {1}: {2}'.format(name, type(exc).__name__, str(exc)[:240]))
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only Volcengine API verification')
    parser.add_argument('--usage-days', type=int, default=2)
    parser.add_argument('--bill-period', default=None, help='YYYY-MM')
    parser.add_argument('--task-id', default=None)
    parser.add_argument('--request-id', default=None)
    parser.add_argument('--query-hour', default=None)
    parser.add_argument('--split', action='store_true')
    args = parser.parse_args(argv)

    cfg = Config()
    if not cfg.has_volcengine_management_credentials():
        print('management_credentials: missing')
        return 2
    print('management_credentials: configured')
    ok = True
    usage = VolcengineUsageClient(cfg)
    from datetime import datetime, timedelta, timezone
    beijing = timezone(timedelta(hours=8))
    end = datetime.now(beijing).date()
    start = end - timedelta(days=max(1, args.usage_days) - 1)
    ok = _report(
        'GetInferenceUsage',
        lambda: usage.get_inference_usage(
            start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'),
            filters=usage.dimension_filters(),
        ),
    ) and ok
    if args.task_id:
        ok = _report(
            'GetInferenceTaskUsage',
            lambda: usage.get_inference_task_usage(args.task_id),
        ) and ok
    if args.request_id and args.query_hour:
        ok = _report(
            'GetInferenceRequestUsage',
            lambda: usage.get_inference_request_usage(
                args.request_id, args.query_hour
            ),
        ) and ok
    if args.bill_period:
        billing = VolcengineBillingClient(cfg)
        ok = _report(
            'QueryBalanceAcct', billing.query_balance_acct
        ) and ok
        ok = _report(
            'ListBillOverviewByProd',
            lambda: billing.list_bill_overview_by_prod(args.bill_period, limit=300),
        ) and ok
        ok = _report(
            'ListBill',
            lambda: billing.list_bill(args.bill_period, limit=5),
        ) and ok
        ok = _report(
            'ListBillDetail',
            lambda: billing.list_bill_detail(args.bill_period, limit=5, group_period=2),
        ) and ok
        if args.split:
            ok = _report(
                'ListSplitBillDetail',
                lambda: billing.list_split_bill_detail(
                    args.bill_period, limit=5, group_period=2,
                    split_dimension=cfg.VOLCENGINE_ARK_BILL_SPLIT_DIMENSION or None,
                ),
            ) and ok
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
