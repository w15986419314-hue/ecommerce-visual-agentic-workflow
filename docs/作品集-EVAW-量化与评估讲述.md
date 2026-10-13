# EVAW 量化与评估讲述（面试用 · 演示集）

**吴林栩（Cici）** · 跑数时间：2026-10-13（Asia/Singapore）  
命令：`python3 -m evaw.cli evalset-v0`（辅：`qa-live-demo` / `knowledge-block` / `high-risk` / `happy`）

> **原则**：只报本机真实跑数；无业务线上样本时，一律标 **演示集 / fixture**，不编造「业务通过率」。

---

## 1. evalset-v0 是什么

| 项 | 说明 |
|----|------|
| 路径 | `evalset/v0/cases.json` |
| 规模 | **15** 条匿名用例 |
| 引擎 | **Rules QA**（元数据 / fixture 触发五维，**不是**真实客户像素图） |
| 目的 | 对照「期望 overall + reason_code」是否被规则引擎稳定打出，证明 **Pass / PassWithRisk / Fail 边界可复现** |
| 五维 | product_fidelity · brand · text · layout · mobile_readability |

设计意图：用可控 fixture 覆盖低风险 Pass、结构/品牌/文案/版式/移动临界 Risk、以及各维硬 Fail，方便面试口述「人审入口从哪来」。

---

## 2. Pass / PassWithRisk / Fail 含义

| overall | 产品含义 | 流水线后果（HITL） |
|---------|----------|-------------------|
| **Pass** | 五维均过；无强制风险标记 | 低风险 → **可 auto Approve**（可抽检）；若 `structure_sensitive` / 新品 / 知识豁免 → **仍强制 PendingReview** |
| **PassWithRisk** | 可交付但有残余风险（至少一维 Risk） | **强制人审** → `PendingReview`；Lead 可 `accept_risk` 后 Approved |
| **Fail** | 至少一维硬失败 | → `QAFailed`，**不** auto-approve；需改 Brief/素材/知识后再跑（打回回流另述） |

**reason_code（演示集出现）**

| code | 典型场景 |
|------|----------|
| `FIDELITY_STRUCTURE` | 结构敏感 / 结构混淆 / 缺 knowledge_snapshot |
| `BRAND_VIOLATION` | 品牌未在册（软 Risk）或 VIS 硬违规（Fail） |
| `TEXT_ERROR` | 无卖点 / 宣称错误 / 占位词 TODO |
| `LAYOUT_PLATFORM` | 尺寸提示异常 / 平台安全区失败 |
| `MOBILE_READABILITY` | 移动端临界 Risk 或不可读 Fail |

代码依据：`evaw/hitl.py`（PassWithRisk / structure_sensitive / 新品强制人审；低风险可 auto）。

---

## 3. 本次真实跑数（evalset-v0）

```
evalset=v0 engine=rules cases=15 matched=15 pass_rate=100.0%
```

### 3.1 两个「率」不要混

| 指标 | 数值 | 含义 |
|------|------|------|
| **期望对齐率**（CLI 的 `pass_rate`） | **100%（15/15）** | 规则输出与用例 `expected_overall` / `expected_reason_code` **一致** |
| **标签分布 · Pass** | **20%（3/15）** | 演示集里设计为 Pass 的占比，**≠ 业务 QA 通过率** |
| **标签分布 · PassWithRisk** | **33.3%（5/15）** | 强制人审语义入口 |
| **标签分布 · Fail** | **46.7%（7/15）** | 硬失败用例占比（故意偏多，用于覆盖五维） |

### 3.2 逐条结果（全部 [PASS] = 对齐期望）

| id | 实际 overall | reason |
|----|--------------|--------|
| v0-001 … 003 | Pass | — |
| v0-004 | PassWithRisk | FIDELITY_STRUCTURE |
| v0-005 | PassWithRisk | MOBILE_READABILITY |
| v0-006 | PassWithRisk | BRAND_VIOLATION |
| v0-007 | PassWithRisk | LAYOUT_PLATFORM |
| v0-008 | PassWithRisk | TEXT_ERROR |
| v0-009 | Fail | FIDELITY_STRUCTURE |
| v0-010 | Fail | TEXT_ERROR |
| v0-011 | Fail | BRAND_VIOLATION |
| v0-012 | Fail | LAYOUT_PLATFORM |
| v0-013 | Fail | MOBILE_READABILITY |
| v0-014 | Fail | FIDELITY_STRUCTURE（缺 snapshot） |
| v0-015 | Fail | TEXT_ERROR（占位文案） |

### 3.3 reason_code 频次（Risk + Fail 合计，演示集）

