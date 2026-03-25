from __future__ import absolute_import

import os
import time

from .database import get_database
from .models import (
    Tenant,
    User,
    Project,
    ProjectMembership,
    Resource,
    EngineProfile,
    AssetRights,
    AssetProvenanceEvent,
    BillingAccount,
)


def _insert_if_missing(db, table_name, item_id, params):
    row = db.fetch_one('SELECT id FROM {0} WHERE id = ?'.format(table_name), (item_id,))
    if row:
        return
    db.insert(table_name, params)


class DemoSeedService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def seed(self):
        now_ts = int(time.time())

        tenant = Tenant(id='tenant_museum_group', name='华中文博演示集团', code='museum-group', tier='旗舰版', status='active', metadata={'package_status': '正常', 'region': 'cn-central'})
        _insert_if_missing(self.db, Tenant.TABLE_NAME, tenant.id, tenant.to_insert_params())

        user_admin = User(id='user_curator_01', tenant_id=tenant.id, name='陈策展', role='owner', title='数字内容总监', status='active', metadata={'avatar_label': '策'})
        user_pm = User(id='user_pm_01', tenant_id=tenant.id, name='刘制片', role='producer', title='项目制片', status='active', metadata={'avatar_label': '制'})
        _insert_if_missing(self.db, User.TABLE_NAME, user_admin.id, user_admin.to_insert_params())
        _insert_if_missing(self.db, User.TABLE_NAME, user_pm.id, user_pm.to_insert_params())

        project = Project(id='project_mid_demo', tenant_id=tenant.id, name='中期汇报沉浸式样片', code='mid-demo', status='active', render_mode='cinematic', metadata={'package_status': 'demo_ready', 'usage_scope': 'client_review'})
        _insert_if_missing(self.db, Project.TABLE_NAME, project.id, project.to_insert_params())

        membership_1 = ProjectMembership(id='membership_owner_demo', project_id=project.id, user_id=user_admin.id, tenant_id=tenant.id, role='owner', permissions=['submit_job', 'approve_rights', 'view_billing'])
        membership_2 = ProjectMembership(id='membership_pm_demo', project_id=project.id, user_id=user_pm.id, tenant_id=tenant.id, role='editor', permissions=['submit_job', 'view_monitor'])
        _insert_if_missing(self.db, ProjectMembership.TABLE_NAME, membership_1.id, membership_1.to_insert_params())
        _insert_if_missing(self.db, ProjectMembership.TABLE_NAME, membership_2.id, membership_2.to_insert_params())

        resources = [
            Resource(id='resource_local_a10', tenant_id=tenant.id, node_name='local-gpu-a10-01', pool_type='local_gpu', region='lab-a', gpu_type='A10', capacity_units=2, queue_depth=1, status='ready', utilization_hint=0.42, metadata={'network_zone': 'studio-lan'}),
            Resource(id='resource_cloud_a100', tenant_id=tenant.id, node_name='cloud-a100-hz-01', pool_type='public_cloud', region='cn-hangzhou', gpu_type='A100', capacity_units=8, queue_depth=3, status='ready', utilization_hint=0.78, metadata={'provider': 'demo-cloud'}),
            Resource(id='resource_edge_l40', tenant_id=tenant.id, node_name='edge-l40-sh-01', pool_type='edge_gpu', region='cn-shanghai-edge', gpu_type='L40', capacity_units=4, queue_depth=2, status='ready', utilization_hint=0.61, metadata={'latency_profile': 'low_latency'}),
        ]
        for item in resources:
            _insert_if_missing(self.db, Resource.TABLE_NAME, item.id, item.to_insert_params())

        engines = [
            EngineProfile(id='engine_blender_anchor', engine_type='blender_anchor', display_name='Blender Anchor', render_mode='cinematic', stream_mode='balanced', status='active', metadata={'preview_label': '空间锚点'}),
            EngineProfile(id='engine_ue5_cloud', engine_type='ue5_cloud', display_name='UE5 Cloud', render_mode='cinematic', stream_mode='showcase', status='showcase', metadata={'preview_label': '云渲染'}),
            EngineProfile(id='engine_unity_cloud', engine_type='unity_cloud', display_name='Unity Cloud', render_mode='interactive', stream_mode='balanced', status='showcase', metadata={'preview_label': '实时交互'}),
            EngineProfile(id='engine_steamvr_stream', engine_type='steamvr_stream', display_name='SteamVR Stream', render_mode='vr_walkthrough', stream_mode='low_latency', status='showcase', metadata={'preview_label': '低时延推流'}),
        ]
        for item in engines:
            _insert_if_missing(self.db, EngineProfile.TABLE_NAME, item.id, item.to_insert_params())

        rights_rows = [
            AssetRights(id='rights_gallery_modern', asset_id='gallery_modern', tenant_id=tenant.id, license_type='exclusive_demo', source_name='馆内自有资产库', approval_status='approved', usage_scope='client_review', expires_at=now_ts + 86400 * 90, restrictions=['不可商用', '需保留来源标签'], metadata={'approver': '法务审批流-02'}),
            AssetRights(id='rights_theater_stage', asset_id='theater_stage', tenant_id=tenant.id, license_type='partner_demo', source_name='合作方授权包', approval_status='approved_with_notice', usage_scope='internal_demo', expires_at=now_ts + 86400 * 30, restrictions=['仅限内部演示'], metadata={'approver': '项目经理'}),
            AssetRights(id='rights_museum_warning', asset_id='museum_warning_asset', tenant_id=tenant.id, license_type='pending_clearance', source_name='外部采样素材', approval_status='pending', usage_scope='client_review', expires_at=now_ts + 86400 * 7, restrictions=['待补齐授权证明'], metadata={'approver': '待处理'}),
        ]
        for item in rights_rows:
            _insert_if_missing(self.db, AssetRights.TABLE_NAME, item.id, item.to_insert_params())

        provenance_rows = [
            AssetProvenanceEvent(id='prov_gallery_1', asset_id='gallery_modern', tenant_id=tenant.id, event_type='ingest', event_summary='资产接入演示目录', metadata={'source': '导入任务'}),
            AssetProvenanceEvent(id='prov_gallery_2', asset_id='gallery_modern', tenant_id=tenant.id, event_type='approval', event_summary='版权审批通过', metadata={'reviewer': '法务审批流-02'}),
            AssetProvenanceEvent(id='prov_warning_1', asset_id='museum_warning_asset', tenant_id=tenant.id, event_type='warning', event_summary='检测到授权材料缺失', metadata={'severity': 'medium'}),
        ]
        for item in provenance_rows:
            _insert_if_missing(self.db, AssetProvenanceEvent.TABLE_NAME, item.id, item.to_insert_params())

        billing = BillingAccount(id='billing_demo_primary', tenant_id=tenant.id, project_id=project.id, plan_name='演示旗舰套餐', balance=48000.0, currency='CNY', status='active', metadata={'quota_gpu_hours': 120.0, 'quota_stream_hours': 80.0})
        _insert_if_missing(self.db, BillingAccount.TABLE_NAME, billing.id, billing.to_insert_params())


def seed_demo_data(data_dir=None):
    DemoSeedService(data_dir).seed()
