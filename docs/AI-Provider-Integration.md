# AI Provider 接入与运维说明

本文档描述当前仓库中**真实实现**的图片/视频生成链路、模型能力、环境变量、错误处理与验证状态。所有密钥只从环境变量读取，不进入数据库、前端或日志。

## 1. 总览

```
POST /api/generation/images|videos
        │
        ▼
generation_service.create_generation_task()
  - 能力校验/参数归一化/项目与参考图所有权/配额/幂等
  - 写入 generation_tasks(status=queued)
        │
        ▼
GenerationWorker (SQLite BEGIN IMMEDIATE 原子领取 + 租约)
  - submit: 调用 Provider，保存 provider_job_id → running
  - poll:   查询 Provider；成功则下载到 data/assets/generated/<user>/<task>/
            单事务写入 assets/task_artifacts/任务结果/分镜关联
        │
        ▼
GET /api/generation/tasks/<id>   ← 前端轮询（只显示真实阶段，不伪造百分比）
```

任务状态：`queued → submitting → running → succeeded | failed | cancelled | needs_review`。

- `submitting` 期间租约过期会被恢复为 `needs_review`（提交结果不确定，禁止自动重复扣费）。
- `needs_review` 只有在人工确认后才允许重试；已有 `provider_job_id` 的任务重试只恢复轮询。
- 任务有整体截止时间（图片 1800s / 视频 7200s，可配置），超时标记 `task_timeout` 并保留第三方任务 ID。

## 2. Provider 与模型

模型注册表：`backend/generation_models.py`，官方 ID 单一来源：`backend/model_ids.py`。`available` 只表示**凭据已配置/ComfyUI 可达**；连接测试的 `verified` 仅代表 `/models` 鉴权通过，真实模型可调用性必须通过“真实调用测试”或实际任务确认。

| UI key | Provider | 官方模型 ID | 类型 | 说明 |
|---|---|---|---|---|
| `ark_seedream_pro` | `ark_seedream` | `doubao-seedream-5-0-pro-260628` | 图片 | 1K/1.5K/2K；最多 10 参考图 |
| `ark_seedream_flash` | `ark_seedream` | `doubao-seedream-5-0-flash-260915` | 图片 | 1K/1.5K/2K；最多 10 参考图；**默认图片模型** |
| `comfyui_default` | `comfyui` | `default` | 图片 | 本地工作流；异步 prompt_id |
| `ark_seedance_25` | `ark_seedance` | `doubao-seedance-2-5-260628` | 视频 | 4–30s；480/720/1080p；最多 30 参考图；音频默认开 |
| `ark_seedance_20` | `ark_seedance` | `doubao-seedance-2-0-260128` | 视频 | 4–15s；480/720/1080p；最多 9 参考图；支持音频 |
| `ark_seedance_10_pro` | `ark_seedance` | `doubao-seedance-1-0-pro-250528` | 视频 | 2–12s；480/720/1080p；仅首/尾帧（最多 2 图）；无音频 |
| `atlas_seedance_default` | `atlas_seedance` | `SEEDANCE_MODEL_NAME` | 视频 | 旧 Atlas Cloud 适配，非方舟直连 |
| `luma_default` | `luma` | `LUMA_MODEL_NAME`（默认 ray-2） | 视频 | 旧适配，未验证 |

旧 `ark_seedream_lite` 仅作为前端选择别名映射到 Flash；旧 Lite override 不会应用到 Flash。模型 ID 默认由注册表提供，只有显式设置环境变量才覆盖：

```env
ARK_IMAGE_MODEL=
ARK_IMAGE_MODEL_FLASH=
ARK_VIDEO_MODEL=
ARK_VIDEO_MODEL_20=
ARK_VIDEO_MODEL_10_PRO=
LUMA_MODEL_NAME=ray-2
```

前端通过 `GET /api/generation/models` 获取模型与 `capabilities`；未配置的模型也会返回（`available=false` + `unavailable_reason`），由页面置灰并提示。`?available_only=1` 只返回已配置模型。

### 连接测试与真实调用测试

- `POST /api/user/provider-credentials/<provider>/test` 只做非计费探测：
  - LLM / Ark / OpenAI 图片走 `GET {base_url}/models`，仅当返回 200 且响应是可识别的模型列表时才标记 `key.status=verified`；
  - 401/403 → `rejected`；404/405 → `unsupported`（明确“无法通过此方式验证”）；429/5xx/重定向 → `unknown`；
  - Atlas/Luma 只做**不带 Authorization** 的网络可达探测，`key.status=unsupported`；
  - 响应同时返回 `network/key/model` 三段状态，禁止把任意 HTTP 响应当成密钥验证成功；
  - 仅真正的 200 模型列表写入 `last_verified_at`。
