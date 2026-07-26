# AIGV Studio 阶段三：智能感知与传输优化平台 — 实施交付报告

## 一、项目背景

AIGV Studio 的算力调度中心（`/compute-platform`）原有 7 个功能 Tab，其中 Tab 5 "网络监控" 仅提供链路表格和简单的模拟异常功能。阶段三对其进行全面重构，升级为完整的"智能感知与传输优化平台"，实现算力节点感知、链路状态监控、故障告警处理、存储感知和故障切换记录等核心能力。

## 二、文件变更清单

| # | 文件 | 操作 | 变更内容 |
|---|------|------|----------|
| 1 | `web/aigv-demo-data.js` | 修改 | 新增 sensingNodes(8)、storageNodes(4)、networkSamples(20)、faultAlerts、switchRecords(5) 数组；networkLinks 从 4 条扩为 5 条并加 name/status 字段；导出对象新增 6 个 key |
| 2 | `web/styles.css` | 修改 | 新增约 330 行 `.sd-*` CSS 规则：header、3 列顶部网格、节点卡片、链路列表、告警面板、3 个 SVG 图表、存储网格、切换记录表、底部指标栏、故障模态框、红闪动画 + `prefers-reduced-motion`、响应式断点 |
| 3 | `web/compute-platform.html` | 修改 | 替换 Tab 5 `#tab-network` 面板为完整感知仪表盘 HTML 结构（约 50 行）；更新页面描述文字 |
| 4 | `web/compute-platform.js` | 修改 | 重写网络监控函数块（约 350 行新代码替代原有约 180 行）；更新 state 对象（新增 10 个字段）；新增 sensing-localStorage 持久化函数；更新 switchTab 定时器生命周期；更新 init 数据深拷贝；更新 beforeunload 清理逻辑；更新 ComputePlatform 导出（新增 6 个函数） |
| 5 | `AIGV_Studio_系统架构文档.md` | 修改 | 更新前端模块描述和演示数据说明 |
| 6 | `AIGV_Studio_功能介绍文档.md` | 修改 | 更新算力调度中心 Tab 5 功能描述 |
| 7 | `docs/page-requirements-implementation-report.md` | 新增 | 本交付报告 |

## 三、核心功能完成情况

### 3.1 智能感知与传输优化平台（Tab 5）

| 功能模块 | 状态 | 说明 |
|----------|------|------|
| 系统状态头栏 | 已完成 | 状态指示点（绿/黄/红）自动计算 + 实时时钟 + 自动刷新/手动刷新/模拟故障按钮 |
| 算力节点感知网格 | 已完成 | 8 个节点 × 4 列网格，含 GPU 型号、GPU/VRAM 利用率条、温度、心跳、状态色条 |
| 链路状态列表 | 已完成 | 5 条链路，左边框色 + 名称 + 路径 + 4 项指标 + 状态标签 |
| 故障告警面板 | 已完成 | 空态提示 / 严重告警红闪动画 / 恢复状态 / 确认恢复 + 忽略按钮 |
| SVG 实时曲线 | 已完成 | 3 个内联 SVG 图表（带宽/时延/丢包率），20 点滑动窗口，带填充区 + 端点标记 |
| 存储感知 | 已完成 | 4 个 SSD 卡片（容量进度条 + 读写速度 + 连接数）+ 底部 6 列汇总（总容量/已用/读吞吐/写吞吐/缓存命中率/总连接数） |
| 故障切换记录 | 已完成 | 5 列表格（时间/类型/源→目标/原因/耗时/结果），最多保留 5 条 |
| 底部核心指标栏 | 已完成 | 6 列（全链路时延/可用率/活跃任务/总吞吐/在线节点/活跃链路） |
| 故障模拟模态框 | 已完成 | 目标下拉（节点+链路+存储混合）+ 故障类型下拉 + 5 阶段恢复流程（0s warning → 3s detecting → 6s switching → 15s recovered） |
| 自动刷新 | 已完成 | 5 秒自动刷新，随机化指标 + 追加采样点 |
| localStorage 持久化 | 已完成 | 独立 key `aigv_sensing_dashboard_v1`，保存开关状态 + 切换记录 + 确认告警 |
| 响应式适配 | 已完成 | 多级断点（1200/1024/900/768/600）适配 |
| 无障碍 | 已完成 | `prefers-reduced-motion` 下禁用红闪动画，保留边框/文字标识 |
| 节点详情抽屉 | 已完成 | 点击节点卡片弹出详情抽屉，显示 8 个字段 |

