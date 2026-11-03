# -*- coding: utf-8 -*-
"""Unified document library over asset documents and prompt documents.

The two tables are independent (no shared ID or mapping key), so a merged
"文档" category must be paginated and ordered in the database.  This service
builds a UNION ALL page query and then normalizes the selected rows through the
owning services, keeping permission checks authoritative.
"""
from __future__ import absolute_import

import logging

from .asset_service import get_asset_service
from .prompt_doc_service import get_prompt_doc_service

logger = logging.getLogger(__name__)


class DocumentLibraryServiceError(RuntimeError):
    """Raised for invalid unified document query parameters."""


class DocumentLibraryService(object):
    SORT_ORDERS = {
        'newest': 'sort_ts DESC, sort_name COLLATE NOCASE ASC, source_type ASC, sort_id ASC',
        'oldest': 'sort_ts ASC, sort_name COLLATE NOCASE ASC, source_type ASC, sort_id ASC',
        'name': 'sort_name COLLATE NOCASE ASC, sort_ts DESC, source_type ASC, sort_id ASC',
    }
    SOURCE_TYPES = ('all', 'asset', 'prompt_document')
    CONTENT_EXCERPT_LENGTH = 160

    def __init__(self, asset_service, prompt_doc_service):
        self.asset_service = asset_service
        self.prompt_doc_service = prompt_doc_service
        self.db = asset_service.db

    def _asset_scope(self, viewer, is_admin):
        return {
            'owner_user_id': None if is_admin else (viewer or {}).get('id'),
            'include_shared': not is_admin,
            'tenant_id': None if is_admin else (viewer or {}).get('tenant_id'),
        }

    def count_documents(self, viewer, is_admin, q=None, created_after=None,
                        created_before=None, source_type='all'):
        if source_type not in self.SOURCE_TYPES:
            raise DocumentLibraryServiceError('Unsupported source_type')
        scope = self._asset_scope(viewer, is_admin)
        asset_count = 0
        prompt_count = 0
        if source_type in ('all', 'asset'):
            asset_count = self.asset_service.count_assets(
                asset_type=self.asset_service.TYPE_DOCUMENT,
                owner_user_id=scope['owner_user_id'],
                include_shared=scope['include_shared'],
                tenant_id=scope['tenant_id'],
                q=q,
                created_after=created_after,
                created_before=created_before,
            )
        if source_type in ('all', 'prompt_document'):
            prompt_count = self.prompt_doc_service.count_documents(
                q=q,
                created_after=created_after,
                created_before=created_before,
            )
        return {
            'asset': asset_count,
            'prompt_document': prompt_count,
            'total': asset_count + prompt_count,
        }

    def list_documents(self, viewer, is_admin, q=None, created_after=None,
                       created_before=None, sort='newest',
                       source_type='all', limit=12, offset=0):
        if sort not in self.SORT_ORDERS:
            raise DocumentLibraryServiceError('Unsupported sort')
        if source_type not in self.SOURCE_TYPES:
            raise DocumentLibraryServiceError('Unsupported source_type')

        scope = self._asset_scope(viewer, is_admin)
        branches = []
        params = []

        if source_type in ('all', 'asset'):
            conditions, asset_params = self.asset_service.document_filter_conditions(
                owner_user_id=scope['owner_user_id'],
                include_shared=scope['include_shared'],
                tenant_id=scope['tenant_id'],
                q=q,
                created_after=created_after,
                created_before=created_before,
            )
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            branches.append(
                "SELECT id AS sort_id, 'asset' AS source_type, "
                "name AS sort_name, COALESCE(created_at, 0) AS sort_ts "
                "FROM assets WHERE {0}".format(where_clause)
            )
            params.extend(asset_params)

        if source_type in ('all', 'prompt_document'):
            conditions, prompt_params = self.prompt_doc_service.filter_conditions(
                q=q,
                created_after=created_after,
                created_before=created_before,
            )
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            branches.append(
                "SELECT id AS sort_id, 'prompt_document' AS source_type, "
                "title AS sort_name, COALESCE(created_at, 0) AS sort_ts "
                "FROM prompt_documents WHERE {0}".format(where_clause)
            )
            params.extend(prompt_params)

        counts = self.count_documents(
            viewer=viewer,
            is_admin=is_admin,
            q=q,
            created_after=created_after,
            created_before=created_before,
            source_type=source_type,
        )

        if not branches:
            return {
                'items': [],
                'total': 0,
                'limit': int(limit),
                'offset': int(offset),
                'counts': counts,
            }

        union_sql = ' UNION ALL '.join(branches)
        page_sql = (
            'SELECT sort_id, source_type FROM ({0}) '
            'ORDER BY {1} LIMIT ? OFFSET ?'
        ).format(union_sql, self.SORT_ORDERS[sort])
        rows = self.db.fetch_all(
            page_sql,
            tuple(params) + (int(limit), int(offset)),
        )

        asset_ids = [row['sort_id'] for row in rows if row['source_type'] == 'asset']
        prompt_ids = [
            row['sort_id'] for row in rows if row['source_type'] == 'prompt_document'
        ]
        assets = self.asset_service.get_assets_by_ids(asset_ids) if asset_ids else {}
        prompt_docs = (
            self.prompt_doc_service.get_documents_by_ids(prompt_ids)
            if prompt_ids
            else {}
        )

        items = []
        for row in rows:
            source = row['source_type']
            record_id = row['sort_id']
            if source == 'asset':
                asset = assets.get(record_id)
                if not asset:
                    continue
                item = self.asset_service.public_dict(
                    asset,
                    include_owner=is_admin,
                    viewer=viewer,
                )
                item['source_type'] = 'asset'
                item['can_delete'] = bool(item.get('can_edit'))
                item.setdefault('content', None)
                item.setdefault('category', None)
                item.setdefault('keywords', None)
                item['title'] = item.get('name')
                items.append(item)
            elif source == 'prompt_document':
                doc = prompt_docs.get(record_id)
                if not doc:
                    continue
                content = doc.content or ''
                excerpt = content
                if len(excerpt) > self.CONTENT_EXCERPT_LENGTH:
                    excerpt = excerpt[:self.CONTENT_EXCERPT_LENGTH] + '…'
                items.append({
                    'id': doc.id,
                    'source_type': 'prompt_document',
                    'name': doc.title,
                    'title': doc.title,
                    'description': excerpt,
                    'content': excerpt,
                    'category': doc.category,
                    'keywords': doc.keywords,
                    'created_at': doc.created_at,
                    'updated_at': doc.updated_at,
                    'file_size': None,
                    'file_ext': None,
                    'file_url': None,
                    'download_url': None,
                    'previewable': False,
                    'preview_reason': None,
                    'visibility': None,
                    'venue_type': None,
                    'can_edit': bool(is_admin),
                    'can_delete': bool(is_admin),
                })

        return {
            'items': items,
            'total': counts['total'],
            'limit': int(limit),
            'offset': int(offset),
            'counts': counts,
        }


_document_library_service = None


def get_document_library_service(data_dir=None):
    global _document_library_service
    if _document_library_service is None:
        _document_library_service = DocumentLibraryService(
            get_asset_service(data_dir),
            get_prompt_doc_service(data_dir),
        )
    return _document_library_service
