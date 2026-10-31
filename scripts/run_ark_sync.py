#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Periodic / one-shot sync for Volcengine Ark usage and official bills.

The worker is intentionally separate from the web process.  It reads the same
.env and SQLite database, uses the admin-only read APIs, and never logs
credentials or full upstream payloads.
"""
from __future__ import absolute_import

import argparse
import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import Config
from backend.database import get_database, init_database
from backend.volcengine.billing_sync_service import VolcengineBillingService
from backend.volcengine.client import VolcengineAPIError
from backend.volcengine.usage_service import VolcengineUsageService

logger = logging.getLogger('ark_sync')


def _build_config():
    cfg = Config()
    init_database(cfg.DATA_DIR)
    return cfg


def _run_usage(cfg, days=None):
    service = VolcengineUsageService(cfg, db=get_database(os.path.join(cfg.DATA_DIR, 'aigv.db')))
    try:
        result = service.sync_official_usage(days=days or cfg.VOLCENGINE_USAGE_LOOKBACK_DAYS)
        logger.info(
            'usage sync %s rows=%s start=%s end=%s filters=%s',
            result.get('status'), result.get('rows'), result.get('start_date'),
            result.get('end_date'), result.get('dimension_filters_supported'),
        )
        return True
    except VolcengineAPIError as exc:
        logger.warning('usage sync failed category=%s code=%s', exc.category, exc.code)
        return False
    except Exception as exc:
        logger.warning('usage sync unexpected error: %s', str(exc)[:300])
        return False


def _run_billing(cfg, bill_period=None, include_split=None):
    service = VolcengineBillingService(cfg, db=get_database(os.path.join(cfg.DATA_DIR, 'aigv.db')))
    try:
        result = service.sync_billing(
            bill_period=bill_period, include_split=include_split
        )
        logger.info(
            'billing sync %s periods=%s counts=%s split=%s balance=%s',
            result.get('status'), result.get('periods'), result.get('counts'),
            result.get('split_status'), (result.get('balance') or {}).get('status'),
        )
        return True
    except VolcengineAPIError as exc:
        logger.warning('billing sync failed category=%s code=%s', exc.category, exc.code)
        return False
    except Exception as exc:
        logger.warning('billing sync unexpected error: %s', str(exc)[:300])
        return False


def _one_shot(cfg, args):
    ok = True
    run_usage = not args.billing_only
    run_billing = not args.usage_only
    if run_usage:
        ok = _run_usage(cfg, days=args.days) and ok
    if run_billing:
        ok = _run_billing(
            cfg, bill_period=args.bill_period,
            include_split=True if args.include_split else None,
        ) and ok
    return 0 if ok else 1


def _loop(cfg, args):
    stop = {'value': False}

    def _stop(signum, frame):
        stop['value'] = True
        logger.info('received signal %s, stopping', signum)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    usage_interval = max(60, int(cfg.VOLCENGINE_USAGE_SYNC_INTERVAL_S or 1800))
    billing_interval = max(300, int(cfg.VOLCENGINE_BILLING_SYNC_INTERVAL_S or 86400))
    next_usage = 0
    next_billing = 0
    while not stop['value']:
        now = time.time()
        usage_wanted = (
            not args.billing_only and cfg.VOLCENGINE_USAGE_ENABLED
            and cfg.VOLCENGINE_USAGE_SYNC_ENABLED
        )
        billing_wanted = (
            not args.usage_only and cfg.VOLCENGINE_BILLING_ENABLED
            and cfg.VOLCENGINE_BILLING_SYNC_ENABLED
        )
        if usage_wanted and now >= next_usage:
            _run_usage(cfg, days=args.days)
            next_usage = time.time() + usage_interval
        if billing_wanted and now >= next_billing:
            _run_billing(
                cfg, bill_period=args.bill_period,
                include_split=True if args.include_split else None,
            )
            next_billing = time.time() + billing_interval
        sleep_for = 30
        upcoming = [value for value in (next_usage, next_billing) if value]
        if upcoming:
            sleep_for = max(5, min(60, min(upcoming) - time.time()))
        time.sleep(sleep_for)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Sync Volcengine Ark usage / official bills')
    parser.add_argument('--once', action='store_true', help='run one sync and exit')
    parser.add_argument('--loop', action='store_true', help='run continuously')
    parser.add_argument('--usage-only', action='store_true')
    parser.add_argument('--billing-only', action='store_true')
    parser.add_argument('--bill-period', default=None, help='YYYY-MM for a single bill period')
    parser.add_argument('--days', type=int, default=None, help='usage lookback days')
    parser.add_argument('--include-split', action='store_true',
                        help='also request split bill details when configured')
    args = parser.parse_args(argv)
    if not args.once and not args.loop:
        parser.error('choose --once or --loop')
    if args.usage_only and args.billing_only:
        parser.error('--usage-only and --billing-only are mutually exclusive')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    cfg = _build_config()
    if args.once:
        return _one_shot(cfg, args)
    return _loop(cfg, args)


if __name__ == '__main__':
    sys.exit(main())
