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

**Legacy 创作 worker（TTS/合成/精修/导出）没有租约，启动时会回收 running 任务；只允许运行一个 legacy worker 进程。** 不要把 `START_TASK_WORKER=true` 与独立的 `run_generation_worker.py` 同时使用。

### 2.1 媒体依赖（配音 / 时间线 / 成片）

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-noto-cjk fontconfig
ffmpeg -version && ffprobe -version
ffmpeg -hide_banner -filters | grep -E 'subtitles|amix|alimiter|sidechaincompress'
fc-match 'Noto Sans CJK SC'

# Piper：可放在独立 venv，避免污染 Flask 运行环境
python3 -m venv /opt/piper-venv
/opt/piper-venv/bin/pip install piper-tts
sudo ln -sf /opt/piper-venv/bin/piper /usr/local/bin/piper
# 中文音色与配置必须成对放入 data/tts_models/
# 音色注册表 data/tts_voices.json 只列实际安装且验证可用的音色
piper --model data/tts_models/zh_CN-huayan-medium.onnx \
  --output_file /tmp/piper-test.wav <<< "中文配音测试"
ffprobe -v error -show_entries format=duration,stream=codec_name -of json /tmp/piper-test.wav
```

`.env` 需设置 `PIPER_BIN`、`PIPER_MODEL_PATH`、`TTS_VOICES_FILE`、`TTS_MODEL_DIR`、`FFMPEG_BIN`、`FFPROBE_BIN`、`SUBTITLE_FONT_NAME`。没有安装的模型不会出现在 `/api/creative/tts/voices` 的可用列表里；没有授权文件时系统预设音乐库为空。

### 2.2 媒体工作流数据库迁移

```bash
# 先备份，再执行增量迁移（可重复执行，不删除已有项目/分镜/任务）
cp data/aigv.db data/aigv.db.bak-$(date +%Y%m%d%H%M%S)
.venv/bin/python scripts/migrate_workflow_v2.py --backup
```

迁移新增时间线版本、音频元数据、分镜媒体版本、最终成片指针和阶段计时字段；旧的 WAV 误写入 `srt_path` 的指针会被清空，但音频文件保留。

## 3. Nginx

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/aigv
sudo ln -s /etc/nginx/sites-available/aigv /etc/nginx/sites-enabled/aigv
sudo nginx -t && sudo systemctl reload nginx
```

生产必须使用 HTTPS；`SESSION_SECURE=true` 时 Cookie 不会通过 HTTP 发送。

### 当前部署例外（2026-10-30）

当前站点暂无域名/证书，继续使用 `http://<host>:8000`，未安装 Nginx，也未开启
`CREDENTIAL_REQUIRE_HTTPS`。这意味着 API Key 在浏览器到服务器之间可能以明文传输；
`/api-settings` 页面与启动日志会显示风险提示。后续取得域名后可按下述步骤启用 HTTPS：

1. 安装 Nginx/certbot，配置证书与 80→443 跳转，设置 `X-Forwarded-Proto`。
2. `.env` 设置 `SESSION_SECURE=true`、`TRUST_PROXY=true`、`CREDENTIAL_REQUIRE_HTTPS=true`。
3. Gunicorn 改为绑定 `127.0.0.1:8000`，防火墙禁止公网访问 8000。

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

## 7. 火山方舟官方用量/账单同步（2026-10-31）

线上实际 service 名为 `aigv-studio.service`（工作目录 `/sdc/恒联项目/cursor-blender-mcp-master`，root 运行）。新增的官方用量/账单同步由独立 `aigv-ark-sync.service` 执行，不在 Web 请求中同步。

### 7.1 配置

在 `.env` 中配置独立的管理凭据（不要使用 `ARK_API_KEY`）：

```env
VOLCENGINE_USAGE_ENABLED=true
VOLCENGINE_BILLING_ENABLED=true
VOLCENGINE_ACCESS_KEY_ID=
VOLCENGINE_SECRET_ACCESS_KEY=
VOLCENGINE_ARK_REGION=cn-beijing
VOLCENGINE_BILLING_REGION=cn-north-1
VOLCENGINE_ARK_PROJECT=default
VOLCENGINE_USAGE_SYNC_ENABLED=true
VOLCENGINE_BILLING_SYNC_ENABLED=true
VOLCENGINE_ARK_BILL_PRODUCT_FILTER=ark_bd,Doubao-Seedream
# 当前账号未开通分账账单，保持为空
VOLCENGINE_ARK_BILL_SPLIT_DIMENSION=
```

- 建议使用最小权限 IAM 子用户，只授予 Ark 用量与费用中心只读接口；不要授予资源变更/充值/退订权限。
- `.env` 必须 `chmod 600`；`docs/用户信息.csv` 不得提交。
- 只配置一半 AK/SK 时启动仅告警，不影响图片/视频/LLM 生成。

### 7.2 备份、迁移与验证

```bash
# 先备份（SQLite backup API；不含 .env）
.venv/bin/python scripts/backup_data.py --data-dir ./data --output ./backups

# 单次只读验证/补数
.venv/bin/python scripts/run_ark_sync.py --once --usage-only
.venv/bin/python scripts/run_ark_sync.py --once --billing-only --bill-period 2026-10

# 检查同步状态
.venv/bin/python - <<'PY'
from backend.database import get_database
from backend.volcengine.store import get_all_sync_statuses
for row in get_all_sync_statuses(get_database('./data/aigv.db')):
    print(row['sync_key'], row['status'], row['last_success_at'], row['records_processed'])
PY
```

### 7.3 定时 worker

```bash
sudo cp deploy/aigv-ark-sync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aigv-ark-sync.service
sudo systemctl status aigv-ark-sync.service --no-pager
```

用量默认每 30 分钟、账单默认每日；由 `VOLCENGINE_USAGE_SYNC_ENABLED`/`VOLCENGINE_BILLING_SYNC_ENABLED` 控制。worker 与 Web 共用 SQLite，每次同步通过 `volcengine_sync_status` 跨进程锁避免并发。

### 7.4 Web 部署

先确认没有排队/运行中的生成任务，再优雅重载；不健康时完整重启：

```bash
.venv/bin/python - <<'PY'
import sqlite3
print(sqlite3.connect('data/aigv.db').execute(
    "SELECT status, COUNT(*) FROM generation_tasks WHERE status IN ('queued','submitting','running') GROUP BY status"
).fetchall())
PY
kill -HUP "$(systemctl show -p MainPID --value aigv-studio.service)"
sleep 3
systemctl is-active aigv-studio.service
curl -fsS http://127.0.0.1:8000/api/health
```

### 7.5 回滚

1. 停 `aigv-studio.service` 与 `aigv-ark-sync.service`。
2. 恢复阶段前备份的 `data/aigv.db`（清理 `-wal`/`-shm`）。
3. 回退代码，关闭 `VOLCENGINE_USAGE_ENABLED`/`VOLCENGINE_BILLING_ENABLED`/`*_SYNC_ENABLED`。
4. 重启并健康检查。新增表/列增量兼容，旧代码可忽略。
