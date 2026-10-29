# AIGV Studio 真实可用性优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能够配置自己的 LLM/图片/视频 API 密钥并真实生成、分析；修复 3D 预览、素材编辑和素材筛选。

**Architecture:** 新增用户级凭据服务与 `/api-settings` 页面，生成/分析链路按任务创建者解析凭据；素材侧修复共享/租户读取语义，补齐编辑、缓存、预览格式判断和时间/排序筛选；前端继续使用 Vanilla JS，3D 预览改为本地 model-viewer + 点击加载。

**Tech Stack:** Python 3.10、Flask、SQLite、requests、cryptography/Fernet、Vanilla JS、model-viewer 4.4.0、pytest。

**Spec:** `docs/superpowers/specs/2026-10-30-real-usage-optimizations-design.md`

## Global Constraints

- Python 3.10；不引入前端构建工具；不使用新的 JS 框架。
- 所有新增 `/api/*` 写接口必须经过全局登录与 CSRF 守卫。
- 密钥不得进入日志、审计 metadata、API 响应、前端 DOM 或 Git。
- 用户密钥优先于平台环境变量；用户显式配置但失效时不得静默回退平台。
- 用户自定义 Base URL 与平台 Base URL 不同时，必须使用用户自己的密钥。
- 只允许公网 HTTPS provider 地址；默认拒绝私网/回环/HTTP。
- 素材文件缓存 `Cache-Control: private, max-age=86400`；其余 `/api/*` 保持 `no-store`。
- shared 素材仅同租户可读；编辑仅 owner/admin。
- 数据库迁移必须幂等，不重建既有表。
- 每个任务先写失败测试，再实现，测试通过后提交。

## Review Focus

1. 用户填自定义 Base URL 但不填自己的密钥——平台密钥绝不能发往该主机；由 Task 2 的 `test_custom_base_url_requires_user_key` 覆盖。
2. 用户在任务排队/运行中修改或删除凭据——必须 409，不能产生失去账号的付费任务；由 Task 2 的 `test_credential_locked_by_active_task` 覆盖。
3. 同租户用户读取他人 shared 素材——列表、详情、文件、下载四处必须一致允许；跨租户必须全部拒绝；由 Task 5 覆盖。
4. 伪造 `.glb` 或 OBJ/FBX——不能出现空白 model-viewer；由 Task 6 的上传/预览标志测试和 Task 10 的浏览器验证覆盖。
5. 日期筛选边界和快速切换 Tab——不能有 8 小时偏移或错类型内容；由 Task 7 的时区/边界测试和 Task 11 的竞态验证覆盖。

---

### Task 1: 凭据存储与加密服务

**Files:**
- Create: `backend/credential_service.py`
- Modify: `backend/database.py`（`init_database` 内新增表/索引）
- Modify: `backend/config.py`（新增 `CREDENTIAL_ENCRYPTION_KEY`、`ALLOW_INSECURE_PROVIDER_URLS`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_IMAGE_MODEL`）
- Modify: `requirements.txt`（`cryptography>=42,<47`）
- Test: `tests/test_credential_service.py`

**Interfaces:**
- Produces:
  - `class CredentialError(RuntimeError): code, message, status_code, details`
  - `class CredentialService: __init__(data_dir=None, config=None)`
  - `upsert(user_id, tenant_id, provider, api_key=None, base_url=None, model=None, model_overrides=None, is_active=None, clear_key=False) -> dict`
  - `delete(user_id, provider) -> bool`
  - `effective(user_id, provider, cfg=None, prefer_source=None) -> dict`（键：`api_key/base_url/model/model_overrides/source/credential_id`）
  - `has_provider(user_id, provider, cfg=None) -> (bool, str|None)`
  - `has_active_tasks(user_id, provider) -> bool`
  - `list_public(user_id) -> list[dict]`
  - `catalog() -> list[dict]`
  - `validate_base_url(url, cfg, resolver=None) -> str`
- `source` 取值：`"user" | "platform" | None`。

- [ ] **Step 1: 写失败测试**

`tests/test_credential_service.py`：

```python
def test_roundtrip_encrypts_and_masks(app):
    cfg = app.config["AIGV_CONFIG"]
    svc = CredentialService(cfg.DATA_DIR, cfg)
    user = support.create_admin(cfg.DATA_DIR, username="creduser")
    svc.upsert(user["id"], user.get("tenant_id"), "llm",
               api_key="sk-secret-1234", base_url="https://93.184.216.34/v1",
               model="gpt-4o-mini")
    row = svc.get_record(user["id"], "llm")
    assert "sk-secret-1234" not in row["api_key_ciphertext"]
    public = svc.list_public(user["id"])[0]
    assert public["has_key"] is True and public["key_last4"] == "1234"
    assert "api_key" not in public
    eff = svc.effective(user["id"], "llm", cfg)
    assert eff["api_key"] == "sk-secret-1234" and eff["source"] == "user"

