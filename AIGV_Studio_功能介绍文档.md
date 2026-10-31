# AIGV Studio 功能介绍文档

## 一、产品概述

AIGV Studio 是一个面向文化场馆（剧场、美术馆、博物馆、音乐厅）的 **AI 智能视频生成平台**，将知识增强 Prompt 编排、Blender 空间锚点系统与多模型路由收敛为同一条创作链路，提供从"创意输入"到"视频交付"的完整工作流。

**核心价值：**
- 用结构化的黄金六模块 Prompt 公式替代凭经验的提示词工程
- 用 Blender 三维空间约束确保视频内容的物理一致性
- 用多模型统一路由器实现透明切换与降级容错
- 用多租户权限体系面向企业级协作场景

---

## 二、功能总览

### 2.1 功能矩阵

| 功能模块 | 描述 | 类型 |
|----------|------|------|
| Prompt 编排引擎 | 黄金六模块自动组装 + 知识库匹配 | 后端核心服务 |
| 任务流水线 | 10 阶段异步状态流转 + 全生命周期快照 | 后端核心服务 |
| 多模型路由 | Seedance/Luma 等厂商统一接入与智能路由 | 后端核心服务 |
| Blender 空间锚点 | 无头批处理 3D 场景导出 + 7 种相机动画 | 可选扩展 |
| 资产管理系统 | 3D 模型/图片/Prompt 文档的 CRUD + 上传下载 | 后端 + 前端 |
| 用户认证 | Session 登录/注册/登出 + 密码哈希安全 | 后端 + 前端 |
| 多租户管理 | 租户/用户/项目/成员四级权限体系 | 后端服务 |
| 算力调度 | GPU 资源池匹配 + 调度决策分配 + 监控 | 后端 + 前端 |
| 版权确权 | 资产版权校验 + 来源追踪链 + 不可变快照 | 后端服务 |
| 计费管理 | GPU/引擎/推流三部分费用核算与记录 | 后端服务 |
| 流媒体推流 | WebRTC/HLS 协议自适应配置 | 后端服务 |
| 运维监控 | 事件记录 + 采样监控 + 诊断日志 | 后端服务 |
| 创意生产工作台 | 6 步创意流程（需求分析→输出适配） | 前端演示 |
| 算力调度中心 | 7 Tab GPU 资源管理可视化 | 前端演示 |
| 工作台主页 | 双栏创作工作台 + Prompt 预览 + 实时状态轮询 | 前端交互 |

---

## 三、核心功能详解

### 3.1 知识增强 Prompt 编排引擎

**功能描述：** 将视频创作的创意参数自动转化为高质量 AI 视频 Prompt，无需手动编写提示词。

**实现方式：** `PromptOrchestrator`（backend/prompt_engine.py, 253 行）

**黄金六模块公式：**

| 模块 | 参数来源 | 作用 |
|------|----------|------|
| 1. 镜头语言 | shot.prompt（7 种运镜类型） | 锁定三维坐标系与观众视角 |
| 2. 主体材质 | subject_hint / venue.default_subject | 定义核心被摄对象与材质触感 |
| 3. 动态行为 | dynamics_hint / venue.default_dynamics | 锚定时间流逝与场景生命感 |
| 4. 环境空间 | environment_hint / venue.default_environment | 定义物理容器与建筑逻辑 |
| 5. 光影氛围 | lighting_hint / venue.default_lighting | 建立情绪与空间深度 |
| 6. 风格锚点 | style_anchor / venue.default_style | 控制完成度与稳定性 |

**智能回退策略：**
- 用户输入 → 知识库场馆预设 → 系统默认值，逐级回退，永不中断
- 场馆切换自动联动：标题、环境、光影、资产全部跟随
- 负向提示词自动合成：知识规则 + 场馆规则 + 资产规则 + 用户输入（去重拼接）

**工作流模式：**
- `text_to_video`：纯文本驱动，适合快速原型
- `hybrid_image_to_video`：图文混合，结合 Blender 空间锚点约束

**知识命中追踪：**
每个 Prompt 生成后记录 5 条知识命中记录：`venue`、`shot`、`model`、`asset`、`workflow`，完整可追溯。

### 3.2 异步任务流水线

**功能描述：** 视频生成任务从创建到交付的全生命周期管理，支持后台异步执行与前端实时轮询。

**实现方式：** `JobStore` + `start_job_worker()`（backend/jobs.py, 459 行）

**10 阶段状态机：**

```
queued → knowledge_ready → rights_validated → resource_scheduling
  → blender_exporting(条件) → provider_submitted → provider_running
  → streaming → billing_recorded → succeeded/error
```

**关键特性：**
- 每个任务生成 UUID，隔离存储于 `data/jobs/<uuid>/`
- 每个阶段写入对应 JSON 文件，完整保留执行轨迹
- 后台线程异步执行（`daemon=True`），不阻塞 Flask 主进程
- 前端每 5 秒轮询 `/api/jobs/<id>` 获取最新状态
- 线程安全的内存缓存 + 原子文件写入（tmp → rename）
- preview-only 模式自动跳过视频生成阶段

