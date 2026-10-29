# 部署说明（单机首期）

目标部署形态：Nginx (HTTPS) → Gunicorn (Flask) → SQLite + 本地素材目录，生成任务由**独立 Worker 进程**处理。

## 1. 准备

```bash
cd /srv/aigv-studio
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：AIGV_ENV=production、SECRET_KEY、ARK_API_KEY、SESSION_SECURE=true 等
.venv/bin/python scripts/init_db.py
# 如存在旧 users.json，先备份并迁移：
.venv/bin/python scripts/migrate_auth_v2.py --apply
# 创建首个管理员（交互输入，不会写日志）：
.venv/bin/python scripts/create_admin.py
```

## 2. 启动/停止

```bash
sudo cp deploy/aigv.service deploy/aigv-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aigv aigv-worker
sudo systemctl status aigv aigv-worker
sudo journalctl -u aigv -f
sudo journalctl -u aigv-worker -f
sudo systemctl restart aigv aigv-worker
```

Gunicorn 使用 `wsgi:app`，多 Worker 时 `START_TASK_WORKER=false`，避免每个 Web 进程各起一套后台线程。生成任务只由 `aigv-worker` 领取（SQLite `BEGIN IMMEDIATE` + 租约保证原子性）。

## 3. Nginx

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/aigv
sudo ln -s /etc/nginx/sites-available/aigv /etc/nginx/sites-enabled/aigv
sudo nginx -t && sudo systemctl reload nginx
```

生产必须使用 HTTPS；`SESSION_SECURE=true` 时 Cookie 不会通过 HTTP 发送。

## 4. 备份与恢复

```bash
# 备份数据库 + catalog/jobs；加 --include-assets 连同 data/assets 一起打包
python3 scripts/backup_data.py --data-dir ./data --output ./backups --include-assets

# 恢复（停服后）：
# 1) 解压备份目录到临时位置
# 2) 用备份中的 aigv.db 覆盖 data/aigv.db（先停 aigv 与 aigv-worker）
# 3) 需要时解压 assets.tar.gz 回 data/assets
# 4) 启动服务
```

备份脚本不会复制 `.env` 或任何密钥，请单独安全保管环境变量文件。

## 5. 日志与容量

- systemd journal 已带轮转；如使用文件日志，请配置 `logrotate`。
- `GENERATION_*_DEADLINE_S` 控制任务最长等待；`MAX_GENERATION_DOWNLOAD_MB` 控制单文件大小。
- 定期清理孤立生成文件前，先确认 `task_artifacts`/分镜/时间线不再引用。

## 6. 升级

1. 先备份数据库与 `data/`。
2. 拉取代码、安装依赖、执行迁移脚本（均为幂等/增量）。
3. 先重启 worker，再重启 web；观察 `needs_review` 与失败任务。

不要在没有实际执行环境的情况下宣称已完成线上部署。
