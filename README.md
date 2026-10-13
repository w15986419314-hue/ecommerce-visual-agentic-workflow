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
                    │  Asset Generation   │──► 2–4 candidates（stub / simulated_live / 豆包 / 万相 / OpenAI）
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

**打回回流：** `PendingReview → Rejected` 后可用 `hitl-rework`（或 `hitl-apply --decision rework`）按 `REASON_DEFAULT_REFLOW` 回到 Generating/Strategized，注入打回反馈再跑 gen+QA；高风险再次 PendingReview。口令见 [`docs/飞书人审聊天说明.md`](docs/%E9%A3%9E%E4%B9%A6%E4%BA%BA%E5%AE%A1%E8%81%8A%E5%A4%A9%E8%AF%B4%E6%98%8E.md)。

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

更多：`live-happy` · `live-knowledge-block` · `feishu-intake` / `feishu-intake-from-json` / `feishu-intake-webhook` / `feishu-bitable-setup` / `feishu-bitable-sync`（真飞书提需：表单→多维表轮询/webhook 建任务）· `feishu-demo` · `hitl-chat-demo` / `hitl-apply` / `hitl-rework`（飞书聊天人审 + 打回回流，不代审）· `--live` / `--qa-live`。

值班常驻轮询见下文「值班：多维表轮询」。飞书提需（表单字段 → VisualTask → 通知）见 [`docs/飞书提需说明.md`](docs/%E9%A3%9E%E4%B9%A6%E6%8F%90%E9%9C%80%E8%AF%B4%E6%98%8E.md)。  
飞书人审（待办含五维 QA / reason_code / 候选图）见 [`docs/飞书人审聊天说明.md`](docs/%E9%A3%9E%E4%B9%A6%E4%BA%BA%E5%AE%A1%E8%81%8A%E5%A4%A9%E8%AF%B4%E6%98%8E.md)。
SKU 知识包（真实 SKU / VIS / 结构图 / 平台规范）见 [`knowledge/README.md`](knowledge/README.md)。

---

## 现状：Feishu / Live Gen（诚实说明）

| 能力 | 现状 |
|------|------|
| **飞书 D3** | 已接 Open API（`FEISHU_APP_ID` + `SECRET`）；无凭证时走 mock。提需支持多维表单字段映射 + **`feishu-bitable-sync` 轮询** / webhook stub / from-json；状态通知、审批跳转可用。运营填：**多维表格表单链接**（见 docs）。 |
| **Live Gen** | **国内默认：通义万相（DashScope `dashscope_wanx`）**。有 `structure_ref.png` 时强制 **I2I**（`wanx-v1` + `repaint`），否则 **T2I**（`wan2.2-t2i-plus`）。**结构敏感品系统自动锁参**（见下），PM 不手拧。`live-happy` 默认 SKU=`folding-bed-01`。设 `DASHSCOPE_API_KEY` 后 `--live` 真出图；备用豆包 / OpenAI；失败回落 **`simulated_live`**。 |
| **Live QA** | 默认 **规则引擎**（五维可复现）；多模态 Vision 需 key + `EVAW_QA_MULTIMODAL=1`，失败回落规则。 |
| **Secrets** | `.env.local` 已 gitignore，**勿提交**密钥。 |

