from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import AssetRights, AssetProvenanceEvent


class RightsService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def get_asset_rights(self, asset_id):
        row = self.db.fetch_one('SELECT * FROM asset_rights WHERE asset_id = ? ORDER BY created_at DESC LIMIT 1', (asset_id,))
        item = AssetRights.from_row(row)
        return item.to_dict() if item else None

    def validate_asset_rights(self, asset_id, usage_scope, tenant_id=None):
        rights = self.get_asset_rights(asset_id)
        now_ts = int(time.time())
        if not rights:
            return {
                'asset_id': asset_id,
                'status': 'warning',
                'allowed': False,
                'message': '未找到版权记录，已进入演示告警路径',
                'checked_at': now_ts,
                'usage_scope': usage_scope,
            }
        restrictions = rights.get('restrictions') or []
        approved = rights.get('approval_status') in ('approved', 'approved_with_notice')
        not_expired = not rights.get('expires_at') or rights.get('expires_at') > now_ts
        allowed_scope = rights.get('usage_scope') in (None, '', usage_scope, 'all')
        allowed = approved and not_expired and allowed_scope
        return {
            'asset_id': asset_id,
            'status': 'approved' if allowed else 'warning',
            'allowed': allowed,
            'message': '版权校验通过' if allowed else '版权存在范围或到期告警，已进入受限模式',
            'checked_at': now_ts,
            'usage_scope': usage_scope,
            'rights': rights,
            'restriction_tags': restrictions,
            'tenant_id': tenant_id,
        }

    def list_provenance(self, asset_id):
        rows = self.db.fetch_all(
            'SELECT * FROM asset_provenance_events WHERE asset_id = ? ORDER BY created_at ASC',
            (asset_id,)
        )
        return [AssetProvenanceEvent.from_row(row).to_dict() for row in rows]

    def build_job_snapshot(self, job_id, asset_id, tenant_id, project_id, user_id, validation_result):
        return {
            'job_id': job_id,
            'asset_id': asset_id,
            'tenant_id': tenant_id,
            'project_id': project_id,
            'user_id': user_id,
            'validation_result': validation_result,
            'provenance_chain': self.list_provenance(asset_id) if asset_id else [],
            'immutable_digest': 'demo-{0}-{1}'.format(job_id[:8], asset_id or 'text'),
            'recorded_at': int(time.time()),
        }


def get_rights_service(data_dir=None):
    return RightsService(data_dir)
