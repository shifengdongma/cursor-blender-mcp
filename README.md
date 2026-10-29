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

> 当前环境 `.env` 仅有旧 Luma / Atlas 密钥，没有 `ARK_API_KEY`，因此图片生成在实际运行时会明确显示“未配置”，不会返回假结果。

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

**重要：本次交付未进行真实付费 API 调用；所有模型的 `verified=false`。** 正式使用前请配置密钥并做最小额度真实验证。

## 用户 API 配置

登录后打开 `/api-settings`，可为自己保存 5 类 Provider 凭据：OpenAI 兼容 LLM、火山方舟、OpenAI Images、Atlas Seedance、Luma。

- 密钥加密存储（Fernet，见 `CREDENTIAL_ENCRYPTION_KEY`），只回显末四位掩码，API/日志/审计均不含明文。
- 用户凭据优先于环境变量；未配置时回退平台默认。平台密钥只与平台默认 Base URL 成对使用。
- Base URL 必须为 HTTPS 公网地址（拒绝私网/回环，`ALLOW_INSECURE_PROVIDER_URLS` 生产保持 false）。
- 用户在该 Provider 有排队/运行中任务时，修改或删除凭据返回 409，避免运行中任务失去账号。
- 保存后可点击“测试连接”验证可达性（LLM 走 `/models`，其余走 HEAD，不发起计费生成）。

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

保留旧 `/api/jobs` 十阶段流水线、Prompt 编排、Blender 导出、资产管理、算力调度展示、监控告警与知识库/创意模板。演示数据默认关闭（`DEMO_MODE=false`），演示模块仅在明确标注时使用。
