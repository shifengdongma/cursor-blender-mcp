from __future__ import absolute_import

import json
import os
import time

from .database import get_database
from .models import Tenant, User, Project, ProjectMembership


class TenantService(object):
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

    def list_tenants(self):
        rows = self.db.fetch_all('SELECT * FROM tenants ORDER BY created_at ASC')
        return [Tenant.from_row(row).to_dict() for row in rows]

    def list_users(self, tenant_id=None):
        if tenant_id:
            rows = self.db.fetch_all('SELECT * FROM users WHERE tenant_id = ? ORDER BY created_at ASC', (tenant_id,))
        else:
            rows = self.db.fetch_all('SELECT * FROM users ORDER BY created_at ASC')
        return [User.from_row(row).to_dict() for row in rows]

    def list_projects(self, tenant_id=None):
        if tenant_id:
            rows = self.db.fetch_all('SELECT * FROM projects WHERE tenant_id = ? ORDER BY created_at ASC', (tenant_id,))
        else:
            rows = self.db.fetch_all('SELECT * FROM projects ORDER BY created_at ASC')
        return [Project.from_row(row).to_dict() for row in rows]

    def list_project_members(self, project_id):
        rows = self.db.fetch_all(
            'SELECT * FROM project_memberships WHERE project_id = ? ORDER BY created_at ASC',
            (project_id,)
        )
        memberships = [ProjectMembership.from_row(row).to_dict() for row in rows]
        users = dict((user.get('id'), user) for user in self.list_users())
        for membership in memberships:
            membership['user'] = users.get(membership.get('user_id'))
        return memberships

    def get_context(self, tenant_id=None, user_id=None, project_id=None):
        tenants = self.list_tenants()
        if not tenants:
            return {'tenant': None, 'user': None, 'project': None}

        tenant = None
        for item in tenants:
            if item.get('id') == tenant_id:
                tenant = item
                break
        if tenant is None:
            tenant = tenants[0]

        users = self.list_users(tenant.get('id'))
        user = None
        for item in users:
            if item.get('id') == user_id:
                user = item
                break
        if user is None:
            user = users[0] if users else None

        projects = self.list_projects(tenant.get('id'))
        project = None
        for item in projects:
            if item.get('id') == project_id:
                project = item
                break
        if project is None:
            project = projects[0] if projects else None

        return {
            'tenant': tenant,
            'user': user,
            'project': project,
            'available_users': users,
            'available_projects': projects,
        }

    def check_permission(self, tenant_id, user_id, project_id, permission):
        rows = self.db.fetch_all(
            'SELECT * FROM project_memberships WHERE tenant_id = ? AND user_id = ? AND project_id = ?',
            (tenant_id, user_id, project_id)
        )
        for row in rows:
            membership = ProjectMembership.from_row(row).to_dict()
            permissions = membership.get('permissions') or []
            # Project ownership controls project CRUD, not platform/compute
            # permissions.  Keep this consistent with auth_middleware.
            if permission in permissions:
                return True
        return False


def get_tenant_service(data_dir=None):
    return TenantService(data_dir)
