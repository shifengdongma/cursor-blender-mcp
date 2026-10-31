# 管理员审计日志展示层

本文说明 AIGV Studio 管理员“审计日志”页面的可读性改造。底层 `ops_events` 表仍是唯一事实来源，展示层只读，不修改、不删除审计记录。

## 1. 数据来源

审计事件写入 `ops_events`：

| 字段 | 含义 |
|---|---|
| `event_type` | 原始事件码 |
| `message` | 审计结果（`success`/`failed`/`inconclusive`），旧 ops 事件为人类可读消息 |
| `actor_user_id` | 操作用户 ID（`auth_users.id`），系统事件为空 |
| `metadata.user_id` | 旧数据的操作人 ID |
| `metadata.target_type` | 目标类型（`generation_task`、`user`、`asset` 等） |
| `metadata.target_id` | 目标 ID |
| `metadata.details` | 事件细节（已脱敏） |
| `request_id` | 请求追踪 ID |
| `created_at` | Unix 秒级时间戳 |

结果没有独立列，展示层读取 `message`；目标信息没有独立列，展示层读取 `metadata.target_type/target_id`。

## 2. 展示层结构

`backend/audit_presenter.py` 负责：

- 中文事件映射（未知事件显示“其他系统事件”，保留原始事件码）。
- 操作人与目标名称解析。
- 批量查询：用户、生成任务、创意项目、素材、作业、渲染任务分别按类型一次查询。
- metadata 二次脱敏。
- 列表与详情数据结构组装。

`backend/admin_routes.py` 只负责参数校验、查询和调用展示层；不在路由里逐条查询关联表。

## 3. 操作人解析

优先级：

1. `auth_users` 中仍存在的用户：`昵称（用户名）`；无昵称时显示用户名。
2. 事件写入时的安全快照 `metadata.details.actor_display`（用户后来被删除时仍可追溯）。
3. 有操作人 ID 但用户和快照都不存在：`已删除用户`。
4. `login_failed` 且有 `metadata.details.username`：`未认证用户（用户名）`。
5. 完全没有操作人线索：`系统任务`。

新写入的审计事件在 `AuditService.record_audit()` 时查询一次用户并保存展示快照；快照只含昵称/用户名，不含邮箱、密码或凭据。历史日志无需重建即可显示。

详情弹窗中，已删除操作人的原始 ID 会脱敏为“前 8 位…后 4 位”。

## 4. 操作目标解析

只使用显式 `metadata.target_type` 和 `metadata.target_id`，**不根据 UUID 格式猜测类型**。

| target_type | 关联表 | 展示 |
|---|---|---|
| `user` | `auth_users` | 昵称（用户名）/ 已删除用户 |
| `generation_task` | `generation_tasks` + `creative_projects` | 任务类型 + Provider + 模型 + 项目名 |
| `project` | `creative_projects`，必要时回退 `projects` | 项目名称 |
| `asset` | `assets` | 素材名称 + 类型 |
| `job` / `job_history` | `job_history` | 生成作业短 ID + 状态 |
| `render_job` | `render_jobs` + `projects` | 渲染作业短 ID + 状态 + 项目 |
| `provider_credential` | 不查表，target_id 是 provider code | Provider 中文名 |

- 目标记录已删除：显示“原始目标已删除”；若 metadata 中有任务类型/Provider/模型快照，会补充展示。
- 旧版 ops 事件没有 `metadata.target_type`，但顶层 `job_id` 有值：按已知的 `job_id` 列关联 `job_history`。
- 无目标或未知 target_type：列表显示“—”，详情保留原始 type/id。

## 5. 事件与结果映射

映射覆盖 `backend/ops_service.py` 常量以及代码中实际发射的事件，包括登录/资料、管理员用户管理、生成任务、素材、AI 服务配置、创意项目、权限、算力/渲染/运维、以及本次新增的火山方舟同步事件。

常见示例：

| 原始事件 | 中文 |
|---|---|
| `login` | 用户登录 |
| `login_failed` | 登录失败 |
| `admin_role_change` | 修改用户权限 |
| `generation_submit` | 提交 AI 生成任务 |
| `generation_succeeded` | AI 生成任务完成 |
| `generation_failed` | AI 生成任务失败 |
| `generation_delete` | 删除生成记录 |
| `provider_credential_test` | 测试 AI 服务连接 |
| `rights_validated` | 版权校验完成 |
| `resource_scheduling` | 资源调度完成 |
| `admin_ark_sync` | 管理员同步火山方舟用量与账单 |

