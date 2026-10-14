# EVAW｜AI PM 面试问答 · 标准答法

| 字段 | 内容 |
|------|------|
| **适用人** | 吴林栩（Cici） |
| **目标岗** | AIGC 电商视觉 / 内容 AI PM |
| **旗舰作品** | EVAW（Brief&Strategy / Asset Generation / Visual QA + Knowledge + HITL） |
| **用法** | 每题先背 **30 秒版**；面试官追问再接 **标准版** |
| **口径** | 只报仓内已有数字；演示集 ≠ 业务 KPI；两套业务 Case 与系统 KPI 分开讲 |

---

## 1. 为什么是 3 个 Agent

### 30 秒版

电商视觉翻车贵在「好看但结构不对」。我拆成三个 Agent：Brief&Strategy 收可机读 Brief 和策略；Asset Gen 在约束下出候选；Visual QA 五维打 Pass / PassWithRisk / Fail。Knowledge 是约束层，不是第四 Agent；HITL 只分流不代审。捆成一个模型不可归因，QA 也没法单独回归。

### 标准版

我做功能家居电商视觉，床架、折叠床这类结构敏感品，AI 出图最怕保真翻车。EVAW 是一条工作流、三个 Agent：Brief&Strategy 把运营提需变成可机读 Brief 和 Visual Strategy；Asset Gen 在 Knowledge 约束下出图，结构敏感走通义万相 I2I；Visual QA 按保真、品牌、文案、版式、移动可读五维出可解释结论。拆开是为了归因和替换：换生成模型不动五维标准，Knowledge 单独做闸门，成本与失败能分段计量。Knowledge 不是第四 Agent，HITL 也不代审。

---

## 2. Knowledge 闸门拦什么

### 30 秒版

Knowledge 看 ready / missing / outdated / exempted。不是 ready，默认阻断 Live 出图——缺结构参考、VIS、平台安全区这类硬约束时，宁可不真出图。demo 里 `knowledge-block` 验过一次阻断。知识豁免可以放行，但后面仍强制人审。

### 标准版

闸门拦的是「知识不齐还硬出真图」。状态不是 ready 时，Live Gen 默认停在 KnowledgePending，missing 常见是 structure_refs、VIS、平台安全区。产品决策是：缺规范就不出真图，避免「好看但不合规」流到人审或上线。豁免路径存在，但 HITL 仍强制人审，不拿豁免当免检。批量业务阻断率还没有，面试只报演示路径已验阻断，不编业务 %。

---

## 3. 什么强制人审

### 30 秒版

四类强制进 PendingReview：新品、`structure_sensitive`、QA 打出 PassWithRisk、以及知识豁免。其余 QA Pass 可以 auto Approve，加抽检。Fail 停在 QAFailed，不进批准。人不代审，系统只分流。

### 标准版

HITL 分层我写成不可回退规则：新品、结构敏感、PassWithRisk、知识豁免——一律强制人审。结构敏感即使 QA 是 Pass 也要审，因为规则过了不等于像素级结构一定对。低风险 Pass 才允许 auto，再用抽检守质量。Fail 不 auto-approve，要改 Brief、素材或知识后再跑。飞书聊天里 Lead 做批准或打回，系统不替人拍板。

---

## 4. 为何锁 I2I 参数

### 30 秒版

结构敏感品 I2I 最怕「创意自由把结构拧歪」。系统锁参：有结构参考图强制走通义万相 I2I，strength 自动抬到 ≥0.95，配短 prompt。PM 和运营不手拧强度。保真优先于创意自由度，翻车成本比多一点花样贵。

### 标准版

折叠床这类 SKU，垫图强度一低，腿数、折叠关节就容易漂。产品决策是结构敏感品系统锁参：有 `structure_ref` 就走万相 I2I，`ref_strength` 弱于 0.95 会被抬高，prompt 偏短、偏约束。我不把「调强度」留给一线临场判断，因为那是责任外溢。创意空间留给 Brief 和场景策略；结构维度先锁死，再进人审兜底。

---

## 5. 打回回流怎么设计

### 30 秒版

PendingReview 被 Reject 后，不口头过。飞书「改完再审」或 `hitl-rework`：注入原因码，再出图、再 QA；高风险再进 PendingReview。闭环样本 n=1：Reject `FIDELITY_STRUCTURE` → rework → 再次待审。不是线上打回率。

### 标准版

打回要形成可复现闭环，不是聊天里改完就算。流程是 PendingReview → Rejected → 按原因码回流 Generating/Strategized，strategy 注入类似 `HITL_REJECT[FIDELITY_STRUCTURE]`，再跑 Gen+QA；高风险再次 PendingReview。已跑通样本 n=1（`task_7717b7a94d`，飞书 IM 已通知）；该条 chat-demo 未绑看板行，看板回写跳过——边界如实讲。批量人审打回率还没有，不填假 %。

