# -*- coding: utf-8 -*-
"""Official Ark usage sync and AIGV-local usage statistics."""
from __future__ import absolute_import

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from ..database import get_database
from .client import VolcengineAPIError
from .store import (
    USAGE_SYNC_KEY,
    claim_sync,
    finish_sync,
    get_all_sync_statuses,
    get_sync_status,
    now,
    upsert_bill_snapshot,
    upsert_usage_snapshot,
)
from .usage_client import VolcengineUsageClient

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))
OFFICIAL_SOURCE = 'volcengine_usage'
LOCAL_SOURCE = 'aigv_local'


def _beijing_today():
    return datetime.now(BEIJING_TZ).date()


def _day_start(value=None):
    """Return the epoch second of Beijing midnight for a date/date string."""
    if value is None:
        value = _beijing_today()
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d').date()
    parsed = datetime(value.year, value.month, value.day, tzinfo=BEIJING_TZ)
    return int(parsed.timestamp())


def _date_range(days):
    end = _beijing_today()
    start = end - timedelta(days=max(1, int(days or 1)) - 1)
    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def _parse_date_arg(value, field):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise VolcengineAPIError(
            'invalid_param', '{0} 格式应为 YYYY-MM-DD'.format(field)
        )


def _range_bounds(days, start_date=None, end_date=None):
    """Return (since_epoch, until_epoch, start_label, end_label)."""
    today = _beijing_today()
    if start_date or end_date:
        start = _parse_date_arg(start_date, 'start_date') if start_date else (
            today - timedelta(days=max(1, int(days or 1)) - 1)
        )
        end = _parse_date_arg(end_date, 'end_date') if end_date else today
        if start > end:
            raise VolcengineAPIError('invalid_param', 'start_date 不能晚于 end_date')
    else:
        end = today
        start = end - timedelta(days=max(1, int(days or 1)) - 1)
    return (
        _day_start(start), _day_start(end) + 86400,
        start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'),
    )


