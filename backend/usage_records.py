# -*- coding: utf-8 -*-
"""AIGV-local AI model usage records.

Only provider-reported metrics are stored.  Missing metrics remain NULL rather
than being inferred from task counts, requested duration or status.
"""
from __future__ import absolute_import

import hashlib
import json
import logging
import time

from .database import get_database

logger = logging.getLogger(__name__)

TABLE = 'ai_model_usage_records'

_SAFE_USAGE_KEYS = set([
    'generated_images', 'input_images', 'output_tokens', 'total_tokens',
    'input_tokens', 'completion_tokens', 'prompt_tokens',
    'tool_usage', 'web_search', 'image_count', 'duration', 'resolution',
])
_SAFE_TOP_KEYS = set([
    'id', 'model', 'status', 'created', 'resolution', 'duration', 'ratio',
    'task_id', 'request_id', 'usage', 'error',
])


def _now():
    return int(time.time())


def _dedupe_key(parts):
    raw = '|'.join(str(part or '') for part in parts)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _safe_mapping(value, allowed_keys, depth=0):
    if depth > 4 or not isinstance(value, dict):
        return None
    result = {}
    for key, item in list(value.items())[:50]:
        if key not in allowed_keys:
            continue
        if isinstance(item, dict):
            result[key] = _safe_mapping(item, _SAFE_USAGE_KEYS, depth + 1)
        elif isinstance(item, (list, tuple)):
            result[key] = [
                entry for entry in list(item)[:20]
                if isinstance(entry, (str, int, float, bool)) or entry is None
            ]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
    return result or None


def safe_usage_payload(raw):
    """Keep only usage/ID fields; never store URLs, prompts or media content."""
    if not isinstance(raw, dict):
        return None
    payload = {}
    for key in _SAFE_TOP_KEYS:
        if key not in raw:
            continue
        item = raw[key]
        if key == 'usage' and isinstance(item, dict):
            payload['usage'] = _safe_mapping(item, _SAFE_USAGE_KEYS)
        elif key == 'error' and isinstance(item, dict):
            payload['error'] = {
                'code': str(item.get('code') or item.get('Code') or '')[:120] or None,
                'message': str(item.get('message') or item.get('Message') or '')[:300] or None,
            }
        elif isinstance(item, (str, int, float, bool)) or item is None:
            payload[key] = item
    return payload or None


def _usage_dict(raw):
    if not isinstance(raw, dict):
        return {}
    usage = raw.get('usage')
    if not isinstance(usage, dict):
        nested = raw.get('data')
        usage = nested.get('usage') if isinstance(nested, dict) else {}
    return usage if isinstance(usage, dict) else {}


def extract_image_usage(raw, actual_image_count=None):
    usage = _usage_dict(raw)
    payload = {}
    image_count = usage.get('generated_images')
    if image_count is None:
        image_count = usage.get('image_count')
    if image_count is not None:
        try:
            image_count = int(image_count)
        except (TypeError, ValueError):
            image_count = None
    if image_count is None and actual_image_count is not None:
        image_count = int(actual_image_count)
        payload['image_count_source'] = 'response_data_length'
    output_tokens = usage.get('output_tokens')
    total_tokens = usage.get('total_tokens')
    input_images = usage.get('input_images')
    tool_usage = usage.get('tool_usage')
    return {
        'image_count': image_count,
        'output_tokens': _as_int(output_tokens),
        'total_tokens': _as_int(total_tokens),
        'input_tokens': None,
        'input_images': _as_int(input_images),
        'tool_usage': tool_usage if isinstance(tool_usage, dict) else None,
        'usage_payload_extra': payload or None,
    }


def extract_video_usage(raw):
    usage = _usage_dict(raw)
    payload = {}
    output_tokens = (
        usage.get('completion_tokens')
        if usage.get('completion_tokens') is not None
        else usage.get('output_tokens')
    )
    total_tokens = usage.get('total_tokens')
    duration = raw.get('duration') if isinstance(raw, dict) else None
    if duration is not None:
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = None
        if duration is not None:
            payload['duration_source'] = 'provider_response'
    return {
        'output_tokens': _as_int(output_tokens),
        'total_tokens': _as_int(total_tokens),
        'input_tokens': _as_int(usage.get('input_tokens')),
        'video_duration_s': duration,
        'billing_status': usage.get('billing_status') or raw.get('billing_status'),
        'resolution': raw.get('resolution') if isinstance(raw, dict) else None,
        'tool_usage': usage.get('tool_usage') if isinstance(usage.get('tool_usage'), dict) else None,
        'usage_payload_extra': payload or None,
    }


