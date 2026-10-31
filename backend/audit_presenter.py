# -*- coding: utf-8 -*-
"""Read-only presentation layer for admin audit events.

The raw ``ops_events`` table intentionally stays immutable.  This module turns
its technical fields (event codes, ``success``/``failed`` strings, UUIDs) into
business-facing Chinese labels and resolves the related user/task/project names
with a bounded number of batched queries.

Nothing in this module writes to the database.
"""
from __future__ import absolute_import

import json
import re

MAX_IN_QUERY = 200
MAX_SUMMARY_LENGTH = 300
MAX_DETAIL_STRING = 2000

_SENSITIVE_KEY_PATTERNS = (
    'password', 'secret', 'api_key', 'apikey', 'access_key', 'private_key',
    'credential', 'token', 'authorization', 'cookie', 'session',
)

# Event labels cover both the audit events emitted today and the constants in
# backend.ops_service (some are reserved for future emitters).  Unknown codes
# fall back to "其他系统事件" in the presenter.
EVENT_LABELS = {
    # Authentication / profile
    'login': '用户登录',
    'login_failed': '登录失败',
    'logout': '用户退出登录',
    'user_register': '用户注册',
    'profile_update': '修改个人资料',
    'password_change': '修改账户密码',
    'avatar_update': '更新头像',
    'avatar_delete': '删除头像',
    # Admin user management
    'admin_user_update': '管理员修改用户资料',
    'admin_role_change': '修改用户权限',
    'admin_status_change': '修改账户状态',
    'admin_revoke_sessions': '强制用户重新登录',
    # Generation / jobs
    'generation_submit': '提交 AI 生成任务',
    'generation_succeeded': 'AI 生成任务完成',
    'generation_failed': 'AI 生成任务失败',
    'generation_cancel': '取消生成任务',
    'generation_delete': '删除生成记录',
    'generation_retry': '重试生成任务',
    'image_submit': '提交图片生成',
    'video_submit': '提交视频生成',
    'task_cancel': '取消生成任务',
    'task_retry': '重试生成任务',
    'job_create': '创建生成作业',
    # Assets / provider credentials
    'asset_update': '更新素材',
    'asset_delete': '删除素材',
    'provider_credential_update': '更新 AI 服务配置',
    'provider_credential_delete': '删除 AI 服务配置',
    'provider_credential_test': '测试 AI 服务连接',
    'provider_credential_test_generation': 'AI 服务真实生成测试',
    # Creative projects / permissions
    'project_create': '创建创意项目',
    'project_delete': '删除创意项目',
    'storyboard_generate': '生成项目分镜',
    'export_download': '下载项目导出文件',
    'permission_change': '修改用户权限',
    'permission_grant': '授予权限',
    'permission_revoke': '撤销权限',
    # Compute / operations
    'rights_validated': '版权校验完成',
    'resource_scheduling': '资源调度完成',
    'resource_re_scheduled': '资源重新调度',
    'render_started': '渲染任务开始',
    'render_progress': '渲染任务进行中',
    'render_succeeded': '渲染任务成功',
    'render_failed': '渲染任务失败',
    'render_cancelled': '渲染任务取消',
    'health_check': '健康检查',
    'schedule_allocation': '调度分配',
    'schedule_reschedule': '调度重新编排',
    'provider_sync': '服务商同步',
    'cloud_sync': '同步云平台资源',
    'resource_allocate': '分配计算资源',
    'resource_reassign': '资源重新分配',
    'node_online': '节点上线',
    'node_offline': '节点离线',
    'node_error': '节点异常',
    'node_maintenance': '节点维护',
    'alert_acknowledge': '告警确认',
    'alert_close': '告警关闭',
    # Volcengine admin sync (added by this feature)
    'admin_ark_sync': '管理员同步火山方舟用量与账单',
    'volcengine_sync': '火山方舟数据同步',
}

