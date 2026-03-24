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
        """Create model instance from database row."""
        raise NotImplementedError

    def to_dict(self):
        """Convert model to dictionary."""
        raise NotImplementedError

    def to_insert_params(self):
        """Get parameters for INSERT query."""
        raise NotImplementedError


class Asset(BaseModel):
    """
    Asset model for 3D models, images, and other resources.

    asset_type: 'glb', 'image', 'prompt_doc', 'spatial_anchor'
    """

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
        """Create Asset from database row."""
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
        """Convert Asset to dictionary."""
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
        """Get parameters for INSERT query."""
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
    """
    Prompt document model for storing reusable prompt templates.
    """

    TABLE_NAME = 'prompt_documents'
    COLUMNS = [
        'id', 'title', 'category', 'content', 'keywords',
        'source_file', 'created_at', 'updated_at'
    ]

    # Category constants
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
        """Create PromptDocument from database row."""
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
        """Convert PromptDocument to dictionary."""
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
        """Get parameters for INSERT query."""
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
    """
    Venue preset model for storing venue configurations.
    """

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
        """Create VenuePreset from database row."""
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
        """Convert VenuePreset to dictionary."""
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
        """Get parameters for INSERT query."""
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
    """
    Model configuration for video generation providers.
    """

    TABLE_NAME = 'model_configs'
    COLUMNS = [
        'id', 'display_model', 'execution_provider', 'route_mode',
        'status', 'description', 'style_hint', 'recommended',
        'created_at', 'updated_at'
    ]

    # Route mode constants
    ROUTE_NATIVE = 'native'
    ROUTE_DEMO = 'demo-route'
    ROUTE_PREVIEW = 'preview-only'
    ROUTE_OPTIONAL = 'optional'

    # Status constants
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
        """Create ModelConfig from database row."""
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
        """Convert ModelConfig to dictionary."""
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
        """Get parameters for INSERT query."""
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
    """
    Job history model for tracking video generation jobs.
    """

    TABLE_NAME = 'job_history'
    COLUMNS = [
        'id', 'status', 'stage', 'payload', 'result',
        'error', 'created_at', 'updated_at'
    ]

    # Status constants
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
        """Create JobHistory from database row."""
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
        """Convert JobHistory to dictionary."""
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
        """Get parameters for INSERT query."""
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