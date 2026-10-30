# AIGV Studio 系统架构文档

## 一、项目概述

AIGV Studio（AI Generated Video Studio，AI 视频生成工坊）是一个面向文化场馆（剧场、美术馆、博物馆、音乐厅）的 **AI 智能视频生成平台**。平台整合了三个核心技术支柱：

1. **知识增强 Prompt 编排引擎** —— "黄金六模块"公式，从知识库自动填充场景参数，生成高质量视频 Prompt
2. **Blender 空间锚点系统** —— 基于 3D 场景约束的相机轨迹生成与 GLB 资产导出
3. **多模型路由机制** —— 支持 Seedance、Luma 等视频生成服务商的智能路由与透明切换

项目技术栈：**Python 3.10+ + Flask 3.x（后端） + 原生 JavaScript（前端） + SQLite（持久化） + Blender / ComfyUI（可选）**

---

## 二、系统总体架构（五层架构）

```
┌──────────────────────────────────────────────────────────────────┐
│                    前端展示层 (SPA)                                │
│                                                                   │
│  ┌──────────────┐ ┌────────────────┐ ┌───────────────────────┐   │
│  │ 工作台 (首页) │ │ 创意生产工作台   │ │ 算力调度中心             │   │
│  │ index.html   │ │ creative-studio │ │ compute-platform       │   │
│  │ app.js       │ │ creative-studio │ │ compute-platform.js    │   │
│  │              │ │ .js            │ │ aigv-demo-data.js      │   │
│  └──────────────┘ └────────────────┘ └───────────────────────┘   │
│                                                                   │
│  ┌──────────────┐ ┌────────────────┐ ┌───────────────────────┐   │
│  │ 资产库        │ │ 认证页面        │ │ 统一样式主题             │   │
│  │ assets.html  │ │ login/register │ │ styles.css (~5200行)   │   │
│  │ assets.js    │ │ auth.js        │ │ 暗金奢华UI              │   │
│  └──────────────┘ └────────────────┘ └───────────────────────┘   │
│                                                                   │
│  原生 JavaScript 实现，零框架依赖，纯 SPA 架构                      │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP/JSON REST API
┌───────────────────────────▼──────────────────────────────────────┐
│                  Flask 路由与控制层 (app.py)                        │
│                                                                   │
│  create_app() 工厂函数注册以下路由模块：                             │
│  ┌──────────────────┐ ┌─────────────────┐ ┌──────────────────┐   │
│  │ _register_main_   │ │ _register_auth_ │ │ _register_asset_ │   │
│  │ routes            │ │ routes          │ │ routes           │   │
│  │ POST /api/jobs    │ │ /api/auth/login │ │ /api/assets CRUD │   │
│  │ POST /api/prompt  │ │ /api/auth/      │ │ /api/assets/     │   │
│  │ /preview          │ │ register        │ │ upload           │   │
│  │ GET /api/jobs/<id>│ │ /api/auth/logout│ │ /api/assets/<id> │   │
│  │ GET /api/bootstrap│ │ /api/auth/status│ │ /download        │   │
│  │ GET /api/health   │ │                 │ │                  │   │
│  └──────────────────┘ └─────────────────┘ └──────────────────┘   │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────────────────────────┐   │
│  │ _register_prompt_ │ │ register_control_plane_routes         │   │
│  │ doc_routes        │ │ /api/tenants, /api/users, /api/      │   │
│  │ /api/prompts/     │ │ projects, /api/resources,            │   │
│  │ documents CRUD    │ │ /api/engines, /api/scheduler,        │   │
│  │ /api/prompts/     │ │ /api/rights, /api/billing,           │   │
│  │ categories        │ │ /api/ops, /api/demo/context          │   │
│  └──────────────────┘ └──────────────────────────────────────┘   │
│                                                                   │
│  _register_error_handlers: ApiError / 400 / 404 / 500 / Exception │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                   核心业务服务层 (backend/)                          │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐   │
│  │ PromptOrchestrator│ │ JobStore +       │ │ ProviderRouter  │   │
│  │ prompt_engine.py  │ │ Job Worker       │ │ provider_router  │   │
│  │ 253行              │ │ jobs.py (459行)  │ │ .py (137行)      │   │
│  │ 黄金六模块Prompt编 │ │ 11阶段异步流水线  │ │ 多厂商路由工厂    │   │
│  │ 排 + 知识库匹配    │ │ 线程Worker        │ │ + 轮询等待机制    │   │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘   │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐   │
│  │ CatalogService   │ │ BlenderAdapter + │ │ AuthService      │   │
│  │ catalog_service.py│ │ BlenderRunner    │ │ auth_service.py   │   │
│  │ 119行             │ │ blender_adapter   │ │ 76行             │   │
│  │ JSON知识库加载/   │ │ /blender_runner   │ │ werkzeug密码哈希  │   │
│  │ 缓存查询          │ │ 子进程无头Blender  │ │ users.json存储    │   │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘   │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐   │
│  │ AssetService     │ │ PromptDocService │ │ SchedulerService │   │
│  │ asset_service.py  │ │ prompt_doc_      │ │ scheduler_       │   │
│  │ 357行             │ │ service.py 327行 │ │ service.py 116行  │   │
│  │ 文件上传/存储/     │ │ Prompt文档CRUD   │ │ GPU资源池匹配     │   │
│  │ 数据库CRUD        │ │ +知识库导入       │ │ +调度决策分配     │   │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘   │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐   │
│  │ RightsService    │ │ BillingService   │ │ StreamService    │   │
│  │ rights_service.py │ │ billing_service  │ │ stream_service   │   │
│  │ 72行              │ │ .py 83行         │ │ .py 32行          │   │
│  │ 版权校验/快照/    │ │ GPU/引擎/推流     │ │ WebRTC/HLS推流    │   │
│  │ 来源追踪          │ │ 三部分计费        │ │ 会话参数配置       │   │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘   │
│                                                                   │
│  ┌──────────────────┐ ┌──────────────────┐ ┌─────────────────┐   │
│  │ EngineService    │ │ OpsService       │ │ TenantService    │   │
│  │ engine_service.py │ │ ops_service.py   │ │ tenant_service   │   │
│  │ 51行              │ │ 41行             │ │ .py 99行          │   │
│  │ 引擎配置/渲染会话 │ │ 运维事件记录/查询 │ │ 多租户/用户/项目  │   │
│  │                  │ │                  │ │ +权限检查         │   │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘   │
│                                                                   │
│  ┌──────────────────────┐ ┌──────────────────────────────────┐    │
│  │ DemoSeedService      │ │ http_utils (109行)                │    │
│  │ demo_seed_service.py │ │ ApiError异常 + 分页解析            │    │
│  │ 90行 自动注入演示数据 │ │ + JSON校验 + 统一响应格式          │    │
│  └──────────────────────┘ └──────────────────────────────────┘    │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    数据持久层 (双轨存储)                             │
│                                                                   │
│  ┌──────────────────────┐  ┌────────────────────────────────────┐ │
│  │ SQLite (data/aigv.db)│  │ JSON 文件存储 (data/jobs/<uuid>/)  │ │
│  ├──────────────────────┤  ├────────────────────────────────────┤ │
│  │ Database (566行)      │  │ JobStore (jobs.py)                 │ │
│  │ - 14 张业务表          │  │ - job.json (主状态)                │ │
│  │ - 16 个性能索引        │  │ - prompt_bundle.json               │ │
│  │ - 线程本地连接         │  │ - knowledge_hits.json              │ │
│  │ - threading.local()   │  │ - asset_bundle.json                │ │
│  │ - CRUD 封装           │  │ - scene_spec.json                  │ │
│  │                        │  │ - artifacts.json                   │ │
│  │ 14张表:                │  │ - render_session.json              │ │
│  │ assets                 │  │ - stream_session.json              │ │
│  │ prompt_documents       │  │ - rights_snapshot.json             │ │
│  │ venue_presets          │  │ - scheduler_decision.json          │ │
│  │ model_configs          │  │ - monitor_ticks.json               │ │
│  │ job_history            │  │ - billing_snapshot.json            │ │
│  │ tenants                │  │                                    │ │
│  │ users                  │  ├────────────────────────────────────┤ │
│  │ projects               │  │ 文件系统存储                        │ │
│  │ project_memberships    │  │ data/users.json (认证)             │ │
│  │ resources              │  │ data/assets/ (上传文件)            │ │
│  │ resource_allocations   │  │ data/catalog/ (知识库)             │ │
│  │ engine_profiles        │  │                                    │ │
│  │ stream_sessions        │  │                                    │ │
│  │ asset_rights           │  │                                    │ │
│  │ asset_provenance_events│  │                                    │ │
│  │ billing_accounts       │  │                                    │ │
│  │ billing_usage_records  │  │                                    │ │
│  │ ops_events             │  │                                    │ │
│  └──────────────────────┘  └────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                    外部服务集成层                                    │
│                                                                   │
│  ┌──────────────────┐ ┌───────────────┐ ┌────────────────────┐   │
│  │ Seedance / Atlas │ │ Luma Dream    │ │ Blender (headless) │   │
│  │ Cloud API        │ │ Machine API   │ │ blender_batch.py   │   │
│  │ POST /model/     │ │ POST /gener-  │ │ - subprocess.Popen │   │
│  │ generateVideo    │ │ ations        │ │ - 场景几何体创建     │   │
│  │ GET /model/      │ │ GET /gener-   │ │ - 7种相机动画       │   │
│  │ prediction/{id}  │ │ ations/{id}   │ │ - GLB + JSON 导出   │   │
│  │ 文生视频 + 轮询   │ │ 文生视频 + 轮询 │ │ - 超时300s          │   │
│  └──────────────────┘ └───────────────┘ └────────────────────┘   │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ Blender MCP Server (可选, blender_agent.py)                 │   │
│  │ - JSON-RPC over stdio 实时交互                              │   │
│  │ - MCP 工具: list_scene_objects, run_python_script,          │   │
│  │   capture_viewport                                           │   │
│  │ - stdout劫持机制 (os.dup2) 保持管道干净                       │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、目录结构与文件职责

### 3.1 根目录

| 文件 | 行数 | 职责 |
|------|------|------|
| `app.py` | 421 | Flask 应用工厂入口 `create_app()`，注册全部路由模块与错误处理 |
| `requirements.txt` | - | Python 依赖：Flask 3.x, Werkzeug 3.x, requests, python-dotenv, gunicorn, Pillow 等（以文件为准） |
| `.env.example` | - | 环境变量模板：API Keys、Blender 路径、功能开关 |
| `CLAUDE.md` | - | 项目开发指南（供 AI 辅助开发用） |
| `SKILL.md` | - | Claude Code 技能定义（"cultural-aigv-director"） |

### 3.2 后端核心模块 (`backend/`)

| 文件 | 行数 | 核心职责 |
|------|------|----------|
| `config.py` | 89 | 环境变量读取、布尔/整数转换、配置启动验证、数据目录自动创建 |
| `models.py` | 1196 | **18 个数据模型类**：Asset、PromptDocument、VenuePreset、ModelConfig、JobHistory、Tenant、User、Project、ProjectMembership、Resource、ResourceAllocation、EngineProfile、StreamSession、AssetRights、AssetProvenanceEvent、BillingAccount、BillingUsageRecord、OpsEvent。每个类支持 from_row/ to_dict/ to_insert_params |
| `database.py` | 566 | **SQLite ORM 封装**：14 张业务表建表、16 个性能索引、threading.local() 线程本地连接、CRUD 方法（insert/update/delete/fetch_one/fetch_all/count）、外键约束 |
| `jobs.py` | 459 | **任务流水线引擎**：10 阶段异步状态流转、JobStore 线程安全 JSON 文件存储、normalize_job_payload 参数规范化、start_job_worker 后台 Worker 线程 |
| `http_utils.py` | 109 | **API 基础设施**：ApiError 异常类、PaginationParams 分页对象、parse_json_body/parse_pagination 请求解析、require_fields 字段校验、api_success/api_error 统一响应格式 |
| `prompt_engine.py` | 253 | **PromptOrchestrator**：黄金六模块 Prompt 编排核心，实体解析 → 工作流判定 → 六模块组装 → 负向提示词构建 → 执行计划与知识命中记录 |
| `prompt_builder.py` | 37 | 简化版 Prompt 构建器（基于 scene_spec 的备选方案） |
| `catalog_service.py` | 119 | **CatalogService**：JSON 知识库惰性加载、内存缓存、实体 ID 精确查找、bootstrap_payload 全量数据接口 |
| `provider_router.py` | 137 | **ProviderRouter**：Seedance/Luma 厂商工厂、submit_generation 提交生成、wait_until_done 轮询等待（900s 超时、5s 间隔） |
| `blender_adapter.py` | 29 | **BlenderExecutionAdapter**：local_batch / mcp_remote 模式适配器，当前仅 local_batch 可用 |
| `blender_runner.py` | 94 | **BlenderRunner**：subprocess.Popen 启动无头 Blender，300s 超时、stdout/stderr 捕获、artifacts.json 结果读取 |
| `asset_service.py` | 357 | **AssetService**：资产 CRUD 完整服务、文件上传分区存储（models/images/prompts 按场馆目录）、全文搜索、分页查询 |
| `auth_service.py` | 76 | **AuthService**：JSON 文件用户存储、werkzeug pbkdf2:sha256 密码哈希、注册/认证/用户名查重 |
| `prompt_doc_service.py` | 327 | **PromptDocService**：Prompt 文档 CRUD、分类统计、全文搜索、knowledge_base.json 批量导入（场馆/镜头/词汇） |
| `tenant_service.py` | 99 | **TenantService**：多租户查询、用户/项目列表、项目成员、角色权限检查 |
| `scheduler_service.py` | 116 | **SchedulerService**：GPU 资源池匹配（local_gpu/public_cloud/edge_gpu 按引擎目标选择）、资源分配记录、监控采样点生成 |
| `engine_service.py` | 51 | **EngineService**：4 种渲染引擎配置查询（blender_anchor/ue5_cloud/unity_cloud/steamvr_stream）、渲染会话创建 |
| `stream_service.py` | 32 | **StreamService**：推流会话管理（WebRTC低延迟 / HLS标准 / 展示模式）、码率/延迟/FPS 按配置自适应 |
| `billing_service.py` | 83 | **BillingService**：GPU 小时 + 引擎小时 + 推流小时三部分计费核算、费用记录持久化、项目和租户维度汇总 |
| `rights_service.py` | 72 | **RightsService**：资产版权校验（许可类型/审批状态/用途范围/过期时间）、来源追踪链、不可变版权快照 |
| `ops_service.py` | 41 | **OpsService**：运维事件记录与查询，支持按项目维度筛选 |
| `control_plane_routes.py` | 150 | **控制平面路由注册**：租户/用户/项目/资源/调度/引擎/流/版权/计费/运维 API 端点注册 |
| `demo_seed_service.py` | 90 | **演示数据初始化**：自动注入租户、用户、项目、成员、GPU资源节点、引擎配置、版权记录、来源事件、计费账户 |

### 3.3 视频生成提供商 (`backend/providers/`)

| 文件 | 行数 | 职责 |
|------|------|------|
| `seedance.py` | 141 | **SeedanceProvider**：Atlas Cloud API 客户端。`create_generation()` → POST /model/generateVideo（含 prompt/duration/resolution/aspect_ratio/camera_fixed/seed）→ `get_generation()` → GET /model/prediction/{id} → `wait_until_done()` 轮询（900s超时/5s间隔）→ `extract_video_url()` 从 data.outputs[0] 提取视频 |
| `luma.py` | 105 | **LumaProvider**：Luma Dream Machine API 客户端。`create_generation()` → POST /generations（含 prompt/aspect_ratio/可选 keyframes）→ `get_generation()` → GET /generations/{id} → `wait_until_done()` 轮询 → `extract_video_url()` 从 assets.video 提取 |

### 3.4 Blender 集成 (`blender/`)

| 文件 | 职责 |
|------|------|
| `blender_batch.py` | 无头批处理脚本：解析 scene_spec.json → 创建场景几何体（Cube/Cylinder/Plane 按 assets 配置）→ 7 种相机动画（orbit/dolly_in/crane_up/tracking/fpv/macro_pan/low_angle_glide）→ GLB 导出 + camera_path.json + artifacts.json |
| `blender_agent.py` | MCP 服务器：在 Blender 内部运行，通过 JSON-RPC over stdio 暴露工具接口（list_scene_objects、run_python_script、robust_operator_execution、capture_viewport） |
| `server_transport.py` | stdout 劫持模块：使用 os.dup2() 重定向 Blender 日志到 stderr，保护 JSON-RPC 通信管道 |
| `start_blender_mcp.sh` | 一键启动 Blender MCP 服务器的 Shell 脚本 |

### 3.5 前端 (`web/`)

| 文件 | 行数 | 职责 |
|------|------|------|
| `index.html` | 605 | **主页 SPA**：5 区域双栏工作台（配置面板 + 状态/Prompt预览/结果/监控面板）、Hero 引导区、能力展示区、模型展示、六模块公式、空间资产库、项目指标 |
| `app.js` | 585 | **核心交互逻辑**：bootstrap 初始化 → 知识库加载 → 演示上下文加载 → 下拉框填充 → 场馆联动（applyVenueDefaults）→ 静默 Preview（queueSilentPreview）→ 表单提交（handleSubmit）→ 5秒轮询（startPolling）→ 竞态防护（previewRequestId/submitRequestId/pollRequestId） |
| `assets.html` | 199 | 资产库页面：Tab 切换（3D模型/图片/Prompt文档）、搜索、上传 |
| `assets.js` | 733 | 资产库逻辑：Tab 切换、搜索过滤、分页加载、文件拖拽上传、3D 模型预览 |
| `creative-studio.html` | 123 | 创意生产工作台：6 步流程导航（需求分析→概念图→视频生成→多模态增强→人机精调→输出适配） |
| `creative-studio.js` | ~2,900 | 创意生产逻辑：6 步完整工作流，每步含独立 UI、API 交互和本地方案回退 |
| `compute-platform.html` | ~320 | 算力调度中心：7 个功能 Tab 导航（含智能感知与传输优化仪表盘） |
| `compute-platform.js` | ~1,800 | 算力调度逻辑：指标看板、云渲染管理、GPU 调度、任务编排、智能感知与传输优化平台（算力节点感知、链路状态、故障告警、SVG 实时曲线、存储感知、故障切换记录、核心指标栏）、权限安全矩阵、费用告警 |
| `aigv-demo-data.js` | ~1,350 | 全域演示数据集：创意项目、分镜脚本、GPU 资源池、渲染会话、网络链路、算力节点感知数据（8 个节点）、存储节点（4 个 SSD）、网络采样数据（20 个采样点）、故障告警、切换记录（5 条历史）等 |
| `login.html` | 52 | 登录页面 |
| `register.html` | 60 | 注册页面 |
| `auth.js` | 134 | 认证逻辑：表单校验、登录/注册 API 调用、消息提示、状态持久化 |
| `styles.css` | ~5,200 | 暗金奢华主题全站样式：CSS 变量体系、网格布局、响应式断点、创意工作台 + 算力平台定制样式 |

### 3.6 数据与脚本

| 文件/目录 | 职责 |
|-----------|------|
| `data/catalog/knowledge_base.json` | **核心知识库**：项目指标（4项）、模型目录（6个模型）、场馆目录（4个场馆）、资产目录（空间锚点）、镜头目录（7种运镜）、知识规则、词汇库、引擎目录、资源池配置、推流配置、版权模板、演示租户 |
| `data/aigv.db` | SQLite 数据库（运行时首次自动创建 Schema + 索引） |
| `data/users.json` | 注册用户数据（werkzeug pbkdf2:sha256 密码哈希存储） |
| `data/jobs/<uuid>/` | 每个任务一个目录，包含 12 个 JSON 文件 |
| `data/assets/` | 上传资产文件存储（models/images/prompts 按场馆分类） |
| `scripts/init_db.py` | 数据库初始化 + 目录创建脚本 |
| `scripts/migrate_data.py` | 从 knowledge_base.json 批量迁移数据到 SQLite 的表 |

---

## 四、数据库设计

### 4.1 SQLite 数据库架构（14 张表 + 16 个索引）

数据库文件：`data/aigv.db`，通过 `Database` 类（database.py:28-531）管理，使用 threading.local() 实现线程安全。

**核心业务表：**

```
┌──────────────────────────────────────────────────────────────────┐
│  assets                                                          │
│  id(PK) | name | asset_type | venue_type | file_path | file_size │
│  | description | metadata(JSON) | thumbnail_path | created_at    │
│  | updated_at                                                     │
│  索引: idx_assets_type (asset_type)                               │
│  索引: idx_assets_venue (venue_type)                              │
├──────────────────────────────────────────────────────────────────┤
│  prompt_documents                                                 │
│  id(PK) | title | category | content | keywords | source_file    │
│  | created_at | updated_at                                        │
│  索引: idx_prompts_category (category)                            │
├──────────────────────────────────────────────────────────────────┤
│  venue_presets                                                    │
│  id(PK) | name | description | default_environment               │
│  | default_lighting | default_style                               │
│  | camera_defaults(JSON) | negative_prompt_parts                  │
│  | created_at | updated_at                                        │
├──────────────────────────────────────────────────────────────────┤
│  model_configs                                                    │
│  id(PK) | display_model | execution_provider | route_mode         │
│  | status | description | style_hint | recommended(INT)           │
│  | created_at | updated_at                                        │
├──────────────────────────────────────────────────────────────────┤
│  job_history                                                      │
│  id(PK) | status | stage | payload(JSON) | result(JSON)          │
│  | error | created_at | updated_at                                 │
│  索引: idx_jobs_status (status)                                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  ───────── 多租户/项目管理表（4 张）──────────                     │
│                                                                   │
│  tenants: id(PK) | name | code | tier | status | metadata(JSON)  │
│  users:   id(PK) | tenant_id(FK) | name | role | title | status  │
│           | metadata(JSON) | created_at | updated_at              │
│           索引: idx_users_tenant (tenant_id)                       │
│  projects: id(PK) | tenant_id(FK) | name | code | status         │
│            | render_mode | metadata(JSON) | created_at            │
│            索引: idx_projects_tenant (tenant_id)                   │
│  project_memberships: id(PK) | project_id(FK) | user_id(FK)       │
│                       | tenant_id(FK) | role | permissions(JSON)  │
│                       | created_at | updated_at                   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  ───────── 资源调度表（2 张）─────────────────                     │
│                                                                   │
│  resources: id(PK) | tenant_id(FK) | node_name | pool_type       │
│             | region | gpu_type | capacity_units | queue_depth    │
│             | status | utilization_hint | metadata(JSON)          │
│             索引: idx_resources_status (status)                    │
│  resource_allocations: id(PK) | job_id | resource_id(FK)          │
│                        | tenant_id(FK) | project_id(FK)           │
│                        | decision_reason | allocation_status       │
│                        | snapshot(JSON) | created_at               │
│                        索引: idx_allocations_job (job_id)          │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  ───────── 引擎与流表（2 张）─────────────────                     │
│                                                                   │
│  engine_profiles: id(PK) | engine_type | display_name            │
│                   | render_mode | stream_mode | status            │
│                   | metadata(JSON) | created_at                   │
│  stream_sessions: id(PK) | job_id | project_id(FK)               │
│                   | engine_profile_id(FK) | protocol               │
│                   | bitrate_mbps | latency_ms | fps               │
│                   | preview_url | metadata(JSON)                   │
│                   索引: idx_stream_job (job_id)                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  ───────── 版权与计费表（5 张）─────────────────                   │
│                                                                   │
│  asset_rights: id(PK) | asset_id | tenant_id(FK)                 │
│                | license_type | source_name | approval_status     │
│                | usage_scope | expires_at | restrictions(JSON)    │
│                | metadata(JSON) | created_at                       │
│                索引: idx_rights_asset (asset_id)                   │
│  asset_provenance_events: id(PK) | asset_id | tenant_id(FK)       │
│                           | event_type | event_summary            │
│                           | metadata(JSON) | created_at            │
│                           索引: idx_provenance_asset (asset_id)    │
│  billing_accounts: id(PK) | tenant_id(FK) | project_id(FK)       │
│                    | plan_name | balance | currency | status      │
│                    | metadata(JSON) | created_at                   │
│  billing_usage_records: id(PK) | job_id | tenant_id(FK)           │
│                         | project_id(FK) | amount | currency       │
│                         | usage_type | usage_units | metadata(JSON)│
│                         索引: idx_billing_project (project_id)     │
│  ops_events: id(PK) | tenant_id(FK) | project_id(FK) | job_id    │
│              | event_type | severity | message | metadata(JSON)   │
│              索引: idx_ops_project (project_id)                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 JSON 文件存储（任务持久化）