def extract_llm_usage(response_meta):
    if not isinstance(response_meta, dict):
        return {}
    usage = response_meta.get('usage') or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        'input_tokens': _as_int(usage.get('prompt_tokens')),
        'output_tokens': _as_int(usage.get('completion_tokens')),
        'total_tokens': _as_int(usage.get('total_tokens')),
        'provider_request_id': response_meta.get('id'),
        'model_id': response_meta.get('model'),
    }


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


def _compose_payload(base, extra, usage, request_id=None, model_id=None):
    payload = dict(base or {})
    if usage:
        payload['usage'] = usage
    if extra:
        payload.update(extra)
    if request_id:
        payload['request_id'] = request_id
    if model_id:
        payload['model'] = model_id
    return payload or None


def record_usage(record):
    """Upsert one usage record by ``dedupe_key``.

    The function is intentionally tolerant: a usage persistence failure must
    never break a user's generation task.
    """
    if not record or not record.get('dedupe_key'):
        return None
    db = get_database()
    now = _now()
    payload = record.get('usage_payload')
    if payload is not None and not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)
    values = {
        'id': record.get('id') or _dedupe_key([record['dedupe_key'], 'id']),
        'dedupe_key': record['dedupe_key'],
        'task_id': record.get('task_id'),
        'user_id': record.get('user_id'),
        'project_id': record.get('project_id'),
        'provider': record.get('provider'),
        'model_id': record.get('model_id'),
        'provider_job_id': record.get('provider_job_id'),
        'provider_request_id': record.get('provider_request_id'),
        'api_key_resource_id': record.get('api_key_resource_id'),
        'input_tokens': record.get('input_tokens'),
        'output_tokens': record.get('output_tokens'),
        'total_tokens': record.get('total_tokens'),
        'image_count': record.get('image_count'),
        'video_duration_s': record.get('video_duration_s'),
        'usage_unit': record.get('usage_unit'),
        'usage_source': record.get('usage_source') or 'local',
        'billing_status': record.get('billing_status'),
        'resolution': record.get('resolution'),
        'usage_payload': payload,
        'recorded_at': record.get('recorded_at') or now,
        'synced_at': record.get('synced_at'),
        'created_at': record.get('created_at') or now,
        'updated_at': now,
    }
    columns = list(values.keys())
    placeholders = ', '.join('?' for _ in columns)
    updates = []
    for column in columns:
        if column in ('id', 'dedupe_key', 'created_at'):
            continue
        if column in ('recorded_at',):
            updates.append('{0} = COALESCE({1}.{0}, excluded.{0})'.format(column, TABLE))
        else:
            updates.append(
                '{0} = COALESCE(excluded.{0}, {1}.{0})'.format(column, TABLE)
            )
    query = (
        'INSERT INTO {0} ({1}) VALUES ({2}) '
        'ON CONFLICT(dedupe_key) DO UPDATE SET {3}'
    ).format(TABLE, ', '.join(columns), placeholders, ', '.join(updates))
    db.execute(query, tuple(values[column] for column in columns))
    return values['id']


def record_image_usage(task, files, raw, cfg=None, provider_request_id=None):
    usage = extract_image_usage(raw, actual_image_count=len(files or []))
    provider = getattr(task, 'provider', None)
    if provider != 'ark_seedream':
        return None
    request_id = provider_request_id or getattr(task, 'provider_request_id', None)
    key = _dedupe_key([task.id, 'image', 'response'])
    payload = _compose_payload(
        {'status': 'succeeded', 'usage': usage.get('tool_usage')},
        usage.get('usage_payload_extra'),
        _image_usage_payload(usage),
        request_id=request_id,
        model_id=getattr(task, 'model_id', None),
    )
    return record_usage({
        'dedupe_key': key,
        'task_id': task.id,
        'user_id': task.created_by,
        'project_id': task.creative_project_id,
        'provider': provider,
        'model_id': task.model_id,
        'provider_request_id': request_id,
        'api_key_resource_id': getattr(cfg, 'VOLCENGINE_ARK_API_KEY_RESOURCE_ID', None),
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
        'total_tokens': usage.get('total_tokens'),
        'image_count': usage.get('image_count'),
        'usage_unit': 'image' if usage.get('image_count') is not None else None,
        'usage_source': 'response',
        'usage_payload': payload,
    })