**任务结果包含：**
- `prompt_bundle`：六模块 Prompt + 负向提示词
- `knowledge_hits`：5 条知识匹配记录
- `schedule_result`：GPU 节点分配结果
- `engine_session`：4 类渲染引擎会话
- `stream_session`：WebRTC/HLS 推流参数
- `monitor_summary`：3 个监控采样点
- `rights_result`：版权校验结果
- `billing_result`：GPU/引擎/推流三部分费用
- `video_url`：最终生成的视频地址
- `ops_events`：运维事件记录

### 3.3 多模型智能路由

**功能描述：** 统一接入多个 AI 视频生成模型，支持透明路由切换与降级容错。

**实现方式：** `ProviderRouter`（backend/provider_router.py, 137 行）

**支持的模型与路由模式：**

| 模型 | 模式 | 执行通道 | 说明 |
|------|------|----------|------|
| Seedance v1.5 Pro | native | seedance | 真实执行通道，推荐使用 |
| OpenAI Sora 2 | demo-route | seedance | 展示 Sora 2，由 Seedance 代理执行 |
| Google Veo 3 | demo-route | seedance | 展示 Veo 3，由 Seedance 代理执行 |
| Runway Gen-3 Alpha | demo-route | seedance | 展示 Gen-3，由 Seedance 代理执行 |
| Kling 3.0 | demo-route | seedance | 展示 Kling 3.0，由 Seedance 代理执行 |
| Luma Dream Machine | optional | luma | 可选备用通道 |

**四种路由模式：**

| 模式 | 前端展示 | 实际执行 | 用途 |
|------|----------|----------|------|
| `native` | 模型 A | 模型 A | 真实生产 |
| `demo-route` | 模型 A | 通道 B | 申报演示，前端展示未部署的模型 |
| `preview-only` | 模型 | 不执行 | 仅展示不生成 |
| `optional` | 模型 | 按需 | 可选的备用通道 |

**API Key 防护：**
- 每个 Provider 创建前检查对应 API Key
- 未配置则抛出明确错误信息，不会静默失败
- 支持 Seedance 完整的文生视频参数：duration、resolution、aspect_ratio、camera_fixed、audio

**轮询机制：**
- 提交后进入轮询等待：5 秒间隔，900 秒超时
- 支持 completed/succeeded/done 完成状态检测
- 支持 failed/error/canceled 失败状态处理
- 超时后保留最后一次响应，标记 `_timeout` 字段

### 3.4 Blender 空间锚点系统

**功能描述：** 利用 Blender 三维引擎创建场景空间约束，生成相机动画与 GLB 资产，确保视频的空间一致性。

**实现方式：** `BlenderExecutionAdapter` + `BlenderRunner`（backend/blender_adapter.py + backend/blender_runner.py）

**两种运行模式：**

**模式 1 - local_batch（当前可用）:**
- Flask 后端通过 `subprocess.Popen` 启动无头 Blender（`--background`）
- 传入 `scene_spec.json`（摄像机参数 + 资产几何体配置）
- Blender 执行 `blender_batch.py` 脚本：创建占位几何体 → 设置材质 → 相机动画关键帧 → 导出
- 300 秒超时控制，超时自动终止
- 导出产物：`scene.glb`（3D 场景）、`camera_path.json`（相机轨迹）、`artifacts.json`（元数据）

**模式 2 - mcp_remote（预留待开启）:**
- 基于 JSON-RPC over stdio 的实时交互协议
- MCP 服务端运行在 Blender 内部（`blender_agent.py`）
- 暴露工具：`list_scene_objects`、`run_python_script`、`capture_viewport`
- stdout 劫持机制（`os.dup2`）保持通信管道干净

**7 种相机运动类型：**

| 运镜 | 类型 ID | 运动方式 | 视觉效果 |
|------|---------|----------|----------|
| 环绕 | orbit | 水平 360° 旋转 | 全景空间展示 |
| 推近 | dolly_in | 沿 Y 轴平滑推进 | 空间层次递进 |
| 升起 | crane_up | 沿 Z 轴垂直上升 | 纵向空间展开 |
| 跟拍 | tracking | 沿 X 轴水平移动 | 平行空间扫描 |
| 穿梭 | fpv | 对角线运动 | 动态空间探索 |
| 微距 | macro_pan | 近距离平移 | 细节特写 |
| 低角 | low_angle_glide | 贴地滑行 | 仰角空间感 |

**触发条件：** `ENABLE_BLENDER_EXPORT=true` AND `workflow_mode="hybrid_image_to_video"` AND 资产非 `text_only`

### 3.5 用户认证系统

**功能描述：** 完整的用户注册/登录/登出功能，密码安全存储。

**实现方式：** `AuthService`（backend/auth_service.py, 76 行）+ Flask Session

**认证特性：**
- 密码使用 werkzeug `generate_password_hash` 进行 pbkdf2:sha256 哈希存储
- 验证使用 `check_password_hash` 避免明文比较
- 用户数据存储在 `data/users.json` JSON 文件
- 用户名唯一性检查，注册时防止重复
- 密码至少 6 位字符，用户名至少 2 个字符
- Flask Session 管理登录状态
- 登出时清除 Session，不留痕迹
- 提供 `/api/auth/status` 检查当前登录状态