每个任务以 UUID 为目录名，存储在 `data/jobs/<uuid>/` 下。JobStore 类提供线程安全的读写，使用 `threading.Lock()` 保护内存缓存，原子写入（先写 .tmp 再 rename）。

| 文件 | 写入阶段 | 内容 |
|------|----------|------|
| `job.json` | queued → succeeded/error | 主状态记录：id、status、stage、result、payload、created_at、updated_at、error |
| `prompt_bundle.json` | knowledge_ready | PromptOrchestrator 完整输出：六模块、最终 Prompt、负向提示词、工作流模式 |
| `knowledge_hits.json` | knowledge_ready | 知识库命中记录：场馆/镜头/模型/资产/工作流 5 个维度的匹配来源和原因 |
| `asset_bundle.json` | knowledge_ready | 资产元数据：id、name、venue_type、workflow_mode、placeholder_geometry |
| `rights_snapshot.json` | rights_validated | 不可变版权快照：验证结果、来源链、数字摘要 |
| `scheduler_decision.json` | resource_scheduling | 调度决策：匹配节点、资源池、队列深度、决策原因 |
| `scene_spec.json` | blender_exporting | Blender 场景规格：摄像机运动参数、分辨率、帧率、资产几何体配置 |
| `artifacts.json` | blender_exporting | Blender 导出产物记录：scene.glb 路径、camera_path.json 路径、状态 |
| `render_session.json` | resource_scheduling | 引擎渲染会话：engine_type、render_mode、session_id、预览链接 |
| `stream_session.json` | streaming | 推流会话参数：协议类型、码率、延迟、FPS、编码器 |
| `monitor_ticks.json` | streaming | 监控采样点（3 个 tick）：GPU 利用率、显存、网络、码率、延迟、FPS |
| `billing_snapshot.json` | billing_recorded | 计费快照：GPU/引擎/推流三部分费用明细 |