| reason_code | 次数 |
|-------------|------|
| FIDELITY_STRUCTURE | 3 |
| TEXT_ERROR | 3 |
| MOBILE_READABILITY | 2 |
| BRAND_VIOLATION | 2 |
| LAYOUT_PLATFORM | 2 |
| （Pass · None） | 3 |

### 3.4 相关路径 demo（同一会话，非 evalset）

| 场景 | 结果 | 说明 |
|------|------|------|
| `qa-live-demo` Pass | Delivered · auto_approved | QA Pass → 低风险 auto |
| `qa-live-demo` PassWithRisk | Delivered · 经 PendingReview | `reasons=['qa_pass_with_risk']` |
| `qa-live-demo` Fail | QAFailed | 不进入批准 |
| `knowledge-block` | KnowledgePending | Live Gen **阻断**；missing 含 structure_refs / VIS / 平台安全区 |
| `high-risk` | Delivered · forced HITL | PassWithRisk → Lead 批准 |
| `happy`（structure_sensitive） | Delivered · forced HITL | QA 可为 Pass，仍因 `structure_sensitive` 人审 |

**知识闸阻断次数（演示路径）**：本轮 `knowledge-block` **1** 次明确阻断（非批量业务统计）。

**人审打回率**：尚无批量业务统计，**不填虚假 %**。已补 **闭环样本 n=1**（2026-10-13 SGT）：`task_7717b7a94d` · stub gen + 飞书 live IM · `hitl-chat-demo` → `hitl-apply --decision reject --reason FIDELITY_STRUCTURE` → `hitl-rework` → 再次 **PendingReview**（strategy v2 已注入 `HITL_REJECT[FIDELITY_STRUCTURE]`）。看板：chat-demo 未写 bitable `synced_record_ids`，`try_push` 跳过（诚实边界）。Case 表写「闭环样本 n=1」，勿口述成线上打回率。

---

## 4. 与 HITL 如何对齐（口述一句）

> 「评估集证明规则能稳定打出三类 overall；HITL 只消费标签：**Fail 停、Risk 必审、Pass 低风险可 auto，结构敏感/新品即使 Pass 也审。** 人不代审，系统分流。」

映射表：

```
QA Fail              → QAFailed（不 auto）
QA PassWithRisk      → PendingReview（强制）
QA Pass + 结构/新品/豁免 → PendingReview（强制）
QA Pass + 低风险     → Approved（auto，可抽检）
Knowledge ≠ ready    → 阻断 Live Gen（本轮 demo 已验证）
```

---

## 5. 诚实边界（面试加分）

1. **evalset-v0 = 规则 / fixture**，不是真实 SKU 像素级视觉评测；`pass_rate=100%` 是 **期望对齐**，不是「图都过了」。  
2. 标签分布 **故意偏 Fail/Risk**，用于覆盖五维，**不能**当成线上通过率对外吹。  
3. `qa-live-demo` 默认仍走 **rules**；多模态需 `EVAW_QA_MULTIMODAL` + Key，本轮日志为 `multimodal_connected=no`。  
4. 通义 I2I 保真、飞书真实人审打回率、提需→交付耗时：属 **下一阶段真实样本**，当前 Case 不填假数。  
5. 结构敏感品像素级几何一致性：**未**纳入 v0 评估集。

---

## 6. 怎么填 Case 一页里的占位

把 Case「量化」表改成下面口径（已建议同步进 `作品集-EVAW-Case一页.md`）：

| Case 行 | 填法 |
|---------|------|
| QA 通过率（Pass） | **20%（3/15）** · 标注「演示集标签分布，非业务」 |
| PassWithRisk 占比 | **33.3%（5/15）** |
| Fail 占比 | **46.7%（7/15）** |
| 另增一行更佳 | **期望对齐率 100%（15/15）** · `evalset-v0` |
| 知识闸阻断 | **演示路径 1 次**（`knowledge-block`）；批量待业务日志 |
| 人审打回率 | **闭环样本 n=1** · `task_7717b7a94d` Reject→rework→PendingReview（非业务 %） |
| 打回原因 Top | 用演示集 reason：**保真 / 文案 / 移动 / 品牌 / 版式**（各 2–3 次） |

口述开场建议：先报 **对齐率 100%**（规则可信），再报 **标签分布**（人审入口占比），最后一句边界：**「这是演示集，不是线上 KPI。」**

---

## 7. 复现命令

```bash
cd ecommerce-visual-agentic-workflow
python3 -m evaw.cli evalset-v0
python3 -m evaw.cli qa-live-demo   # 可选：HITL 分流对照
python3 -m evaw.cli knowledge-block
```

附件副本：`/workspace/EVAW-量化与评估讲述.md`（与本文同步）。