### 3.6 多租户权限体系

**功能描述：** 企业级 SAAS 多租户架构，支持租户/用户/项目/成员四级关系与角色权限控制。

**实现方式：** `TenantService`（backend/tenant_service.py, 99 行）+ 演示数据自动注入

**四级关系模型：**
```
Tenant（租户）
  ├── User（用户）
  │     └── role: owner / producer / editor / viewer
  ├── Project（项目）
  │     └── render_mode: cinematic / interactive / vr_walkthrough
  └── ProjectMembership（成员关系）
        └── role + permissions: [submit_job, approve_rights, view_billing, view_monitor]
```

**权限检查逻辑：**
- 检查 `project_memberships` 表中的角色与权限列表
- `owner` / `admin` 角色拥有全部权限（超级管理员）
- 其他角色按 `permissions` JSON 列表精确控制

**演示数据：**
- 默认注入：`华中文博演示集团`（旗舰版）
- 2 个用户：`陈策展`（数字内容总监，owner）、`刘制片`（项目制片，editor）
- 1 个项目：`中期汇报沉浸式样片`
- 启动时幂等注入，不重复创建

---

## 四、企业服务功能

### 4.1 算力调度服务

**功能描述：** GPU 计算资源的智能匹配与分配，支持本地/公有云/边缘三种资源池。

**实现方式：** `SchedulerService`（backend/scheduler_service.py, 116 行）

**资源池类型：**

| 池类型 | GPU 示例 | 适用场景 |
|--------|----------|----------|
| local_gpu | A10 | Blender 空间锚点渲染 |
| public_cloud | A100 | UE5/Unity 云渲染 |
| edge_gpu | L40 | SteamVR 低延迟推流 |

**调度策略：**
- 按 `engine_target` 自动匹配最优资源池
- `blender_anchor` → local_gpu
- `ue5_cloud` / `unity_cloud` → public_cloud
- `steamvr_stream` → edge_gpu
- 同池内选择队列深度最浅的节点
- 每次分配写入 `resource_allocations` 表，可审计追溯

**监控采样：**
- 自动生成 3 个监控采样点（模拟 GPU 利用率/显存/网络/码率/延迟/FPS）
- 支持心跳检测，标记节点健康状态

### 4.2 版权确权服务

**功能描述：** 资产版权全生命周期管理，包括校验、来源追踪与不可变快照。

**实现方式：** `RightsService`（backend/rights_service.py, 72 行）

**版权校验维度（4 项检查）：**
1. **审批状态**：需 `approved` 或 `approved_with_notice`
2. **有效期**：检查 `expires_at` 是否过期
3. **用途范围**：检查 `usage_scope` 是否匹配（internal_demo / client_review / public_showcase）
4. **版权记录**：是否存在 `asset_rights` 记录

**来源追踪链：**
- `asset_provenance_events` 表记录资产的完整生命周期
- 支持事件类型：ingest（接入）、approval（审批）、warning（告警）
- 每个事件包含时间戳、操作者、摘要、元数据

**不可变版权快照：**
- 每次任务生成 `rights_snapshot.json`
- 包含数字摘要（`immutable_digest`），防篡改
- 关联完整的 provenance_chain 来源链

### 4.3 计费管理服务

**功能描述：** 按 GPU 使用、引擎会话、推流三个维度精细化费用核算。

**实现方式：** `BillingService`（backend/billing_service.py, 83 行）

**三部分计费模型：**

| 计费项 | 单价 | 计算公式 |
|--------|------|----------|
| GPU 调度 | 120 CNY/小时 | duration_s / 3600 |
| 引擎会话 | 80 CNY/小时 | GPU小时 × 1.15 |
| 编码推流 | 40 CNY/小时 | GPU小时 × 1.25 |

**费用管理：**
- 每个任务完成时生成 `billing_snapshot.json`
- 存入 `billing_usage_records` 表，支持项目/租户维度汇总
- 支持 `billing_accounts` 账户管理（余额、套餐、配额）
- 演示数据注入旗舰套餐账户：余额 48,000 CNY

### 4.4 流媒体推流服务

**功能描述：** 根据使用场景自动配置推流协议与参数。

**实现方式：** `StreamService`（backend/stream_service.py, 32 行）

**三种推流配置：**

| 配置 | 协议 | 延迟 | 码率 | FPS | 适用场景 |
|------|------|------|------|-----|----------|
| low_latency | WebRTC | 35ms | 9.8 Mbps | 72 | SteamVR 低延迟 |
| balanced | HLS | 75ms | 12.5 Mbps | 30 | 通用平衡模式 |
| showcase | HLS | 120ms | 18.0 Mbps | 30 | 高质量展示 |

### 4.5 引擎管理服务

**功能描述：** 4 种渲染引擎的统一配置管理与会话创建。

**实现方式：** `EngineService`（backend/engine_service.py, 51 行）

**支持的引擎：**