---

## 五、核心业务流程

### 5.1 完整任务流水线（10 阶段状态机）

```
JOB_STAGE_ORDER = [
    "queued",             # ① 任务已创建
    "knowledge_ready",    # ② 知识检索与 Prompt 编排
    "rights_validated",   # ③ 资产版权校验
    "resource_scheduling",# ④ 算力资源调度
    "blender_exporting",  # ⑤ Blender 空间导出（条件触发）
    "provider_submitted", # ⑥ 已提交视频生成通道
    "provider_running",   # ⑦ 视频模型推理中
    "streaming",          # ⑧ 推流会话准备
    "billing_recorded",   # ⑨ 计费快照记录
    "succeeded",          # ⑩ 生成成功
    "error"               # 错误终止
]
```

**阶段流转详述：**

```
用户提交表单
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│ ① queued (已创建任务)                                           │
│   JobStore.create() → 生成 UUID → 写入 job.json                │
│   → build_initial_result(preview) 初始化结果对象                 │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ② knowledge_ready (知识检索 + Prompt 编排)                       │
│   PromptOrchestrator.preview(payload) 执行：                     │
│   ├─ _resolve_venue()     → 场馆模板（知识库匹配 + 默认回退）     │
│   ├─ _resolve_model()     → AI 模型配置（模式 + 通道）            │
│   ├─ _resolve_asset()     → 空间锚点资产（场馆联动 + 默认）       │
│   ├─ _resolve_shot()      → 镜头语言（用户选择 + 场馆默认）       │
│   ├─ _resolve_workflow_mode() → text_to_video / hybrid_image     │
│   ├─ _build_prompt_modules() → 六模块组装                       │
│   ├─ _assemble_prompt()   → 逗号拼接六模块为最终 Prompt          │
│   ├─ _build_negative_prompt() → 多层来源合并去重                 │
│   ├─ _build_execution_plan() → 路由模式 + 执行通道               │
│   └─ _build_knowledge_hits() → 5 维度知识命中记录                │
│   写入: prompt_bundle.json, knowledge_hits.json, asset_bundle.json│
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ③ rights_validated (版权校验)                                    │
│   RightsService.validate_asset_rights(asset_id, usage_scope)     │
│   ├─ 查询 asset_rights 表                                       │
│   ├─ 检查 approval_status（需 approved/approved_with_notice）    │
│   ├─ 检查 expires_at（未过期）                                   │
│   ├─ 检查 usage_scope（匹配用途范围）                            │
│   └─ 构建 rights_snapshot（含来源链 + 不可变摘要）               │
│   写入: rights_snapshot.json                                     │
│   OpsService 记录运维事件                                         │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ④ resource_scheduling (算力调度)                                 │
│   SchedulerService.allocate(job_id, payload)                     │
│   ├─ 按 engine_target 确定首选资源池类型                          │
│   │   blender_anchor → local_gpu                                 │
│   │   ue5_cloud/unity_cloud → public_cloud                       │
│   │   steamvr_stream → edge_gpu                                   │
│   ├─ 从 resources 表匹配对应的资源节点                            │
│   ├─ 记录 resource_allocations 表                               │
│   └─ 生成调度决策快照                                             │
│   写入: scheduler_decision.json                                  │
│   EngineService.create_session() → 创建渲染会话                   │
│   写入: render_session.json                                       │
│   生成 scene_spec.json（摄像机参数 + 资产几何体）                  │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑤ blender_exporting (空间导出 - 条件触发)                         │
│   触发条件:                                                        │
│     ENABLE_BLENDER_EXPORT = true                                  │
│     AND workflow_mode = "hybrid_image_to_video"                   │
│     AND asset_bundle.id != "text_only"                            │
│                                                                   │
│   BlenderExecutionAdapter(local_batch)                             │
│   └─► BlenderRunner.run_blender_export()                           │
│       ├─ subprocess.Popen: blender -b -P blender_batch.py         │
│       ├─ 传入 scene_spec.json 参数                                │
│       ├─ 无头 Blender: 创建几何体 → 设置材质 → 相机动画             │
│       ├─ 导出: scene.glb + camera_path.json + artifacts.json      │
│       └─ 超时控制: 300s                                           │
│                                                                   │
│   不触发时: artifacts = { "status": "skipped" }                    │
│   写入: artifacts.json                                            │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ [如果 route_mode == "preview-only" → 跳过 ⑥⑦⑧ → 到 ⑨]        │
│   仅展示模式：直接 complete_preview_only_job()                     │
│   result.provider_result.status = "preview_only"                  │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑥ provider_submitted (提交视频生成)                              │
│   ProviderRouter.submit_generation()                             │
│   ├─ create_provider(execution_provider) 厂商工厂                │
│   │   "seedance" → SeedanceProvider(api_key, base_url, model)    │
│   │   "luma" → LumaProvider(api_key, base_url)                   │
│   │   "preview_only/placeholder" → ProviderRoutingError          │
│   ├─ _build_generation_request() 构建请求                        │
│   │   seedance: prompt + duration_s + resolution + aspect_ratio  │
│   │   luma: prompt + aspect_ratio + optional keyframes           │
│   └─ provider.create_generation() → 提取 job_id                  │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑦ provider_running (视频模型推理中)                              │
│   ProviderRouter.wait_until_done()                               │
│   ├─ 轮询间隔: 5 秒                                               │
│   ├─ 超时时间: 900 秒                                             │
│   ├─ 状态检查: completed/succeeded/done → 返回                    │
│   ├─ 失败检查: failed/error/canceled → 终止                      │
│   └─ extract_video_url()                                         │
│       seedance: data.outputs[0]                                   │
│       luma: assets.video 或 output.video_url                     │
│   写入: provider_result.json                                     │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑧ streaming (推流会话准备)                                      │
│   StreamService.create_session(job_id, payload, engine_session)  │
│   ├─ low_latency → WebRTC, 35ms, 9.8 Mbps, 72 FPS (VR)         │
│   ├─ balanced → HLS, 75ms, 12.5 Mbps, 30 FPS                    │
│   └─ showcase → HLS, 120ms, 18.0 Mbps, 30 FPS                   │
│   写入: stream_session.json                                       │
│   SchedulerService.build_monitor_ticks() → 生成 3 个监控采样点    │
│   写入: monitor_ticks.json                                        │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑨ billing_recorded (计费快照记录)                                │
│   BillingService.build_job_billing()                              │
│   ├─ GPU小时 = duration_s / 3600 × 120 CNY/h                    │
│   ├─ 引擎小时 = GPU小时 × 1.15 × 80 CNY/h                        │
│   ├─ 推流小时 = GPU小时 × 1.25 × 40 CNY/h                        │
│   └─ 写入 billing_usage_records 表                               │
│   写入: billing_snapshot.json                                     │
└────────────┬───────────────────────────────────────────────────┘
             ▼
┌────────────────────────────────────────────────────────────────┐
│ ⑩ succeeded (生成完成)  /  error (执行失败)                      │
│   succeeded: video_url 已提取 → 前端展示视频                     │
│   error:    异常信息记录到 job.error → 前端展示错误详情           │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 前端 Task 提交与轮询流程

```
用户点击"生成视频"按钮
    │
    ├─► handleSubmit(event) in app.js
    │   ├─ preventDefault()
    │   ├─ clearPoll()                       // 清除之前的轮询
    │   ├─ setUiStatus('submitting')
    │   ├─ previewPrompt({ silent: true })    // 静默生成最终 Prompt
    │   ├─ POST /api/jobs (JSON body)        // 提交任务
    │   ├─ renderJob(job)                    // 渲染初始结果
    │   └─ startPolling(job.id)              // 5秒轮询
    │
    ▼
