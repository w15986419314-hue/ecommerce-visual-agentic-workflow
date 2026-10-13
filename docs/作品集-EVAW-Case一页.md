# AI 产品经理作品 · Ecommerce Visual Agentic Workflow（EVAW）

**吴林栩（Cici）** · 电商视觉负责人 → AI PM · 角色：产品定义 / HITL 策略 / 闭环编排（非纯工程 demo）

---

## 背景 / 问题

电商视觉提需链路常见三类痛点：

1. **提需乱** — 口头/截图混杂，Brief 不可机读，策略与出图反复对不齐  
2. **保真风险** — 结构敏感品（折叠床等）I2I 易漂，参数靠人手拧，翻车成本高  
3. **人审不清** — Pass / 有风险 / Fail 边界模糊，新品与高风险未强制人审，责任难落

---

## 方案

**1 Workflow · 3 Agents** + **Knowledge 约束层（非第 4 Agent）** + **HITL**

| 层 | 职责 |
|----|------|
| Brief & Strategy | Ops Brief → CreativeBrief + VisualStrategy |
| Knowledge（约束） | ready / missing / outdated / exempted；**≠ready 默认阻断 Live Gen** |
| Asset Gen | 候选图；结构敏感走通义万相 I2I，系统锁参 |
| Visual QA | 五维（保真/品牌/文案/版式/移动可读）→ Pass / PassWithRisk / Fail |
| HITL | 风险分层人审；人不代审，系统只分流 |

**HITL 规则（不可回退）**  
新品 / `structure_sensitive` / `PassWithRisk`（及知识豁免）→ **强制人审**；其余 QA Pass 可 **auto + 抽检**。

---

## 闭环（飞书最小可演示）

飞书表单提需 → 多维表轮询建单 → 知识闸 → 通义万相 I2I（结构敏感锁参）→ QA → 飞书人审 → 交付 → **看板状态回写**；打回后可「改完再审」/`hitl-rework` 再入 PendingReview

---

## 我的产品决策（面试主线）

1. **知识 ≠ ready → 阻断 Live Gen** — 缺 VIS/结构/平台规范时不出真图，避免「好看但不合规」。  
2. **结构敏感系统锁参** — I2I strength ≥ 0.95 + 短 prompt；PM/运营不手拧，保真优先于创意自由度。  
3. **看板与 AI 流水线分离、状态映射** — 运营看中文「看板状态」；EVAW 保留细粒度枚举，两边同一 Base 回写对齐。  
4. **诚实边界写进产品** — 地区/模型限制、非像素级保真；失败回落 stub/`simulated_live`，不假装「已全自动上线」。  
5. **HITL 分层不可回退** — 高风险强制人审，低风险可 auto，用抽检守质量，而不是「全部人审」或「全部自动」。

---

## 证据

| 类型 | 链接 |
|------|------|
| GitHub | https://github.com/w15986419314-hue/ecommerce-visual-agentic-workflow |
| Figma | https://www.figma.com/design/VA5vBY8QfMtfvhUJeZKQPq |
| 简历站 | https://cici-visual.netlify.app |
| 面试口述稿 | [`作品集-EVAW-面试口述稿.md`](作品集-EVAW-面试口述稿.md) |
| 量化讲述 | [`作品集-EVAW-量化与评估讲述.md`](作品集-EVAW-量化与评估讲述.md) |
| **业务 Case · 主图详情**（同一品） | [`作品集-Case-主图详情.md`](作品集-Case-主图详情.md) |
| **业务 Case · 短视频**（另一品） | [`作品集-Case-短视频.md`](作品集-Case-短视频.md) |

**与口述对齐：** 主图详情 / 短视频是**两品、两窗、两套证据**；面试分开讲，禁止串成同品故事；业务数字只出现在上述两份 Case，**不混进**下方演示集 KPI。

**飞书运营看板：** 同一 Base 已建「运营看板」视图，按「看板状态」分组（表单提需 → 回写进度）。说明见 [`飞书运营看板说明.md`](飞书运营看板说明.md)。公开可读截图待补：[`assets/`](assets/)（计划 `feishu-ops-kanban.png`），不在此虚构图。

---

## 量化（演示集 · 2026-10-13 实跑，无虚构业务 KPI）

> 来源：`python3 -m evaw.cli evalset-v0`（15 fixture 用例）。**标签分布 ≠ 线上通过率**；详述见 `docs/作品集-EVAW-量化与评估讲述.md`。

| 指标 | 演示集结果 | 备注 |
|------|------------|------|
| 期望对齐率 | **100%（15/15）** | 规则 overall/reason 与期望一致（CLI `pass_rate`） |
| QA 标签 · Pass | **20%（3/15）** | 演示集设计占比，非业务通过率 |
| QA 标签 · PassWithRisk | **33.3%（5/15）** | 强制人审入口 |
| QA 标签 · Fail | **46.7%（7/15）** | 故意偏多以覆盖五维 |
| 知识闸阻断 | **演示 1 次** | `knowledge-block` 路径；批量待业务日志 |
| 人审打回率 | **闭环样本 n=1**（非业务率） | `task_7717b7a94d`：PendingReview→Rejected(`FIDELITY_STRUCTURE`)→rework→PendingReview；飞书 IM 已通知；看板因 chat-demo 未绑 bitable 行跳过 |

**reason_code Top（Risk+Fail · 演示集）**

| reason_code / 原因 | 次数 | 处理 |
|--------------------|------|------|
| FIDELITY_STRUCTURE / 保真 | 3 | 强制人审或 Fail 打回再审 |
| TEXT_ERROR / 文案 | 3 | 补卖点 / 去占位 / 改宣称 |
| MOBILE_READABILITY | 2 | 移动可读性人审或 Fail |
| BRAND_VIOLATION / VIS | 2 | 软 Risk 人审；硬 Fail 阻断 |
| LAYOUT_PLATFORM | 2 | 尺寸/安全区修正 |

---

## 边界与下一步

### 已完成（闭环）

- **打回回流** — `Rejected` → `hitl-rework` / 飞书「改完再审」→ 注入打回原因再出图/QA → 高风险再入 `PendingReview`

### 下一步

- **更强保真模型** — 结构敏感品评估像素级/几何一致性，不止规则 QA  
- **真实样本评估** — 脱敏真实 SKU 图进 evalset，替换 fixture 触发

---

*一页纸 · 面试口述以「产品决策」开场，再落到闭环与证据。*
