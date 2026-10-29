# AIGV Studio 真实可用性优化设计

日期：2026-10-30
状态：待评审
范围：API 配置平台、素材库 3D 预览、素材编辑、素材筛选

## 1. 背景与意图

平台目前只能靠服务端环境变量配置 AI 模型，普通用户无法使用自己的图片、视频、大模型密钥。同时，生成/分析 worker 没有运行，LLM 分析还存在代码级阻断；素材库的 3D 预览、编辑和筛选也不足以支撑真实使用。

本次目标不是做演示功能，而是让**登录后的真实用户能够配置自己的 API、真正生成图片/视频、真正运行 LLM 分镜分析，并顺畅管理素材**。

## 2. 已确定的产品决定

1. API 配置首批接入：现有通道（火山方舟 Seedream/Seedance、Atlas Seedance、Luma、ComfyUI）+ OpenAI 兼容 LLM + OpenAI Images。
2. 素材编辑范围：名称、描述、场馆、可见性（私有/共享）；**不替换文件**。
3. 时间筛选形态：日期范围 + 快捷预设（今天/近 7 天/近 30 天/全部）+ 排序。
4. 超大 3D 模型：点击后再加载 + 长缓存 + 自托管并锁定 model-viewer；不做服务端压缩/缩略图。

### 评审决议（2026-10-30）

设计评审发现并确定了以下 6 点，均已在后文落实：

1. **平台密钥不得发往用户自定义地址**：用户覆盖 `base_url` 且该地址与平台默认地址不同时，必须同时提供用户自己的密钥；否则拒绝保存/使用。平台密钥只与平台 Base URL 成对使用。
2. **shared 的读取语义**：同一租户内可读；`tenant_id IS NULL` 的历史共享素材视为全局共享。修复 `can_read_asset` 当前“有 owner 的 shared 素材返回 False”的缺陷；列表/计数增加租户过滤。素材文件缓存改为 `private, max-age=86400`，不做一年 immutable，避免可见性收回后长期滞留。
3. **OpenAI Images 必须进入模型注册表**：新增 `openai_gpt_image_1` 模型项与 `_provider_for_task` 分支，否则配置了也永远不可选。
4. **单模型字段显式化**：`provider_credentials` 增加 `model` 列；单模型 provider 用 `model`，Ark 用 `model_overrides`。PUT 的字段省略/清空语义在 6.1.5 明确。
5. **移除本地 Ollama 预设**：本期只允许公网 HTTPS 端点，不支持私网/HTTP/无密钥 LLM。
6. **任务凭据快照与编辑锁**：任务创建时快照 `credential_source`；用户在该 provider 存在 queued/submitting/running 任务时，禁止修改/删除该凭据（409），避免轮询中的付费任务失去账号或切换 Base URL。

## 3. 目标

### G1. 用户级 API 配置平台
- 用户可在 `/api-settings` 为 LLM、火山方舟、OpenAI Images、Atlas、Luma 保存自己的凭据。
- 密钥加密存储、只显示掩码、永不回传明文、永不写日志。
- 用户凭据优先于平台环境变量；用户未配置时回退平台默认。
- 图片/视频/LLM 分析链路真正读取用户凭据。
- 提供各协议的默认 Base URL、模型 ID 和常见服务商预设。
- 修复 `task_worker.py` 的 `CreativeProject` 未导入问题；启动 worker，任务不再卡在 queued。

### G2. 3D 预览
- 首屏不自动下载几十 MB 模型；大模型点击后加载，小模型进入视口后自动加载。
- 素材文件使用长缓存，切 Tab/搜索/翻页不重复下载。
- 明确区分可预览格式与仅下载格式，不再出现空白 model-viewer。
- 加载中、失败、超时有可见反馈。

### G3. 素材编辑
- 卡片增加“编辑”，可改名称、描述、场馆、私有/共享。
- 只有 owner/admin 可编辑；共享素材对非 owner 隐藏编辑入口。
- 后端更新接口有校验、错误映射和审计。

