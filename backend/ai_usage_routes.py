# -*- coding: utf-8 -*-
"""Admin-only AI model usage and Volcengine Ark usage endpoints."""
from __future__ import absolute_import

from datetime import datetime

from flask import g, request

from .auth_middleware import admin_required
from .http_utils import ApiError, parse_json_body, parse_pagination
from .rate_limiter import rate_limit
from .volcengine.client import VolcengineAPIError
from .volcengine.usage_service import VolcengineUsageService


def get_usage_service(cfg):
    return VolcengineUsageService(cfg)


def _admin_rate_key(req):
    user = getattr(g, 'current_user', None) or {}
    return 'user:' + str(user.get('id') or req.remote_addr or 'unknown')


def _days():
    raw = request.args.get('days', 30)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise ApiError('invalid_days', 'days 必须为整数', status_code=400)
    if days < 1 or days > 366:
        raise ApiError('invalid_days', 'days 必须在 1 到 366 之间', status_code=400)
    return days


def _date_arg(name):
    value = (request.args.get(name) or '').strip()
    if not value:
        return None
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise ApiError(
            'invalid_date', '{0} 格式应为 YYYY-MM-DD'.format(name), status_code=400
        )
    return value


def _upstream_error(exc, json_error):
    category = getattr(exc, 'category', 'sync_error')
    details = {
        'category': category,
        'code': getattr(exc, 'code', None),
        'request_id': getattr(exc, 'request_id', None),
    }
    if category in ('unconfigured', 'disabled'):
        return json_error(
            'official_usage_{0}'.format(category),
            str(exc),
            status_code=400,
            details=details,
        )
    if category == 'no_permission':
        return json_error(
            'volcengine_no_permission',
            '火山引擎管理凭据没有读取用量/账单的权限',
            status_code=502,
            details=details,
        )
    if category == 'unauthorized':
        return json_error(
            'volcengine_credentials_invalid',
            '火山引擎管理凭据无效或签名不通过',
            status_code=502,
            details=details,
        )
    if category == 'throttled':
        return json_error(
            'volcengine_throttled',
            '火山引擎接口限流，请稍后重试',
            status_code=429,
            details=details,
        )
    if category == 'invalid_param':
        return json_error(
            'volcengine_invalid_param',
            '火山引擎接口参数无效',
            status_code=400,
            details=details,
        )
    return json_error(
        'volcengine_unavailable',
        '火山引擎接口暂不可用',
        status_code=502,
        details=details,
    )


def register_ai_usage_routes(app, cfg, json_success, json_error):
    @app.route('/api/admin/ark/status', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_status():
        return json_success(get_usage_service(cfg).status())

    @app.route('/api/admin/ark/usage/summary', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_usage_summary():
        days = _days()
        service = get_usage_service(cfg)
        return json_success({
            'days': days,
            'local': service.local_summary(days=days),
            'official': service.official_summary(days=days),
            'status': service.status(),
        })

    @app.route('/api/admin/ark/usage/models', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_usage_models():
        days = _days()
        service = get_usage_service(cfg)
        return json_success({
            'days': days,
            'local': service.local_models(days=days),
            'official': service.official_models(days=days),
        })

    @app.route('/api/admin/ark/usage/trend', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_usage_trend():
        days = _days()
        service = get_usage_service(cfg)
        return json_success({
            'days': days,
            'local': service.local_trend(days=days),
            'official': service.official_trend(days=days),
        })

    @app.route('/api/admin/ark/usage/tasks', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ark_usage_tasks():
        days = _days()
        pagination = parse_pagination(request, default_limit=50, max_limit=200)
        service = get_usage_service(cfg)
        payload = service.local_tasks(
            days=days, limit=pagination.limit, offset=pagination.offset
        )
        payload['performance'] = service.task_performance(days=days)
        return json_success(payload)

    @app.route('/api/admin/ark/usage/sync', methods=['POST'])
    @admin_required
    @rate_limit(3, 60, key_func=_admin_rate_key)
    def admin_ark_usage_sync():
        data = parse_json_body(request)
        days = data.get('days')
        if days is None:
            days = request.args.get('days', 31)
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise ApiError('invalid_days', 'days 必须为整数', status_code=400)
        if days < 1 or days > 366:
            raise ApiError('invalid_days', 'days 必须在 1 到 366 之间', status_code=400)
        start_date = (data.get('start_date') or '').strip() or None
        end_date = (data.get('end_date') or '').strip() or None
        for name, value in (('start_date', start_date), ('end_date', end_date)):
            if value:
                try:
                    datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    raise ApiError(
                        'invalid_date', '{0} 格式应为 YYYY-MM-DD'.format(name),
                        status_code=400,
                    )
        try:
            result = get_usage_service(cfg).sync_official_usage(
                days=days, start_date=start_date, end_date=end_date,
                actor=getattr(g, 'current_user', None),
            )
        except VolcengineAPIError as exc:
            return _upstream_error(exc, json_error)
        if not result.get('claimed'):
            return json_error(
                'sync_running', '官方用量同步正在进行中，请稍后刷新状态',
                status_code=409,
            )
        return json_success(result, message='火山方舟官方用量同步完成')

    @app.route('/api/admin/ai-usage/users', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ai_usage_users():
        days = _days()
        return json_success(get_usage_service(cfg).local_users(days=days))

    @app.route('/api/admin/ai-usage/tasks', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ai_usage_tasks():
        days = _days()
        pagination = parse_pagination(request, default_limit=50, max_limit=200)
        return json_success(get_usage_service(cfg).local_tasks(
            days=days, limit=pagination.limit, offset=pagination.offset
        ))

    @app.route('/api/admin/ai-usage/reconciliation', methods=['GET'])
    @admin_required
    @rate_limit(120, 60, key_func=_admin_rate_key)
    def admin_ai_usage_reconciliation():
        days = _days()
        return json_success(get_usage_service(cfg).reconciliation(days=days))