RESULT_LABELS = {
    'success': '成功',
    'succeeded': '成功',
    'failed': '失败',
    'failure': '失败',
    'error': '错误',
    'warning': '警告',
    'pending': '处理中',
    'accepted': '已接受',
    'inconclusive': '结果不确定',
    'cancelled': '已取消',
    'canceled': '已取消',
    'completed': '已完成',
}

TASK_TYPE_LABELS = {
    'image': 'AI 图片生成任务',
    'video': 'AI 视频生成任务',
    'storyboard': '创意分析任务',
    'tts': 'TTS 配音任务',
    'compose': '视频合成任务',
    'refine': '视频精修任务',
    'export': '视频导出任务',
}

PROVIDER_LABELS = {
    'ark_seedream': '火山方舟 Seedream',
    'ark_seedance': '火山方舟 Seedance',
    'atlas_seedance': 'Atlas Seedance',
    'openai_image': 'OpenAI 图片',
    'comfyui': 'ComfyUI 本地',
    'luma': 'Luma',
    'llm': 'LLM',
    'seedance': 'Seedance',
}

ASSET_TYPE_LABELS = {
    'image': '图片',
    'video': '视频',
    'model': '3D 模型',
    'audio': '音频',
    'prompt': '提示词',
    'document': '文档',
}

SEVERITY_LABELS = {
    'info': '信息',
    'warning': '警告',
    'error': '错误',
}

# These are platform/operations events whose ``message`` is human text rather
# than an audit result.  They are still presented, but the summary comes from
# the original message instead of being assembled from actor + event label.
OPS_EVENT_TYPES = set([
    'rights_validated', 'resource_scheduling', 'resource_re_scheduled',
    'render_started', 'render_progress', 'render_succeeded', 'render_failed',
    'render_cancelled', 'health_check', 'schedule_allocation',
    'schedule_reschedule', 'provider_sync', 'cloud_sync', 'resource_allocate',
    'resource_reassign', 'node_online', 'node_offline', 'node_error',
    'node_maintenance', 'alert_acknowledge', 'alert_close',
])

KNOWN_RESULT_VALUES = set(RESULT_LABELS.keys())


def _clean_text(value, limit=MAX_DETAIL_STRING):
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    value = value.replace('\r', ' ').replace('\n', ' ')
    value = re.sub(r'[\x00-\x1f\x7f]', ' ', value)
    return value.strip()[:limit]


def _shorten(value, limit=MAX_SUMMARY_LENGTH):
    text = _clean_text(value, limit + 1)
    if len(text) > limit:
        return text[:limit - 1] + '…'
    return text


def mask_identifier(value):
    """Mask an internal UUID for the detail dialog."""
    text = _clean_text(value, 128)
    if not text:
        return None
    if len(text) <= 12:
        return text
    return text[:8] + '…' + text[-4:]


def display_user(username, nickname):
    username = _clean_text(username, 80)
    nickname = _clean_text(nickname, 80)
    if nickname and nickname != username:
        if username:
            return '{0}（{1}）'.format(nickname, username)
        return nickname
    return username or nickname or ''


