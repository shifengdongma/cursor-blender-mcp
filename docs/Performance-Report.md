# AIGV Studio 生成与媒体性能报告（2026-10-30）

本报告只记录实际执行过的测量。没有为了 benchmark 触发任何付费 LLM/图片/视频生成。

## 1. 真实任务基线（来自 `data/aigv.db` 既有记录）

| 任务 | 类型 | 实际总耗时 | 说明 |
|---|---|---:|---|
| `5223ed63...` | Ark Seedream 图片 | 13s | 同步生成 + 下载 + 落库 |
| `86a65e11...` | Ark Seedance 视频 | 125s | 提交后异步轮询；包含 10s 轮询节拍 |
| `3c8cd7c2...` | LLM 分镜失败 | 188s | 3 次 60s 超时 + 退避 |

这些记录没有完整的阶段时间戳（旧代码只有整数秒级的 created/claimed/completed），所以只能说明端到端量级，不能拆出纯模型推理时间。视频任务的主要耗时来自服务商排队与生成，本地代码无法显著降低。

## 2. 本地基准方法

`scripts/benchmark_generation.py` 使用：

- 临时 `DATA_DIR` + 独立 SQLite
- 真实 `GenerationService.submit_task` / `finalize_task` / `TaskService` 队列/租约/序列化路径
- 本地假 Provider（可配置延迟），不访问任何外部 API
- 真实 FFmpeg/FFprobe 生成并合成 3 个 1 秒镜头

```bash
.venv/bin/python scripts/benchmark_generation.py --tasks 12 --provider-delay 0.02
.venv/bin/python scripts/benchmark_generation.py --tasks 100 --provider-delay 0
```

## 3. 结果

### 12 个任务，假 Provider 延迟 0.02s

| 指标 | 平均 | 中位数 | P95 |
|---|---:|---:|---:|
| 本地提交总耗时 | 33.58ms | 32.90ms | 36.75ms |
| 队列等待（创建→领取） | 2.41ms | 2.40ms | 2.70ms |
| Provider 请求段 | 22.65ms | 22.28ms | 24.54ms |
| 本地持久化 | 0.42ms | 0.41ms | 0.45ms |

### 100 个任务，假 Provider 延迟 0

| 指标 | 平均 | 中位数 | P95 |
|---|---:|---:|---:|
| 本地提交总耗时 | 7.11ms | 5.07ms | 14.92ms |
| 队列等待 | 1.48ms | 1.04ms | 2.60ms |
| Provider 请求段 | 1.14ms | 0.83ms | 2.22ms |
| 本地持久化 | 0.35ms | 0.34ms | 0.42ms |

### 任务列表序列化（同一批 100 条任务）

| 方式 | 耗时 |
|---|---:|
| 旧式逐条查询（每个任务查资产/工件） | 12.55ms |
| 批量查询 `public_task_dicts` | 4.38ms |

约减少 65% 的列表序列化时间，且结果集相同（`same_result=true`）。这是本次代码层面可验证的前后对比。

### 三镜头 720p 合成

| 场景 | 耗时 |
|---|---:|
| 3×1s 镜头 + 静音轨，CRF 26 | 约 0.63–0.67s |

合成耗时与镜头数、分辨率、滤镜、字幕烧录和服务器 CPU 强相关；真实 1080p + 烧录字幕会明显更慢。

## 4. 已实施的优化

1. **阶段计时**：`generation_tasks` 增加 created/claimed/provider request/provider job/finished/download/persist/completed 时间戳和 `timing_json`；新增 `GET /api/generation/tasks/<id>/timing` 与管理员聚合。`provider_elapsed_ms` 明确包含服务商排队，不冒充纯推理。
2. **批量序列化**：任务列表、项目任务列表使用 `get_assets_by_ids` + `list_artifacts_for_tasks` + `public_task_dicts`，去掉逐任务 N+1。
3. **公平调度**：GenerationWorker 在提交与轮询之间交替，避免大量到期轮询持续饿死新任务；租约/claim SQL 未改变。
4. **周期恢复**：worker 每 `GENERATION_RECOVERY_INTERVAL_S` 清理过期租约，进程不重启也能恢复卡住的 `submitting/running` 任务。
5. **下载连接复用**：`media_fetcher.download_url` 使用线程局部 `requests.Session`，连接/读取超时分开；SSRF、重定向、大小、魔数校验保持不变。
6. **前端轮询**：自适应 1s→2s→5s、页面隐藏降频、`AbortController`、项目/任务守卫、仅状态变化回调、终态才刷新模块；刷新后从 `/workflow` 的 active_tasks 恢复 TTS/精修/合成/导出。
7. **真实后期制作**：Piper 每镜头一次进程 + 一次后处理；时间线合成为单次 FFmpeg filter graph；精修/合成/导出使用任务级目录，避免并发覆盖。

## 5. 未实施的优化及原因

- **GenerationWorker 默认并发仍为 1**：没有生产负载数据证明提高并发不会触发 Provider 429/SQLite 写锁；部署时可在压测后设置 `GENERATION_WORKER_CONCURRENCY=2`，但不作为默认。
- **Provider 提交/轮询未全面切换到 Session**：现有测试大量 monkeypatch `requests.post`；直接替换会掩盖真实错误路径。下载路径已安全复用；后续可在补充测试后逐个 Provider 迁移。
- **图片/视频推理时间**：由服务商决定，本地只能优化排队、提交、下载、持久化和前端可见延迟。
- **参考图 data URL**：继续使用受控 base64，不公开用户素材为远程 URL；未做对象存储临时链接。
- **计时列命名**：`*_at_ms` 列当前存放 UTC epoch 秒（浮点，`time.time()`），`/timing` API 统一换算为毫秒；直接读 SQL 的管理员需注意单位。

## 5.1 最终回归与复测（2026-10-31）

- 全量自动化：`AIGV_ENV=test .venv/bin/python -m pytest tests/ -q` → **427 passed**（包含真实 Piper + FFmpeg 的 TTS → 时间线 → 烧录字幕 MP4 → ZIP 下载 E2E）。
- 20 任务复测（假 Provider 延迟 0.01s）：提交端到端平均 22.86ms、队列等待 2.59ms、持久化 0.40ms；任务列表批量 1.05ms vs 逐条 2.54ms；三镜头 720p 合成 658.76ms。
- 真实付费 Provider 推理延迟不包含在上述数字中。

## 6. 结论

- 本地队列、序列化和持久化已在毫秒级；对于图片约 13s、视频约 125s 的真实任务，主要延迟仍在服务商侧。
- 本次优化可减少多用户任务互相排队、轮询饿死提交、下载重复建连、任务列表 N+1 和前端无意义重绘。
- 任何“优化后模型推理更快”的说法都不成立；本报告只对本地代码路径负责。