### G4. 素材筛选
- 修复 Tab 快速切换时“文档 Tab 显示图片”的竞态。
- 增加“全部”素材入口。
- 素材库支持时间范围、快捷预设和排序；生成历史的日期筛选增加校验、预设和排序。
- 日期按服务器本地时区解释，避免 UTC 导致的 8 小时偏移。

## 4. 非目标

- 不做 Anthropic / Gemini 原生协议（本期只做 OpenAI 兼容 LLM）。
- 不做用户级 ComfyUI 地址（避免 SSRF）；ComfyUI 继续由平台环境变量控制，配置页只展示状态。
- 不支持本地 Ollama、私网 LLM、HTTP 端点或无密钥 LLM；本期只允许公网 HTTPS。
- 不做素材文件替换、版本历史、标签、license 编辑。
- 不做服务端 3D 减面/贴图压缩/缩略图生成，不安装 Blender。
- 不做“测试连接即真实生成”的付费探测；测试只做可达性/鉴权可验证范围内的检查。
- 不改动算力调度、计费、监控等既有模块。

## 5. 约束

- Python 3.10 + Flask + Vanilla JS SPA + SQLite；无前端构建工具。
- 当前生产进程为单进程 `.venv/bin/python -u app.py`，`.env` 为 development。
- 所有 `/api/*` 默认 `no-store`，需要为素材文件单独豁免。
- 数据库迁移必须幂等，不能重建既有表。
- 现有测试必须继续通过；新增功能必须有后端测试。
- 用户密钥只允许 owner 使用；不得进入审计元数据、异常消息或前端 DOM。

## 6. 详细设计

### 6.1 API 配置平台

#### 6.1.1 数据模型

新增表 `provider_credentials`（在 `backend/database.py` 的 `init_database` 中用 `CREATE TABLE IF NOT EXISTS` 创建）：

```sql
CREATE TABLE IF NOT EXISTS provider_credentials (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  tenant_id TEXT,
  provider TEXT NOT NULL,          -- llm | ark | openai_image | atlas_seedance | luma
  base_url TEXT,
  model TEXT,                      -- 单模型 provider 的模型 ID
  api_key_ciphertext TEXT,
  model_overrides TEXT,            -- JSON: registry model_key -> model_id（Ark）
  is_active INTEGER DEFAULT 1,
  last_verified_at INTEGER,
  created_at INTEGER,
  updated_at INTEGER,
  UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_provider_credentials_user
  ON provider_credentials(user_id);
```

约束：
- 一个用户每个 provider 只有一条记录；再次保存为 upsert。
- `api_key_ciphertext` 为空表示“未提供用户密钥”；此时**不得**同时覆盖 `base_url` 为平台地址之外的地址（见 6.1.4 安全规则）。
- `model` 用于 `llm`/`openai_image`/`atlas_seedance`/`luma`；`model_overrides` 只用于 `ark`。
- ComfyUI 不进入此表。

#### 6.1.2 加密

新增 `backend/credential_service.py`：

- 使用 `cryptography.fernet.Fernet`（新依赖 `cryptography`，加入 `requirements.txt`）。
- 密钥来源：环境变量 `CREDENTIAL_ENCRYPTION_KEY`；未设置时由 `cfg.SECRET_KEY` 经 SHA-256 派生 `urlsafe_b64` Fernet key。
- 密文格式 `v1:<fernet token>`，便于未来轮换。
- 解密失败（例如 SECRET_KEY 轮换）时视为该凭据无效：记录 warning（不含密钥）、返回未配置原因，不抛 500。
- 公开序列化只返回：`provider`、`base_url`、`model`、`model_overrides`、`has_key`、`key_last4`、`source`、`last_verified_at`、`updated_at`。永不含 `api_key`/密文。

#### 6.1.3 Provider 目录与预设

`PROVIDER_CATALOG`（后端常量，同时通过接口提供给前端）：

