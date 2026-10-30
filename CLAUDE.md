# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIGV Studio is an AI-powered video generation platform for cultural venues (theaters, galleries, museums, concert halls). It combines:
- **Knowledge-enhanced prompt orchestration** with a "Golden Six-Module" formula
- **Blender spatial anchors** for 3D scene constraints and camera trajectories
- **Multi-model routing** to video generation providers (Seedance, Luma, etc.)
- **SAAS multi-tenant architecture** with enterprise services (scheduling, billing, rights, streaming, monitoring)

Tech stack: **Python 3.10 + Flask 2.0.3 + Vanilla JS SPA + SQLite + JSON dual storage + Blender (optional)**

## Git Workflow

- Commit and push directly to `master` (the default branch). Do not create feature branches for this project.
- After completing changes, push to `origin/master` unless the user explicitly says otherwise.
- Do not commit runtime data, model weights, databases, uploaded assets, or secrets; `.gitignore` covers these.

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

### Database & Data Migration
```bash
python3 scripts/init_db.py          # Initialize SQLite schema + asset directories
python3 scripts/migrate_data.py     # Import knowledge_base.json into SQLite tables
```

### Environment Configuration
Copy `.env.example` to `.env` and configure:
- `SEEDANCE_API_KEY` - Primary video generation provider (Atlas Cloud API)
- `SEEDANCE_BASE_URL` - Seedance API endpoint (default: `https://api.atlascloud.ai/api/v1`)
- `SEEDANCE_MODEL_NAME` - Seedance model identifier (default: `bytedance/seedance-v1.5-pro/text-to-video`)
- `LUMA_API_KEY` - Optional alternative provider
- `LUMA_BASE_URL` - Luma API endpoint (default: `https://api.lumalabs.ai/dream-machine/v1`)
- `BLENDER_BIN` - Path to Blender executable (default: `blender`)
- `ENABLE_BLENDER_EXPORT` - Set to `true` to enable Blender integration (default: `true`)
- `BLENDER_EXECUTION_MODE` - `local_batch` or `mcp_remote` (default: `local_batch`)
- `DATA_DIR` - Data storage root (default: `./data`)
- `SECRET_KEY` - Flask session secret key
- `PORT` / `HOST` - Server listen address (default: `8000` / `0.0.0.0`)

## Architecture

### Five-Layer Architecture

```
┌──────────────────────────────────────────────────────┐
│  Frontend Layer (SPA, Vanilla JS, zero-framework)     │
│  index.html + creative-studio + compute-platform      │
│  assets.html + login/register + styles.css (5.2k)     │
├──────────────────────────────────────────────────────┤
│  Flask Route & Control Layer (app.py)                 │
│  _register_main_routes     _register_auth_routes      │
│  _register_asset_routes    _register_prompt_doc_routes│
│  register_control_plane_routes  _register_error_handlers
├──────────────────────────────────────────────────────┤
│  Core Business Services (backend/)                    │
│  3 core: PromptOrchestrator, JobStore+Worker,         │
│          ProviderRouter                               │
│  6 enterprise: SchedulerService, BillingService,      │
│          RightsService, StreamService, EngineService, │
│          OpsService                                   │
│  2 data: CatalogService, Database ORM                 │
│  5 management: AssetService, PromptDocService,        │
│          AuthService, TenantService, DemoSeedService  │
│  utilities: http_utils (ApiError, pagination, JSON)   │
│  models: 18 data model classes                        │
├──────────────────────────────────────────────────────┤
│  Data Persistence (dual-storage)                      │
│  SQLite (14 tables + 16 indexes) for business data    │
│  JSON files (data/jobs/<uuid>/) for task snapshots    │
│  File system: data/assets/, data/users.json           │
├──────────────────────────────────────────────────────┤
│  External Services                                    │
│  Seedance Atlas Cloud API, Luma Dream Machine API     │
│  Blender headless subprocess, Blender MCP Server      │
└──────────────────────────────────────────────────────┘
```

### Backend Module Map (`backend/`)