POST /api/jobs (Flask: create_job)
    ├─ parse_json_body(request)              // 解析 + 校验 JSON
    ├─ _normalize_preview_payload()          // 规范化参数 + 调用 PromptOrchestrator.preview()
    ├─ job_store.create(normalized, result)  // 生成 UUID，写入 job.json
    └─ start_job_worker() (后台守护线程)     // daemon=True，异步执行
        │
        └─ _run() 线程内执行完整流水线（阶段 ②→⑩）
            ├─ prompt_orchestrator.preview()        → 知识检索 + Prompt 编排
            ├─ rights_service.validate_asset_rights() → 版权校验
            ├─ scheduler_service.allocate()          → 算力调度
            ├─ blender_adapter.export_scene()        → Blender 导出（条件触发）
            ├─ router.submit_generation()            → 提交视频生成
            ├─ router.wait_until_done()              → 轮询等待（900s/5s）
            ├─ stream_service.create_session()       → 推流会话
            ├─ scheduler_service.build_monitor_ticks() → 监控采样
            ├─ billing_service.build_job_billing()   → 计费核算
            └─ _set_job_state()                      → 阶段状态更新

前端轮询 (每 5 秒)
    └─ GET /api/jobs/<id> → api() 解析响应
        └─ renderJob(job)
            ├─ renderStageList()                    → 阶段进度列表
            ├─ renderJobResult()                    → 结果面板
            ├─ renderSchedulePanel()                → 调度面板
            ├─ renderMonitorPanel()                 → 监控面板
            ├─ renderRightsPanel()                  → 版权面板
            ├─ renderBillingPanel()                 → 计费面板
            └─ renderOpsPanel()                     → 运维事件流
            └─ 若 succeeded/error → clearPoll()     → 停止轮询
```

**竞态防护机制：**
- `previewRequestId`、`submitRequestId`、`pollRequestId` 三个递增计数器
- 每次操作递增 ID，回调时用闭包保留的 ID 与当前全局 ID 比较
- ID 不匹配则丢弃过期结果，防止快速连续操作导致 UI 状态错乱

---

## 六、核心模块详细设计

### 6.1 Prompt 编排引擎 (`prompt_engine.py`)

**类：`PromptOrchestrator(catalog_service)`**

`preview(payload)` 方法的完整执行流程：

```python
def preview(self, payload):
    # 1. 实体解析（从知识库精确匹配 + 默认回退）
    venue = self._resolve_venue(payload)       # payload.venue_type → 知识库 venue_catalog → default_venue
    model = self._resolve_model(payload)       # payload.ai_model → 知识库 model_catalog → default_model
    asset = self._resolve_asset(payload, venue) # payload.asset_id → 场馆默认资产 → text_only
    shot  = self._resolve_shot(payload, venue)  # payload.shot_type → 场馆 default_shot → 第一个镜头

    # 2. 工作流模式判定
    workflow_mode = self._resolve_workflow_mode(payload, venue, asset)
    # 显式 > 资产绑定 > 场馆推荐 > text_to_video（纯文本）
    # 资产 id == "text_only" 且未显式指定 → 强制 text_to_video

    # 3. 六模块 Prompt 组装
    prompt_modules = self._build_prompt_modules(payload, venue, model, asset, shot, workflow_mode)
    # ┌──────┬─────────────────────────────────────────────┐
    # │ 模块  │ 来源与逻辑                                    │
    # ├──────┼─────────────────────────────────────────────┤
    # │ 1 镜头│ shot.prompt 或 venue.default_camera_prompt   │
    # │ 2 主体│ subject_hint → venue.default_subject          │
    # │      │ 混合模式附加: "using {asset} as spatial anchor"│
    # │ 3 动态│ dynamics_hint → venue.default_dynamics        │
    # │ 4 环境│ environment_hint → venue.default_environment  │
    # │ 5 光影│ lighting_hint → venue.default_lighting        │
    # │ 6 风格│ style_anchor → venue.default_style            │
    # │      │ + model.style_hint (追加)                     │
    # │      │ + engine_target + render_mode (尾部标记)      │
    # │      │ 混合模式: "preserve structural proportions..." │
    # └──────┴─────────────────────────────────────────────┘

    # 4. 最终 Prompt 拼接
    prompt = self._assemble_prompt(prompt_modules)
    # 格式: "camera, subject, dynamics, environment, lighting, style."

    # 5. 负向提示词构建
    negative_prompt = self._build_negative_prompt(payload, venue, asset)
    # 来源顺序（去重）: 知识规则 → 场馆预设 → 资产预设 → 用户输入

    # 6. 执行计划生成
    execution_plan = self._build_execution_plan(model)
    # display_model + execution_provider + route_mode

    # 7. 警告生成
    warnings = self._build_warnings(model, asset, workflow_mode)
    # demo-route 路由提示 / preview-only 不可用警告 / 无锚点警告

    # 8. 知识命中记录
    knowledge_hits = self._build_knowledge_hits(...)
    # 5 条记录: venue / shot / model / asset / workflow

    return { prompt_bundle, knowledge_hits, warnings, asset_bundle, ... }