| provider | 名称 | 协议 | 字段 | 默认 Base URL |
|---|---|---|---|---|
| `llm` | 大语言模型 | OpenAI 兼容 `/chat/completions` | api_key, base_url, model | `https://api.openai.com/v1` |
| `ark` | 火山方舟 | `/images/generations`, `/contents/generations/tasks` | api_key, base_url, model_overrides | `https://ark.cn-beijing.volces.com/api/v3` |
| `openai_image` | OpenAI 图片 | `/images/generations` | api_key, base_url, model | `https://api.openai.com/v1` |
| `atlas_seedance` | Atlas Cloud Seedance | 旧兼容协议 | api_key, base_url, model | `https://api.atlascloud.ai/api/v1` |
| `luma` | Luma Dream Machine | Luma v1 | api_key, base_url, model | `https://api.lumalabs.ai/dream-machine/v1` |

LLM 预设（只填 Base URL/模型，不填密钥）：OpenAI、DeepSeek、通义千问 DashScope 兼容模式、Moonshot/Kimi、智谱。**本期不提供本地 Ollama/私网端点预设**（见 6.1.7）。

Ark 的 `model_overrides` 以模型注册表的 key 为键：`ark_seedream_pro`、`ark_seedream_lite`、`ark_seedance_25`、`ark_seedance_20`、`ark_seedance_10_pro`。配置页提供“常用模型”输入，高级项可折叠。

#### 6.1.4 凭据解析与优先级

`credential_service` 提供：

- `effective(user_id, provider, cfg)` → `{api_key, base_url, model, model_overrides, source}`。
  - 用户有 active 记录且密钥可解密/非空 → `source='user'`，使用用户 base_url/model。
  - 用户记录无密钥、且 base_url 为空或等于平台 Base URL → 密钥回退平台，`source='platform'`；模型覆盖仍生效。
  - **安全规则**：用户 base_url 非空且与平台 Base URL 不同时，必须有用户密钥；否则保存直接 400 `user_key_required`，运行时也拒绝构造 provider。平台密钥永远不会发往用户指定的不同主机。
  - 无用户记录 → 全部回退平台，`source='platform'`（若平台也未配置则 `source=None`）。
  - 用户显式配置了密钥但鉴权失败时**不回退平台**，直接失败，避免账单归属混乱。
- `placeholder` 检测：空字符串、`placeholder`、`your_api_key`、`changeme` 一律视为未配置。
- `has_llm(user_id, cfg)`、`has_provider(user_id, model_provider, cfg)` 供路由和模型列表使用。

provider → 平台配置映射：

| provider | 平台密钥 | 平台 Base URL | 平台模型 |
|---|---|---|---|
| llm | `LLM_API_KEY` | `LLM_BASE_URL` | `LLM_MODEL_NAME` |
| ark | `ARK_API_KEY` | `ARK_BASE_URL` | `ARK_IMAGE_MODEL*` / `ARK_VIDEO_MODEL*` |
| openai_image | `OPENAI_API_KEY`（新增） | `OPENAI_BASE_URL`（新增） | `OPENAI_IMAGE_MODEL`（新增） |
| atlas_seedance | `SEEDANCE_API_KEY` | `SEEDANCE_BASE_URL` | `SEEDANCE_MODEL_NAME` |
| luma | `LUMA_API_KEY` | `LUMA_BASE_URL` | `LUMA_MODEL_NAME` |

#### 6.1.5 接口

全部要求登录 + CSRF：

- `GET /api/user/provider-credentials`
  - 返回 `{items: [...], catalog: [...]}`；每项含掩码字段、`source`、平台是否可用。
- `PUT /api/user/provider-credentials/<provider>`
  - body：`api_key?`、`base_url?`、`model?`、`model_overrides?`、`is_active?`、`clear_key?`。
  - `api_key` 省略或空字符串 = 保留现有密钥；显式 `clear_key: true` = 删除密钥。
  - `base_url` 省略 = 保留现值；显式空字符串 = 清除覆盖，回退平台 Base URL；非空时通过 SSRF 校验。
  - `model` 省略 = 保留现值；显式空字符串 = 回退平台模型。
  - `model_overrides` 省略 = 保留现值；显式 `{}` = 清除覆盖。
  - 校验 provider 属于目录、SSRF 规则、`model_overrides` 是字符串字典；若 base_url 与平台不同且无用户密钥 → 400。
  - 若该用户在该 provider 存在 queued/submitting/running 任务 → 409 `active_tasks`，要求等任务结束或取消后再改。
  - 返回掩码后的记录。