```
backend/
├── __init__.py
│
│   # ── Core Pipeline ──
├── config.py              # Env config reading + startup validation
├── jobs.py                # JobStore (thread-safe JSON persistence) + async Worker (10-stage pipeline)
├── prompt_engine.py       # PromptOrchestrator: Golden Six-Module prompt assembly
├── prompt_builder.py      # Legacy prompt builder (based on scene_spec)
├── catalog_service.py     # JSON knowledge base loader with lazy caching
├── provider_router.py     # Multi-provider routing factory (Seedance/Luma)
│
│   # ── Data Layer ──
├── database.py            # SQLite ORM: 14 tables, threading.local(), CRUD methods
├── models.py              # 18 model classes (Asset, PromptDocument, Tenant, User, Project,
│                          #   Resource, ResourceAllocation, EngineProfile, StreamSession,
│                          #   AssetRights, AssetProvenanceEvent, BillingAccount,
│                          #   BillingUsageRecord, OpsEvent, VenuePreset, ModelConfig, JobHistory,
│                          #   ProjectMembership)
│                          #   Each with from_row/to_dict/to_insert_params
│
│   # ── Enterprise Services ──
├── scheduler_service.py   # GPU resource pool matching + scheduling decision + monitor ticks
├── billing_service.py     # 3-part billing: GPU hours + engine hours + stream hours
├── rights_service.py      # Asset rights validation + provenance chain + immutable snapshot
├── stream_service.py      # WebRTC/HLS stream session config (3 profiles: low_latency/balanced/showcase)
├── engine_service.py      # 4 engine types: blender_anchor/ue5_cloud/unity_cloud/steamvr_stream
├── ops_service.py         # Operations event logging and querying
│
│   # ── Business Services ──
├── asset_service.py       # Asset CRUD + file upload/storage (by venue type)
├── prompt_doc_service.py  # Prompt document CRUD + knowledge_base.json bulk import
├── auth_service.py        # User auth: JSON file storage, werkzeug pbkdf2:sha256 hashing
├── tenant_service.py      # Multi-tenant management: Tenant→User→Project→Membership + permission check
├── demo_seed_service.py   # Demo data auto-injection on startup (idempotent via _insert_if_missing)
├── control_plane_routes.py# All enterprise API routes (tenants, users, projects, resources, engines,
│                          #   scheduler, rights, billing, ops, monitoring)
│
│   # ── Utilities ──
├── http_utils.py          # ApiError exception, PaginationParams, parse_json_body/parse_pagination,
│                          #   require_fields, api_success/api_error unified response format
│
│   # ── Blender Integration ──
├── blender_adapter.py     # BlenderExecutionAdapter: local_batch/mcp_remote mode switch
├── blender_runner.py      # Subprocess wrapper: Popen headless Blender, 300s timeout, artifacts parsing
│
│   # ── Providers ──
└── providers/
    ├── __init__.py
    ├── seedance.py        # Atlas Cloud API: POST /model/generateVideo, GET /model/prediction/{id}
    │                      #   wait_until_done (900s timeout, 5s interval), extract_video_url from data.outputs[0]
    └── luma.py            # Luma API: POST /generations, GET /generations/{id}
                           #   wait_until_done, extract_video_url from assets.video
```

### Job Pipeline Stages (10 stages)

```
queued → knowledge_ready → rights_validated → resource_scheduling
  → blender_exporting (conditional) → provider_submitted → provider_running
  → streaming → billing_recorded → succeeded/error
```

**Stage details:**

