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

---

## 量化（演示集 · 待填，无虚构指标）

> 以下为 **演示集 / 评估集 v0** 假设位，面试前用真实跑数填入；**勿编造通过率**。

| 指标 | 演示集结果 | 备注 |
|------|------------|------|
| QA 通过率（Pass） | ___% | `evalset-v0` / 现场跑数 |
| PassWithRisk 占比 | ___% | 强制人审入口 |
| Fail 占比 | ___% | |
| 知识闸阻断次数 | ___ | Knowledge≠ready |
| 人审打回率 | ___% | 已批准样本中 |

**打回原因骨架（填 Top）**

| reason_code / 原因 | 次数 | 处理 |
|--------------------|------|------|
| product_fidelity | | |
| brand / VIS | | |
| text / 平台文案 | | |
| layout / mobile | | |
| 其他 | | |

---

## 边界与下一步

### 已完成（闭环）

- **打回回流** — `Rejected` → `hitl-rework` / 飞书「改完再审」→ 注入打回原因再出图/QA → 高风险再入 `PendingReview`

### 下一步

- **更强保真模型** — 结构敏感品评估像素级/几何一致性，不止规则 QA  
- **真实样本评估** — 脱敏真实 SKU 图进 evalset，替换 fixture 触发

---

*一页纸 · 面试口述以「产品决策」开场，再落到闭环与证据。*
