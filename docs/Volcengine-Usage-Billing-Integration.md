# 火山方舟官方用量与火山引擎账单集成

本文说明 AIGV Studio 如何接入火山方舟（Ark）只读模型用量和火山引擎费用中心官方账单，以及如何严格区分官方数据、AIGV 本地任务记录和内部 GPU 估算。

> 状态：官方用量与官方账单/余额均已接入，并通过真实只读接口验证（2026-10-31）。账单金额口径、对账和分账限制详见 `docs/Volcengine-Billing-Reconciliation.md`。真实 AK/SK 只写入服务器 `.env`，不会出现在数据库、审计、日志、接口响应或文档中。

## 1. 边界与数据来源

| 数据 | 来源 | 是否官方 | 说明 |
|---|---|---|---|
| 模型调用任务、排队/运行/下载/总耗时 | AIGV `generation_tasks` | 否 | 本地真实任务记录 |
| 图片/视频/LLM Provider 返回的 usage | 服务商响应 | 是（服务商响应） | 只在服务商真实返回时保存，缺失为 NULL |
| Ark 官方账号用量 | `GetInferenceUsage` / `GetInferenceTaskUsage` | 是 | 账号级，可能包含同一账号下的其他应用 |
| GPU 资源池/节点/渲染费用 | AIGV 内部 `resources` / `render_jobs` / `billing_usage_records` | 否 | 内部调度与内部核算，不是火山方舟费用 |

明确禁止：

- 不把模型请求数换算为 GPU 数量、显存占用或 GPU 利用率。
- 不把内部虚拟账户余额称为火山引擎余额。
- 不用任务成功数替代计费成功数。
- 不在 Provider 未返回 Token 时填入推算值。
- 不把多个用户共用的 Key/账号官方总额按任务次数平均成“真实用户消费”。

## 2. 管理凭据（与推理 Key 完全分离）

推理生成仍使用原有 `ARK_API_KEY`/`ARK_BASE_URL`。新增的管理凭据只用于火山引擎 OpenAPI 只读查询：

```env
VOLCENGINE_USAGE_ENABLED=false
VOLCENGINE_BILLING_ENABLED=false
VOLCENGINE_ACCESS_KEY_ID=
VOLCENGINE_SECRET_ACCESS_KEY=
VOLCENGINE_ARK_REGION=cn-beijing
VOLCENGINE_BILLING_REGION=cn-north-1
VOLCENGINE_ARK_PROJECT=default
VOLCENGINE_USAGE_SYNC_ENABLED=false
VOLCENGINE_BILLING_SYNC_ENABLED=false
VOLCENGINE_USAGE_SYNC_INTERVAL_S=1800
VOLCENGINE_BILLING_SYNC_INTERVAL_S=86400
VOLCENGINE_USAGE_LOOKBACK_DAYS=31
VOLCENGINE_BILLING_LOOKBACK_MONTHS=3
VOLCENGINE_SYNC_TIMEOUT_S=20
VOLCENGINE_SYNC_MAX_RETRIES=2
VOLCENGINE_ARK_BILL_PRODUCT_FILTER=
VOLCENGINE_ARK_BILL_SPLIT_DIMENSION=
VOLCENGINE_ARK_API_KEY_RESOURCE_ID=
```

- 代码只使用 `VOLCENGINE_ACCESS_KEY_ID` + `VOLCENGINE_SECRET_ACCESS_KEY`，**永不回退到 `ARK_API_KEY`/`VOLCENGINE_API_KEY`**。
- 只配置一半凭据时启动仅告警，现有图片/视频/LLM 生成不受影响。
- `.env` 必须 `chmod 600`，已被 `.gitignore` 忽略；`docs/用户信息.csv` 也已加入忽略规则。
- 强烈建议在火山引擎 IAM 创建独立子用户，仅授予以下 API 的只读权限（控制台权限点名称以实际 IAM 策略编辑器为准）：
  - Ark 用量：`GetInferenceUsage`、`GetInferenceTaskUsage`、`GetInferenceRequestUsage`
  - 费用中心：`ListBillOverviewByProd`、`ListBill`、`ListBillDetail`、`ListSplitBillDetail`、`QueryBalanceAcct`
  - 不授予资源创建、删除、变更、充值、退订等权限。
- 拿到根账号或主账号 AK/SK 只用于临时联调时，应在联调后轮换，并替换为最小权限子用户。

## 3. 官方接口与签名

### 3.1 Ark 用量

- `POST https://ark.cn-beijing.volcengineapi.com/?Action=GetInferenceUsage&Version=2024-01-01`
  - service `ark`，region `cn-beijing`
  - Body：`StartTime`/`EndTime`（`YYYY-MM-DD`，北京时间）、`QueryInterval=Day|Hour`、`ProjectName`、可选 `Filters`
  - 响应 `Result.Fields` + `Result.Data` 二维数组，按列名动态解析
  - 为获得模型/API Key 维度，使用 `Filters` 中 `ApikeyID`/`ModelName` 的空 `Values`（官方文档语义：不过滤但返回该列）；真实环境已验证可用。若某账号不支持，代码会回退无 Filters 并在状态中标记 `dimension_filters_supported=false`
