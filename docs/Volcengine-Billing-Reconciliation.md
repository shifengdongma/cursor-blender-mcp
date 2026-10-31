# 火山引擎官方账单与对账说明

本文记录 AIGV Studio 接入火山引擎费用中心官方账单、余额和本地对账的实现与验证结果。

## 1. 真实只读验证状态（2026-10-31）

使用服务器 `.env` 中的管理 AK/SK（未写入任何日志/文档）完成以下只读验证：

| 接口 | 结果 |
|---|---|
| `QueryBalanceAcct` | 成功；返回可用余额/现金余额/信控/冻结/欠费，币种 `CNY` |
| `ListBillOverviewByProd(2026-10)` | 成功；2 个产品：`Doubao-Seedream`（豆包图像创作模型）、`ark_bd`（字节跳动大模型服务/豆包大模型） |
| `ListBillDetail(2026-10, GroupPeriod=2)` | 成功；3 条明细，官方配置名包含 `Doubao-Seedream-5.0-flash`、`Doubao-Seedance-2.0` |
| `ListBill(2026-10)` | 成功；包含 `PayStatus` |
| `ListBillOverviewByProd(2026-09)` 及更早 | 当前账号无数据（返回 0 条） |
| `ListSplitBillDetail` | 账号未开通分账账单能力，官方返回 `The current account has not enabled split bill capability`；代码按“未启用分账”展示，不影响主账单同步 |

已确认的 Ark 产品过滤：

```env
VOLCENGINE_ARK_BILL_PRODUCT_FILTER=ark_bd,Doubao-Seedream
```

分账维度配置保持为空，避免每次同步都请求未开通的接口：

```env
VOLCENGINE_ARK_BILL_SPLIT_DIMENSION=
```

若后续管理员在火山引擎开通分账账单，可配置官方示例：

```env
VOLCENGINE_ARK_BILL_SPLIT_DIMENSION={"ark_bd":"apikey_id"}
```

配置后仍需先重新同步，并在页面确认 `split_status` 为 `success`，不要直接假设分账可用。

## 2. 官方金额口径

官方接口金额均为字符串，代码使用 Python `Decimal` 解析，数据库列为 TEXT，**不使用 float 汇总官方金额**。

| 字段 | 口径 |
|---|---|
| `OriginalBillAmount` | 原价 |
| `PreferentialBillAmount` | 优惠金额 |
| `DiscountBillAmount` | 折后价 |
| `CouponAmount` | 代金券抵扣 |
| `PayableAmount` | 应付金额（定价币种） |
| `PaidAmount` | 已支付 |
| `UnpaidAmount` | 未支付/欠费 |
| `SettlePayableAmount` / `SettlePosttaxAmount` | 结算币种金额 |
| `Currency` / `CurrencySettlement` | 定价币种 / 结算币种 |
| `PayStatus` | `CompletedSettle` / `PartSettle` / `Unsettle` |

规则：

- 不同字段不直接相加（原价 + 优惠 + 应付不是同一口径）。
- 不同币种不直接相加。
- 只有 `PayStatus=CompletedSettle`（或中文“已结清”）才显示“已结清”。
- 当月账单是部分数据；上月完整账单通常在次月 2 日 12:00 后生成。

## 3. 数据表

### `volcengine_bill_snapshots`

保存官方账单快照：

- `record_level`：`overview`（产品汇总）、`bill`（账单流水）、`detail`（账单明细）、`split`（分账明细）
- `snapshot_key` 唯一；重复同步 UPSERT，不重复累计
- 官方标识：`official_bill_id`、`bill_detail_id`、`split_bill_detail_id`
- 产品/配置：`product`、`product_zh`、`config_name`、`charge_item_code`、`resource_id`、`instance_no`
- 用量：`usage_amount`、`usage_unit`
- 金额：全部 TEXT 十进制字符串
- 归因：`split_item_id/name/ratio`、`api_key_resource_id`
- `raw_payload`：官方行 JSON（不含密钥）
- `bill_period` / `expense_date`

去重优先级：

