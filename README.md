# Ecommerce Visual Agentic Workflow — MVP (Phase 0 + Live Gen + Live QA + Feishu D3)

可运行原型：三 Agent + Knowledge Constraint + 风险分层 HITL + **可切换 Live Generation** + **可切换 Live QA（规则 ± 多模态）** + **飞书最小闭环（D3）**。  
对齐文档：

- `../Ecommerce-Visual-Agentic-Workflow-架构方案-v0.1.md`
- `../Ecommerce-Visual-Agentic-Workflow-PRD-v0.2.1.md`

**标语：** 1 Workflow · 3 Core Agents · Human in Control.

> Stub 默认保留。  
> Gen：`--live` / `EVAW_GEN_MODE=live` → Live Gen（有 `OPENAI_API_KEY` 调 OpenAI Images；否则 **simulated_live**）。Knowledge != ready 时 Live 也不能绕过。  
> QA：`--qa-live` / `EVAW_QA_MODE=live|rules` → **规则引擎**（五维 + overall + reason_code）；有 key 且 `EVAW_QA_MULTIMODAL=1` 时可扩展 vision。  
> 飞书：无凭证 → mock；有 `FEISHU_APP_ID`/`SECRET` → Open API。

---

## 已确认策略（不得回退）

| # | 策略 |
|---|------|
| 1 | 三 Agent = Brief & Strategy / Asset Generation / Visual QA；Knowledge = Constraint，**非**第 4 Agent |
| 2 | HITL：新品 / `structure_sensitive` / `PassWithRisk`（及豁免）**强制人审**；其余 QA Pass 可 `auto_approve` + 抽样审计（默认 15%） |
| 3 | `KnowledgeStatus != ready` **默认阻断** Live Generation；豁免 = Lead 工单 + 强制人审 |
| D1–D5 | 候选 **2–4**；QA **规则+多模态**（本阶段默认规则版，多模态可开关）；**飞书最小闭环 = 提需+通知+审批跳转**；Feedback 可顺延；指标优先修正轮次 / Fidelity |

---

## 快速开始

依赖：Python 3.10+。核心路径仅标准库；Pillow 可选（simulated_live 占位图更清晰）。

```bash
cd /workspace/ecommerce-visual-agentic-workflow

# Phase 0 stub 三条路径（默认）
python3 -m evaw.cli all

# Live Gen
python3 -m evaw.cli live-happy
python3 -m evaw.cli live-knowledge-block

# Live QA（规则版，无多模态 API）— Pass / PassWithRisk / Fail
python3 -m evaw.cli qa-live-demo
# 等价
EVAW_QA_MODE=live python3 -m evaw.cli qa-live-demo
python3 -m evaw.cli happy --qa-live

# 飞书 D3
python3 -m evaw.cli feishu-demo
```

---

## Live QA（本步）

### 五维 + 结构化报告

`VisualQAReport`（`schema.QAReport`）字段：

| 字段 | 说明 |
|------|------|
| `dimensions` | `product_fidelity` / `brand` / `text` / `layout` / `mobile_readability` → Pass \| Risk \| Fail |
| `overall` | Pass \| PassWithRisk \| Fail（任一 Fail → Fail；否则任一 Risk → PassWithRisk） |
| `reason_code` | 主因枚举（如 `FIDELITY_STRUCTURE` / `TEXT_ERROR`） |
| `engine` | `stub` \| `rules` \| `multimodal` |
| `mode` | `stub` \| `live` |
| `suggested_fixes` | 修复建议 |

### 模式开关

| 优先级 | 开关 |
|--------|------|
| 1 | CLI `--qa-live` / `--qa-stub` |
| 2 | `EVAW_QA_MODE=stub\|live\|rules`（`live` 与 `rules` 均走规则引擎） |
| 3 | 默认 `stub`（可注入 overall，兼容旧 demo） |
| 场景 | `qa-live-demo` **始终** live QA |

### 无 API key：规则引擎（可复现）

`evaw/qa/rules.py` 检查候选元数据 / 占位图：

- **product_fidelity**：缺 snapshot/strategy → Fail；`structure_sensitive` → Risk
- **brand**：未知 brand → Fail/Risk
- **text**：fixture / `text_error` / 占位文案 → Fail；无卖点 → Risk
- **layout**：平台 size_hint 异常 → Risk
- **mobile_readability**：本地 PNG 边长过小 → Risk/Fail；`stub://` 跳过硬尺寸

Fixture（demo / 注入）：

- `risk_flags` 含 `qa_fixture:fail_text` 等，或 `QAEvaluateRequest.fixture`
- 支持：`fail_fidelity` / `fail_text` / `fail_brand` / `fail_layout` / `fail_mobile` / `risk_mobile`

报告写入：`artifacts/<task_id>/<gen_id>/qa_*.json`