- `POST ...?Action=GetInferenceTaskUsage&Version=2024-01-01`，Body `{"TaskID": "..."}`
  - 使用 `generation_tasks.provider_job_id`，只查真实异步任务
  - 返回 `APIKeyID`、`ModelName`、`BillingStatus`、`OutputTokens`、`Resolution` 等；不假设所有模型都按 Token 计价
- `POST ...?Action=GetInferenceRequestUsage&Version=2024-01-01`，Body `RequestID` + `QueryHour`
  - 只在确有**响应体 `id`** 的同步请求上调用
  - Seedream 图片响应没有该 ID；**绝不把响应头 request id 当作查询 ID**
  - LLM 的 OpenAI 兼容响应有 `id`，但只有确认属于平台管理账号时才适合查询；默认不自动逐请求查询

### 3.2 签名

`backend/volcengine/auth.py` 按火山引擎官方 SignerV4 规则实现：

- UTC `X-Date`、`X-Content-Sha256`、`Content-Type: application/json`
- 规范 query 排序 + RFC3986 编码、规范 signed headers、body SHA-256
- 签名密钥链 `date/region/service/request`
- `Authorization: HMAC-SHA256 Credential=AK/date/region/service/request, SignedHeaders=..., Signature=...`
- 不引入 Python SDK 依赖；只用 `hmac`、`hashlib`、`requests`
- 真实只读接口已验证签名（2026-10-31，`GetInferenceUsage` 成功返回账号级数据）

### 3.3 错误与限流

`backend/volcengine/client.py` 统一分类：

`unconfigured`、`disabled`、`unauthorized`、`no_permission`、`throttled`、`invalid_param`、`network`、`invalid_response`、`sync_error`

- 5 QPS 进程内节流
- 429/5xx/网络错误有限重试，尊重 `Retry-After`
- 错误消息、日志、状态表不包含 AK/SK、Authorization、完整响应
- 重定向拒绝跟随

## 4. 本地用量记录

新增表 `ai_model_usage_records`，字段包括：

`dedupe_key`、`task_id`、`user_id`、`project_id`、`provider`、`model_id`、`provider_job_id`、`provider_request_id`、`api_key_resource_id`、`input_tokens`、`output_tokens`、`total_tokens`、`image_count`、`video_duration_s`、`usage_unit`、`usage_source`、`billing_status`、`resolution`、`usage_payload`、`recorded_at`、`synced_at`

规则：

- 图片：优先 `usage.generated_images` 作为 `image_count`；没有该字段时使用实际返回图片数，并在 payload 标记 `image_count_source=data_length`；`output_tokens/total_tokens` 仅作参考，缺失为 NULL
- 视频：只保存 Provider 真实返回的 `usage.completion_tokens/total_tokens`；`input_tokens` 通常为 NULL；`duration` 仅来自 Provider 响应
- LLM：保存 `usage.prompt_tokens/completion_tokens/total_tokens` 及响应 `id`
- `usage_payload` 只保留 ID/model/status/usage/resolution 等白名单字段，绝不保存图片/视频 URL、Base64、Prompt、Header 或 API Key
- 幂等键：`task_id + 来源 + provider_job_id/request_id`；重复轮询/同步更新同一行
- 写入失败不影响用户生成任务；失败/取消请求只有在 Provider 真实返回用量时才记录
- `api_key_resource_id` 只来自官方响应或管理员显式配置，绝不使用 API Key 密钥内容

采集位置：

- `backend/generation_service.py`：Seedream 同步图片、Seedance 异步视频提交/轮询
- `backend/providers/llm_provider.py` + `backend/task_worker.py`：LLM 响应 `id/usage`
- `backend/usage_records.py`：统一落库、upsert、脱敏

## 5. 官方用量同步

新增表：

- `volcengine_usage_snapshots`：按账号、API Key、模型、版本、接入点、计费状态、项目、日期/小时聚合；`snapshot_key` 唯一，重复同步 UPSERT 更新，不重复累计
- `volcengine_sync_status`：`ark_usage`/`ark_billing`/`ark_balance` 的 `never_run/running/success/failed/disabled/unconfigured` 状态、最近成功时间、错误类别、处理条数
- `ai_model_usage_records` 中 `usage_source=official_api`：通过 `GetInferenceTaskUsage` 补充异步视频任务的官方用量（每轮限量）

策略：

- 默认回看 31 天，按天聚合；周期同步默认 30 分钟（由独立 worker 执行，不在每个页面请求中同步）
- 手动同步由管理员按钮触发，3 次/分钟限流
- 跨进程 DB 抢占锁，避免并发同步
- 失败保留上次有效快照和 `last_success_at`，状态表记录脱敏错误
- GET 管理接口只读数据库快照，不调用第三方
- 同步行为写入审计事件 `admin_ark_sync` / `volcengine_sync`，只含 scope、时间范围、条数、错误类别

## 6. 管理 API 与页面

全部 `@admin_required`（普通用户 403、匿名 401）：