| Stage | Service | Actions | Output Files |
|-------|---------|---------|--------------|
| `queued` | JobStore | Generate UUID, create job.json | job.json |
| `knowledge_ready` | PromptOrchestrator | Resolve venue/model/asset/shot → 6-module prompt → negative prompt → execution plan | prompt_bundle.json, knowledge_hits.json, asset_bundle.json |
| `rights_validated` | RightsService | Validate license type, approval status, expiry, usage scope | rights_snapshot.json |
| `resource_scheduling` | SchedulerService | Match GPU node by engine_target → allocate → create engine session | scheduler_decision.json, render_session.json, scene_spec.json |
| `blender_exporting` | BlenderAdapter+Runner | Conditional: ENABLE_BLENDER_EXPORT=true AND hybrid workflow AND asset not text_only. Subprocess Blender, 300s timeout | artifacts.json, scene.glb, camera_path.json |
| `provider_submitted` | ProviderRouter | Create Seedance/Luma client, build request, submit generation | provider_result.json |
| `provider_running` | ProviderRouter | Poll every 5s, 900s timeout, extract video_url | provider_result.json (updated) |
| `streaming` | StreamService | Configure WebRTC/HLS session, build 3 monitor ticks | stream_session.json, monitor_ticks.json |
| `billing_recorded` | BillingService | Calculate GPU/engine/stream costs, insert record | billing_snapshot.json |
| `succeeded`/`error` | - | Final state: return video URL or error message | - |

**preview-only mode:** When route_mode is "preview-only" or execution_provider is empty/placeholder, stages ⑥-⑧ are skipped. The job completes at billing_recorded with status "preview_only".

### Prompt Six-Module Formula

The `PromptOrchestrator` (backend/prompt_engine.py:253 lines) assembles prompts from:

| # | Module | Source (priority order) | Typical Content |
|---|--------|------------------------|-----------------|
| 1 | **camera** | shot.prompt → venue.default_camera_prompt | "Cinematic orbit shot, 360-degree rotation" |
| 2 | **subject** | user.subject_hint → venue.default_subject | "Grand theater stage with velvet curtains" |
| 3 | **dynamics** | user.dynamics_hint → venue.default_dynamics | "Curtains subtly swaying, dust motes in light" |
| 4 | **environment** | user.environment_hint → venue.default_environment | "Baroque opera house interior" |
| 5 | **lighting** | user.lighting_hint → venue.default_lighting | "Warm chandelier glow, volumetric rays" |
| 6 | **style** | user.style_anchor → venue.default_style + model.style_hint + engine_target + render_mode | "Cinematic realism, architectural visualization, engine blender_anchor, render cinematic" |

**Fallback chain:** user input → venue default → model default → system empty string. Never breaks.

**Final prompt assembly:** `"camera, subject, dynamics, environment, lighting, style."` (comma-separated, period-terminated)

**Negative prompt assembly (deduplicated):** knowledge_rules.default_negative_prompt_parts → venue.negative_prompt_parts → asset.negative_prompt_parts → user.negative_prompt

### Knowledge Base (`data/catalog/knowledge_base.json`)

13 catalogs:
- `project_metrics` (4 items) — Display metrics
- `model_catalog` (6 models) — Seedance Pro (native), Sora 2/Veo 3/Runway Gen-3/Kling 3.0 (demo-route), Luma (optional)
- `venue_catalog` (4 venues) — Grand Theater, Modern Gallery, Ancient Museum, Concert Hall. Each has: hero_title, default_subject/dynamics/environment/lighting/style, negative_prompt_parts, camera_defaults
- `asset_catalog` — Spatial anchor assets with placeholder_geometry definitions, plus `text_only` mode
- `shot_catalog` (7 types) — orbit/dolly_in/crane_up/tracking/fpv/macro_pan/low_angle_glide, each with Chinese/English prompt templates
- `knowledge_rules` — Global default_negative_prompt_parts
- `workflow_tips` — UI operation hints
- `lexicon_catalog` — Term glossary (term/goal/usage)
- `engine_catalog` (4 engines) — Blender Anchor/UE5 Cloud/Unity Cloud/SteamVR Stream
- `resource_pool_catalog` — GPU pool type configs
- `stream_profile_catalog` (3 profiles) — low_latency/balanced/showcase
- `rights_template_catalog` — License templates
- `demo_tenant_catalog` — Demo tenant data

### Provider Routing Modes

| Mode | display_model | execution_provider | Behavior |
|------|---------------|-------------------|----------|
| `native` | Model A | Model A | Direct execution |
| `demo-route` | Model A (e.g., Sora 2) | Provider B (e.g., seedance) | Display A, execute via B (for demos) |
| `preview-only` | Display only | preview_only | No execution, showcase only |
| `optional` | Optional model | (varies) | Optional execution channel |