- `DELETE /api/user/provider-credentials/<provider>`：删除用户覆盖，回退平台默认；存在该 provider 的 queued/submitting/running 任务时返回 409。
- `POST /api/user/provider-credentials/<provider>/test`
  - LLM：优先 `GET {base_url}/models`；不支持时返回 `reachable=true, verified=false`，说明“端点可达，未发起计费调用”。
  - 其他 provider：做 DNS/TLS/HTTP 可达性检查，不发起生成请求；返回 `verified=false` 并说明原因。
  - 不记录、不回传密钥。

审计：`provider_credential_update`、`provider_credential_delete`、`provider_credential_test`，metadata 只含 provider/base_url/host，不含密钥。

#### 6.1.6 生成与分析链路接入

1. `backend/generation_models.py`
   - `get_model(cfg, key, user=None)`、`list_models(cfg, task_type=None, user=None)`。
   - `_availability` 改用 `credential_service.has_provider(...)`，返回 `unavailable_reason` 指向配置页。
   - 模型条目增加 `credential_source`（user/platform/none）。
   - 新增图片模型项 `openai_gpt_image_1`：provider `openai_image`，model_id 取 `OPENAI_IMAGE_MODEL`（默认 `gpt-image-1`），task_type `image`；capabilities 使用 `sizes=["1K","1.5K"]`、`default_size="1K"`、`default_ratio="1:1"`、`supports_custom_size=true`、`supports_reference_image=false`、`supports_watermark=false`、`supports_seed=false`。1K 方形解析为 1024×1024，1.5K 横/竖为 1536×1024 / 1024×1536。
2. `backend/generation_routes.py`
   - `/api/generation/models` 传入 `g.current_user`。
   - 创建任务前确认该模型可用；错误 `provider_not_configured` 附带 `details.configure_url='/api-settings'`。
3. `backend/generation_service.py`
   - `_provider_for_task(cfg, task)` 用 `task.created_by` 与任务 params 里的 `credential_source` 解析凭据，按 provider 实例化：
     - ark：用户/平台 key + base_url；模型用任务已存的 `task.model_id`。
     - openai_image：新增 `OpenAIImageProvider`。
     - atlas/luma：同上。
     - comfyui：仅平台配置。
   - 任务创建时把用户 `model`/`model_overrides` 应用到 `task.model_id`，并写入 `params.credential_source`（user/platform），保证排队/轮询期间不受用户后续配置影响。
   - 提交和轮询都必须通过同一凭据来源；若该来源已不可用，任务失败并给出 `provider_credential_missing`，不静默改用其他账号。
4. `backend/providers/openai_image.py`（新增）
   - `POST {base_url}/images/generations`，Bearer 鉴权。
   - 处理 401/403/429/5xx 和超时，错误类型与现有 provider 对齐。
   - 不支持参考图（MVP）；`response_format` 优先 `b64_json`，兼容 `url`。
   - 把生成服务传入的 width/height 归一到 OpenAI 支持的三档尺寸：横图 `1536x1024`、竖图 `1024x1536`、方图 `1024x1024`；不支持的比例在创建任务前由 capabilities 拦截。
   - `generation_service.submit_task` 增加 `task.provider == "openai_image"` 分支，复用现有 `provider.generate(...)` + `_download_image_items` 流程。
   - 新增配置项：`OPENAI_API_KEY`、`OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`）、`OPENAI_IMAGE_MODEL`（默认 `gpt-image-1`），同步 `.env.example`。
5. LLM 分析
   - 修复 `backend/task_worker.py` 导入：把 `CreativeProject` 加入 `.models` 导入。
   - `_execute_storyboard` 用 `task.created_by` 解析 LLM 凭据（用户优先、平台回退），再实例化 `LLMProvider`。
   - `backend/creative_routes.py` 的 analyze 前置检查改为 `credential_service.has_llm(user_id, cfg)`。
