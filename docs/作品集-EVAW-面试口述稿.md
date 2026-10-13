# EVAW｜AI 产品经理面试口述稿（约 3 分钟）

| 字段 | 内容 |
|------|------|
| **适用人** | 吴林栩（Cici） |
| **产品** | Ecommerce Visual Agentic Workflow（EVAW） |
| **总时长** | 约 3 分钟（主稿约 550–700 字，口语约 220–240 字/分钟） |
| **讲法** | 以**产品决策**开场 → 闭环 → 演示集数字 → 边界与链接；括号可省略 |

---

## 一、主口述稿（约 3 分钟）

### 【开场 · 产品决策 · 约 45 秒】（约 160–180 字）

我做功能家居电商视觉。床架、折叠床这类结构敏感 SKU，AI 出图常「好看但结构不对」，客诉和品牌信任都贵。我做的不是又一款一键出图，而是 **EVAW：一条工作流、三个 Agent，加 Knowledge 闸门和 HITL**。

产品上我钉死五条决策：第一，知识不是 ready，**默认阻断 Live 出图**；第二，结构敏感品系统锁 I2I 参数，运营不手拧；第三，看板中文状态和流水线细粒度枚举分离、同一 Base 回写；第四，边界写进产品，失败可回落 stub，不假装已全自动商用；第五，HITL 分层不可回退——高风险强制人审，低风险可 auto 加抽检。

### 【闭环 · 约 70 秒】（约 240–280 字）

落地是飞书最小闭环：运营填**飞书表单** → 多维表**轮询建任务** → Knowledge 闸 → 结构敏感走通义万相 **I2I 锁参** → Visual QA 五维打 Pass / PassWithRisk / Fail → **飞书聊天人审** → Delivered，同时**看板状态回写**。人审打回后走「**改完再审**」：注入原因码再出图再 QA，高风险再次进 PendingReview，不是口头改完就算。

三个 Agent 各管一段：Brief & Strategy 把提需收成可机读 Brief 和策略；Asset Gen 在约束下出候选；Visual QA 按保真、品牌、文案、版式、移动可读五维给可解释结论。中间的 Knowledge 是**约束层，不是第四个 Agent**——VIS、真实结构、平台规范没齐，就不让真图空转。HITL 只分流不代审：新品、structure_sensitive、PassWithRisk 必须人审；其余 QA Pass 可自动放行再抽检。

### 【数字与边界 · 约 40 秒】（约 140–160 字）

量化只报本机真实跑数。评估集 v0 共 15 条 fixture：**期望对齐率 15/15**，说明规则能稳定打出三类 overall；标签分布是 Pass 约 **20%**、PassWithRisk 约 **33%**、Fail 约 **47%**——这是**演示集设计占比**，故意偏 Risk/Fail 来盖五维，**不是线上 KPI，也不是业务通过率**。下一步才是脱敏真实 SKU 图和更强保真评测。成功标准是闸门生效、任务可归因，不是「模型更强」。

### 【收束 · 链接 · 约 15 秒】（约 50–70 字）

代码在 GitHub，交互在 Figma，作品集 Case 一页有闭环图和决策表。我可以按 Knowledge 阻断、结构敏感强制人审、或打回改完再审任一条路径现场演示。

---

## 二、口播全文（连读版 · 约 3 分钟）

