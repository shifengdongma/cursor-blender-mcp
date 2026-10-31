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
        'owner_user_id', 'tenant_id', 'visibility', 'checksum_sha256',
        'duration_s', 'audio_role', 'media_info',
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
        self.owner_user_id = kwargs.get('owner_user_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.visibility = kwargs.get('visibility') or ('shared' if not self.owner_user_id else 'private')
        self.checksum_sha256 = kwargs.get('checksum_sha256')
        self.duration_s = kwargs.get('duration_s')
        self.audio_role = kwargs.get('audio_role')
        self.media_info = kwargs.get('media_info')
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
            owner_user_id=row.get('owner_user_id'),
            tenant_id=row.get('tenant_id'),
            visibility=row.get('visibility'),
            checksum_sha256=row.get('checksum_sha256'),
            duration_s=row.get('duration_s'),
            audio_role=row.get('audio_role'),
            media_info=_json_loads(row.get('media_info')),
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
            'owner_user_id': self.owner_user_id,
            'tenant_id': self.tenant_id,
            'visibility': self.visibility,
            'checksum_sha256': self.checksum_sha256,
            'duration_s': self.duration_s,
            'audio_role': self.audio_role,
            'media_info': self.media_info,
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
            'owner_user_id': self.owner_user_id,
            'tenant_id': self.tenant_id,
            'visibility': self.visibility,
            'checksum_sha256': self.checksum_sha256,
            'duration_s': self.duration_s,
            'audio_role': self.audio_role,
            'media_info': _json_dumps(self.media_info),
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
    COLUMNS = [
        'id', 'job_id', 'tenant_id', 'project_id', 'amount', 'currency',
        'usage_type', 'usage_units', 'render_job_id', 'node_id', 'provider',
        'usage_seconds', 'unit_price', 'metadata', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.job_id = kwargs.get('job_id')
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.amount = kwargs.get('amount', 0.0)
        self.currency = kwargs.get('currency')
        self.usage_type = kwargs.get('usage_type')
        self.usage_units = kwargs.get('usage_units', 0.0)
        self.render_job_id = kwargs.get('render_job_id')
        self.node_id = kwargs.get('node_id')
        self.provider = kwargs.get('provider')
        self.usage_seconds = kwargs.get('usage_seconds')
        self.unit_price = kwargs.get('unit_price')
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
            render_job_id=row.get('render_job_id'),
            node_id=row.get('node_id'),
            provider=row.get('provider'),
            usage_seconds=row.get('usage_seconds'),
            unit_price=row.get('unit_price'),
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
            'render_job_id': self.render_job_id,
            'node_id': self.node_id,
            'provider': self.provider,
            'usage_seconds': self.usage_seconds,
            'unit_price': self.unit_price,
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
            'render_job_id': self.render_job_id,
            'node_id': self.node_id,
            'provider': self.provider,
            'usage_seconds': self.usage_seconds,
            'unit_price': self.unit_price,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class OpsEvent(BaseModel):
    TABLE_NAME = 'ops_events'
    COLUMNS = ['id', 'tenant_id', 'project_id', 'job_id', 'event_type', 'severity', 'message', 'metadata', 'actor_user_id', 'request_id', 'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.job_id = kwargs.get('job_id')
        self.event_type = kwargs.get('event_type')
        self.severity = kwargs.get('severity')
        self.message = kwargs.get('message')
        self.metadata = kwargs.get('metadata')
        self.actor_user_id = kwargs.get('actor_user_id')
        self.request_id = kwargs.get('request_id')
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
            actor_user_id=row.get('actor_user_id'),
            request_id=row.get('request_id'),
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
            'actor_user_id': self.actor_user_id,
            'request_id': self.request_id,
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
            'actor_user_id': self.actor_user_id,
            'request_id': self.request_id,
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
        'creative_brief', 'settings', 'timeline_version',
        'final_video_asset_id', 'final_compose_task_id', 'final_timeline_version',
        'created_at', 'updated_at'
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
        self.timeline_version = kwargs.get('timeline_version', 0)
        self.final_video_asset_id = kwargs.get('final_video_asset_id')
        self.final_compose_task_id = kwargs.get('final_compose_task_id')
        self.final_timeline_version = kwargs.get('final_timeline_version')
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
            timeline_version=row.get('timeline_version'),
            final_video_asset_id=row.get('final_video_asset_id'),
            final_compose_task_id=row.get('final_compose_task_id'),
            final_timeline_version=row.get('final_timeline_version'),
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
            'timeline_version': self.timeline_version,
            'final_video_asset_id': self.final_video_asset_id,
            'final_compose_task_id': self.final_compose_task_id,
            'final_timeline_version': self.final_timeline_version,
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
            'timeline_version': self.timeline_version,
            'final_video_asset_id': self.final_video_asset_id,
            'final_compose_task_id': self.final_compose_task_id,
            'final_timeline_version': self.final_timeline_version,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class StoryboardShot(BaseModel):
    TABLE_NAME = 'storyboard_shots'

    STATUS_PENDING = 'pending'
    STATUS_GENERATING_IMAGE = 'generating_image'
    STATUS_GENERATING_VIDEO = 'generating_video'
    STATUS_READY = 'ready'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_FAILED = 'failed'

    COLUMNS = [
        'id', 'creative_project_id', 'sequence_no', 'scene_title',
        'scene_description', 'shot_type', 'duration_s', 'dialogue',
        'voice_id', 'camera_movement', 'lighting_mood',
        'environment_detail', 'character_action', 'visual_style',
        'prompt_cn', 'prompt_en', 'negative_prompt',
        'primary_image_asset_id', 'keyframe_asset_id', 'video_asset_id', 'audio_asset_id',
        'selected_video_asset_id', 'refined_video_asset_id', 'video_selection_source',
        'subtitle_asset_id', 'audio_options', 'audio_duration_s',
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
        self.keyframe_asset_id = kwargs.get('keyframe_asset_id')
        self.video_asset_id = kwargs.get('video_asset_id')
        self.audio_asset_id = kwargs.get('audio_asset_id')
        self.selected_video_asset_id = kwargs.get('selected_video_asset_id')
        self.refined_video_asset_id = kwargs.get('refined_video_asset_id')
        self.video_selection_source = kwargs.get('video_selection_source')
        self.subtitle_asset_id = kwargs.get('subtitle_asset_id')
        self.audio_options = kwargs.get('audio_options')
        self.audio_duration_s = kwargs.get('audio_duration_s')
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
            keyframe_asset_id=row.get('keyframe_asset_id'),
            video_asset_id=row.get('video_asset_id'),
            audio_asset_id=row.get('audio_asset_id'),
            selected_video_asset_id=row.get('selected_video_asset_id'),
            refined_video_asset_id=row.get('refined_video_asset_id'),
            video_selection_source=row.get('video_selection_source'),
            subtitle_asset_id=row.get('subtitle_asset_id'),
            audio_options=_json_loads(row.get('audio_options')),
            audio_duration_s=row.get('audio_duration_s'),
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
            'keyframe_asset_id': self.keyframe_asset_id,
            'video_asset_id': self.video_asset_id,
            'audio_asset_id': self.audio_asset_id,
            'selected_video_asset_id': self.selected_video_asset_id,
            'refined_video_asset_id': self.refined_video_asset_id,
            'video_selection_source': self.video_selection_source,
            'subtitle_asset_id': self.subtitle_asset_id,
            'audio_options': self.audio_options,
            'audio_duration_s': self.audio_duration_s,
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
            'keyframe_asset_id': self.keyframe_asset_id,
            'video_asset_id': self.video_asset_id,
            'audio_asset_id': self.audio_asset_id,
            'selected_video_asset_id': self.selected_video_asset_id,
            'refined_video_asset_id': self.refined_video_asset_id,
            'video_selection_source': self.video_selection_source,
            'subtitle_asset_id': self.subtitle_asset_id,
            'audio_options': _json_dumps(self.audio_options),
            'audio_duration_s': self.audio_duration_s,
            'srt_path': self.srt_path,
            'video_url': self.video_url,
            'status': self.status,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class ShotMediaVersion(BaseModel):
    """A historical, selectable media variant attached to one shot."""

    TABLE_NAME = 'shot_media_versions'

    KIND_VIDEO = 'video'
    KIND_AUDIO = 'audio'
    KIND_SUBTITLE = 'subtitle'

    SOURCE_GENERATION = 'generation'
    SOURCE_TTS = 'tts'
    SOURCE_REFINE = 'refine'
    SOURCE_UPLOAD = 'upload'
    SOURCE_LEGACY = 'legacy'

    COLUMNS = [
        'id', 'creative_project_id', 'shot_id', 'media_kind', 'asset_id',
        'task_id', 'source', 'label', 'metadata', 'is_selected',
        'created_at', 'updated_at',
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.shot_id = kwargs.get('shot_id')
        self.media_kind = kwargs.get('media_kind')
        self.asset_id = kwargs.get('asset_id')
        self.task_id = kwargs.get('task_id')
        self.source = kwargs.get('source')
        self.label = kwargs.get('label')
        self.metadata = kwargs.get('metadata')
        self.is_selected = kwargs.get('is_selected', 0)
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            creative_project_id=row.get('creative_project_id'),
            shot_id=row.get('shot_id'),
            media_kind=row.get('media_kind'),
            asset_id=row.get('asset_id'),
            task_id=row.get('task_id'),
            source=row.get('source'),
            label=row.get('label'),
            metadata=_json_loads(row.get('metadata')),
            is_selected=row.get('is_selected'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'shot_id': self.shot_id,
            'media_kind': self.media_kind,
            'asset_id': self.asset_id,
            'task_id': self.task_id,
            'source': self.source,
            'label': self.label,
            'metadata': self.metadata,
            'is_selected': bool(self.is_selected),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'creative_project_id': self.creative_project_id,
            'shot_id': self.shot_id,
            'media_kind': self.media_kind,
            'asset_id': self.asset_id,
            'task_id': self.task_id,
            'source': self.source,
            'label': self.label,
            'metadata': _json_dumps(self.metadata),
            'is_selected': 1 if self.is_selected else 0,
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
    STATUS_SUBMITTING = 'submitting'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_NEEDS_REVIEW = 'needs_review'

    COLUMNS = [
        'id', 'creative_project_id', 'task_type', 'status', 'stage',
        'progress', 'params', 'result_payload', 'error_code',
        'error_message', 'target_shot_id', 'target_asset_id',
        'claimed_at', 'completed_at', 'created_at', 'updated_at',
        'created_by', 'provider', 'model_id', 'provider_job_id',
        'provider_request_id', 'provider_status', 'attempt_count', 'max_attempts',
        'next_retry_at', 'lease_expires_at', 'lease_owner',
        'submission_uncertain', 'submission_started_at',
        'poll_error_count', 'last_polled_at', 'output_asset_id',
        'client_request_id', 'cost_estimate', 'currency',
        'cancel_requested', 'timeline_version', 'timeline_snapshot',
        'created_at_ms', 'claimed_at_ms',
        'provider_request_started_at', 'provider_request_finished_at',
        'provider_job_created_at', 'provider_finished_at',
        'download_started_at', 'download_finished_at',
        'persist_started_at', 'persist_finished_at', 'completed_at_ms',
        'timing_json'
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
        self.provider = kwargs.get('provider')
        self.model_id = kwargs.get('model_id')
        self.provider_job_id = kwargs.get('provider_job_id')
        self.provider_request_id = kwargs.get('provider_request_id')
        self.provider_status = kwargs.get('provider_status')
        self.attempt_count = kwargs.get('attempt_count', 0)
        self.max_attempts = kwargs.get('max_attempts', 3)
        self.next_retry_at = kwargs.get('next_retry_at')
        self.lease_expires_at = kwargs.get('lease_expires_at')
        self.lease_owner = kwargs.get('lease_owner')
        self.submission_uncertain = kwargs.get('submission_uncertain', 0)
        self.submission_started_at = kwargs.get('submission_started_at')
        self.poll_error_count = kwargs.get('poll_error_count', 0)
        self.last_polled_at = kwargs.get('last_polled_at')
        self.output_asset_id = kwargs.get('output_asset_id')
        self.client_request_id = kwargs.get('client_request_id')
        self.cost_estimate = kwargs.get('cost_estimate')
        self.currency = kwargs.get('currency')
        self.cancel_requested = kwargs.get('cancel_requested', 0)
        self.timeline_version = kwargs.get('timeline_version')
        self.timeline_snapshot = kwargs.get('timeline_snapshot')
        self.created_at_ms = kwargs.get('created_at_ms')
        self.claimed_at_ms = kwargs.get('claimed_at_ms')
        self.provider_request_started_at = kwargs.get('provider_request_started_at')
        self.provider_request_finished_at = kwargs.get('provider_request_finished_at')
        self.provider_job_created_at = kwargs.get('provider_job_created_at')
        self.provider_finished_at = kwargs.get('provider_finished_at')
        self.download_started_at = kwargs.get('download_started_at')
        self.download_finished_at = kwargs.get('download_finished_at')
        self.persist_started_at = kwargs.get('persist_started_at')
        self.persist_finished_at = kwargs.get('persist_finished_at')
        self.completed_at_ms = kwargs.get('completed_at_ms')
        self.timing_json = kwargs.get('timing_json')

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
            provider=row.get('provider'),
            model_id=row.get('model_id'),
            provider_job_id=row.get('provider_job_id'),
            provider_request_id=row.get('provider_request_id'),
            provider_status=row.get('provider_status'),
            attempt_count=row.get('attempt_count'),
            max_attempts=row.get('max_attempts'),
            next_retry_at=row.get('next_retry_at'),
            lease_expires_at=row.get('lease_expires_at'),
            lease_owner=row.get('lease_owner'),
            submission_uncertain=row.get('submission_uncertain'),
            submission_started_at=row.get('submission_started_at'),
            poll_error_count=row.get('poll_error_count'),
            last_polled_at=row.get('last_polled_at'),
            output_asset_id=row.get('output_asset_id'),
            client_request_id=row.get('client_request_id'),
            cost_estimate=row.get('cost_estimate'),
            currency=row.get('currency'),
            cancel_requested=row.get('cancel_requested'),
            timeline_version=row.get('timeline_version'),
            timeline_snapshot=_json_loads(row.get('timeline_snapshot')),
            created_at_ms=row.get('created_at_ms'),
            claimed_at_ms=row.get('claimed_at_ms'),
            provider_request_started_at=row.get('provider_request_started_at'),
            provider_request_finished_at=row.get('provider_request_finished_at'),
            provider_job_created_at=row.get('provider_job_created_at'),
            provider_finished_at=row.get('provider_finished_at'),
            download_started_at=row.get('download_started_at'),
            download_finished_at=row.get('download_finished_at'),
            persist_started_at=row.get('persist_started_at'),
            persist_finished_at=row.get('persist_finished_at'),
            completed_at_ms=row.get('completed_at_ms'),
            timing_json=_json_loads(row.get('timing_json')),
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
            'provider': self.provider,
            'model_id': self.model_id,
            'provider_job_id': self.provider_job_id,
            'provider_request_id': self.provider_request_id,
            'provider_status': self.provider_status,
            'attempt_count': self.attempt_count,
            'max_attempts': self.max_attempts,
            'next_retry_at': self.next_retry_at,
            'lease_expires_at': self.lease_expires_at,
            'submission_uncertain': self.submission_uncertain,
            'submission_started_at': self.submission_started_at,
            'poll_error_count': self.poll_error_count,
            'last_polled_at': self.last_polled_at,
            'output_asset_id': self.output_asset_id,
            'client_request_id': self.client_request_id,
            'cost_estimate': self.cost_estimate,
            'currency': self.currency,
            'cancel_requested': self.cancel_requested,
            'timeline_version': self.timeline_version,
            'timeline_snapshot': self.timeline_snapshot,
            'created_at_ms': self.created_at_ms,
            'claimed_at_ms': self.claimed_at_ms,
            'provider_request_started_at': self.provider_request_started_at,
            'provider_request_finished_at': self.provider_request_finished_at,
            'provider_job_created_at': self.provider_job_created_at,
            'provider_finished_at': self.provider_finished_at,
            'download_started_at': self.download_started_at,
            'download_finished_at': self.download_finished_at,
            'persist_started_at': self.persist_started_at,
            'persist_finished_at': self.persist_finished_at,
            'completed_at_ms': self.completed_at_ms,
            'timing_json': self.timing_json,
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
            'provider': self.provider,
            'model_id': self.model_id,
            'provider_job_id': self.provider_job_id,
            'provider_request_id': self.provider_request_id,
            'provider_status': self.provider_status,
            'attempt_count': self.attempt_count,
            'max_attempts': self.max_attempts,
            'next_retry_at': self.next_retry_at,
            'lease_expires_at': self.lease_expires_at,
            'lease_owner': self.lease_owner,
            'submission_uncertain': self.submission_uncertain,
            'submission_started_at': self.submission_started_at,
            'poll_error_count': self.poll_error_count,
            'last_polled_at': self.last_polled_at,
            'output_asset_id': self.output_asset_id,
            'client_request_id': self.client_request_id,
            'cost_estimate': self.cost_estimate,
            'currency': self.currency,
            'cancel_requested': self.cancel_requested,
            'timeline_version': self.timeline_version,
            'timeline_snapshot': _json_dumps(self.timeline_snapshot),
            'created_at_ms': self.created_at_ms,
            'claimed_at_ms': self.claimed_at_ms,
            'provider_request_started_at': self.provider_request_started_at,
            'provider_request_finished_at': self.provider_request_finished_at,
            'provider_job_created_at': self.provider_job_created_at,
            'provider_finished_at': self.provider_finished_at,
            'download_started_at': self.download_started_at,
            'download_finished_at': self.download_finished_at,
            'persist_started_at': self.persist_started_at,
            'persist_finished_at': self.persist_finished_at,
            'completed_at_ms': self.completed_at_ms,
            'timing_json': _json_dumps(self.timing_json),
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
        'id', 'creative_project_id', 'name', 'track_type', 'role',
        'sequence_no', 'settings', 'created_at', 'updated_at'
    ]

    ROLE_VIDEO = 'video'
    ROLE_NARRATION = 'narration'
    ROLE_MUSIC = 'music'
    ROLE_SFX = 'sfx'
    ROLE_SUBTITLE = 'subtitle'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.creative_project_id = kwargs.get('creative_project_id')
        self.name = kwargs.get('name', '')
        self.track_type = kwargs.get('track_type')
        self.role = kwargs.get('role')
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
            role=row.get('role'),
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
            'role': self.role,
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
            'role': self.role,
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
        'trim_in', 'trim_out', 'volume', 'muted',
        'source_audio_enabled', 'fade_in', 'fade_out',
        'subtitle_text', 'properties', 'created_at', 'updated_at'
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
        self.volume = kwargs.get('volume', 1.0)
        self.muted = kwargs.get('muted', 0)
        self.source_audio_enabled = kwargs.get('source_audio_enabled', 1)
        self.fade_in = kwargs.get('fade_in', 0.0)
        self.fade_out = kwargs.get('fade_out', 0.0)
        self.subtitle_text = kwargs.get('subtitle_text')
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
            volume=row.get('volume'),
            muted=row.get('muted'),
            source_audio_enabled=row.get('source_audio_enabled'),
            fade_in=row.get('fade_in'),
            fade_out=row.get('fade_out'),
            subtitle_text=row.get('subtitle_text'),
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
            'volume': self.volume,
            'muted': bool(self.muted),
            'source_audio_enabled': bool(self.source_audio_enabled),
            'fade_in': self.fade_in,
            'fade_out': self.fade_out,
            'subtitle_text': self.subtitle_text,
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
            'volume': self.volume,
            'muted': 1 if self.muted else 0,
            'source_audio_enabled': 1 if self.source_audio_enabled else 0,
            'fade_in': self.fade_in,
            'fade_out': self.fade_out,
            'subtitle_text': self.subtitle_text,
            'properties': _json_dumps(self.properties),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


# ── Cloud Compute Models ──


class CloudAccount(BaseModel):
    """Cloud provider account configuration (credentials stored in env, never in DB)."""
    TABLE_NAME = 'cloud_accounts'

    PROVIDER_ALIYUN = 'aliyun'
    PROVIDER_TENCENT = 'tencent'
    PROVIDER_VMWARE = 'vmware'
    PROVIDER_GENERIC_REST = 'generic_rest'

    COLUMNS = [
        'id', 'tenant_id', 'provider_type', 'name', 'region_list',
        'enabled', 'config_metadata', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.provider_type = kwargs.get('provider_type', '')
        self.name = kwargs.get('name', '')
        self.region_list = kwargs.get('region_list')
        self.enabled = kwargs.get('enabled', 1)
        self.config_metadata = kwargs.get('config_metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            tenant_id=row.get('tenant_id'),
            provider_type=row.get('provider_type'),
            name=row.get('name'),
            region_list=_json_loads(row.get('region_list')),
            enabled=row.get('enabled', 1),
            config_metadata=_json_loads(row.get('config_metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'provider_type': self.provider_type,
            'name': self.name,
            'region_list': self.region_list,
            'enabled': bool(self.enabled),
            'config_metadata': self.config_metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'provider_type': self.provider_type,
            'name': self.name,
            'region_list': _json_dumps(self.region_list),
            'enabled': 1 if self.enabled else 0,
            'config_metadata': _json_dumps(self.config_metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class ComputeNode(BaseModel):
    """Compute node registered from cloud providers or node agent."""
    TABLE_NAME = 'compute_nodes'

    STATUS_ONLINE = 'online'
    STATUS_OFFLINE = 'offline'
    STATUS_ERROR = 'error'
    STATUS_MAINTENANCE = 'maintenance'

    COLUMNS = [
        'id', 'tenant_id', 'provider_type', 'external_id', 'node_name',
        'host_name', 'ip_address', 'region', 'zone', 'cluster_name',
        'cpu_cores', 'memory_mb', 'disk_gb', 'gpu_type', 'gpu_count',
        'gpu_memory_mb', 'status', 'schedulable', 'last_heartbeat_at',
        'metadata', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.provider_type = kwargs.get('provider_type')
        self.external_id = kwargs.get('external_id')
        self.node_name = kwargs.get('node_name', '')
        self.host_name = kwargs.get('host_name')
        self.ip_address = kwargs.get('ip_address')
        self.region = kwargs.get('region')
        self.zone = kwargs.get('zone')
        self.cluster_name = kwargs.get('cluster_name')
        self.cpu_cores = kwargs.get('cpu_cores', 0)
        self.memory_mb = kwargs.get('memory_mb', 0)
        self.disk_gb = kwargs.get('disk_gb', 0)
        self.gpu_type = kwargs.get('gpu_type')
        self.gpu_count = kwargs.get('gpu_count', 0)
        self.gpu_memory_mb = kwargs.get('gpu_memory_mb', 0)
        self.status = kwargs.get('status', self.STATUS_ONLINE)
        self.schedulable = kwargs.get('schedulable', 1)
        self.last_heartbeat_at = kwargs.get('last_heartbeat_at')
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
            provider_type=row.get('provider_type'),
            external_id=row.get('external_id'),
            node_name=row.get('node_name'),
            host_name=row.get('host_name'),
            ip_address=row.get('ip_address'),
            region=row.get('region'),
            zone=row.get('zone'),
            cluster_name=row.get('cluster_name'),
            cpu_cores=row.get('cpu_cores'),
            memory_mb=row.get('memory_mb'),
            disk_gb=row.get('disk_gb'),
            gpu_type=row.get('gpu_type'),
            gpu_count=row.get('gpu_count'),
            gpu_memory_mb=row.get('gpu_memory_mb'),
            status=row.get('status'),
            schedulable=row.get('schedulable'),
            last_heartbeat_at=row.get('last_heartbeat_at'),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'provider_type': self.provider_type,
            'external_id': self.external_id,
            'node_name': self.node_name,
            'host_name': self.host_name,
            'ip_address': self.ip_address,
            'region': self.region,
            'zone': self.zone,
            'cluster_name': self.cluster_name,
            'cpu_cores': self.cpu_cores,
            'memory_mb': self.memory_mb,
            'disk_gb': self.disk_gb,
            'gpu_type': self.gpu_type,
            'gpu_count': self.gpu_count,
            'gpu_memory_mb': self.gpu_memory_mb,
            'status': self.status,
            'schedulable': bool(self.schedulable),
            'last_heartbeat_at': self.last_heartbeat_at,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'provider_type': self.provider_type,
            'external_id': self.external_id,
            'node_name': self.node_name,
            'host_name': self.host_name,
            'ip_address': self.ip_address,
            'region': self.region,
            'zone': self.zone,
            'cluster_name': self.cluster_name,
            'cpu_cores': self.cpu_cores,
            'memory_mb': self.memory_mb,
            'disk_gb': self.disk_gb,
            'gpu_type': self.gpu_type,
            'gpu_count': self.gpu_count,
            'gpu_memory_mb': self.gpu_memory_mb,
            'status': self.status,
            'schedulable': 1 if self.schedulable else 0,
            'last_heartbeat_at': self.last_heartbeat_at,
            'metadata': _json_dumps(self.metadata),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class NodeMetricSample(BaseModel):
    """Time-series metrics collected from compute nodes."""
    TABLE_NAME = 'node_metric_samples'

    COLUMNS = [
        'id', 'node_id', 'sampled_at', 'cpu_percent', 'memory_percent',
        'gpu_percent', 'gpu_memory_percent', 'gpu_temperature',
        'disk_read_bps', 'disk_write_bps', 'network_rx_bps',
        'network_tx_bps', 'latency_ms', 'packet_loss_percent',
        'running_tasks', 'metadata'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.node_id = kwargs.get('node_id')
        self.sampled_at = kwargs.get('sampled_at') or _now()
        self.cpu_percent = kwargs.get('cpu_percent')
        self.memory_percent = kwargs.get('memory_percent')
        self.gpu_percent = kwargs.get('gpu_percent')
        self.gpu_memory_percent = kwargs.get('gpu_memory_percent')
        self.gpu_temperature = kwargs.get('gpu_temperature')
        self.disk_read_bps = kwargs.get('disk_read_bps')
        self.disk_write_bps = kwargs.get('disk_write_bps')
        self.network_rx_bps = kwargs.get('network_rx_bps')
        self.network_tx_bps = kwargs.get('network_tx_bps')
        self.latency_ms = kwargs.get('latency_ms')
        self.packet_loss_percent = kwargs.get('packet_loss_percent')
        self.running_tasks = kwargs.get('running_tasks', 0)
        self.metadata = kwargs.get('metadata')

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            node_id=row.get('node_id'),
            sampled_at=row.get('sampled_at'),
            cpu_percent=row.get('cpu_percent'),
            memory_percent=row.get('memory_percent'),
            gpu_percent=row.get('gpu_percent'),
            gpu_memory_percent=row.get('gpu_memory_percent'),
            gpu_temperature=row.get('gpu_temperature'),
            disk_read_bps=row.get('disk_read_bps'),
            disk_write_bps=row.get('disk_write_bps'),
            network_rx_bps=row.get('network_rx_bps'),
            network_tx_bps=row.get('network_tx_bps'),
            latency_ms=row.get('latency_ms'),
            packet_loss_percent=row.get('packet_loss_percent'),
            running_tasks=row.get('running_tasks'),
            metadata=_json_loads(row.get('metadata'))
        )

    def to_dict(self):
        return {
            'id': self.id,
            'node_id': self.node_id,
            'sampled_at': self.sampled_at,
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'gpu_percent': self.gpu_percent,
            'gpu_memory_percent': self.gpu_memory_percent,
            'gpu_temperature': self.gpu_temperature,
            'disk_read_bps': self.disk_read_bps,
            'disk_write_bps': self.disk_write_bps,
            'network_rx_bps': self.network_rx_bps,
            'network_tx_bps': self.network_tx_bps,
            'latency_ms': self.latency_ms,
            'packet_loss_percent': self.packet_loss_percent,
            'running_tasks': self.running_tasks,
            'metadata': self.metadata
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'node_id': self.node_id,
            'sampled_at': self.sampled_at,
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'gpu_percent': self.gpu_percent,
            'gpu_memory_percent': self.gpu_memory_percent,
            'gpu_temperature': self.gpu_temperature,
            'disk_read_bps': self.disk_read_bps,
            'disk_write_bps': self.disk_write_bps,
            'network_rx_bps': self.network_rx_bps,
            'network_tx_bps': self.network_tx_bps,
            'latency_ms': self.latency_ms,
            'packet_loss_percent': self.packet_loss_percent,
            'running_tasks': self.running_tasks,
            'metadata': _json_dumps(self.metadata)
        }


class RenderJob(BaseModel):
    """Render job tracking for Blender rendering tasks."""
    TABLE_NAME = 'render_jobs'

    STATUS_PENDING = 'pending'
    STATUS_RENDERING = 'rendering'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    COLUMNS = [
        'id', 'tenant_id', 'project_id', 'node_id', 'engine_type',
        'asset_id', 'status', 'progress', 'input_spec', 'output_dir',
        'output_files', 'error_message', 'started_at', 'finished_at',
        'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.project_id = kwargs.get('project_id')
        self.node_id = kwargs.get('node_id')
        self.engine_type = kwargs.get('engine_type', 'blender_anchor')
        self.asset_id = kwargs.get('asset_id')
        self.status = kwargs.get('status', self.STATUS_PENDING)
        self.progress = kwargs.get('progress', 0)
        self.input_spec = kwargs.get('input_spec')
        self.output_dir = kwargs.get('output_dir')
        self.output_files = kwargs.get('output_files')
        self.error_message = kwargs.get('error_message')
        self.started_at = kwargs.get('started_at')
        self.finished_at = kwargs.get('finished_at')
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
            node_id=row.get('node_id'),
            engine_type=row.get('engine_type'),
            asset_id=row.get('asset_id'),
            status=row.get('status'),
            progress=row.get('progress'),
            input_spec=_json_loads(row.get('input_spec')),
            output_dir=row.get('output_dir'),
            output_files=_json_loads(row.get('output_files')),
            error_message=row.get('error_message'),
            started_at=row.get('started_at'),
            finished_at=row.get('finished_at'),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'node_id': self.node_id,
            'engine_type': self.engine_type,
            'asset_id': self.asset_id,
            'status': self.status,
            'progress': self.progress,
            'input_spec': self.input_spec,
            'output_dir': self.output_dir,
            'output_files': self.output_files,
            'error_message': self.error_message,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'project_id': self.project_id,
            'node_id': self.node_id,
            'engine_type': self.engine_type,
            'asset_id': self.asset_id,
            'status': self.status,
            'progress': self.progress,
            'input_spec': _json_dumps(self.input_spec),
            'output_dir': self.output_dir,
            'output_files': _json_dumps(self.output_files),
            'error_message': self.error_message,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class SchedulerPolicy(BaseModel):
    """Scheduler scoring algorithm configuration."""
    TABLE_NAME = 'scheduler_policies'

    POLICY_LOWEST_COST = 'lowest_cost'
    POLICY_LOWEST_LATENCY = 'lowest_latency'
    POLICY_SHORTEST_QUEUE = 'shortest_queue'
    POLICY_HIGHEST_PERFORMANCE = 'highest_performance'
    POLICY_LOCAL_FIRST = 'local_first'

    COLUMNS = [
        'id', 'tenant_id', 'name', 'policy_type', 'scoring_weights',
        'rules', 'enabled', 'created_at', 'updated_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.name = kwargs.get('name', '')
        self.policy_type = kwargs.get('policy_type')
        self.scoring_weights = kwargs.get('scoring_weights')
        self.rules = kwargs.get('rules')
        self.enabled = kwargs.get('enabled', 1)
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
            policy_type=row.get('policy_type'),
            scoring_weights=_json_loads(row.get('scoring_weights')),
            rules=_json_loads(row.get('rules')),
            enabled=row.get('enabled', 1),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'policy_type': self.policy_type,
            'scoring_weights': self.scoring_weights,
            'rules': self.rules,
            'enabled': bool(self.enabled),
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'policy_type': self.policy_type,
            'scoring_weights': _json_dumps(self.scoring_weights),
            'rules': _json_dumps(self.rules),
            'enabled': 1 if self.enabled else 0,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class HealthCheck(BaseModel):
    """Health check records for nodes and services."""
    TABLE_NAME = 'health_checks'

    STATUS_OK = 'ok'
    STATUS_ERROR = 'error'
    STATUS_WARNING = 'warning'

    COLUMNS = [
        'id', 'target_type', 'target_id', 'status', 'latency_ms',
        'error_message', 'checked_at', 'created_at'
    ]

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.target_type = kwargs.get('target_type')
        self.target_id = kwargs.get('target_id')
        self.status = kwargs.get('status', self.STATUS_OK)
        self.latency_ms = kwargs.get('latency_ms')
        self.error_message = kwargs.get('error_message')
        self.checked_at = kwargs.get('checked_at') or _now()
        self.created_at = kwargs.get('created_at') or _now()

    @classmethod
    def from_row(cls, row):
        if row is None:
            return None
        return cls(
            id=row.get('id'),
            target_type=row.get('target_type'),
            target_id=row.get('target_id'),
            status=row.get('status'),
            latency_ms=row.get('latency_ms'),
            error_message=row.get('error_message'),
            checked_at=row.get('checked_at'),
            created_at=row.get('created_at')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'status': self.status,
            'latency_ms': self.latency_ms,
            'error_message': self.error_message,
            'checked_at': self.checked_at,
            'created_at': self.created_at
        }

    def to_insert_params(self):
        return {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'status': self.status,
            'latency_ms': self.latency_ms,
            'error_message': self.error_message,
            'checked_at': self.checked_at,
            'created_at': self.created_at
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
        'download_url', 'asset_id', 'timeline_version',
        'created_at', 'updated_at', 'created_by'
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
        self.asset_id = kwargs.get('asset_id')
        self.timeline_version = kwargs.get('timeline_version')
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
            asset_id=row.get('asset_id'),
            timeline_version=row.get('timeline_version'),
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
            'asset_id': self.asset_id,
            'timeline_version': self.timeline_version,
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
            'asset_id': self.asset_id,
            'timeline_version': self.timeline_version,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'created_by': self.created_by,
        }


# ── Phase 3 Models: Alerting, Task Attempts, Auth ──


class AlertRule(BaseModel):
    TABLE_NAME = 'alert_rules'
    COLUMNS = ['id', 'tenant_id', 'rule_type', 'target_type', 'metric_name',
               'operator', 'threshold', 'duration_s', 'severity', 'enabled',
               'metadata', 'created_at', 'updated_at']

    RULE_TYPE_THRESHOLD = 'threshold'
    RULE_TYPE_HEARTBEAT = 'heartbeat'
    RULE_TYPE_HEALTH_CHECK = 'health_check'
    RULE_TYPE_BUDGET = 'budget'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.rule_type = kwargs.get('rule_type', '')
        self.target_type = kwargs.get('target_type')
        self.metric_name = kwargs.get('metric_name')
        self.operator = kwargs.get('operator', 'gt')
        self.threshold = kwargs.get('threshold', 0)
        self.duration_s = kwargs.get('duration_s', 30)
        self.severity = kwargs.get('severity', 'warning')
        self.enabled = kwargs.get('enabled', 1)
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row['id'], tenant_id=row.get('tenant_id'),
            rule_type=row['rule_type'], target_type=row.get('target_type'),
            metric_name=row.get('metric_name'), operator=row.get('operator'),
            threshold=row.get('threshold', 0), duration_s=row.get('duration_s', 30),
            severity=row.get('severity', 'warning'), enabled=row.get('enabled', 1),
            metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'), updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        result = {}
        for col in self.COLUMNS:
            val = getattr(self, col, None)
            if col == 'metadata':
                result[col] = val
            elif col == 'enabled':
                result[col] = bool(val)
            else:
                result[col] = val
        return result

    def to_insert_params(self):
        return {col: getattr(self, col) if col != 'metadata' else _json_dumps(getattr(self, col))
                for col in self.COLUMNS}


class Alert(BaseModel):
    TABLE_NAME = 'alerts'
    COLUMNS = ['id', 'tenant_id', 'rule_id', 'target_type', 'target_id', 'metric_name',
               'current_value', 'threshold_value', 'status', 'severity',
               'first_triggered_at', 'last_triggered_at', 'recovered_at', 'closed_at',
               'acknowledged_by', 'closed_by', 'notes', 'metadata', 'created_at', 'updated_at']

    STATUS_OPEN = 'open'
    STATUS_ACKNOWLEDGED = 'acknowledged'
    STATUS_PROCESSING = 'processing'
    STATUS_RECOVERED = 'recovered'
    STATUS_CLOSED = 'closed'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.tenant_id = kwargs.get('tenant_id')
        self.rule_id = kwargs.get('rule_id')
        self.target_type = kwargs.get('target_type')
        self.target_id = kwargs.get('target_id')
        self.metric_name = kwargs.get('metric_name')
        self.current_value = kwargs.get('current_value')
        self.threshold_value = kwargs.get('threshold_value')
        self.status = kwargs.get('status', 'open')
        self.severity = kwargs.get('severity', 'warning')
        self.first_triggered_at = kwargs.get('first_triggered_at')
        self.last_triggered_at = kwargs.get('last_triggered_at')
        self.recovered_at = kwargs.get('recovered_at')
        self.closed_at = kwargs.get('closed_at')
        self.acknowledged_by = kwargs.get('acknowledged_by')
        self.closed_by = kwargs.get('closed_by')
        self.notes = kwargs.get('notes')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row['id'], tenant_id=row.get('tenant_id'),
            rule_id=row.get('rule_id'), target_type=row.get('target_type'),
            target_id=row.get('target_id'), metric_name=row.get('metric_name'),
            current_value=row.get('current_value'), threshold_value=row.get('threshold_value'),
            status=row.get('status', 'open'), severity=row.get('severity', 'warning'),
            first_triggered_at=row.get('first_triggered_at'), last_triggered_at=row.get('last_triggered_at'),
            recovered_at=row.get('recovered_at'), closed_at=row.get('closed_at'),
            acknowledged_by=row.get('acknowledged_by'), closed_by=row.get('closed_by'),
            notes=row.get('notes'), metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'), updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        result = {}
        for col in self.COLUMNS:
            val = getattr(self, col, None)
            if col == 'metadata':
                result[col] = val
            else:
                result[col] = val
        return result

    def to_insert_params(self):
        return {col: getattr(self, col) if col != 'metadata' else _json_dumps(getattr(self, col))
                for col in self.COLUMNS}


class AlertEvent(BaseModel):
    TABLE_NAME = 'alert_events'
    COLUMNS = ['id', 'alert_id', 'event_type', 'user_id', 'message', 'metadata', 'created_at']

    EVENT_TRIGGERED = 'triggered'
    EVENT_ACKNOWLEDGED = 'acknowledged'
    EVENT_ASSIGNED = 'assigned'
    EVENT_RECOVERED = 'recovered'
    EVENT_CLOSED = 'closed'
    EVENT_COMMENTED = 'commented'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.alert_id = kwargs.get('alert_id', '')
        self.event_type = kwargs.get('event_type', '')
        self.user_id = kwargs.get('user_id')
        self.message = kwargs.get('message')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row['id'], alert_id=row['alert_id'],
            event_type=row['event_type'], user_id=row.get('user_id'),
            message=row.get('message'), metadata=_json_loads(row.get('metadata')),
            created_at=row.get('created_at'),
        )

    def to_dict(self):
        result = {}
        for col in self.COLUMNS:
            val = getattr(self, col, None)
            if col == 'metadata':
                result[col] = val
            else:
                result[col] = val
        return result

    def to_insert_params(self):
        return {col: getattr(self, col) if col != 'metadata' else _json_dumps(getattr(self, col))
                for col in self.COLUMNS}


class TaskAttempt(BaseModel):
    TABLE_NAME = 'task_attempts'
    COLUMNS = ['id', 'job_id', 'attempt_number', 'node_id', 'allocation_id',
               'status', 'started_at', 'finished_at', 'error_message', 'metadata', 'created_at']

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.job_id = kwargs.get('job_id', '')
        self.attempt_number = kwargs.get('attempt_number', 1)
        self.node_id = kwargs.get('node_id')
        self.allocation_id = kwargs.get('allocation_id')
        self.status = kwargs.get('status', 'pending')
        self.started_at = kwargs.get('started_at')
        self.finished_at = kwargs.get('finished_at')
        self.error_message = kwargs.get('error_message')
        self.metadata = kwargs.get('metadata')
        self.created_at = kwargs.get('created_at') or _now()

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row['id'], job_id=row['job_id'],
            attempt_number=row.get('attempt_number', 1),
            node_id=row.get('node_id'), allocation_id=row.get('allocation_id'),
            status=row.get('status', 'pending'), started_at=row.get('started_at'),
            finished_at=row.get('finished_at'), error_message=row.get('error_message'),
            metadata=_json_loads(row.get('metadata')), created_at=row.get('created_at'),
        )

    def to_dict(self):
        result = {}
        for col in self.COLUMNS:
            val = getattr(self, col, None)
            if col == 'metadata':
                result[col] = val
            else:
                result[col] = val
        return result

    def to_insert_params(self):
        return {col: getattr(self, col) if col != 'metadata' else _json_dumps(getattr(self, col))
                for col in self.COLUMNS}


class AuthUser(BaseModel):
    TABLE_NAME = 'auth_users'
    COLUMNS = ['id', 'username', 'email', 'password_hash', 'tenant_id', 'user_id',
               'is_active', 'last_login_at', 'failed_login_count', 'locked_until',
               'created_at', 'updated_at']

    def __init__(self, **kwargs):
        self.id = kwargs.get('id') or _generate_id()
        self.username = kwargs.get('username', '')
        self.email = kwargs.get('email')
        self.password_hash = kwargs.get('password_hash', '')
        self.tenant_id = kwargs.get('tenant_id')
        self.user_id = kwargs.get('user_id')
        self.is_active = kwargs.get('is_active', 1)
        self.last_login_at = kwargs.get('last_login_at')
        self.failed_login_count = kwargs.get('failed_login_count', 0)
        self.locked_until = kwargs.get('locked_until')
        self.created_at = kwargs.get('created_at') or _now()
        self.updated_at = kwargs.get('updated_at') or _now()

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row['id'], username=row['username'], email=row.get('email'),
            password_hash=row['password_hash'], tenant_id=row.get('tenant_id'),
            user_id=row.get('user_id'), is_active=row.get('is_active', 1),
            last_login_at=row.get('last_login_at'),
            failed_login_count=row.get('failed_login_count', 0),
            locked_until=row.get('locked_until'),
            created_at=row.get('created_at'), updated_at=row.get('updated_at'),
        )

    def to_dict(self):
        result = {}
        for col in self.COLUMNS:
            val = getattr(self, col, None)
            if col == 'password_hash':
                continue  # Never expose password hash
            if col == 'is_active':
                result[col] = bool(val)
            else:
                result[col] = val
        return result

    def to_insert_params(self):
        return {col: getattr(self, col) for col in self.COLUMNS}
