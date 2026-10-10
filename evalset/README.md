# EVAW Evalset — Visual QA 评估集

匿名化对照集，用于验证 **规则引擎**（`evaw/qa/rules.py`）五维 QA 与期望 overall / reason_code 是否一致。  
**不含真实客户图**；案例仅通过 fixture 名与元数据触发规则。

## 目录

```text
evalset/
├── README.md          ← 本说明
└── v0/
    └── cases.json     ← 15 条脱敏案例
```

## 案例字段

| 字段 | 说明 |
|------|------|
| `id` | 稳定案例 ID |
| `scenario` | 简短场景描述（脱敏） |
| `dimensions_focus` | 本案主要考察的维度标签 |
| `expected_overall` | `Pass` / `PassWithRisk` / `Fail` |
| `expected_reason_code` | 主因枚举或 `null`（Pass） |
| `fixture` | 合成任务元数据：brand/sku/platform/卖点/risk_flags/`qa_fixture`/snapshot 等 |

维度标签：`product_fidelity` · `brand` · `text` · `layout` · `mobile_readability`

可用 `qa_fixture`：`fail_fidelity` / `fail_text` / `fail_brand` / `fail_layout` / `fail_mobile` / `risk_mobile`

## 如何跑

在仓库根目录：

```bash
# 规则 QA 对照期望，打印逐条结果与通过率
python3 -m evaw.cli evalset-v0
```

退出码：全部匹配 → `0`；有 mismatch → `1`。

## v0 覆盖意图

| overall | 典型触发 |
|---------|----------|
| Pass | 知识绑定 + 在册品牌 + 卖点 + 标准尺寸 |
| PassWithRisk | `structure_sensitive` / `risk_mobile` / 未注册品牌 / 异常 size_hint / 无卖点 |
| Fail | `fail_*` fixture / 缺 snapshot / 占位文案 |

## 诚实边界

- v0 只测 **规则引擎**，不调用 Vision API，不读真实商品图。
- 通过率反映「规则与标注是否一致」，不是线上 CTR / 人审准确率。
- 扩充真人标注或多模态对照时，新增 `evalset/v1/`，勿覆盖 v0 期望。