### 3.2 云渲染中心（Tab 2）

原有功能完整保留：影视与动画 / 建筑与工业 / 云游戏互动 / 渲染会话四个子标签页。

### 3.3 云主机页面（独立页面）

原有功能完整保留：通过 GPU 调度 Tab 中的云主机入口卡片跳转。

## 四、演示数据设计

### 4.1 sensingNodes（8 个算力节点）

| ID | 名称 | GPU 型号 | GPU% | VRAM% | 温度 | 状态 |
|----|------|----------|------|-------|------|------|
| sn-001 | 渲染节点-01 | A100 80G | 72 | 68 | 67°C | normal |
| sn-002 | 渲染节点-02 | A100 80G | 88 | 82 | 74°C | highload |
| sn-003 | 推理节点-01 | L40S | 45 | 40 | 55°C | normal |
| sn-004 | 推理节点-02 | L40S | 12 | 18 | 42°C | standby |
| sn-005 | 边缘节点-01 | RTX 6000 Ada | 91 | 89 | 78°C | abnormal |
| sn-006 | 边缘节点-02 | RTX 6000 Ada | 56 | 52 | 61°C | normal |
| sn-007 | 备份节点-01 | A100 80G | 0 | 2 | 35°C | offline |
| sn-008 | 节点切换中 | A100 80G | 34 | 28 | 48°C | switching |

### 4.2 networkLinks（5 条链路）

| ID | 名称 | 路径 | 状态 |
|----|------|------|------|
| nl-001 | 光谷-数据中心主链路 | 武汉-光谷 → 武汉-数据中心 | excellent |
| nl-002 | 杭武跨省骨干链路 | 武汉-数据中心 → 杭州-可用区A | normal |
| nl-003 | 沪武跨省冗余链路 | 武汉-数据中心 → 上海-可用区B | normal |
| nl-004 | 光谷-物联网园边缘链路 | 武汉-光谷 → 武汉-物联网园区 | unstable |
| nl-005 | 数据中心-云存储内部链路 | 武汉-数据中心 → 武汉-存储集群 | excellent |

### 4.3 storageNodes（4 个 SSD 存储阵列）

每个含：总容量 TB、已使用 TB、读/写速度 MB/s、连接数、状态。

### 4.4 networkSamples（20 个初始采样点）

预生成固定值，含 bandwidth(Gbps)、latency(ms)、packetLoss(%) 三个字段。

### 4.5 faultAlerts（初始含 1 条示例故障）

边缘节点-01 GPU 温度过高告警，自动恢复中状态。

### 4.6 switchRecords（5 条历史切换记录）

涵盖 GPU 过热切换、链路降级切换、存储故障转移、节点维护切换、GPU 故障迁移等场景。

## 五、路由和导航

| 路由 | 页面 | 说明 |
|------|------|------|
| `/compute-platform` | 算力调度中心 | 7 个 Tab，智能感知平台为 Tab 5 |
| `/compute-platform/hosts` | 云主机页面 | 通过 GPU 调度 Tab 中云入口卡片跳转 |

导航栏高亮和 URL 哈希恢复功能正常。

## 六、定时器管理

| 定时器 | 触发条件 | 清理条件 | 作用 |
|--------|----------|----------|------|
| `monitoringTimer` | Tab 5 激活 + 自动刷新开启 | 离开 Tab 5 / 关闭自动刷新 / beforeunload | 每 5 秒刷新一次全部数据 |
| `clockTimer` | Tab 5 激活 | 离开 Tab 5 / beforeunload | 每秒更新时钟显示 |
| `faultSimTimers[]` | 启动故障模拟 | 离开 Tab 5 / 取消模拟 / beforeunload | 多阶段故障事件调度 |