def _image_usage_payload(usage):
    payload = {}
    for key in ('image_count', 'input_images', 'output_tokens', 'total_tokens', 'tool_usage'):
        if usage.get(key) is not None:
            payload[key] = usage[key]
    if usage.get('usage_payload_extra'):
        payload.update(usage['usage_payload_extra'])
    return payload or None


def record_video_submission(task, raw, provider_job_id=None, provider_request_id=None, cfg=None):
    provider = getattr(task, 'provider', None)
    if provider != 'ark_seedance':
        return None
    usage = extract_video_usage(raw)
    key = _dedupe_key([task.id, 'video', 'response', provider_job_id or ''])
    payload = _compose_payload(
        {'status': 'submitted'},
        usage.get('usage_payload_extra'),
        usage.get('tool_usage'),
        request_id=provider_request_id,
        model_id=getattr(task, 'model_id', None),
    )
    return record_usage({
        'dedupe_key': key,
        'task_id': task.id,
        'user_id': task.created_by,
        'project_id': task.creative_project_id,
        'provider': provider,
        'model_id': task.model_id,
        'provider_job_id': provider_job_id,
        'provider_request_id': provider_request_id,
        'api_key_resource_id': getattr(cfg, 'VOLCENGINE_ARK_API_KEY_RESOURCE_ID', None),
        'usage_source': 'response_submit',
        'usage_payload': payload,
    })


def record_video_usage(task, raw, provider_job_id=None, provider_request_id=None, cfg=None):
    provider = getattr(task, 'provider', None)
    if provider != 'ark_seedance':
        return None
    usage = extract_video_usage(raw)
    key = _dedupe_key([task.id, 'video', 'response', provider_job_id or ''])
    payload = _compose_payload(
        {'status': (raw or {}).get('status') if isinstance(raw, dict) else None},
        usage.get('usage_payload_extra'),
        usage.get('tool_usage'),
        request_id=provider_request_id,
        model_id=getattr(task, 'model_id', None),
    )
    return record_usage({
        'dedupe_key': key,
        'task_id': task.id,
        'user_id': task.created_by,
        'project_id': task.creative_project_id,
        'provider': provider,
        'model_id': task.model_id,
        'provider_job_id': provider_job_id,
        'provider_request_id': provider_request_id,
        'api_key_resource_id': getattr(cfg, 'VOLCENGINE_ARK_API_KEY_RESOURCE_ID', None),
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
        'total_tokens': usage.get('total_tokens'),
        'video_duration_s': usage.get('video_duration_s'),
        'usage_unit': 'token' if usage.get('total_tokens') is not None else None,
        'usage_source': 'response_poll',
        'billing_status': usage.get('billing_status'),
        'resolution': usage.get('resolution'),
        'usage_payload': payload,
    })


def record_llm_usage(task, model_name, response_meta):
    if not isinstance(response_meta, dict) or not response_meta:
        return None
    usage = extract_llm_usage(response_meta)
    request_id = usage.get('provider_request_id')
    model_id = usage.get('model_id') or model_name
    key = _dedupe_key([task.id, 'llm', 'response', request_id or ''])
    payload = _compose_payload(
        {'status': 'succeeded', 'model': model_id},
        None,
        {
            'prompt_tokens': usage.get('input_tokens'),
            'completion_tokens': usage.get('output_tokens'),
            'total_tokens': usage.get('total_tokens'),
        },
        request_id=request_id,
        model_id=model_id,
    )
    return record_usage({
        'dedupe_key': key,
        'task_id': task.id,
        'user_id': task.created_by,
        'project_id': task.creative_project_id,
        'provider': 'llm',
        'model_id': model_id,
        'provider_request_id': request_id,
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
        'total_tokens': usage.get('total_tokens'),
        'usage_unit': 'token' if usage.get('total_tokens') is not None else None,
        'usage_source': 'response_llm',
        'usage_payload': payload,
    })


def get_usage_for_task(task_id):
    db = get_database()
    rows = db.fetch_all(
        'SELECT * FROM ai_model_usage_records WHERE task_id = ? '
        'ORDER BY recorded_at ASC, id ASC',
        (task_id,),
    )
    return [dict(row) for row in rows]