6. Worker
   - `.env` 增加 `START_TASK_WORKER=true`（当前单进程 Flask 部署）。
   - 若未来改为多 worker gunicorn，必须改用 `scripts/run_worker.py` + `scripts/run_generation_worker.py` 独立进程；写入部署文档。

#### 6.1.7 SSRF 与安全

- `validate_provider_base_url`：
  - 只允许 `https`；`http` 仅当 `ALLOW_INSECURE_PROVIDER_URLS=true`（默认 false）。
  - 拒绝 userinfo、fragment、非 http(s) scheme。
  - DNS 解析后拒绝 loopback/private/link-local/reserved/multicast 地址。
  - 保存时校验一次，实际请求前再解析一次（降低 DNS rebinding 风险；残余风险在文档中说明）。
  - **当用户 base_url 与平台 Base URL 不同时，必须提供用户密钥**；否则拒绝，防止平台密钥被发往用户控制的主机。
  - 本期不支持本地 Ollama / 私网 LLM / HTTP 端点；无密钥 LLM 端点也不支持。
- 所有凭据接口按 `g.current_user.id` 隔离，不提供跨用户读取。
- 请求体不写日志；异常消息截断且不含 Authorization。
- 前端密码框输入，保存后只显示 `••••1234`；不再展示明文。
- 配置页提示：密钥仅加密存储于本平台，请使用可撤销的子账号 Key。

#### 6.1.8 前端

- 新页面 `/api-settings`（`web/api-settings.html`、`web/api-settings.js`），复用 `styles.css` 的 profile-card/form-group/btn 样式，新增 provider 卡片与状态徽章样式。
- 用户菜单（`web/session-nav.js`）增加“API 配置”；个人中心增加入口卡片。
- 每张 provider 卡片：
  - 状态：`使用个人配置` / `使用平台默认` / `未配置`。
  - Base URL、API Key（password，占位显示掩码）、模型/高级模型覆盖。
  - 保存、测试连接、删除个人配置。
  - “获取密钥”文档链接与协议说明。
- LLM 卡片提供预设下拉，选择后填充 base_url/model。
- 创意生产页（`web/creative-studio.js`）在 `provider_not_configured`、模型不可用提示中加入“去配置 API”链接。
- 保存成功/失败用现有 toast 或页面消息；401 由 api-client 统一跳登录。

#### 6.1.9 测试

- 加密/解密、掩码、SECRET_KEY 轮换后的降级。
- 用户隔离：A 不能看到/使用 B 的凭据。
- placeholder 视为未配置。
- 用户 key 优先、平台回退、用户 key 失败不回退。
- 模型可用性随用户凭据变化。
- Provider 工厂使用对应用户凭据（mock provider，不发真实请求）。
- LLM 分析任务可解析用户凭据；`CreativeProject` 导入回归测试。
- 配置 API 的 CSRF、校验、SSRF 拒绝（localhost/http/私网）。
- 自定义 base_url 无用户密钥时拒绝保存；平台密钥不会被发往自定义主机。
- 用户存在 queued/submitting/running 任务时，修改/删除该 provider 凭据返回 409；任务 params 中 `credential_source` 在提交后保持不变。
- OpenAI Images 模型出现在 `/api/generation/models`，且 provider 工厂能构造 `OpenAIImageProvider`。

### 6.2 3D 预览

#### 6.2.1 根因

1. 首屏 3 个 GLB 合计约 118MiB；model-viewer 进入视口才加载，两个大模型各 54/66MB、8K 贴图、约 86–100 万面。
2. `/api/*` 全局 `Cache-Control: no-store`，每次重渲染重新下载。
3. 上传允许 OBJ/FBX/STL 等，但统一归为 `glb` 并交给 model-viewer，必然空白。
4. model-viewer 从 unpkg 加载且未锁版本，CDN 不稳定会全站失效。
5. 无进度/错误/超时反馈，进度条被 CSS `all: unset` 清掉。

#### 6.2.2 后端