已接国内通道（**通义万相优先**，豆包可选）；补 `DASHSCOPE_API_KEY` 即可真出图，无需改状态机。

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
├── knowledge/               # SKU 知识包（VIS / 结构 / 平台规范）※ 非 Agent
│   ├── README.md            # 如何新增 SKU、补 VIS/结构图/平台规范
│   ├── catalog.json         # 索引 + SKU-BED-* 演示前缀规则
│   ├── platforms/           # tmall · jd · amazon · dtc
│   ├── brands/<id>/vis.json
│   └── skus/<sku_id>/       # manifest.json + structure.json
├── evalset/                 # QA 评估集
│   ├── README.md
│   └── v0/cases.json
├── docs/                    # 飞书提需 / 人审说明
├── artifacts/               # 本地产物（gitignore）
└── evaw/
    ├── schema.py            # 锁定枚举 + VisualQAReport
    ├── state_machine.py
    ├── knowledge.py         # Constraint：扫描 knowledge/ 目录
    ├── hitl.py
    ├── workflow.py
    ├── cli.py
    ├── evalset_v0.py
    ├── providers/           # stub · simulated_live · doubao_ark · dashscope_wanx · openai_images
    ├── qa/                  # stub · rules · multimodal
    ├── feishu/              # mock · api · field_map · webhook · bitable_setup · bitable_sync
    └── agents/              # brief_strategy · generation · visual_qa
```

---

## 环境变量（摘要）

| 变量 | 作用 |
|------|------|
| `EVAW_GEN_MODE=live\|stub` | 出图模式；`--live` / `--stub` 优先 |
| `EVAW_GEN_PROVIDER=auto\|dashscope\|doubao\|openai\|simulated` | Live 强制通道；`auto`=万相→豆包→OpenAI |
| `DASHSCOPE_API_KEY` | **通义万相（国内默认）**；[百炼 API-KEY](https://bailian.console.aliyun.com/) |
| `EVAW_DASHSCOPE_MODEL` | 默认 `wan2.2-t2i-plus`（可用 `wanx-v1` 回退） |
| `EVAW_DASHSCOPE_SIZE` | 默认 `1024*1024` |
| `EVAW_DASHSCOPE_I2I` | 默认开；有结构参考图时走 I2I（`0` 强制纯 T2I） |
| `EVAW_DASHSCOPE_I2I_MODEL` | I2I 模型，默认 `wanx-v1`（支持 `ref_img`） |
| `EVAW_DASHSCOPE_REF_STRENGTH` | 垫图相似度，默认 `0.85`；**结构敏感品自动锁 ≥`0.95`**（弱于 0.95 的 env 会被抬高） |
| `EVAW_DASHSCOPE_REF_MODE` | 默认 `repaint`（保结构）；`refonly`=仅风格 |
| `ARK_API_KEY` / `DOUBAO_API_KEY` | 豆包 Seedream（可选备用）；[方舟 API Key](https://console.volcengine.com/ark/region:ark+cn-beijing/apikey) |
| `EVAW_DOUBAO_MODEL` | 默认 `doubao-seedream-4-0-250828` |
| `EVAW_DOUBAO_SIZE` | 默认 `2K` |
| `EVAW_FORCE_SIMULATED_LIVE=1` | 有 key 也走 simulated_live |
| `EVAW_GEN_FALLBACK_SIMULATED=0` | 关闭「外部 API 失败 → simulated」回落（默认开） |
| `OPENAI_API_KEY` | OpenAI Images / 可选 Vision（CN 常 403） |
| `EVAW_OPENAI_IMAGES_URL` | OpenAI 兼容 Images 网关（可选） |
| `EVAW_QA_MODE=live\|rules\|stub` | QA 模式；`--qa-live` 优先 |
| `EVAW_QA_MULTIMODAL=1` | 开启 Vision 扩展 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书真连 |
| `EVAW_FEISHU_FORCE_MOCK=1` | 强制飞书 mock |

---

## Live Gen（国内）怎么开

1. 在[阿里云百炼](https://bailian.console.aliyun.com/)创建 **API-KEY**（北京）。开通万相文生图（T2I：`wan2.2-t2i-plus`）与垫图能力（I2I：`wanx-v1`）。  
2. 写入本地（**勿提交**）：

```bash
# .env.local
export DASHSCOPE_API_KEY=sk-xxxx
# 可选：export EVAW_DASHSCOPE_MODEL=wan2.2-t2i-plus
# 可选：export EVAW_DASHSCOPE_I2I=1
# 可选：export EVAW_DASHSCOPE_I2I_MODEL=wanx-v1
```

3. 跑真出图（默认 SKU=`folding-bed-01`，有 `structure_ref.png` → I2I）：

```bash
set -a && . ./.env.local && set +a
EVAW_GEN_PROVIDER=dashscope python3 -m evaw.cli live-happy --live
```

日志会出现 `[gen:dashscope] mode=i2i` 或 `mode=t2i`。产物在 `artifacts/<task_id>/<gen_id>/cand_*.png`，`candidates.json` 含 `mode` / prompt / 结构约束。

未配置 `DASHSCOPE_API_KEY` 时：`auto` 依次试豆包 / OpenAI，否则 `simulated_live`；外部失败默认回落 simulated，日志会出现 `[gen:fallback]`。

---

## 诚实边界

- 不编造 CTR / 耗时提升。  
- Knowledge **不是**第 4 个 Agent。  
- 无 `DASHSCOPE_API_KEY` / `ARK_API_KEY`（且无可用 OpenAI）→ **simulated_live，非真实出图**。  
- 无 Vision / 未开多模态 → **规则 QA，非真实多模态**。  
- 评估集通过率 = 规则与标注一致性，≠ 业务 KPI。

---

## License / 用途

个人作品集与面试演示用原型。对齐内部架构/PRD 草案；生产接入需替换密钥、图像通道与人审工作台。

## 值班：多维表轮询（常驻）

无公网 webhook 时，用轮询把表单新行拉进 EVAW。运营只填表；值班开这个进程即可。

**做什么：** 每隔 N 秒扫提需多维表 → 新 `record_id` 建 `VisualTask` →（可选）飞书群通知；建单成功且看板已接线时会回写「看板状态」。按 `record_id` 去重，已同步的不重复建。

```bash
cd ecommerce-visual-agentic-workflow
set -a && . ./.env.local && set +a   # FEISHU_APP_ID / SECRET 等，勿提交 .env.local

