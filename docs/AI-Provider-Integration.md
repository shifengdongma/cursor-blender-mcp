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

模型注册表：`backend/generation_models.py`。`available` 只表示**凭据已配置/ComfyUI 可达**；`verified` 始终为 `false`，除非真实调用成功（当前未做付费验证）。

| UI key | Provider | 默认模型 ID | 类型 | 说明 |
|---|---|---|---|---|
| `ark_seedream_pro` | `ark_seedream` | `doubao-seedream-5-0-pro-260628` | 图片 | 同步接口；1K/1.5K/2K；最多 10 参考图 |
| `ark_seedream_lite` | `ark_seedream` | `doubao-seedream-5-0-lite-260128` | 图片 | 2K/3K/4K；最多 14 参考图 |
| `comfyui_default` | `comfyui` | `default` | 图片 | 本地工作流；异步 prompt_id |
| `ark_seedance_25` | `ark_seedance` | `doubao-seedance-2-5-260628` | 视频 | 4–30s；480/720/1080p；音频默认开 |
| `ark_seedance_20` | `ark_seedance` | `doubao-seedance-2-0-260128` | 视频 | 能力保守标注，未验证 |
| `ark_seedance_10_pro` | `ark_seedance` | `doubao-seedance-1-0-pro-250528` | 视频 | 5/10s，无音频 |
| `atlas_seedance_default` | `atlas_seedance` | `SEEDANCE_MODEL_NAME` | 视频 | 旧 Atlas Cloud 适配，非方舟直连 |
| `luma_default` | `luma` | `LUMA_MODEL_NAME`（默认 ray-2） | 视频 | 旧适配，未验证 |

模型 ID 可被环境变量覆盖：

```env
ARK_IMAGE_MODEL=doubao-seedream-5-0-pro-260628
ARK_IMAGE_MODEL_LITE=doubao-seedream-5-0-lite-260128
ARK_VIDEO_MODEL=doubao-seedance-2-5-260628
ARK_VIDEO_MODEL_20=doubao-seedance-2-0-260128
ARK_VIDEO_MODEL_10_PRO=doubao-seedance-1-0-pro-250528
LUMA_MODEL_NAME=ray-2
```

前端通过 `GET /api/generation/models` 获取模型与 `capabilities`；未配置的模型也会返回（`available=false` + `unavailable_reason`），由页面置灰并提示。`?available_only=1` 只返回已配置模型。

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
MAX_GENERATION_DOWNLOAD_MB=500
MAX_REFERENCE_IMAGE_MB=10
MAX_CONCURRENT_TASKS_PER_USER=2
DAILY_IMAGE_LIMIT=20
DAILY_VIDEO_LIMIT=5
```

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
| `provider_auth_error` | 401/403 | 检查 API Key、账号开通与区域 |
| `provider_rate_limited` | 429 | 自动延迟重试（提交阶段）或降低频率 |
| `provider_rejected` | 4xx | 检查模型 ID、尺寸/时长/比例/参考图是否符合文档 |
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

## 7. 真实验证状态（重要）

截至本次交付：

- **未进行任何付费真实调用**（用户明确选择）。
- Ark Seedream / Seedance 的请求/响应映射、错误分类与异步轮询已用 Mock/单元测试覆盖，但**未对真实账号验证**。
- ComfyUI 仅用 fake HTTP 测试了异步提交/轮询/下载；未连接真实 ComfyUI。
- Atlas Cloud 与 Luma 为旧适配，均有单元测试覆盖超时/状态映射，但未真实验证；Luma 不支持参考图。
- 因此所有模型的 `verified` 均为 `false`。在正式对外提供生成能力前，必须配置密钥并做一次最小额度真实验证，再在界面/文档中更新状态。

## 8. 已知限制

- Seedream 的 `seed`/负面提示词能力按官方文档保守标注；不支持的参数会被拒绝或丢弃（负面提示词来自分镜默认值时丢弃，不发送）。
- 多参考图、组图、视频编辑/延长、首尾帧等高级能力尚未开放。
- 第三方状态若出现未知值，按轮询错误退避处理，不会猜测成功。
- 单机 SQLite + 本地文件存储；扩展到多机时需将任务队列与素材迁移到 PostgreSQL/对象存储。