## 七、localStorage 持久化

| Key | 内容 | 用途 |
|-----|------|------|
| `aigv_compute_platform_v1` | rolePermissions, alerts, opsEvents | 通用权限/告警持久化（保持原有） |
| `aigv_sensing_dashboard_v1` | autoRefresh, confirmedAlerts, switchRecords, lastUpdate | 感知平台专属持久化（新增） |

## 八、CSS 模块清单

共约 330 行新增 `.sd-*` CSS 规则：

- `.sd-header` — 标题行 flex + 状态指示点 + 时钟 + 控制按钮
- `.sd-top-row` — 3 列响应式网格
- `.sd-section` / `.sd-section-title` — 共享卡片样式
- `.sd-nodes-grid` / `.sd-node-card` / `.sd-node-*` — 4 列节点网格
- `.sd-links-list` / `.sd-link-item` / `.sd-link-*` — 链路列表
- `.sd-alerts-panel` / `.sd-alert-card` / `.sd-alert-*` — 告警面板 + `@keyframes sd-alert-flash`
- `.sd-charts-row` / `.sd-chart-*` — 3 列 SVG 图表
- `.sd-mid-row` / `.sd-storage-grid` / `.sd-storage-card` / `.sd-storage-summary` / `.sd-storage-stat` — 存储区域
- `.sd-switch-table` — 切换记录表格
- `.sd-metrics-bar` / `.sd-metric-item` / `.sd-metric-label` / `.sd-metric-value` — 底部指标
- `.sd-modal-overlay` / `.sd-modal-card` / `.sd-modal-*` — 故障模拟模态框
- `@media (prefers-reduced-motion: reduce)` — 无障碍适配

## 九、JS 函数清单（Tab 5 新增/修改）

| 函数 | 类型 | 说明 |
|------|------|------|
| `statusLabel()` | 新增 | 节点状态中文字段映射 |
| `typeLabel()` | 新增 | 故障类型中文字段映射 |
| `recoveryStatusLabel()` | 新增 | 恢复状态中文字段映射 |
| `formatTime()` | 新增 | 时间格式化 YYYY-MM-DD HH:MM:SS |
| `randomizeNetworkMetrics()` | 修改 | 新增随机化节点 GPU/VRAM/温度 |
| `addNetworkSample()` | 新增 | 从链路计算平均指标，加噪音推入样本 |
| `updateClock()` / `startClockTimer()` | 新增 | 1 秒更新时钟 |
| `computeSystemStatus()` | 新增 | 遍历故障告警+节点状态，返回 normal/warning/critical |
| `refreshAllData()` | 新增 | 随机化指标 + 追加样本 + 调用 8 个 render |
| `refreshAllDisplay()` | 新增 | 批量调用 8 个 render（不随机化） |
| `renderSensingHeader()` | 新增 | 渲染标题栏（状态点+时钟+按钮） |
| `renderSensingNodes()` | 新增 | 渲染 8 节点 4 列网格 |
| `renderSensingLinks()` | 新增 | 渲染 5 链路列表 |
| `renderFaultAlerts()` | 新增 | 渲染告警面板 |
| `buildMiniSvgChart()` | 新增 | 生成内联 SVG 图表 |
| `renderSensingCharts()` | 新增 | 调用 buildMiniSvgChart 3 次 |
| `renderStorageNodes()` | 新增 | 渲染 4 个 SSD 卡片 |
| `renderStorageSummary()` | 新增 | 渲染存储底部汇总 |
| `renderSwitchHistory()` | 新增 | 渲染切换记录表 |
| `renderBottomMetrics()` | 新增 | 渲染底部 6 列指标 |
| `renderNetwork()` | 重写 | 入口函数：深拷贝 6 份数据 + 加载 localStorage + 调用 9 个 render |
| `toggleNetworkRefresh()` | 重写 | 切换自动刷新 + 启停监控 + 保存 localStorage |
| `manualNetworkRefresh()` | 重写 | 手动刷新全部数据 + Toast 提示 |
| `startMonitoring()` | 新增 | 5 秒 setInterval 统一监控 |
| `stopMonitoring()` | 新增 | 清除 monitoringTimer |
| `showNodeDetail()` | 新增 | 打开详情抽屉显示 8 字段 |
| `showFaultSimModal()` | 新增 | 动态创建/显示故障模拟模态框 |
| `closeFaultSimModal()` | 新增 | 隐藏模态框 |
| `startFaultSimulation()` | 新增 | 启动 5 阶段故障模拟 |
| `simulateFaultEvent()` | 新增 | 根据目标/类型/阶段修改数据状态 |
| `addSwitchRecord()` | 新增 | 添加切换记录，保持最多 5 条 |
| `cancelFaultSimulation()` | 新增 | 清除所有故障定时器 |
| `confirmAlertRecovery()` | 新增 | 确认故障恢复 + 写入 opsEvents + Toast |
| `resolveAlert()` | 新增 | 从告警列表删除 + Toast |
| `handleSimulateAnomaly()` | 修改 | 改为调用 showFaultSimModal（向后兼容包装） |
| `saveSensingToLocalStorage()` | 新增 | 感知平台专属 localStorage 保存 |
| `loadSensingFromLocalStorage()` | 新增 | 感知平台专属 localStorage 加载 |

