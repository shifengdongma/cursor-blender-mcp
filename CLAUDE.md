# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIGV Studio is an AI-powered video generation platform for cultural venues (theaters, galleries, museums, concert halls). It combines:
- **Knowledge-enhanced prompt orchestration** with a "Golden Six-Module" formula
- **Blender spatial anchors** for 3D scene constraints and camera trajectories
- **Multi-model routing** to video generation providers (Seedance, Luma, etc.)

## Commands

### Start the Server
```bash
# Development mode
python3 app.py

# Production mode
gunicorn -b 0.0.0.0:8000 app:app
```

### Install Dependencies
```bash
pip3 install -r requirements.txt
```

### Environment Configuration
Copy `.env.example` to `.env` and configure:
- `SEEDANCE_API_KEY` - Primary video generation provider
- `LUMA_API_KEY` - Optional alternative provider
- `BLENDER_BIN` - Path to Blender executable (for spatial exports)
- `ENABLE_BLENDER_EXPORT` - Set to `true` to enable Blender integration

## Architecture

### Backend (Flask, Python 3.6 compatible)

```
app.py                    # Flask application factory, API routes
backend/
├── config.py             # Environment configuration with validation
├── jobs.py               # Job store + async worker pipeline
├── prompt_engine.py      # PromptOrchestrator: six-module prompt assembly
├── catalog_service.py    # Knowledge base loader (JSON)
├── provider_router.py    # Route to video generation providers
├── blender_adapter.py    # Adapter for Blender execution modes
├── blender_runner.py     # Subprocess wrapper for headless Blender
└── providers/
    ├── seedance.py       # Seedance/Atlas Cloud API client
    └── luma.py           # Luma Dream Machine API client
```

### Job Pipeline Stages
1. `queued` → `knowledge_ready` → `blender_exporting` → `provider_submitted` → `provider_running` → `succeeded`/`error`
2. Jobs run in background threads, state persisted to `data/jobs/<job_id>/`

### Prompt Six-Module Formula
The `PromptOrchestrator` assembles prompts from:
1. **camera** - Shot type / camera movement
2. **subject** - Main subject with materials
3. **dynamics** - Motion and behavior
4. **environment** - Spatial context
5. **lighting** - Light and atmosphere
6. **style** - Style anchors and aesthetic parameters

### Knowledge Base (`data/catalog/knowledge_base.json`)
Contains:
- `venue_catalog` - Venue presets (theater, gallery, museum, concert hall)
- `model_catalog` - AI model configurations with routing modes
- `asset_catalog` - Spatial anchor assets with placeholder geometry
- `shot_catalog` - Camera movement patterns
- `knowledge_rules` - Default negative prompts

### Blender Integration (`blender/`)
- `blender_batch.py` - Headless script for scene generation, camera animation, GLB export
- `blender_agent.py` - MCP server for real-time Blender control (requires Blender environment with mcp installed)

### Frontend (`web/`)
- Vanilla JS single-page app
- No framework dependencies
- Key functions: `bootstrap()`, `previewPrompt()`, `handleSubmit()`, `startPolling()`

## Provider Routing Modes

| Mode | Description |
|------|-------------|
| `native` | Direct execution with the specified provider |
| `demo-route` | Display model A, execute with provider B (for demos) |
| `preview-only` | No actual execution, for showcase only |

## Key API Endpoints

- `GET /api/bootstrap` - Load knowledge base
- `POST /api/prompt/preview` - Generate prompt preview
- `POST /api/jobs` - Create video generation job
- `GET /api/jobs/<id>` - Poll job status

## Blender MCP Setup (Optional)

For real-time Blender control via MCP:

1. Install dependencies in Blender's Python:
```bash
blender -b --python-expr "import sys; print(sys.executable)"
# Then use that Python path:
<blender_python> -m ensurepip
<blender_python> -m pip install mcp fastmcp numpy requests opencv-python pydantic
```

2. Start MCP server:
```bash
blender --background --python blender/blender_agent.py
```

## Important Notes

- **Python 3.6 compatibility**: Use `from __future__ import absolute_import` and avoid f-strings
- **Blender stdout hijacking**: MCP requires `os.dup2()` to redirect Blender's verbose output away from JSON-RPC stream
- **Headless context**: Blender operators (`bpy.ops`) fail without GUI; use `bpy.data` direct manipulation instead