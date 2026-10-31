# -*- coding: utf-8 -*-
"""Tests for provider-reported usage capture and NULL/no-invention rules."""
from __future__ import absolute_import

import json

from backend.models import GenerationTask
from backend.usage_records import (
    get_usage_for_task,
    record_image_usage,
    record_llm_usage,
    record_video_submission,
    record_video_usage,
)


def _task(task_id='task-1', task_type='image', provider='ark_seedream',
          model_id='doubao-seedream-5-0-pro'):
    return GenerationTask(
        id=task_id, task_type=task_type, provider=provider, model_id=model_id,
        created_by='user-1', creative_project_id='project-1',
    )


def test_image_usage_uses_generated_images_and_redacts_urls(test_db):
    task = _task()
    raw = {
        'data': [{'url': 'https://secret.example/image.png'}],
        'usage': {
            'generated_images': 2,
            'input_images': 1,
            'output_tokens': 100,
            'total_tokens': 100,
            'tool_usage': {'web_search': 0},
        },
    }
    record_image_usage(task, ['a.png', 'b.png'], raw, provider_request_id='req-image')
    rows = get_usage_for_task('task-1')
    assert len(rows) == 1
    row = rows[0]
    assert row['image_count'] == 2
    assert row['output_tokens'] == 100
    assert row['total_tokens'] == 100
    assert row['usage_source'] == 'response'
    assert row['provider_request_id'] == 'req-image'
    assert 'secret.example' not in (row['usage_payload'] or '')
    payload = json.loads(row['usage_payload'])
    assert payload['usage']['image_count'] == 2


def test_image_usage_without_usage_field_does_not_invent_tokens(test_db):
    task = _task(task_id='task-image-2')
    raw = {'data': [{'url': 'https://secret.example/image.png'}]}
    record_image_usage(task, ['a.png', 'b.png'], raw)
    row = get_usage_for_task('task-image-2')[0]
    assert row['image_count'] == 2
    assert row['output_tokens'] is None
    assert row['total_tokens'] is None
    payload = json.loads(row['usage_payload'])
    assert payload['image_count_source'] == 'response_data_length'


def test_video_usage_submission_and_poll_update_one_record(test_db):
    task = _task(
        task_id='task-video', task_type='video', provider='ark_seedance',
        model_id='doubao-seedance-2-0-260128',
    )
    created = {'id': 'cgt-1', '_request_id': 'req-video'}
    record_video_submission(
        task, created, provider_job_id='cgt-1', provider_request_id='req-video'
    )
    polled = {
        'id': 'cgt-1',
        'status': 'succeeded',
        'duration': 5,
        'resolution': '720p',
        'content': {'video_url': 'https://secret.example/video.mp4'},
        'usage': {'completion_tokens': 500, 'total_tokens': 500},
    }
    record_video_usage(
        task, polled, provider_job_id='cgt-1', provider_request_id='req-video'
    )
    rows = get_usage_for_task('task-video')
    assert len(rows) == 1
    row = rows[0]
    assert row['output_tokens'] == 500
    assert row['total_tokens'] == 500
    assert row['input_tokens'] is None
    assert row['video_duration_s'] == 5.0
    assert row['usage_source'] == 'response_poll'
    assert row['provider_job_id'] == 'cgt-1'
    assert 'secret.example' not in (row['usage_payload'] or '')

    # A later poll without usage metrics must not erase the previously
    # provider-reported values.
    record_video_usage(task, {'id': 'cgt-1', 'status': 'succeeded'}, provider_job_id='cgt-1')
    row = get_usage_for_task('task-video')[0]
    assert row['output_tokens'] == 500
    assert row['total_tokens'] == 500


def test_llm_usage_and_no_metadata_does_not_create_record(test_db):
    task = _task(task_id='task-llm', task_type='storyboard', provider=None, model_id=None)
    record_llm_usage(task, 'gpt-4o', {
        'id': 'req-llm', 'model': 'gpt-4o',
        'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30},
    })
    rows = get_usage_for_task('task-llm')
    assert len(rows) == 1
    row = rows[0]
    assert row['provider'] == 'llm'
    assert row['input_tokens'] == 10
    assert row['output_tokens'] == 20
    assert row['total_tokens'] == 30
    assert row['provider_request_id'] == 'req-llm'

    assert record_llm_usage(task, 'gpt-4o', None) is None
    assert len(get_usage_for_task('task-llm')) == 1


def test_image_usage_is_idempotent(test_db):
    task = _task(task_id='task-idempotent')
    raw = {'usage': {'generated_images': 1, 'total_tokens': 5}}
    record_image_usage(task, ['a.png'], raw)
    record_image_usage(task, ['a.png'], raw)
    rows = get_usage_for_task('task-idempotent')
    assert len(rows) == 1
    assert rows[0]['image_count'] == 1


def test_non_ark_provider_does_not_create_volcengine_usage(test_db):
    task = _task(task_id='task-openai', provider='openai_image')
    assert record_image_usage(task, ['a.png'], {'usage': {'generated_images': 1}}) is None
    assert get_usage_for_task('task-openai') == []