```

**数据来源优先级（逐级回退）:**

| 参数 | 优先级 1 (用户) | 优先级 2 (知识库) | 优先级 3 (兜底) |
|------|-----------------|-------------------|-----------------|
| venue | `payload.venue_type` | catalog 默认/推荐场馆 | `{}` 空对象 |
| model | `payload.ai_model` | catalog 默认/推荐模型 | `{}` 空对象 |
| asset | `payload.asset_id` | 场馆推荐资产 → 场馆任意资产 | `text_only` |
| shot | `payload.shot_type` | 场馆 `default_shot` → 首个镜头 | `{}` 空对象 |
| workflow | `payload.workflow_mode` | 资产 `workflow_mode` → 场馆推荐 | `text_to_video` |
| subject_hint | `payload.subject_hint` | `venue.default_subject` | `""` 空字符串 |
| dynamics_hint | `payload.dynamics_hint` | `venue.default_dynamics` | `""` |
| environment_hint | `payload.environment_hint` | `venue.default_environment` | `""` |
| lighting_hint | `payload.lighting_hint` | `venue.default_lighting` | `""` |
| style_anchor | `payload.style_anchor` | `venue.default_style` | `""` |

### 6.2 多模型路由系统 (`provider_router.py`)

**路由模式矩阵：**

| 模式 | display_model | execution_provider | 执行行为 | 适用场景 |
|------|---------------|-------------------|----------|----------|
| `native` | Seedance v1.5 Pro | seedance | 直接执行 | 真实生产通道 |
| `demo-route` | Sora 2 / Veo 3 / Runway Gen-3 / Kling 3.0 | seedance | 展示模型A，Seedance代理执行 | 申报演示 |
| `preview-only` | 未配置通道的模型 | preview_only | 不执行，仅预览 | 占位展示 |
| `optional` | Luma Dream Machine | luma | 可选执行通道 | 备选方案 |

**提供商工厂 (`create_provider`):**

```
ProviderRouter.create_provider(execution_provider)
    │
    ├─ "seedance" ──► SeedanceProvider(api_key, base_url, model_name)
    │   ├─ 创建: POST {base_url}/model/generateVideo
    │   │   参数: model, prompt, aspect_ratio, duration, resolution,
    │   │         camera_fixed=False, generate_audio=True, seed=-1
    │   │   返回: { data: { id: "prediction_id" } }
    │   │
    │   ├─ 轮询: GET {base_url}/model/prediction/{id}
    │   │   返回: { data: { status, outputs: [video_url] } }
    │   │
    │   └─ 状态: completed/succeeded/done → 完成
    │           failed/error/canceled → 失败
    │
    ├─ "luma" ──► LumaProvider(api_key, base_url)
    │   ├─ 创建: POST {base_url}/generations
    │   │   参数: prompt, aspect_ratio, 可选 keyframes
    │   │   返回: { id: "generation_id", state: "pending" }
    │   │
    │   ├─ 轮询: GET {base_url}/generations/{id}
    │   │   返回: { state, assets: { video: "url" } }
    │   │
    │   └─ 状态: completed/succeeded/done → 完成
    │
    └─ "preview_only" / "placeholder" / ""
        └─► ProviderRoutingError("仅用于申报展示")
```

**API Key 校验：** 创建 Provider 实例前先检查对应 API Key 是否存在，未配置则抛出 `ProviderRoutingError("missing_api_key")`。

### 6.3 Blender 集成架构

**两种运行模式：**

```
模式 1: local_batch (本地批处理 — 当前可用)
┌──────────────────┐  subprocess.Popen  ┌──────────────────────────┐
│ backend/          │ ─────────────────►│ Blender (--background)    │
│ blender_runner.py │                    │ blender/batch.py          │
│                   │                    │                           │
│ 超时: 300s        │                    │ 1. 解析 scene_spec.json   │
│ 捕获 stdout/stderr│                    │ 2. 创建占位几何体 (Cube/   │
│ 读取 artifacts.json│◄─────────────────│    Cylinder/Plane)         │
└──────────────────┘  返回 artifacts    │ 3. 7 种相机动画           │
                                         │ 4. GLB 导出                │
 mode 2: mcp_remote (实时交互 — 预留)    │ 5. camera_path.json 导出   │
┌──────────────────┐  JSON-RPC/stdio   │ 6. artifacts.json 导出     │
│ backend/          │ ─────────────────►└──────────────────────────┘
│ blender_adapter.py│                    ┌──────────────────────────┐
│                   │                    │ Blender (MCP Server)      │
│ 当前抛出          │◄─────────────────│ blender_agent.py           │
│ BlenderAdapterError│  预留接口         │                           │
│ ("演示版未开启")  │                    │ MCP 工具:                 │
└──────────────────┘                    │ - list_scene_objects      │
                                        │ - run_python_script       │
                                        │ - capture_viewport        │
                                        └──────────────────────────┘
```

**Blender Batch 7 种相机运动：**

| 运镜类型 | camera_move.type | 运动描述 | 视觉表现 |
|----------|------------------|----------|----------|
| orbit | `orbit` | 360° 环绕目标点水平旋转 | 全方位展示空间 |
| dolly_in | `dolly_in` | 沿 Y 轴从远处平滑推进至 30% 距离 | 空间层次递进 |
| crane_up | `crane_up` | 沿 Z 轴缓慢垂直升起 | 纵向空间展开 |
| tracking | `tracking` | 沿 X 轴横向平行跟拍 | 水平空间扫描 |
| fpv | `fpv` | 对角线穿梭运动 | 动态空间探索 |
| macro_pan | `macro_pan` | 近距离微距平移 | 细节特写 |
| low_angle_glide | `low_angle_glide` | 低机位贴地滑行 | 仰角空间感 |

**触发条件：** `ENABLE_BLENDER_EXPORT=true` AND `workflow_mode="hybrid_image_to_video"` AND `asset_bundle.id != "text_only"`

### 6.4 知识库服务 (`catalog_service.py`)

**CatalogService** —— 基于 JSON 文件的知识库加载器，采用惰性缓存策略。

`knowledge_base.json` 包含 13 个目录：

| 目录 | 数量 | 用途 |
|------|------|------|
| `project_metrics` | 4 项 | 项目展示指标（素材库容量、示范场景数、软件成果、服务企业数） |
| `model_catalog` | 6 个 | AI 模型配置：Seedance Pro（native）、Sora 2/Veo 3/Runway Gen-3/Kling 3.0（demo-route）、Luma（optional） |
| `venue_catalog` | 4 个 | 场馆预设：大剧院/现代美术馆/古典博物馆/音乐厅，各有 hero_title/default_*/negative_prompt_parts/camera_defaults |
| `asset_catalog` | 多个 | 空间锚点资产：各场馆占位几何体（包含 placeholder_geometry）、text_only 纯文本模式 |
| `shot_catalog` | 7 个 | 镜头语言：orbit/dolly_in/crane_up/tracking/fpv/macro_pan/low_angle_glide 的中英文 Prompt 模板 |
| `knowledge_rules` | 1 组 | 全局规则：default_negative_prompt_parts 通用负向提示词模板 |
| `workflow_tips` | 多条 | 工作流操作提示文案 |
| `lexicon_catalog` | 多个 | 词汇库：包含 term（术语）、goal（目标）、usage（用法） |
| `engine_catalog` | 4 个 | 引擎目录：Blender Anchor / UE5 Cloud / Unity Cloud / SteamVR Stream |
| `resource_pool_catalog` | 多个 | 资源池类型配置 |
| `stream_profile_catalog` | 3 个 | 推流配置：low_latency / balanced / showcase |
| `rights_template_catalog` | 多个 | 版权模板 |
| `demo_tenant_catalog` | 1 个 | 演示租户数据 |

### 6.5 前端 SPA 架构

**状态管理模式（app.js 全局 state 对象）：**

```javascript
var state = {
    bootstrap: null,         // /api/bootstrap 知识库全量数据
    currentJobId: null,      // 当前任务 UUID
    pollTimer: null,         // setInterval 定时器 ID
    autoTitle: true,         // 场馆切换时自动填充标题
    uiStatus: "loading",     // UI 状态: loading/ready/previewing/submitting/polling/success/error
    lastPreview: null,       // 最近一次 /api/prompt/preview 返回数据
    currentJob: null,        // 最近一次 /api/jobs/<id> 返回的任务对象
    demoContext: null,       // /api/demo/context 租户/用户/项目上下文
    previewRequestId: 0,     // 竞态防护：预览请求 ID
    submitRequestId: 0,      // 竞态防护：提交请求 ID
    pollRequestId: 0         // 竞态防护：轮询请求 ID
};
```

**事件驱动链路：**

```
用户交互                      前端处理                      API 调用
──────────────────────────────────────────────────────────────
页面加载          →  bootstrap()              →  GET /api/bootstrap
                  →  GET /api/demo/context    →  GET /api/demo/context
                  →  applyVenueDefaults()
                  →  previewPrompt({silent})
                  →  renderModels/initializeSelects