def test_custom_base_url_requires_user_key(app):
    ... # upsert(base_url="https://93.184.216.34/v1", api_key=None) raises CredentialError code user_key_required

def test_user_isolation_and_placeholder(app):
    ... # A 的 key 不影响 B；环境中 placeholder 视为未配置
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_credential_service.py -q`
Expected: FAIL（`ModuleNotFoundError: backend.credential_service`）。

- [ ] **Step 3: 实现表、配置和服务**

`provider_credentials` 结构严格按 spec 6.1.1（含 `model` 列、唯一约束、user 索引）。服务要点：
- `self.db = get_database(os.path.join(self.data_dir, "aigv.db"))`
- Fernet key：`sha256((cfg.CREDENTIAL_ENCRYPTION_KEY or cfg.SECRET_KEY).encode())` → `urlsafe_b64encode`。
- 密文前缀 `v1:`；解密失败返回空 key 并记录 warning（不含密钥）。
- `_PLACEHOLDER_VALUES = {"", "placeholder", "your_api_key", "your-api-key", "changeme", "change-me", "none", "null"}`。
- `effective` 实现 spec 6.1.4 的优先级与 `user_key_required` 规则。
- `validate_base_url` 用 `ipaddress.ip_address(...).is_global` 判断；hostname 用 `resolver(host, port)`（默认 `socket.getaddrinfo`），所有解析结果必须 `is_global`；`https` 之外默认拒绝。
- `has_active_tasks` 查询 `generation_tasks`：`status IN ('queued','submitting','running')`，`created_by=?`，且 provider 映射命中（`llm` → `task_type='storyboard'`；`ark` → `provider IN ('ark_seedream','ark_seedance')`；其余同 provider 名）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_credential_service.py -q`
Expected: PASS。

- [ ] **Step 5: 安装依赖并提交**

```bash
.venv/bin/pip install 'cryptography>=42,<47'
git add backend/credential_service.py backend/database.py backend/config.py requirements.txt tests/test_credential_service.py
git commit -m "feat: add encrypted per-user provider credentials"
```

---

### Task 2: 凭据 HTTP API 与 SSRF/任务锁

**Files:**
- Create: `backend/provider_routes.py`
- Modify: `app.py`（`register_provider_routes(...)`）
- Test: `tests/test_provider_credentials_api.py`

**Interfaces:**
- Consumes: Task 1 的 `CredentialService` / `CredentialError`。
- Produces: `/api-settings` 页面路由与 4 个 API（见 spec 6.1.5）。

- [ ] **Step 1: 写失败测试**

覆盖：
```python
def test_put_get_delete_credential_masks_key(client): ...
def test_custom_base_url_requires_user_key_via_api(client): ...
def test_reject_private_and_http_base_url(client): ...  # https://127.0.0.1/v1 -> 400；http://93.184.216.34 -> 400
def test_credential_locked_by_active_task(client): ...  # 插入 queued task 后 PUT/DELETE -> 409 active_tasks
def test_other_user_cannot_see_credential(client): ...
```
测试里使用 `https://93.184.216.34/v1`（公网字面 IP，避免 DNS）和 `X-CSRF-Token`。

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_provider_credentials_api.py -q`
Expected: 404（路由不存在）。

- [ ] **Step 3: 实现路由**

- `GET /api/user/provider-credentials` → `{"items": [...], "catalog": [...]}`
- `PUT /api/user/provider-credentials/<provider>` → `parse_json_body`，调用 `upsert`，`CredentialError` → `json_error(code, message, status_code, details)`；成功返回掩码记录。
- `DELETE`、`POST .../test` 按 spec。
- 测试接口：LLM 用 `GET {base_url}/models`；其他 provider 用 `HEAD base_url`；不发起生成；不记录密钥。
- `GET /api-settings` → `send_from_directory(web_root, "api-settings.html")`。
- 在 `app.py` 的 `create_app` 中注册（在 profile 路由之后）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_provider_credentials_api.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/provider_routes.py app.py tests/test_provider_credentials_api.py
git commit -m "feat: expose provider credential API"
```