| 引擎 | 类型 ID | 渲染模式 | 推流模式 |
|------|---------|----------|----------|
| Blender Anchor | blender_anchor | cinematic | balanced |
| UE5 Cloud | ue5_cloud | cinematic | showcase |
| Unity Cloud | unity_cloud | interactive | balanced |
| SteamVR Stream | steamvr_stream | vr_walkthrough | low_latency |

### 4.6 运维监控服务

**功能描述：** 全链路运维事件记录与查询，支持按项目维度追溯。

**实现方式：** `OpsService`（backend/ops_service.py, 41 行）

**运维事件记录：**
- 每个任务流水线关键节点自动记录运维事件
- 事件类型包括：`rights_validated`、`resource_scheduling`
- 严重级别：info / warning / error
- 每个事件关联 tenant_id、project_id、job_id

---

## 五、前端页面功能

### 5.1 工作台主页（`/`）

**技术实现：** `index.html`（605 行）+ `app.js`（585 行）+ `styles.css`（5,200 行）

**功能布局（5 区域双栏工作台）：**

```
左侧：配置面板                  右侧：状态与预览区
┌──────────────────┐         ┌──────────────────────────┐
│ 01 基础任务设置   │         │ 演示上下文               │
│   - 任务标题      │         │   [租户] [用户] [项目]    │
│   - 视频时长      │         ├──────────────────────────┤
│                  │         │ 任务状态 / 10阶段进度列表  │
│ 02 演示上下文     │         ├──────────────────────────┤
│   - 租户/用户     │         │ Prompt 预览               │
│   - 项目/引擎目标 │         │   六模块卡片 + 最终Prompt  │
│   - 渲染/推流配置 │         ├──────────────────────────┤
│   - 用途范围      │         │ 结果输出                  │
│                  │         │   视频播放 + 任务详情       │
│ 03 场馆与模型选择 │         ├──────────────────────────┤
│   - 场馆类型      │         │ 监控与运维面板             │
│   - 生成模型      │         │   调度 | 监控 | 版权       │
│   - 空间锚点      │         │   计费 | 运维日志          │
│                  │         └──────────────────────────┘
│ 04 镜头语言      │
│                  │
│ 05 环境与光影     │
│                  │
│ [预览Prompt]     │
│ [生成视频]       │
└──────────────────┘
```

**交互特性：**
- **实时预览机制**：下拉框变更 → 自动静默调用 `/api/prompt/preview` → 更新六模块卡片
- **场馆联动**：场馆切换 → 自动填充标题、环境、光影、资产
- **5 秒轮询**：任务提交后每 5 秒查询 `/api/jobs/<id>` → 更新阶段进度与结果面板
- **竞态防护**：3 个请求计数器（preview/submit/poll），防止快速操作导致状态错乱
- **暗金奢华 UI**：CSS 变量体系，`data-ui-status` 属性驱动全局状态样式

**页面其他展示区：**
- Hero 引导区：品牌介绍 + 三大核心能力展示
- 模型展示网格：6 个 AI 模型的 route_mode 与描述
- 黄金六格公式展示：6 步模块的可视化说明
- 空间资产库：场馆对应的占位几何体展示
- 项目指标：素材库容量、示范场景、软件成果、服务企业

### 5.2 创意生产工作台（`/creative-studio`）

**技术实现：** `creative-studio.html`（123 行）+ `creative-studio.js`（~2,900 行）+ `aigv-demo-data.js`

**6 步创意生产流程：**

| 步骤 | 模块 | 核心功能 |
|------|------|----------|
| 01 | 需求分析 | 创作需求表单 → AI 语义分析 → 自动生成 6 个分镜脚本 → 编辑/复制/删除/排序/确认 |
| 02 | 概念图生成 | 分镜 → 4 张概念参考图 → 选择模型 → 设置关键帧 → 收藏/查看/删除 |
| 03 | 视频生成 | 基于关键帧生成视频 → 时长/运镜/运动强度/稳定性/分辨率/帧率/模型 → 进度条 → 取消/重试 |
| 04 | 多模态增强 | 4 种音色配音 + 5 种 BGM + 音效库 → 5 轨时间线（视频/配音/音乐/音效/字幕）→ 片段 CRUD |
| 05 | 人机精调 | 左右对比面板 → 6 项基础滤镜 + 8 项专业调色 + 6 项 AI 批量处理 |
| 06 | 输出适配 | 9 个输出平台 → 参数自动填充 → 导出目录树 → 复制 Manifest → 模拟下载 |

**当前模式：** 纯前端演示模式，数据来自 `aigv-demo-data.js`，localStorage 持久化进度

### 5.3 算力调度中心（`/compute-platform`）

**技术实现：** `compute-platform.html`（~270 行）+ `compute-platform.js`（~1,320 行）+ `aigv-demo-data.js`

**7 个功能 Tab：**

