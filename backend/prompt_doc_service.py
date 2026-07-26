# -*- coding: utf-8 -*-
"""
Prompt document service for AIGV Studio.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import json
import logging
import os
import time

from .database import get_database
from .models import PromptDocument

logger = logging.getLogger(__name__)


class PromptDocServiceError(RuntimeError):
    """Custom error for prompt document service."""
    pass


class PromptDocService(object):
    """
    Service for managing prompt documents.
    """

    def __init__(self, data_dir=None):
        """
        Initialize prompt document service.

        Args:
            data_dir: Base data directory
        """
        self.data_dir = data_dir or os.environ.get('DATA_DIR', './data')
        self.prompts_dir = os.path.join(self.data_dir, 'assets', 'prompts')
        self.db = get_database(os.path.join(self.data_dir, 'aigv.db'))

        # Ensure prompts directory exists
        if not os.path.exists(self.prompts_dir):
            os.makedirs(self.prompts_dir, exist_ok=True)

    def list_documents(self, category=None, limit=100, offset=0):
        """
        List prompt documents with optional filtering.

        Args:
            category: Filter by category
            limit: Maximum number of results
            offset: Result offset for pagination

        Returns:
            list: List of PromptDocument objects
        """
        if category:
            query = '''
                SELECT * FROM prompt_documents
                WHERE category = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            '''
            rows = self.db.fetch_all(query, (category, limit, offset))
        else:
            query = '''
                SELECT * FROM prompt_documents
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            '''
            rows = self.db.fetch_all(query, (limit, offset))

        return [PromptDocument.from_row(row) for row in rows]

    def get_document(self, doc_id):
        """
        Get a prompt document by ID.

        Args:
            doc_id: Document ID

        Returns:
            PromptDocument: Document object or None
        """
        row = self.db.fetch_one(
            'SELECT * FROM prompt_documents WHERE id = ?',
            (doc_id,)
        )
        return PromptDocument.from_row(row)

    def create_document(self, title, category=None, content=None,
                        keywords=None, source_file=None):
        """
        Create a new prompt document.

        Args:
            title: Document title
            category: Document category
            content: Prompt content
            keywords: Keywords for search
            source_file: Source file path

        Returns:
            PromptDocument: Created document
        """
        doc = PromptDocument(
            title=title,
            category=category,
            content=content,
            keywords=keywords,
            source_file=source_file
        )

        self.db.insert(PromptDocument.TABLE_NAME, doc.to_insert_params())
        logger.info("Created prompt document: %s (%s)", doc.id, title)
        return doc

    def update_document(self, doc_id, **kwargs):
        """
        Update a prompt document.

        Args:
            doc_id: Document ID
            **kwargs: Fields to update

        Returns:
            PromptDocument: Updated document or None
        """
        doc = self.get_document(doc_id)
        if not doc:
            return None

        # Update fields
        for key, value in kwargs.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        doc.updated_at = int(time.time())

        self.db.update(
            PromptDocument.TABLE_NAME,
            doc.to_insert_params(),
            'id = ?',
            (doc_id,)
        )

        logger.info("Updated prompt document: %s", doc_id)
        return doc

    def delete_document(self, doc_id):
        """
        Delete a prompt document.

        Args:
            doc_id: Document ID

        Returns:
            bool: True if deleted, False if not found
        """
        doc = self.get_document(doc_id)
        if not doc:
            return False

        self.db.delete(PromptDocument.TABLE_NAME, 'id = ?', (doc_id,))
        logger.info("Deleted prompt document: %s", doc_id)
        return True

    def search_documents(self, query, category=None, limit=20):
        """
        Search prompt documents by title, content, or keywords.

        Args:
            query: Search query string
            category: Optional category filter
            limit: Maximum results

        Returns:
            list: List of matching PromptDocument objects
        """
        search_pattern = '%{0}%'.format(query)
        conditions = ['(title LIKE ? OR content LIKE ? OR keywords LIKE ?)']
        params = [search_pattern, search_pattern, search_pattern]

        if category:
            conditions.append('category = ?')
            params.append(category)

        where_clause = ' AND '.join(conditions)
        sql = 'SELECT * FROM prompt_documents WHERE {0} ORDER BY created_at DESC LIMIT ?'.format(where_clause)
        params.append(limit)

        rows = self.db.fetch_all(sql, tuple(params))
        return [PromptDocument.from_row(row) for row in rows]

    def count_documents(self, category=None):
        """
        Count prompt documents with optional filtering.

        Args:
            category: Filter by category

        Returns:
            int: Number of documents
        """
        if category:
            return self.db.count(PromptDocument.TABLE_NAME, 'category = ?', (category,))
        return self.db.count(PromptDocument.TABLE_NAME)

    def get_categories(self):
        """
        Get list of all categories with document counts.

        Returns:
            list: List of dicts with category and count
        """
        query = '''
            SELECT category, COUNT(*) as cnt
            FROM prompt_documents
            GROUP BY category
            ORDER BY cnt DESC
        '''
        return self.db.fetch_all(query)

    def import_from_knowledge_base(self, catalog_path):
        """
        Import prompt documents from knowledge_base.json.

        Args:
            catalog_path: Path to knowledge_base.json

        Returns:
            int: Number of documents imported
        """
        if not os.path.exists(catalog_path):
            raise PromptDocServiceError('Catalog file not found: {0}'.format(catalog_path))

        with open(catalog_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        count = 0

        # Import venue prompts
        venues = data.get('venue_catalog') or []
        for venue in venues:
            venue_id = venue.get('id')
            name = venue.get('name', venue_id)

            # Create document for each venue with full prompt info
            content_parts = []
            if venue.get('default_subject'):
                content_parts.append('Subject: ' + venue.get('default_subject'))
            if venue.get('default_dynamics'):
                content_parts.append('Dynamics: ' + venue.get('default_dynamics'))
            if venue.get('default_environment'):
                content_parts.append('Environment: ' + venue.get('default_environment'))
            if venue.get('default_lighting'):
                content_parts.append('Lighting: ' + venue.get('default_lighting'))
            if venue.get('default_style'):
                content_parts.append('Style: ' + venue.get('default_style'))

            if content_parts:
                self.create_document(
                    title='{0} - Venue Prompt'.format(name),
                    category=PromptDocument.CATEGORY_VENUE,
                    content='\n'.join(content_parts),
                    keywords=venue_id,
                    source_file='knowledge_base.json'
                )
                count += 1

        # Import shot prompts
        shots = data.get('shot_catalog') or []
        for shot in shots:
            shot_id = shot.get('id')
            label = shot.get('label', shot_id)
            prompt = shot.get('prompt', '')

            if prompt:
                self.create_document(
                    title='{0} - Shot Prompt'.format(label),
                    category=PromptDocument.CATEGORY_SHOT,
                    content=prompt,
                    keywords=shot_id,
                    source_file='knowledge_base.json'
                )
                count += 1

        # Import lexicon as style/technique documents
        lexicons = data.get('lexicon_catalog') or []
        for lex in lexicons:
            term = lex.get('term', '')
            goal = lex.get('goal', '')
            usage = lex.get('usage', '')

            if term:
                content = 'Goal: {0}\n\nUsage: {1}'.format(goal, usage)
                self.create_document(
                    title=term,
                    category=PromptDocument.CATEGORY_STYLE,
                    content=content,
                    keywords=goal,
                    source_file='knowledge_base.json'
                )
                count += 1

        logger.info("Imported %d prompt documents from knowledge base", count)
        return count


# Global service instance
_prompt_doc_service = None


def get_prompt_doc_service(data_dir=None):
    """
    Get or create the global prompt document service instance.

    Args:
        data_dir: Base data directory

    Returns:
        PromptDocService: Global service instance
    """
    global _prompt_doc_service
    if _prompt_doc_service is None:
        _prompt_doc_service = PromptDocService(data_dir)
    return _prompt_doc_service