- `POST /api/user/provider-credentials/<provider>/test-generation` 是独立的**计费**测试：
  - 必须携带 `{"confirm_billing": true}`，否则 400 `billing_confirmation_required`；
  - 图片：使用模型最小尺寸真实生成 1 张图；
  - 视频：创建最短规格任务并立即尝试取消；返回 `status=accepted`（不代表生成完成），取消失败仍可能计费；
  - 结果写入 `last_verification`（按模型），失败时保留安全 `error_code`、`provider_code`、`provider_request_id`，不返回 Key。

## 3. 环境变量

```env
ARK_API_KEY=
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_REQUEST_TIMEOUT_S=180

SEEDANCE_API_KEY=
SEEDANCE_BASE_URL=https://api.atlascloud.ai/api/v1
SEEDANCE_MODEL_NAME=bytedance/seedance-v1.5-pro/text-to-video

LUMA_API_KEY=
LUMA_BASE_URL=https://api.lumalabs.ai/dream-machine/v1
LUMA_MODEL_NAME=ray-2

COMFYUI_ENABLED=false
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_FILE=./data/workflows/comfyui_default.json

GENERATION_TASK_LEASE_SECONDS=900
GENERATION_IMAGE_DEADLINE_S=1800
GENERATION_VIDEO_DEADLINE_S=7200
GENERATION_POLL_INTERVAL_S=10
GENERATION_POLL_MAX_ERRORS=8
GENERATION_DOWNLOAD_TIMEOUT_S=180
GENERATION_RECOVERY_INTERVAL_S=60
PROVIDER_CONNECT_TIMEOUT_S=10
MAX_GENERATION_DOWNLOAD_MB=500
MAX_REFERENCE_IMAGE_MB=10
MAX_CONCURRENT_TASKS_PER_USER=2
DAILY_IMAGE_LIMIT=20
DAILY_VIDEO_LIMIT=5

# 本地 TTS / FFmpeg 后期
PIPER_BIN=piper
PIPER_MODEL_PATH=./data/tts_models/zh_CN-huayan-medium.onnx
TTS_VOICES_FILE=./data/tts_voices.json
TTS_MODEL_DIR=./data/tts_models
TTS_DEFAULT_VOICE_ID=piper:zh_CN-huayan-medium
FFMPEG_BIN=ffmpeg
FFPROBE_BIN=ffprobe
SUBTITLE_FONT_NAME=Noto Sans CJK SC
MAX_COMPOSE_DURATION_S=900
MAX_AUDIO_UPLOAD_MB=50
```

TTS 不是外部生成 Provider，但同样遵循“未配置/不可用就明确报错”的原则：音色注册表只列出真实安装的 Piper 模型；云端 TTS 本期未启用，也没有伪造音色。

## 4. 图片生成

### 文本生图

1. 前端 POST `/api/generation/images`（或创意工作台 `/api/creative/shots/<id>/images`）。
2. 后端验证模型类型/可用性、Prompt 长度、项目与分镜所有权、配额与幂等键。
3. 根据 `size`（1K/1.5K/2K/3K/4K 或 `WxH`）与 `ratio` 计算实际宽高，校验模型像素范围；参数写入任务 `params`。
4. Worker 调用 Provider：
   - Ark Seedream：`POST {ARK_BASE_URL}/images/generations`，Bearer 鉴权；`size` 发送为 `WxH`；`image` 为参考图 data URL；`seed` 仅模型支持时发送。
   - ComfyUI：`POST /prompt` 提交工作流，保存 `prompt_id`，随后轮询 `/history/{prompt_id}`，从 `/view` 下载。
5. 图片下载后做 URL 白名单/DNS 校验、内容类型/魔数/大小校验，保存为私有素材。
6. 任务与素材在**同一数据库事务**中落库；租约丢失则回滚并删除文件。

### 图生图

- 请求字段 `reference_asset_id`（首期单张）。后端验证资产存在、属于当前用户/可读、类型为图片、大小限制，并转换为 data URL。
- 可选参考图在创建任务时写入 `target_asset_id`，任务排队/运行期间该资产不能被删除。
- 前端在模型 `supports_reference_image=true` 时显示参考图选择器，支持当前分镜图、已上传图片、临时上传。

### 多图

