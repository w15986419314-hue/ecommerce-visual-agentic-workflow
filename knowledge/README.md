# Knowledge 目录（约束层，不是 Agent）

Live Generation 前必须绑定 **KnowledgeStatus**：`ready` / `missing` / `outdated` / `exempted`。  
本目录是 **SKU 知识包的文件系统源**；`evaw/knowledge.py` 启动时扫描这里，不再只靠代码里写死的三四个演示 SKU。

> Knowledge ≠ 第 4 个 Agent。缺包默认阻断出图；Lead 可发豁免工单，但豁免后 **一律强制人审**。

---

## 目录结构

```text
knowledge/
├── README.md                 # 本说明
├── catalog.json              # 索引、前缀默认规则（SKU-BED-* 演示友好）
├── platforms/                # 平台规范（安全区 / 画布 / 文案）
│   ├── tmall.json
│   ├── jd.json
│   ├── amazon.json
│   └── dtc.json
├── brands/<brand_id>/
│   └── vis.json              # 品牌 VIS：色板、字体、语气、禁用项
└── skus/<sku_id>/
    ├── manifest.json         # 必填：status、refs、aliases、missing_items
    └── structure.json        # 结构图约束（ready 时建议有）
```

环境变量（可选）：`EVAW_KNOWLEDGE_ROOT` = 绝对/相对路径，覆盖默认 `knowledge/`。

---

## 怎么判断 ready？

`skus/<sku_id>/manifest.json` 里：

| 字段 | 含义 |
|------|------|
| `status` | `ready` / `missing` / `outdated` |
| `has_vis` / `has_structure` / `has_platform_spec` | 三类资产是否齐 |
| `missing_items` | 缺失清单（missing 时非空） |
| `vis_ref` | 相对本目录的 VIS 路径，如 `brands/YSRJ/vis.json` |
| `structure_ref` | 结构约束路径，如 `skus/sku-bed-01/structure.json` |
| `platform_refs` | 平台规范路径列表 |
| `aliases` | 同款别名（大小写、连字符变体） |

**ready 条件（加载器校验）：** `status=ready` 且三类 `has_*` 为 true，且引用文件存在。否则降为 `missing` 并列出 `missing_items`。

查找顺序：精确 `sku_id` → 别名 → 大小写不敏感规范化 → `catalog.json` 的 **prefix_defaults**（演示用，如 `SKU-BED-*` 除 `SKU-BED-MISSING` 外可继承模板包）。

---

## 如何新增一个真实 SKU

1. **品牌 VIS（若还没有）**  
   复制 `brands/brand_xiu/vis.json` → `brands/<你的 brand_id>/vis.json`，改色板 / 字体 / 禁用项。

2. **建 SKU 目录**  
   ```bash
   mkdir -p knowledge/skus/<SKU_ID>
   ```

3. **写 `manifest.json`**（最小 ready 模板）  
   ```json
   {
     "sku_id": "<SKU_ID>",
     "brand_id": "<brand_id>",
     "status": "ready",
     "aliases": ["可选小写别名"],
     "title": "商品短名",
     "has_vis": true,
     "has_structure": true,
     "has_platform_spec": true,
     "missing_items": [],
     "vis_ref": "brands/<brand_id>/vis.json",
     "structure_ref": "skus/<SKU_ID>/structure.json",
     "platform_refs": [
       "platforms/tmall.json",
       "platforms/jd.json"
     ]
   }
   ```

4. **写 `structure.json`（结构图 / 结构约束）**  
   - `must_show`：出图必须看清的结构点（侧板、铰链、腿数…）  
   - `must_not`：禁止穿帮  
   - `camera_refs`：推荐机位  
   - 可另存结构参考图到同目录（如 `structure_ref.png`），并在 JSON 里加 `"image_refs": ["skus/<SKU_ID>/structure_ref.png"]`（路径相对 `knowledge/`）。

5. **平台规范**  
   - 共用：直接引用 `platforms/*.json`  
   - 某 SKU 特殊安全区：可在 `skus/<SKU_ID>/platform_override_<platform>.json` 并写入 `platform_refs`。

6. **验证**  
   ```bash
   python3 -c "from evaw.knowledge import lookup_sku_catalog; print(lookup_sku_catalog('<SKU_ID>'))"
   ```
   应看到 `status=ready`。再跑一单飞书同步 / `feishu-intake`，不应再进 Knowledge 豁免。

---

## 演示库存（已入库）

| sku_id | 用途 |
|--------|------|
| `SKU-BED-001` | happy path |
| `sku-bed-01` | 用户表单试填（YSRJ / 酒店加床） |
| `SKU-BED-STRUCT` | 结构敏感 / 高风险 HITL |
| `SKU-BED-MISSING` | knowledge-block（**必须保持 missing**） |
| `SKU-BED-FORM-001` / `DEMO` / `NEW` / `BITABLE-001` | 表单与同步试填 |

`catalog.json` 的 prefix 规则：未知的 `SKU-BED-*` / `sku-bed-*`（除 MISSING）在演示环境会继承模板 ready 包，避免再走豁免。正式环境请为每个真实 SKU 建独立目录。

---

## 与流水线的关系

```text
Brief/Strategy → bind_knowledge() 读本目录
                 ├─ ready     → KnowledgeReady → Gen / QA / HITL
                 ├─ missing   → KnowledgePending（可 Lead 豁免）
                 └─ exempted  → 可 Gen，但 HITL 强制人审
```

代码入口：`evaw/knowledge.py`（`load_sku_catalog` / `bind_knowledge`）。
