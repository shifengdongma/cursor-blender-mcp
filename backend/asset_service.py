# -*- coding: utf-8 -*-
"""
Asset management service for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import logging
import os
import time
import uuid
import shutil

from .database import get_database
from .models import Asset

logger = logging.getLogger(__name__)


class AssetServiceError(RuntimeError):
    """Custom error for asset service."""
    pass


class AssetService(object):
    """
    Service for managing assets (3D models, images, prompt documents).
    """

    # Asset type constants
    TYPE_GLB = 'glb'
    TYPE_IMAGE = 'image'
    TYPE_PROMPT_DOC = 'prompt_doc'
    TYPE_SPATIAL_ANCHOR = 'spatial_anchor'

    # Venue type constants
    VENUE_THEATER = 'grand_theater'
    VENUE_GALLERY = 'modern_gallery'
    VENUE_MUSEUM = 'ancient_museum'
    VENUE_CONCERT = 'concert_hall'

    def __init__(self, data_dir=None):
        """
        Initialize asset service.

        Args:
            data_dir: Base data directory for asset storage
        """
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.assets_dir = os.path.join(self.data_dir, 'assets')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

        # Ensure asset directories exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure asset storage directories exist."""
        subdirs = [
            'models/theater', 'models/gallery', 'models/museum', 'models/concert',
            'images/textures', 'images/previews', 'images/references',
            'prompts/venues', 'prompts/shots', 'prompts/styles'
        ]
        for subdir in subdirs:
            path = os.path.join(self.assets_dir, subdir)
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)

    def _get_storage_path(self, asset_type, venue_type=None, filename=None):
        """
        Get storage path for an asset.

        Args:
            asset_type: Type of asset (glb, image, prompt_doc)
            venue_type: Venue type for organizing assets
            filename: Optional filename

        Returns:
            str: Storage path relative to assets directory
        """
        if asset_type == self.TYPE_GLB:
            venue = venue_type or 'general'
            return os.path.join('models', venue, filename) if filename else os.path.join('models', venue)
        elif asset_type == self.TYPE_IMAGE:
            return os.path.join('images', 'references', filename) if filename else os.path.join('images', 'references')
        elif asset_type == self.TYPE_PROMPT_DOC:
            return os.path.join('prompts', filename) if filename else 'prompts'
        else:
            return filename

    def list_assets(self, asset_type=None, venue_type=None, limit=100, offset=0):
        """
        List assets with optional filtering.

        Args:
            asset_type: Filter by asset type
            venue_type: Filter by venue type
            limit: Maximum number of results
            offset: Result offset for pagination

        Returns:
            list: List of Asset objects
        """
        conditions = []
        params = []

        if asset_type:
            conditions.append('asset_type = ?')
            params.append(asset_type)

        if venue_type:
            conditions.append('venue_type = ?')
            params.append(venue_type)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        query = 'SELECT * FROM assets WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?'.format(where_clause)
        params.extend([limit, offset])

        rows = self.db.fetch_all(query, tuple(params))
        return [Asset.from_row(row) for row in rows]

    def get_asset(self, asset_id):
        """
        Get an asset by ID.

        Args:
            asset_id: Asset ID

        Returns:
            Asset: Asset object or None
        """
        row = self.db.fetch_one(
            'SELECT * FROM assets WHERE id = ?',
            (asset_id,)
        )
        return Asset.from_row(row)

    def create_asset(self, name, asset_type, venue_type=None, file_path=None,
                     file_size=0, description=None, metadata=None):
        """
        Create a new asset.

        Args:
            name: Asset name
            asset_type: Type of asset
            venue_type: Venue type
            file_path: Path to stored file
            file_size: File size in bytes
            description: Asset description
            metadata: Additional metadata dict

        Returns:
            Asset: Created asset
        """
        asset = Asset(
            name=name,
            asset_type=asset_type,
            venue_type=venue_type,
            file_path=file_path,
            file_size=file_size,
            description=description,
            metadata=metadata
        )

        self.db.insert(Asset.TABLE_NAME, asset.to_insert_params())
        logger.info("Created asset: %s (%s)", asset.id, name)
        return asset

    def update_asset(self, asset_id, **kwargs):
        """
        Update an asset.

        Args:
            asset_id: Asset ID
            **kwargs: Fields to update

        Returns:
            Asset: Updated asset or None
        """
        asset = self.get_asset(asset_id)
        if not asset:
            return None

        # Update fields
        for key, value in kwargs.items():
            if hasattr(asset, key):
                setattr(asset, key, value)

        asset.updated_at = int(time.time())

        self.db.update(
            Asset.TABLE_NAME,
            asset.to_insert_params(),
            'id = ?',
            (asset_id,)
        )

        logger.info("Updated asset: %s", asset_id)
        return asset

    def delete_asset(self, asset_id):
        """
        Delete an asset and its associated file.

        Args:
            asset_id: Asset ID

        Returns:
            bool: True if deleted, False if not found
        """
        asset = self.get_asset(asset_id)
        if not asset:
            return False

        # Delete file if exists
        if asset.file_path:
            full_path = os.path.join(self.assets_dir, asset.file_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info("Deleted file: %s", full_path)

        # Delete thumbnail if exists
        if asset.thumbnail_path:
            thumb_path = os.path.join(self.assets_dir, asset.thumbnail_path)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        # Delete from database
        self.db.delete(Asset.TABLE_NAME, 'id = ?', (asset_id,))
        logger.info("Deleted asset: %s", asset_id)
        return True

    def store_file(self, uploaded_file, asset_type, venue_type=None):
        """
        Store an uploaded file and return the relative path.

        Args:
            uploaded_file: File-like object with read() method
            asset_type: Type of asset
            venue_type: Venue type for organizing

        Returns:
            tuple: (relative_path, file_size)
        """
        # Generate unique filename
        original_name = getattr(uploaded_file, 'filename', 'file')
        ext = os.path.splitext(original_name)[1] or ''
        filename = '{0}{1}'.format(str(uuid.uuid4()), ext)

        # Get storage path
        rel_dir = self._get_storage_path(asset_type, venue_type)
        rel_path = os.path.join(rel_dir, filename)
        full_path = os.path.join(self.assets_dir, rel_path)

        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write file
        file_size = 0
        with open(full_path, 'wb') as f:
            while True:
                chunk = uploaded_file.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                file_size += len(chunk)

        logger.info("Stored file: %s (%d bytes)", rel_path, file_size)
        return rel_path, file_size

    def get_file_path(self, asset_id):
        """
        Get the full file path for an asset.

        Args:
            asset_id: Asset ID

        Returns:
            str: Full file path or None
        """
        asset = self.get_asset(asset_id)
        if not asset or not asset.file_path:
            return None

        return os.path.join(self.assets_dir, asset.file_path)

    def count_assets(self, asset_type=None, venue_type=None):
        """
        Count assets with optional filtering.

        Args:
            asset_type: Filter by asset type
            venue_type: Filter by venue type

        Returns:
            int: Number of assets
        """
        conditions = []
        params = []

        if asset_type:
            conditions.append('asset_type = ?')
            params.append(asset_type)

        if venue_type:
            conditions.append('venue_type = ?')
            params.append(venue_type)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        return self.db.count(Asset.TABLE_NAME, where_clause, tuple(params) if params else None)

    def search_assets(self, query, asset_type=None, limit=20):
        """
        Search assets by name or description.

        Args:
            query: Search query string
            asset_type: Optional asset type filter
            limit: Maximum results

        Returns:
            list: List of matching Asset objects
        """
        search_pattern = '%{0}%'.format(query)
        conditions = ['(name LIKE ? OR description LIKE ?)']
        params = [search_pattern, search_pattern]

        if asset_type:
            conditions.append('asset_type = ?')
            params.append(asset_type)

        where_clause = ' AND '.join(conditions)
        sql = 'SELECT * FROM assets WHERE {0} ORDER BY created_at DESC LIMIT ?'.format(where_clause)
        params.append(limit)

        rows = self.db.fetch_all(sql, tuple(params))
        return [Asset.from_row(row) for row in rows]


# Global service instance
_asset_service = None


def get_asset_service(data_dir=None):
    """
    Get or create the global asset service instance.

    Args:
        data_dir: Base data directory

    Returns:
        AssetService: Global service instance
    """
    global _asset_service
    if _asset_service is None:
        _asset_service = AssetService(data_dir)
    return _asset_service