> 我做功能家居电商视觉。床架、折叠床这类结构敏感 SKU，AI 出图常「好看但结构不对」，客诉和品牌信任都贵。我做的不是又一款一键出图，而是 EVAW：一条工作流、三个 Agent，加 Knowledge 闸门和 HITL。
>
> 产品上我钉死五条决策：知识不是 ready，默认阻断 Live 出图；结构敏感品系统锁 I2I 参数，运营不手拧；看板中文状态和流水线细粒度枚举分离、同一 Base 回写；边界写进产品，失败可回落 stub，不假装已全自动商用；HITL 分层不可回退——高风险强制人审，低风险可 auto 加抽检。
>
> 落地是飞书最小闭环：运营填飞书表单，多维表轮询建任务，过 Knowledge 闸，结构敏感走通义万相 I2I 锁参，Visual QA 五维打 Pass、PassWithRisk 或 Fail，飞书聊天人审，Delivered 并回写看板。人审打回后走「改完再审」：注入原因码再出图再 QA，高风险再次进 PendingReview。
>
> 三个 Agent：Brief & Strategy 收结构化 Brief；Asset Gen 约束下出候选；Visual QA 五维可解释结论。Knowledge 是约束层不是第四 Agent。HITL 只分流不代审。
>
> 评估集 v0 十五个用例，期望对齐十五比十五；标签分布大约 Pass 两成、Risk 三成、Fail 近一半——这是演示集，不是线上 KPI。GitHub、Figma 和 Case 一页都在，我可以现场跑阻断、强制人审或改完再审。

---

## 三、链接（背得出即可）

| 类型 | URL |
|------|-----|
| **GitHub** | https://github.com/w15986419314-hue/ecommerce-visual-agentic-workflow |
| **Figma** | https://www.figma.com/design/VA5vBY8QfMtfvhUJeZKQPq |
| **Case 一页** | 仓库 `docs/作品集-EVAW-Case一页.md`；简历站 https://cici-visual.netlify.app |

---

## 四、高频追问 · 各 2–3 句

### 1. 幻觉 / 保真怎么控？承诺零幻觉吗？

不承诺零幻觉。生成前 Knowledge ≠ ready 默认阻断；结构敏感 I2I 锁参；生成后 QA 盯保真；高风险强制人审，低风险抽检。原因码回流「改完再审」和禁用规则。

### 2. 评估集怎么建？20%/33%/47% 是业务通过率吗？

**不是。** 那是 evalset-v0 的**标签分布**（15 fixture，规则引擎对照期望）。对齐率 15/15 证明边界可复现；Fail/Risk 故意偏多盖五维。业务通过率要等脱敏真实图，当前不编。

### 3. 为什么拆三个 Agent，不合成一个？

需求、出图、质检捆一起不可归因，QA 没法单独回归，人审也插不进。拆开后换生成模型不动五维标准；Knowledge 单独做闸门，成本与失败可分段计量。

### 4. 打回之后怎么走？

PendingReview → Rejected 后，飞书「改完再审」或 `hitl-rework`：按原因码回流再 Gen+QA；高风险再进 PendingReview，不是改完口头过。

### 5. 为什么是你来做 AI PM？

八年以上视觉、现任电商视觉负责人，结构纠错和场景策略先在一线验证再产品化。AI PM 我盯问题定义、Agent 边界、HITL 闸门和诚实指标；责任边界和失败路径必须产品先写清。

### 6. 现在上线了吗？能商用吗？

飞书提需/轮询/人审/看板、通义万相 I2I、规则 QA 与评估集可演示；无 Key 回落 stub/`simulated_live`。这是**可演示闭环 MVP**，不是「已全自动商用」。像素级几何一致性、真实人审打回率是下一步。

---

## 五、临场提示（自用）

| 项 | 提示 |
|----|------|
| 语速 | 约 220–240 字/分钟；决策条与闭环段之间停半拍 |
| 可白板 | 表单 → poll → Knowledge 闸 → I2I 锁参 → QA → 聊天 HITL → Delivered → 看板；Reject → 改完再审 |
| 禁止 | 把 20%/33%/47% 说成业务 KPI；称已商用全自动；Knowledge 说成第四 Agent；编造 CTR/耗时涨幅 |
| Demo 锚点 | `knowledge-block` 阻断 · `structure_sensitive` 即使 Pass 也人审 · Reject「改完再审」· `evalset-v0` 对齐率 |
| 开场优先 | **先讲五条产品决策**，再讲飞书闭环与数字 |

---

*与 `docs/作品集-EVAW-Case一页.md`、`docs/作品集-EVAW-量化与评估讲述.md` 口径一致 · 2026-10-13*
