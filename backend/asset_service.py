# -*- coding: utf-8 -*-
"""Asset storage and ownership-aware asset management.

Stored ``file_path`` values are relative to the assets directory.  All file
resolution goes through ``_safe_asset_path``; absolute paths and traversal are
rejected.  Legacy absolute paths are accepted only when they resolve inside the
assets directory.
"""
from __future__ import absolute_import

import hashlib
import json
import logging
import os
import time
import uuid

from .access import can_write_asset
from .database import get_database
from .models import Asset

logger = logging.getLogger(__name__)


class AssetServiceError(RuntimeError):
    """Custom error for asset service."""


class AssetService(object):
    TYPE_GLB = 'glb'
    TYPE_IMAGE = 'image'
    TYPE_PROMPT_DOC = 'prompt_doc'
    TYPE_SPATIAL_ANCHOR = 'spatial_anchor'
    TYPE_VIDEO = 'video'
    TYPE_AUDIO = 'audio'
    TYPE_DOCUMENT = 'document'
    TYPE_ARCHIVE = 'archive'

    VENUE_THEATER = 'grand_theater'
    VENUE_GALLERY = 'modern_gallery'
    VENUE_MUSEUM = 'ancient_museum'
    VENUE_CONCERT = 'concert_hall'
    VALID_VENUES = {VENUE_THEATER, VENUE_GALLERY, VENUE_MUSEUM, VENUE_CONCERT}

    # SVG is intentionally excluded from uploadable images (stored XSS risk).
    ALLOWED_EXTENSIONS = {
        TYPE_GLB: ['glb', 'gltf', 'obj', 'fbx', 'stl', 'blend', 'dae', '3ds', 'ply'],
        TYPE_IMAGE: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'tif', 'ico', 'heic', 'avif'],
        TYPE_VIDEO: ['mp4', 'mov', 'avi', 'webm', 'mkv', 'flv', 'm4v', 'mpeg', 'mpg', 'wmv'],
        TYPE_AUDIO: ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus'],
        TYPE_DOCUMENT: ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'md', 'csv', 'rtf', 'odt', 'json', 'xml', 'yaml', 'yml'],
        TYPE_ARCHIVE: ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'],
    }

    _EXTENSION_TO_TYPE = {
        ext: asset_type
        for asset_type, exts in ALLOWED_EXTENSIONS.items()
        for ext in exts
    }

    _UPDATE_FIELDS = {'name', 'description', 'venue_type', 'metadata', 'visibility'}

    VALID_VISIBILITIES = {'private', 'shared'}
    NAME_MAX_LENGTH = 120
    DESCRIPTION_MAX_LENGTH = 2000

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.assets_dir = os.path.join(self.data_dir, 'assets')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))
        self._ensure_directories()

    def _ensure_directories(self):
        subdirs = [
            'models/theater', 'models/gallery', 'models/museum', 'models/concert',
            'images/textures', 'images/previews', 'images/references',
            'prompts/venues', 'prompts/shots', 'prompts/styles',
            'videos', 'audio', 'documents', 'archives', 'generated',
        ]
        for subdir in subdirs:
            path = os.path.join(self.assets_dir, subdir)
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)

    # ── Path safety ──

    def _safe_asset_path(self, rel_path, must_exist=False):
        if not rel_path:
            return None
        rel_path = str(rel_path)
        real_base = os.path.realpath(self.assets_dir)
        if os.path.isabs(rel_path):
            candidate = os.path.realpath(rel_path)
        else:
            candidate = os.path.realpath(os.path.join(self.assets_dir, rel_path))
        if candidate != real_base and not candidate.startswith(real_base + os.sep):
            logger.warning("Rejected asset path outside assets directory: %s", rel_path)
            return None
        if must_exist and not os.path.exists(candidate):
            return None
        return candidate

    def _relative_asset_path(self, full_path):
        real_base = os.path.realpath(self.assets_dir)
        candidate = os.path.realpath(full_path)
        if not candidate.startswith(real_base + os.sep):
            raise AssetServiceError("Asset path outside assets directory")
        return os.path.relpath(candidate, real_base)

    def _validate_venue(self, venue_type):
        if venue_type in (None, ''):
            return None
        if not isinstance(venue_type, str):
            raise AssetServiceError("Unsupported venue_type")
        if venue_type not in self.VALID_VENUES:
            raise AssetServiceError("Unsupported venue_type")
        return venue_type

    def _validate_name(self, name):
        if not isinstance(name, str):
            raise AssetServiceError("资产名称必须是字符串")
        name = name.strip()
        if not name:
            raise AssetServiceError("资产名称不能为空")
        if len(name) > self.NAME_MAX_LENGTH:
            raise AssetServiceError(
                "资产名称不能超过 {0} 个字符".format(self.NAME_MAX_LENGTH)
            )
        return name

    def _validate_description(self, description):
        if description is None:
            return None
        if not isinstance(description, str):
            raise AssetServiceError("资产描述必须是字符串")
        if len(description) > self.DESCRIPTION_MAX_LENGTH:
            raise AssetServiceError(
                "资产描述不能超过 {0} 个字符".format(self.DESCRIPTION_MAX_LENGTH)
            )
        return description

    def _validate_visibility(self, visibility):
        if not isinstance(visibility, str) or visibility not in self.VALID_VISIBILITIES:
            raise AssetServiceError("可见性只能是 private 或 shared")
        return visibility

    # ── Classification / storage paths ──

    def _get_storage_path(self, asset_type, venue_type=None, filename=None):
        if asset_type == self.TYPE_GLB:
            venue = venue_type or 'general'
            return os.path.join('models', venue, filename) if filename else os.path.join('models', venue)
        elif asset_type == self.TYPE_IMAGE:
            return os.path.join('images', 'references', filename) if filename else os.path.join('images', 'references')
        elif asset_type == self.TYPE_PROMPT_DOC:
            return os.path.join('prompts', filename) if filename else 'prompts'
        elif asset_type == self.TYPE_VIDEO:
            return os.path.join('videos', filename) if filename else 'videos'
        elif asset_type == self.TYPE_AUDIO:
            return os.path.join('audio', filename) if filename else 'audio'
        elif asset_type == self.TYPE_DOCUMENT:
            return os.path.join('documents', filename) if filename else 'documents'
        elif asset_type == self.TYPE_ARCHIVE:
            return os.path.join('archives', filename) if filename else 'archives'
        else:
            return filename

    def classify_filename(self, filename):
        ext = os.path.splitext(filename or '')[1].lstrip('.').lower()
        return self._EXTENSION_TO_TYPE.get(ext)

    def allowed_extensions_list(self):
        return sorted(self._EXTENSION_TO_TYPE.keys())

    def extension_for(self, filename):
        return os.path.splitext(filename or '')[1].lstrip('.').lower()

    # ── Queries ──

    def list_assets(self, asset_type=None, venue_type=None, limit=100, offset=0,
                    owner_user_id=None, include_shared=False, tenant_id=None, q=None):
        conditions = []
        params = []
        if asset_type:
            conditions.append('asset_type = ?')
            params.append(asset_type)
        if venue_type:
            conditions.append('venue_type = ?')
            params.append(venue_type)
        if owner_user_id:
            if include_shared:
                conditions.append(
                    "(owner_user_id = ? "
                    "OR (visibility = 'shared' AND (tenant_id = ? OR tenant_id IS NULL)) "
                    "OR owner_user_id IS NULL)"
                )
                params.extend([owner_user_id, tenant_id])
            else:
                conditions.append('owner_user_id = ?')
                params.append(owner_user_id)
        if q:
            like = '%{0}%'.format(q.strip())
            conditions.append('(name LIKE ? OR description LIKE ?)')
            params.extend([like, like])
        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        rows = self.db.fetch_all(
            'SELECT * FROM assets WHERE {0} ORDER BY created_at DESC LIMIT ? OFFSET ?'.format(where_clause),
            tuple(params) + (int(limit), int(offset)),
        )
        return [Asset.from_row(row) for row in rows]

    def count_assets(self, asset_type=None, venue_type=None, owner_user_id=None,
                     include_shared=False, tenant_id=None, q=None):
        conditions = []
        params = []
        if asset_type:
            conditions.append('asset_type = ?')
            params.append(asset_type)
        if venue_type:
            conditions.append('venue_type = ?')
            params.append(venue_type)
        if owner_user_id:
            if include_shared:
                conditions.append(
                    "(owner_user_id = ? "
                    "OR (visibility = 'shared' AND (tenant_id = ? OR tenant_id IS NULL)) "
                    "OR owner_user_id IS NULL)"
                )
                params.extend([owner_user_id, tenant_id])
            else:
                conditions.append('owner_user_id = ?')
                params.append(owner_user_id)
        if q:
            like = '%{0}%'.format(q.strip())
            conditions.append('(name LIKE ? OR description LIKE ?)')
            params.extend([like, like])
        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        return self.db.count(Asset.TABLE_NAME, where_clause, tuple(params) if params else None)

    def get_asset(self, asset_id):
        row = self.db.fetch_one('SELECT * FROM assets WHERE id = ?', (asset_id,))
        return Asset.from_row(row)

    # ── CRUD ──

    def create_asset(self, name, asset_type, venue_type=None, file_path=None,
                     file_size=0, description=None, metadata=None,
                     owner_user_id=None, tenant_id=None, visibility=None,
                     checksum_sha256=None, cursor=None):
        venue_type = self._validate_venue(venue_type)
        asset = Asset(
            name=name,
            asset_type=asset_type,
            venue_type=venue_type,
            file_path=file_path,
            file_size=file_size,
            description=description,
            metadata=metadata,
            owner_user_id=owner_user_id,
            tenant_id=tenant_id,
            visibility=visibility,
            checksum_sha256=checksum_sha256,
        )
        params = asset.to_insert_params()
        if cursor is None:
            self.db.insert(Asset.TABLE_NAME, params)
        else:
            columns = list(params.keys())
            cursor.execute(
                "INSERT INTO {0} ({1}) VALUES ({2})".format(
                    Asset.TABLE_NAME,
                    ", ".join(columns),
                    ", ".join("?" for _ in columns),
                ),
                tuple(params[column] for column in columns),
            )
        logger.info("Created asset: %s (%s)", asset.id, name)
        return asset

    def update_asset(self, asset_id, **kwargs):
        """Update an asset. Only presentation metadata is mutable."""
        asset = self.get_asset(asset_id)
        if not asset:
            return None
        updates = {}
        for key, value in kwargs.items():
            if key not in self._UPDATE_FIELDS:
                continue
            if key == 'name':
                value = self._validate_name(value)
            elif key == 'description':
                value = self._validate_description(value)
            elif key == 'venue_type':
                value = self._validate_venue(value)
            elif key == 'visibility':
                value = self._validate_visibility(value)
                # Ownerless rows are the historical shared library; the
                # read rule and list predicate require them to stay shared.
                if value == 'private' and asset.owner_user_id is None:
                    raise AssetServiceError("无主历史素材必须保持共享，不能设为私有")
            elif key == 'metadata' and value is not None and not isinstance(value, dict):
                raise AssetServiceError("metadata must be an object")
            setattr(asset, key, value)
            updates[key] = json.dumps(value, ensure_ascii=False) if key == 'metadata' else value
        if not updates:
            return asset
        updates['updated_at'] = int(time.time())
        self.db.update(Asset.TABLE_NAME, updates, 'id = ?', (asset_id,))
        logger.info("Updated asset: %s", asset_id)
        return self.get_asset(asset_id)

    def asset_reference_breakdown(self, asset_id):
        """Count hard references to an asset, including active generation tasks."""
        db = self.db
        shots = db.count(
            'storyboard_shots',
            '(primary_image_asset_id = ? OR keyframe_asset_id = ? OR video_asset_id = ? OR audio_asset_id = ?)',
            (asset_id, asset_id, asset_id, asset_id),
        )
        artifacts = db.count('task_artifacts', 'asset_id = ?', (asset_id,))
        timeline = db.count('timeline_clips', 'asset_id = ?', (asset_id,))
        # New tasks store target_asset_id; legacy queued tasks only mention the
        # asset inside params JSON, so match both while the task is active.
        active_tasks = db.count(
            'generation_tasks',
            "status IN ('queued','submitting','running') "
            "AND (target_asset_id = ? OR params LIKE ?)",
            (asset_id, '%{0}%'.format(asset_id)),
        )
        return {
            'shots': shots,
            'artifacts': artifacts,
            'timeline': timeline,
            'active_tasks': active_tasks,
        }

    def asset_reference_count(self, asset_id):
        breakdown = self.asset_reference_breakdown(asset_id)
        return sum(breakdown.values())

    def delete_asset(self, asset_id):
        asset = self.get_asset(asset_id)
        if not asset:
            return False
        if asset.file_path:
            full_path = self._safe_asset_path(asset.file_path, must_exist=False)
            if full_path and os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except OSError as exc:
                    logger.warning("Failed to delete asset file %s: %s", full_path, exc)
        if asset.thumbnail_path:
            thumb_path = self._safe_asset_path(asset.thumbnail_path, must_exist=False)
            if thumb_path and os.path.isfile(thumb_path):
                try:
                    os.remove(thumb_path)
                except OSError:
                    pass
        self.db.delete(Asset.TABLE_NAME, 'id = ?', (asset_id,))
        logger.info("Deleted asset: %s", asset_id)
        return True

    def store_file(self, uploaded_file, asset_type, venue_type=None, max_bytes=None):
        """Store an uploaded file and return (relative_path, file_size, sha256)."""
        original_name = getattr(uploaded_file, 'filename', 'file') or 'file'
        ext = self.extension_for(original_name)
        if self.classify_filename(original_name) != asset_type:
            raise AssetServiceError("File extension does not match asset type")
        venue_type = self._validate_venue(venue_type)
        filename = '{0}.{1}'.format(uuid.uuid4(), ext)
        rel_dir = self._get_storage_path(asset_type, venue_type)
        rel_path = os.path.join(rel_dir, filename)
        full_path = self._safe_asset_path(rel_path)
        if not full_path:
            raise AssetServiceError("Invalid storage path")
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        size = 0
        digest = hashlib.sha256()
        try:
            with open(full_path, 'wb') as handle:
                while True:
                    chunk = uploaded_file.read(8192)
                    if not chunk:
                        break
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise AssetServiceError("上传文件超过大小限制")
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception:
            try:
                os.remove(full_path)
            except OSError:
                pass
            raise

        if asset_type == self.TYPE_IMAGE and not self._is_allowed_image(full_path):
            try:
                os.remove(full_path)
            except OSError:
                pass
            raise AssetServiceError("图片文件类型校验失败")

        logger.info("Stored file: %s (%d bytes)", rel_path, size)
        return rel_path, size, digest.hexdigest()

    def _is_allowed_image(self, path):
        try:
            with open(path, 'rb') as handle:
                head = handle.read(32)
        except OSError:
            return False
        signatures = (
            b'\x89PNG\r\n\x1a\n',
            b'\xff\xd8\xff',
            b'GIF87a',
            b'GIF89a',
            b'BM',
        )
        if head.startswith(signatures):
            return True
        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
            return True
        if head[:4] in (b'II*\x00', b'MM\x00*'):
            return True
        # ISO BMFF (HEIC/AVIF)
        if head[4:8] == b'ftyp':
            return True
        return False

    def get_file_path(self, asset_id):
        asset = self.get_asset(asset_id)
        if not asset or not asset.file_path:
            return None
        return self._safe_asset_path(asset.file_path, must_exist=True)

    def get_file_path_for_asset(self, asset):
        if not asset or not asset.file_path:
            return None
        return self._safe_asset_path(asset.file_path, must_exist=True)

    def public_dict(self, asset, include_owner=False, viewer=None):
        """Safe API representation; deliberately omits filesystem paths."""
        if not asset:
            return None
        item = {
            'id': asset.id,
            'name': asset.name,
            'asset_type': asset.asset_type,
            'venue_type': asset.venue_type,
            'file_size': asset.file_size,
            'description': asset.description,
            'metadata': asset.metadata,
            'visibility': asset.visibility,
            'can_edit': can_write_asset(asset, viewer) if viewer else False,
            'checksum_sha256': asset.checksum_sha256,
            'created_at': asset.created_at,
            'updated_at': asset.updated_at,
            'file_url': '/api/assets/{0}/file'.format(asset.id) if asset.file_path else None,
            'download_url': '/api/assets/{0}/download'.format(asset.id) if asset.file_path else None,
            'thumbnail_url': None,
        }
        if include_owner:
            item['owner_user_id'] = asset.owner_user_id
            item['tenant_id'] = asset.tenant_id
        return item

    def search_assets(self, query, asset_type=None, limit=20):
        return self.list_assets(asset_type=asset_type, limit=limit, q=query)


# Global service instance
_asset_service = None


def get_asset_service(data_dir=None):
    global _asset_service
    if _asset_service is None:
        _asset_service = AssetService(data_dir)
    return _asset_service