- `backend/web_security.py` 的 `after_request`：
  - 对 `GET /api/assets/<id>/file` 和 `/download` 不写 `no-store`。
  - 设置 `Cache-Control: private, max-age=86400`（1 天；配合 checksum 查询参数）。不使用一年期 `immutable`，确保私有/共享可见性变更后最多 1 天生效。
  - 其余 `/api/*` 保持 `no-store`。
- `backend/asset_service.py`：
  - `public_dict` 增加 `file_ext`、`previewable`（仅 `.glb` 且 GLB magic 正确为 true）、`preview_reason`。
  - `file_url` 追加 `?v=<checksum_sha256 前 12 位>`，保证缓存失效可控。
  - 上传 `.glb` 时校验前 4 字节为 `glTF`；`.gltf` 因只保存单文件、外部 bin/纹理会失效，标记不可预览；OBJ/FBX/STL 等同样标记为仅下载。
  - 不改变上传白名单，避免破坏既有用户流程。
- `thumbnail_url` 保持现状（本期不生成缩略图），前端使用本地图标占位。

#### 6.2.3 前端

- 自托管 model-viewer 4.4.0：`web/vendor/model-viewer/model-viewer.min.js` + LICENSE；`assets.html` 改为本地 `<script type="module">`，移除 unpkg preconnect/CDN。
- 卡片渲染：
  - `previewable=false`：显示格式图标 + “该格式不支持在线预览，请下载查看”，不创建 model-viewer。
  - `previewable=true` 且 `file_size <= AUTO_PREVIEW_MAX_BYTES`（默认 8MB）：进入视口后自动创建 model-viewer。
  - 大模型：显示占位面板（模型图标、文件大小、“点击加载 3D 预览”）。点击后才设置 `src`，避免首屏下载 120MB。
- 加载反馈：
  - 监听 `progress` 显示百分比；`load` 隐藏遮罩；`error` 显示“预览加载失败，点击重试/下载”；90 秒未完成显示超时提示。
  - 移除 `model-viewer::part(default-progress-bar) { all: unset; }`。
- 重渲染时保留已加载状态：用 `loadedPreviewAssetIds` 集合记录已加载模型，重新渲染时对已加载的小模型直接创建（命中 HTTP 缓存），大模型保持点击加载；避免内存泄漏由元素移除自然处理。
- 卡片操作区同时增加编辑按钮（见 6.3）。

#### 6.2.4 测试

- 响应头：素材文件返回长缓存且保留 ETag/Range；JSON API 仍为 no-store。
- `public_dict.previewable`：GLB magic 正确为 true；伪造 GLB、OBJ、FBX 为 false。
- 上传伪造 `.glb` 返回 400。
- Playwright：首屏无模型文件请求；点击后请求一次；再次切 Tab 不再走网络（或命中缓存）。

### 6.3 素材编辑

#### 6.3.1 后端

**共享与租户语义（评审新增，必须先修）**

- `can_read_asset` 改为：admin 可读；owner 可读；`visibility == 'shared'` 且（`asset.tenant_id IS NULL` 或等于当前用户 `tenant_id`）可读；历史无主 shared 素材保持全局可读。
- `list_assets` / `count_assets` 的非 admin 条件改为：`owner_user_id = ?` 或 `(visibility='shared' AND (tenant_id = ? OR tenant_id IS NULL))` 或 `owner_user_id IS NULL`；路由传入当前用户 tenant_id。
- 把可见性改为 private 后，新的列表/详情/文件请求立即拒绝；浏览器已缓存文件最多保留 1 天（见 6.2.2）。
- shared 只影响读取，不授予编辑权限；编辑仍仅 owner/admin。

- `app.py` PUT `/api/assets/<id>`：
  - 用 try/except 捕获 `AssetServiceError` → 400 `invalid_asset_update`。
  - 校验 `name`：非空字符串、≤120 字符；`description` ≤2000；`venue_type` 沿用服务校验。
  - `AssetService._UPDATE_FIELDS` 增加 `visibility`，只允许 `private`/`shared`。
  - 写审计 `asset_update`，metadata 记录变更字段名（不记录内容）。