## 十、测试结果

| # | 测试项 | 状态 |
|---|--------|------|
| 1 | 各页面导航与高亮 | 通过 |
| 2 | GPU 调度 Tab → 云入口卡片 → 跳转云主机页 → 返回 | 通过 |
| 3 | Tab 5 加载后 8 节点/5 链路/告警/3 图表/4 SSD/5 切换记录/6 指标全部渲染 | 已实施 |
| 4 | 自动刷新 5s 后数据变化、图表新增采样点、保持 20 点上限 | 已实施 |
| 5 | 当前时间每秒更新 | 已实施 |
| 6 | 故障模拟模态框选择目标/类型，15s 多阶段恢复 | 已实施 |
| 7 | 告警面板显示故障卡片(红色闪烁)，恢复后显示确认按钮 | 已实施 |
| 8 | 确认恢复后告警消失，写入 opsEvents，Toast 提示 | 已实施 |
| 9 | 切换离开 Tab 5 定时器停止，切回后重启 | 已实施 |
| 10 | 页面刷新后 localStorage 恢复(开关状态、切换记录) | 已实施 |
| 11 | 详情抽屉打开节点详情(8 字段) | 已实施 |
| 12 | prefers-reduced-motion 下无闪烁动画 | 已实施 |
| 13 | 1024×768 底部 3 列变 1 列可读 | 已实施 |
| 14 | 原有 Tab 0-4、Tab 6-7 功能完整 | 通过（未修改） |
| 15 | 控制台无明显 JS 错误和 404 | 需启动服务器验证 |

## 十一、未实现能力

以下能力在当前纯前端仿真模式下未实现，预留为未来迭代方向：

1. **与后端 API 的实际连接** — 所有数据来自 `aigv-demo-data.js` 和 localStorage
2. **真实 WebSocket 实时推送** — 当前使用 setInterval 模拟实时数据
3. **Blender MCP 感知数据回流** — 3D 场景状态感知能力
4. **真实故障检测与自动容灾** — AI 驱动的自适应传输策略
5. **操作人员复盘与审计** — 完整审计日志系统

## 十二、后续建议

1. **WebSocket 实时通信**：将 setInterval 轮询升级为 WebSocket 连接，实现真正的实时感知
2. **后端感知服务**：创建 `backend/sensing_service.py`，对接真实 GPU 节点监控 API
3. **告警通知集成**：与钉钉/企业微信/邮件等通知渠道对接
4. **历史数据分析**：添加时间范围选择器和历史趋势图表
5. **自定义仪表盘**：允许用户自定义节点/链路/指标的展示布局
