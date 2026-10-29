# -*- coding: utf-8 -*-
"""Cloud provider API routes for AIGV Studio."""
from __future__ import absolute_import

import logging

from flask import g, request

from .auth_middleware import (
    login_required,
    permission_required,
    is_admin,
    PERM_VIEW_COMPUTE,
    PERM_MANAGE_COMPUTE,
    PERM_SUBMIT_RENDER_JOB,
    PERM_MANAGE_CLOUD_ACCOUNTS,
    PERM_VIEW_BILLING,
    PERM_VIEW_MONITOR,
)
from .cloud_inventory_service import get_cloud_inventory_service
from .http_utils import parse_json_body

logger = logging.getLogger(__name__)


def register_cloud_routes(app, cfg, json_success, json_error):
    cloud_service = get_cloud_inventory_service(cfg.DATA_DIR, cfg)

    def _account_allowed(account_id):
        row = cloud_service.db.fetch_one(
            'SELECT tenant_id FROM cloud_accounts WHERE id = ?', (account_id,)
        )
        if not row:
            return None
        if is_admin(g.current_user):
            return True
        return row.get('tenant_id') == g.current_user.get('tenant_id')

    # ── Cloud Accounts ──

    @app.route('/api/cloud/providers', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_cloud_providers():
        tenant_id = request.args.get('tenant_id') if is_admin(g.current_user) else g.current_user.get('tenant_id')
        return json_success(cloud_service.list_accounts(tenant_id=tenant_id))

    @app.route('/api/cloud/providers', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_CLOUD_ACCOUNTS)
    def create_cloud_provider():
        payload = parse_json_body(request)
        tenant_id = payload.get('tenant_id') if is_admin(g.current_user) else g.current_user.get('tenant_id')
        if not tenant_id:
            return json_error('missing_field', '缺少 tenant_id', 400)

        try:
            account = cloud_service.create_account(
                tenant_id=tenant_id,
                provider_type=payload.get('provider_type'),
                name=payload.get('name'),
                region_list=payload.get('region_list'),
                config_metadata=payload.get('config_metadata'),
            )
            return json_success(account)
        except ValueError as e:
            return json_error('invalid_request', str(e), 400)
        except Exception as e:
            logger.error('Failed to create cloud account: %s', e)
            return json_error('server_error', '创建云账号失败', 500)

    @app.route('/api/cloud/providers/<account_id>', methods=['DELETE'])
    @login_required
    @permission_required(PERM_MANAGE_CLOUD_ACCOUNTS)
    def delete_cloud_provider(account_id):
        allowed = _account_allowed(account_id)
        if allowed is None:
            return json_error('not_found', '云账号不存在', 404)
        if allowed is not True:
            return json_error('forbidden', '无权操作该云账号', 403)
        try:
            cloud_service.delete_account(account_id)
            return json_success(None, message='已删除')
        except Exception as e:
            logger.error('Failed to delete cloud account: %s', e)
            return json_error('server_error', '删除云账号失败', 500)

    @app.route('/api/cloud/providers/<account_id>/sync', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_COMPUTE)
    def sync_cloud_provider(account_id):
        allowed = _account_allowed(account_id)
        if allowed is None:
            return json_error('not_found', '云账号不存在', 404)
        if allowed is not True:
            return json_error('forbidden', '无权操作该云账号', 403)
        try:
            result = cloud_service.sync_hosts(account_id)
            return json_success(result)
        except ValueError as e:
            return json_error('not_found', str(e), 404)
        except Exception as e:
            logger.error('Failed to sync hosts: %s', e)
            return json_error('sync_error', '同步主机失败: {0}'.format(str(e)[:200]), 500)

    @app.route('/api/cloud/providers/<account_id>/health', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def cloud_provider_health(account_id):
        allowed = _account_allowed(account_id)
        if allowed is None:
            return json_error('not_found', '云账号不存在', 404)
        if allowed is not True:
            return json_error('forbidden', '无权操作该云账号', 403)
        try:
            result = cloud_service.provider_health_check(account_id)
            return json_success(result)
        except ValueError as e:
            return json_error('not_found', str(e), 404)
        except Exception as e:
            logger.error('Health check failed: %s', e)
            return json_error('health_error', str(e), 500)

    # ── Hosts ──

    @app.route('/api/cloud/hosts', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_cloud_hosts():
        tenant_id = request.args.get('tenant_id') if is_admin(g.current_user) else g.current_user.get('tenant_id')
        provider_type = request.args.get('provider_type')
        region = request.args.get('region')
        status = request.args.get('status')
        keyword = request.args.get('keyword')
        sort_field = request.args.get('sort', 'node_name')
        sort_order = request.args.get('order', 'asc')
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
        schedulable = request.args.get('schedulable')
        if schedulable is not None:
            schedulable = schedulable.lower() in ('1', 'true', 'yes')

        return json_success(cloud_service.list_hosts(
            tenant_id=tenant_id,
            provider_type=provider_type,
            region=region,
            status=status,
            keyword=keyword,
            sort_field=sort_field,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
            schedulable=schedulable,
        ))

    @app.route('/api/cloud/hosts/<host_id>', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def get_cloud_host(host_id):
        host = cloud_service.get_host(host_id)
        if not host:
            return json_error('not_found', '主机不存在', 404)
        if not is_admin(g.current_user) and host.get('tenant_id') != g.current_user.get('tenant_id'):
            return json_error('forbidden', '无权访问该主机', 403)
        return json_success(host)