| Tab | 核心功能 | 交互类型 |
|-----|----------|----------|
| 运行总览 | 10 项指标卡片（总任务/成功/失败/就绪GPU/队列/推流会话/费用）+ 4 SVG 图表 | 可视化展示 |
| 云渲染 | 渲染会话表格 → 点击查看详情抽屉 → 状态循环切换（排队→渲染→完成→失败） | 交互管理 |
| GPU 调度 | 资源池卡片 + 节点搜索/筛选 + 表格详情 + 抽屉面板 | 交互管理 |
| 调度任务编排 | 8 字段表单（任务类型/需求GPU/优先级/时长/区域/推流/引擎/渲染模式）→ 智能匹配结果卡片 | 流程仿真 |
| 智能感知与传输优化 | 算力节点感知（8 节点 GPU/VRAM/温度/心跳）+ 链路状态（5 条时延/抖动/丢包/带宽）+ 故障告警（红闪动画/自动恢复/确认恢复）+ 3 个 SVG 实时曲线 + 存储感知（4 个 SSD 容量/读写/连接数）+ 故障切换记录表 + 底部 6 列核心指标栏 + 故障模拟模态框（多阶段恢复流程） | 实时监控+交互仿真 |
| 权限安全 | 4 角色 × 8 权限复选框矩阵（租户管理/项目管理/算力调度/引擎会话/推流/版权/计费/运维）→ localStorage | 配置管理 |
| 费用告警 | 费用摘要（今日/本周/本月/构成）+ 告警表格（确认/处理中/关闭状态）+ 运维事件日志 | 财务管理 |

**当前模式：** 纯前端仿真，不调用后端 API

### 5.4 资产库（`/assets`）

**技术实现：** `assets.html`（199 行）+ `assets.js`（733 行）

**功能特性：**
- Tab 切换：3D 模型 / 图片 / Prompt 文档
- 搜索过滤：按名称和描述全文搜索
- 分页加载：支持 limit/offset 参数
- 文件上传：拖拽上传，支持 GLB 等格式
- 资产 CRUD：创建/查看/更新/删除
- 场馆分类：按剧场/画廊/博物馆/音乐厅组织
- 文件存储：按类型和场馆自动分区存储

### 5.5 用户认证页面

**技术实现：** `login.html`（52 行）+ `register.html`（60 行）+ `auth.js`（134 行）

**功能特性：**
- 登录表单：用户名 + 密码 → POST `/api/auth/login`
- 注册表单：用户名 + 密码 + 邮箱（可选）→ POST `/api/auth/register`
- 表单校验：密码 >= 6 位、用户名 >= 2 位
- 错误提示：用户名已占用、密码错误等明确提示
- 状态持久化：登录成功后 Session 保持

---

## 六、资产管理功能

### 6.1 资产 CRUD（完整 REST API）

| 操作 | API | 说明 |
|------|-----|------|
| 列表查询 | `GET /api/assets` | 支持 asset_type/venue_type 过滤 + 分页 |
| 详情查询 | `GET /api/assets/<id>` | 返回完整资产信息（含 metadata） |
| 创建资产 | `POST /api/assets` | 至少需要 name 字段 |
| 更新资产 | `PUT /api/assets/<id>` | 部分字段更新 |
| 删除资产 | `DELETE /api/assets/<id>` | 同时删除关联文件 |
| 文件上传 | `POST /api/assets/upload` | multipart/form-data |
| 文件下载 | `GET /api/assets/<id>/download` | 原始文件下载 |
| 直接访问 | `GET /data/assets/<path>` | 静态文件服务 |

### 6.2 资产存储结构

```
data/assets/
  ├── models/
  │   ├── theater/    (剧院场景的 GLB 模型)
  │   ├── gallery/    (画廊场景的 GLB 模型)
  │   ├── museum/     (博物馆场景的 GLB 模型)
  │   └── concert/    (音乐厅场景的 GLB 模型)
  ├── images/
  │   ├── textures/   (图片纹理)
  │   ├── previews/   (预览图片)
  │   └── references/ (参考图片)
  └── prompts/
      ├── venues/     (场馆类 Prompt 文档)
      ├── shots/      (镜头类 Prompt 文档)
      └── styles/     (风格类 Prompt 文档)
```

### 6.3 Prompt 文档管理

**功能描述：** 独立的 Prompt 知识文档管理系统，支持从知识库批量导入。

**API：**
- `GET /api/prompts/documents` - 列表查询（支持 category 过滤 + 分页）
- `POST /api/prompts/documents` - 创建文档
- `GET /api/prompts/documents/<id>` - 查看详情
- `PUT /api/prompts/documents/<id>` - 更新文档
- `DELETE /api/prompts/documents/<id>` - 删除文档
- `GET /api/prompts/categories` - 分类统计

**文档分类：**
- `venue` - 场馆 Prompt
- `shot` - 镜头 Prompt
- `lighting` - 光影 Prompt
- `style` - 风格 Prompt
- `subject` - 主体 Prompt
- `dynamics` - 动态 Prompt
- `environment` - 环境 Prompt

**知识库导入功能：**
- 从 `knowledge_base.json` 自动提取场馆信息、镜头语言、词汇库
- 生成结构化 PromptDocument 记录
- 支持分类存储与全文搜索

---

## 七、知识库体系