# 前台（Ctrl+C 停）
python3 -m evaw.cli feishu-bitable-sync --poll --interval 60 --live-notify

# 后台 + 日志
nohup python3 -m evaw.cli feishu-bitable-sync --poll --interval 60 --live-notify \
  > /tmp/evaw-bitable-poll.log 2>&1 &
echo $! > /tmp/evaw-bitable-poll.pid
```

| 操作 | 命令 |
|------|------|
| 看日志 | `tail -f /tmp/evaw-bitable-poll.log` |
| 停进程 | `kill $(cat /tmp/evaw-bitable-poll.pid)`（或按 `ps` 找 `feishu-bitable-sync` 再 kill） |
| 只跑一次 | `python3 -m evaw.cli feishu-bitable-sync --live-notify`（不要 `--poll`） |

**环境：** `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（必填）；`--live-notify` 还需 `FEISHU_CHAT_ID`。表 ID 可走默认或 `FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID`。全部放 `.env.local`（已 gitignore），**勿提交密钥**。

**诚实边界：** 这是普通进程（`nohup` 可抗 shell 退出），**机器重启或被 kill 后不会自动起来**，不是 systemd / 守护服务（以后若要可再加）。状态文件：`artifacts/feishu_bitable_sync_state.json`。细则见 [`docs/飞书提需说明.md`](docs/%E9%A3%9E%E4%B9%A6%E6%8F%90%E9%9C%80%E8%AF%B4%E6%98%8E.md)「值班轮询」。

---

## 运营看板（Feishu Kanban）

表单提需与 EVAW 进度对齐：状态变化回写多维表「看板状态」列。说明见 [`docs/飞书运营看板说明.md`](docs/飞书运营看板说明.md)。

```bash
python3 -m evaw.cli feishu-kanban-sync --ensure-fields
python3 -m evaw.cli feishu-kanban-sync --all
python3 -m evaw.cli feishu-kanban-sync --map
```