API Key validation: each provider checks its API key before creation. Missing keys throw `ProviderRoutingError("missing_api_key")`.

### SQLite Database (14 tables + 16 indexes)

Database file: `data/aigv.db`. Managed by `Database` class (backend/database.py:566 lines). Uses `threading.local()` for thread-local connections.

**Table groups:**
- **Core business**: assets, prompt_documents, venue_presets, model_configs, job_history
- **Multi-tenant**: tenants, users, projects, project_memberships
- **Resource**: resources, resource_allocations
- **Engine & Stream**: engine_profiles, stream_sessions
- **Rights & Billing**: asset_rights, asset_provenance_events, billing_accounts, billing_usage_records
- **Ops**: ops_events

**Key indexes:** `idx_assets_type`, `idx_assets_venue`, `idx_prompts_category`, `idx_jobs_status`, `idx_users_tenant`, `idx_projects_tenant`, `idx_resources_status`, `idx_allocations_job`, `idx_stream_job`, `idx_rights_asset`, `idx_provenance_asset`, `idx_billing_project`, `idx_ops_project`

### Job Persistence (JSON)

Each job stored as a directory: `data/jobs/<uuid>/`. `JobStore` (in jobs.py) provides thread-safe operations with `threading.Lock()` and atomic writes (tmp → rename).

12 JSON files per job: job.json, prompt_bundle.json, knowledge_hits.json, asset_bundle.json, scene_spec.json, artifacts.json, render_session.json, stream_session.json, rights_snapshot.json, scheduler_decision.json, monitor_ticks.json, billing_snapshot.json

### Blender Integration (`blender/`)

- `blender_batch.py` — Headless script: parse scene_spec.json → create placeholder geometry (Cube/Cylinder/Plane) → 7 camera animations → export scene.glb + camera_path.json + artifacts.json
- `blender_agent.py` — MCP server inside Blender: JSON-RPC over stdio, tools: list_scene_objects, run_python_script, robust_operator_execution, capture_viewport
- `server_transport.py` — stdout hijacking via `os.dup2()` to redirect Blender logs to stderr
- `start_blender_mcp.sh` — One-click start script

**Execution modes:**
- `local_batch` — subprocess.Popen headless Blender, 300s timeout (current)
- `mcp_remote` — JSON-RPC real-time interaction (placeholder, returns error)

### Frontend (`web/`)

Vanilla JS single-page application, zero framework dependencies, dark-gold luxury theme.

| File | Lines | Purpose |
|------|-------|---------|
| `index.html` | 605 | Main SPA: dual-pane workspace (config panel + status/preview/result/monitoring) |
| `app.js` | 585 | Core logic: bootstrap → select init → venue link → silent preview → submit → 5s polling → race protection |
| `assets.html` | 199 | Asset library: tabbed (3D models/images/prompts), search, upload |
| `assets.js` | 733 | Asset CRUD, pagination, drag-drop upload |
| `creative-studio.html` | 123 | Creative production: 6-step workflow navigation |
| `creative-studio.js` | ~2,900 | 6-step workflow: requirements → concept → video → multimodal → refine → export |
| `compute-platform.html` | ~270 | Compute platform: 7 Tab navigation |
| `compute-platform.js` | ~1,320 | 7 Tabs: overview, cloud render, GPU scheduling, task orchestration, network monitor, permissions, billing alerts |
| `aigv-demo-data.js` | ~1,100 | Demo datasets: projects, storyboards, GPU pools, render sessions, network links |
| `login.html` / `register.html` | ~112 | Auth pages |
| `auth.js` | 134 | Auth logic: form validation, login/register API, status persistence |
| `styles.css` | ~5,200 | Dark-gold theme, CSS variables, grid layouts, responsive |

**Key JS functions:** `bootstrap()` (initialization), `previewPrompt({silent})` (prompt preview), `handleSubmit()` (job creation), `startPolling(jobId)` (5s status polling), `collectPayload()` (form data), `applyVenueDefaults()` (venue linkage)