### 多模态扩展（可选，默认未连）

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | Vision 调用凭证 |
| `EVAW_QA_MULTIMODAL=1` | 显式开启（live 模式下 key 在场也可 auto） |
| `EVAW_FORCE_RULES_QA=1` | 强制只用规则，不调 vision |
| `EVAW_QA_VISION_MODEL` | 默认 `gpt-4o-mini` |

有 key 且开启时：`MultimodalQAProvider` 先跑规则，再可选 vision enrich notes；失败则**回落规则**，不静默编造分数。

**当前环境未配置多模态 key → `qa-live-demo` 为规则引擎，未真实连接 Vision API。**

### HITL（与 PRD 一致）

| QA overall | 行为 |
|------------|------|
| PassWithRisk | **强制** PendingReview |
| Pass + 新品/`structure_sensitive`/豁免 | **强制** PendingReview |
| Pass + 低风险 | 可 auto Approve + 抽检 |
| Fail | → `QAFailed`（既有失败路径；不自动放行） |

### `qa-live-demo` 预期

| case | 触发 | overall | 终态 |
|------|------|---------|------|
| pass | 低风险 SKU-BED-001 | Pass | Delivered（auto） |
| pass_with_risk | `structure_sensitive` | PassWithRisk | PendingReview → Lead → Delivered |
| fail | `qa_fixture:fail_text` | Fail | QAFailed |

```bash
python3 -m evaw.cli qa-live-demo
```

---

## 飞书最小闭环（Architecture D3）

### Must / 后置

| 能力 | 状态 |
|------|------|
| 提需 `create_task_from_brief` | ✅ |
| 状态通知 `notify_status` | ✅ |
| 审批跳转 `approval_link` | ✅ 本地控制台占位 |
| 飞书内细打回评论 | 后置 |

解析：`--feishu-mock` / `EVAW_FEISHU_FORCE_MOCK=1` → mock；`FEISHU_APP_ID`+`SECRET` → api；否则 mock。

```bash
python3 -m evaw.cli feishu-demo
```

当前环境无飞书凭证 → **mock，未真实连接飞书 API**。

---

## Live Generation

1. CLI `--live` / `--stub`
2. `EVAW_GEN_MODE=live|stub`
3. `live-*` 场景名始终 live

| 变量 | 行为 |
|------|------|
| `OPENAI_API_KEY` | live → OpenAI Images |
| `EVAW_FORCE_SIMULATED_LIVE=1` | 即使有 key 也 simulated |

无 key → `simulated_live` 写 `artifacts/<task>/…/cand_*.png` + `candidates.json`。

---

## 演示路径

| 命令 | 场景 | 预期终态 |
|------|------|----------|
| `happy` | 低风险 QA Pass | `Delivered` auto |
| `knowledge-block` | Knowledge missing | `KnowledgePending` |
| `high-risk` | 新品+structure+PassWithRisk | `Delivered` 经人审 |
| `live-happy` / `live-knowledge-block` | Live Gen | Delivered / blocked |
| `feishu-demo` | 飞书 D3 | Delivered |
| `qa-live-demo` | Live QA ×3 | Pass→Delivered / PassWithRisk→Delivered / Fail→QAFailed |

---

## 仓库结构

```text
ecommerce-visual-agentic-workflow/
├── README.md
├── artifacts/
├── evaw/
│   ├── schema.py              # VisualQAReport = QAReport（五维+reason_code）
│   ├── state_machine.py
│   ├── knowledge.py
│   ├── hitl.py
│   ├── workflow.py
│   ├── cli.py
│   ├── providers/             # Live Gen
│   ├── qa/                    # Live QA
│   │   ├── base.py
│   │   ├── stub.py            # 可注入 overall
│   │   ├── rules.py           # 规则引擎（默认 live）
│   │   └── multimodal.py      # 可选 vision 扩展
│   ├── feishu/
│   └── agents/
│       ├── brief_strategy.py
│       ├── generation.py
│       └── visual_qa.py
```

---

## 与架构对齐

| 模块 | 对应 |
|------|------|
| `qa/rules.py` + `qa/multimodal.py` | §QA 规则+多模态；P0 规则版可开关 Live |
| `schema.QAReport` | VisualQAReport 五维 + overall + reason_code |
| `hitl.py` | PassWithRisk / 高风险强制人审；Fail → QAFailed |
| `providers/*` | Live Gen |
| `feishu/*` | D3 |

---

## 下一步

1. ~~Live Generation~~  
2. ~~飞书最小闭环~~  
3. ~~Live QA：规则版 + 可开关；多模态可扩展~~（本步；评估集 v0 / 真 vision 联调仍可加深）  
4. 抽样审计工作台  
5. Data Feedback（可顺延）

---

## 诚实边界

- Live Gen：无 image API key → **simulated_live，非真实出图**。  
- Live QA：无 vision key / 未开 `EVAW_QA_MULTIMODAL` → **规则引擎，非真实多模态 API**。  
- 飞书：无凭证 → **mock**。  
- Stub QA 仍保留，可注入 overall。  
- 不编造 CTR / 耗时提升。  
- Knowledge **不是**第 4 个 Agent。  
