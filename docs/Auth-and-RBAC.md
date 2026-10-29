# 账户、会话与权限设计（实现版）

本文档对应当前代码，而不是早期原型设计。核心实现位于：

- `backend/auth_service.py`：账户、密码、锁定、会话版本、管理员操作
- `backend/identity_service.py`：平台租户 + 业务 `users` 行 + 个人工作区 + 项目成员
- `backend/web_security.py`：全站鉴权 / CSRF / 安全响应头
- `backend/auth_middleware.py`、`backend/access.py`：角色、权限与对象所有权
- `backend/admin_routes.py`、`backend/profile_routes.py`：管理员与个人中心 API
- `app.py`：登录/注册/登出/状态/CSRF 路由与应用装配

## 1. 数据模型

### `auth_users`（登录账户，唯一认证来源）

| 字段 | 说明 |
|---|---|
| `id` | UUID，主键 |
| `username` | 登录名，大小写不敏感唯一 |
| `email` | 可空，大小写不敏感唯一 |
| `password_hash` | Werkzeug `pbkdf2:sha256` |
| `nickname` / `bio` / `avatar_path` | 个人资料 |
| `role` | 平台角色：`admin` / `user` |
| `status` | `active` / `disabled` |
| `is_active` | 兼容字段，与 `status` 同步维护 |
| `session_version` | 会话失效版本；改密/改角色/禁用/撤销会话时 +1 |
| `failed_login_count` / `locked_until` | 连续失败计数与临时锁定 |
| `last_login_at` / `created_at` / `updated_at` | UTC 时间戳 |
| `tenant_id` | 平台租户（默认 `tenant_platform`） |
| `user_id` | 关联业务 `users.id`（与 `auth_users.id` 相同） |

`database.py` 在 `init_database()` 中执行增量 `_ensure_column` 迁移，保留存量字段与数据；唯一索引为大小写不敏感索引，创建失败时记录告警而不是清库。

`users.json` 仅在 `scripts/migrate_auth_v2.py` 中一次性读取。运行时认证**不再**回退到 JSON；`tests/test_auth_hardening.py::test_users_json_is_never_an_authentication_source` 覆盖该行为。

### `users` / `projects` / `project_memberships`

- `users` 是业务账户（租户/项目外键使用），不代表平台管理员权限。
- 每个注册账户自动创建个人工作区项目 `workspace_<auth_user_id>` 与 `owner` 成员关系。
- `project_memberships.role` 是**项目角色**（`owner`/`admin`/`editor` 等），不等于平台角色。
- `tenant_service.check_permission()` 只认 `permissions` 列表中的显式权限；项目 owner/admin 不再隐式获得算力/云资源权限。

## 2. 注册、登录与会话

### 注册

- 用户名 3–32 位（中文/字母/数字/下划线/点/短横线），昵称 ≤40，密码 8–128，邮箱可选并校验格式。
- 密码两次一致、必须勾选协议；所有新账号 `role=user`，请求体中的 `role` 被忽略。
- 用户名/邮箱冲突返回 409；注册写入在 `BEGIN IMMEDIATE` 事务内完成（账户 + 租户 + 业务用户 + 工作区 + 成员关系）。
- `ALLOW_REGISTRATION=false` 时返回 403 `registration_closed`。
- 注册成功即建立真实 Session，并轮换 CSRF Token。

### 登录

- 数据库查询用户 → 禁用检查 → 锁定检查 → 密码哈希校验。
- 失败累计 `failed_login_count`，达到 `LOGIN_MAX_FAILURES` 后锁定 `LOGIN_LOCKOUT_SECONDS`。
- 成功后清空失败计数/锁定、更新 `last_login_at`，`session.clear()` 后写入：
  - `auth_uid`
  - `auth_session_version`
- Session 不保存密码、邮箱等完整敏感数据。
- 登录/注册接受可选 `next`，服务端用 `safe_redirect_target()` 清洗后返回 `redirect_to`；`//evil`、`https://evil`、反斜杠与 `/api/*` 均回退 `/`。
- 管理员重新启用账户时同时清空锁定字段。

### 会话失效

每次请求由 `auth_service.load_current_user()` 重新读取数据库并校验：

- 用户存在且 `status=active`、`is_active=1`
- `session_version` 与 Session 中一致
- 未处于临时锁定

修改密码、管理员改角色/禁用、管理员撤销会话都会递增 `session_version`，旧会话立即 401。

### Cookie / CSRF