---

### Task 3: OpenAI Images Provider 与生成链路凭据接入

**Files:**
- Create: `backend/providers/openai_image.py`
- Modify: `backend/generation_models.py`
- Modify: `backend/generation_service.py`
- Modify: `backend/generation_routes.py`
- Test: `tests/test_openai_image_provider.py`
- Test: `tests/test_generation_credentials.py`

**Interfaces:**
- Produces:
  - `OpenAIImageProvider(api_key, base_url, model_id, timeout_s=180).generate(prompt, negative_prompt=None, size="1024x1024", seed=None, reference_image_urls=None, watermark=False, response_format="b64_json") -> {"images": [...]}`
  - `generation_models.get_model(..., user=None)` / `list_models(..., user=None)`
  - 模型项 `openai_gpt_image_1`（provider `openai_image`，model_id 取 `OPENAI_IMAGE_MODEL`）
  - `generation_service._provider_for_task(cfg, task)` 解析 `task.created_by` + `task.params["credential_source"]`
- 任务创建时写入 `params["credential_source"]`，并用用户 `model`/`model_overrides` 计算 `task.model_id`。

- [ ] **Step 1: 写失败测试**

`tests/test_openai_image_provider.py`：
```python
def test_maps_sizes_and_parses_b64(monkeypatch): ...
def test_auth_error_maps_to_provider_auth_error(monkeypatch): ...
```
`tests/test_generation_credentials.py`：
```python
def test_user_credential_makes_openai_image_available(app): ...
def test_provider_factory_uses_user_key_and_base_url(app): ...
def test_task_snapshots_credential_source(app): ...
def test_missing_user_credential_for_custom_base_url_blocks_task(app): ...
```
用 `monkeypatch.setattr(generation_service, "_provider_for_task", ...)` 只测其他逻辑；工厂本身用 `GenerationTask(...)` 直接调用。

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_openai_image_provider.py tests/test_generation_credentials.py -q`
Expected: FAIL（provider/model 不存在）。

- [ ] **Step 3: 实现**

- 适配器按 OpenAI Images API；把任意 `WxH` 归一到 `1536x1024`/`1024x1536`/`1024x1024`；解析 `url`/`b64_json`；401/403→`ProviderAuthError`，429→`ProviderRateLimited`，4xx→`ProviderRejected`，5xx→`ProviderUncertain`。
- `MODELS` 增加 `openai_gpt_image_1`（capabilities 见 spec 6.1.6）。
- `_availability` 通过 `credential_service.has_provider` 判断，返回 `credential_source`；`_with_config` 应用用户模型覆盖。
- `generation_routes` 的 `/api/generation/models` 传 `g.current_user`；任务创建前不可用 → `provider_not_configured` + `details.configure_url`。
- `create_generation_task` 用 `get_model(..., user=user)` 并写入 `params["credential_source"]`。
- `_provider_for_task`：按模型 provider 映射凭据 provider，调用 `effective(..., prefer_source=params.get("credential_source"))`；`openai_image` 返回 `OpenAIImageProvider`；ark/atlas/luma 用用户 base_url/key；comfyui 仍用平台配置。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_openai_image_provider.py tests/test_generation_credentials.py tests/test_generation.py -q`
Expected: PASS（含原有用例）。

- [ ] **Step 5: 提交**

```bash
git add backend/providers/openai_image.py backend/generation_models.py backend/generation_service.py backend/generation_routes.py tests/test_openai_image_provider.py tests/test_generation_credentials.py
git commit -m "feat: wire user credentials and OpenAI Images into generation"
```

---

### Task 4: LLM 分析凭据与 Worker 修复

**Files:**
- Modify: `backend/creative_routes.py`
- Modify: `backend/task_worker.py`
- Test: `tests/test_llm_credentials.py`

