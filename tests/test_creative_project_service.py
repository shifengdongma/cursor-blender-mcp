# -*- coding: utf-8 -*-
"""Tests for CreativeProjectService."""
from __future__ import absolute_import

import pytest

from backend.creative_project_service import (
    CreativeProjectService,
    get_creative_project_service,
)
from backend.models import CreativeProject


@pytest.fixture
def svc(test_db):
    """Reset service singleton for test isolation."""
    # Insert required FK records
    import time
    now = int(time.time())
    test_db.execute("INSERT OR IGNORE INTO tenants (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     ("t1", "Tenant 1", now, now))
    test_db.execute("INSERT OR IGNORE INTO tenants (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     ("t2", "Tenant 2", now, now))
    test_db.execute("INSERT OR IGNORE INTO users (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("u1", "User 1", "t1", now, now))
    test_db.execute("INSERT OR IGNORE INTO projects (id, name, tenant_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("p1", "Project 1", "t1", now, now))

    import backend.creative_project_service as mod
    old = mod._creative_project_service
    mod._creative_project_service = None
    s = get_creative_project_service()
    yield s
    mod._creative_project_service = old


class TestCreativeProjectService(object):

    def test_create_project(self, svc):
        project = svc.create_project(name="测试项目", tenant_id="t1")
        assert project.id is not None
        assert project.name == "测试项目"
        assert project.status == CreativeProject.STATUS_DRAFT

    def test_get_project(self, svc):
        created = svc.create_project(name="测试项目")
        fetched = svc.get_project(created.id)
        assert fetched is not None
        assert fetched.name == "测试项目"

    def test_get_nonexistent_project(self, svc):
        fetched = svc.get_project("nonexistent")
        assert fetched is None

    def test_list_projects(self, svc):
        svc.create_project(name="项目A", tenant_id="t1")
        svc.create_project(name="项目B", tenant_id="t1")
        svc.create_project(name="项目C", tenant_id="t2")

        result = svc.list_projects(tenant_id="t1")
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_list_projects_pagination(self, svc):
        for i in range(10):
            svc.create_project(name="项目{0}".format(i), tenant_id="t1")

        result = svc.list_projects(tenant_id="t1", limit=3, offset=0)
        assert result["limit"] == 3
        assert result["offset"] == 0
        assert len(result["items"]) == 3

    def test_update_project(self, svc):
        created = svc.create_project(name="原始名称", description="desc1")
        updated = svc.update_project(created.id, name="新名称", description="desc2")
        assert updated is not None
        assert updated.name == "新名称"
        assert updated.description == "desc2"

    def test_update_project_json_fields(self, svc):
        """JSON columns accept dict/list values (frontend save sends requirements as object)."""
        created = svc.create_project(name="原始名称")
        requirements = {"elements": "建筑", "duration": 60, "channels": ["官网"]}
        settings = {"aspect": "16:9"}
        creative_brief = {"beats": [{"title": "开场"}]}

        updated = svc.update_project(
            created.id,
            requirements=requirements,
            settings=settings,
            creative_brief=creative_brief,
        )

        assert updated is not None
        assert updated.requirements == requirements
        assert updated.settings == settings
        assert updated.creative_brief == creative_brief
        assert svc.get_project(created.id).requirements == requirements

    def test_update_nonexistent(self, svc):
        updated = svc.update_project("nonexistent", name="x")
        assert updated is None

    def test_delete_project(self, svc):
        created = svc.create_project(name="待删除")
        success = svc.delete_project(created.id)
        assert success is True
        fetched = svc.get_project(created.id)
        assert fetched is None

    def test_delete_nonexistent(self, svc):
        success = svc.delete_project("nonexistent")
        assert success is False

    def test_tenant_isolation(self, svc):
        svc.create_project(name="租户1项目", tenant_id="t1")
        svc.create_project(name="租户2项目", tenant_id="t2")

        t1_result = svc.list_projects(tenant_id="t1")
        t2_result = svc.list_projects(tenant_id="t2")
        assert t1_result["total"] == 1
        assert t2_result["total"] == 1
        assert t1_result["items"][0]["name"] == "租户1项目"