### 7.1 knowledge_base.json 内容结构

| 目录 | 条目数 | 用途 |
|------|--------|------|
| `project_metrics` | 4 项 | 项目统计指标 |
| `model_catalog` | 6 个 | AI 模型配置与路由 |
| `venue_catalog` | 4 个 | 场馆预设 + 完整 Prompt 模板 |
| `asset_catalog` | 多个 | 空间锚点 + 占位几何体 |
| `shot_catalog` | 7 个 | 镜头语言库 |
| `knowledge_rules` | 1 组 | 全局规则与默认负向提示词 |
| `workflow_tips` | 多条 | 操作提示文案 |
| `lexicon_catalog` | 多个 | 术语词汇库 |
| `engine_catalog` | 4 个 | 渲染引擎配置 |
| `resource_pool_catalog` | 3 个 | GPU 资源池类型 |
| `stream_profile_catalog` | 3 个 | 推流配置协议 |
| `rights_template_catalog` | 多个 | 版权许可模板 |
| `demo_tenant_catalog` | 1 个 | 演示租户数据 |

### 7.2 4 个场馆预设覆盖

| 场馆 | ID | 典型 Prompt |
|------|-----|------------|
| 大剧院 | grand_theater | 巴洛克歌剧院，红色丝绒帷幕，枝形水晶吊灯，金色藻井 |
| 现代美术馆 | modern_gallery | 极简白立方空间，抛光混凝土地面，线性轨道灯系统 |
| 古典博物馆 | ancient_museum | 敦煌风格展厅，砂岩浮雕壁画，暖色导轨射灯 |
| 音乐厅 | concert_hall | 现代交响乐厅，木质扩散面板，舞台聚光灯阵列 |

**每个场馆预设包含：**
- `hero_title` - 默认任务标题
- `default_subject` - 默认主体描述
- `default_dynamics` - 默认动态行为
- `default_environment` - 默认环境描述
- `default_lighting` - 默认光影氛围
- `default_style` - 默认风格锚点
- `negative_prompt_parts` - 场馆特有负向提示词（如 "broken chandelier", "sagging ceiling"）
- `camera_defaults` - 默认相机参数（半径/高度/目标点）

---

## 八、数据持久化策略

### 8.1 双轨存储设计

```
SQLite (结构化)               JSON 文件 (快照)
────────────────────────────────────────────────
关系型业务数据                 任务生命周期快照
- 资产/租户/用户/项目          - 每个阶段一个独立文件
- 角色/权限/资源              - 完整保留执行轨迹
- 版权/来源/计费              - 便于审计与问题排查
- 引擎/流/运维               - 支持独立备份与恢复

优势:                        优势:
- 支持复杂关联查询            - 无 Schema 约束
- 外键约束保证数据完整性       - 人类可读
- 索引加速检索                - 每任务独立隔离
```

### 8.2 数据库表统计

- **14 张业务表**：assets, prompt_documents, venue_presets, model_configs, job_history, tenants, users, projects, project_memberships, resources, resource_allocations, engine_profiles, stream_sessions, asset_rights, asset_provenance_events, billing_accounts, billing_usage_records, ops_events
- **16 个性能索引**：覆盖主要查询字段
- **外键约束**：tenants → users → projects → project_memberships 链路

---

## 九、技术特性

### 9.1 线程安全

- SQLite 使用 `threading.local()` 线程本地连接，每个线程独立连接
- `JobStore` 使用 `threading.Lock()` 保护内存缓存
- 任务 Worker 线程 `daemon=True`，主进程退出时自动清理

### 9.2 前端竞态防护

- `previewRequestId`、`submitRequestId`、`pollRequestId` 三个递增计数器
- 闭包内捕获请求 ID，回调时对比全局 ID，不匹配则丢弃
- 防止快速连续操作导致 UI 状态错乱

### 9.3 演示数据自动注入

- 每次启动自动执行 `seed_demo_data()`
- 使用 `_insert_if_missing()` 幂等覆盖
- 注入完整的演示环境：租户/用户/项目/资源/引擎/版权/计费