- `public_dict` / 列表项增加 `can_edit`：`can_write_asset(asset, viewer)`；详情接口同样。
- 非 owner 对共享素材仍不可写。

#### 6.3.2 前端

- `assets.html` 新增编辑弹窗（名称、场馆、描述、可见性；类型和文件只读展示）。
- `assets.js`：
  - 卡片操作区增加“编辑”按钮（铅笔图标）。
  - 点击从当前页数据回填；提交 `PUT /api/assets/<id>` JSON。
  - 成功后关闭、toast、`loadAssets()+loadSummary()`；403/400 显示后端消息。
  - `can_edit=false` 时隐藏按钮或禁用并提示“共享素材仅所有者可编辑”。
  - 卡片显示上传时间（`created_at` 格式化）。
- 复用现有 modal/toast 样式，避免新增框架。

#### 6.3.3 测试

- PUT 成功更新 name/description/venue/visibility。
- 非 owner 403；不存在 404；非法 venue 400；非法 visibility 400；空 name 400；非 dict metadata 400。
- `can_edit` 在列表/详情中正确。
- 同租户用户可读取 owner 的 shared 素材（列表 + detail + file/download）；不同租户不可读；改回 private 后不可读。
- shared 素材的非 owner 编辑仍 403。

### 6.4 素材筛选

#### 6.4.1 竞态修复

`web/assets.js`：

- 移除“`isLoading` 为真就直接 return”的全局丢弃逻辑。
- 引入 `loadSeq`：每次 load 递增，响应回来只有 `seq === loadSeq` 才渲染；旧响应直接丢弃。
- 使用 `AbortController` 取消上一请求（可选，但推荐）。
- Tab 切换、搜索、场馆、时间、排序、分页统一走 `requestAssets()`，避免 150ms 定时器叠加。
- 保留骨架屏，仅对最新请求显示。

#### 6.4.2 类型筛选

- 保留现有类型 Tab（3D/图片/视频/音频/文档/压缩包/Prompt/历史）。
- 增加“全部”Tab：`asset_type` 为空，调用 `/api/assets` 返回全部类型（含 badge）。
- 修复 6.4.1 竞态后，Tab 与内容保持一致；浏览器实测“文档 Tab 显示图片”问题消失。
- 不新增重复的“类型下拉”，避免两套控件状态不同步。

#### 6.4.3 时间与排序

后端：

- `/api/assets` 新增 `created_after`、`created_before`、`sort` 参数。
- `asset_service.list_assets/count_assets` 支持时间条件；`sort` 白名单：
  - `newest`（默认，`created_at DESC`）
  - `oldest`（`created_at ASC`）
  - `name`（`name COLLATE NOCASE ASC`）
- `/api/generation/tasks` 的 `_parse_date` 改为按服务器本地时区解释日期（去掉 `tzinfo=timezone.utc`），并新增 `sort` 支持。
- 日期参数接受 `YYYY-MM-DD` 或 Unix 时间戳；非法格式 400。
- 校验 `created_after <= created_before`；前端也做同样校验。

前端（素材 Tab 共用工具栏）：

- 新增控件：快捷时间下拉（全部时间/今天/近 7 天/近 30 天/自定义）、起止日期、排序下拉（最新/最早/名称）、清除筛选按钮。
- 快捷预设按浏览器本地日期生成 `YYYY-MM-DD`；自定义时显示日期输入。
- 切换 Tab 保留时间/排序/搜索/场馆状态；场馆筛选仅对 3D/图片/全部可见。
- 生成历史 Tab：复用预设与校验，保留类型/状态筛选，增加排序（最新/最早）。
- 所有筛选变更重置到第 1 页。
- 空结果展示“没有符合条件的素材”，并提供清除筛选按钮。

#### 6.4.4 测试

- 后端时间过滤边界：当天 00:00:00–23:59:59、跨天、非法日期、after>before。
- 排序白名单与注入尝试。
- Playwright 竞态回归：延迟图片请求后快速切到文档，最终标签与内容一致。
- 快捷预设生成的日期正确。