**Race protection:** `previewRequestId`, `submitRequestId`, `pollRequestId` — increment IDs, closure capture, discard stale callbacks.

### Multi-Tenant Architecture (SAAS Demo)

Four-level model: `Tenant → User → Project → ProjectMembership`

- Permission check: `project_memberships.role` (owner/admin → all) OR permission in `permissions` JSON list
- Permissions: submit_job, approve_rights, view_billing, view_monitor
- Resource pools, billing, rights all isolated at tenant/project level
- Demo tenant injected on startup: `华中文博演示集团` with 2 users, 1 project, 3 GPU nodes, 4 engine profiles

## Key API Endpoints

### Page Routes
- `GET /` — Main workspace (index.html)
- `GET /creative-studio` — Creative production workbench
- `GET /compute-platform` — Compute scheduling center
- `GET /assets` — Asset library
- `GET /login` / `GET /register` — Auth pages
- `GET /web/<filename>` — Static resources (JS/CSS)

### Core Business API
- `GET /api/bootstrap` — Load full knowledge base
- `GET /api/health` — Health check (API key status, Blender status, persistence mode)
- `POST /api/prompt/preview` — Generate prompt preview (no job creation)
- `POST /api/jobs` — Create and start video generation job
- `GET /api/jobs/<id>` — Poll job status

### Auth API
- `POST /api/auth/login` — Login (Session-based)
- `POST /api/auth/register` — Register (password >= 6 chars, username >= 2 chars)
- `POST /api/auth/logout` — Logout
- `GET /api/auth/status` — Check login status

### Asset API (full CRUD)
- `GET /api/assets` — List (supports asset_type/venue_type filters + pagination)
- `POST /api/assets` — Create (requires name field)
- `GET /api/assets/<id>` — Detail
- `PUT /api/assets/<id>` — Update
- `DELETE /api/assets/<id>` — Delete (+ associated file)
- `POST /api/assets/upload` — Upload file (multipart)
- `GET /api/assets/<id>/download` — Download file
- `GET /data/assets/<path>` — Direct file access

### Prompt Document API (full CRUD)
- `GET /api/prompts/documents` — List (category filter + pagination)
- `POST /api/prompts/documents` — Create (requires title)
- `GET /api/prompts/documents/<id>` — Detail
- `PUT /api/prompts/documents/<id>` — Update
- `DELETE /api/prompts/documents/<id>` — Delete
- `GET /api/prompts/categories` — Category statistics

### Enterprise Control Plane API
- `GET /api/tenants` — Tenant list
- `GET /api/users` — User list (filter by tenant_id)
- `GET /api/projects` — Project list (filter by tenant_id)
- `GET /api/projects/<id>/members` — Project members with user details
- `GET /api/permissions/check` — Permission check
- `GET /api/demo/context` — Demo context (tenant/user/project)
- `GET /api/resources` / `GET /api/resources/summary` — GPU resources
- `POST /api/scheduler/preview` — Schedule preview
- `GET /api/jobs/<id>/schedule` / `GET /api/jobs/<id>/monitor` — Job schedule/monitor
- `GET /api/engines` / `POST /api/engines/session/preview` — Engine profiles
- `GET /api/jobs/<id>/engine-session` / `GET /api/jobs/<id>/stream-session` — Sessions
- `GET /api/assets/<id>/rights` / `POST /api/assets/<id>/rights/validate` — Rights
- `GET /api/assets/<id>/provenance` — Provenance chain
- `GET /api/jobs/<id>/rights-snapshot` — Rights snapshot
- `GET /api/billing/summary` / `GET /api/projects/<id>/usage` / `GET /api/jobs/<id>/billing` — Billing
- `GET /api/ops/events` — Ops events (filter by project_id)

## Configuration Parameters

