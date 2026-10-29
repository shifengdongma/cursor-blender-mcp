from __future__ import absolute_import

from flask import g, request, session

from .access import require_job
from .auth_middleware import (
    admin_required,
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
from .billing_service import get_billing_service
from .database import get_database
from .engine_service import get_engine_service
from .http_utils import parse_json_body
from .models import ComputeNode, NodeMetricSample, HealthCheck, Tenant, User, Project
from .monitoring.local_collector import MetricsCollector
from .ops_service import (
    get_ops_service,
    EVENT_NODE_ONLINE,
    EVENT_NODE_OFFLINE,
    EVENT_HEALTH_CHECK,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_ERROR,
)
from .render_service import get_render_service
from .rights_service import get_rights_service
from .scheduler_service import get_scheduler_service
from .stream_service import get_stream_service
from .tenant_service import get_tenant_service
import time
import json
import logging


def register_control_plane_routes(app, cfg, catalog_service, job_store, json_success, json_error):
    tenant_service = get_tenant_service(cfg.DATA_DIR)
    rights_service = get_rights_service(cfg.DATA_DIR)
    scheduler_service = get_scheduler_service(cfg.DATA_DIR)
    engine_service = get_engine_service(cfg.DATA_DIR)
    billing_service = get_billing_service(cfg.DATA_DIR)
    ops_service = get_ops_service(cfg.DATA_DIR)
    stream_service = get_stream_service()
    render_service = get_render_service(cfg.DATA_DIR, cfg)
    logger = logging.getLogger(__name__)

    def _current_context():
        user = g.current_user
        db = get_database()
        tenant_row = db.fetch_one('SELECT * FROM tenants WHERE id = ?', (user.get('tenant_id'),))
        business_user_row = db.fetch_one('SELECT * FROM users WHERE id = ?', (user.get('id'),))
        workspace_id = 'workspace_{0}'.format(user.get('id'))
        project_row = db.fetch_one('SELECT * FROM projects WHERE id = ?', (workspace_id,))
        project_rows = db.fetch_all(
            'SELECT p.* FROM projects p JOIN project_memberships m '
            'ON m.project_id = p.id AND m.tenant_id = p.tenant_id '
            'WHERE m.user_id = ? AND m.tenant_id = ? ORDER BY p.created_at ASC',
            (user.get('id'), user.get('tenant_id')),
        )
        return {
            'tenant': Tenant.from_row(tenant_row).to_dict() if tenant_row else None,
            'user': User.from_row(business_user_row).to_dict() if business_user_row else None,
            'project': Project.from_row(project_row).to_dict() if project_row else None,
            'available_users': [User.from_row(business_user_row).to_dict()] if business_user_row else [],
            'available_projects': [Project.from_row(row).to_dict() for row in project_rows],
        }

    @app.route('/api/demo/context', methods=['GET'])
    def demo_context():
        if cfg.DEMO_MODE and is_admin(g.current_user) and any(
            request.args.get(key) for key in ('tenant_id', 'user_id', 'project_id')
        ):
            return json_success(tenant_service.get_context(
                request.args.get('tenant_id'),
                request.args.get('user_id'),
                request.args.get('project_id'),
            ))
        return json_success(_current_context())

    @app.route('/api/demo/context/select', methods=['POST'])
    @admin_required
    def select_demo_context():
        if not cfg.DEMO_MODE:
            return json_error('not_found', '演示上下文未启用', status_code=404)
        payload = parse_json_body(request)
        return json_success(tenant_service.get_context(payload.get('tenant_id'), payload.get('user_id'), payload.get('project_id')))

    @app.route('/api/tenants', methods=['GET'])
    @admin_required
    def list_tenants():
        return json_success(tenant_service.list_tenants())

    @app.route('/api/users', methods=['GET'])
    @admin_required
    def list_users():
        return json_success(tenant_service.list_users(request.args.get('tenant_id')))

    @app.route('/api/projects', methods=['GET'])
    @admin_required
    def list_projects():
        return json_success(tenant_service.list_projects(request.args.get('tenant_id')))

    @app.route('/api/projects/<project_id>/members', methods=['GET'])
    @admin_required
    def project_members(project_id):
        return json_success(tenant_service.list_project_members(project_id))

    @app.route('/api/permissions/check', methods=['GET'])
    @admin_required
    def permission_check():
        allowed = tenant_service.check_permission(
            request.args.get('tenant_id'),
            request.args.get('user_id'),
            request.args.get('project_id'),
            request.args.get('permission')
        )
        return json_success({'allowed': allowed})

    @app.route('/api/resources', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_resources():
        return json_success(scheduler_service.list_resources())

    @app.route('/api/resources/summary', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def resources_summary():
        return json_success(scheduler_service.get_resource_summary())

    @app.route('/api/scheduler/preview', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def scheduler_preview():
        payload = parse_json_body(request)
        return json_success(scheduler_service.preview_schedule(payload))

    @app.route('/api/scheduler/policies', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_scheduler_policies():
        db = get_database()
        rows = db.fetch_all('SELECT * FROM scheduler_policies ORDER BY created_at DESC')
        from .models import SchedulerPolicy
        return json_success([SchedulerPolicy.from_row(r).to_dict() for r in rows])

    @app.route('/api/scheduler/policies', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def create_scheduler_policy():
        payload = parse_json_body(request)
        from .models import SchedulerPolicy
        policy = SchedulerPolicy(
            tenant_id=payload.get('tenant_id'),
            name=payload.get('name'),
            policy_type=payload.get('policy_type'),
            scoring_weights=payload.get('scoring_weights'),
            rules=payload.get('rules'),
            enabled=payload.get('enabled', 1),
        )
        db = get_database()
        db.insert(SchedulerPolicy.TABLE_NAME, policy.to_insert_params())
        return json_success(policy.to_dict())

    @app.route('/api/jobs/<job_id>/reschedule', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_COMPUTE)
    def job_reschedule(job_id):
        require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        try:
            result = scheduler_service.re_schedule(job_id)
            return json_success(result)
        except ValueError as e:
            return json_error('reschedule_error', str(e), 400)

    @app.route('/api/jobs/<job_id>/schedule', methods=['GET'])
    @login_required
    def job_schedule(job_id):
        job = require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        return json_success((job.get('result') or {}).get('schedule_result'))

    @app.route('/api/jobs/<job_id>/monitor', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_MONITOR)
    def job_monitor(job_id):
        job = require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        monitor_summary = (job.get('result') or {}).get('monitor_summary') or {}
        return json_success(monitor_summary)

    @app.route('/api/engines', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_engines():
        return json_success(engine_service.list_engines())

    @app.route('/api/engines/session/preview', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def engine_preview():
        payload = parse_json_body(request)
        return json_success(engine_service.preview_session(payload))

    @app.route('/api/jobs/<job_id>/engine-session', methods=['GET'])
    @login_required
    def job_engine_session(job_id):
        job = require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        return json_success((job.get('result') or {}).get('engine_session'))

    @app.route('/api/jobs/<job_id>/stream-session', methods=['GET'])
    @login_required
    def job_stream_session(job_id):
        job = require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        return json_success((job.get('result') or {}).get('stream_session'))

    @app.route('/api/assets/<asset_id>/rights', methods=['GET'])
    @login_required
    @permission_required('approve_rights')
    def asset_rights(asset_id):
        return json_success(rights_service.get_asset_rights(asset_id))

    @app.route('/api/assets/<asset_id>/rights/validate', methods=['POST'])
    @login_required
    @permission_required('approve_rights')
    def validate_asset_rights(asset_id):
        payload = parse_json_body(request)
        usage_scope = payload.get('usage_scope') or 'internal_demo'
        return json_success(rights_service.validate_asset_rights(asset_id, usage_scope, payload.get('tenant_id')))

    @app.route('/api/assets/<asset_id>/provenance', methods=['GET'])
    @login_required
    @permission_required('approve_rights')
    def asset_provenance(asset_id):
        return json_success(rights_service.list_provenance(asset_id))

    @app.route('/api/jobs/<job_id>/rights-snapshot', methods=['GET'])
    @login_required
    def job_rights_snapshot(job_id):
        job = require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        return json_success((job.get('result') or {}).get('rights_result'))

    @app.route('/api/billing/summary', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_BILLING)
    def billing_summary():
        return json_success(billing_service.get_billing_summary())

    @app.route('/api/projects/<project_id>/usage', methods=['GET'])
    @admin_required
    def project_usage(project_id):
        return json_success(billing_service.get_project_usage(project_id))

    @app.route('/api/jobs/<job_id>/billing', methods=['GET'])
    @login_required
    def job_billing(job_id):
        require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        return json_success(billing_service.get_job_billing(job_id))

    @app.route('/api/jobs/<job_id>/billing/finalize', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_BILLING)
    def job_billing_finalize(job_id):
        require_job(job_store.get(job_id), demo_mode=cfg.DEMO_MODE)
        try:
            return json_success(billing_service.finalize_billing(job_id))
        except ValueError as e:
            return json_error('billing_error', str(e), 400)

    # ── Render Job Routes ──

    @app.route('/api/render/jobs', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_render_jobs():
        tenant_id = request.args.get('tenant_id') if is_admin(g.current_user) else g.current_user.get('tenant_id')
        project_id = request.args.get('project_id')
        status = request.args.get('status')
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
        return json_success(render_service.list_render_jobs(
            tenant_id=tenant_id, project_id=project_id, status=status,
            limit=limit, offset=offset))

    @app.route('/api/render/jobs', methods=['POST'])
    @login_required
    @permission_required(PERM_SUBMIT_RENDER_JOB)
    def create_render_job():
        payload = parse_json_body(request)
        tenant_id = payload.get('tenant_id') if is_admin(g.current_user) else g.current_user.get('tenant_id')
        try:
            job = render_service.create_render_job(
                tenant_id=tenant_id,
                project_id=payload.get('project_id'),
                node_id=payload.get('node_id'),
                engine_type=payload.get('engine_type'),
                asset_id=payload.get('asset_id'),
                input_spec=payload.get('input_spec'),
                # output_dir is server-controlled; ignore client input.
                output_dir=None,
            )
            return json_success(job)
        except Exception as e:
            return json_error('create_error', str(e), 500)

    @app.route('/api/render/jobs/<job_id>', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def get_render_job_route(job_id):
        job = render_service.get_render_job(job_id)
        if not job:
            return json_error('not_found', '渲染任务不存在', 404)
        return json_success(job)

    @app.route('/api/render/jobs/<job_id>/start', methods=['POST'])
    @login_required
    @permission_required(PERM_SUBMIT_RENDER_JOB)
    def start_render_job_route(job_id):
        try:
            return json_success(render_service.start_render_job(job_id))
        except ValueError as e:
            return json_error('start_error', str(e), 400)

    @app.route('/api/render/jobs/<job_id>/cancel', methods=['POST'])
    @login_required
    @permission_required(PERM_SUBMIT_RENDER_JOB)
    def cancel_render_job_route(job_id):
        try:
            return json_success(render_service.cancel_render_job(job_id))
        except ValueError as e:
            return json_error('cancel_error', str(e), 400)

    @app.route('/api/render/jobs/<job_id>/output/<path:filename>', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def serve_render_output(job_id, filename):
        job = render_service.get_render_job(job_id)
        if not job:
            return json_error('not_found', '渲染任务不存在', 404)
        if not is_admin(g.current_user) and job.get('tenant_id') != g.current_user.get('tenant_id'):
            return json_error('forbidden', '无权访问该渲染结果', 403)
        try:
            filepath = render_service.get_render_output(job_id, filename)
            from flask import send_file
            return send_file(filepath)
        except ValueError as e:
            return json_error('not_found', str(e), 404)

    @app.route('/api/ops/events', methods=['GET'])
    @admin_required
    def ops_events():
        project_id = request.args.get('project_id')
        return json_success(ops_service.list_events(project_id=project_id, limit=50))

    # ── Monitoring Endpoints ──

    _monitoring_collector = MetricsCollector()

    @app.route('/api/monitoring/collect', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def monitoring_collect():
        payload = parse_json_body(request)
        node_id = payload.get('node_id')

        metrics = _monitoring_collector.collect()

        if node_id:
            db = get_database()
            # Verify node exists before inserting metrics
            node_row = db.fetch_one('SELECT id FROM compute_nodes WHERE id = ?', (node_id,))
            if node_row:
                sample = NodeMetricSample(
                    node_id=node_id,
                    cpu_percent=metrics.get('cpu_percent'),
                    memory_percent=metrics.get('memory_percent'),
                    gpu_percent=metrics.get('gpu_percent'),
                    gpu_memory_percent=metrics.get('gpu_memory_percent'),
                    gpu_temperature=metrics.get('gpu_temperature'),
                    disk_read_bps=metrics.get('disk_read_bps'),
                    disk_write_bps=metrics.get('disk_write_bps'),
                    network_rx_bps=metrics.get('network_rx_bps'),
                    network_tx_bps=metrics.get('network_tx_bps'),
                    latency_ms=metrics.get('latency_ms'),
                    packet_loss_percent=metrics.get('packet_loss_percent'),
                    running_tasks=metrics.get('running_tasks', 0),
                    metadata={'collected_at': metrics.get('collected_at')},
                )
                db.insert(NodeMetricSample.TABLE_NAME, sample.to_insert_params())

                # Update node heartbeat
                db.update(
                    ComputeNode.TABLE_NAME,
                    {'last_heartbeat_at': int(time.time()), 'updated_at': int(time.time())},
                    'id = ?',
                    (node_id,)
                )

        return json_success(metrics)

    @app.route('/api/monitoring/nodes/<node_id>/metrics', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def node_metrics(node_id):
        since = request.args.get('since')
        until = request.args.get('until')
        limit = min(int(request.args.get('limit', 50)), 500)

        db = get_database()
        where_clauses = ['node_id = ?']
        params = [node_id]

        if since:
            where_clauses.append('sampled_at >= ?')
            params.append(int(since))
        if until:
            where_clauses.append('sampled_at <= ?')
            params.append(int(until))

        where_sql = ' AND '.join(where_clauses)
        rows = db.fetch_all(
            'SELECT * FROM node_metric_samples WHERE {0} ORDER BY sampled_at DESC LIMIT {1}'.format(where_sql, limit),
            tuple(params)
        )
        samples = [NodeMetricSample.from_row(row).to_dict() for row in rows]

        return json_success({
            'node_id': node_id,
            'samples': samples,
            'count': len(samples),
        })

    @app.route('/api/monitoring/nodes/<node_id>/health-check', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def node_health_check(node_id):
        db = get_database()
        node_row = db.fetch_one('SELECT * FROM compute_nodes WHERE id = ?', (node_id,))
        if not node_row:
            return json_error('node_not_found', '节点不存在', 404)

        start = time.time()
        try:
            metrics = _monitoring_collector.collect()
            latency_ms = int((time.time() - start) * 1000)
            status = HealthCheck.STATUS_OK
            error_message = None

            # If node has GPU but no GPU metrics, flag as warning
            node = ComputeNode.from_row(node_row)
            if node and node.gpu_count > 0 and metrics.get('gpu_percent') is None:
                status = HealthCheck.STATUS_WARNING
                error_message = 'GPU metrics unavailable on expected GPU node'
        except Exception as e:
            status = HealthCheck.STATUS_ERROR
            error_message = str(e)[:500]
            latency_ms = int((time.time() - start) * 1000)

        hc = HealthCheck(
            target_type='compute_node',
            target_id=node_id,
            status=status,
            latency_ms=latency_ms,
            error_message=error_message,
        )
        db.insert(HealthCheck.TABLE_NAME, hc.to_insert_params())

        # Record ops event
        user = __import__('flask').session.get('user', {})
        ops_service.record_event(
            tenant_id=node.to_dict().get('tenant_id') if node else None,
            project_id=None,
            job_id=None,
            event_type=EVENT_HEALTH_CHECK,
            severity=SEVERITY_ERROR if status == HealthCheck.STATUS_ERROR else SEVERITY_INFO,
            message='Health check for node {0}: {1}'.format(node_id, status),
            metadata={'latency_ms': latency_ms, 'error': error_message},
        )

        return json_success(hc.to_dict())

    # ── Compute Overview ──

    @app.route('/api/compute/overview', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def compute_overview():
        """Aggregated compute overview."""
        try:
            db = get_database()
            # Merge resources, billing, render, ops data
            resources_summary = scheduler_service.get_resource_summary()
            billing_summary = billing_service.get_billing_summary()

            # Count recent alerts
            from .models import Alert
            alert_rows = db.fetch_all("SELECT status, severity, COUNT(*) as cnt FROM alerts GROUP BY status, severity")

            # Get recent render jobs
            render_rows = db.fetch_all(
                "SELECT status, COUNT(*) as cnt FROM render_jobs GROUP BY status"
            )

            overview = {
                'resources': resources_summary,
                'billing': {'summary': billing_summary} if billing_summary else {},
                'alerts': [dict(r) for r in alert_rows],
                'render_jobs': [dict(r) for r in render_rows],
            }
            return json_success(overview)
        except Exception as e:
            logger.error("Compute overview error: %s", str(e))
            return json_error('compute_overview_error', str(e), status_code=500)

    # ── Monitoring Routes ──

    @app.route('/api/monitoring/nodes', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def monitoring_nodes():
        """List compute nodes with latest metrics."""
        try:
            db = get_database()
            node_rows = db.fetch_all(
                "SELECT cn.*, "
                "(SELECT nms.gpu_percent FROM node_metric_samples nms "
                " WHERE nms.node_id = cn.id ORDER BY nms.sampled_at DESC LIMIT 1) as latest_gpu_percent, "
                "(SELECT nms.cpu_percent FROM node_metric_samples nms "
                " WHERE nms.node_id = cn.id ORDER BY nms.sampled_at DESC LIMIT 1) as latest_cpu_percent, "
                "(SELECT nms.memory_percent FROM node_metric_samples nms "
                " WHERE nms.node_id = cn.id ORDER BY nms.sampled_at DESC LIMIT 1) as latest_memory_percent, "
                "(SELECT nms.gpu_temperature FROM node_metric_samples nms "
                " WHERE nms.node_id = cn.id ORDER BY nms.sampled_at DESC LIMIT 1) as latest_gpu_temperature, "
                "(SELECT nms.sampled_at FROM node_metric_samples nms "
                " WHERE nms.node_id = cn.id ORDER BY nms.sampled_at DESC LIMIT 1) as latest_sample_at "
                "FROM compute_nodes cn ORDER BY cn.node_name"
            )
            nodes = []
            for row in node_rows:
                d = dict(row)
                if d.get('metadata'):
                    try:
                        d['metadata'] = json.loads(d['metadata'])
                    except Exception:
                        pass
                # Calculate heartbeat age
                if d.get('last_heartbeat_at'):
                    d['heartbeat_age_s'] = int(time.time()) - d['last_heartbeat_at']
                else:
                    d['heartbeat_age_s'] = None
                nodes.append(d)
            return json_success({'nodes': nodes, 'total': len(nodes)})
        except Exception as e:
            logger.error("Monitoring nodes error: %s", str(e))
            return json_error('monitoring_nodes_error', str(e), status_code=500)

    @app.route('/api/monitoring/links', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def monitoring_links():
        """Get current link probe results."""
        try:
            from .link_probe import LinkProbe
            probe = LinkProbe()
            results = probe.probe_all(cfg.MONITOR_TARGETS)
            stats = probe.get_stats()
            return json_success({'links': results, 'stats': stats})
        except Exception as e:
            logger.error("Monitoring links error: %s", str(e))
            return json_error('monitoring_links_error', str(e), status_code=500)

    @app.route('/api/monitoring/samples', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def monitoring_samples():
        """Get recent metric samples time-series."""
        try:
            db = get_database()
            limit = int(request.args.get('limit', 20))
            node_id = request.args.get('node_id')

            if node_id:
                rows = db.fetch_all(
                    "SELECT * FROM node_metric_samples WHERE node_id = ? "
                    "ORDER BY sampled_at DESC LIMIT ?",
                    (node_id, limit)
                )
            else:
                rows = db.fetch_all(
                    "SELECT * FROM node_metric_samples "
                    "ORDER BY sampled_at DESC LIMIT ?",
                    (limit,)
                )
            samples = []
            for row in rows:
                d = dict(row)
                if d.get('metadata'):
                    try:
                        d['metadata'] = json.loads(d['metadata'])
                    except Exception:
                        pass
                samples.append(d)
            return json_success({'samples': list(reversed(samples)), 'total': len(samples)})
        except Exception as e:
            logger.error("Monitoring samples error: %s", str(e))
            return json_error('monitoring_samples_error', str(e), status_code=500)

    @app.route('/api/monitoring/storage', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def monitoring_storage():
        """Get storage targets usage."""
        try:
            from .storage_monitor import StorageMonitor
            monitor = StorageMonitor(cfg.STORAGE_TARGETS)
            data = monitor.collect()
            return json_success(data)
        except Exception as e:
            logger.error("Monitoring storage error: %s", str(e))
            return json_error('monitoring_storage_error', str(e), status_code=500)

    # ── Alert Routes ──

    @app.route('/api/alerts', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_alerts():
        """List alerts with pagination and filters."""
        try:
            status = request.args.get('status')
            severity = request.args.get('severity')
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))

            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            alerts_list, total = alert_svc.list_alerts(
                status=status, severity=severity, limit=limit, offset=offset
            )
            return json_success({
                'items': alerts_list,
                'total': total,
                'limit': limit,
                'offset': offset,
            })
        except Exception as e:
            logger.error("List alerts error: %s", str(e))
            return json_error('alerts_list_error', str(e), status_code=500)

    @app.route('/api/alerts/<alert_id>', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def get_alert_detail(alert_id):
        """Get alert detail with event history."""
        try:
            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            alert = alert_svc.get_alert_detail(alert_id)
            if not alert:
                return json_error('alert_not_found', '\u544a\u8b66\u4e0d\u5b58\u5728', status_code=404)
            return json_success(alert)
        except Exception as e:
            logger.error("Get alert detail error: %s", str(e))
            return json_error('alert_detail_error', str(e), status_code=500)

    @app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def acknowledge_alert(alert_id):
        """Acknowledge an alert."""
        try:
            user = session.get('user', {})
            user_id = user.get('id', 'anonymous')

            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            result = alert_svc.acknowledge_alert(alert_id, user_id)
            if not result:
                return json_error('alert_not_found', '\u544a\u8b66\u4e0d\u5b58\u5728', status_code=404)
            return json_success(result, message='\u544a\u8b66\u5df2\u786e\u8ba4')
        except Exception as e:
            logger.error("Acknowledge alert error: %s", str(e))
            return json_error('alert_acknowledge_error', str(e), status_code=500)

    @app.route('/api/alerts/<alert_id>/assign', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_COMPUTE)
    def assign_alert(alert_id):
        """Assign an alert to the current user."""
        try:
            user = session.get('user', {})
            user_id = user.get('id', 'anonymous')

            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            result = alert_svc.assign_alert(alert_id, user_id)
            if not result:
                return json_error('alert_not_found', '\u544a\u8b66\u4e0d\u5b58\u5728', status_code=404)
            return json_success(result, message='\u544a\u8b66\u5df2\u5206\u914d')
        except Exception as e:
            logger.error("Assign alert error: %s", str(e))
            return json_error('alert_assign_error', str(e), status_code=500)

    @app.route('/api/alerts/<alert_id>/close', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_COMPUTE)
    def close_alert(alert_id):
        """Close an alert."""
        try:
            user = session.get('user', {})
            user_id = user.get('id', 'anonymous')
            payload = request.get_json(silent=True) or {}
            notes = payload.get('notes')

            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            result = alert_svc.close_alert(alert_id, user_id, notes)
            if not result:
                return json_error('alert_not_found', '\u544a\u8b66\u4e0d\u5b58\u5728', status_code=404)
            return json_success(result, message='\u544a\u8b66\u5df2\u5173\u95ed')
        except Exception as e:
            logger.error("Close alert error: %s", str(e))
            return json_error('alert_close_error', str(e), status_code=500)

    @app.route('/api/alerts/<alert_id>/comment', methods=['POST'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def add_alert_comment(alert_id):
        """Add a comment to an alert."""
        try:
            user = session.get('user', {})
            user_id = user.get('id', 'anonymous')
            payload = request.get_json(silent=True) or {}
            message = payload.get('message', '')

            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            result = alert_svc.add_comment(alert_id, user_id, message)
            if not result:
                return json_error('alert_not_found', '\u544a\u8b66\u4e0d\u5b58\u5728', status_code=404)
            return json_success(result, message='\u8bc4\u8bba\u5df2\u6dfb\u52a0')
        except Exception as e:
            logger.error("Add alert comment error: %s", str(e))
            return json_error('alert_comment_error', str(e), status_code=500)

    @app.route('/api/alerts/rules', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_alert_rules():
        """List alert rules."""
        try:
            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            rules = alert_svc.get_rules(enabled_only=False)
            return json_success({'items': rules, 'total': len(rules)})
        except Exception as e:
            logger.error("List alert rules error: %s", str(e))
            return json_error('alert_rules_error', str(e), status_code=500)

    @app.route('/api/alerts/rules', methods=['POST'])
    @login_required
    @permission_required(PERM_MANAGE_COMPUTE)
    def create_alert_rule():
        """Create or update an alert rule."""
        try:
            payload = request.get_json(silent=True) or {}
            from .alert_service import get_alert_service
            alert_svc = get_alert_service(cfg.DATA_DIR)
            rule = alert_svc.create_rule(payload)
            return json_success(rule, message='\u544a\u8b66\u89c4\u5219\u5df2\u521b\u5efa', status_code=201)
        except Exception as e:
            logger.error("Create alert rule error: %s", str(e))
            return json_error('alert_rule_create_error', str(e), status_code=500)

    # ── Switch Events Route ──

    @app.route('/api/switch-events', methods=['GET'])
    @login_required
    @permission_required(PERM_VIEW_COMPUTE)
    def list_switch_events():
        """List task attempt switches."""
        try:
            db = get_database()
            limit = int(request.args.get('limit', 50))
            rows = db.fetch_all(
                "SELECT * FROM task_attempts ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            attempts = []
            for row in rows:
                d = dict(row)
                if d.get('metadata'):
                    try:
                        d['metadata'] = json.loads(d['metadata'])
                    except Exception:
                        pass
                attempts.append(d)
            return json_success({'items': attempts, 'total': len(attempts)})
        except Exception as e:
            logger.error("List switch events error: %s", str(e))
            return json_error('switch_events_error', str(e), status_code=500)
