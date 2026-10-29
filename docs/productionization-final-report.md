# AIGV Studio 生产化改造最终交付报告

日期：2026-10-29  
范围：在现有 Flask + SQLite + 原生 JS 代码上完成账户/权限、管理员后台、真实生成任务管线、创意工作台闭环、生成历史、演示数据治理、测试与部署文档。

> 结论先说：**代码、自动化测试、HTTP 冒烟与部署样例已完成；未进行任何真实付费 AI API 调用，未在线上服务器执行部署，因此不得视为“真实生成已验证”或“已上线”。** 详细未验证项见第 8 节。

---

## 1. 本次实际完成的功能

### A. 账户与全站认证

- 登录账户统一使用 SQLite `auth_users`；`users.json` 仅由迁移脚本一次性读取，运行时不再作为认证来源。
- 注册：用户名/昵称/邮箱/密码校验、协议确认、用户名与邮箱大小写不敏感唯一、409 冲突、默认 `role=user`、事务内创建账户 + 租户 + 业务用户 + 个人工作区 + owner 成员。
- 登录：数据库校验、PBKDF2、禁用/锁定检查、失败计数与临时锁定、成功后重置计数、真实 Session、CSRF 轮换、`last_login_at`。
- 会话版本：改密、改角色、禁用、管理员撤销会话后旧 Session 立即 401。
- 全站守卫：未登录 API 401 / 页面 302 `/login?next=`；`/admin*` 管理员；`/compute-platform*` 需 `view_compute`；`/web/*.html` 404；静态 JS/CSS 仍可访问。
- CSRF：登录/注册也受保护；守卫先鉴权后 CSRF，匿名保护 API 无 Token 返回 401 而非 403。
- 登录 `next` 服务端清洗，防止开放重定向。
- 生产 `SECRET_KEY` 必须显式配置且 ≥32 字符；开发环境使用持久化文件密钥；生产 Cookie `Secure/HttpOnly/SameSite=Lax`。
- 管理员初始化 `scripts/create_admin.py`（交互/环境变量，无硬编码密码）；提升已有用户走服务层并写审计；离线重置 `scripts/reset_password.py`。
- 迁移保留旧账户密码哈希，并保留旧 `is_active=false` 的禁用状态；不导入 JSON 中的管理员角色。

### B. 个人中心与管理员后台

- `/profile`：头像、昵称、邮箱、简介、角色/状态、注册/最近登录、真实任务统计、最近 5 条任务；改密后强制重登；头像 PNG/JPEG/WebP 校验（有 Pillow 时完整解码，无 Pillow 时结构校验）。
- `/admin/users`：真实用户分页、搜索、角色/状态筛选、编辑资料、角色变更、禁用/启用、会话撤销、平台统计、审计事件。
- 新增“全平台生成任务”区块：类型/状态筛选、分页、创建者、参数、错误、取消、重试（管理员）。
- 最后一名有效管理员不能降级/禁用；管理员不能修改自己的角色/状态；敏感操作写审计。
- 导航显示头像/昵称、个人中心、管理员入口、退出；无 `view_compute` 的普通用户不显示算力入口。

### C. 真实生成任务管线

- 统一 Provider 注册表/能力矩阵，前端按能力显示尺寸、比例、时长、分辨率、音频、种子、参考图；未配置模型返回 `available=false` + 原因，不再静默隐藏。
- Ark Seedream 同步图片、Ark Seedance 异步视频适配；ComfyUI 改为**异步**（提交 `prompt_id`，轮询 history 后下载），不再在提交阶段阻塞 600 秒。
- Atlas Cloud / Luma 旧适配保留；超时/连接失败映射为 `ProviderUncertain`，不会自动重复扣费；Luma `dreaming` 视为运行中。
- 任务持久化：SQLite `generation_tasks` + `task_artifacts`；独立 Worker 原子领取（`BEGIN IMMEDIATE`）、租约、重启恢复、整体截止时间、幂等键、配额、取消、`needs_review`。
- 结果落库：单事务写入任务结果 + 素材 + artifact + 分镜关联；租约丢失回滚并删除文件；不产生孤儿记录。
- 临时签名 URL 由后端立即下载；下载器校验 http/https、公网 DNS、端口、重定向、内容类型、魔数、大小上限。
- 任务响应统一剔除 `provider_job_id/lease_owner/client_request_id` 等内部字段。
- 参考图写入 `target_asset_id`，排队期间禁止删除；删除生成作品时清理自身 artifact/输出指针，仍被分镜/时间线引用则 409。
- 图片/视频任务失败保留记录，不生成假素材；配额按用户/类型限制。