| Env Variable | Default | Type | Description |
|-------------|---------|------|-------------|
| `SEEDANCE_API_KEY` | (empty) | String | Seedance Atlas Cloud API key |
| `SEEDANCE_BASE_URL` | `https://api.atlascloud.ai/api/v1` | String | Seedance API base URL |
| `SEEDANCE_MODEL_NAME` | `bytedance/seedance-v1.5-pro/text-to-video` | String | Seedance model identifier |
| `LUMA_API_KEY` | (empty) | String | Luma Dream Machine API key |
| `LUMA_BASE_URL` | `https://api.lumalabs.ai/dream-machine/v1` | String | Luma API base URL |
| `BLENDER_BIN` | `blender` | String | Blender executable path |
| `ENABLE_BLENDER_EXPORT` | `true` | Boolean | Enable Blender spatial export |
| `BLENDER_EXECUTION_MODE` | `local_batch` | String | `local_batch` or `mcp_remote` |
| `DATA_DIR` | `./data` | String | Data storage root directory |
| `SECRET_KEY` | (random 24-byte hex) | String | Flask session secret key |
| `HOST` | `0.0.0.0` | String | Server listen address |
| `PORT` | `8000` | Integer | Server listen port |

## Important Notes

### API Response Format
All endpoints return unified JSON format:
```json
{
  "success": true/false,
  "data": { ... },
  "error": null / "error_code",
  "message": "Human-readable message",
  "details": null / { ... }
}
```
Frontend `api()` function checks `success` field and throws on `false`.

### Thread Safety
- **Database**: `threading.local()` for thread-local SQLite connections, `threading.Lock()` for writes
- **JobStore**: `threading.Lock()` for memory cache, atomic file writes (tmp → rename)
- **Job Worker**: Background `daemon=True` threads, non-blocking

### Dual Storage Strategy
- **SQLite** (14 tables): Structured business data with relationships and indexes
- **JSON files** (`data/jobs/<uuid>/`): Per-task snapshot files for debugging and audit trails
- **File system**: `data/assets/`, `data/users.json`, `data/catalog/`

### Python Compatibility
- Runtime: Python 3.10 (`.venv/lib/python3.10/`)
- Uses `.format()` for string formatting
- All modules have `from __future__ import absolute_import` (reserved for potential 3.6 backward compat)
- `os.makedirs(exist_ok=True)` for directory creation

### Demo Data Auto-Injection
- `seed_demo_data(cfg.DATA_DIR)` called on every `create_app()`
- Uses `_insert_if_missing()` — idempotent, won't duplicate on restart
- Injects: 1 tenant + 2 users + 1 project + 2 memberships + 3 GPU nodes + 4 engine profiles + 3 rights records + 3 provenance events + 1 billing account

### Blender stdout Hijacking
- MCP uses JSON-RPC over stdio, but Blender outputs verbose logs to stdout
- `server_transport.py` uses `os.dup2()` to redirect original stdout to stderr
- MCP messages sent through preserved original fd, keeping JSON-RPC pipe clean
- Headless context: `bpy.ops` operators fail without GUI; use `bpy.data` direct manipulation

### Frontend Race Protection
- 3 incrementing request IDs: preview/submit/poll
- Callbacks compare closure-captured ID against global ID
- Stale callbacks silently discarded when IDs don't match

### Blender MCP Setup (Optional)

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

### Data Files
- `data/catalog/knowledge_base.json` — Core knowledge base (13 catalogs, ~3,000 lines)
- `data/aigv.db` — SQLite database (auto-created on first startup)
- `data/users.json` — Registered users with pbkdf2:sha256 hashed passwords
- `data/jobs/<uuid>/` — Per-job snapshot directories (12 JSON files each)
- `data/assets/` — Uploaded asset files organized by type and venue

### Documentation
- `AIGV_Studio_系统架构文档.md` — Full system architecture documentation
- `AIGV_Studio_功能介绍文档.md` — Complete feature documentation
- `AI视频生成技术路线部署指南.md` — Deployment guide
- `Blender_自动化建模视频生成技术路线.md` — Blender automation guide
- `AI视频生成艺术展厅Prompt手册.md` — Prompt manual
- `SKILL.md` — Claude Code skill definition ("cultural-aigv-director")