场馆变更          →  applyVenueDefaults()     →  自动填充 环境/光影/资产
                  →  queueSilentPreview()      →  POST /api/prompt/preview

下拉框变更        →  queueSilentPreview()      →  POST /api/prompt/preview
（模型/镜头/引擎等）→  renderContextPanel()

点击"预览Prompt"  →  previewPrompt({silent:false}) → POST /api/prompt/preview
                  →  renderPromptPreview()

点击"生成视频"    →  handleSubmit()            →  POST /api/prompt/preview(silent)
                  ├─  previewPrompt({silent})  →  POST /api/jobs
                  ├─  renderJob()              →  startPolling(job.id)
                  └─  每5秒轮询                 →  GET /api/jobs/<id>
                                              →  成功后 clearPoll()
```

**关键渲染函数：**
- `renderPromptPreview(data)` —— 六模块卡片网格 + 最终 Prompt 文本展示
- `renderStageList(job)` —— 10 阶段进度列表（done/active/pending/error 状态）
- `renderJobResult(job)` —— 综合结果面板：调度/引擎/推流/版权/计费/视频
- `renderContextPanel()` —— 租户/用户/项目/引擎/推流上下文摘要
- `renderSchedulePanel()` / `renderMonitorPanel()` / `renderRightsPanel()` / `renderBillingPanel()` / `renderOpsPanel()` —— 各监控运维面板

### 6.6 创意生产工作台 (Creative Studio)

页面路径：`/creative-studio`，由 `creative-studio.html` + `creative-studio.js` + `aigv-demo-data.js` 组成。

**6 个生产步骤：**

| 步骤 | 模块 | 功能描述 |
|------|------|----------|
| 01 | 需求分析 | 填写创作需求表单 → AI 分析语义要素 → 自动生成 6 个分镜脚本 → 编辑/复制/删除/排序/确认分镜 |
| 02 | 概念图生成 | 为已确认分镜生成 4 张概念参考图 → 选择模型 → 设置关键帧 → 收藏/查看/删除 |
| 03 | 视频生成 | 基于关键帧生成视频：时长/运镜/运动强度/稳定性/分辨率/帧率/模型 → 进度条 → 取消/重新生成 |
| 04 | 多模态增强 | 配音角色选择（4 种音色）→ 背景音乐（5 种风格）→ 音效库 → 5 轨时间线（视频/配音/音乐/音效/字幕）→ 片段 CRUD |
| 05 | 人机精调 | 左右对比面板 → 6 项基础滤镜 → 8 项专业调色 → 6 项 AI 批量处理 |
| 06 | 输出适配 | 9 个输出平台选择 → 参数自动填充 → 导出目录树 → 复制 Manifest → 模拟下载 |

**数据特性：** 当前为纯前端演示模式，数据来自 `aigv-demo-data.js`，通过 `localStorage` 持久化工作进度。

### 6.7 算力调度中心 (Compute Platform)

页面路径：`/compute-platform`，由 `compute-platform.html` + `compute-platform.js` + `aigv-demo-data.js` 组成。

**7 个功能 Tab：**

| Tab | 功能 | 交互特性 |
|-----|------|----------|
| 运行总览 | 10 项指标卡片 + 4 个 SVG 图表 | 纯展示 |
| 云渲染 | 渲染会话表格 → 详情抽屉 → 状态循环切换 | 可交互 |
| GPU 调度 | 资源池卡片 → 搜索/筛选 → 节点表格 → 详情抽屉 | 可交互 |
| 调度任务编排 | 8 字段表单 → 按策略匹配最优 GPU 节点 → 结果卡片 | 可交互 |
| 智能感知与传输优化 | 算力节点感知网格（8 节点 × GPU/VRAM/温度/心跳）→ 链路状态列表（5 条 × 时延/抖动/丢包/带宽）→ 故障告警面板（红闪动画/自动恢复/确认）→ 3 个 SVG 实时曲线（带宽/时延/丢包率）→ 存储感知（4 个 SSD × 容量/读写速度/连接数）→ 故障切换记录表（5 条历史）→ 底部 6 列核心指标栏 → 故障模拟模态框（多阶段恢复 0-15s） | 实时监控+交互仿真 |
| 权限安全 | 角色 × 权限矩阵（4 角色 × 8 权限）→ 复选框切换 → localStorage 持久化 | 可交互 |
| 费用告警 | 费用摘要（今日/本周/本月/构成）→ 告警表格（确认/处理中/关闭）→ 运维事件日志 | 可交互 |

**数据特性：** 纯前端仿真模式，所有数据来自 `aigv-demo-data.js`，告警/权限/配置通过 localStorage 持久化。

---

## 七、数据流图

### 7.1 Prompt 生成数据流

```
用户表单 payload (collectPayload)
    │
    ├─► venue_type ──────────► CatalogService.get_venue(id)
    ├─► ai_model  ───────────► CatalogService.get_model(id)
    ├─► asset_id  ───────────► CatalogService.get_asset(id) + 场馆联动
    ├─► shot_type ───────────► CatalogService.get_shot(id)
    │
    ▼
PromptOrchestrator.preview(payload)
    │
    ├─► venue.default_* ──────► prompt_modules {camera, subject, dynamics, environment, lighting, style}
    ├─► shot.prompt            filter: _to_text()
    ├─► model.style_hint       拼接: _join_fragments()
    ├─► user hints (覆盖)
    │
    ├─► _assemble_prompt() ───► "{camera}, {subject}, {dynamics}, {environment}, {lighting}, {style}."
    │
    └─► 返回完整 preview:
        {
          prompt_bundle: { title, modules, prompt, negative_prompt,
                           workflow_mode, shot_id, camera_move_type,
                           display_model, execution_provider, route_mode,
                           camera_defaults, venue_id, venue_name },
          knowledge_hits: [5条记录],
          workflow_mode, execution_provider, display_model, route_mode,
          warnings: [],
          asset_bundle: { id, name, venue_type, workflow_mode,
                          source_type, metadata, placeholder_geometry, ... }
        }
```

### 7.2 视频生成任务数据流

```
JobStore.create(payload, initial_result)
    │
    └─► data/jobs/<uuid>/job.json              ← 主状态记录

start_job_worker() → _run() (后台线程)
    │
    ├─► knowledge_ready:
    │   ├─ prompt_bundle.json                   ← PromptOrchestrator 完整输出
    │   ├─ knowledge_hits.json                  ← 5 维度知识命中记录
    │   └─ asset_bundle.json                    ← 资产元数据
    │
    ├─► rights_validated:
    │   └─ rights_snapshot.json                 ← 版权校验 + 来源链 + 摘要
    │
    ├─► resource_scheduling:
    │   ├─ scheduler_decision.json              ← 调度决策 + 节点信息
    │   ├─ render_session.json                  ← 引擎渲染会话
    │   └─ scene_spec.json                      ← Blender 场景规格
    │
    ├─► blender_exporting (条件触发):
    │   ├─ artifacts.json                       ← status: exported/skipped/warning
    │   ├─ scene.glb                            ← 3D 场景模型
    │   └─ camera_path.json                     ← 相机运动轨迹
    │
    ├─► stream_session.json                     ← 推流参数
    ├─► monitor_ticks.json                      ← 3 个监控采样点
    │
    ├─► provider_submitted → provider_running:
    │   └─ provider_result.json                 ← 执行通道结果 + 视频 URL
    │
    └─► billing_recorded:
        └─ billing_snapshot.json                ← 三方费用明细
```

### 7.3 配置文件加载流程

```
app.py: create_app(Config)
    │
    ├─► Config()                                ← backend/config.py
    │   ├─ os.environ 读取环境变量
    │   ├─ _to_bool() / _to_int() 类型转换
    │   └─ _validate_config()                   ← 启动时校验
    │       ├─ 检查 API Key
    │       ├─ 创建 DATA_DIR
    │       ├─ 验证 CATALOG_PATH
    │       └─ 输出配置警告
    │
    ├─► seed_demo_data(cfg.DATA_DIR)            ← backend/demo_seed_service.py
    │   └─► Database._init_schema()             ← 首次运行时创建 14 张表 + 16 个索引
    │   └─► 注入演示租户/用户/项目/资源/引擎/版权/计费
    │
    ├─► JobStore(cfg.JOBS_DIR)                  ← data/jobs/ 目录
    ├─► CatalogService(cfg.CATALOG_PATH)        ← data/catalog/knowledge_base.json
    ├─► PromptOrchestrator(catalog_service)
    │
    └─► 注册全部路由模块 + 错误处理器
```

---

## 八、配置参数说明

| 环境变量 | 默认值 | 类型 | 说明 |
|----------|--------|------|------|
| `SEEDANCE_API_KEY` | (空) | String | Seedance Atlas Cloud API 密钥，未配置则无法执行 |
| `SEEDANCE_BASE_URL` | `https://api.atlascloud.ai/api/v1` | String | Seedance API 基础 URL |
| `SEEDANCE_MODEL_NAME` | `bytedance/seedance-v1.5-pro/text-to-video` | String | Seedance 模型标识 |
| `LUMA_API_KEY` | (空) | String | Luma Dream Machine API 密钥 |
| `LUMA_BASE_URL` | `https://api.lumalabs.ai/dream-machine/v1` | String | Luma API 基础 URL |
| `BLENDER_BIN` | `blender` | String | Blender 可执行文件路径 |
| `ENABLE_BLENDER_EXPORT` | `true` | Boolean | 是否启用 Blender 空间导出（true/false/1/0） |
| `BLENDER_EXECUTION_MODE` | `local_batch` | String | Blender 执行模式：`local_batch` / `mcp_remote` |
| `DATA_DIR` | `./data` | String | 数据存储根目录 |
| `SECRET_KEY` | (随机 24 字节 hex) | String | Flask Session 密钥 |
| `HOST` | `0.0.0.0` | String | Flask 服务监听地址 |
| `PORT` | `8000` | Integer | Flask 服务监听端口 |