### D. 创意工作台与素材历史

- 项目/分镜/任务全部走后端 API；分镜编辑、复制、删除、上下移动落库；保存项目调用 `PUT /api/creative/projects/<id>`。
- 模型能力驱动参数；图生图参考图选择器（当前分镜图、已上传图片、临时上传）；生成器仅发送模型支持的可选参数。
- 图片结果真实预览、下载、参数查看、收藏（写入素材 metadata）、删除（409 时提示仍被引用）。
- 视频结果真实播放/下载/重新生成；取消任务显示“已取消”，不再当作成功；不伪造百分比，只显示真实阶段。
- `projectId`、当前图片/视频任务 ID、当前步骤、分镜索引持久化；刷新后恢复项目、分镜与进行中的图片/视频任务轮询；分析任务可重新执行。
- 素材库新增“生成历史”：类型/状态/日期筛选、分页、图片预览、视频播放、下载、参数、取消、删除、重新生成、“用此图生成视频”。
- 首页资产网格展示真实最近素材；素材搜索服务端 `q`；上传类型与扩展名不一致返回 400。

### E. 演示数据与界面治理

- `DEMO_MODE=false` 默认；生产不注入演示用户/GPU/任务；`aigv-demo-data.js` 在生产自置 null；后端演示注入仅在 `DEMO_MODE=true`。
- 算力平台：权限页改为真实项目成员只读展示，移除不存在的 `/permissions` POST 与 `mergedRoles`；真实项目来自 `/api/demo/context`；非管理员显示“仅管理员可查看”。
- 演示会话/图表/网络延迟只在演示模式使用并标注；生产显示空状态/`—`；节点/链路/会话补空状态。
- 保留 Three.js 影视/建筑/游戏演示模块，但生产模式有明确提示且不参与真实统计。
- 新增部署样例与 SQLite 一致性备份脚本。

---

## 2. 主要新增/修改文件

新增（节选）：

```
backend/access.py                 backend/identity_service.py
backend/web_security.py           backend/profile_routes.py
backend/admin_routes.py           backend/generation_models.py
backend/generation_routes.py      backend/generation_service.py
backend/generation_worker.py     backend/media_fetcher.py
backend/task_serializer.py        backend/providers/mock_provider.py
backend/providers/volcengine_image.py
backend/providers/volcengine_video.py
scripts/create_admin.py           scripts/migrate_auth_v2.py
scripts/reset_password.py         scripts/run_generation_worker.py
scripts/cleanup_demo_data.py      scripts/backup_data.py
web/api-client.js                 web/session-nav.js
web/profile.html/js               web/admin-users.html/js
web/403.html                      wsgi.py
deploy/aigv.service               deploy/aigv-worker.service
deploy/nginx.conf.example         deploy/README.md
docs/Auth-and-RBAC.md             docs/AI-Provider-Integration.md
docs/productionization-final-report.md
tests/test_auth_hardening.py      tests/test_generation_hardening.py
tests/test_generation_history.py  tests/test_app_security.py
tests/test_profile_admin.py       tests/test_route_protection.py
...
```

修改（节选）：`app.py`、`backend/config.py`、`backend/auth_service.py`、`auth_middleware.py`、`csrf.py`、`database.py`、`models.py`、`asset_service.py`、`task_service.py`、`storyboard_service.py`、`creative_project_service.py`、`creative_routes.py`、`demo_seed_service.py`、`tenant_service.py`、`provider_router.py`、`providers/base.py`、`providers/image_provider.py`、`seedance.py`、`luma.py`、`web/creative-studio.js`、`assets.js`、`compute-platform.js`、`app.js`、`auth.js`、`styles.css`、`.env.example`、`README.md`、两份总文档等。

## 3. 数据库与 API 变更