- Seedream 单次调用固定返回 1 张（`n=1`）；`max_images=1`。需要多张时前端/调用方应创建多个任务，配额与费用按任务计。

## 5. 视频生成

### 文生视频 / 图生视频

1. POST `/api/generation/videos` 或 `/api/creative/shots/<id>/videos`。
2. 校验比例/时长/分辨率/音频/种子是否在模型能力内；不支持则 400，不静默改写。
3. Ark Seedance：
   - 创建：`POST {ARK_BASE_URL}/contents/generations/tasks`，`content` 数组包含文本与可选 `image_url`（首帧 `role=first_frame`）。
   - 查询：`GET .../tasks/{id}`，状态 `queued/running/succeeded/failed/cancelled`。
   - 取消：`DELETE .../tasks/{id}`（Provider 支持时）。
   - 成功：从 `content.video_url` 取临时 URL，立即由后端下载到本地私有素材。
4. Atlas / Luma：旧适配，仅发送其支持的字段；超时/连接失败标记为 `submission_uncertain`，不会自动重复提交。

### 结果与有效期

- 方舟返回的图片/视频 URL 是临时签名地址（通常 24 小时），后端会立即转存到 `data/assets/generated/...`，数据库只保存本地素材。
- 下载器只允许 http/https、标准端口、公网地址、白名单内容类型，拒绝内网/重定向到私网/超大文件。

## 6. 错误与排查

| 现象/错误码 | 原因 | 处理 |
|---|---|---|
| `provider_not_configured` | 模型凭据缺失或 ComfyUI 不可达 | 配置对应环境变量；前端会列出具体原因 |
| `provider_auth_error` | 401 | API Key 无效或过期；检查 Key 与区域 |
| `provider_permission_denied` | 403 | Key 无权限/账户受限；检查方舟控制台权限与项目空间 |
| `provider_endpoint_not_found` | 404 | Base URL 路径错误；方舟应为 `https://ark.cn-beijing.volces.com/api/v3` |
| `model_not_activated` | 400 `ModelNotOpen` / “not activated” | 账户未开通该模型；到方舟控制台开通或改选已开通模型 |
| `model_not_found` | 400 `InvalidEndpointOrModel.NotFound` | 模型 ID 不存在/区域不匹配；核对控制台模型 ID |
| `provider_rate_limited` | 429 | 自动延迟重试（提交阶段）或降低频率；保留 Retry-After |
| `provider_rejected` | 其他 4xx | 检查尺寸/时长/比例/参考图是否符合模型能力 |
| `billing_confirmation_required` | 真实测试未确认计费 | 前端确认费用后携带 `confirm_billing=true` |
| `https_required` | 启用 `CREDENTIAL_REQUIRE_HTTPS=true` 后经 HTTP 写入 | 改用 HTTPS 或可信代理的 `X-Forwarded-Proto` |
| `submission_uncertain` → `needs_review` | 提交超时/5xx | 不要自动重试；在管理后台确认第三方是否已创建任务 |
| `task_timeout` | 超过整体截止时间 | 第三方 ID 保留，管理员可恢复轮询 |
| `provider_poll_timeout` | 查询超时 | 指数退避，达到上限后失败 |
| `asset_in_use` (409) | 资产仍被分镜/时间线/运行中任务引用 | 先解除引用再删除 |
| `csrf_invalid` (403) | 页面 Token 过期 | 前端自动刷新一次 Token 后重试 |
| `unauthorized` (401) | 未登录/会话失效 | 重新登录 |
| `provider_not_configured` + 前端空模型 | 未配置任何图片/视频 Key | 这是预期状态，不会返回假结果 |

诊断命令：

```bash
python3 -m pytest tests/test_generation.py tests/test_generation_hardening.py \
  tests/test_generation_providers.py tests/test_generation_history.py -q
python3 -m pytest tests/test_comfyui_provider.py -q
```

真实调用（会产生费用，默认不执行）：

```bash
# 配置 ARK_API_KEY 后，用测试客户端或浏览器登录后提交最小任务：
# 图片：POST /api/generation/images  {"model_key":"ark_seedream_pro","prompt":"test","size":"1K"}
# 视频：POST /api/generation/videos  {"model_key":"ark_seedance_25","prompt":"test","duration_s":4,"resolution":"480p"}
# 然后在素材库「生成历史」观察状态；失败时查看 error_code/error_message。
```

## 7. 真实验证状态（2026-10-30）

本次交付进行了两项真实调用（不包含任何 Mock 成功响应）：