def sanitize_metadata(value, depth=0):
    """Recursively redact secrets and bound the payload size.

    Historical events may predate the AuditService sanitiser, so the presenter
    sanitises again on read.
    """
    if depth > 6:
        return '[TRUNCATED]'
    if isinstance(value, dict):
        sanitized = {}
        for key, item in list(value.items())[:100]:
            key_text = str(key)
            lowered = key_text.lower()
            if any(pattern in lowered for pattern in _SENSITIVE_KEY_PATTERNS):
                sanitized[key_text] = '[REDACTED]'
            else:
                sanitized[key_text] = sanitize_metadata(item, depth + 1)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize_metadata(item, depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value[:MAX_DETAIL_STRING]
    return value


def build_actor_snapshot(db, user_id):
    """Return a safe display snapshot for a real authenticated user.

    Called while writing new audit records so that later nickname changes or
    account deletion do not erase the original identity clue.
    """
    if not user_id:
        return None
    try:
        row = db.fetch_one(
            'SELECT username, nickname FROM auth_users WHERE id = ?',
            (user_id,),
        )
    except Exception:
        return None
    if not row:
        return None
    display = display_user(row.get('username'), row.get('nickname'))
    return display or None


def filter_options():
    return {
        'event_types': [
            {'value': code, 'label': label}
            for code, label in EVENT_LABELS.items()
        ],
        'results': [
            {'value': code, 'label': label}
            for code, label in RESULT_LABELS.items()
        ],
    }


def _event_dict(row):
    """Normalise a sqlite3.Row or dict into a plain event dict."""
    if isinstance(row, dict):
        data = dict(row)
        metadata = data.get('metadata')
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (TypeError, ValueError):
                metadata = None
        data['metadata'] = metadata if isinstance(metadata, dict) else {}
        return data
    # sqlite3.Row
    try:
        data = {key: row[key] for key in row.keys()}
    except Exception:
        data = dict(row)
    metadata = data.get('metadata')
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            metadata = None
    data['metadata'] = metadata if isinstance(metadata, dict) else {}
    return data


def _details(event):
    metadata = event.get('metadata') or {}
    details = metadata.get('details')
    return details if isinstance(details, dict) else {}


def _metadata_text(event, key, default=None):
    metadata = event.get('metadata') or {}
    value = metadata.get(key)
    if value is None:
        value = _details(event).get(key)
    return value if value is not None else default


def _target_identity(event):
    """Return (target_type, target_id) using only explicit protocol fields."""
    metadata = event.get('metadata') or {}
    target_type = metadata.get('target_type')
    target_id = metadata.get('target_id')
    if not target_type and not target_id and event.get('job_id'):
        # Legacy platform events store the job id in a dedicated column.
        return 'job', event.get('job_id')
    return target_type, target_id


def _chunks(values, size=MAX_IN_QUERY):
    values = list(values)
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _placeholders(values):
    return ','.join('?' for _ in values)


def _fetch_maps(db, ids):
    maps = {
        'users': {},
        'tasks': {},
        'creative_projects': {},
        'projects': {},
        'assets': {},
        'jobs': {},
        'render_jobs': {},
    }

    user_ids = list(ids.get('users') or [])
    if user_ids:
        for chunk in _chunks(user_ids):
            rows = db.fetch_all(
                'SELECT id, username, nickname FROM auth_users WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['users'][row.get('id')] = row

    task_ids = list(ids.get('tasks') or [])
    if task_ids:
        for chunk in _chunks(task_ids):
            rows = db.fetch_all(
                'SELECT id, task_type, status, provider, model_id, creative_project_id '
                'FROM generation_tasks WHERE id IN ({0})'.format(_placeholders(chunk)),
                tuple(chunk),
            )
            for row in rows:
                maps['tasks'][row.get('id')] = row

    creative_ids = set(ids.get('creative_projects') or [])
    for task in maps['tasks'].values():
        if task.get('creative_project_id'):
            creative_ids.add(task['creative_project_id'])
    if creative_ids:
        for chunk in _chunks(creative_ids):
            rows = db.fetch_all(
                'SELECT id, name FROM creative_projects WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['creative_projects'][row.get('id')] = row

    asset_ids = list(ids.get('assets') or [])
    if asset_ids:
        for chunk in _chunks(asset_ids):
            rows = db.fetch_all(
                'SELECT id, name, asset_type FROM assets WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['assets'][row.get('id')] = row

    job_ids = list(ids.get('jobs') or [])
    if job_ids:
        for chunk in _chunks(job_ids):
            rows = db.fetch_all(
                'SELECT id, status, stage FROM job_history WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['jobs'][row.get('id')] = row

    render_ids = list(ids.get('render_jobs') or [])
    if render_ids:
        for chunk in _chunks(render_ids):
            rows = db.fetch_all(
                'SELECT id, status, project_id FROM render_jobs WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['render_jobs'][row.get('id')] = row

    project_ids = set(ids.get('projects') or [])
    for render_job in maps['render_jobs'].values():
        if render_job.get('project_id'):
            project_ids.add(render_job['project_id'])
    if project_ids:
        for chunk in _chunks(project_ids):
            rows = db.fetch_all(
                'SELECT id, name FROM projects WHERE id IN ({0})'.format(
                    _placeholders(chunk)
                ),
                tuple(chunk),
            )
            for row in rows:
                maps['projects'][row.get('id')] = row

    return maps


def _collect_ids(events):
    ids = {
        'users': set(),
        'tasks': set(),
        'creative_projects': set(),
        'projects': set(),
        'assets': set(),
        'jobs': set(),
        'render_jobs': set(),
    }
    for event in events:
        actor_id = event.get('actor_user_id')
        metadata = event.get('metadata') or {}
        if not actor_id and metadata.get('user_id'):
            actor_id = metadata.get('user_id')
        if actor_id:
            ids['users'].add(actor_id)

        target_type, target_id = _target_identity(event)
        if not target_type or not target_id:
            continue
        if target_type == 'user':
            ids['users'].add(target_id)
        elif target_type == 'generation_task':
            ids['tasks'].add(target_id)
        elif target_type == 'project':
            ids['creative_projects'].add(target_id)
            ids['projects'].add(target_id)
        elif target_type == 'asset':
            ids['assets'].add(target_id)
        elif target_type in ('job', 'job_history'):
            ids['jobs'].add(target_id)
        elif target_type == 'render_job':
            ids['render_jobs'].add(target_id)
        # provider_credential target ids are provider codes, not UUIDs.
    return ids


def _resolve_actor(event, maps):
    actor_id = event.get('actor_user_id')
    metadata = event.get('metadata') or {}
    if not actor_id and metadata.get('user_id'):
        actor_id = metadata.get('user_id')
    details = _details(event)
    snapshot = details.get('actor_display') if isinstance(details, dict) else None

    user = maps['users'].get(actor_id) if actor_id else None
    if user:
        return display_user(user.get('username'), user.get('nickname')) or '用户'
    if actor_id and snapshot:
        return _clean_text(snapshot, 120)
    if actor_id:
        return '已删除用户'
    if snapshot:
        return _clean_text(snapshot, 120)
    if event.get('event_type') == 'login_failed':
        username = details.get('username') or metadata.get('username')
        if username:
            return '未认证用户（{0}）'.format(_clean_text(username, 80))
    return '系统任务'


def _task_display(task, maps):
    task_type = TASK_TYPE_LABELS.get(task.get('task_type'), 'AI 生成任务')
    provider = PROVIDER_LABELS.get(task.get('provider'), task.get('provider') or '')
    model_id = task.get('model_id') or ''
    project_name = ''
    if task.get('creative_project_id'):
        project = maps['creative_projects'].get(task.get('creative_project_id'))
        if project:
            project_name = project.get('name') or ''
    parts = [task_type]
    if provider:
        parts.append(provider)
    if model_id:
        parts.append(model_id)
    if project_name:
        parts.append(project_name)
    return ' · '.join(parts)


def _target_display(event, maps):
    target_type, target_id = _target_identity(event)
    details = _details(event)
    if not target_type or not target_id:
        return '—'

    if target_type == 'user':
        user = maps['users'].get(target_id)
        if user:
            return display_user(user.get('username'), user.get('nickname')) or '用户'
        return '已删除用户'

    if target_type == 'generation_task':
        task = maps['tasks'].get(target_id)
        if task:
            return _task_display(task, maps)
        snapshot_type = details.get('task_type')
        if snapshot_type:
            parts = [TASK_TYPE_LABELS.get(snapshot_type, 'AI 生成任务')]
            provider = details.get('provider')
            if provider:
                parts.append(PROVIDER_LABELS.get(provider, provider))
            model_id = details.get('model_id')
            if model_id:
                parts.append(str(model_id))
            return ' · '.join(parts) + '（原始任务已删除）'
        return '原始目标已删除'

    if target_type == 'project':
        project = maps['creative_projects'].get(target_id) or maps['projects'].get(target_id)
        if project:
            return project.get('name') or '项目'
        return '原始项目已删除'

    if target_type == 'asset':
        asset = maps['assets'].get(target_id)
        if asset:
            label = ASSET_TYPE_LABELS.get(asset.get('asset_type'), asset.get('asset_type') or '素材')
            return '{0} · {1}'.format(asset.get('name') or '素材', label)
        return '原始素材已删除'

    if target_type in ('job', 'job_history'):
        job = maps['jobs'].get(target_id)
        short_id = _clean_text(target_id, 8)
        if job:
            status = job.get('status') or job.get('stage') or '已记录'
            return '生成作业 {0}（{1}）'.format(short_id, status)
        return '生成作业 {0}'.format(short_id)

    if target_type == 'render_job':
        job = maps['render_jobs'].get(target_id)
        short_id = _clean_text(target_id, 8)
        if not job:
            return '渲染作业 {0}'.format(short_id)
        project_name = ''
        if job.get('project_id'):
            project = maps['projects'].get(job.get('project_id'))
            if project:
                project_name = project.get('name') or ''
        text = '渲染作业 {0}（{1}）'.format(short_id, job.get('status') or '已记录')
        return text + (' · ' + project_name if project_name else '')

    if target_type == 'provider_credential':
        return PROVIDER_LABELS.get(target_id, _clean_text(target_id, 80))

    if target_type == 'volcengine_sync':
        return {
            'ark_usage': '火山方舟官方用量同步',
            'ark_billing': '火山引擎官方账单同步',
            'ark_balance': '火山引擎官方余额同步',
        }.get(target_id, '火山引擎数据同步')

    # Do not guess a target type from the UUID shape.
    return '—'


def _result_for(event):
    message = _clean_text(event.get('message'), 80)
    if message.lower() in KNOWN_RESULT_VALUES:
        return message.lower(), RESULT_LABELS.get(message.lower(), '已记录')
    severity = _clean_text(event.get('severity') or 'info', 20)
    if event.get('event_type') in OPS_EVENT_TYPES:
        return severity, SEVERITY_LABELS.get(severity, '已记录')
    if message:
        return message, '已记录'
    return severity, SEVERITY_LABELS.get(severity, '已记录')


def _summary(event, actor_display, event_label, target_display):
    message = _clean_text(event.get('message'), MAX_SUMMARY_LENGTH)
    if event.get('event_type') in OPS_EVENT_TYPES:
        return message or event_label
    if event.get('event_type') == 'login_failed':
        return '{0}{1}'.format(actor_display, event_label)
    if not event.get('actor_user_id') and not (event.get('metadata') or {}).get('user_id'):
        # No identity clue: this is a system task, but keep the original
        # message when it carries a meaningful business description.
        if message and message.lower() not in KNOWN_RESULT_VALUES:
            return message
        return '系统任务{0}'.format(event_label)
    text = '{0}{1}'.format(actor_display, event_label)
    if target_display and target_display != '—':
        text += '，目标：{0}'.format(target_display)
    return _shorten(text)


def _detail_error(event):
    details = _details(event)
    error_code = details.get('error_code') or details.get('provider_code')
    error_message = details.get('error_message') or details.get('message')
    if not error_code and not error_message:
        return None
    return {
        'code': _clean_text(error_code, 120) or None,
        'message': _clean_text(error_message, 500) or None,
    }


def _detail_model(event, maps):
    target_type, target_id = _target_identity(event)
    task = maps['tasks'].get(target_id) if target_type == 'generation_task' else None
    details = _details(event)
    if task:
        return {
            'provider': task.get('provider'),
            'model_id': task.get('model_id'),
        }
    if details.get('provider') or details.get('model_id'):
        return {
            'provider': details.get('provider'),
            'model_id': details.get('model_id'),
        }
    return None


def _detail_project(event, maps):
    target_type, target_id = _target_identity(event)
    if target_type == 'generation_task':
        task = maps['tasks'].get(target_id)
        if task and task.get('creative_project_id'):
            project = maps['creative_projects'].get(task['creative_project_id'])
            if project:
                return {'id': project.get('id'), 'name': project.get('name')}
    if target_type == 'project':
        project = maps['creative_projects'].get(target_id) or maps['projects'].get(target_id)
        if project:
            return {'id': project.get('id'), 'name': project.get('name')}
    return None


def _build_item(event, maps, include_detail=False):
    metadata = event.get('metadata') if isinstance(event.get('metadata'), dict) else {}
    details = _details(event)
    actor_id = event.get('actor_user_id') or metadata.get('user_id')
    target_type, target_id = _target_identity(event)
    actor_display = _resolve_actor(event, maps)
    target_display = _target_display(event, maps)
    event_label = EVENT_LABELS.get(event.get('event_type'), '其他系统事件')
    result, result_label = _result_for(event)

    item = {
        'id': event.get('id'),
        'tenant_id': event.get('tenant_id'),
        'project_id': event.get('project_id'),
        'job_id': event.get('job_id'),
        'event_type': event.get('event_type'),
        'event_label': event_label,
        'result': result,
        'result_label': result_label,
        'severity': event.get('severity'),
        'message': event.get('message'),
        'metadata': sanitize_metadata(metadata),
        'actor_user_id': actor_id,
        'actor_display': actor_display,
        'actor_display_snapshot': _clean_text(details.get('actor_display'), 120) or None,
        'target_type': target_type,
        'target_id': target_id,
        'target_display': target_display,
        'summary': _summary(event, actor_display, event_label, target_display),
        'request_id': event.get('request_id') or metadata.get('request_id'),
        'created_at': event.get('created_at'),
        'updated_at': event.get('updated_at'),
    }

    if include_detail:
        actor_is_deleted = bool(actor_id) and actor_id not in maps['users']
        item['detail'] = {
            'event_raw_code': event.get('event_type'),
            'actor_display_snapshot': item['actor_display_snapshot'],
            'raw_ids': {
                'event_id': event.get('id'),
                'actor_user_id': mask_identifier(actor_id) if actor_is_deleted else actor_id,
                'target_id': target_id,
                'project_id': event.get('project_id'),
                'job_id': event.get('job_id'),
                'request_id': item['request_id'],
            },
            'model': _detail_model(event, maps),
            'project': _detail_project(event, maps),
            'error': _detail_error(event),
            'sanitized_metadata': sanitize_metadata(metadata),
        }
    return item


def present_events(db, rows):
    """Present a list of raw ops_events rows with bounded batched lookups."""
    events = [_event_dict(row) for row in rows]
    maps = _fetch_maps(db, _collect_ids(events))
    return [_build_item(event, maps) for event in events]


def fetch_event(db, event_id):
    row = db.fetch_one('SELECT * FROM ops_events WHERE id = ?', (event_id,))
    return _event_dict(row) if row else None


def present_event_detail(db, event):
    if not event:
        return None
    event = _event_dict(event)
    maps = _fetch_maps(db, _collect_ids([event]))
    return _build_item(event, maps, include_detail=True)


def actor_filter_clause():
    """SQL fragment + parameter count for actor id/username/nickname filters."""
    return (
        '(actor_user_id = ? OR EXISTS ('
        'SELECT 1 FROM auth_users u WHERE u.id = ops_events.actor_user_id '
        'AND (u.username = ? OR u.nickname = ?)))',
        3,
    )
