# -*- coding: utf-8 -*-
"""Read-only Volcengine Ark inference usage client."""
from __future__ import absolute_import

import json
from datetime import datetime

from .client import VolcengineAPIError, VolcengineHTTPClient

USAGE_VERSION = '2024-01-01'
USAGE_SERVICE = 'ark'
USAGE_ACTIONS = (
    'GetInferenceUsage',
    'GetInferenceTaskUsage',
    'GetInferenceRequestUsage',
)

_NUMERIC_FIELDS = set([
    'AccountID', 'UserID', 'InputTokens', 'OutputTokens', 'TotalTokens',
    'ReqCnt', 'ImageCount', 'WindowMaxInputTokens', 'WindowMaxOutputTokens',
    'CacheHitTokens', 'AudioTokens', 'AudioCachedTokens',
    'AudioOriginalDurationMs', 'ImageNumber', 'InputImageCount',
    'AccountantStartTime', 'AccountantEndTime', 'Timestamp',
])


def _validate_day(value, field):
    try:
        parsed = datetime.strptime(str(value), '%Y-%m-%d')
    except (TypeError, ValueError):
        raise VolcengineAPIError(
            'invalid_param',
            '{0} 日期格式应为 YYYY-MM-DD'.format(field),
        )
    return parsed.strftime('%Y-%m-%d')


def _coerce(name, value, type_name=None):
    if value is None:
        return None
    if name in _NUMERIC_FIELDS or str(type_name or '').upper() in (
        'BIGINT', 'INTEGER', 'LONG', 'INT',
    ):
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return value
    if str(type_name or '').upper() in ('BOOLEAN', 'BOOL'):
        if isinstance(value, bool):
            return value
        return str(value).lower() == 'true'
    return value


def rows_from_fields(fields, data):
    """Map the dynamic ``Fields``/``Data`` response into row dicts.

    The API may add columns at any time, so callers must not rely on a fixed
    column order or a fixed metric set.
    """
    if not isinstance(data, list):
        return []
    if data and isinstance(data[0], dict):
        return [dict(item) for item in data]
    names = []
    types = {}
    for item in fields or []:
        if isinstance(item, dict):
            name = item.get('Name')
            if name:
                names.append(name)
                types[name] = item.get('Type')
    rows = []
    for row in data:
        if not isinstance(row, (list, tuple)):
            continue
        values = {}
        for index, name in enumerate(names):
            value = row[index] if index < len(row) else None
            values[name] = _coerce(name, value, types.get(name))
        rows.append(values)
    return rows


class VolcengineUsageClient(object):
    """Calls the Ark management APIs with the management AK/SK only."""

    def __init__(self, cfg, http_client=None):
        self.cfg = cfg
        self.http = http_client or VolcengineHTTPClient(
            cfg.VOLCENGINE_ACCESS_KEY_ID,
            cfg.VOLCENGINE_SECRET_ACCESS_KEY,
            timeout_s=getattr(cfg, 'VOLCENGINE_SYNC_TIMEOUT_S', 20),
            max_retries=getattr(cfg, 'VOLCENGINE_SYNC_MAX_RETRIES', 2),
        )

    @property
    def host(self):
        region = getattr(self.cfg, 'VOLCENGINE_ARK_REGION', 'cn-beijing')
        return 'ark.{0}.volcengineapi.com'.format(region)

    def _call(self, action, body):
        return self.http.post_json(
            self.host,
            action,
            USAGE_VERSION,
            body,
            region=getattr(self.cfg, 'VOLCENGINE_ARK_REGION', 'cn-beijing'),
            service=USAGE_SERVICE,
        )

    def get_inference_usage(self, start_date, end_date, query_interval='Day',
                            filters=None, project_name=None,
                            show_window_detail=False):
        start_date = _validate_day(start_date, 'StartTime')
        end_date = _validate_day(end_date, 'EndTime')
        if start_date > end_date:
            raise VolcengineAPIError(
                'invalid_param', 'StartTime 不能晚于 EndTime'
            )
        interval = 'Hour' if str(query_interval).lower() == 'hour' else 'Day'
        body = {
            'StartTime': start_date,
            'EndTime': end_date,
            'QueryInterval': interval,
            'ProjectName': project_name or getattr(
                self.cfg, 'VOLCENGINE_ARK_PROJECT', 'default'
            ),
        }
        if filters:
            body['Filters'] = filters
        if show_window_detail:
            body['ShowWindowDetail'] = True
        payload = self._call('GetInferenceUsage', body)
        result = payload.get('Result') or {}
        if not isinstance(result, dict):
            raise VolcengineAPIError(
                'invalid_response', 'GetInferenceUsage 返回结构无效'
            )
        fields = result.get('Fields') or []
        rows = rows_from_fields(fields, result.get('Data'))
        metadata = payload.get('ResponseMetadata') or {}
        return {
            'fields': fields,
            'fields_json': json.dumps(fields, ensure_ascii=False),
            'rows': rows,
            'data_count': result.get('DataCount', len(rows)),
            'request_id': metadata.get('RequestId'),
            'query_interval': interval,
            'query_start': start_date,
            'query_end': end_date,
        }

    def get_inference_task_usage(self, task_id):
        task_id = str(task_id or '').strip()
        if not task_id:
            raise VolcengineAPIError('invalid_param', 'TaskID 不能为空')
        payload = self._call('GetInferenceTaskUsage', {'TaskID': task_id})
        result = payload.get('Result')
        if not isinstance(result, dict):
            raise VolcengineAPIError(
                'invalid_response', 'GetInferenceTaskUsage 返回结构无效'
            )
        return result

    def get_inference_request_usage(self, request_id, query_hour):
        request_id = str(request_id or '').strip()
        if not request_id:
            raise VolcengineAPIError('invalid_param', 'RequestID 不能为空')
        try:
            parsed = datetime.strptime(str(query_hour), '%Y-%m-%d %H:00:00')
        except (TypeError, ValueError):
            raise VolcengineAPIError(
                'invalid_param', 'QueryHour 格式应为 YYYY-MM-DD HH:00:00'
            )
        payload = self._call('GetInferenceRequestUsage', {
            'RequestID': request_id,
            'QueryHour': parsed.strftime('%Y-%m-%d %H:00:00'),
        })
        result = payload.get('Result') or {}
        if isinstance(result, list):
            records = result
        elif isinstance(result, dict):
            records = result.get('Records') or []
        else:
            records = []
        if not isinstance(records, list):
            raise VolcengineAPIError(
                'invalid_response', 'GetInferenceRequestUsage 返回结构无效'
            )
        return [dict(item) for item in records if isinstance(item, dict)]

    @staticmethod
    def dimension_filters(keys=('ApikeyID', 'ModelName')):
        """Request dimension columns without filtering.

        The official documentation states that an empty ``Values`` array means
        "do not filter by this key, but still return the column".  Callers
        should verify this against the real account and fall back safely.
        """
        return [{'Key': key, 'Values': []} for key in keys]