1. `BillDetailId`
2. `SplitBillDetailId`
3. 稳定复合键（账期 + 产品 + 配置 + 计费项 + 日期 + 币种 + 实例 + 官方账单号 + 用量/原价）

### `volcengine_balance_snapshots`

保存 `QueryBalanceAcct` 历史快照：账号、可用余额、现金余额、信控额度、冻结、欠费、币种、原始响应、同步时间。页面只取最新快照，不把内部 `billing_accounts.balance` 当作官方余额。

### `volcengine_sync_status`

`ark_billing` 与 `ark_balance` 独立状态：`never_run/running/success/failed/disabled/unconfigured`、最近成功时间、错误类别/码/消息、处理条数、账期、metadata（产品过滤、分账状态、截断页）。

## 4. 同步策略

- 默认同步**当月和上月**；管理员可指定 `bill_period=YYYY-MM`（最近 24 个月）。
- 每个账期同步：
  - `ListBillOverviewByProd` → `overview`
  - `ListBill` → `bill`
  - `ListBillDetail(GroupPeriod=2)` → `detail`
  - `ListSplitBillDetail`（仅在配置分账维度时）→ `split`
- 每页最多 300 条，最多 10 页；超过上限在响应和状态中标记 `truncated`，不静默截断。
- 5 QPS 节流、超时/限流/5xx 有限重试。
- 同步锁写 `volcengine_sync_status`，跨进程防止并发。
- 失败保留上次成功快照和 `last_success_at`；错误只记录类别/码/脱敏消息。
- 同步成功后独立调用 `QueryBalanceAcct`；余额无权限不影响主账单同步成功，但会记录 `ark_balance=failed/no_permission`。
- 定时 worker：`scripts/run_ark_sync.py --loop`，账单默认每日、用量默认 30 分钟；由独立 systemd unit `aigv-ark-sync.service` 运行，不在 Web 请求中同步。

## 5. API

全部管理员鉴权、CSRF（POST）、限流：

- `GET /api/admin/ark/billing/summary?bill_period=YYYY-MM`
- `GET /api/admin/ark/billing/details?bill_period=&level=overview|bill|detail|split&limit=&offset=`
- `GET /api/admin/ark/billing/balance`
- `GET /api/admin/ark/billing/sync-status`
- `GET /api/admin/ark/billing/models`
- `GET /api/admin/ark/billing/trend`
- `GET /api/admin/ark/billing/attribution`
- `GET /api/admin/ark/billing/reconciliation`
- `POST /api/admin/ark/billing/sync`，Body `{"bill_period":"YYYY-MM", "include_split": false}`

返回统一带：

```json
{
  "source": "volcengine_billing",
  "source_label": "火山引擎官方账单（费用中心）",
  "last_synced_at": 1793431590,
  "is_estimated": false,
  "billing_period": "2026-10",
  "currency": "CNY"
}
```

金额始终是字符串；多币种时 `currency=null`，并返回 `*_by_currency` 数组，不提供跨币种合计。

## 6. 费用页展示

“算力调度 → 费用告警”页：

1. **火山引擎官方账单**（仅管理员）
   - 本月累计应付（部分出账）
   - 上月账单应付/结算状态
   - 官方可用余额
   - 最近同步、产品过滤、分账状态、是否过期
   - 官方按模型/配置费用、按日费用、用户用量与官方分账、对账
2. **内部 GPU / 渲染核算**（原有）
   - 明确标注“非火山官方账单”“内部核算余额”
   - `total_amount` 已修复为全量 SQL SUM，不再是最近 20 条

无官方权限/未启用/无数据时显示明确状态，不使用演示数据。

## 7. 按模型归属

- 官方账单没有统一模型字段，代码在 `ConfigName`、`Product`、`ChargeItemCode`、`InstanceNo`、`ResourceID`、`raw_payload` 中匹配**已知官方模型 ID**。
- 已用真实账单验证：
  - `Doubao-Seedream-5.0-flash` → `doubao-seedream-5-0-flash-260915`
  - `Doubao-Seedance-2.0` → `doubao-seedance-2-0-260128`