- `auth_users`：新增/规范 `role`、`status`、`session_version`、`nickname`、`avatar_path`、`bio`、`terms_accepted_at`、`failed_login_count`、`locked_until`、`last_login_at`、`tenant_id`、`user_id` 等；增量迁移，不清库。
- `generation_tasks`：新增 provider/model/provider_job_id/租约/重试/幂等/取消/输出素材等列；唯一幂等索引。
- 资产引用统计加入运行中生成任务；生成作品删除支持清理自身 artifact/输出指针。
- 新增/完善 API：`/api/user/*`、`/api/admin/*`、`/api/generation/*`、`/api/auth/csrf`；创意路由复用现有路径并改为真实任务。
- 所有 API 保持统一响应结构；分页/日期/状态筛选；任务响应脱敏。

## 4. 测试结果（本机实测）

运行环境：Python 3.10.12、pytest 9.1.1、Node 18.20.5。

```text
$ python3 -m pytest tests/ -q
223 passed in 75.64s

$ for f in web/*.js; do node --check "$f"; done
（全部通过）

$ python3 -m compileall -q app.py wsgi.py backend scripts tests
（通过）
```

新增/强化的覆盖：

- 认证：注册/重复/非法邮箱/弱密码/关闭注册、登录/错误密码/禁用/锁定/管理员启用解锁、旧会话失效、CSRF 顺序、开放重定向、生产密钥长度、`users.json` 非认证源、迁移保留禁用状态。
- 权限：普通用户 403、管理员 200、最后管理员、项目 owner 非平台管理员、跨用户任务/素材 403、管理员 `scope=all` 仅管理员、创建者信息。
- 生成：模型能力/未配置提示、图片尺寸/比例、ComfyUI 异步、Luma dreaming、提交超时→needs_review、取消竞态、幂等竞态、超时任务、租约丢失回滚、敏感字段、参考图删除 409、生成作品删除、项目删除清理、生成历史日期筛选。
- E2E：注册 → 项目 → 分镜 → Mock 图片任务 → Worker → 素材下载 → 分镜关联 → 跨用户 403。

HTTP 冒烟（临时数据目录、无 ARK Key、独立进程）：

```text
GET /                          → 302 /login?next=/
GET /api/auth/status           → 200 logged_in=false, capabilities=false
GET /login                     → 200
GET /web/creative-studio.html  → 404
GET /web/api-client.js         → 200
GET /api/generation/tasks      → 401
POST /api/auth/register        → 201，真实 Session/CSRF
GET /creative-studio           → 200（登录后）
GET /api/generation/models     → ark/comfyui 均 available=false 且给出原因
POST /api/generation/images    → 400 provider_not_configured（无假成功）
```

备份脚本冒烟：`scripts/init_db.py` 初始化临时库 → `scripts/backup_data.py` 生成一致性 `aigv.db` 快照，未复制 `.env`。

## 5. 验收标准对照（任务文档 8.5）

| # | 标准 | 结果 | 证据/限制 |
|---|---|---|---|
| 1 | 真实注册/登录可用 | ✅ | 认证测试 + HTTP 冒烟 |
| 2 | 未登录不能操作核心功能 | ✅ | 路由矩阵 + 冒烟 302/401 |
| 3 | 管理员/普通用户权限隔离 | ✅ | 认证/权限测试 |
| 4 | 个人中心保存真实信息 | ✅ | profile 测试 |
| 5 | 管理员管理真实账户 | ✅ | admin 测试 + 页面 |
| 6 | 图片生成真实执行或明确未验证 | ⚠️ 部分 | 代码+Mock 测试完成；无 ARK Key，**真实调用未验证** |
| 7 | 视频生成真实执行或明确未验证 | ⚠️ 部分 | 同上；旧 Luma/Atlas 也未真实验证 |
| 8 | 任务持久化，刷新不丢 | ✅ | SQLite + 前端持久化/恢复（后端测试；无浏览器自动化） |
| 9 | 结果保存并关联正确用户 | ✅ | Mock E2E：asset/owner/shot 关联、跨用户 403 |
| 10 | 生产模式无伪造用户/GPU/任务 | ✅ | DEMO_MODE 测试；算力演示门控 |
| 11 | 原有关键功能回归 | ✅ | 全量 223 项通过 |
| 12 | 测试报告 + 部署文档 | ✅ | 本报告 + `deploy/` + 两份新专项文档 |