**Interfaces:**
- Consumes: Task 1/3 的 `CredentialService` 与 `effective`。
- Produces:
  - `analyze` 路由使用 `credential_service.has_llm(user_id, cfg)`。
  - `_execute_storyboard` 使用任务创建者的 LLM 凭据，并修复 `CreativeProject` 导入。

- [ ] **Step 1: 写失败测试**

```python
def test_analyze_accepts_user_llm_credential(app): ...
def test_analyze_returns_configure_url_without_llm(app): ...
def test_storyboard_executor_uses_user_llm_and_imports_creative_project(app, monkeypatch):
    # 用一个 fake LLMProvider 捕获 api_key/base_url/model_name；
    # 调用 task_worker._execute_storyboard，确认不再 NameError。
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_llm_credentials.py -q`
Expected: FAIL（`NameError: CreativeProject` 或 provider_not_configured）。

- [ ] **Step 3: 实现**

- `creative_routes.analyze`：用 `CredentialService(cfg.DATA_DIR, cfg).has_llm(...)`；任务 `params` 写入 `credential_source`。
- `task_worker.py` 导入 `CreativeProject`；`_execute_storyboard` 调用 `effective(task.created_by, "llm", cfg, prefer_source=params.get("credential_source"))`，用返回的 `api_key/base_url/model` 构造 `LLMProvider`；缺失时抛 `ProviderError("llm_missing_key")`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_llm_credentials.py tests/test_creative_routes.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/creative_routes.py backend/task_worker.py tests/test_llm_credentials.py
git commit -m "fix: run LLM analysis with per-user credentials"
```

---

### Task 5: 素材共享语义、编辑 API 与 can_edit

**Files:**
- Modify: `backend/access.py`
- Modify: `backend/asset_service.py`
- Modify: `app.py`（PUT 错误映射、列表/详情传 viewer）
- Test: `tests/test_asset_edit_access.py`

**Interfaces:**
- Consumes: 现有 `AssetService`、`can_read_asset`、`can_write_asset`。
- Produces:
  - `can_read_asset` 支持同租户 shared（含 owner 非空的 shared）。
  - `AssetService.update_asset` 支持 `visibility`，校验 name/description/visibility。
  - `public_dict(asset, include_owner=False, viewer=None)` 输出 `can_edit`。
  - 列表响应每项含 `can_edit`。

- [ ] **Step 1: 写失败测试**

```python
def test_shared_asset_readable_within_tenant(client, tmp_path):
    # A 上传并 PUT visibility=shared；B 同租户 list/detail/file/download 全部 200；B PUT 403
def test_shared_asset_not_readable_across_tenants(client, tmp_path):
    # 把 B 的 auth_users.tenant_id 改成 tenant_other；list 不含、detail/file/download 403
def test_edit_metadata_and_validation(client):
    # name/description/venue/visibility 成功；空 name、非法 venue、非法 visibility -> 400
def test_can_edit_flag(client):
    # owner true，非 owner false，admin true（管理员可编辑）
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_asset_edit_access.py -q`
Expected: FAIL（shared 文件 403、can_edit 缺失）。

- [ ] **Step 3: 实现**

- `access.can_read_asset` 按 spec 6.3.1 改为：admin → owner → shared 且同租户/tenant NULL → 历史无主 shared。
- `asset_service.list_assets/count_assets` 增加 `tenant_id`，非 admin 条件按 spec。
- `_UPDATE_FIELDS` 加 `visibility`；`update_asset` 校验 name（非空、≤120）、description（≤2000）、visibility ∈ {private, shared}；未知字段忽略。
- `app.py` PUT 捕获 `AssetServiceError` → 400 `invalid_asset_update`；更新后写 `_audit(cfg, "asset_update", ...)`。
- `public_dict` 增加 `viewer` 参数并输出 `can_edit`；列表/详情传入 `g.current_user`。
- 更新 `tests/test_file_safety.py` 中对 `file_url` 的断言（Task 6 会加 `?v=`；本任务先不加）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_asset_edit_access.py tests/test_file_safety.py tests/test_app_security.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/access.py backend/asset_service.py app.py tests/test_asset_edit_access.py tests/test_file_safety.py
git commit -m "feat: fix shared asset access and add editable metadata"
```

---

### Task 6: 3D 后端——缓存、预览格式与 GLB 校验