---

## 6. 15/15 证明了什么

### 30 秒版

evalset-v0 十五个 fixture，规则引擎 overall 和 reason_code 与期望 **15/15 对齐**。证明 Pass / PassWithRisk / Fail 边界可复现，不是证明「图都过了」。标签分布大约 Pass 20%、Risk 33%、Fail 47%，是演示集设计占比，故意偏 Fail/Risk 盖五维，不是线上通过率。

### 标准版

15/15 是期望对齐率：每条用例的实际结论要对上预设的 overall 和 reason_code。引擎是 Rules QA，用元数据/fixture 触发五维，不是真实客户像素图。所以我对外先说「边界可复现、人审入口从哪来」，再说标签分布给人审分流感。绝不把 20%/33%/47% 讲成业务 QA 通过率，也不把对齐率讲成「上线零幻觉」。像素级几何一致性和脱敏真实图，是下一步评估，当前不编。

---

## 7. PassWithRisk 含义

### 30 秒版

PassWithRisk 是「可交付但有残余风险」——至少一维是 Risk，比如结构临界、品牌软违规、移动可读临界。流水线强制 PendingReview；Lead 可以 accept_risk 后 Approved。它不是 Fail，也不是可以放心 auto 的 Pass。

### 标准版

三类 overall 对应三条后果：Pass 且低风险可 auto；PassWithRisk 强制人审；Fail 停在 QAFailed。PassWithRisk 的产品含义是：系统认为未必必须重做，但责任不能自动放行——要人看见风险点再签字。演示集里五个 Risk 用例覆盖保真、移动、品牌、版式、文案五维入口。面试官若问「和 Fail 差在哪」：Fail 是硬失败要改完再跑；Risk 是可带风险交付，但必须人审。

---

## 8. 主图 CTR 怎么讲（含归因边界）

### 30 秒版

这是业务 Case，不是 EVAW 系统 KPI。同品同窗：功能使用主图 CTR **9.18%**，行业基准 **3.17%**；温馨大流量 CTR 只有约 3.49%——流量不等于效率。详情转化、加购高于行业，整页跳出偏高。非严格对照，只报同向，不作改版因果。短视频是另一品，分开讲。

### 标准版

主图详情包是一线内容策略证据，和 EVAW 演示集数字禁止混谈。观测窗里四版主图并行，功能使用图 CTR 9.18% 对基准 3.17%；展现最大的温馨图 CTR 约 3.49%，说明不能拿流量当好坏。同窗详情转化约 1.01% vs 行业 0.67%、收藏加购约 10.08% vs 4.00%，整页跳出约 68.43% 高于行业 60.50%——承接有同向，也有张力，我不硬圆成「改版成功」。边界三句：非严格随机对照；主图与详情未做因果隔离；与短视频包（另一品，加购 6.87%→12.36% 等）证据独立。和 EVAW 只在方法论挂钩：场景可测、效率优先、归因诚实。

---

## 转岗开场 · 45 秒

我在功能家居电商做视觉负责人八年以上，结构敏感品怎么纠错、场景策略怎么测，一线已经踩过坑。现在转 AI PM，不是只会出图，而是把坑产品化：EVAW 一条工作流、三个 Agent，Knowledge 闸门、I2I 锁参、风险分层人审，飞书提需到看板回写跑通最小闭环。评估集 15/15 证明边界可复现；业务侧另有主图 CTR、短视频加购两套独立证据，跟系统 KPI 分开讲、边界讲清楚。我盯的是问题定义、Agent 边界、HITL 闸门和诚实指标——责任和失败路径必须产品先写清，再谈模型能力。

---

## 临场禁区（自用）

| 禁止 | 正确说法 |
|------|----------|
| 把 20%/33%/47% 说成业务通过率 | 「演示集标签分布」 |
| 把 15/15 说成「图都过了」 | 「期望对齐，边界可复现」 |
| 主图/短视频数字说成 EVAW 产出 | 「业务 Case，方法论挂钩」 |
| 两套业务 Case 串成同品故事 | 「两品、两窗、两套证据」 |
| 打回 n=1 说成线上打回率 | 「闭环样本 n=1」 |
| Knowledge 说成第四 Agent | 「约束层」 |
| 称已全自动商用 | 「可演示闭环 MVP」 |

---

*口径对齐：`docs/作品集-EVAW-Case一页.md` · `docs/作品集-EVAW-量化与评估讲述.md` · `docs/作品集-Case-主图详情.md` · `docs/作品集-Case-短视频.md` · 2026-10-14*