## 6. 部署步骤（未在线上执行）

1. 备份现有 `data/` 与数据库；不要清库。
2. 安装依赖：`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`。
3. 复制 `.env.example` 为 `.env`，设置 `AIGV_ENV=production`、≥32 字符 `SECRET_KEY`、Provider Key、`SESSION_SECURE=true`。
4. `python3 scripts/init_db.py`；如有旧 `users.json`，先备份再 `python3 scripts/migrate_auth_v2.py --apply`。
5. `python3 scripts/create_admin.py` 创建首个管理员。
6. 安装 `deploy/aigv.service`（Gunicorn `wsgi:app`，多 worker，`START_TASK_WORKER=false`）与 `deploy/aigv-worker.service`（独立生成 Worker）。
7. 配置 Nginx/HTTPS（样例 `deploy/nginx.conf.example`），`client_max_body_size` 与上传限制一致。
8. 启动后验证：匿名 302/401、登录、管理员后台、模型列表；配置真实 Key 后做最小额度生成验证。
9. 备份：`python3 scripts/backup_data.py --data-dir ./data --output ./backups --include-assets`。

**未执行第 6–8 步于任何线上服务器；本报告不声称已部署。**

## 7. 保留的演示模块

- 算力平台 Three.js 影视/建筑/游戏可视化、故障模拟、部分图表、云主机模拟指标：仅 `DEMO_MODE=true` 且带“演示”标识。
- 知识库中的场馆/镜头/Prompt/引擎/资源池目录：静态知识资源，生产保留。
- 旧 `/api/jobs` 十阶段流水线与 Blender 导出：保留，不与新生成任务互相删除。

## 8. 未验证/待配置项

1. **真实 Ark Seedream 图片**：未调用；需 `ARK_API_KEY` 与账号开通的模型 ID。
2. **真实 Ark Seedance 视频**：未调用；需确认模型/时长/分辨率权限。
3. **ComfyUI**：仅 fake HTTP 测试；需真实实例与工作流/checkpoint。
4. **Atlas Cloud / Luma**：旧适配，未调用；Luma 不支持参考图。
5. **线上部署**：未执行；`deploy/` 是样例。
6. **浏览器端自动化**：未运行 Playwright/Cypress；前端仅做 `node --check` 与 HTTP 冒烟。刷新恢复、点击流程需人工验收。
7. **模型 ID**：默认值来自方舟文档/公开资料；必须在控制台确认实际可用 ID，`verified` 仍为 false。

## 9. 已知问题与下一步建议

- **限流为进程内内存**：多 Gunicorn worker 下登录/注册频率限制不共享；账户锁定在数据库内不受影响。生产建议接 Redis 或 Nginx 层限流。
- **needs_review 需人工处理**：提交超时且无第三方 ID 的任务不会自动重试；管理后台重试需确认可能重复扣费。
- **删除被分镜引用的生成图会 409**：当前没有“先清除分镜主图再删除”的一键 UI；可在项目内替换图片后再从历史删除。
- **分析任务刷新恢复**：图片/视频任务可恢复轮询；进行中的 LLM 分镜分析任务刷新后需重新触发，项目和已保存分镜不丢。
- **SQLite 单机**：高并发/多机需迁移 PostgreSQL + 对象存储；任务领取已做原子性，但 SQLite 写锁仍是扩展瓶颈。
- **头像 Pillow**：当前解释器未安装 Pillow 时使用结构校验降级；生产 `requirements.txt` 已包含 Pillow≥10。
- **旧演示数据清理脚本**：只清理已知 seed ID，不清理演示模式中用户自行生成的项目/素材；需人工确认后处理。
- **模型能力**：多参考图、组图、视频编辑/延长、首尾帧等未开放；按当前单模型最小闭环交付。

## 10. 文档索引

- 系统架构：`AIGV_Studio_系统架构文档.md`（附录为最新实现）
- 功能介绍：`AIGV_Studio_功能介绍文档.md`（附录区分真实/需配置/未验证/演示）
- 账户与权限：`docs/Auth-and-RBAC.md`
- Provider 接入：`docs/AI-Provider-Integration.md`
- 部署：`deploy/README.md`
- 本报告：`docs/productionization-final-report.md`