def _as_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _row_value(row, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _parse_metadata(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _period_info(row):
    day = _row_value(row, 'Day', 'day')
    hour = _row_value(row, 'Hour', 'hour')
    label = str(day or '')
    period_start = None
    if day:
        try:
            parsed = datetime.strptime(str(day)[:10], '%Y-%m-%d')
            hour_value = 0
            if hour is not None:
                try:
                    hour_value = int(str(hour).split(':')[0])
                except (TypeError, ValueError):
                    hour_value = 0
                label = '{0} {1}'.format(parsed.strftime('%Y-%m-%d'), str(hour))
            parsed = parsed.replace(hour=max(0, min(23, hour_value)), tzinfo=BEIJING_TZ)
            period_start = int(parsed.timestamp())
        except (TypeError, ValueError):
            period_start = None
    return label or None, period_start


def _snapshot_key(row, interval, start_date=None, end_date=None):
    # The key must not include the sync window: a 31-day sync and a 7-day sync
    # overlap, and the same period dimension must update, not duplicate.
    dimensions = [
        interval,
        _row_value(row, 'AccountID', 'account_id'),
        _row_value(row, 'ApikeyID', 'APIKeyID', 'ApiKeyID', 'apikey_id'),
        _row_value(row, 'ModelName', 'model_name'),
        _row_value(row, 'ModelVersion', 'model_version'),
        _row_value(row, 'ModelEndpoint', 'model_endpoint'),
        _row_value(row, 'BillingStatus', 'billing_status'),
        _row_value(row, 'ProjectName', 'project_name'),
        row.get('Day'), row.get('Hour'),
    ]
    raw = '|'.join(str(item or '') for item in dimensions)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _audit(cfg, actor, result, details):
    if not getattr(cfg, 'AUDIT_ENABLED', True):
        return
    try:
        from ..audit_service import get_audit_service
        get_audit_service(getattr(cfg, 'DATA_DIR', './data')).record_audit(
            user_id=(actor or {}).get('id'),
            tenant_id=(actor or {}).get('tenant_id'),
            project_id=None,
            action='admin_ark_sync' if actor else 'volcengine_sync',
            target_type='volcengine_sync',
            target_id=USAGE_SYNC_KEY,
            result=result,
            metadata=details,
        )
    except Exception:
        pass


class VolcengineUsageService(object):
    def __init__(self, cfg, db=None, client=None):
        self.cfg = cfg
        self.db = db or get_database()
        self.client = client or VolcengineUsageClient(cfg)

    # ── configuration / status ──
    def credentials_configured(self):
        return bool(
            getattr(self.cfg, 'VOLCENGINE_ACCESS_KEY_ID', '')
            and getattr(self.cfg, 'VOLCENGINE_SECRET_ACCESS_KEY', '')
        )

    def usage_enabled(self):
        return bool(getattr(self.cfg, 'VOLCENGINE_USAGE_ENABLED', False))

    def status(self):
        statuses = {row['sync_key']: row for row in get_all_sync_statuses(self.db)}
        for row in statuses.values():
            row['metadata'] = _parse_metadata(row.get('metadata'))
        usage = statuses.get(USAGE_SYNC_KEY) or {}
        last_success = usage.get('last_success_at')
        interval = int(getattr(self.cfg, 'VOLCENGINE_USAGE_SYNC_INTERVAL_S', 1800) or 1800)
        stale = True
        if last_success:
            stale = (now() - int(last_success)) > max(interval * 2, 600)
        return {
            'has_credentials': self.credentials_configured(),
            'usage_enabled': self.usage_enabled(),
            'billing_enabled': bool(getattr(self.cfg, 'VOLCENGINE_BILLING_ENABLED', False)),
            'ark_region': getattr(self.cfg, 'VOLCENGINE_ARK_REGION', 'cn-beijing'),
            'ark_project': getattr(self.cfg, 'VOLCENGINE_ARK_PROJECT', 'default'),
            'sync': statuses,
            'usage_last_synced_at': last_success,
            'is_stale': bool(stale),
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方用量（账号级）',
            'is_estimated': False,
        }

    # ── official sync ──
    def sync_official_usage(self, days=None, start_date=None, end_date=None,
                            actor=None, enrich_tasks=True):
        if not self.usage_enabled():
            finish_sync(
                self.db, USAGE_SYNC_KEY, 'disabled', error_category='disabled',
                error_code='usage_disabled', error_message='VOLCENGINE_USAGE_ENABLED=false',
            )
            raise VolcengineAPIError('disabled', '火山方舟官方用量未启用')
        if not self.credentials_configured():
            finish_sync(
                self.db, USAGE_SYNC_KEY, 'unconfigured', error_category='unconfigured',
                error_code='missing_credentials', error_message='未配置管理 AK/SK',
            )
            raise VolcengineAPIError('unconfigured', '未配置火山引擎管理 AK/SK')
        stale_seconds = max(
            300, int(getattr(self.cfg, 'VOLCENGINE_USAGE_SYNC_INTERVAL_S', 1800) or 1800)
        )
        if not claim_sync(self.db, USAGE_SYNC_KEY, stale_seconds=stale_seconds):
            return {'status': 'running', 'claimed': False}
        if start_date or end_date:
            start_date = start_date or end_date
            end_date = end_date or start_date
        else:
            start_date, end_date = _date_range(
                days or getattr(self.cfg, 'VOLCENGINE_USAGE_LOOKBACK_DAYS', 31)
            )
        dimension_filters_supported = True
        try:
            try:
                result = self.client.get_inference_usage(
                    start_date, end_date, query_interval='Day',
                    filters=self.client.dimension_filters(),
                )
            except VolcengineAPIError as exc:
                if exc.category != 'invalid_param':
                    raise
                dimension_filters_supported = False
                result = self.client.get_inference_usage(
                    start_date, end_date, query_interval='Day', filters=None,
                )
            rows = self._merge_usage_rows(
                result.get('rows') or [], result.get('query_interval') or 'Day',
                start_date, end_date, result.get('fields_json'),
            )
            synced_at = now()
            for snapshot in rows:
                snapshot['synced_at'] = synced_at
                snapshot['updated_at'] = synced_at
                upsert_usage_snapshot(self.db, snapshot)
            finish_sync(
                self.db, USAGE_SYNC_KEY, 'success', records_processed=len(rows),
                last_period='{0}..{1}'.format(start_date, end_date),
                metadata={
                    'query_interval': 'Day',
                    'dimension_filters_supported': dimension_filters_supported,
                    'rows': len(rows),
                },
                success=True,
            )
            _audit(self.cfg, actor, 'success', {
                'scope': 'usage', 'start_date': start_date, 'end_date': end_date,
                'rows': len(rows),
                'dimension_filters_supported': dimension_filters_supported,
            })
            enrichment = {'tasks_checked': 0, 'records': 0, 'errors': 0}
            if enrich_tasks:
                try:
                    enrichment = self.enrich_task_usage(limit=20)
                except Exception as exc:
                    logger.warning('Official task usage enrichment failed: %s', exc)
                    enrichment = {
                        'tasks_checked': 0, 'records': 0, 'errors': 1,
                        'error_category': getattr(exc, 'category', 'sync_error'),
                    }
            return {
                'status': 'success',
                'claimed': True,
                'start_date': start_date,
                'end_date': end_date,
                'rows': len(rows),
                'dimension_filters_supported': dimension_filters_supported,
                'enrichment': enrichment,
            }
        except Exception as exc:
            category = getattr(exc, 'category', 'sync_error')
            code = getattr(exc, 'code', None)
            finish_sync(
                self.db, USAGE_SYNC_KEY, 'failed', error_category=category,
                error_code=code, error_message=str(exc)[:500],
                last_period='{0}..{1}'.format(start_date, end_date),
            )
            _audit(self.cfg, actor, 'failed', {
                'scope': 'usage', 'start_date': start_date, 'end_date': end_date,
                'error_category': category, 'error_code': code,
            })
            raise

    def _merge_usage_rows(self, rows, interval, start_date, end_date, fields_json):
        merged = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = _snapshot_key(row, interval, start_date, end_date)
            period_label, period_start = _period_info(row)
            snapshot = merged.get(key)
            if snapshot is None:
                snapshot = {
                    'snapshot_key': key,
                    'query_interval': interval,
                    'query_start': start_date,
                    'query_end': end_date,
                    'period_label': period_label,
                    'period_start_at': period_start,
                    'account_id': _row_value(row, 'AccountID', 'account_id'),
                    'api_key_id': _row_value(
                        row, 'ApikeyID', 'APIKeyID', 'ApiKeyID', 'apikey_id'
                    ),
                    'model_name': _row_value(row, 'ModelName', 'model_name'),
                    'model_version': _row_value(row, 'ModelVersion', 'model_version'),
                    'model_endpoint': _row_value(
                        row, 'ModelEndpoint', 'model_endpoint'
                    ),
                    'billing_status': _row_value(
                        row, 'BillingStatus', 'billing_status'
                    ),
                    'project_name': _row_value(
                        row, 'ProjectName', 'project_name'
                    ),
                    'input_tokens': _as_int(_row_value(row, 'InputTokens', 'input_tokens')),
                    'output_tokens': _as_int(_row_value(row, 'OutputTokens', 'output_tokens')),
                    'total_tokens': _as_int(_row_value(row, 'TotalTokens', 'total_tokens')),
                    'req_cnt': _as_int(_row_value(row, 'ReqCnt', 'req_cnt')),
                    'image_count': _as_int(_row_value(row, 'ImageCount', 'image_count')),
                    'fields_json': fields_json,
                    'row_payload': json.dumps({'rows': [row]}, ensure_ascii=False),
                }
                merged[key] = snapshot
            else:
                metric_sources = {
                    'input_tokens': ('InputTokens', 'input_tokens'),
                    'output_tokens': ('OutputTokens', 'output_tokens'),
                    'total_tokens': ('TotalTokens', 'total_tokens'),
                    'req_cnt': ('ReqCnt', 'req_cnt'),
                    'image_count': ('ImageCount', 'image_count'),
                }
                for metric, names in metric_sources.items():
                    value = _as_int(_row_value(row, *names))
                    if snapshot.get(metric) is not None or value is not None:
                        snapshot[metric] = (snapshot.get(metric) or 0) + (value or 0)
                payload = json.loads(snapshot.get('row_payload') or '{}')
                payload.setdefault('rows', []).append(row)
                snapshot['row_payload'] = json.dumps(payload, ensure_ascii=False)
        return list(merged.values())

    def enrich_task_usage(self, limit=20):
        """Fetch official usage for recent terminal Ark video tasks (bounded)."""
        if not self.credentials_configured():
            return {'tasks_checked': 0, 'records': 0, 'errors': 0}
        rows = self.db.fetch_all(
            "SELECT t.* FROM generation_tasks t "
            "WHERE t.provider = 'ark_seedance' AND t.provider_job_id IS NOT NULL "
            "AND t.provider_job_id <> '' AND t.status IN ('succeeded','failed','cancelled') "
            "AND NOT EXISTS (SELECT 1 FROM ai_model_usage_records u "
            "WHERE u.task_id = t.id AND u.usage_source = 'official_api') "
            "ORDER BY t.completed_at DESC, t.created_at DESC LIMIT ?",
            (max(1, int(limit or 20)),),
        )
        checked = 0
        records = 0
        errors = 0
        for row in rows:
            checked += 1
            task_id = row.get('id')
            provider_job_id = row.get('provider_job_id')
            try:
                result = self.client.get_inference_task_usage(provider_job_id)
            except VolcengineAPIError as exc:
                errors += 1
                logger.info(
                    'Official task usage unavailable for task %s: %s/%s',
                    task_id, exc.category, exc.code,
                )
                continue
            if not result:
                continue
            self._record_official_task_usage(row, result)
            records += 1
        return {'tasks_checked': checked, 'records': records, 'errors': errors}

    def _record_official_task_usage(self, task_row, result):
        from ..usage_records import record_usage
        task_id = task_row.get('id')
        provider_job_id = task_row.get('provider_job_id')
        api_key_id = _row_value(result, 'APIKeyID', 'ApikeyID', 'ApiKeyID', 'apikey_id')
        output_tokens = _as_int(_row_value(result, 'OutputTokens', 'output_tokens'))
        input_tokens = _as_int(_row_value(result, 'InputTokens', 'input_tokens'))
        total_tokens = _as_int(_row_value(result, 'TotalTokens', 'total_tokens'))
        payload = {
            'task_id': provider_job_id,
            'model': _row_value(result, 'ModelName', 'model_name'),
            'status': _row_value(result, 'BillingStatus', 'billing_status'),
            'resolution': _row_value(result, 'Resolution', 'resolution'),
            'usage': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
            },
        }
        record_usage({
            'dedupe_key': 'official-task:{0}:{1}'.format(task_id, provider_job_id),
            'task_id': task_id,
            'user_id': task_row.get('created_by'),
            'project_id': task_row.get('creative_project_id'),
            'provider': 'ark_seedance',
            'model_id': task_row.get('model_id'),
            'provider_job_id': provider_job_id,
            'api_key_resource_id': api_key_id,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'usage_unit': 'token' if (output_tokens is not None or total_tokens is not None) else None,
            'usage_source': 'official_api',
            'billing_status': _row_value(result, 'BillingStatus', 'billing_status'),
            'resolution': _row_value(result, 'Resolution', 'resolution'),
            'usage_payload': payload,
            'synced_at': now(),
        })

    # ── official views (read-only snapshots) ──
    def _official_where(self, days):
        start = (datetime.now(BEIJING_TZ).date() - timedelta(days=max(1, int(days or 1)) - 1))
        return _day_start(start), '{0}'.format(start.strftime('%Y-%m-%d'))

    def official_summary(self, days=30):
        since, start_label = self._official_where(days)
        row = self.db.fetch_one(
            "SELECT COUNT(*) AS row_count, "
            "COALESCE(SUM(req_cnt),0) AS req_cnt, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM volcengine_usage_snapshots WHERE period_start_at >= ?",
            (since,),
        ) or {}
        last = get_sync_status(self.db, USAGE_SYNC_KEY) or {}
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方用量（账号级）',
            'is_estimated': False,
            'last_synced_at': last.get('last_success_at'),
            'billing_period': start_label,
            'currency': None,
            'has_data': bool(row.get('row_count')),
            'row_count': int(row.get('row_count') or 0),
            'req_cnt': int(row.get('req_cnt') or 0),
            'input_tokens': int(row.get('input_tokens') or 0),
            'output_tokens': int(row.get('output_tokens') or 0),
            'total_tokens': int(row.get('total_tokens') or 0),
            'image_count': int(row.get('image_count') or 0),
            'dimension_filters_supported': bool(
                _parse_metadata(last.get('metadata')).get(
                    'dimension_filters_supported', True
                )
            ),
        }

    def official_models(self, days=30):
        since, start_label = self._official_where(days)
        rows = self.db.fetch_all(
            "SELECT COALESCE(model_name, '未标注模型') AS model_name, "
            "COALESCE(api_key_id, '') AS api_key_id, "
            "COUNT(*) AS row_count, "
            "COALESCE(SUM(req_cnt),0) AS req_cnt, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM volcengine_usage_snapshots WHERE period_start_at >= ? "
            "GROUP BY model_name, api_key_id ORDER BY total_tokens DESC, req_cnt DESC",
            (since,),
        )
        last = get_sync_status(self.db, USAGE_SYNC_KEY) or {}
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方用量（账号级）',
            'is_estimated': False,
            'last_synced_at': last.get('last_success_at'),
            'billing_period': start_label,
            'currency': None,
            'has_data': bool(rows),
            'items': [dict(row) for row in rows],
        }

    def official_trend(self, days=30, start_date=None, end_date=None, model=None):
        since, until, start_label, end_label = _range_bounds(
            days, start_date=start_date, end_date=end_date
        )
        conditions = ['period_start_at >= ?', 'period_start_at < ?', 'period_label IS NOT NULL']
        params = [since, until]
        if model:
            conditions.append('model_name = ?')
            params.append(model)
        rows = self.db.fetch_all(
            "SELECT period_label, "
            "COALESCE(SUM(req_cnt),0) AS req_cnt, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM volcengine_usage_snapshots WHERE {0} "
            "GROUP BY period_label ORDER BY period_label ASC".format(
                ' AND '.join(conditions)
            ),
            tuple(params),
        )
        last = get_sync_status(self.db, USAGE_SYNC_KEY) or {}
        return {
            'source': OFFICIAL_SOURCE,
            'source_label': '火山引擎官方用量（账号级）',
            'is_estimated': False,
            'last_synced_at': last.get('last_success_at'),
            'billing_period': start_label + '..' + end_label,
            'currency': None,
            'has_data': bool(rows),
            'items': [dict(row) for row in rows],
        }

    # ── local views ──
    def _local_since(self, days):
        start = datetime.now(BEIJING_TZ).date() - timedelta(days=max(1, int(days or 1)) - 1)
        return _day_start(start), start.strftime('%Y-%m-%d')

    def _task_rows(self, days):
        since, _ = self._local_since(days)
        return self.db.fetch_all(
            "SELECT created_at, completed_at, task_type, status, provider, model_id, "
            "created_by, created_at_ms, claimed_at_ms, provider_job_created_at, "
            "provider_finished_at, download_started_at, download_finished_at, "
            "persist_started_at, persist_finished_at, completed_at_ms "
            "FROM generation_tasks WHERE created_at >= ?",
            (since,),
        )

    def local_summary(self, days=30):
        rows = self._task_rows(days)
        _, start_label = self._local_since(days)
        statuses = {}
        types = {}
        models = set()
        model_task_types = ('image', 'video', 'storyboard')
        running = 0
        succeeded = 0
        failed = 0
        model_calls = 0
        for row in rows:
            status = row.get('status')
            statuses[status] = statuses.get(status, 0) + 1
            task_type = row.get('task_type')
            types[task_type] = types.get(task_type, 0) + 1
            if task_type in model_task_types:
                model_calls += 1
                if row.get('model_id'):
                    models.add(row.get('model_id'))
                if status in ('queued', 'submitting', 'running'):
                    running += 1
                elif status == 'succeeded':
                    succeeded += 1
                elif status == 'failed':
                    failed += 1
        terminal = succeeded + failed
        performance = self.task_performance(days=days)
        since, _ = self._local_since(days)
        usage_models = self.db.fetch_all(
            "SELECT DISTINCT model_id FROM ai_model_usage_records "
            "WHERE recorded_at >= ? AND usage_source <> 'official_api' "
            "AND model_id IS NOT NULL AND model_id <> ''",
            (since,),
        )
        for row in usage_models:
            if row.get('model_id'):
                models.add(row.get('model_id'))
        try:
            from .. import generation_models
            configured_model_count = len(generation_models.list_models(
                self.cfg, include_unavailable=True, user=None
            ))
        except Exception:
            configured_model_count = None
        return {
            'source': LOCAL_SOURCE,
            'source_label': 'AIGV 本地真实任务记录',
            'is_estimated': False,
            'last_synced_at': None,
            'billing_period': start_label,
            'currency': None,
            'has_data': bool(rows),
            'tasks_total': len(rows),
            'model_calls': model_calls,
            'images': types.get('image', 0),
            'videos': types.get('video', 0),
            'llm_tasks': types.get('storyboard', 0),
            'running': running,
            'succeeded': succeeded,
            'failed': failed,
            'success_rate': round((succeeded / terminal) * 100, 1) if terminal else None,
            'model_count': len(models),
            'configured_model_count': configured_model_count,
            'avg_duration_ms': performance.get('total_ms'),
            'avg_queue_ms': performance.get('queue_wait_ms'),
            'avg_provider_ms': performance.get('provider_elapsed_ms'),
            'avg_download_ms': performance.get('download_ms'),
            'status_counts': statuses,
            'task_type_counts': types,
        }

    def task_performance(self, days=30):
        rows = [
            row for row in self._task_rows(days)
            if row.get('task_type') in ('image', 'video', 'storyboard')
        ]
        durations = {
            'queue_wait_ms': [],
            'provider_elapsed_ms': [],
            'download_ms': [],
            'persist_ms': [],
            'total_ms': [],
        }

        def epoch_ms(value):
            if value is None:
                return None
            try:
                return float(value) * 1000.0
            except (TypeError, ValueError):
                return None

        def delta(finish, start):
            if finish is None or start is None:
                return None
            value = finish - start
            return value if value >= 0 else None

        for row in rows:
            queue = delta(epoch_ms(row.get('claimed_at_ms')), epoch_ms(row.get('created_at_ms')))
            provider = delta(
                epoch_ms(row.get('provider_finished_at')),
                epoch_ms(row.get('provider_job_created_at')),
            )
            download = delta(
                epoch_ms(row.get('download_finished_at')),
                epoch_ms(row.get('download_started_at')),
            )
            persist = delta(
                epoch_ms(row.get('persist_finished_at')),
                epoch_ms(row.get('persist_started_at')),
            )
            total = delta(epoch_ms(row.get('completed_at_ms')), epoch_ms(row.get('created_at_ms')))
            for key, value in (
                ('queue_wait_ms', queue), ('provider_elapsed_ms', provider),
                ('download_ms', download), ('persist_ms', persist),
                ('total_ms', total),
            ):
                if value is not None:
                    durations[key].append(value)
        result = {}
        for key, values in durations.items():
            result[key] = round(sum(values) / len(values), 1) if values else None
        return result

    def local_models(self, days=30):
        since, start_label = self._local_since(days)
        task_rows = self.db.fetch_all(
            "SELECT COALESCE(model_id, '') AS model_id, "
            "COALESCE(provider, '') AS provider, task_type, status, COUNT(*) AS task_count "
            "FROM generation_tasks WHERE created_at >= ? GROUP BY model_id, provider, task_type, status",
            (since,),
        )
        usage_rows = self.db.fetch_all(
            "SELECT COALESCE(model_id, '') AS model_id, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count, "
            "COUNT(DISTINCT task_id) AS usage_task_count "
            "FROM ai_model_usage_records WHERE recorded_at >= ? AND usage_source <> 'official_api' "
            "GROUP BY model_id",
            (since,),
        )
        usage = {row.get('model_id'): dict(row) for row in usage_rows}
        merged = {}
        for row in task_rows:
            if not row.get('model_id') and not row.get('provider'):
                continue
            key = (row.get('model_id') or '', row.get('provider') or '')
            item = merged.setdefault(key, {
                'model_id': row.get('model_id') or None,
                'provider': row.get('provider') or None,
                'task_count': 0, 'succeeded': 0, 'failed': 0,
                'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                'image_count': 0,
            })
            count = int(row.get('task_count') or 0)
            item['task_count'] += count
            if row.get('status') == 'succeeded':
                item['succeeded'] += count
            elif row.get('status') == 'failed':
                item['failed'] += count
        for key, item in merged.items():
            extra = usage.get(item.get('model_id') or '') or {}
            for field in ('input_tokens', 'output_tokens', 'total_tokens', 'image_count'):
                item[field] = int(extra.get(field) or 0)
        # LLM usage records may not have a task model_id (the model lives in
        # provider_credentials / the response), so include usage-only models.
        seen_models = set(item.get('model_id') for item in merged.values())
        for model_id, extra in usage.items():
            if not model_id or model_id in seen_models:
                continue
            merged[('usage-only', model_id)] = {
                'model_id': model_id,
                'provider': 'llm',
                'task_count': 0,
                'succeeded': 0,
                'failed': 0,
                'input_tokens': int(extra.get('input_tokens') or 0),
                'output_tokens': int(extra.get('output_tokens') or 0),
                'total_tokens': int(extra.get('total_tokens') or 0),
                'image_count': int(extra.get('image_count') or 0),
            }
        items = sorted(
            merged.values(),
            key=lambda entry: (entry['task_count'], entry['total_tokens']),
            reverse=True,
        )
        return {
            'source': LOCAL_SOURCE,
            'source_label': 'AIGV 本地真实任务/Provider 响应',
            'is_estimated': False,
            'last_synced_at': None,
            'billing_period': start_label,
            'currency': None,
            'has_data': bool(items),
            'items': items,
        }

    def local_trend(self, days=30, start_date=None, end_date=None, model=None):
        since, until, start_label, end_label = _range_bounds(
            days, start_date=start_date, end_date=end_date
        )
        rows = self.task_trend_rows(since, until=until, model=model)
        return {
            'source': LOCAL_SOURCE,
            'source_label': 'AIGV 本地真实任务记录',
            'is_estimated': False,
            'last_synced_at': None,
            'billing_period': start_label + '..' + end_label,
            'currency': None,
            'has_data': bool(rows),
            'items': rows,
        }

    def task_trend_rows(self, since, until=None, model=None):
        conditions = ['created_at >= ?']
        params = [since]
        if until is not None:
            conditions.append('created_at < ?')
            params.append(until)
        if model:
            conditions.append('model_id = ?')
            params.append(model)
        rows = self.db.fetch_all(
            "SELECT created_at, task_type, status FROM generation_tasks WHERE {0}".format(
                ' AND '.join(conditions)
            ),
            tuple(params),
        )
        buckets = {}
        for row in rows:
            try:
                day = datetime.fromtimestamp(int(row.get('created_at') or 0), BEIJING_TZ)
            except (TypeError, ValueError, OSError):
                continue
            label = day.strftime('%Y-%m-%d')
            item = buckets.setdefault(label, {
                'period_label': label, 'tasks': 0, 'images': 0, 'videos': 0,
                'succeeded': 0, 'failed': 0,
            })
            item['tasks'] += 1
            if row.get('task_type') == 'image':
                item['images'] += 1
            elif row.get('task_type') == 'video':
                item['videos'] += 1
            if row.get('status') == 'succeeded':
                item['succeeded'] += 1
            elif row.get('status') == 'failed':
                item['failed'] += 1
        return [buckets[key] for key in sorted(buckets.keys())]

    def local_users(self, days=30):
        since, start_label = self._local_since(days)
        task_rows = self.db.fetch_all(
            "SELECT COALESCE(created_by, '') AS user_id, task_type, status, COUNT(*) AS task_count "
            "FROM generation_tasks WHERE created_at >= ? GROUP BY user_id, task_type, status",
            (since,),
        )
        usage_rows = self.db.fetch_all(
            "SELECT COALESCE(user_id, '') AS user_id, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM ai_model_usage_records WHERE recorded_at >= ? AND usage_source <> 'official_api' "
            "GROUP BY user_id",
            (since,),
        )
        usage = {row.get('user_id'): dict(row) for row in usage_rows}
        merged = {}
        for row in task_rows:
            user_id = row.get('user_id') or ''
            item = merged.setdefault(user_id, {
                'user_id': user_id or None,
                'task_count': 0, 'images': 0, 'videos': 0, 'llm_requests': 0,
                'succeeded': 0, 'failed': 0,
                'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0,
                'image_count': 0,
            })
            count = int(row.get('task_count') or 0)
            item['task_count'] += count
            if row.get('task_type') == 'image':
                item['images'] += count
            elif row.get('task_type') == 'video':
                item['videos'] += count
            elif row.get('task_type') == 'storyboard':
                item['llm_requests'] += count
            if row.get('status') == 'succeeded':
                item['succeeded'] += count
            elif row.get('status') == 'failed':
                item['failed'] += count
        for user_id, item in merged.items():
            extra = usage.get(user_id) or {}
            for field in ('input_tokens', 'output_tokens', 'total_tokens', 'image_count'):
                item[field] = int(extra.get(field) or 0)
            terminal = item['succeeded'] + item['failed']
            item['success_rate'] = round(item['succeeded'] / terminal * 100, 1) if terminal else None
        user_ids = [user_id for user_id in merged.keys() if user_id]
        users = {}
        if user_ids:
            placeholders = ','.join('?' for _ in user_ids)
            rows = self.db.fetch_all(
                'SELECT id, username, nickname FROM auth_users WHERE id IN ({0})'.format(placeholders),
                tuple(user_ids),
            )
            users = {row.get('id'): dict(row) for row in rows}
        items = []
        for user_id, item in merged.items():
            user = users.get(user_id)
            if user:
                username = user.get('username') or ''
                nickname = user.get('nickname') or ''
                item['username'] = username
                item['nickname'] = nickname
                item['display'] = nickname + ('（' + username + '）' if nickname and nickname != username else '')
                if not item['display']:
                    item['display'] = username or '用户'
            elif user_id:
                item['username'] = None
                item['nickname'] = None
                item['display'] = '已删除用户'
            else:
                item['display'] = '系统/未归属'
            items.append(item)
        items.sort(key=lambda entry: (entry['task_count'], entry['total_tokens']), reverse=True)
        return {
            'source': LOCAL_SOURCE,
            'source_label': 'AIGV 本地真实任务/Provider 响应',
            'is_estimated': False,
            'last_synced_at': None,
            'billing_period': start_label,
            'currency': None,
            'has_data': bool(items),
            'items': items,
        }

    def local_tasks(self, days=30, limit=50, offset=0):
        since, start_label = self._local_since(days)
        limit = max(1, min(200, int(limit or 50)))
        offset = max(0, int(offset or 0))
        total = self.db.count(
            'generation_tasks', 'created_at >= ?', (since,)
        )
        rows = self.db.fetch_all(
            "SELECT id, task_type, status, provider, model_id, created_by, "
            "creative_project_id, error_code, created_at, completed_at, "
            "created_at_ms, claimed_at_ms, provider_job_created_at, "
            "provider_finished_at, download_started_at, download_finished_at, "
            "persist_started_at, persist_finished_at, completed_at_ms, provider_job_id "
            "FROM generation_tasks WHERE created_at >= ? "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (since, limit, offset),
        )
        task_ids = [row.get('id') for row in rows]
        usage_map = {}
        if task_ids:
            placeholders = ','.join('?' for _ in task_ids)
            usage_rows = self.db.fetch_all(
                "SELECT task_id, usage_source, api_key_resource_id, "
                "COALESCE(SUM(input_tokens),0) AS input_tokens, "
                "COALESCE(SUM(output_tokens),0) AS output_tokens, "
                "COALESCE(SUM(total_tokens),0) AS total_tokens, "
                "COALESCE(SUM(image_count),0) AS image_count "
                "FROM ai_model_usage_records WHERE task_id IN ({0}) "
                "GROUP BY task_id, usage_source, api_key_resource_id".format(placeholders),
                tuple(task_ids),
            )
            for usage_row in usage_rows:
                item = usage_map.setdefault(usage_row.get('task_id'), {
                    'sources': [], 'api_key_resource_ids': [],
                    'input_tokens': 0, 'output_tokens': 0,
                    'total_tokens': 0, 'image_count': 0,
                })
                source = usage_row.get('usage_source') or 'local'
                if source not in item['sources']:
                    item['sources'].append(source)
                key_id = usage_row.get('api_key_resource_id')
                if key_id and key_id not in item['api_key_resource_ids']:
                    item['api_key_resource_ids'].append(key_id)
                for field in ('input_tokens', 'output_tokens', 'total_tokens', 'image_count'):
                    item[field] += int(usage_row.get(field) or 0)
        creator_ids = sorted(set(row.get('created_by') for row in rows if row.get('created_by')))
        creators = {}
        if creator_ids:
            placeholders = ','.join('?' for _ in creator_ids)
            creator_rows = self.db.fetch_all(
                'SELECT id, username, nickname FROM auth_users WHERE id IN ({0})'.format(
                    placeholders
                ),
                tuple(creator_ids),
            )
            creators = {row.get('id'): dict(row) for row in creator_rows}
        items = []
        for row in rows:
            creator = creators.get(row.get('created_by'))
            if creator:
                username = creator.get('username') or ''
                nickname = creator.get('nickname') or ''
                creator_display = nickname + (
                    '（' + username + '）' if nickname and nickname != username else ''
                )
                creator_display = creator_display or username or '用户'
            elif row.get('created_by'):
                creator_display = '已删除用户'
            else:
                creator_display = '系统/未归属'
            usage = usage_map.get(row.get('id')) or {
                'sources': [], 'api_key_resource_ids': [],
                'input_tokens': 0, 'output_tokens': 0,
                'total_tokens': 0, 'image_count': 0,
            }
            items.append({
                'id': row.get('id'),
                'task_type': row.get('task_type'),
                'status': row.get('status'),
                'provider': row.get('provider'),
                'model_id': row.get('model_id'),
                'provider_job_id': row.get('provider_job_id'),
                'created_by': row.get('created_by'),
                'creator_display': creator_display,
                'creative_project_id': row.get('creative_project_id'),
                'error_code': row.get('error_code'),
                'created_at': row.get('created_at'),
                'completed_at': row.get('completed_at'),
                'timings': self._durations_for_row(row),
                'usage': usage,
            })
        return {
            'source': LOCAL_SOURCE,
            'source_label': 'AIGV 本地真实任务/Provider 响应',
            'is_estimated': False,
            'last_synced_at': None,
            'billing_period': start_label,
            'currency': None,
            'items': items,
            'total': total,
            'limit': limit,
            'offset': offset,
        }

    def _durations_for_row(self, row):
        def epoch_ms(value):
            if value is None:
                return None
            try:
                return float(value) * 1000.0
            except (TypeError, ValueError):
                return None

        def delta(finish, start):
            if finish is None or start is None:
                return None
            value = finish - start
            return round(value, 1) if value >= 0 else None

        return {
            'queue_wait_ms': delta(
                epoch_ms(row.get('claimed_at_ms')), epoch_ms(row.get('created_at_ms'))
            ),
            'provider_elapsed_ms': delta(
                epoch_ms(row.get('provider_finished_at')),
                epoch_ms(row.get('provider_job_created_at')),
            ),
            'download_ms': delta(
                epoch_ms(row.get('download_finished_at')),
                epoch_ms(row.get('download_started_at')),
            ),
            'persist_ms': delta(
                epoch_ms(row.get('persist_finished_at')),
                epoch_ms(row.get('persist_started_at')),
            ),
            'total_ms': delta(
                epoch_ms(row.get('completed_at_ms')), epoch_ms(row.get('created_at_ms'))
            ),
        }

    def reconciliation(self, days=30):
        since, start_label = self._local_since(days)
        official = self.official_summary(days)
        local_usage = self.db.fetch_one(
            "SELECT COUNT(DISTINCT task_id) AS task_count, "
            "COALESCE(SUM(input_tokens),0) AS input_tokens, "
            "COALESCE(SUM(output_tokens),0) AS output_tokens, "
            "COALESCE(SUM(total_tokens),0) AS total_tokens, "
            "COALESCE(SUM(image_count),0) AS image_count "
            "FROM ai_model_usage_records WHERE recorded_at >= ? "
            "AND provider IN ('ark_seedream','ark_seedance')",
            (since,),
        ) or {}
        ark_tasks = self.db.fetch_one(
            "SELECT COUNT(*) AS task_count FROM generation_tasks "
            "WHERE created_at >= ? AND provider IN ('ark_seedream','ark_seedance')",
            (since,),
        ) or {}
        return {
            'source': 'internal_estimate',
            'source_label': '官方用量与 AIGV 本地记录对账（非金额）',
            'is_estimated': True,
            'last_synced_at': official.get('last_synced_at'),
            'billing_period': start_label,
            'currency': None,
            'official': {
                'req_cnt': official.get('req_cnt'),
                'input_tokens': official.get('input_tokens'),
                'output_tokens': official.get('output_tokens'),
                'total_tokens': official.get('total_tokens'),
                'image_count': official.get('image_count'),
                'has_data': official.get('has_data'),
            },
            'local': {
                'ark_task_count': int(ark_tasks.get('task_count') or 0),
                'task_count': int(local_usage.get('task_count') or 0),
                'input_tokens': int(local_usage.get('input_tokens') or 0),
                'output_tokens': int(local_usage.get('output_tokens') or 0),
                'total_tokens': int(local_usage.get('total_tokens') or 0),
                'image_count': int(local_usage.get('image_count') or 0),
            },
            'notes': [
                '官方用量是账号级数据，可能包含同一账号下的其他应用调用。',
                '本地任务数不等于官方计费请求数；失败/取消请求也可能被服务商计费。',
                'Token 与图片张数是不同计量单位，不能直接相加或换算为金额。',
                '未配置官方管理凭据或未同步时，官方侧显示为空，不代表本地没有调用。',
            ],
        }