### 9.4 统一 API 响应格式

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "message": "任务已创建",
  "details": null
}
```

所有 API 端点遵循统一格式，前端仅需检查 `success` 字段。

### 9.5 错误处理体系

- `ApiError` 自定义异常：code + message + status_code + details
- 全局异常捕获：400 / 404 / 500 / Exception
- 前端统一 `api()` 函数：自动解析 JSON 响应 + 异常抛出

---

## 十、功能对比总览

| 功能 | 后端实现 | 前端实现 | 状态 |
|------|----------|----------|------|
| Prompt 编排 | PromptOrchestrator | renderPromptPreview | 完整可用 |
| 任务流水线 | JobStore + Worker | startPolling + renderJob | 完整可用 |
| 多模型路由 | ProviderRouter | 无需前端 | 完整可用（需 API Key） |
| Blender 导出 | BlenderAdapter + Runner | 无需前端 | 条件触发 |
| 用户认证 | AuthService | login/register/auth.js | 完整可用 |
| 资产管理 | AssetService | assets.html/assets.js | 完整可用 |
| Prompt 文档 | PromptDocService | - | 完整可用 |
| 多租户管理 | TenantService | - | 演示可用 |
| 算力调度 | SchedulerService | compute-platform 演示 | 后端可用 |
| 版权确权 | RightsService | renderRightsPanel | 演示可用 |
| 计费管理 | BillingService | renderBillingPanel | 演示可用 |
| 流媒体推流 | StreamService | - | 演示可用 |
| 引擎管理 | EngineService | - | 演示可用 |
| 运维监控 | OpsService | renderOpsPanel | 演示可用 |
| 创意生产 6 步 | - | creative-studio 完整演示 | 前端演示 |
| 算力调度 7 Tab | - | compute-platform 完整演示 | 前端演示 |
| MCP 实时控制 | blender_agent | - | 预留待开启 |

---

*文档基于 AIGV Studio 代码实际分析生成*
*最后更新: 2026-07-23*

---

# 附录：生产化能力清单（2026-10-29）

> 本节区分“已实现并测试”“需要外部配置”“已实现但未真实验证”“演示模块”。前文功能矩阵如与本表冲突，以本表为准。

## A. 已实现并通过自动化测试

| 能力 | 说明 |
|---|---|
| 注册 / 登录 / 登出 | 真实 SQLite 账户、PBKDF2 哈希、CSRF、会话版本失效、登录锁定与管理员启用解锁 |
| 全站鉴权 | 未登录 API 401、页面跳转登录；`/admin*` 管理员；`/compute-platform*` 需 `view_compute`；静态 HTML 绕过被阻断 |
| 个人中心 | 头像/昵称/邮箱/简介、改密后强制重登、真实任务统计与最近任务 |
| 管理员后台 | 用户分页/搜索/角色/状态/会话撤销/统计/审计/全平台生成任务（筛选、取消、重试） |
| 创意项目与分镜 | 项目 CRUD、分镜 CRUD/排序、图片/视频任务创建、任务轮询、失败/取消/待确认状态 |
| 生成任务持久化 | SQLite 任务、第三方 ID、租约、重启恢复、超时、幂等键、配额、取消 |
| 图片生成链路 | Seedream 同步适配、ComfyUI 异步适配（Mock 测试）、图生图参考图、结果下载与私有素材 |
| 视频生成链路 | Seedance 异步创建/轮询/取消、图生视频参考图、临时 URL 转存、结果预览/下载 |
| 生成历史 | 素材库“生成历史”Tab：类型/状态/日期/分页、预览、参数、下载、取消、删除、重新生成、图生视频入口 |
| 对象权限 | 任务/素材/项目/分镜所有权校验；跨用户访问 403；管理员 `scope=all` |
| 演示数据隔离 | `DEMO_MODE=false` 默认；生产不注入演示用户/GPU/任务；演示模块有明确标识 |
| 部署支持 | `wsgi.py`、Gunicorn 样例、独立 Worker、Nginx/HTTPS 样例、SQLite 备份脚本 |
| 自动化测试 | 认证/权限/CSRF/迁移/文件安全/生成 Provider/任务竞态/历史筛选/演示模式等 |

## B. 需要外部配置后才能使用

| 能力 | 所需配置 |
|---|---|
| 图片生成（方舟 Seedream） | `ARK_API_KEY`；确认账号已开通对应模型 ID |
| 视频生成（方舟 Seedance） | `ARK_API_KEY`；确认模型/时长/分辨率权限 |
| ComfyUI 本地生图 | `COMFYUI_ENABLED=true`、`COMFYUI_BASE_URL`、可用工作流 |
| Luma / Atlas 旧通道 | `LUMA_API_KEY` / `SEEDANCE_API_KEY`，模型 ID 以服务商为准 |
| LLM 分镜分析 | `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL_NAME` |
| TTS/合成/精修 | Piper / FFmpeg 可执行文件与模型 |
| 算力/云主机/监控 | 云厂商凭据与节点采集源；未接入时页面显示空状态 |

未配置时：模型在当前用户界面显示为不可用并给出原因；提交接口返回 `provider_not_configured`，**不会返回假成功或示例图**。

## C. 已实现但未进行真实 API 验证

- Ark Seedream 图片、Ark Seedance 视频：请求/响应映射、错误分类、异步轮询由单元/Mock 测试覆盖；未用真实密钥调用。
- ComfyUI：仅 fake HTTP 测试；未连接真实实例。
- Luma / Atlas：旧适配 + 单元测试；未真实验证，Luma 不支持参考图。
- 因此模型注册表中的 `verified` 均为 `false`；`docs/AI-Provider-Integration.md` 列出了验证方法。

## D. 保留的演示模块（有明确标识）

- 算力平台中的 Three.js 影视/建筑/游戏可视化、部分演示图表、故障模拟、云主机模拟指标：仅在 `DEMO_MODE=true` 时展示，并标注“演示”。
- `web/aigv-demo-data.js` 在非演示模式下自置为 `null`；后端不再注入演示用户、GPU 或任务。
- 知识库中的场馆/镜头/Prompt/引擎目录属于静态知识资源，生产模式保留（不是伪造业务数据）。

## E. 与原功能的兼容

- 保留 Prompt 六模块编排、Blender 空间锚点、资产管理、算力调度展示、监控/告警、创意模板与知识库。
- 保留旧 `/api/jobs` 十阶段流水线；新图片/视频生成走 `generation_tasks` 体系，两者不互相删除。
- Blender 未配置时，普通文生图/文生视频仍可独立运行；不支持空间锚点的模型不会被宣称为已使用 Blender 数据。

## F. 使用提示

1. 首次部署：`scripts/init_db.py` → 迁移旧账户（如有）→ `scripts/create_admin.py`。
2. 新注册用户自动获得个人工作区；首次进入创意工作台从“分析需求”或已有项目开始。
3. 若模型列表为空/均不可用，请检查 `.env` 中的 Provider 密钥；这是配置问题，不是页面故障。
4. 生成历史在“素材库 → 生成历史”；失败任务保留记录但不产生素材。
5. 删除仍被分镜引用的生成图会被拒绝（409），避免破坏项目。

---

# 附录 G：真实媒体制作能力（2026-10-30）

第 04–06 步不再依赖前端演示数据：

| 步骤 | 真实能力 |
|---|---|
| 04 配音与素材 | 后端音色注册表；每镜头真实 Piper 配音、试听、历史版本、无配音；语速/音量真实后处理；真实 SRT；音乐/音效上传（FFprobe 校验）与试听；可编辑多轨时间线保存到服务器 |
| 05 单镜头试调 | 选择具体分镜与版本；真实原始/精修双播放器（CSS 仅快速预览）；白名单 FFmpeg 滤镜；生成独立精修资产；选择精修/原始版本用于成片；AI 超分等未接入项明确禁用 |
| 06 最终成片与导出 | 从已保存时间线合成 720p/1080p MP4；真实旁白/音乐/音效/字幕；可选字幕封装或烧录；FFprobe+完整解码验证；播放/下载 MP4/字幕；ZIP 素材包含 final/videos/audio/images/subtitles/manifest/project |

补充说明：

- 第 05 步是可选的，不阻塞第 06 步；第 04 步是否可继续由服务端时间线/视频片段派生，而不是本地布尔值或“任意音频存在”。
- 刷新或重新登录后，工作流状态、时间线、配音历史和最终成片均从 SQLite/素材库恢复。
- 系统预设音乐库没有授权文件时保持为空；不会用前端假卡片冒充音频。
- 云端 TTS 本期未启用；只展示实际安装且通过可执行性检查的本地音色。
- 性能诊断：`GET /api/generation/tasks/<id>/timing`（所有者/管理员）与 `/api/generation/timing/summary`（管理员），详见 `docs/Performance-Report.md`。

# 附录 H：管理员审计可读性与 AI 模型服务/官方账单（2026-10-31）

## H.1 管理员审计日志

- “用户管理”页面的审计区域升级为“审计日志”：
  - 中文事件/结果（如 `generation_succeeded` → AI 生成任务完成，`success` → 成功）。
  - 操作人显示昵称（用户名）；已删除用户显示“已删除用户”。
  - 业务目标显示任务类型、Provider、模型、项目/素材等；不展示裸 UUID。
  - 支持事件类型、结果、操作人、日期范围筛选和后端分页。
  - 每行“查看详情”展示相关模型、项目、错误、请求 ID、原始 ID 和脱敏 metadata。
  - 默认最近 10 条，“查看全部记录”进入分页模式。
- 底层审计记录只追加，不提供页面修改/删除。

## H.2 AI 模型服务

“算力调度”页面新增管理员可见“AI 模型服务”标签：

- 本地真实任务：模型调用次数、图片/视频/LLM 任务、运行中/成功/失败、成功率、平均排队/Provider/下载/完成耗时。
- 火山引擎官方用量：请求数、输入/输出/总 Token、图片数、按模型统计、7/30 天趋势、最近同步/同步状态。
- 本地和官方数据分开展示并带来源说明；无数据/未配置/无权限不显示演示曲线。
- 管理员可手动“同步官方用量”；定时同步由独立 worker 执行。

## H.3 费用管理

- 新增管理员可见“火山引擎官方账单”区域：
  - 本月累计应付（部分出账）、上月应付/结算状态、官方可用余额、最近同步。
  - 官方按模型/配置费用、按日费用、用户用量与官方分账、对账。
  - 官方账单与内部 GPU/渲染估算明确分区。
- 原有内部 GPU/渲染费用保留，并标注“内部核算、非官方账单”；累计费用已修复为全量汇总（不再只统计最近 20 条）。
- 官方金额按币种/原价/优惠/应付/已付/结算口径分开展示，不跨币种相加。
- 当前账号未开通分账账单能力，官方费用显示未归属；AIGV 本地用户任务/用量仍可查看，不按任务次数平均官方金额。
- 当前账号 2026-09 及更早无官方账单数据；当前月已有 `Doubao-Seedream`、`ark_bd` 两类官方产品数据。