**Files:**
- Modify: `backend/web_security.py`
- Modify: `backend/asset_service.py`
- Test: `tests/test_asset_preview_cache.py`

**Interfaces:**
- Produces:
  - `public_dict` 输出 `file_ext`、`previewable`、`preview_reason`；`file_url` 带 `?v=<checksum[:12]>`。
  - 上传 `.glb` 校验前 4 字节 `glTF`，否则 400。
  - `GET /api/assets/<id>/file|download` 返回 `Cache-Control: private, max-age=86400`；其他 API 仍 `no-store`。

- [ ] **Step 1: 写失败测试**

```python
def test_glb_magic_validation_and_previewable(client):
    # 合法 glTF magic -> 201, previewable true, file_ext glb, '?v=' in file_url
    # fake .glb -> 400
def test_obj_is_download_only(client):
    # .obj 上传成功；previewable false；preview_reason 非空
def test_asset_file_cache_header(client):
    # GET file -> Cache-Control contains private, max-age=86400；ETag exists
    # GET /api/assets -> Cache-Control == no-store
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_asset_preview_cache.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

- `AssetService.store_file`：`ext == "glb"` 时读前 4 字节，必须 `b"glTF"`。
- `public_dict`：`file_ext = extension_for(file_path)`；`previewable = asset_type == "glb" and file_ext == "glb"`（GLB magic 已在上传校验）；`preview_reason` 对非 glTF 模型说明“仅支持下载”。
- `file_url` 追加 checksum 查询参数（有 checksum 时）。
- `web_security.py` `_security_headers`：在写入 `no-store` 前判断 `request.method == "GET"` 且路径匹配 `^/api/assets/[^/]+/(file|download)$` 且 200 → `private, max-age=86400`；否则维持现有逻辑。
- 更新 `tests/test_file_safety.py` 的 `file_url` 断言（现在包含 `?v=`）。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_asset_preview_cache.py tests/test_file_safety.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/web_security.py backend/asset_service.py tests/test_asset_preview_cache.py tests/test_file_safety.py
git commit -m "feat: cache asset files and mark previewable formats"
```

---

### Task 7: 素材/历史时间筛选与排序后端

**Files:**
- Modify: `backend/asset_service.py`
- Modify: `app.py`
- Modify: `backend/generation_routes.py`
- Modify: `backend/task_service.py`（历史排序）
- Test: `tests/test_asset_filters.py`

**Interfaces:**
- `list_assets(..., tenant_id=None, created_after=None, created_before=None, sort="newest")`
- `count_assets(...)` 同步增加 `tenant_id/created_after/created_before`
- `/api/assets` 接受 `created_after`、`created_before`、`sort`（`newest|oldest|name`）
- `/api/generation/tasks` 接受 `sort`（`newest|oldest`），日期按服务器本地时区解释
- `TaskService.list_tasks(..., sort="newest")`

- [ ] **Step 1: 写失败测试**

```python
def test_asset_date_and_sort_filters(client, tmp_path):
    # 直接 UPDATE assets SET created_at 为固定值；验证 after/before 边界、newest/oldest/name
def test_asset_invalid_sort_and_range(client):
    # sort=evil -> 400；after > before -> 400
def test_generation_date_is_local_time(client):
    # '2026-10-30' 解析为本地 00:00:00；end_of_day 为 23:59:59
def test_generation_sort_oldest(client): ...
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_asset_filters.py -q`
Expected: FAIL。

- [ ] **Step 3: 实现**