1. **非计费鉴权验证**：`GET https://ark.cn-beijing.volces.com/api/v3/models`
   - 结果：HTTP 200，`key.status=verified`，`Seedream 5.0 Flash` 出现在模型列表中；
   - 请求 ID：`021793360706066bc68ba76535d4d8d120d8e883d298b95f3f881`；
   - 结论：Key 有效；**模型出现在列表中不等于已开通**。
2. **一次授权的真实图片调用**（Seedream Flash，1K，最小规格）：
   - 结果：HTTP **404**，`error.code=ModelNotOpen`；
   - 请求 ID：`0217933607196221cb6d3ad1bdd7a7436196dd041d7fa42e7e12b`；
   - 结论：方舟账户尚未开通该模型，未产生图片。此前账号对 Pro 也报过未开通。
   - 已修正分类：Ark 的 404 + `ModelNotOpen` 现在映射为 `model_not_activated`，而不是误导性的“接口路径不存在”；该场景有 Mock 回归测试覆盖。
   - 未在未授权的情况下重复付费调用或改试 Pro。

因此，真实生图成功仍需用户在方舟控制台开通至少一个 Seedream 模型后，通过 `/api-settings` 的“真实调用测试（可能计费）”验证。Seedance 视频真实测试尚未执行；创建后立即取消的测试入口已实现并通过 Mock 测试。ComfyUI/Atlas/Luma 未做真实调用验证。

## 8. 生成计时与性能诊断

- `generation_tasks` 现在记录 `created_at_ms/claimed_at_ms/provider_request_started_at/provider_request_finished_at/provider_job_created_at/provider_finished_at/download_started_at/download_finished_at/persist_started_at/persist_finished_at/completed_at_ms`。
- `GET /api/generation/tasks/<task_id>/timing`：任务所有者或管理员可读，返回各阶段时间戳与 durations_ms。
- `GET /api/generation/timing/summary`：仅管理员，可按 task_type/provider/model/status/has_reference/hours 过滤，返回 count、成功率、均值/中位数/P95。
- `provider_elapsed_ms` 包含服务商排队和运行，不等于纯推理时间。详细 benchmark 见 `docs/Performance-Report.md`。

## 9. 已知限制

- Seedream 的 `seed`/负面提示词能力按官方文档保守标注；不支持的参数会被拒绝或丢弃（负面提示词来自分镜默认值时丢弃，不发送）。
- 后端已接受 `reference_asset_ids` 列表并按模型真实上限校验；创意工作台前端仍为单选参考图，完整多选 UI 尚未实现。
- Seedance 4K 档位未在注册表开放（仅 480/720/1080p），待真实账户验证后再放开。
- 组图、视频编辑/延长等高级能力尚未开放。
- 第三方状态若出现未知值，按轮询错误退避处理，不会猜测成功。
- 当前部署仍为 HTTP，未强制 HTTPS；API Key 传输存在明文风险，页面与启动日志会有提示。
- 单机 SQLite + 本地文件存储；扩展到多机时需将任务队列与素材迁移到 PostgreSQL/对象存储。

## 10. 火山方舟推理 API 与管理 API 的区分

`ARK_API_KEY` / `ARK_BASE_URL`（`https://ark.cn-beijing.volces.com/api/v3`）只用于 Seedream/Seedance 推理。它们**不能**用于查询账号级用量或费用账单。

官方用量/账单使用独立的管理凭据和 OpenAPI 域名：

| 用途 | 域名 | 凭据 | 文档 |
|---|---|---|---|
| Ark 推理 | `ark.cn-beijing.volces.com/api/v3` | `ARK_API_KEY` 或用户个人 Key | 本文 1-9 节 |
| Ark 用量 | `ark.cn-beijing.volcengineapi.com` | `VOLCENGINE_ACCESS_KEY_ID/SECRET_ACCESS_KEY` | `docs/Volcengine-Usage-Billing-Integration.md` |
| 费用中心账单/余额 | `billing.volcengineapi.com` | 同一管理 AK/SK（最小权限 IAM） | `docs/Volcengine-Billing-Reconciliation.md` |

管理凭据只存在于服务器 `.env`，不会返回前端或写入数据库/审计/日志。未配置管理凭据时，图片、视频、LLM 生成不受影响；AI 模型服务/官方账单页面显示未配置状态。

API Key 资源 ID（`ApiKeyID`）不是 API Key 密钥内容；官方用量响应中的 `APIKeyID` 可用于分账关联，但当前账号尚未开通分账账单能力。
