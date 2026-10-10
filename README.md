# Ecommerce Visual Agentic Workflow（EVAW）

**电商视觉素材的可编排 Agent 流水线：Brief → 出图 → 五维 QA → 风险分层人审，飞书最小闭环可接。**

> 1 Workflow · 3 Core Agents · Human in Control  
> 仓库：[github.com/w15986419314-hue/ecommerce-visual-agentic-workflow](https://github.com/w15986419314-hue/ecommerce-visual-agentic-workflow)

面向作品集 / 面试可演示的 Python MVP：标准库为主，本地一条命令跑通三条路径；Live Gen / Live QA / 飞书均可切换 stub ↔ live。

---

## 架构示意

```text
                    ┌─────────────────────┐
   Ops Brief ──────►│  Brief & Strategy   │──► CreativeBrief + VisualStrategy
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Knowledge Constraint│  ※ 约束层，不是第 4 个 Agent
                    │  ready / missing /  │  Knowledge≠ready → 默认阻断 Live Gen
                    │  outdated/exempted  │
                    └──────────┬──────────┘
                               │ ready
                    ┌──────────▼──────────┐
                    │  Asset Generation   │──► 2–4 candidates（stub / simulated_live / OpenAI）
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │     Visual QA       │──► 五维 + overall + reason_code
                    │  rules ± multimodal │     Pass / PassWithRisk / Fail
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
           Fail            PassWithRisk      Pass(+低风险)
         QAFailed         强制人审 HITL     可 auto_approve + 抽检
                               │
                    ┌──────────▼──────────┐
                    │ Feishu D3（可选）    │  提需 · 状态通知 · 审批跳转
                    └─────────────────────┘
```

**HITL 策略（不可回退）：** 新品 / `structure_sensitive` / `PassWithRisk`（及知识豁免）→ **强制人审**；其余 QA Pass 可自动通过并抽样审计。

---

## 三条演示命令

依赖：Python 3.10+（核心路径仅标准库）。

```bash
cd ecommerce-visual-agentic-workflow

# 1) Phase 0：happy / knowledge-block / high-risk
python3 -m evaw.cli all

# 2) Live QA 规则引擎 ×3（Pass / PassWithRisk / Fail）
python3 -m evaw.cli qa-live-demo

# 3) 评估集 v0：规则 QA 对照期望 overall，打印通过率
python3 -m evaw.cli evalset-v0
```

更多：`live-happy` · `live-knowledge-block` · `feishu-intake`（CLI 模拟填表提需）· `feishu-demo` · `hitl-chat-demo` / `hitl-apply`（飞书聊天人审，不代审）· `--live` / `--qa-live`。

飞书提需（表单字段 → VisualTask → 通知）见 [`docs/飞书提需说明.md`](docs/%E9%A3%9E%E4%B9%A6%E6%8F%90%E9%9C%80%E8%AF%B4%E6%98%8E.md)。  
飞书人审（待办含五维 QA / reason_code / 候选图）见 [`docs/飞书人审聊天说明.md`](docs/%E9%A3%9E%E4%B9%A6%E4%BA%BA%E5%AE%A1%E8%81%8A%E5%A4%A9%E8%AF%B4%E6%98%8E.md)。

---

## 现状：Feishu / Live Gen（诚实说明）

| 能力 | 现状 |
|------|------|
| **飞书 D3** | 已接 Open API（`FEISHU_APP_ID` + `SECRET`）；无凭证时走 mock。提需、状态通知、审批跳转可用。 |
| **Live Gen** | 有 `OPENAI_API_KEY` 时尝试 OpenAI Images；**当前运行环境被官方以地区限制拒绝（403 `unsupported_country_region`）**，因此作品集演示默认用 **`simulated_live`** 写本地占位 PNG + `candidates.json`，语义与闸门与真出图一致。 |
| **Live QA** | 默认 **规则引擎**（五维可复现）；多模态 Vision 需 key + `EVAW_QA_MULTIMODAL=1`，失败回落规则。 |
| **Secrets** | `.env.local` 已 gitignore，**勿提交**密钥。 |

换国内图像通道或 OpenAI 兼容 Base URL 后，可将 Gen 切回真出图，无需改状态机。

---

## 评估集

- 说明与字段：[`evalset/README.md`](evalset/README.md)
- 数据：[`evalset/v0/cases.json`](evalset/v0/cases.json)（15 条脱敏案例）
- 跑法：`python3 -m evaw.cli evalset-v0`

维度：`product_fidelity` / `brand` / `text` / `layout` / `mobile_readability`。  
案例用 fixture / 元数据触发规则，**无真实客户图**。

---

## 仓库结构

```text
ecommerce-visual-agentic-workflow/
├── README.md
├── evalset/                 # QA 评估集
│   ├── README.md
│   └── v0/cases.json
├── artifacts/               # 本地产物（gitignore）
└── evaw/
    ├── schema.py            # 锁定枚举 + VisualQAReport
    ├── state_machine.py
    ├── knowledge.py         # Constraint，非 Agent
    ├── hitl.py
    ├── workflow.py
    ├── cli.py
    ├── evalset_v0.py
    ├── providers/           # stub · simulated_live · openai_images
    ├── qa/                  # stub · rules · multimodal
    ├── feishu/              # mock · api
    └── agents/              # brief_strategy · generation · visual_qa
```

---

## 环境变量（摘要）

| 变量 | 作用 |
|------|------|
| `EVAW_GEN_MODE=live\|stub` | 出图模式；`--live` / `--stub` 优先 |
| `EVAW_FORCE_SIMULATED_LIVE=1` | 有 key 也走 simulated_live |
| `OPENAI_API_KEY` | Images / 可选 Vision |
| `EVAW_QA_MODE=live\|rules\|stub` | QA 模式；`--qa-live` 优先 |
| `EVAW_QA_MULTIMODAL=1` | 开启 Vision 扩展 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书真连 |
| `EVAW_FEISHU_FORCE_MOCK=1` | 强制飞书 mock |

---

## 诚实边界

- 不编造 CTR / 耗时提升。  
- Knowledge **不是**第 4 个 Agent。  
- 无可用图像 API → **simulated_live，非真实出图**。  
- 无 Vision / 未开多模态 → **规则 QA，非真实多模态**。  
- 评估集通过率 = 规则与标注一致性，≠ 业务 KPI。

---

## License / 用途

个人作品集与面试演示用原型。对齐内部架构/PRD 草案；生产接入需替换密钥、图像通道与人审工作台。
