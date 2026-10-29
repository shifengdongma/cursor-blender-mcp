# -*- coding: utf-8 -*-
"""Legacy creative worker: recovery, cancellation, asset ownership, quotas."""
from __future__ import absolute_import

from backend import storyboard_service, task_worker
from backend.access import can_read_asset
from backend.asset_service import get_asset_service
from backend.creative_project_service import get_creative_project_service
from backend.credential_service import CredentialService
from backend.database import get_database
from backend.models import CreativeProject, GenerationTask
from backend.providers.base import ProviderError
from backend.task_service import get_task_service
from tests import support

PUBLIC_BASE_URL = "https://93.184.216.34/v1"


def _setup(app, username):
    cfg = app.config["AIGV_CONFIG"]
    user = support.create_admin(
        cfg.DATA_DIR, username=username, email="{0}@example.com".format(username)
    )
    return cfg, user


def _create_project(cfg, user, status=CreativeProject.STATUS_DRAFT):
    return get_creative_project_service(cfg.DATA_DIR).create_project(
        name="Legacy project",
        tenant_id=user.get("tenant_id"),
        user_id=user["id"],
        status=status,
    )


def _create_task(cfg, user, project, task_type, status=GenerationTask.STATUS_QUEUED,
                 params=None):
    task_service = get_task_service(cfg.DATA_DIR)
    task = task_service.create_task(
        creative_project_id=project.id,
        task_type=task_type,
        created_by=user["id"],
        params=params,
    )
    if status != GenerationTask.STATUS_QUEUED:
        task_service.update_task(task.id, status=status)
    return task_service.get_task(task.id)


def test_recovery_fails_orphaned_running_task_and_unsticks_project(app):
    cfg, user = _setup(app, "recover_orphan")
    project = _create_project(cfg, user, status=CreativeProject.STATUS_ANALYZING)
    task = _create_task(
        cfg, user, project, GenerationTask.TYPE_STORYBOARD,
        status=GenerationTask.STATUS_RUNNING,
    )

    result = task_worker.recover_orphaned_legacy_tasks(get_task_service(cfg.DATA_DIR))

    refreshed = get_task_service(cfg.DATA_DIR).get_task(task.id)
    assert refreshed.status == GenerationTask.STATUS_FAILED
    assert refreshed.error_code == "worker_restarted"
    assert refreshed.completed_at
    assert (
        get_creative_project_service(cfg.DATA_DIR).get_project(project.id).status
        == CreativeProject.STATUS_DRAFT
    )
    assert result["tasks"] >= 1
    assert result["projects"] >= 1


def test_recovery_keeps_project_analyzing_while_another_task_is_active(app):
    cfg, user = _setup(app, "recover_active")
    project = _create_project(cfg, user, status=CreativeProject.STATUS_ANALYZING)
    _create_task(
        cfg, user, project, GenerationTask.TYPE_STORYBOARD,
        status=GenerationTask.STATUS_RUNNING,
    )
    _create_task(cfg, user, project, GenerationTask.TYPE_TTS)

    task_worker.recover_orphaned_legacy_tasks(get_task_service(cfg.DATA_DIR))

    assert (
        get_creative_project_service(cfg.DATA_DIR).get_project(project.id).status
        == CreativeProject.STATUS_ANALYZING
    )


def test_failed_storyboard_executor_resets_analyzing_project(app, monkeypatch):
    cfg, user = _setup(app, "recover_failure")
    CredentialService(cfg.DATA_DIR, cfg).upsert(
        user["id"], user.get("tenant_id"), "llm",
        api_key="sk-user-reset-1", base_url=PUBLIC_BASE_URL,
    )
    project = _create_project(cfg, user)
    task = _create_task(
        cfg, user, project, GenerationTask.TYPE_STORYBOARD,
        status=GenerationTask.STATUS_RUNNING,
        params={"project_id": project.id, "credential_source": "user"},
    )

    class FailingLLM(object):
        def __init__(self, *args, **kwargs):
            pass

        def generate_structured(self, system_prompt, user_prompt, schema):
            raise ProviderError("upstream exploded", error_type="llm_server_error")

    monkeypatch.setattr(task_worker, "LLMProvider", FailingLLM)
    task_worker._process_task(
        get_task_service(cfg.DATA_DIR), cfg, get_database(), task
    )

    refreshed = get_task_service(cfg.DATA_DIR).get_task(task.id)
    assert refreshed.status == GenerationTask.STATUS_FAILED
    assert refreshed.error_code == "llm_server_error"
    assert (
        get_creative_project_service(cfg.DATA_DIR).get_project(project.id).status
        == CreativeProject.STATUS_DRAFT
    )


def test_cancelled_task_is_not_executed(app, monkeypatch):
    cfg, user = _setup(app, "cancel_before")
    project = _create_project(cfg, user)
    task_service = get_task_service(cfg.DATA_DIR)
    _create_task(cfg, user, project, GenerationTask.TYPE_EXPORT)

    claimed = task_service.claim_next_task(
        task_types=(GenerationTask.TYPE_EXPORT,)
    )
    assert claimed is not None and claimed.status == GenerationTask.STATUS_RUNNING
    assert task_service.cancel_task(claimed.id) is True

    called = []
    monkeypatch.setitem(
        task_worker.EXECUTOR_MAP,
        GenerationTask.TYPE_EXPORT,
        lambda *args: called.append(True),
    )
    task_worker._process_task(
        task_service, cfg, get_database(), claimed
    )

    assert called == []
    assert task_service.get_task(claimed.id).status == GenerationTask.STATUS_CANCELLED


def test_legacy_tts_asset_is_private_and_owner_scoped(app, monkeypatch):
    cfg, user = _setup(app, "tts_owner")
    project = _create_project(cfg, user)
    storyboard_service.get_storyboard_service(cfg.DATA_DIR).create_shot(
        project.id,
        scene_title="Narration shot",
        dialogue="hello world",
        duration_s=2,
    )
    task = _create_task(cfg, user, project, GenerationTask.TYPE_TTS)

    class FakeTTS(object):
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, text, voice_id, output_path):
            with open(output_path, "wb") as handle:
                handle.write(b"RIFF0000WAVEfmt ")
            return {"duration_s": 1.0, "format": "wav"}

    monkeypatch.setattr(task_worker, "PiperTTSProvider", FakeTTS)

    result = task_worker._execute_tts(task, cfg, get_database())

    asset = get_asset_service(cfg.DATA_DIR).get_asset(
        result["audio_assets"][0]["asset_id"]
    )
    assert asset is not None
    assert asset.owner_user_id == user["id"]
    assert asset.tenant_id == user["tenant_id"]
    assert asset.visibility == "private"
    other_user = {
        "id": "another-user",
        "tenant_id": user["tenant_id"],
        "role": "user",
    }
    assert can_read_asset(asset, other_user) is False
    assert can_read_asset(asset, user) is True


def test_legacy_task_cap_per_user(app):
    cfg, user = _setup(app, "legacy_cap")
    project = _create_project(cfg, user)
    task_service = get_task_service(cfg.DATA_DIR)
    for _index in range(cfg.MAX_ACTIVE_LEGACY_TASKS_PER_USER):
        _create_task(cfg, user, project, GenerationTask.TYPE_EXPORT)

    client = app.test_client()
    _user, token = support.login_and_token(
        client, "legacy_cap", password="AdminPass12345"
    )
    response = client.post(
        "/api/creative/projects/{0}/exports".format(project.id),
        headers=support.auth_headers(token),
    )
    assert response.status_code == 429, response.get_json()
    assert response.get_json()["error"] == "quota_exceeded"
