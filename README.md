# AIGV Studio

面向文化场馆（剧院、画廊、博物馆、音乐厅）的 AI 图片/视频生成平台。包含真实账户体系、管理员后台、创意项目管理、分镜、AI 图片/视频生成、素材库与生成历史，并保留 Prompt 六模块编排、Blender 空间锚点与算力调度展示。

技术栈：**Python 3.10 + Flask 3 + SQLite + 原生 JavaScript + 可选 Blender / ComfyUI**。

## 快速开始（开发）

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：至少配置一个 Provider；生产必须配置 SECRET_KEY
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/create_admin.py   # 交互创建首个管理员，无硬编码密码
.venv/bin/python app.py
```

访问 `http://127.0.0.1:8000/`，未登录会跳转 `/login`。

## 两个入口怎么选

- **工作台（`/`）= 快速生成单条视频**：选场馆/模型/参数 → 预览 Prompt → 真实生成一条视频；结果自动下载并保存到素材库与生成历史，可播放、下载、取消。
- **创意生产（`/creative-studio`）= 多镜头项目工作流**：需求/分镜 → 概念图 → 视频 → 配音/素材 → 导出 ZIP 素材包。适合多镜头项目。
- 工作台不再展示调度/计费/监控等企业演示面板；这些内容统一在“算力调度”页。
- 旧 `/api/jobs` 十阶段流水线仅为兼容保留，不再由工作台 UI 调用；其历史结果只保存在 `data/jobs/`，不会迁移到新素材库/生成历史。

## 账户与权限

- 登录账户存于 SQLite `auth_users`，PBKDF2 哈希，Session + CSRF，`session_version` 使旧会话立即失效。
- 平台角色：`admin` / `user`；项目角色（owner/editor…）不等于平台管理员。
- 管理员：`/admin/users`（用户管理、角色/状态、会话撤销、统计、审计、全平台生成任务）。
- 个人中心：`/profile`（资料、头像、改密、真实生成统计与最近任务）。
- 设计说明：[docs/Auth-and-RBAC.md](docs/Auth-and-RBAC.md)

## AI 生成

- 图片：火山方舟 Seedream（主）、ComfyUI（本地，可选）。
- 视频：火山方舟 Seedance（主）、Atlas Cloud / Luma（旧适配，未验证）。
- 任务：SQLite `generation_tasks`，独立 Worker 原子领取 + 租约，支持重启恢复、幂等、取消、超时与 `needs_review`。
- 生成历史：素材库 → “生成历史”。
- 接入/排错/验证状态：[docs/AI-Provider-Integration.md](docs/AI-Provider-Integration.md)

**重要：连接测试的“密钥已验证”只代表 `/models` 鉴权通过，不代表模型已开通或可调用。** 真实生图/视频测试会单独提示计费；正式使用前请在服务商控制台开通模型，并通过 `/api-settings` 的“真实调用测试”确认。

## 用户 API 配置

登录后打开 `/api-settings`，可为自己保存 5 类 Provider 凭据：OpenAI 兼容 LLM、火山方舟、OpenAI Images、Atlas Seedance、Luma。

- 密钥加密存储（Fernet，见 `CREDENTIAL_ENCRYPTION_KEY`），只回显末四位掩码，API/日志/审计均不含明文。
- 用户凭据优先于环境变量；未配置时回退平台默认。平台密钥只与平台默认 Base URL 成对使用。
- Base URL 必须为 HTTPS 公网地址（拒绝私网/回环，`ALLOW_INSECURE_PROVIDER_URLS` 生产保持 false）。
- 用户在该 Provider 有排队/运行中任务时，修改或删除凭据返回 409，避免运行中任务失去账号。
- 保存后可点击“测试连接”做非计费三态探测（网络可达 / 密钥鉴权 / 模型是否列出；LLM、Ark、OpenAI 图片走 `/models`，Atlas/Luma 只做网络探测）。
- “真实调用测试”是独立的计费操作，必须确认费用；图片生成 1 张最低规格图，视频创建最短任务并尝试取消。

## 测试

```bash
python3 -m pytest tests/ -q
node --check web/creative-studio.js ...   # 前端语法检查
```

覆盖认证/权限/CSRF/迁移/文件安全/Provider 映射/任务竞态/历史筛选/演示模式等。

## 生产部署

推荐：Nginx (HTTPS) → Gunicorn（`wsgi:app`，多 worker）→ SQLite + 本地素材；生成 Worker 独立进程运行。

- 样例：[deploy/README.md](deploy/README.md)、`deploy/aigv.service`、`deploy/aigv-worker.service`、`deploy/nginx.conf.example`
- 备份：`python3 scripts/backup_data.py --data-dir ./data --output ./backups --include-assets`
- 生产配置：`START_TASK_WORKER=false`、`AIGV_ENV=production`、稳定的 `SECRET_KEY`、`SESSION_SECURE=true`

### Worker 部署方式

- **单进程部署（当前线上）**：`.env` 设置 `START_TASK_WORKER=true`，Web 进程内同时启动创意任务 Worker 与生成 Worker；只能运行一个 Web 进程，否则任务会被重复领取。
- **多进程部署**：Gunicorn 多 worker 时必须保持 `START_TASK_WORKER=false`，用 `deploy/aigv-worker.service`（`scripts/run_generation_worker.py`）独立运行 Worker。
- 分镜分析（LLM）任务由 Web 进程内的创意任务 Worker 处理；图片/视频任务由生成 Worker 处理。二者均以 `queued → running/submitting → succeeded/failed` 记录状态。

未在本机之外执行部署，`deploy/` 仅为可执行样例。

## 文档

- [AIGV_Studio_系统架构文档.md](AIGV_Studio_系统架构文档.md)
- [AIGV_Studio_功能介绍文档.md](AIGV_Studio_功能介绍文档.md)
- [docs/Auth-and-RBAC.md](docs/Auth-and-RBAC.md)
- [docs/AI-Provider-Integration.md](docs/AI-Provider-Integration.md)
- [docs/productionization-final-report.md](docs/productionization-final-report.md)

## 兼容性

保留旧 `/api/jobs` 十阶段流水线、Prompt 编排、Blender 导出、资产管理、算力调度展示、监控告警与知识库/创意模板。旧 `/api/jobs` 仅用于兼容，不再由工作台 UI 调用，历史任务不会迁移到新生成历史。演示数据默认关闭（`DEMO_MODE=false`），演示模块仅在明确标注时使用。

## 火山方舟官方用量与账单

管理员可在“算力调度 → AI 模型服务”查看 AIGV 本地真实模型任务和火山方舟官方用量；在“费用告警”查看火山引擎官方账单/余额，并与内部 GPU/渲染核算分开展示。

- 管理凭据与推理 `ARK_API_KEY` 完全分离：`VOLCENGINE_ACCESS_KEY_ID` / `VOLCENGINE_SECRET_ACCESS_KEY`，只读，只存在服务器 `.env`。
- 首次部署先备份数据库，再按 `deploy/README.md` 第 7 节执行单次 `scripts/run_ark_sync.py --once` 验证，最后启用 `aigv-ark-sync.service`。
- 当前线上验证：Ark 官方用量、余额和 2026-10 官方账单成功同步；当前账号未开通分账账单，官方金额保持未归属；2026-09 及更早无账单数据。
- 详细说明：`docs/Volcengine-Usage-Billing-Integration.md`、`docs/Volcengine-Billing-Reconciliation.md`、`docs/Audit-Log-Presentation.md`。