结果映射：`success`→成功、`failed`→失败、`pending`→处理中、`inconclusive`→结果不确定、`cancelled/canceled`→已取消、`warning`→警告、`error`→错误。非审计型 ops 事件按 severity 显示信息/警告/错误，保留原始 message 作为摘要。

任务类型映射：

| task_type | 展示 |
|---|---|
| `image` | AI 图片生成任务 |
| `video` | AI 视频生成任务 |
| `storyboard` | 创意分析任务 |
| `tts` | TTS 配音任务 |
| `compose` | 视频合成任务 |
| `refine` | 视频精修任务 |
| `export` | 视频导出任务 |

## 6. API

### GET `/api/admin/audit-logs`

保留原有 `items/total/limit/offset`，并继续支持旧参数：

- `action`（等价于 `event_type`）
- `actor_user_id`（等价于 `actor`）

新增：

- `event_type`：精确匹配事件码。
- `result`：精确匹配审计结果（`success`/`failed` 等）。
- `actor`：用户 ID、用户名或昵称；匹配不到用户时按原始 actor ID 查询，因此已删除用户 ID 也可筛选。
- `start_date` / `end_date`：`YYYY-MM-DD`，北京时间 UTC+8，含首尾。
- `offset` / `limit`：上限 200。

排序：`created_at DESC, id DESC`。

响应在旧字段基础上增加：

```json
{
  "event_label": "AI 生成任务完成",
  "result": "success",
  "result_label": "成功",
  "actor_display": "昵称（用户名）",
  "actor_display_snapshot": "昵称（用户名）",
  "target_type": "generation_task",
  "target_id": "...",
  "target_display": "AI 视频生成任务 · 火山方舟 Seedance · 模型 · 项目",
  "summary": "昵称（用户名）AI 生成任务完成，目标：..."
}
```

同时返回 `filters`（回显筛选）和 `filter_options`（事件类型/结果下拉选项）。旧字段 `message`、`severity`、`metadata`、`actor_user_id` 等保持不变。

### GET `/api/admin/audit-logs/<event_id>`

管理员只读详情：

- 事件类型/原始事件码、时间、操作人、操作对象、结果。
- 相关模型（provider/model_id）、相关项目（id/name）、错误原因。
- 请求 ID、原始事件 ID、原始目标 ID、脱敏后的操作人 ID。
- 已脱敏的完整 metadata。

不存在时返回 404 `audit_event_not_found`。

两个接口都要求平台管理员；不提供修改或删除审计记录的接口。

## 7. 敏感信息与不可否认性

- 写入时 `AuditService._sanitize_metadata()` 已对 password/secret/api_key/token/credential/access_key/private_key 等键做递归脱敏。
- 展示层再次递归脱敏，兼容历史日志。
- 详情弹窗使用 DOM `textContent` 渲染，metadata 使用 `<pre>`，不使用 `innerHTML`。
- 不展示 API Key、Access Key Secret、密码、Cookie、明文 Token 或认证头。
- 审计记录只追加，不提供页面修改/删除入口。

## 8. 前端

`web/admin-users.html` / `web/admin-users.js`：

- 默认显示最近 10 条；筛选栏在服务端执行。
- “查看全部记录”切换分页模式（每页 20 条）。
- 表格列：时间 / 事件 / 结果 / 操作人 / 操作目标 / 详情。
- 详情弹窗显示上述字段和脱敏 metadata。
- 加载失败显示 toast 和错误状态，不再静默吞错。

## 9. 测试

`tests/test_audit_presenter.py`：

- 事件标签覆盖、未知事件回退。
- 正常/无昵称/已删除/快照/系统/登录失败操作人。
- 所有目标类型、已删除目标、未知类型不猜测。
- 批量查询次数有上限。
- 嵌套敏感字段脱敏。
- 操作人快照在用户删除后仍可显示。

`tests/test_admin_audit_api.py`：

- 可读字段、旧字段兼容、筛选、日期、分页、详情、404。
- 普通用户 403、匿名 401。
- 已删除用户/目标显示、ID 脱敏。
- 敏感信息不出现在列表或详情响应中。
- 前端契约（筛选 ID、详情弹窗、详情 API）。

## 10. 已知限制

- 历史事件没有写入时快照；操作人仍存在时显示当前昵称/用户名，已删除时只能显示“已删除用户”+ 脱敏 ID。
- 旧版 ops 事件没有明确 target_type 且没有 `job_id` 时无法可靠关联业务目标，只显示“—”，不猜测。
- 审计列表按事件类型、结果、操作人、日期筛选；不提供全文搜索。
- 审计记录不提供导出或删除接口。
