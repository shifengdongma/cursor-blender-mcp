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


# ── Creative Production Models ──


class CreativeProject(BaseModel):
    TABLE_NAME = 'creative_projects'

    STATUS_DRAFT = 'draft'
    STATUS_ANALYZING = 'analyzing'
    STATUS_READY = 'ready'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_ARCHIVED = 'archived'

    COLUMNS = [
        'id', 'tenant_id', 'project_id', 'user_id', 'name', 'description',
        'status', 'genre', 'target_duration', 'concept', 'requirements',
        'creative_brief', 'settings', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.user_id = kwargs.get('user_id')
        self.name = kwargs.get('name', '')
        self.description = kwargs.get('description')
        self.status = kwargs.get('status', self.STATUS_DRAFT)
        self.genre = kwargs.get('genre')
        self.target_duration = kwargs.get('target_duration', 0)
        self.concept = kwargs.get('concept')
        self.requirements = kwargs.get('requirements')
        self.creative_brief = kwargs.get('creative_brief')
        self.settings = kwargs.get('settings')
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
            user_id=row.get('user_id'),
            name=row.get('name'),
            description=row.get('description'),
            status=row.get('status'),
            genre=row.get('genre'),
            target_duration=row.get('target_duration'),
            concept=row.get('concept'),
            requirements=_json_loads(row.get('requirements')),
            creative_brief=_json_loads(row.get('creative_brief')),
            settings=_json_loads(row.get('settings')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'genre': self.genre,
            'target_duration': self.target_duration,
            'concept': self.concept,
            'requirements': self.requirements,
            'creative_brief': self.creative_brief,
            'settings': self.settings,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'genre': self.genre,
            'target_duration': self.target_duration,
            'concept': self.concept,
            'requirements': _json_dumps(self.requirements),
            'creative_brief': _json_dumps(self.creative_brief),
            'settings': _json_dumps(self.settings),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class StoryboardShot(BaseModel):
    TABLE_NAME = 'storyboard_shots'

    STATUS_PENDING = 'pending'
    STATUS_GENERATING_IMAGE = 'generating_image'
    STATUS_GENERATING_VIDEO = 'generating_video'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'

    COLUMNS = [
        'id', 'creative_project_id', 'sequence_no', 'scene_title',
        'scene_description', 'shot_type', 'duration_s', 'dialogue',
        'voice_id', 'camera_movement', 'lighting_mood',
        'environment_detail', 'character_action', 'visual_style',
        'prompt_cn', 'prompt_en', 'negative_prompt',
        'primary_image_asset_id', 'video_asset_id', 'audio_asset_id',
        'srt_path', 'video_url', 'status', 'metadata',
        'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.sequence_no = kwargs.get('sequence_no', 0)
        self.scene_title = kwargs.get('scene_title')
        self.scene_description = kwargs.get('scene_description')
        self.shot_type = kwargs.get('shot_type')
        self.duration_s = kwargs.get('duration_s', 0)
        self.dialogue = kwargs.get('dialogue')
        self.voice_id = kwargs.get('voice_id')
        self.camera_movement = kwargs.get('camera_movement')
        self.lighting_mood = kwargs.get('lighting_mood')
        self.environment_detail = kwargs.get('environment_detail')
        self.character_action = kwargs.get('character_action')
        self.visual_style = kwargs.get('visual_style')
        self.prompt_cn = kwargs.get('prompt_cn')
        self.prompt_en = kwargs.get('prompt_en')
        self.negative_prompt = kwargs.get('negative_prompt')
        self.primary_image_asset_id = kwargs.get('primary_image_asset_id')
        self.video_asset_id = kwargs.get('video_asset_id')
        self.audio_asset_id = kwargs.get('audio_asset_id')
        self.srt_path = kwargs.get('srt_path')
        self.video_url = kwargs.get('video_url')
        self.status = kwargs.get('status', self.STATUS_PENDING)
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            creative_project_id=row.get('creative_project_id'),
            sequence_no=row.get('sequence_no'),
            scene_title=row.get('scene_title'),
            scene_description=row.get('scene_description'),
            shot_type=row.get('shot_type'),
            duration_s=row.get('duration_s'),
            dialogue=row.get('dialogue'),
            voice_id=row.get('voice_id'),
            camera_movement=row.get('camera_movement'),
            lighting_mood=row.get('lighting_mood'),
            environment_detail=row.get('environment_detail'),
            character_action=row.get('character_action'),
            visual_style=row.get('visual_style'),
            prompt_cn=row.get('prompt_cn'),
            prompt_en=row.get('prompt_en'),
            negative_prompt=row.get('negative_prompt'),
            primary_image_asset_id=row.get('primary_image_asset_id'),
            video_asset_id=row.get('video_asset_id'),
            audio_asset_id=row.get('audio_asset_id'),
            srt_path=row.get('srt_path'),
            video_url=row.get('video_url'),
            status=row.get('status'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'sequence_no': self.sequence_no,
            'scene_title': self.scene_title,
            'scene_description': self.scene_description,
            'shot_type': self.shot_type,
            'duration_s': self.duration_s,
            'dialogue': self.dialogue,
            'voice_id': self.voice_id,
            'camera_movement': self.camera_movement,
            'lighting_mood': self.lighting_mood,
            'environment_detail': self.environment_detail,
            'character_action': self.character_action,
            'visual_style': self.visual_style,
            'prompt_cn': self.prompt_cn,
            'prompt_en': self.prompt_en,
            'negative_prompt': self.negative_prompt,
            'primary_image_asset_id': self.primary_image_asset_id,
            'video_asset_id': self.video_asset_id,
            'audio_asset_id': self.audio_asset_id,
            'srt_path': self.srt_path,
            'video_url': self.video_url,
            'status': self.status,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'sequence_no': self.sequence_no,
            'scene_title': self.scene_title,
            'scene_description': self.scene_description,
            'shot_type': self.shot_type,
            'duration_s': self.duration_s,
            'dialogue': self.dialogue,
            'voice_id': self.voice_id,
            'camera_movement': self.camera_movement,
            'lighting_mood': self.lighting_mood,
            'environment_detail': self.environment_detail,
            'character_action': self.character_action,
            'visual_style': self.visual_style,
            'prompt_cn': self.prompt_cn,
            'prompt_en': self.prompt_en,
            'negative_prompt': self.negative_prompt,
            'primary_image_asset_id': self.primary_image_asset_id,
            'video_asset_id': self.video_asset_id,
            'audio_asset_id': self.audio_asset_id,
            'srt_path': self.srt_path,
            'video_url': self.video_url,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class GenerationTask(BaseModel):
    TABLE_NAME = 'generation_tasks'

    TYPE_STORYBOARD = 'storyboard'
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_TTS = 'tts'
    TYPE_COMPOSE = 'compose'
    TYPE_REFINE = 'refine'
    TYPE_EXPORT = 'export'

    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    COLUMNS = [
        'id', 'creative_project_id', 'task_type', 'status', 'stage',
        'progress', 'params', 'result_payload', 'error_code',
        'error_message', 'target_shot_id', 'target_asset_id',
        'claimed_at', 'completed_at', 'created_at', 'updated_at',
        'created_by'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.task_type = kwargs.get('task_type')
        self.status = kwargs.get('status', self.STATUS_QUEUED)
        self.stage = kwargs.get('stage')
        self.progress = kwargs.get('progress', 0)
        self.params = kwargs.get('params')
        self.result_payload = kwargs.get('result_payload')
        self.error_code = kwargs.get('error_code')
        self.error_message = kwargs.get('error_message')
        self.target_shot_id = kwargs.get('target_shot_id')
        self.target_asset_id = kwargs.get('target_asset_id')
        self.claimed_at = kwargs.get('claimed_at')
        self.completed_at = kwargs.get('completed_at')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()
        self.created_by = kwargs.get('created_by')

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            creative_project_id=row.get('creative_project_id'),
            task_type=row.get('task_type'),
            status=row.get('status'),
            stage=row.get('stage'),
            progress=row.get('progress'),
            params=_json_loads(row.get('params')),
            result_payload=_json_loads(row.get('result_payload')),
            error_code=row.get('error_code'),
            error_message=row.get('error_message'),
            target_shot_id=row.get('target_shot_id'),
            target_asset_id=row.get('target_asset_id'),
            claimed_at=row.get('claimed_at'),
            completed_at=row.get('completed_at'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
            created_by=row.get('created_by'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'task_type': self.task_type,
            'status': self.status,
            'stage': self.stage,
            'progress': self.progress,
            'params': self.params,
            'result_payload': self.result_payload,
            'error_code': self.error_code,
            'error_message': self.error_message,
            'target_shot_id': self.target_shot_id,
            'target_asset_id': self.target_asset_id,
            'claimed_at': self.claimed_at,
            'completed_at': self.completed_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'created_by': self.created_by,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'task_type': self.task_type,
            'status': self.status,
            'stage': self.stage,
            'progress': self.progress,
            'params': _json_dumps(self.params),
            'result_payload': _json_dumps(self.result_payload),
            'error_code': self.error_code,
            'error_message': self.error_message,
            'target_shot_id': self.target_shot_id,
            'target_asset_id': self.target_asset_id,
            'claimed_at': self.claimed_at,
            'completed_at': self.completed_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'created_by': self.created_by,
        }


class TaskArtifact(BaseModel):
    TABLE_NAME = 'task_artifacts'

    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_AUDIO = 'audio'
    TYPE_MANIFEST = 'manifest'
    TYPE_OTHER = 'other'

    COLUMNS = [
        'id', 'task_id', 'creative_project_id', 'name', 'artifact_type',
        'file_path', 'file_size', 'asset_id', 'metadata',
        'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.task_id = kwargs.get('task_id')
        self.creative_project_id = kwargs.get('creative_project_id')
        self.name = kwargs.get('name', '')
        self.artifact_type = kwargs.get('artifact_type')
        self.file_path = kwargs.get('file_path')
        self.file_size = kwargs.get('file_size', 0)
        self.asset_id = kwargs.get('asset_id')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            task_id=row.get('task_id'),
            creative_project_id=row.get('creative_project_id'),
            name=row.get('name'),
            artifact_type=row.get('artifact_type'),
            file_path=row.get('file_path'),
            file_size=row.get('file_size'),
            asset_id=row.get('asset_id'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'creative_project_id': self.creative_project_id,
            'name': self.name,
            'artifact_type': self.artifact_type,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'asset_id': self.asset_id,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'creative_project_id': self.creative_project_id,
            'name': self.name,
            'artifact_type': self.artifact_type,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'asset_id': self.asset_id,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class TimelineTrack(BaseModel):
    TABLE_NAME = 'timeline_tracks'

    TYPE_VIDEO = 'video'
    TYPE_AUDIO = 'audio'
    TYPE_SUBTITLE = 'subtitle'
    TYPE_EFFECT = 'effect'

    COLUMNS = [
        'id', 'creative_project_id', 'name', 'track_type',
        'sequence_no', 'settings', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.name = kwargs.get('name', '')
        self.track_type = kwargs.get('track_type')
        self.sequence_no = kwargs.get('sequence_no', 0)
        self.settings = kwargs.get('settings')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            creative_project_id=row.get('creative_project_id'),
            name=row.get('name'),
            track_type=row.get('track_type'),
            sequence_no=row.get('sequence_no'),
            settings=_json_loads(row.get('settings')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'name': self.name,
            'track_type': self.track_type,
            'sequence_no': self.sequence_no,
            'settings': self.settings,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'name': self.name,
            'track_type': self.track_type,
            'sequence_no': self.sequence_no,
            'settings': _json_dumps(self.settings),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class TimelineClip(BaseModel):
    TABLE_NAME = 'timeline_clips'

    COLUMNS = [
        'id', 'track_id', 'creative_project_id', 'shot_id',
        'asset_id', 'name', 'start_time', 'duration_s',
        'trim_in', 'trim_out', 'properties',
        'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.track_id = kwargs.get('track_id')
        self.creative_project_id = kwargs.get('creative_project_id')
        self.shot_id = kwargs.get('shot_id')
        self.asset_id = kwargs.get('asset_id')
        self.name = kwargs.get('name', '')
        self.start_time = kwargs.get('start_time', 0.0)
        self.duration_s = kwargs.get('duration_s', 0.0)
        self.trim_in = kwargs.get('trim_in', 0.0)
        self.trim_out = kwargs.get('trim_out')
        self.properties = kwargs.get('properties')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            track_id=row.get('track_id'),
            creative_project_id=row.get('creative_project_id'),
            shot_id=row.get('shot_id'),
            asset_id=row.get('asset_id'),
            name=row.get('name'),
            start_time=row.get('start_time'),
            duration_s=row.get('duration_s'),
            trim_in=row.get('trim_in'),
            trim_out=row.get('trim_out'),
            properties=_json_loads(row.get('properties')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'track_id': self.track_id,
            'creative_project_id': self.creative_project_id,
            'shot_id': self.shot_id,
            'asset_id': self.asset_id,
            'name': self.name,
            'start_time': self.start_time,
            'duration_s': self.duration_s,
            'trim_in': self.trim_in,
            'trim_out': self.trim_out,
            'properties': self.properties,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'track_id': self.track_id,
            'creative_project_id': self.creative_project_id,
            'shot_id': self.shot_id,
            'asset_id': self.asset_id,
            'name': self.name,
            'start_time': self.start_time,
            'duration_s': self.duration_s,
            'trim_in': self.trim_in,
            'trim_out': self.trim_out,
            'properties': _json_dumps(self.properties),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class ExportPackage(BaseModel):
    TABLE_NAME = 'export_packages'

    STATUS_PENDING = 'pending'
    STATUS_EXPORTING = 'exporting'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    FORMAT_MP4 = 'mp4'
    FORMAT_MOV = 'mov'
    FORMAT_ZIP = 'zip'

    COLUMNS = [
        'id', 'creative_project_id', 'task_id', 'format',
        'file_path', 'file_size', 'status', 'manifest',
        'download_url', 'created_at', 'updated_at', 'created_by'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.task_id = kwargs.get('task_id')
        self.format = kwargs.get('format', self.FORMAT_ZIP)
        self.file_path = kwargs.get('file_path')
        self.file_size = kwargs.get('file_size', 0)
        self.status = kwargs.get('status', self.STATUS_PENDING)
        self.manifest = kwargs.get('manifest')
        self.download_url = kwargs.get('download_url')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()
        self.created_by = kwargs.get('created_by')

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            creative_project_id=row.get('creative_project_id'),
            task_id=row.get('task_id'),
            format=row.get('format'),
            file_path=row.get('file_path'),
            file_size=row.get('file_size'),
            status=row.get('status'),
            manifest=_json_loads(row.get('manifest')),
            download_url=row.get('download_url'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
            created_by=row.get('created_by'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'task_id': self.task_id,
            'format': self.format,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'status': self.status,
            'manifest': self.manifest,
            'download_url': self.download_url,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'created_by': self.created_by,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'task_id': self.task_id,
            'format': self.format,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'status': self.status,
            'manifest': _json_dumps(self.manifest),
            'download_url': self.download_url,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'created_by': self.created_by,
        }