## 7. 数据库与部署

### 7.1 迁移

- `init_database` 新增 `provider_credentials` 表与索引；幂等。
- 不修改既有表结构。
- 上线前备份 `data/aigv.db`（`scripts/backup_data.py` 或 `cp`）。
- 老库启动时自动建表。

### 7.2 依赖

- `requirements.txt` 增加 `cryptography>=42,<47`（以 Python 3.10 可安装为准）。
- 安装到 `.venv`；当前 venv 为 Python 3.10.12。

### 7.3 Worker

- 当前单进程部署：`.env` 设置 `START_TASK_WORKER=true`，重启 Web 进程后同进程启动 `TaskWorker` 与 `GenerationWorker`。
- 文档注明：若改 gunicorn 多进程，必须关闭 Web 进程内 worker，改用独立 worker 进程。

### 7.4 3D 资源

- 下载并提交 `@google/model-viewer@4.4.0` 的 `model-viewer.min.js` 与 LICENSE 到 `web/vendor/model-viewer/`。
- 若实现时 CDN 不可达，使用 npm `@google/model-viewer@4.4.0` 包内 dist 文件；不保留运行时 CDN 依赖。

## 8. 验收标准

1. 新用户登录后打开 `/api-settings`，保存一个 OpenAI 兼容 LLM Key，点击测试得到可达结果；创意生产“需求分析”任务从 queued 变为 running/succeeded，生成分镜。
2. 保存 Ark Key 和模型 ID 后，图片/视频模型在创意生产页显示可用；提交一个小尺寸图片任务，worker 完成并生成素材；视频任务能提交并轮询（真实扣费由用户 key 承担）。
3. 数据库、API 响应、日志中均无明文密钥；换一个用户看不到该凭据。
4. 素材库首屏不下载几十 MB 模型；点击“加载 3D 预览”后加载；切 Tab 不再重复下载；非 GLB 显示下载提示而非空白。
5. 素材卡片出现“编辑”，修改名称/描述/场馆/可见性后列表立即更新；非 owner 看不到编辑入口。
6. 快速切换类型 Tab 不再出现内容错位；增加“全部”Tab；时间预设/起止日期/排序可用；生成历史日期筛选无 8 小时偏移。
7. 现有测试全绿；新增测试覆盖上述关键路径。
8. 同租户用户能看到并读取他人的 shared 素材（含文件下载），不同租户看不到；改回 private 后立即从列表/详情/文件接口消失；shared 素材的非 owner 没有编辑入口。
9. 用户 base_url 与平台不同且未填自己的 key 时保存被拒绝；平台密钥不会出现在非平台主机的请求中。用户存在运行中任务时修改/删除该 provider 凭据返回 409。
10. 素材文件响应带 `private, max-age=86400`，重复切 Tab 不再重新下载百 MB 文件；JSON API 仍为 `no-store`。

## 9. 留给实现者的决定

- 配置页的具体卡片布局、文案、预设列表顺序。
- 自动预览阈值（默认 8MB）与超时时间（默认 90s）。
- “测试连接”的具体提示措辞。
- 是否在配置页显示平台环境变量来源（建议显示“平台默认可用”，不显示具体值）。
- 前端日期控件样式与移动端布局。

## 10. 风险与取舍

- **密钥安全**：加密依赖 SECRET_KEY；轮换 SECRET_KEY 会导致旧凭据不可解密。配置页需提示；后续可引入独立 `CREDENTIAL_ENCRYPTION_KEY` 轮换方案。
- **SSRF**：用户可填 Base URL，尽管有私网校验，DNS rebinding 仍有残余风险；只允许 HTTPS 缩小面。
- **真实计费**：测试连接不发起生成，用户首次真实生成可能才发现模型 ID/额度问题；错误信息会透出 provider 返回，便于排查。
- **大模型预览**：不压缩模型，低端设备仍可能因显存/解码失败；通过点击加载、错误提示和下载兜底，不在本期做转码。
- **Worker 单进程**：`START_TASK_WORKER=true` 仅适合当前单进程部署；扩容前必须拆分 worker。
