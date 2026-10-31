# -*- coding: utf-8 -*-
"""Admin-only Volcengine official bill, balance and reconciliation endpoints."""
from __future__ import absolute_import

from datetime import datetime

from flask import g, request

from .ai_usage_routes import _admin_rate_key, _upstream_error
from .auth_middleware import admin_required
from .http_utils import ApiError, parse_json_body, parse_pagination
from .rate_limiter import rate_limit
from .volcengine.billing_sync_service import VolcengineBillingService
from .volcengine.client import VolcengineAPIError


def get_billing_service(cfg):
    return VolcengineBillingService(cfg)


def _bill_period():
    value = (request.args.get('bill_period') or '').strip()
    if not value:
        return None
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError:
        raise ApiError('invalid_bill_period', 'bill_period 格式应为 YYYY-MM', status_code=400)
    return value


def _level():
    value = (request.args.get('level') or 'detail').strip()
    if value not in ('overview', 'bill', 'detail', 'split'):
        raise ApiError('invalid_level', 'level 必须为 overview/bill/detail/split', status_code=400)
    return value


def register_ark_billing_routes(app, cfg, json_success, json_error):
    @app.route('/api/admin/ark/billing/summary', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_summary():
        return json_success(get_billing_service(cfg).summary(_bill_period()))

    @app.route('/api/admin/ark/billing/details', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_details():
        pagination = parse_pagination(request, default_limit=50, max_limit=300)
        return json_success(get_billing_service(cfg).details(
            _bill_period(), level=_level(),
            limit=pagination.limit, offset=pagination.offset,
        ))

    @app.route('/api/admin/ark/billing/balance', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_balance():
        return json_success(get_billing_service(cfg).balance())

    @app.route('/api/admin/ark/billing/sync-status', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_sync_status():
        return json_success(get_billing_service(cfg).status())

    @app.route('/api/admin/ark/billing/models', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_models():
        return json_success(get_billing_service(cfg).model_breakdown(_bill_period()))

    @app.route('/api/admin/ark/billing/trend', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_trend():
        return json_success(get_billing_service(cfg).daily_trend(_bill_period()))

    @app.route('/api/admin/ark/billing/attribution', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_attribution():
        return json_success(get_billing_service(cfg).user_attribution(_bill_period()))

    @app.route('/api/admin/ark/billing/reconciliation', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_billing_reconciliation():
        return json_success(get_billing_service(cfg).reconciliation(_bill_period()))

    @app.route('/api/admin/ark/billing/sync', methods=['POST'])
    @admin_required
    @rate_limit(2, 60, key_func=_admin_rate_key)
    def admin_ark_billing_sync():
        data = parse_json_body(request)
        bill_period = (data.get('bill_period') or '').strip() or None
        if bill_period:
            try:
                datetime.strptime(bill_period, '%Y-%m')
            except ValueError:
                raise ApiError(
                    'invalid_bill_period', 'bill_period 格式应为 YYYY-MM',
                    status_code=400,
                )
        include_split = data.get('include_split')
        if include_split is not None:
            include_split = bool(include_split)
        try:
            result = get_billing_service(cfg).sync_billing(
                bill_period=bill_period, actor=getattr(g, 'current_user', None),
                include_split=include_split,
            )
        except VolcengineAPIError as exc:
            return _upstream_error(exc, json_error, scope='billing')
        if not result.get('claimed'):
            return json_error(
                'sync_running', '官方账单同步正在进行中，请稍后刷新状态',
                status_code=409,
            )
        return json_success(result, message='火山引擎官方账单同步完成')