- `asset_service` 增加条件与排序白名单，拼接 SQL 时只使用白名单字符串。
- `app.py` 增加 `_parse_date_param(value, end_of_day=False)`：`datetime.strptime(...).timestamp()`（不设置 UTC tzinfo），非法 400；校验 after<=before。
- `generation_routes._parse_date` 去掉 `tzinfo=timezone.utc`；`list_tasks` 增加排序白名单（`created_at DESC/ASC`）。
- 前端尚未改动；本任务只保证接口。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_asset_filters.py tests/test_generation_history.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/asset_service.py backend/task_service.py backend/generation_routes.py app.py tests/test_asset_filters.py
git commit -m "feat: add date and sort filters for assets and history"
```

---

### Task 8: API 配置前端页面

**Files:**
- Create: `web/api-settings.html`
- Create: `web/api-settings.js`
- Modify: `web/session-nav.js`（用户菜单加“API 配置”）
- Modify: `web/profile.html`（增加入口卡片）
- Modify: `web/styles.css`（provider 卡片/状态样式）
- Modify: `web/creative-studio.js`（不可用提示加“去配置 API”链接）
- Test: 浏览器验证（见 Step 4）

**Interfaces:**
- Consumes: Task 2 的 `/api/user/provider-credentials` 系列接口；Task 1 的 `catalog()` 返回结构。
- Produces: `/api-settings` 页面。

- [ ] **Step 1: 写页面骨架与失败验证**

先添加 `web/api-settings.html`（导航 + 页面容器 + 脚本），`app.py` 的页面路由已经在 Task 2 注册。用 curl 验证当前返回 404/空页面（若 Task 2 已加路由则跳过失败断言，改为验证页面缺少卡片容器）。

- [ ] **Step 2: 实现 JS**

- `loadCredentials()`：`AIGV.api('/api/user/provider-credentials')`，渲染 catalog 中每个 provider 的卡片。
- `saveProvider(key)`：收集 base_url/key/model/高级模型；`PUT`；成功后重新加载。
- `testProvider(key)`：`POST .../test`，显示 `verified/reachable/message`。
- `deleteProvider(key)`：确认后 `DELETE`。
- 状态徽章：`user` → 使用个人配置；`platform` → 使用平台默认；`None` → 未配置。
- Key 输入 `type=password`，placeholder 显示 `已保存（••••last4），留空保持不变`；页面不把 key 写入 DOM。
- LLM 预设下拉：OpenAI/DeepSeek/通义/Kimi/智谱，选择后填 base_url/model。
- 对 `active_tasks` 409、`user_key_required` 400 显示后端消息。

- [ ] **Step 3: 接入导航与错误提示**

- `session-nav.js` 在“个人中心”前插入 `<a href="/api-settings">API 配置</a>`。
- `profile.html` 增加一张卡片链接到 `/api-settings`。
- `creative-studio.js` 的 `provider_not_configured`、模型不可用文案增加 `/api-settings` 链接（使用 `escapeHtml`/现有 toast）。

- [ ] **Step 4: 浏览器验证**

用 Playwright（`/tmp/pw` 或等价环境）执行：
1. 登录 admin，打开 `/api-settings`，应看到 5 张 provider 卡片。
2. 在 LLM 卡片填 `https://93.184.216.34/v1` + 测试 key + 模型，保存；Network 响应不含明文 key，页面显示 `••••1234`。
3. 只填自定义 Base URL、不填 key 保存 → 页面显示“必须填写自己的密钥”。
4. 删除配置 → 状态回到“未配置/使用平台默认”。

- [ ] **Step 5: 提交**

```bash
git add web/api-settings.html web/api-settings.js web/session-nav.js web/profile.html web/styles.css web/creative-studio.js
git commit -m "feat: add user API settings page"
```

---

### Task 9: 素材编辑前端

**Files:**
- Modify: `web/assets.html`（编辑弹窗）
- Modify: `web/assets.js`（编辑按钮、回填、PUT、刷新、created_at）
- Modify: `web/styles.css`（如有必要）
- Test: 浏览器验证

**Interfaces:**
- Consumes: Task 5 的 `can_edit`、`PUT /api/assets/<id>`。
- Produces: 卡片“编辑”入口与编辑弹窗。

- [ ] **Step 1: 添加弹窗与按钮（先验证缺失）**

打开素材库，确认卡片只有下载/删除；编辑弹窗不存在。

- [ ] **Step 2: 实现**

- `renderAssetCard` 增加编辑按钮（仅 `asset.can_edit` 为 true）；带 `data-id`。
- 增加 `currentAssetsById` 映射；点击编辑回填 name/venue/description/visibility；类型、文件大小只读。
- 提交 `PUT /api/assets/<id>`，JSON body 仅含 name/description/venue_type/visibility；成功后关闭弹窗、toast、`loadAssets()+loadSummary()`。
- 403/400 显示后端消息；隐藏非 owner 的编辑按钮。
- 卡片显示 `created_at`（调用 `AIGV.formatTime`）。

- [ ] **Step 3: 浏览器验证**

