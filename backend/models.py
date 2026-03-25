# -*- coding: utf-8 -*-
"""
Data models for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import time
import uuid


def _now():
    """Return current timestamp as integer."""
    return int(time.time())


def _generate_id():
    """Generate a unique ID."""
    return str(uuid.uuid4())


def _json_dumps(obj):
    """Safely serialize object to JSON string."""
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(s):
    """Safely deserialize JSON string to object."""
    if s is None or s == '':
        return None
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return None


class BaseModel(object):
    """Base model with common methods."""

    TABLE_NAME = None
    COLUMNS = []

    @classmethod
    def from_row(cls, row):
        raise NotImplementedError

    def to_dict(self):
        raise NotImplementedError

    def to_insert_params(self):
        raise NotImplementedError


class Asset(BaseModel):
    TABLE_NAME = 'assets'
    COLUMNS = [
        'id', 'name', 'asset_type', 'venue_type', 'file_path',
        'file_size', 'description', 'metadata', 'thumbnail_path',
        'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.name = kwargs.get('name', '')
        self.asset_type = kwargs.get('asset_type', 'glb')
        self.venue_type = kwargs.get('venue_type')
        self.file_path = kwargs.get('file_path')
        self.file_size = kwargs.get('file_size', 0)
        self.description = kwargs.get('description')
        self.metadata = kwargs.get('metadata')
        self.thumbnail_path = kwargs.get('thumbnail_path')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            name=row.get('name'),
            asset_type=row.get('asset_type'),
            venue_type=row.get('venue_type'),
            file_path=row.get('file_path'),
            file_size=row.get('file_size'),
            description=row.get('description'),
            metadata=_json_loads(row.get('metadata')),
            thumbnail_path=row.get('thumbnail_path'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'asset_type': self.asset_type,
            'venue_type': self.venue_type,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'description': self.description,
            'metadata': self.metadata,
            'thumbnail_path': self.thumbnail_path,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'name': self.name,
            'asset_type': self.asset_type,
            'venue_type': self.venue_type,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'description': self.description,
            'metadata': _json_dumps(self.metadata),
            'thumbnail_path': self.thumbnail_path,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class PromptDocument(BaseModel):
    TABLE_NAME = 'prompt_documents'
    COLUMNS = [
        'id', 'title', 'category', 'content', 'keywords',
        'source_file', 'created_at', 'updated_at'
    ]

    CATEGORY_VENUE = 'venue'
    CATEGORY_SHOT = 'shot'
    CATEGORY_LIGHTING = 'lighting'
    CATEGORY_STYLE = 'style'
    CATEGORY_SUBJECT = 'subject'
    CATEGORY_DYNAMICS = 'dynamics'
    CATEGORY_ENVIRONMENT = 'environment'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.title = kwargs.get('title', '')
        self.category = kwargs.get('category')
        self.content = kwargs.get('content')
        self.keywords = kwargs.get('keywords')
        self.source_file = kwargs.get('source_file')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            title=row.get('title'),
            category=row.get('category'),
            content=row.get('content'),
            keywords=row.get('keywords'),
            source_file=row.get('source_file'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'category': self.category,
            'content': self.content,
            'keywords': self.keywords,
            'source_file': self.source_file,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'title': self.title,
            'category': self.category,
            'content': self.content,
            'keywords': self.keywords,
            'source_file': self.source_file,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class VenuePreset(BaseModel):
    TABLE_NAME = 'venue_presets'
    COLUMNS = [
        'id', 'name', 'description', 'default_environment',
        'default_lighting', 'default_style', 'camera_defaults',
        'negative_prompt_parts', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.name = kwargs.get('name', '')
        self.description = kwargs.get('description')
        self.default_environment = kwargs.get('default_environment')
        self.default_lighting = kwargs.get('default_lighting')
        self.default_style = kwargs.get('default_style')
        self.camera_defaults = kwargs.get('camera_defaults')
        self.negative_prompt_parts = kwargs.get('negative_prompt_parts')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            name=row.get('name'),
            description=row.get('description'),
            default_environment=row.get('default_environment'),
            default_lighting=row.get('default_lighting'),
            default_style=row.get('default_style'),
            camera_defaults=_json_loads(row.get('camera_defaults')),
            negative_prompt_parts=row.get('negative_prompt_parts'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'default_environment': self.default_environment,
            'default_lighting': self.default_lighting,
            'default_style': self.default_style,
            'camera_defaults': self.camera_defaults,
            'negative_prompt_parts': self.negative_prompt_parts,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'default_environment': self.default_environment,
            'default_lighting': self.default_lighting,
            'default_style': self.default_style,
            'camera_defaults': _json_dumps(self.camera_defaults),
            'negative_prompt_parts': self.negative_prompt_parts,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class ModelConfig(BaseModel):
    TABLE_NAME = 'model_configs'
    COLUMNS = [
        'id', 'display_model', 'execution_provider', 'route_mode',
        'status', 'description', 'style_hint', 'recommended',
        'created_at', 'updated_at'
    ]

    ROUTE_NATIVE = 'native'
    ROUTE_DEMO = 'demo-route'
    ROUTE_PREVIEW = 'preview-only'
    ROUTE_OPTIONAL = 'optional'

    STATUS_ACTIVE = 'active'
    STATUS_SHOWCASE = 'showcase'
    STATUS_OPTIONAL = 'optional'
    STATUS_PLACEHOLDER = 'placeholder'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.display_model = kwargs.get('display_model', '')
        self.execution_provider = kwargs.get('execution_provider')
        self.route_mode = kwargs.get('route_mode')
        self.status = kwargs.get('status')
        self.description = kwargs.get('description')
        self.style_hint = kwargs.get('style_hint')
        self.recommended = kwargs.get('recommended', 0)
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            display_model=row.get('display_model'),
            execution_provider=row.get('execution_provider'),
            route_mode=row.get('route_mode'),
            status=row.get('status'),
            description=row.get('description'),
            style_hint=row.get('style_hint'),
            recommended=row.get('recommended', 0),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'display_model': self.display_model,
            'execution_provider': self.execution_provider,
            'route_mode': self.route_mode,
            'status': self.status,
            'description': self.description,
            'style_hint': self.style_hint,
            'recommended': bool(self.recommended),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'display_model': self.display_model,
            'execution_provider': self.execution_provider,
            'route_mode': self.route_mode,
            'status': self.status,
            'description': self.description,
            'style_hint': self.style_hint,
            'recommended': 1 if self.recommended else 0,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class JobHistory(BaseModel):
    TABLE_NAME = 'job_history'
    COLUMNS = [
        'id', 'status', 'stage', 'payload', 'result',
        'error', 'created_at', 'updated_at'
    ]

    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_ERROR = 'error'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.status = kwargs.get('status')
        self.stage = kwargs.get('stage')
        self.payload = kwargs.get('payload')
        self.result = kwargs.get('result')
        self.error = kwargs.get('error')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            status=row.get('status'),
            stage=row.get('stage'),
            payload=_json_loads(row.get('payload')),
            result=_json_loads(row.get('result')),
            error=row.get('error'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'stage': self.stage,
            'payload': self.payload,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'status': self.status,
            'stage': self.stage,
            'payload': _json_dumps(self.payload),
            'result': _json_dumps(self.result),
            'error': self.error,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Tenant(BaseModel):
    TABLE_NAME = 'tenants'
    COLUMNS = ['id', 'name', 'code', 'tier', 'status', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.name = kwargs.get('name', '')
        self.code = kwargs.get('code')
        self.tier = kwargs.get('tier')
        self.status = kwargs.get('status')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            name=row.get('name'),
            code=row.get('code'),
            tier=row.get('tier'),
            status=row.get('status'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'tier': self.tier,
            'status': self.status,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'tier': self.tier,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class User(BaseModel):
    TABLE_NAME = 'users'
    COLUMNS = ['id', 'tenant_id', 'name', 'role', 'title', 'status', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.name = kwargs.get('name', '')
        self.role = kwargs.get('role')
        self.title = kwargs.get('title')
        self.status = kwargs.get('status')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            name=row.get('name'),
            role=row.get('role'),
            title=row.get('title'),
            status=row.get('status'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'role': self.role,
            'title': self.title,
            'status': self.status,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'role': self.role,
            'title': self.title,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Project(BaseModel):
    TABLE_NAME = 'projects'
    COLUMNS = ['id', 'tenant_id', 'name', 'code', 'status', 'render_mode', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.name = kwargs.get('name', '')
        self.code = kwargs.get('code')
        self.status = kwargs.get('status')
        self.render_mode = kwargs.get('render_mode')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            name=row.get('name'),
            code=row.get('code'),
            status=row.get('status'),
            render_mode=row.get('render_mode'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'code': self.code,
            'status': self.status,
            'render_mode': self.render_mode,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'code': self.code,
            'status': self.status,
            'render_mode': self.render_mode,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class ProjectMembership(BaseModel):
    TABLE_NAME = 'project_memberships'
    COLUMNS = ['id', 'project_id', 'user_id', 'tenant_id', 'role', 'permissions', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.project_id = kwargs.get('project_id')
        self.user_id = kwargs.get('user_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.role = kwargs.get('role')
        self.permissions = kwargs.get('permissions')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            project_id=row.get('project_id'),
            user_id=row.get('user_id'),
            tenant_id=row.get('tenant_id'),
            role=row.get('role'),
            permissions=_json_loads(row.get('permissions')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'tenant_id': self.tenant_id,
            'role': self.role,
            'permissions': self.permissions,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'tenant_id': self.tenant_id,
            'role': self.role,
            'permissions': _json_dumps(self.permissions),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Resource(BaseModel):
    TABLE_NAME = 'resources'
    COLUMNS = ['id', 'tenant_id', 'node_name', 'pool_type', 'region', 'gpu_type', 'capacity_units', 'queue_depth', 'status', 'utilization_hint', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.node_name = kwargs.get('node_name', '')
        self.pool_type = kwargs.get('pool_type')
        self.region = kwargs.get('region')
        self.gpu_type = kwargs.get('gpu_type')
        self.capacity_units = kwargs.get('capacity_units', 0)
        self.queue_depth = kwargs.get('queue_depth', 0)
        self.status = kwargs.get('status')
        self.utilization_hint = kwargs.get('utilization_hint', 0.0)
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            node_name=row.get('node_name'),
            pool_type=row.get('pool_type'),
            region=row.get('region'),
            gpu_type=row.get('gpu_type'),
            capacity_units=row.get('capacity_units'),
            queue_depth=row.get('queue_depth'),
            status=row.get('status'),
            utilization_hint=row.get('utilization_hint'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'node_name': self.node_name,
            'pool_type': self.pool_type,
            'region': self.region,
            'gpu_type': self.gpu_type,
            'capacity_units': self.capacity_units,
            'queue_depth': self.queue_depth,
            'status': self.status,
            'utilization_hint': self.utilization_hint,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'node_name': self.node_name,
            'pool_type': self.pool_type,
            'region': self.region,
            'gpu_type': self.gpu_type,
            'capacity_units': self.capacity_units,
            'queue_depth': self.queue_depth,
            'status': self.status,
            'utilization_hint': self.utilization_hint,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class ResourceAllocation(BaseModel):
    TABLE_NAME = 'resource_allocations'
    COLUMNS = ['id', 'job_id', 'resource_id', 'tenant_id', 'project_id', 'decision_reason', 'allocation_status', 'snapshot', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.job_id = kwargs.get('job_id')
        self.resource_id = kwargs.get('resource_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.decision_reason = kwargs.get('decision_reason')
        self.allocation_status = kwargs.get('allocation_status')
        self.snapshot = kwargs.get('snapshot')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            job_id=row.get('job_id'),
            resource_id=row.get('resource_id'),
            tenant_id=row.get('tenant_id'),
            project_id=row.get('project_id'),
            decision_reason=row.get('decision_reason'),
            allocation_status=row.get('allocation_status'),
            snapshot=_json_loads(row.get('snapshot')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'resource_id': self.resource_id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'decision_reason': self.decision_reason,
            'allocation_status': self.allocation_status,
            'snapshot': self.snapshot,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'resource_id': self.resource_id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'decision_reason': self.decision_reason,
            'allocation_status': self.allocation_status,
            'snapshot': _json_dumps(self.snapshot),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class EngineProfile(BaseModel):
    TABLE_NAME = 'engine_profiles'
    COLUMNS = ['id', 'engine_type', 'display_name', 'render_mode', 'stream_mode', 'status', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.engine_type = kwargs.get('engine_type', '')
        self.display_name = kwargs.get('display_name')
        self.render_mode = kwargs.get('render_mode')
        self.stream_mode = kwargs.get('stream_mode')
        self.status = kwargs.get('status')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            engine_type=row.get('engine_type'),
            display_name=row.get('display_name'),
            render_mode=row.get('render_mode'),
            stream_mode=row.get('stream_mode'),
            status=row.get('status'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'engine_type': self.engine_type,
            'display_name': self.display_name,
            'render_mode': self.render_mode,
            'stream_mode': self.stream_mode,
            'status': self.status,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'engine_type': self.engine_type,
            'display_name': self.display_name,
            'render_mode': self.render_mode,
            'stream_mode': self.stream_mode,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class StreamSession(BaseModel):
    TABLE_NAME = 'stream_sessions'
    COLUMNS = ['id', 'job_id', 'project_id', 'engine_profile_id', 'protocol', 'bitrate_mbps', 'latency_ms', 'fps', 'preview_url', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.job_id = kwargs.get('job_id')
        self.project_id = kwargs.get('project_id')
        self.engine_profile_id = kwargs.get('engine_profile_id')
        self.protocol = kwargs.get('protocol')
        self.bitrate_mbps = kwargs.get('bitrate_mbps', 0.0)
        self.latency_ms = kwargs.get('latency_ms', 0)
        self.fps = kwargs.get('fps', 0)
        self.preview_url = kwargs.get('preview_url')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            job_id=row.get('job_id'),
            project_id=row.get('project_id'),
            engine_profile_id=row.get('engine_profile_id'),
            protocol=row.get('protocol'),
            bitrate_mbps=row.get('bitrate_mbps'),
            latency_ms=row.get('latency_ms'),
            fps=row.get('fps'),
            preview_url=row.get('preview_url'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'project_id': self.project_id,
            'engine_profile_id': self.engine_profile_id,
            'protocol': self.protocol,
            'bitrate_mbps': self.bitrate_mbps,
            'latency_ms': self.latency_ms,
            'fps': self.fps,
            'preview_url': self.preview_url,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'project_id': self.project_id,
            'engine_profile_id': self.engine_profile_id,
            'protocol': self.protocol,
            'bitrate_mbps': self.bitrate_mbps,
            'latency_ms': self.latency_ms,
            'fps': self.fps,
            'preview_url': self.preview_url,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class AssetRights(BaseModel):
    TABLE_NAME = 'asset_rights'
    COLUMNS = ['id', 'asset_id', 'tenant_id', 'license_type', 'source_name', 'approval_status', 'usage_scope', 'expires_at', 'restrictions', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.asset_id = kwargs.get('asset_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.license_type = kwargs.get('license_type')
        self.source_name = kwargs.get('source_name')
        self.approval_status = kwargs.get('approval_status')
        self.usage_scope = kwargs.get('usage_scope')
        self.expires_at = kwargs.get('expires_at')
        self.restrictions = kwargs.get('restrictions')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            asset_id=row.get('asset_id'),
            tenant_id=row.get('tenant_id'),
            license_type=row.get('license_type'),
            source_name=row.get('source_name'),
            approval_status=row.get('approval_status'),
            usage_scope=row.get('usage_scope'),
            expires_at=row.get('expires_at'),
            restrictions=_json_loads(row.get('restrictions')),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'asset_id': self.asset_id,
            'tenant_id': self.tenant_id,
            'license_type': self.license_type,
            'source_name': self.source_name,
            'approval_status': self.approval_status,
            'usage_scope': self.usage_scope,
            'expires_at': self.expires_at,
            'restrictions': self.restrictions,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'asset_id': self.asset_id,
            'tenant_id': self.tenant_id,
            'license_type': self.license_type,
            'source_name': self.source_name,
            'approval_status': self.approval_status,
            'usage_scope': self.usage_scope,
            'expires_at': self.expires_at,
            'restrictions': _json_dumps(self.restrictions),
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class AssetProvenanceEvent(BaseModel):
    TABLE_NAME = 'asset_provenance_events'
    COLUMNS = ['id', 'asset_id', 'tenant_id', 'event_type', 'event_summary', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.asset_id = kwargs.get('asset_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.event_type = kwargs.get('event_type')
        self.event_summary = kwargs.get('event_summary')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            asset_id=row.get('asset_id'),
            tenant_id=row.get('tenant_id'),
            event_type=row.get('event_type'),
            event_summary=row.get('event_summary'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'asset_id': self.asset_id,
            'tenant_id': self.tenant_id,
            'event_type': self.event_type,
            'event_summary': self.event_summary,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'asset_id': self.asset_id,
            'tenant_id': self.tenant_id,
            'event_type': self.event_type,
            'event_summary': self.event_summary,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class BillingAccount(BaseModel):
    TABLE_NAME = 'billing_accounts'
    COLUMNS = ['id', 'tenant_id', 'project_id', 'plan_name', 'balance', 'currency', 'status', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.plan_name = kwargs.get('plan_name')
        self.balance = kwargs.get('balance', 0.0)
        self.currency = kwargs.get('currency')
        self.status = kwargs.get('status')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            project_id=row.get('project_id'),
            plan_name=row.get('plan_name'),
            balance=row.get('balance'),
            currency=row.get('currency'),
            status=row.get('status'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'plan_name': self.plan_name,
            'balance': self.balance,
            'currency': self.currency,
            'status': self.status,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'plan_name': self.plan_name,
            'balance': self.balance,
            'currency': self.currency,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class BillingUsageRecord(BaseModel):
    TABLE_NAME = 'billing_usage_records'
    COLUMNS = ['id', 'job_id', 'tenant_id', 'project_id', 'amount', 'currency', 'usage_type', 'usage_units', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.job_id = kwargs.get('job_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.amount = kwargs.get('amount', 0.0)
        self.currency = kwargs.get('currency')
        self.usage_type = kwargs.get('usage_type')
        self.usage_units = kwargs.get('usage_units', 0.0)
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            job_id=row.get('job_id'),
            tenant_id=row.get('tenant_id'),
            project_id=row.get('project_id'),
            amount=row.get('amount'),
            currency=row.get('currency'),
            usage_type=row.get('usage_type'),
            usage_units=row.get('usage_units'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'amount': self.amount,
            'currency': self.currency,
            'usage_type': self.usage_type,
            'usage_units': self.usage_units,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'amount': self.amount,
            'currency': self.currency,
            'usage_type': self.usage_type,
            'usage_units': self.usage_units,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class OpsEvent(BaseModel):
    TABLE_NAME = 'ops_events'
    COLUMNS = ['id', 'tenant_id', 'project_id', 'job_id', 'event_type', 'severity', 'message', 'metadata', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.job_id = kwargs.get('job_id')
        self.event_type = kwargs.get('event_type')
        self.severity = kwargs.get('severity')
        self.message = kwargs.get('message')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            project_id=row.get('project_id'),
            job_id=row.get('job_id'),
            event_type=row.get('event_type'),
            severity=row.get('severity'),
            message=row.get('message'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'job_id': self.job_id,
            'event_type': self.event_type,
            'severity': self.severity,
            'message': self.message,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'job_id': self.job_id,
            'event_type': self.event_type,
            'severity': self.severity,
            'message': self.message,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
