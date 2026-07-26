# -*- coding: utf-8 -*-
"""Cloud inventory orchestration service — provider factory, host sync, CRUD."""
from __future__ import absolute_import

import logging
import os
import time

from .cloud_providers.aliyun_provider import AliyunProvider
from .cloud_providers.tencent_provider import TencentProvider
from .cloud_providers.vmware_provider import VMwareProvider
from .cloud_providers.generic_rest_provider import GenericRestProvider
from .config import Config
from .database import get_database
from .models import CloudAccount, ComputeNode

logger = logging.getLogger(__name__)


class CloudInventoryService(object):
    """Manages cloud accounts, provider lifecycle, and host inventory sync."""

    def __init__(self, data_dir=None, cfg=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.cfg = cfg or Config()
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    # ── Account CRUD ──

    def list_accounts(self, tenant_id=None):
        if tenant_id:
            rows = self.db.fetch_all(
                'SELECT * FROM cloud_accounts WHERE tenant_id = ? ORDER BY created_at ASC',
                (tenant_id,)
            )
        else:
            rows = self.db.fetch_all('SELECT * FROM cloud_accounts ORDER BY created_at ASC')
        return [CloudAccount.from_row(row).to_dict() for row in rows]

    def create_account(self, tenant_id, provider_type, name, region_list=None, config_metadata=None):
        valid_types = ['aliyun', 'tencent', 'vmware', 'generic_rest']
        if provider_type not in valid_types:
            raise ValueError('Unsupported provider_type: {0}. Must be one of {1}'.format(
                provider_type, valid_types))

        # Verify credentials exist
        self._validate_credentials(provider_type)

        account = CloudAccount(
            tenant_id=tenant_id,
            provider_type=provider_type,
            name=name,
            region_list=region_list or [],
            enabled=1,
            config_metadata=config_metadata or {},
        )
        self.db.insert(CloudAccount.TABLE_NAME, account.to_insert_params())
        return account.to_dict()

    def delete_account(self, account_id):
        self.db.delete(CloudAccount.TABLE_NAME, 'id = ?', (account_id,))

    # ── Provider Factory ──

    def _validate_credentials(self, provider_type):
        """Check that required env vars are set. Raises ValueError."""
        mapping = {
            'aliyun': ('ALIYUN_ACCESS_KEY', 'ALIYUN_ACCESS_SECRET'),
            'tencent': ('TENCENT_SECRET_ID', 'TENCENT_SECRET_KEY'),
            'vmware': ('VMWARE_HOST', 'VMWARE_USER', 'VMWARE_PASSWORD'),
            'generic_rest': ('GENERIC_REST_URL', 'GENERIC_REST_TOKEN'),
        }
        keys = mapping.get(provider_type, ())
        missing = [k for k in keys if not getattr(self.cfg, k, None)]
        if missing:
            raise ValueError(
                'Missing credentials for {0}: {1}'.format(provider_type, ', '.join(missing))
            )

    def _build_provider(self, account):
        """Instantiate the correct provider class for an account."""
        if isinstance(account, dict):
            provider_type = account.get('provider_type')
            config_meta = account.get('config_metadata') or {}
        else:
            provider_type = account.provider_type
            config_meta = account.config_metadata or {}

        if provider_type == 'aliyun':
            return AliyunProvider(
                access_key_id=self.cfg.ALIYUN_ACCESS_KEY,
                access_key_secret=self.cfg.ALIYUN_ACCESS_SECRET,
                region_id=self.cfg.ALIYUN_REGION_ID,
            )
        elif provider_type == 'tencent':
            return TencentProvider(
                secret_id=self.cfg.TENCENT_SECRET_ID,
                secret_key=self.cfg.TENCENT_SECRET_KEY,
                region=self.cfg.TENCENT_REGION,
            )
        elif provider_type == 'vmware':
            return VMwareProvider(
                host=self.cfg.VMWARE_HOST,
                username=self.cfg.VMWARE_USER,
                password=self.cfg.VMWARE_PASSWORD,
            )
        elif provider_type == 'generic_rest':
            return GenericRestProvider(
                base_url=self.cfg.GENERIC_REST_URL,
                token=self.cfg.GENERIC_REST_TOKEN,
                config_metadata=config_meta,
            )
        else:
            raise ValueError('Unknown provider_type: {0}'.format(provider_type))

    # ── Host Sync ──

    def sync_hosts(self, account_id):
        """Fetch hosts from provider and upsert into compute_nodes table."""
        account_row = self.db.fetch_one(
            'SELECT * FROM cloud_accounts WHERE id = ?', (account_id,)
        )
        if not account_row:
            raise ValueError('Cloud account not found: {0}'.format(account_id))

        account = CloudAccount.from_row(account_row)
        if not account.enabled:
            logger.warning('Cloud account %s is disabled, skipping sync', account_id)
            return {'synced': 0, 'total': 0, 'errors': 0, 'account_id': account_id}

        provider = self._build_provider(account)
        region_list = account.region_list or [None]

        synced = 0
        errors = 0
        all_hosts = []

        for region in region_list:
            try:
                hosts = provider.list_hosts(region=region)
                all_hosts.extend(hosts)
            except Exception as e:
                logger.error('Failed to list hosts for region %s: %s', region, e)
                errors += 1

        now_ts = int(time.time())
        for host in all_hosts:
            host['tenant_id'] = account.tenant_id
            host['created_at'] = now_ts
            host['updated_at'] = now_ts

            # Upsert by external_id + provider_type
            existing = self.db.fetch_one(
                'SELECT id FROM compute_nodes WHERE external_id = ? AND provider_type = ?',
                (host['external_id'], host['provider_type'])
            )

            if existing:
                del host['created_at']
                self.db.update(
                    ComputeNode.TABLE_NAME,
                    host,
                    'id = ?',
                    (existing['id'],)
                )
            else:
                node = ComputeNode(**host)
                self.db.insert(ComputeNode.TABLE_NAME, node.to_insert_params())

            synced += 1

        return {
            'synced': synced,
            'total': len(all_hosts),
            'errors': errors,
            'account_id': account_id,
            'provider_type': account.provider_type,
        }

    def provider_health_check(self, account_id):
        """Run a health check on the provider for the given account."""
        account_row = self.db.fetch_one(
            'SELECT * FROM cloud_accounts WHERE id = ?', (account_id,)
        )
        if not account_row:
            raise ValueError('Cloud account not found: {0}'.format(account_id))

        account = CloudAccount.from_row(account_row)
        provider = self._build_provider(account)
        return provider.health_check()

    # ── Host Queries ──

    def list_hosts(self, tenant_id=None, provider_type=None, region=None,
                   status=None, keyword=None, sort_field='node_name',
                   sort_order='asc', limit=50, offset=0, schedulable=None):
        """Paginated host list with filters."""
        where_clauses = []
        params = []

        if tenant_id:
            where_clauses.append('tenant_id = ?')
            params.append(tenant_id)
        if provider_type:
            where_clauses.append('provider_type = ?')
            params.append(provider_type)
        if region:
            where_clauses.append('region = ?')
            params.append(region)
        if status:
            where_clauses.append('status = ?')
            params.append(status)
        if schedulable is not None:
            where_clauses.append('schedulable = ?')
            params.append(1 if schedulable else 0)
        if keyword:
            where_clauses.append('(node_name LIKE ? OR ip_address LIKE ? OR host_name LIKE ?)')
            like = '%{0}%'.format(keyword)
            params.extend([like, like, like])

        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

        # Whitelist sort fields
        valid_sorts = {
            'node_name', 'provider_type', 'region', 'cpu_cores', 'memory_mb',
            'gpu_count', 'status', 'created_at', 'updated_at'
        }
        sf = sort_field if sort_field in valid_sorts else 'node_name'
        so = 'DESC' if sort_order and sort_order.upper() == 'DESC' else 'ASC'

        total = self.db.count('compute_nodes', where_sql, tuple(params))

        query = 'SELECT * FROM compute_nodes WHERE {0} ORDER BY {1} {2} LIMIT {3} OFFSET {4}'.format(
            where_sql, sf, so, int(limit), int(offset)
        )
        rows = self.db.fetch_all(query, tuple(params))
        hosts = [ComputeNode.from_row(row).to_dict() for row in rows]

        return {'items': hosts, 'total': total, 'limit': int(limit), 'offset': int(offset)}

    def get_host(self, host_id):
        row = self.db.fetch_one('SELECT * FROM compute_nodes WHERE id = ?', (host_id,))
        if not row:
            return None
        return ComputeNode.from_row(row).to_dict()

    def count_hosts(self, tenant_id=None, provider_type=None, status=None):
        where_clauses = []
        params = []
        if tenant_id:
            where_clauses.append('tenant_id = ?')
            params.append(tenant_id)
        if provider_type:
            where_clauses.append('provider_type = ?')
            params.append(provider_type)
        if status:
            where_clauses.append('status = ?')
            params.append(status)
        where_sql = ' AND '.join(where_clauses) if where_clauses else None
        return self.db.count('compute_nodes', where_sql, tuple(params) if params else None)


def get_cloud_inventory_service(data_dir=None, cfg=None):
    return CloudInventoryService(data_dir, cfg)
