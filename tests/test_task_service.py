# -*- coding: utf-8 -*-
"""Tests for TaskService."""
from __future__ import absolute_import

import pytest

from backend.creative_project_service import get_creative_project_service
from backend.models import GenerationTask
from backend.task_service import get_task_service


@pytest.fixture
def project_svc(test_db):
    import time
    now = int(time.time())
    test_db.execute("INSERT OR IGNORE INTO tenants (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     ("t1", "Tenant 1", now, now))
    test_db.execute("INSERT OR IGNORE INTO users (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("u1", "User 1", "t1", now, now))
    test_db.execute("INSERT OR IGNORE INTO projects (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("p1", "Project 1", "t1", now, now))
    import backend.creative_project_service as mod
    mod._creative_project_service = None
    return get_creative_project_service()


@pytest.fixture
def svc(test_db):
    import backend.task_service as mod
    mod._task_service = None
    return get_task_service()


@pytest.fixture
def test_project(project_svc):
    return project_svc.create_project(name="Task测试")


class TestTaskService(object):

    def test_create_task(self, svc, test_project):
        task = svc.create_task(
            test_project.id,
            GenerationTask.TYPE_STORYBOARD,
            params={"key": "value"},
        )
        assert task.id is not None
        assert task.task_type == GenerationTask.TYPE_STORYBOARD
        assert task.status == GenerationTask.STATUS_QUEUED
        assert task.params == {"key": "value"}

    def test_get_task(self, svc, test_project):
        created = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        fetched = svc.get_task(created.id)
        assert fetched is not None
        assert fetched.task_type == GenerationTask.TYPE_IMAGE

    def test_get_nonexistent(self, svc):
        assert svc.get_task("nonexistent") is None

    def test_list_tasks(self, svc, test_project):
        svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.create_task(test_project.id, GenerationTask.TYPE_VIDEO)
        svc.create_task(test_project.id, GenerationTask.TYPE_TTS)

        result = svc.list_tasks(creative_project_id=test_project.id)
        assert result["total"] == 3
        assert len(result["items"]) == 3

    def test_list_tasks_by_type(self, svc, test_project):
        svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.create_task(test_project.id, GenerationTask.TYPE_VIDEO)

        result = svc.list_tasks(creative_project_id=test_project.id, task_type=GenerationTask.TYPE_IMAGE)
        assert result["total"] == 2

    def test_claim_next_task(self, svc, test_project):
        t1 = svc.create_task(test_project.id, GenerationTask.TYPE_STORYBOARD)
        t2 = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)

        claimed = svc.claim_next_task()
        assert claimed is not None
        assert claimed.id == t1.id
        assert claimed.status == GenerationTask.STATUS_RUNNING
        assert claimed.claimed_at is not None

        claimed2 = svc.claim_next_task()
        assert claimed2.id == t2.id

    def test_claim_empty_queue(self, svc):
        claimed = svc.claim_next_task()
        assert claimed is None

    def test_claim_only_queued(self, svc, test_project):
        svc.create_task(test_project.id, GenerationTask.TYPE_STORYBOARD)
        # Manually set one to running
        from backend.database import get_database
        get_database().update(
            "generation_tasks",
            {"status": "running"},
            "status = ?",
            ("queued",),
        )
        claimed = svc.claim_next_task()
        assert claimed is None

    def test_update_task(self, svc, test_project):
        task = svc.create_task(test_project.id, GenerationTask.TYPE_COMPOSE)
        updated = svc.update_task(
            task.id,
            status=GenerationTask.STATUS_SUCCEEDED,
            progress=100,
            result_payload={"done": True},
        )
        assert updated.status == GenerationTask.STATUS_SUCCEEDED
        assert updated.progress == 100
        assert updated.result_payload == {"done": True}

    def test_cancel_task(self, svc, test_project):
        task = svc.create_task(test_project.id, GenerationTask.TYPE_VIDEO)
        success = svc.cancel_task(task.id)
        assert success is True
        cancelled = svc.get_task(task.id)
        assert cancelled.status == GenerationTask.STATUS_CANCELLED
        assert cancelled.completed_at is not None

    def test_cancel_already_completed(self, svc, test_project):
        task = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.update_task(task.id, status=GenerationTask.STATUS_SUCCEEDED)
        success = svc.cancel_task(task.id)
        assert success is False

    def test_add_artifact(self, svc, test_project):
        task = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        artifact = svc.add_artifact(
            task.id,
            test_project.id,
            name="test_image.png",
            artifact_type="image",
            file_path="/tmp/test.png",
            file_size=1024,
        )
        assert artifact.id is not None
        assert artifact.name == "test_image.png"
        assert artifact.file_size == 1024

    def test_list_artifacts(self, svc, test_project):
        task = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.add_artifact(task.id, test_project.id, "img1.png", "image")
        svc.add_artifact(task.id, test_project.id, "img2.png", "image")

        artifacts = svc.list_artifacts(creative_project_id=test_project.id)
        assert len(artifacts) == 2

    def test_list_artifacts_by_task(self, svc, test_project):
        t1 = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        t2 = svc.create_task(test_project.id, GenerationTask.TYPE_IMAGE)
        svc.add_artifact(t1.id, test_project.id, "a1", "image")
        svc.add_artifact(t2.id, test_project.id, "a2", "image")

        artifacts = svc.list_artifacts(task_id=t1.id)
        assert len(artifacts) == 1
        assert artifacts[0].name == "a1"
