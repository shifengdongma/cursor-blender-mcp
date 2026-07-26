# -*- coding: utf-8 -*-
"""Tests for StoryboardService."""
from __future__ import absolute_import

import pytest

from backend.creative_project_service import get_creative_project_service
from backend.storyboard_service import get_storyboard_service


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
    import backend.storyboard_service as mod
    mod._storyboard_service = None
    return get_storyboard_service()


@pytest.fixture
def test_project(project_svc):
    return project_svc.create_project(name="分镜测试项目")


class TestStoryboardService(object):

    def test_create_shot(self, svc, test_project):
        shot = svc.create_shot(
            test_project.id,
            scene_title="开场",
            scene_description="开场描述",
            shot_type="wide-shot",
            duration_s=8,
        )
        assert shot.id is not None
        assert shot.sequence_no == 1
        assert shot.scene_title == "开场"
        assert shot.duration_s == 8

    def test_auto_sequence_no(self, svc, test_project):
        s1 = svc.create_shot(test_project.id, scene_title="Shot 1")
        s2 = svc.create_shot(test_project.id, scene_title="Shot 2")
        s3 = svc.create_shot(test_project.id, scene_title="Shot 3")
        assert s1.sequence_no == 1
        assert s2.sequence_no == 2
        assert s3.sequence_no == 3

    def test_list_shots_ordered(self, svc, test_project):
        svc.create_shot(test_project.id, scene_title="C")
        svc.create_shot(test_project.id, scene_title="A")
        svc.create_shot(test_project.id, scene_title="B")
        shots = svc.list_shots(test_project.id)
        assert len(shots) == 3
        assert shots[0].sequence_no == 1
        assert shots[1].sequence_no == 2
        assert shots[2].sequence_no == 3

    def test_get_shot(self, svc, test_project):
        created = svc.create_shot(test_project.id, scene_title="测试镜头")
        fetched = svc.get_shot(created.id)
        assert fetched is not None
        assert fetched.scene_title == "测试镜头"

    def test_get_nonexistent(self, svc):
        assert svc.get_shot("nonexistent") is None

    def test_update_shot(self, svc, test_project):
        created = svc.create_shot(test_project.id, scene_title="原始")
        updated = svc.update_shot(created.id, scene_title="更新后", duration_s=10)
        assert updated.scene_title == "更新后"
        assert updated.duration_s == 10

    def test_delete_shot(self, svc, test_project):
        created = svc.create_shot(test_project.id, scene_title="待删除")
        assert svc.delete_shot(created.id) is True
        assert svc.get_shot(created.id) is None

    def test_reorder_shots(self, svc, test_project):
        s1 = svc.create_shot(test_project.id, scene_title="First")
        s2 = svc.create_shot(test_project.id, scene_title="Second")
        s3 = svc.create_shot(test_project.id, scene_title="Third")

        # Reverse order: s3, s1, s2
        svc.reorder_shots(test_project.id, [s3.id, s1.id, s2.id])

        shots = svc.list_shots(test_project.id)
        assert shots[0].id == s3.id
        assert shots[0].sequence_no == 1
        assert shots[1].id == s1.id
        assert shots[1].sequence_no == 2
        assert shots[2].id == s2.id
        assert shots[2].sequence_no == 3

    def test_bulk_create(self, svc, test_project):
        data = [
            {"scene_title": "Bulk 1", "duration_s": 5},
            {"scene_title": "Bulk 2", "duration_s": 8},
        ]
        shots = svc.bulk_create_shots(test_project.id, data)
        assert len(shots) == 2
        assert shots[0].sequence_no == 1
        assert shots[1].sequence_no == 2