---

## 九、技术要点与设计决策

### 9.1 线程安全设计
- **Database**（database.py）: 使用 `threading.local()` 实现线程本地 SQLite 连接，`threading.Lock()` 保护写操作
- **JobStore**（jobs.py）: 使用 `threading.Lock()` 保护内存缓存字典，原子文件写入（tmp → rename）
- **Job Worker**: 每个任务独立后台线程（`daemon=True`），不阻塞 Flask 主进程

### 9.2 Python 兼容性
- 代码使用 Python 3.10 运行环境（`.venv/lib/python3.10/`），使用 `.format()` 格式化字符串
- 所有模块首行 `from __future__ import absolute_import`（预留 3.6 兼容）
- `os.makedirs(exist_ok=True)` 用于目录创建

### 9.3 前端竞态防护
- 三个递增请求 ID（preview/submit/poll）
- 闭包内保留请求 ID，回调时对比全局 ID
- 不匹配时静默丢弃过期响应

### 9.4 SAAS 多租户架构（演示阶段）
- 四级关系模型：Tenant → User → Project → ProjectMembership
- 权限检查基于 `project_memberships.role`（owner/admin/editor/viewer）和 `.permissions` JSON 列表
- 资源（GPU 节点）、计费、版权均在租户/项目维度隔离
- 当前仅含一套演示数据（`华中文博演示集团` → `陈策展`/`刘制片`）

### 9.5 Blender stdout 劫持
- MCP 基于 JSON-RPC over stdio，但 Blender 大量日志输出到 stdout 会破坏通信
- `server_transport.py` 使用 `os.dup2()` 将原始 stdout fd 重定向到 stderr
- MCP 消息通过预留的原始 fd 发送，确保 JSON-RPC 管道干净

### 9.6 双轨存储策略
- **SQLite**（14 张表）：存储有结构关系的业务数据（资产、租户、资源、计费、版权等）
- **JSON 文件**（`data/jobs/<uuid>/`）：存储任务生命周期快照（便于调试、审计、独立备份）

### 9.7 演示数据自动注入
- 每次启动 `create_app()` 时调用 `seed_demo_data(cfg.DATA_DIR)`
- 使用 `_insert_if_missing()` 幂等覆盖，重复启动不会创建重复数据
- 注入内容：1 个租户 + 2 个用户 + 1 个项目 + 2 个成员 + 3 个 GPU 节点 + 4 个引擎配置 + 3 条版权记录 + 3 条来源事件 + 1 个计费账户

---

## 十、完整 API 路由列表

### 10.1 页面路由

| 方法 | 路径 | 页面 |
|------|------|------|
| GET | `/` | 工作台主页 (index.html) |
| GET | `/creative-studio` | 创意生产工作台 |
| GET | `/compute-platform` | 算力调度中心 |
| GET | `/assets` | 资产库 |
| GET | `/login` | 登录页 |
| GET | `/register` | 注册页 |
| GET | `/web/<filename>` | 静态资源（JS/CSS） |

### 10.2 核心业务 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/bootstrap` | 加载全量知识库数据 |
| GET | `/api/health` | 健康检查（API Key状态/Blender开关/持久化方式） |
| POST | `/api/prompt/preview` | 生成 Prompt 预览（不创建任务） |
| POST | `/api/jobs` | 创建并启动视频生成任务 |
| GET | `/api/jobs/<id>` | 查询任务状态（前端轮询） |

### 10.3 认证 API

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录（Session） |
| POST | `/api/auth/register` | 用户注册（密码 >= 6 位，用户名 >= 2 位） |
| POST | `/api/auth/logout` | 用户登出 |
| GET | `/api/auth/status` | 登录状态查询 |

### 10.4 资产管理 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/assets` | 资产列表（支持 asset_type/venue_type 过滤 + 分页） |
| POST | `/api/assets` | 创建资产（需要 name 字段） |
| GET | `/api/assets/<id>` | 资产详情 |
| PUT | `/api/assets/<id>` | 更新资产 |
| DELETE | `/api/assets/<id>` | 删除资产 + 关联文件 |
| POST | `/api/assets/upload` | 上传资产文件（multipart/form-data） |
| GET | `/api/assets/<id>/download` | 下载资产文件 |
| GET | `/data/assets/<path>` | 直接访问资产文件 |

### 10.5 Prompt 文档 API

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/prompts/documents` | 文档列表（支持 category 过滤 + 分页） |
| POST | `/api/prompts/documents` | 创建文档（需要 title） |
| GET | `/api/prompts/documents/<id>` | 文档详情 |
| PUT | `/api/prompts/documents/<id>` | 更新文档 |
| DELETE | `/api/prompts/documents/<id>` | 删除文档 |
| GET | `/api/prompts/categories` | 分类统计列表 |

### 10.6 控制平面 API（多租户管理）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/demo/context` | 演示上下文（租户/用户/项目） |
| POST | `/api/demo/context/select` | 选择演示上下文 |
| GET | `/api/tenants` | 租户列表 |
| GET | `/api/users` | 用户列表（可按 tenant_id 过滤） |
| GET | `/api/projects` | 项目列表（可按 tenant_id 过滤） |
| GET | `/api/projects/<id>/members` | 项目成员及用户详情 |
| GET | `/api/permissions/check` | 权限检查（tenant/user/project/permission） |

### 10.7 控制平面 API（算力调度与监控）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/resources` | GPU 资源节点列表 |
| GET | `/api/resources/summary` | 资源池摘要（总数/就绪数/队列深度/GPU类型） |
| POST | `/api/scheduler/preview` | 调度预览（不持久化） |
| GET | `/api/jobs/<id>/schedule` | 任务调度决策 |
| GET | `/api/jobs/<id>/monitor` | 任务监控快照 |
| GET | `/api/engines` | 引擎配置列表 |
| POST | `/api/engines/session/preview` | 引擎会话预览 |
| GET | `/api/jobs/<id>/engine-session` | 任务引擎会话 |
| GET | `/api/jobs/<id>/stream-session` | 任务推流会话 |

### 10.8 控制平面 API（版权与计费）

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/assets/<id>/rights` | 资产版权信息 |
| POST | `/api/assets/<id>/rights/validate` | 版权校验 |
| GET | `/api/assets/<id>/provenance` | 资产来源追踪链 |
| GET | `/api/jobs/<id>/rights-snapshot` | 任务版权快照 |
| GET | `/api/billing/summary` | 计费摘要（账户 + 近期用量 + 总额） |
| GET | `/api/projects/<id>/usage` | 项目用量明细 |
| GET | `/api/jobs/<id>/billing` | 任务计费快照 |
| GET | `/api/ops/events` | 运维事件列表（可按 project_id 过滤） |

---

## 十一、部署架构

```
开发模式:
    python3 app.py
    → Flask 内置服务器 (0.0.0.0:8000)
    → 自动创建 data/ 目录结构
    → 自动初始化 SQLite schema + 索引
    → 自动注入演示数据（幂等）
    → Seedance API 连接可用时真实执行视频生成

生产模式:
    gunicorn -b 0.0.0.0:8000 app:app
    → 多 Worker 进程
    → 需配置 SECRET_KEY（生产随机密钥）
    → 需配置真实 SEEDANCE_API_KEY / LUMA_API_KEY
    → 可选启用 ENABLE_BLENDER_EXPORT

Blender MCP（可选）:
    bash blender/start_blender_mcp.sh
    → 启动 Blender + blender_agent.py
    → JSON-RPC MCP 协议
    → 实时 3D 场景操控

数据迁移:
    python3 scripts/init_db.py          # 初始化数据库 + 目录
    python3 scripts/migrate_data.py     # knowledge_base.json → SQLite 表
