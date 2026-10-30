# -*- coding: utf-8 -*-
"""Object-level access helpers for projects, shots, tasks, assets and jobs."""
from __future__ import absolute_import

from flask import g

from .auth_middleware import is_admin
from .database import get_database
from .http_utils import ApiError
from .models import Asset, CreativeProject, GenerationTask, StoryboardShot


def current_user():
    return getattr(g, "current_user", None)


def _user_or_401():
    user = current_user()
    if not user:
        raise ApiError("unauthorized", "请先登录", status_code=401)
    return user


def require_project(project_id, write=False, demo_mode=False):
    user = _user_or_401()
    row = get_database().fetch_one(
        "SELECT * FROM creative_projects WHERE id = ?", (project_id,)
    )
    if not row:
        raise ApiError("project_not_found", "项目不存在", status_code=404)
    project = CreativeProject.from_row(row)
    if is_admin(user):
        return project
    if project.user_id and project.user_id != user.get("id"):
        raise ApiError("forbidden", "无权访问该项目", status_code=403)
    if not project.user_id and write:
        raise ApiError("forbidden", "无权修改共享演示项目", status_code=403)
    if not project.user_id and not demo_mode:
        raise ApiError("forbidden", "无权访问该项目", status_code=403)
    return project


def require_shot(shot_id, write=False, demo_mode=False):
    user = _user_or_401()
    row = get_database().fetch_one(
        "SELECT * FROM storyboard_shots WHERE id = ?", (shot_id,)
    )
    if not row:
        raise ApiError("shot_not_found", "分镜不存在", status_code=404)
    shot = StoryboardShot.from_row(row)
    project = require_project(shot.creative_project_id, write=write, demo_mode=demo_mode)
    return shot, project


def require_task(task_id, write=False, demo_mode=False, creator_only=False):
    user = _user_or_401()
    row = get_database().fetch_one(
        "SELECT * FROM generation_tasks WHERE id = ?", (task_id,)
    )
    if not row:
        raise ApiError("task_not_found", "任务不存在", status_code=404)
    task = GenerationTask.from_row(row)
    if is_admin(user):
        return task
    if task.created_by and task.created_by == user.get("id"):
        return task
    if not creator_only and task.creative_project_id:
        project_row = get_database().fetch_one(
            "SELECT * FROM creative_projects WHERE id = ?", (task.creative_project_id,)
        )
        if project_row and project_row.get("user_id") == user.get("id"):
            return task
    if not creator_only and not task.created_by and demo_mode:
        return task
    raise ApiError("forbidden", "无权访问该任务", status_code=403)


def can_read_asset(asset, user, demo_mode=False):
    if not asset:
        return False
    user = user or {}
    if is_admin(user):
        return True
    if asset.owner_user_id:
        if asset.owner_user_id == user.get("id"):
            return True
        # Owned shared assets are visible to the owner's tenant only.
        if asset.visibility == "shared":
            return asset.tenant_id is None or asset.tenant_id == user.get("tenant_id")
        return False
    # Unowned legacy assets are the shared asset library.
    return asset.visibility == "shared" or demo_mode


def can_write_asset(asset, user):
    if not asset:
        return False
    if is_admin(user):
        return True
    return bool(asset.owner_user_id and asset.owner_user_id == user.get("id"))


def require_asset(asset_id, write=False, demo_mode=False):
    user = _user_or_401()
    row = get_database().fetch_one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not row:
        raise ApiError("asset_not_found", "资产不存在", status_code=404)
    asset = Asset.from_row(row)
    allowed = can_write_asset(asset, user) if write else can_read_asset(asset, user, demo_mode)
    if not allowed:
        raise ApiError("forbidden", "无权访问该资产", status_code=403)
    return asset


def job_visible(job, user, demo_mode=False):
    if not job or not user:
        return False
    if is_admin(user):
        return True
    owner = job.get("owner_user_id")
    if owner:
        return owner == user.get("id")
    return bool(demo_mode)


def require_job(job, demo_mode=False):
    _user_or_401()
    if not job:
        raise ApiError("job_not_found", "任务不存在", status_code=404)
    if not job_visible(job, current_user(), demo_mode):
        raise ApiError("forbidden", "无权访问该任务", status_code=403)
    return job
