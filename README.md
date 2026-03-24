# Cursor + Blender + MCP + Luma（Web 版 PoC）

本项目用于在一台轻量 Linux 云主机上搭建 **AI 视频生成平台（PoC）**：

- **Blender**：只负责“空间/镜头约束资产”（白模、相机轨迹、glb 等）导出，不做重渲染。
- **Luma**：负责最终视频生成（Prompt → Video）。
- **Web**：提供一个简单易用的前端页面用于提交任务、轮询状态、预览结果。

> 适配说明：当前服务器为 `Python 3.6`（CentOS7/KVM 常见），因此后端选用 **Flask**（而不是 FastAPI）。

---

## 目录结构

```text
.
├─ app.py
├─ requirements.txt
├─ .env.example
├─ data/                      # 运行时自动生成（jobs 产物）
├─ backend/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ jobs.py
│  ├─ prompt_builder.py
│  ├─ blender_runner.py
│  └─ providers/
│     ├─ __init__.py
│     └─ luma.py
├─ blender/
│  └─ blender_batch.py
└─ web/
   ├─ index.html
   ├─ app.js
   └─ styles.css
```

---

## 快速开始（PoC）

### 1) 安装依赖

```bash
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
```

### 2) 配置环境变量

```bash
cp .env.example .env
vi .env
```

至少需要：

- `LUMA_API_KEY`

可选：

- `BLENDER_BIN`（默认 `blender`，如果不在 PATH 里请填绝对路径）
- `DATA_DIR`（默认 `./data`）

### 3) 启动服务

```bash
python3 app.py
```

打开浏览器访问：

- `http://<server-ip>:8000/`

---

## 工作流说明

1. 前端提交表单 → `POST /api/jobs`
2. 后端创建 job 记录，并在后台线程中执行：
   - （可选）调用 Blender 批处理导出 `scene.glb`、`camera_path.json`
   - 构建六格 Prompt（参考 `SKILL.md` 思路）
   - 调用 Luma 创建 generation + 轮询，直到拿到 `video_url`
3. 前端轮询 → `GET /api/jobs/<job_id>`，成功后展示视频链接

---

## 重要提示（生产化前必须做）

- **安全**：PoC 仅做结构化输入，不允许任意 Python 注入；上线前仍需加鉴权（Token/Basic Auth）与限流。
- **存储**：PoC 将产物写入本地 `data/jobs/<job_id>`；生产建议接对象存储（S3/OSS/MinIO）。
- **Blender 兼容**：CentOS7 可能因 `glibc` 过旧导致 Blender 二进制不可运行；建议将 Blender 执行迁移到 Ubuntu 容器/独立机器。