```

---

## 十二、文件统计

| 类别 | 文件数 | 总行数（约） |
|------|--------|-------------|
| Python 后端 | 22 | ~5,500 |
| JavaScript 前端 | 6 | ~6,800 |
| HTML 页面 | 7 | ~1,500 |
| CSS 样式 | 1 | ~5,200 |
| Blender 脚本 | 3 | ~500 |
| 配置/脚本文档 | 7 | ~1,000 |
| 数据文件 | 1（JSON） | ~3,000 |
| **合计** | **~47** | **~23,500** |

---

*文档基于 AIGV Studio 代码实际分析生成*
*最后更新: 2026-07-23*

---

# 附录：生产化改造更新（2026-10-29）

> 本节记录当前代码的实际架构。若前文与本节冲突，以本节和代码为准。

## A. 认证与全站访问控制

- 登录账户唯一来源为 SQLite `auth_users`（`backend/auth_service.py`）。`users.json` 只在 `scripts/migrate_auth_v2.py` 中一次性迁移，运行时不再作为认证回退。
- `auth_users` 关键字段：`role`（admin/user）、`status`（active/disabled）、`session_version`、`failed_login_count`、`locked_until`、`last_login_at`、`nickname`、`avatar_path`、`bio`、`tenant_id`、`user_id`。变更通过 `database.py` 的增量 `_ensure_column` 完成，不清空旧数据。
- `backend/identity_service.py` 在注册事务内创建平台租户、业务 `users` 行、个人工作区 `workspace_<uid>` 与 owner 成员关系。项目角色与平台角色严格分离。
- `backend/web_security.py` 是统一入口：
  - 公开白名单仅登录/注册/状态/CSRF/健康检查与静态 JS/CSS/媒体；
  - 未登录 API → 401 JSON，页面 → 302 `/login?next=`；
  - 先鉴权后 CSRF；登录/注册仍受 CSRF 保护；
  - `/web/*.html` 直接 404；`/admin*` 需平台管理员；`/compute-platform*` 需 `view_compute`；
  - Cookie `HttpOnly`、`SameSite=Lax`、生产 `Secure`；生产强制稳定 `SECRET_KEY`。
- 会话每次请求重新读取数据库并校验 `session_version`、状态与锁定；改密/改角色/禁用/撤销会话立即失效。
- 个人中心：`backend/profile_routes.py` + `web/profile.html/js`；管理员：`backend/admin_routes.py` + `web/admin-users.html/js`（用户分页/搜索/筛选、角色、状态、会话撤销、统计、审计、全平台生成任务）。
- 登录/注册的 `next` 由服务端 `safe_redirect_target()` 清洗；管理员初始化使用 `scripts/create_admin.py`，无硬编码密码。

## B. 真实生成任务架构

新链路（创意工作台与独立生成 API 共用）：

```
create_generation_task()
  → generation_tasks(queued)
  → GenerationWorker.claim_generation_submission()  [BEGIN IMMEDIATE + 租约]
  → Provider.submit() → provider_job_id, running
  → GenerationWorker.claim_generation_poll() → Provider.get_status()
  → 下载临时 URL 到 data/assets/generated/<user>/<task>/
  → 单事务：任务结果 + assets + task_artifacts + 分镜关联
```

- 表：`generation_tasks` 在原有基础上增加 `provider`、`model_id`、`provider_job_id`、`provider_status`、`attempt_count`、`next_retry_at`、`lease_owner/lease_expires_at`、`submission_uncertain`、`poll_error_count`、`output_asset_id`、`client_request_id`、`cancel_requested`、`target_asset_id` 等字段；唯一幂等索引 `(created_by, client_request_id)`。
- 原子性：任务领取/租约使用 SQLite `BEGIN IMMEDIATE` 与条件 UPDATE；多 Worker 不会重复领取。配额检查与任务插入在同一事务内。
- 可恢复：Worker 重启后清理过期租约，`submitting` 且无第三方 ID 的任务转 `needs_review`；有 `provider_job_id` 的任务恢复轮询。
- 截止时间：`GENERATION_IMAGE_DEADLINE_S` / `GENERATION_VIDEO_DEADLINE_S`；超时 `task_timeout`，保留第三方 ID 供管理员恢复。
- 结果安全：`backend/media_fetcher.py` 校验 http/https、公网 DNS、端口、重定向、内容类型、魔数与大小上限；临时签名 URL 立即转存本地。
- 序列化：`backend/task_serializer.py` 统一剔除 `provider_job_id/lease_owner/client_request_id` 等内部字段。
- 引用完整性：参考图写入 `target_asset_id` 并阻止排队期间删除；删除生成作品时，仅清理自身 artifact/任务输出指针，仍被分镜/时间线引用时返回 409。

## C. Provider 抽象

- `backend/generation_models.py`：服务端模型注册表与能力矩阵（尺寸/比例/时长/分辨率/音频/种子/参考图/取消），模型 ID 可由环境变量覆盖，未配置模型返回 `available=false` 与原因。
- `backend/providers/volcengine_image.py`：方舟 Seedream 同步接口。
- `backend/providers/volcengine_video.py`：方舟 Seedance 异步任务（创建/查询/取消）。
- `backend/providers/image_provider.py`：ComfyUI，已改为异步（提交 `prompt_id`，轮询 history 后下载），文件名不可信、内容做魔数校验。
- `backend/providers/seedance.py`、`luma.py`：旧 Atlas/Luma 适配，超时映射为 `ProviderUncertain`，不自动重复扣费。
- `backend/providers/mock_provider.py`：仅测试使用，生产注册表不包含。

## D. 前端结构更新

- 统一请求层 `web/api-client.js`：CSRF 预热/重试、401 跳转登录、统一错误对象、用户与 `capabilities` 缓存。
- `web/session-nav.js`：头像/昵称菜单、个人中心、管理员入口、退出；根据 `view_compute` 隐藏算力入口；演示模式标识。
- 新增 `web/profile.html/js`、`web/admin-users.html/js`、`web/403.html`。
- 创意工作台：项目/分镜/任务全部走后端 API；分镜编辑/复制/删除/排序、保存项目、图生图参考图、模型能力驱动的参数、真实预览/参数、任务 ID 与项目 ID 持久化、刷新恢复轮询、取消状态处理。
- 素材库新增“生成历史”Tab：类型/状态/日期筛选、分页、图片/视频预览、下载、参数、取消、删除、重新生成、“用此图生成视频”。
- 算力平台：权限页改为真实项目成员只读展示；演示数据仅在 `DEMO_MODE` 使用并标注；会话/节点/链路空状态；网络时延优先真实监控数据。

## E. 部署架构

```
Browser → Nginx/HTTPS → Gunicorn (wsgi:app, 多 worker)
                          │
                          ├── SQLite data/aigv.db
                          ├── data/assets（本地素材）
                          └── 独立进程 scripts/run_generation_worker.py
                                  ├── Ark Seedream / Seedance
                                  ├── ComfyUI（可选）
                                  └── Atlas / Luma（旧通道，可选）
```

- 生产 `START_TASK_WORKER=false`，生成 Worker 独立运行；样例见 `deploy/`。
- `scripts/backup_data.py` 使用 SQLite backup API 生成一致性备份，不复制 `.env`。
- 演示数据 `DEMO_MODE=false` 默认关闭；演示模式仍只用于明确标注的视觉模块。

## F. 验证状态

- 自动化：`python3 -m pytest tests/`（当前全量通过；具体数字见交付报告）。
- 真实 Ark/ComfyUI/Atlas/Luma 调用**未验证**（未使用付费密钥）；详见 `docs/AI-Provider-Integration.md`。
- 未在本机之外的服务器执行部署；`deploy/` 为可执行样例，不代表已上线。

---

# 附录 G：真实媒体后期工作流（2026-10-30）

> 本节记录第 04–06 步从本地演示升级为真实后端的实现；与 `docs/Media-Workflow.md` 配套。

## G.1 新增后端服务

- `backend/tts_service.py`：Piper 音色注册表（`data/tts_voices.json`），路径限制在 `TTS_MODEL_DIR`，只暴露可用音色与能力。
- `backend/providers/tts_provider.py`：真实 Piper 合成 + FFprobe 校验 + FFmpeg `atempo`/`volume` 后处理；失败不生成假音频。
- `backend/timeline_service.py`：时间线自动初始化、真实时长探测、事务保存、版本冲突、素材/分镜校验、SRT 生成。
- `backend/media_filters.py`：精修滤镜白名单与范围校验。
- `backend/media_service.py`：`compose_timeline()` 单 FFmpeg 图合成视频/配音/音乐/音效/字幕，`verify_output()` 做流/尺寸/帧率/时长/完整解码校验。
- `backend/http_session.py`：线程局部 requests Session，供结果下载复用。

## G.2 新增/扩展表

`shot_media_versions`（分镜视频/音频/字幕历史）、`creative_projects.timeline_version/final_*`、`storyboard_shots.selected_video_asset_id/refined_video_asset_id/subtitle_asset_id/audio_options/audio_duration_s`、`timeline_tracks.role`、`timeline_clips.volume/muted/source_audio_enabled/fade_in/fade_out/subtitle_text`、`generation_tasks.timeline_version/timeline_snapshot` 与阶段计时字段、`export_packages.asset_id/timeline_version`。迁移版本 2–5，可重复执行；旧数据不删除。

## G.3 任务与合成

- `compose` 任务在创建时保存完整 `timeline_snapshot`，运行期间用户修改时间线不影响该任务。
- 输出写入 `data/assets/videos/composed/<task_id>/final_video.mp4`，先写 `.part.mp4` 再原子替换，FFprobe + 解码校验通过后才创建资产/更新 `final_video_asset_id`。
- 旁白/音乐/音效真实混入 MP4；无音频输入时生成静音 AAC 轨；字幕支持 none/mov_text/burn。
- 精修生成独立视频资产与版本行，不覆盖原始 AI 视频；`video-selection` 选择版本并同步时间线 clip/版本号。

## G.4 前端

- 第 04 步：真实音色下拉、每镜头配音试听/下载/历史/使用/无配音、音乐/音效上传与试听、可编辑多轨时间线（起点/时长/入点/音量/淡入淡出/字幕文本/静音/删除，800ms 防抖保存、409 冲突提示）。
- 第 05 步：真实双视频播放器（同源 + CSS 快速预览）、真实滤镜、精修版本列表与“用于成片/恢复原始版”。
- 第 06 步：真实导出参数、MP4 合成进度、成片播放/下载、字幕下载、ZIP 素材包下载；刷新/重登后从 `/workflow` 恢复。
- `pollTask` 自适应轮询、`AbortController`、项目守卫、页面隐藏降频；持久容器监听器改为一次绑定。

## G.5 验证状态

- 全量自动化测试通过（见交付报告）。
- 本机真实 Piper 中文音色 + 真实 FFmpeg 的 E2E 已通过：TTS → 时间线 → 烧录字幕 MP4 → ZIP 下载。
- 真实付费 LLM/图片/视频调用未新增；本地验证不触发计费。
- 线上数据库迁移与进程重载只在隔离验收通过后执行；未执行前不得写成已上线。
