from __future__ import absolute_import

from flask import request

from .billing_service import get_billing_service
from .engine_service import get_engine_service
from .http_utils import parse_json_body
from .ops_service import get_ops_service
from .rights_service import get_rights_service
from .scheduler_service import get_scheduler_service
from .stream_service import get_stream_service
from .tenant_service import get_tenant_service


def register_control_plane_routes(app, cfg, catalog_service, job_store, json_success, json_error):
    tenant_service = get_tenant_service(cfg.DATA_DIR)
    rights_service = get_rights_service(cfg.DATA_DIR)
    scheduler_service = get_scheduler_service(cfg.DATA_DIR)
    engine_service = get_engine_service(cfg.DATA_DIR)
    billing_service = get_billing_service(cfg.DATA_DIR)
    ops_service = get_ops_service(cfg.DATA_DIR)
    stream_service = get_stream_service()

    @app.route('/api/demo/context', methods=['GET'])
    def demo_context():
        tenant_id = request.args.get('tenant_id')
        user_id = request.args.get('user_id')
        project_id = request.args.get('project_id')
        return json_success(tenant_service.get_context(tenant_id, user_id, project_id))

    @app.route('/api/demo/context/select', methods=['POST'])
    def select_demo_context():
        payload = parse_json_body(request)
        return json_success(tenant_service.get_context(payload.get('tenant_id'), payload.get('user_id'), payload.get('project_id')))

    @app.route('/api/tenants', methods=['GET'])
    def list_tenants():
        return json_success(tenant_service.list_tenants())

    @app.route('/api/users', methods=['GET'])
    def list_users():
        return json_success(tenant_service.list_users(request.args.get('tenant_id')))

    @app.route('/api/projects', methods=['GET'])
    def list_projects():
        return json_success(tenant_service.list_projects(request.args.get('tenant_id')))

    @app.route('/api/projects/<project_id>/members', methods=['GET'])
    def project_members(project_id):
        return json_success(tenant_service.list_project_members(project_id))

    @app.route('/api/permissions/check', methods=['GET'])
    def permission_check():
        allowed = tenant_service.check_permission(
            request.args.get('tenant_id'),
            request.args.get('user_id'),
            request.args.get('project_id'),
            request.args.get('permission')
        )
        return json_success({'allowed': allowed})

    @app.route('/api/resources', methods=['GET'])
    def list_resources():
        return json_success(scheduler_service.list_resources())

    @app.route('/api/resources/summary', methods=['GET'])
    def resources_summary():
        return json_success(scheduler_service.get_resource_summary())

    @app.route('/api/scheduler/preview', methods=['POST'])
    def scheduler_preview():
        payload = parse_json_body(request)
        return json_success(scheduler_service.preview_schedule(payload))

    @app.route('/api/jobs/<job_id>/schedule', methods=['GET'])
    def job_schedule(job_id):
        job = job_store.get(job_id)
        if not job:
            return json_error('job_not_found', '任务不存在', 404)
        return json_success((job.get('result') or {}).get('schedule_result'))

    @app.route('/api/jobs/<job_id>/monitor', methods=['GET'])
    def job_monitor(job_id):
        job = job_store.get(job_id)
        if not job:
            return json_error('job_not_found', '任务不存在', 404)
        monitor_summary = (job.get('result') or {}).get('monitor_summary') or {}
        return json_success(monitor_summary)

    @app.route('/api/engines', methods=['GET'])
    def list_engines():
        return json_success(engine_service.list_engines())

    @app.route('/api/engines/session/preview', methods=['POST'])
    def engine_preview():
        payload = parse_json_body(request)
        return json_success(engine_service.preview_session(payload))

    @app.route('/api/jobs/<job_id>/engine-session', methods=['GET'])
    def job_engine_session(job_id):
        job = job_store.get(job_id)
        if not job:
            return json_error('job_not_found', '任务不存在', 404)
        return json_success((job.get('result') or {}).get('engine_session'))

    @app.route('/api/jobs/<job_id>/stream-session', methods=['GET'])
    def job_stream_session(job_id):
        job = job_store.get(job_id)
        if not job:
            return json_error('job_not_found', '任务不存在', 404)
        return json_success((job.get('result') or {}).get('stream_session'))

    @app.route('/api/assets/<asset_id>/rights', methods=['GET'])
    def asset_rights(asset_id):
        return json_success(rights_service.get_asset_rights(asset_id))

    @app.route('/api/assets/<asset_id>/rights/validate', methods=['POST'])
    def validate_asset_rights(asset_id):
        payload = parse_json_body(request)
        usage_scope = payload.get('usage_scope') or 'internal_demo'
        return json_success(rights_service.validate_asset_rights(asset_id, usage_scope, payload.get('tenant_id')))

    @app.route('/api/assets/<asset_id>/provenance', methods=['GET'])
    def asset_provenance(asset_id):
        return json_success(rights_service.list_provenance(asset_id))

    @app.route('/api/jobs/<job_id>/rights-snapshot', methods=['GET'])
    def job_rights_snapshot(job_id):
        job = job_store.get(job_id)
        if not job:
            return json_error('job_not_found', '任务不存在', 404)
        return json_success((job.get('result') or {}).get('rights_result'))

    @app.route('/api/billing/summary', methods=['GET'])
    def billing_summary():
        return json_success(billing_service.get_billing_summary())

    @app.route('/api/projects/<project_id>/usage', methods=['GET'])
    def project_usage(project_id):
        return json_success(billing_service.get_project_usage(project_id))

    @app.route('/api/jobs/<job_id>/billing', methods=['GET'])
    def job_billing(job_id):
        return json_success(billing_service.get_job_billing(job_id))

    @app.route('/api/ops/events', methods=['GET'])
    def ops_events():
        project_id = request.args.get('project_id')
        return json_success(ops_service.list_events(project_id=project_id, limit=50))