1. 上传一个素材，点编辑，改名/描述/场馆/共享 → 列表立即更新。
2. 用另一个普通用户登录：同租户 shared 素材可见但无编辑按钮；private 素材不可见。
3. 管理员可编辑他人素材。

- [ ] **Step 4: 提交**

```bash
git add web/assets.html web/assets.js web/styles.css
git commit -m "feat: edit asset metadata from library"
```

---

### Task 10: 3D 预览前端（自托管 + 点击加载）

**Files:**
- Create: `web/vendor/model-viewer/model-viewer.min.js`
- Create: `web/vendor/model-viewer/LICENSE`
- Modify: `web/assets.html`（本地脚本）
- Modify: `web/assets.js`（预览占位、IntersectionObserver、进度/错误/超时）
- Modify: `web/styles.css`（占位/进度/错误样式，移除 `all: unset`）
- Test: 浏览器验证

**Interfaces:**
- Consumes: Task 6 的 `previewable`、`preview_reason`、`file_size`、`file_url`。
- Produces: 无空白 model-viewer；首屏不下载大模型。

- [ ] **Step 1: 引入本地库（先验证失败）**

下载 `https://unpkg.com/@google/model-viewer@4.4.0/dist/model-viewer.min.js` 与包内 LICENSE 到 `web/vendor/model-viewer/`；`assets.html` 改成本地 module script，移除 unpkg preconnect/CDN。若 CDN 不可达，用 `npm pack @google/model-viewer@4.4.0` 解包 dist。

- [ ] **Step 2: 实现渲染逻辑**

- `previewable === false`：显示图标 + `preview_reason`，不创建 model-viewer。
- `previewable === true` 且 `file_size <= 8 * 1024 * 1024`：IntersectionObserver 进入视口后创建。
- 大于 8MB：显示文件大小 + “点击加载 3D 预览”；点击创建。
- `createModelViewer(container, src)`：设置 `src`，监听 `progress`/`load`/`error`；90s 超时显示重试；失败显示下载链接。
- 记录 `loadedPreviewAssetIds`，重渲染时对已加载小模型直接创建（命中缓存）。
- 移除 `model-viewer::part(default-progress-bar) { all: unset; }`，改为可见进度条样式。

- [ ] **Step 3: 浏览器验证**

1. 打开素材库，Network 中首屏无 `/api/assets/*/file` 的 GLB 请求（大模型未点击）。
2. 点击“加载 3D 预览”，两个大模型文件各请求一次并成功显示。
3. 切到图片再切回模型，已加载模型不再发网络请求（或走 disk cache）。
4. 上传 OBJ/FBX，卡片显示“不支持在线预览”，无空白 viewer。
5. 断网/改错 URL，显示错误与重试，不是空白。

- [ ] **Step 4: 提交**

```bash
git add web/vendor/model-viewer web/assets.html web/assets.js web/styles.css
git commit -m "perf: lazy-load 3D previews with local model-viewer"
```

---

### Task 11: 素材筛选前端（竞态、全部、时间/排序）

**Files:**
- Modify: `web/assets.html`（全部 Tab、时间/排序/清除控件、历史预设）
- Modify: `web/assets.js`（请求序列/AbortController、筛选状态、预设、校验）
- Modify: `web/styles.css`（工具栏布局）
- Test: 浏览器验证

**Interfaces:**
- Consumes: Task 7 的 `/api/assets` 和 `/api/generation/tasks` 参数。
- Produces: 类型切换不再错位，时间/排序筛选可用。

- [ ] **Step 1: 复现竞态并记录**

使用 Playwright 延迟 `asset_type=image` 请求 1.5s，点击图片后 250ms 点文档；当前结果是“文档 Tab 显示图片卡片”。

- [ ] **Step 2: 实现**

- Tab 增加 `data-tab="all"`；`getAssetTypeForTab()` 对 `all` 返回空字符串。
- `loadAssets()` 改为 `requestAssets()`：`var seq = ++loadSeq`；响应仅在 `seq === loadSeq` 时渲染；用 `AbortController` 取消上一请求；去掉基于 `isLoading` 的提前 return。
- 新增控件：`asset-date-preset`（全部/今天/近7天/近30天/自定义）、`asset-date-from`、`asset-date-to`、`asset-sort`（最新/最早/名称）、`clear-filters`。
- 预设计算本地 `YYYY-MM-DD`；自定义时显示日期输入；请求前校验 `from <= to`。
- 切换 Tab 保留搜索/场馆/时间/排序；场馆仅对 all/models/images 显示。
- 历史 Tab 复用日期预设与校验，保留类型/状态，增加排序；请求参数 `date_from/date_to/sort`。
- 所有筛选变更重置 `currentPage=1`；空结果提供“清除筛选”。