- 无法可靠匹配的官方配置标记“未归属模型”，不猜测。
- 不同用量单位（张/千tokens等）分开展示，不强行相加。

## 8. 用户归属与共享 Key

- 只有 `ListSplitBillDetail` 成功、返回 API Key 资源 ID，且该 ID 能唯一映射到一个 AIGV 用户时，才把官方金额归属该用户。
- 映射来源：`ai_model_usage_records.api_key_resource_id`（官方 `GetInferenceTaskUsage` 返回）或管理员显式配置；绝不使用 API Key 密钥内容。
- 多个 AIGV 用户共用同一 Key 时标记 `shared`，金额进入未分摊，不按任务次数平均。
- 分账未开通/未配置时，官方费用全部保持未归属。
- 用户维度可以展示 AIGV 本地图片/视频/LLM 任务数与 Provider 响应用量，但这不是官方金额。

## 9. 对账

对账页展示：

- 官方应付金额（按币种，官方 `overview` 为准）
- 可归属官方金额（官方分账且唯一映射）
- 未归属金额 = 官方应付 - 可归属（同币种，负值按 0 显示并提示时点差异）
- 本地 Ark 任务数、本地用量任务数、输入/输出/总 Token、图片数
- 差异原因说明：出账延迟、免费额度、优惠券/折扣、账号内其他应用、共享 Key、计费规则差异、失败/取消收费、无法归属服务

明确禁止：

- 用任务次数平均分摊官方金额。
- 为了让两侧“看起来一致”而修改历史任务金额。
- 将内部 GPU/渲染估算混入官方账单金额。
- 将不同币种直接合计。

## 10. IAM 权限与安全

建议使用独立 IAM 子用户，只授予：

- Ark 用量：`GetInferenceUsage`、`GetInferenceTaskUsage`、`GetInferenceRequestUsage`
- 费用中心：`ListBillOverviewByProd`、`ListBill`、`ListBillDetail`、`ListSplitBillDetail`、`QueryBalanceAcct`

不授予资源创建/删除/变更、充值、退订等权限。AK/SK 只放在服务器 `.env`（`chmod 600`），不返回前端、不写数据库/审计/日志。建议联调后轮换根账号凭据。

## 11. 部署与回滚

```bash
# 备份（SQLite backup API，含 catalog/jobs，不含 .env）
.venv/bin/python scripts/backup_data.py --data-dir ./data --output ./backups

# 单次只读同步（验证/补数）
.venv/bin/python scripts/run_ark_sync.py --once --usage-only
.venv/bin/python scripts/run_ark_sync.py --once --billing-only --bill-period 2026-10

# 服务重启（先确认无排队/运行中的生成任务）
systemctl restart aigv-studio.service
systemctl is-active aigv-studio.service
curl -fsS http://127.0.0.1:8000/api/health

# 定时 worker（官方验证通过后）
cp deploy/aigv-ark-sync.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now aigv-ark-sync.service
systemctl status aigv-ark-sync.service --no-pager
```

回滚：

1. 停 `aigv-studio.service` 与 `aigv-ark-sync.service`。
2. 恢复阶段前备份的 `data/aigv.db`（清理 WAL/SHM）。
3. 回退代码/关闭 `VOLCENGINE_USAGE_ENABLED`、`VOLCENGINE_BILLING_ENABLED`、`*_SYNC_ENABLED`。
4. 重启并健康检查。

新增表/列是增量兼容的；旧代码可忽略。

## 12. 已知限制

- 当前账号历史账期（2026-09 及更早）无账单数据；页面会显示“暂无官方账单数据”。
- 当前账号未开通分账账单，因此官方费用无法按用户归属；用户用量仍可从 AIGV 本地记录查看。
- 官方当月数据为部分数据；账单延迟与结算状态以官方返回为准。
- 本阶段不提供应用侧金额估算（未配置经过验证的单价）；只展示真实用量和官方账单。
- 以官方 `overview` 为对账总额；`detail` 仅用于分模型/按日分析，不同层级、不同币种不混合相加。