- Cookie：`aigv_session`、`HttpOnly`、`SameSite=Lax`、生产默认 `Secure`；`SESSION_LIFETIME_DAYS` 控制有效期。
- 生产环境 `SECRET_KEY` 必须显式配置；缺失或占位值启动即失败。开发环境使用 `DATA_DIR/.secret_key` 持久化随机密钥。
- CSRF Token 存放在 Session，`GET /api/auth/csrf` 下发；所有 POST/PUT/PATCH/DELETE 必须带 `X-CSRF-Token`（或表单 `_csrf_token`）。
- 鉴权顺序：非公开路由先判断登录（API 401 / 页面 302），再校验 CSRF；登录/注册属于公开路由但仍需 CSRF，缺失返回 403。
- 退出登录 `session.clear()`。

## 3. 路由保护

`backend/web_security.py` 的 `before_request` 是统一入口：

公开白名单（精确匹配）：

```
GET/HEAD /login, /register
GET/HEAD /api/auth/status, /api/auth/csrf
GET/HEAD /api/health
POST /api/auth/login, /api/auth/register
GET /favicon.ico
```

静态资源：`/web/*` 仅允许 JS/CSS/图片/字体/媒体扩展名；`*.html` 直接 404，防止绕过页面路由。
`/web/runtime-config.js` 由 Flask 生成，不作为物理文件暴露。

- 未登录访问受保护 HTML → `302 /login?next=<safe>`。
- 未登录访问 `/api/*` → `401 {"success":false,"error":"unauthorized",...}`。
- 已登录但平台管理员接口 → 403；`/admin*` 页面返回 `403.html`。
- `/compute-platform*` 需要 `view_compute`（平台管理员天然拥有）。
- 对象级权限由 `backend/access.py` 在每个路由内检查，不能依赖前端参数。

## 4. 平台角色与项目角色

| 能力 | user | admin |
|---|---|---|
| 创意工作台 / 图片 / 视频 / 自己的历史 | ✅ | ✅ |
| 修改自己的资料/密码/头像 | ✅ | ✅ |
| 管理自己的素材与项目 | ✅ | ✅ |
| 查看全部平台用户 / 禁用 / 改角色 | ❌ | ✅ |
| 查看平台统计 / 全平台生成任务 | ❌ | ✅ |
| 管理算力 / 云主机 / 全局计费 | 需显式权限 | ✅ |

- 平台管理员权限只来自 `auth_users.role`，不能通过注册请求、项目成员身份或前端字段获得。
- 最后一名有效管理员不能被降级或禁用（服务层事务内检查）。
- 管理员不能修改自己的角色/状态，避免误锁死。
- 管理员操作写入 `ops_events` 审计（`AUDIT_ENABLED` 可关闭）。

## 5. API 一览

| API | 方法 | 权限 |
|---|---|---|
| `/api/auth/register` / `login` / `logout` / `status` / `csrf` | POST/GET | 公开/登录 |
| `/api/user/profile` | GET/PATCH | 登录 |
| `/api/user/password` | PUT | 登录（成功后强制重新登录） |
| `/api/user/avatar` | GET/POST/DELETE | 登录 |
| `/api/admin/users` | GET | 管理员 |
| `/api/admin/users/<id>` | GET/PATCH | 管理员 |
| `/api/admin/users/<id>/role` | PATCH | 管理员 |
| `/api/admin/users/<id>/status` | PATCH | 管理员 |
| `/api/admin/users/<id>/sessions/revoke` | POST | 管理员 |
| `/api/admin/stats` | GET | 管理员 |
| `/api/admin/audit-logs` | GET | 管理员 |
| `/api/generation/tasks?scope=all` | GET | 管理员才返回全平台 |
| `/api/generation/tasks/<id>/retry` | POST | 管理员 |

## 6. 管理员初始化与恢复

```bash
# 创建首个管理员（交互，或使用 ADMIN_USERNAME/ADMIN_PASSWORD 等环境变量）
python3 scripts/create_admin.py

# 提升已有普通用户（走服务层角色校验并写审计）
python3 scripts/create_admin.py --promote-existing <username>

# 离线重置密码（不打印密码，递增 session_version）
python3 scripts/reset_password.py --username <username>
```

不允许在公开注册接口创建管理员，仓库中也没有默认管理员密码。

## 7. 测试

```bash
python3 -m pytest tests/test_auth_hardening.py tests/test_app_security.py \
  tests/test_profile_admin.py tests/test_csrf.py tests/test_auth_migration.py -q
```

覆盖：注册校验/重复、登录/登出、锁定与启用解锁、会话版本、CSRF 顺序、开放重定向、最后管理员、项目 owner 非平台管理员、禁用账户访问、旧 Session 失效、users.json 非认证源。