- [ ] **Step 3: 浏览器验证**

1. 重跑延迟竞态：最终“文档”Tab 只显示文档卡片。
2. “全部”Tab 显示 3D/图片/文档混合列表。
3. 今天/近 7 天/近 30 天/自定义起止日期结果正确；清除后恢复全部。
4. 排序最新/最早/名称顺序正确。
5. 历史 Tab 的日期筛选与排序正确；非法范围提示且不发请求。

- [ ] **Step 4: 提交**

```bash
git add web/assets.html web/assets.js web/styles.css
git commit -m "fix: make asset filters reliable and add time/sort controls"
```

---

### Task 12: 集成、Worker、回归与推送

**Files:**
- Modify: `.env`（`START_TASK_WORKER=true`；不要提交密钥）
- Modify: `.env.example`（新增 OpenAI/加密/worker 配置说明）
- Modify: `README.md` 或 `docs/Auth-and-RBAC.md`（API 配置与 worker 部署说明）
- Test: 全量 pytest + Playwright + 真实服务冒烟

- [ ] **Step 1: 运行后端全量测试**

Run: `.venv/bin/python -m pytest -q`
Expected: 全部通过；记录任何既有失败（不得用新失败掩盖）。

- [ ] **Step 2: 配置并重启服务**

- `.env` 增加 `START_TASK_WORKER=true`；确认 `DATA_DIR`/`SECRET_KEY` 不变；重启 `.venv/bin/python -u app.py`。
- 验证 `/api/health`、`/api/auth/csrf`、`/api/generation/models`（登录后）正常。
- 确认只有一个 Web 进程，避免重复 worker。

- [ ] **Step 3: 端到端冒烟**

用 Playwright：
1. 登录 admin → `/api-settings` 保存真实或 mock LLM/图片凭据（测试环境可用本地 mock；生产用用户 key）。
2. 创意生产提交一个 LLM 分析任务，轮询到 succeeded（或至少 running，证明 worker 已领取）。
3. 提交一个图片任务（若有 key），确认从 queued → running/succeeded，素材库出现结果。
4. 素材库：3D 点击加载、编辑、全部/类型/时间/排序筛选、竞态复现步骤。
5. 检查服务日志无异常、无明文密钥。

- [ ] **Step 4: 代码审计与提交**

```bash
git status --porcelain
# 确认未暂存 .env、data/.secret_key、data/aigv.db、logs/、backups/ 等运行时/敏感文件
git add <本次源文件与测试>
git commit -m "feat: make AIGV Studio usable with real provider credentials"
```

- [ ] **Step 5: 推送 GitHub**

```bash
git remote -v   # 确认 origin 为 git@github.com:shifengdongma/cursor-blender-mcp.git
git branch -M feature/real-usage-optimizations   # 若当前为 master，先建功能分支
git push -u origin feature/real-usage-optimizations
```

如果本仓库尚无 `origin`：

```bash
git remote add origin git@github.com:shifengdongma/cursor-blender-mcp.git
git push -u origin feature/real-usage-optimizations
```

推送后在最终回复中给出分支、提交号和验证结果；是否合并 master 由用户确认。

---

## Self-Review

- **Spec coverage:** API 配置（Task 1–4、8）、3D 预览（Task 6、10）、素材编辑（Task 5、9）、筛选（Task 7、11）、worker/部署/推送（Task 12）。
- **Type consistency:** `CredentialService.effective` 的返回键在 Task 1/3/4 中一致；`public_dict(viewer=...)` 在 Task 5/6 中一致；`previewable/preview_reason/file_ext` 在 Task 6/10 中一致。
- **Review Focus:** 5 条高风险输入均有对应测试或浏览器验证（Task 2、5、6、7、10、11）。
- **比例:** 计划只固定接口/值/验收，不转录实现代码。