- `GET /api/admin/ark/status`
- `GET /api/admin/ark/usage/summary?days=7|30`
- `GET /api/admin/ark/usage/models?days=...`
- `GET /api/admin/ark/usage/trend?days=...`
- `GET /api/admin/ark/usage/tasks?days=...&limit=&offset=`
- `POST /api/admin/ark/usage/sync`
- `GET /api/admin/ai-usage/users?days=...`
- `GET /api/admin/ai-usage/tasks?days=...`
- `GET /api/admin/ai-usage/reconciliation?days=...`

每个返回都带：

```json
{
  "source": "aigv_local | volcengine_usage | internal_estimate | volcengine_billing",
  "source_label": "中文说明",
  "last_synced_at": 1793431590,
  "is_estimated": false,
  "billing_period": "...",
  "currency": null
}
```

前端在“算力调度”页面新增管理员可见的“AI 模型服务”标签：

- 本地卡片：模型调用次数、图片/视频任务、运行中/成功/失败、成功率、平均完成耗时
- 官方卡片：官方请求数、输入/输出/总 Token、图片数、最近同步、同步状态
- 本地/官方按模型表、7/30 天真实趋势、任务性能、最近任务
- 无数据/未配置/无权限显式提示；**不使用演示曲线**
- 非管理员不显示标签，且直接调用 API 返回 403

## 7. 内部 GPU 计费修复

`backend/billing_service.py::get_billing_summary()` 之前的 `total_amount` 只汇总最近 20 条记录，已修复为：

```sql
SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM billing_usage_records
```

返回增加 `total_amount_scope="all_time"`、`usage_record_count`、`source="internal_estimate"`、`source_label`、`is_estimated=true`。页面明确标注“内部 GPU/渲染核算（非火山官方账单）”“内部核算余额（非火山账户余额）”。

## 8. 已知限制

- 官方用量是账号级，可能包含同一账号下其他应用、其他 Key 的调用；不能等同于 AIGV 全部业务量。
- 多用户共用一个平台 Ark Key 时，官方账号/Key 级总量无法天然按用户精确拆分；用户维度只展示 AIGV 本地任务/Provider 响应记录。
- 官方用量接口有延迟；页面显示最近同步时间，过期快照会被标记为 stale，不宣称为实时。
- 不同模型计量单位不同（图片张数/Token/请求数）；页面分开展示，不强行相加或换算金额。
- 本阶段不提供“应用侧金额估算”，因为未配置经过验证的单价；绝不伪造估算费用。
- Seedream 同步请求没有可用于 `GetInferenceRequestUsage` 的响应体 ID，因此不自动查询单请求官方用量；官方账号级用量仍覆盖这些调用。

## 9. 真实验证记录

已通过真实只读验证（2026-10-31）：

- Signature V4 签名成功
- `GetInferenceUsage` 成功返回最近 3 天账号级用量
- 动态 `Fields/Data` 解析成功
- 空 `Values` 维度过滤成功返回 `ApikeyID`/`ModelName`
- 临时数据库完整同步写入 2 条官方用量快照
- 线上 `enrich_task_usage` 对一条真实 Seedance 终态任务调用 `GetInferenceTaskUsage` 成功：返回 `OutputTokens=108900`、`BillingStatus=normal`、`Resolution=720p`；接口未返回 `TotalTokens`，数据库保持 NULL，不推算
- `QueryBalanceAcct` 成功返回官方余额（CNY）
- `ListBillOverviewByProd(2026-10)` 返回 2 个产品：`Doubao-Seedream`、`ark_bd`
- `ListBillDetail(2026-10, GroupPeriod=2)` 返回 3 条明细
- 2026-09 及更早账期当前账号无数据
- `ListSplitBillDetail` 返回“当前账号未开通分账账单能力”；代码将其显示为未归属，不阻断主账单同步
- 临时数据库完整同步写入 overview/bill/detail 快照和余额快照

已配置：

```env
VOLCENGINE_ARK_BILL_PRODUCT_FILTER=ark_bd,Doubao-Seedream
VOLCENGINE_ARK_BILL_SPLIT_DIMENSION=
```

## 10. 官方账单接入（已完成）

新增 `backend/volcengine/billing_client.py` 与 `billing_sync_service.py`：

- `ListBillOverviewByProd`、`ListBill`、`ListBillDetail`、`ListSplitBillDetail`、`QueryBalanceAcct`
- 金额全部 Decimal/TEXT，不跨口径或跨币种相加
- 当月/上月账单、余额、按模型/配置、按日、用户分账、对账
- `volcengine_bill_snapshots`、`volcengine_balance_snapshots`、`volcengine_sync_status`
- 管理 API：`/api/admin/ark/billing/summary|details|balance|sync-status|models|trend|attribution|reconciliation` 与 `POST /sync`
- 费用页官方账单区域；内部 GPU 估算保持独立
- `scripts/run_ark_sync.py` + `deploy/aigv-ark-sync.service` 定时同步
- 详细金额口径、真实结果和限制见 `docs/Volcengine-Billing-Reconciliation.md`
