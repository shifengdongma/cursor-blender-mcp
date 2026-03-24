#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data migration script for AIGV Studio.
Migrates data from knowledge_base.json to SQLite database.
Python 3.6 compatible.
"""
from __future__ import absolute_import

import argparse
import json
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database, get_database
from backend.models import VenuePreset, ModelConfig, Asset
from backend.prompt_doc_service import PromptDocService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_venues(db, venues):
    """
    Migrate venue catalog to database.

    Args:
        db: Database instance
        venues: List of venue dicts from knowledge base

    Returns:
        int: Number of venues migrated
    """
    count = 0
    for venue in venues:
        venue_id = venue.get('id')
        if not venue_id:
            continue

        # Check if already exists
        existing = db.fetch_one(
            'SELECT id FROM venue_presets WHERE id = ?',
            (venue_id,)
        )
        if existing:
            logger.info("Venue already exists: %s, skipping", venue_id)
            continue

        preset = VenuePreset(
            id=venue_id,
            name=venue.get('name', venue_id),
            description=venue.get('description'),
            default_environment=venue.get('default_environment'),
            default_lighting=venue.get('default_lighting'),
            default_style=venue.get('default_style'),
            camera_defaults=venue.get('camera_defaults'),
            negative_prompt_parts=','.join(venue.get('negative_prompt_parts') or [])
        )

        db.insert(VenuePreset.TABLE_NAME, preset.to_insert_params())
        count += 1
        logger.info("Migrated venue: %s", venue_id)

    return count


def migrate_models(db, models):
    """
    Migrate model catalog to database.

    Args:
        db: Database instance
        models: List of model dicts from knowledge base

    Returns:
        int: Number of models migrated
    """
    count = 0
    for model in models:
        model_id = model.get('id')
        if not model_id:
            continue

        # Check if already exists
        existing = db.fetch_one(
            'SELECT id FROM model_configs WHERE id = ?',
            (model_id,)
        )
        if existing:
            logger.info("Model already exists: %s, skipping", model_id)
            continue

        config = ModelConfig(
            id=model_id,
            display_model=model.get('display_model', model_id),
            execution_provider=model.get('execution_provider'),
            route_mode=model.get('route_mode'),
            status=model.get('status'),
            description=model.get('description'),
            style_hint=model.get('style_hint'),
            recommended=1 if model.get('recommended') else 0
        )

        db.insert(ModelConfig.TABLE_NAME, config.to_insert_params())
        count += 1
        logger.info("Migrated model: %s", model_id)

    return count


def migrate_assets(db, assets, data_dir):
    """
    Migrate asset catalog to database.

    Args:
        db: Database instance
        assets: List of asset dicts from knowledge base
        data_dir: Data directory path

    Returns:
        int: Number of assets migrated
    """
    count = 0
    for asset in assets:
        asset_id = asset.get('id')
        if not asset_id:
            continue

        # Check if already exists
        existing = db.fetch_one(
            'SELECT id FROM assets WHERE id = ?',
            (asset_id,)
        )
        if existing:
            logger.info("Asset already exists: %s, skipping", asset_id)
            continue

        # Determine asset type
        asset_kind = asset.get('asset_kind', 'prompt_only')
        if asset_kind == 'spatial_anchor':
            asset_type = Asset.TYPE_SPATIAL_ANCHOR if hasattr(Asset, 'TYPE_SPATIAL_ANCHOR') else 'spatial_anchor'
        elif asset_kind == 'prompt_only':
            asset_type = 'prompt_only'
        else:
            asset_type = 'glb'

        new_asset = Asset(
            id=asset_id,
            name=asset.get('name', asset_id),
            asset_type=asset_type,
            venue_type=asset.get('venue_type'),
            description=asset.get('description'),
            metadata={
                'workflow_mode': asset.get('workflow_mode'),
                'source_type': asset.get('source_type'),
                'file_format': asset.get('file_format'),
                'recommended': asset.get('recommended', False),
                'showcase': asset.get('showcase', False),
                'placeholder_geometry': asset.get('placeholder_geometry', []),
                'negative_prompt_parts': asset.get('negative_prompt_parts', [])
            }
        )

        db.insert(Asset.TABLE_NAME, new_asset.to_insert_params())
        count += 1
        logger.info("Migrated asset: %s", asset_id)

    return count


def migrate_prompt_documents(catalog_path, data_dir):
    """
    Migrate prompt documents from knowledge base.

    Args:
        catalog_path: Path to knowledge_base.json
        data_dir: Data directory path

    Returns:
        int: Number of documents migrated
    """
    service = PromptDocService(data_dir)
    return service.import_from_knowledge_base(catalog_path)


def main():
    parser = argparse.ArgumentParser(
        description='Migrate data from knowledge_base.json to SQLite database'
    )
    parser.add_argument(
        '--catalog-path',
        default=None,
        help='Path to knowledge_base.json (default: ./data/catalog/knowledge_base.json)'
    )
    parser.add_argument(
        '--data-dir',
        default=None,
        help='Base data directory (default: ./data)'
    )
    parser.add_argument(
        '--skip-venues',
        action='store_true',
        help='Skip venue migration'
    )
    parser.add_argument(
        '--skip-models',
        action='store_true',
        help='Skip model migration'
    )
    parser.add_argument(
        '--skip-assets',
        action='store_true',
        help='Skip asset migration'
    )
    parser.add_argument(
        '--skip-prompts',
        action='store_true',
        help='Skip prompt document migration'
    )

    args = parser.parse_args()

    # Determine paths
    data_dir = args.data_dir or os.environ.get('DATA_DIR', './data')
    catalog_path = args.catalog_path or os.path.join(data_dir, 'catalog', 'knowledge_base.json')
    db_path = os.path.join(data_dir, 'aigv.db')

    # Check if catalog exists
    if not os.path.exists(catalog_path):
        logger.error("Catalog file not found: %s", catalog_path)
        sys.exit(1)

    # Load catalog
    logger.info("Loading catalog from: %s", catalog_path)
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Initialize database
    db = Database(db_path)

    total_migrated = 0

    # Migrate venues
    if not args.skip_venues:
        venues = catalog.get('venue_catalog') or []
        logger.info("Migrating %d venues...", len(venues))
        count = migrate_venues(db, venues)
        total_migrated += count
        logger.info("Migrated %d venues", count)

    # Migrate models
    if not args.skip_models:
        models = catalog.get('model_catalog') or []
        logger.info("Migrating %d models...", len(models))
        count = migrate_models(db, models)
        total_migrated += count
        logger.info("Migrated %d models", count)

    # Migrate assets
    if not args.skip_assets:
        assets = catalog.get('asset_catalog') or []
        logger.info("Migrating %d assets...", len(assets))
        count = migrate_assets(db, assets, data_dir)
        total_migrated += count
        logger.info("Migrated %d assets", count)

    # Migrate prompt documents
    if not args.skip_prompts:
        logger.info("Migrating prompt documents...")
        count = migrate_prompt_documents(catalog_path, data_dir)
        total_migrated += count
        logger.info("Migrated %d prompt documents", count)

    logger.info("Migration complete. Total items migrated: %d", total_migrated)


if __name__ == '__main__':
    main()