"""Feishu 提需字段契约：问卷 / 多维表格 / 机器人 → FeishuBriefPayload.

Canonical EVAW brief fields ↔ Feishu form labels / bitable column names.
Also parses common webhook / bitable record / bot card payload shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import FeishuBriefPayload


# ---------------------------------------------------------------------------
# Canonical field map (ops form ↔ EVAW)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldDef:
    """One intake field."""

    key: str  # EVAW / brief attribute
    label_zh: str  # 运营看到的中文名
    feishu_aliases: tuple[str, ...]  # form / bitable / webhook keys
    required: bool = True
    field_type: str = "text"  # text | single_select | multi_select | datetime | checkbox
    options: tuple[str, ...] = ()
    bitable_type: int = 1  # Feishu bitable field type code
    example: str = ""
    notes: str = ""


# Feishu bitable types: 1 text, 3 single select, 4 multi select, 5 datetime, 7 checkbox
INTAKE_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="brand_id",
        label_zh="品牌",
        feishu_aliases=("brand_id", "品牌", "brand", "Brand"),
        bitable_type=1,
        example="brand_xiu",
    ),
    FieldDef(
        key="sku_id",
        label_zh="SKU",
        feishu_aliases=("sku_id", "SKU", "sku", "商品编码"),
        bitable_type=1,
        example="SKU-BED-001",
    ),
    FieldDef(
        key="platform",
        label_zh="平台",
        feishu_aliases=("platform", "平台", "Platform"),
        field_type="single_select",
        options=("tmall", "jd", "amazon", "dtc"),
        bitable_type=3,
        example="tmall",
    ),
    FieldDef(
        key="asset_type",
        label_zh="图型",
        feishu_aliases=("asset_type", "图型", "asset", "AssetType"),
        field_type="single_select",
        options=("hero", "sku", "pdp_module"),
        bitable_type=3,
        example="hero",
        notes="hero=主图 · sku · pdp_module=详情模块",
    ),
    FieldDef(
        key="selling_points",
        label_zh="卖点",
        feishu_aliases=("selling_points", "卖点", "sellingPoints", "卖点列表"),
        field_type="text",
        bitable_type=1,
        example="稳固承重,快速折叠,客房场景",
        notes="2–5 条，逗号/分号/换行分隔；多维表也可用多选",
    ),
    FieldDef(
        key="size_spec",
        label_zh="尺寸",
        feishu_aliases=("size_spec", "尺寸", "size", "Size"),
        bitable_type=1,
        example="800x800",
    ),
    FieldDef(
        key="deadline",
        label_zh="Deadline",
        feishu_aliases=("deadline", "Deadline", "期望交付日", "deadline_iso"),
        field_type="datetime",
        required=False,
        bitable_type=5,
        example="2026-10-17",
        notes="缺省 = 提交日 + 7 天",
    ),
    FieldDef(
        key="is_new_product",
        label_zh="是否新品",
        feishu_aliases=("is_new_product", "是否新品", "新品", "new_product"),
        field_type="checkbox",
        required=False,
        bitable_type=7,
        example="否",
        notes="是 → 后续强制人审",
    ),
    FieldDef(
        key="risk_flags",
        label_zh="风险标记",
        feishu_aliases=("risk_flags", "风险标记", "风险", "riskFlags"),
        field_type="multi_select",
        required=False,
        options=("structure_sensitive",),
        bitable_type=4,
        example="structure_sensitive",
        notes="勾 structure_sensitive → 强制人审",
    ),
    FieldDef(
        key="requester_id",
        label_zh="提需人",
        feishu_aliases=("requester_id", "提需人", "requester", "提交人"),
        required=False,
        bitable_type=1,
        example="ops_feishu",
    ),
)


def field_map_as_dict() -> dict[str, Any]:
    """Serializable field map for docs / bitable setup output."""
    return {
        "version": "1.0",
        "purpose": "EVAW 飞书提需字段契约（问卷 / 多维表格表单视图 / 机器人引导）",
        "operator_fill_where": {
            "preferred": "飞书多维表格「表单视图」分享链接（运营打开链接填表提交）",
            "alt_bot": "飞书群内 @机器人 按字段问答 / 交互卡片",
            "mvp_fallback": "CLI feishu-intake / feishu-intake-from-json（无公网 webhook 时）",
        },
        "fields": [
            {
                "key": f.key,
                "label_zh": f.label_zh,
                "aliases": list(f.feishu_aliases),
                "required": f.required,
                "field_type": f.field_type,
                "options": list(f.options),
                "bitable_type": f.bitable_type,
                "example": f.example,
                "notes": f.notes,
            }
            for f in INTAKE_FIELDS
        ],
        "webhook_paths": {
            "http_stub": "POST /feishu/intake  (CLI: feishu-intake-webhook)",
            "file_ingest": "feishu-intake-from-json --file <payload.json>",
            "bitable_event": "record.created → map fields → create VisualTask",
        },
    }


def _alias_lookup() -> dict[str, str]:
    m: dict[str, str] = {}
    for f in INTAKE_FIELDS:
        m[f.key.lower()] = f.key
        m[f.label_zh.lower()] = f.key
        for a in f.feishu_aliases:
            m[a.lower()] = f.key
    return m


_ALIAS = _alias_lookup()


def _unwrap_bitable_cell(val: Any) -> Any:
    """Normalize Feishu bitable cell values to plain Python."""
    if val is None:
        return None
    if isinstance(val, list):
        # text cells: [{"text":"...", "type":"text"}]
        if val and isinstance(val[0], dict) and "text" in val[0]:
            return "".join(str(x.get("text", "")) for x in val if isinstance(x, dict))
        # multi-select: ["a","b"] or [{"name":"a"}]
        out = []
        for x in val:
            if isinstance(x, dict):
                out.append(str(x.get("name") or x.get("text") or x.get("id") or ""))
            else:
                out.append(str(x))
        return [x for x in out if x]
    if isinstance(val, dict):
        if "text" in val:
            return val["text"]
        if "name" in val:
            return val["name"]
        if "value" in val:
            return val["value"]
    return val


def _flatten_fields(obj: Any) -> dict[str, Any]:
    """Pull key/value pairs from nested webhook / form / bitable shapes."""
    flat: dict[str, Any] = {}

    def put(k: Any, v: Any) -> None:
        if k is None:
            return
        key = str(k).strip()
        if not key:
            return
        flat[key] = _unwrap_bitable_cell(v)
        canon = _ALIAS.get(key.lower())
        if canon:
            flat[canon] = flat[key]

    if not isinstance(obj, dict):
        return flat

    # Direct brief-like
    for k, v in obj.items():
        if k in ("fields", "form_values", "form", "data", "record", "event"):
            continue
        put(k, v)

    # Nested containers commonly used by Feishu
    for nest_key in ("fields", "form_values", "form", "values"):
        nested = obj.get(nest_key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                put(k, v)
        elif isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("field_name") or item.get("key")
                    put(name, item.get("value") or item.get("text") or item.get("option"))

    data = obj.get("data")
    if isinstance(data, dict):
        flat.update(_flatten_fields(data))

    event = obj.get("event")
    if isinstance(event, dict):
        flat.update(_flatten_fields(event))
        rec = event.get("record") or event.get("object")
        if isinstance(rec, dict):
            flat.update(_flatten_fields(rec))

    record = obj.get("record")
    if isinstance(record, dict):
        flat.update(_flatten_fields(record))

    return flat


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "是", "新品", "new")


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if not s:
        return []
    for sep in ("；", ";", "\n", "，", ","):
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s]


def _as_deadline_iso(v: Any) -> str:
    if v is None or v == "":
        return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    if isinstance(v, (int, float)):
        # Feishu datetime often ms since epoch
        ts = float(v)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    s = str(v).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        pass
    # date only
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()


def payload_to_brief(
    payload: dict[str, Any],
    *,
    default_requester: str = "ops_feishu_form",
) -> FeishuBriefPayload:
    """Map a Feishu webhook / bitable / form JSON blob → FeishuBriefPayload."""
    flat = _flatten_fields(payload)

    def get(*keys: str, default: Any = None) -> Any:
        for k in keys:
            if k in flat and flat[k] not in (None, ""):
                return flat[k]
            # also try via alias map already applied
        return default

    brand = str(get("brand_id", default="") or "").strip()
    sku = str(get("sku_id", default="") or "").strip()
    if not brand or not sku:
        raise ValueError(
            f"提需缺少必填 brand_id/sku_id；got brand={brand!r} sku={sku!r} "
            f"keys={sorted(flat.keys())[:40]}"
        )

    platform = str(get("platform", default="tmall") or "tmall").strip().lower()
    asset_type = str(get("asset_type", default="hero") or "hero").strip().lower()
    points = _as_list(get("selling_points"))
    if not points:
        points = ["待补充卖点"]
    size = str(get("size_spec", default="800x800") or "800x800").strip()
    deadline = _as_deadline_iso(get("deadline"))
    is_new = _as_bool(get("is_new_product", default=False))
    flags = _as_list(get("risk_flags"))
    requester = str(
        get("requester_id", default=default_requester) or default_requester
    ).strip()

    source_message_id = None
    for k in ("source_message_id", "message_id", "uuid", "record_id", "open_message_id"):
        if flat.get(k):
            source_message_id = str(flat[k])
            break
    chat_id = None
    for k in ("chat_id", "open_chat_id"):
        if flat.get(k):
            chat_id = str(flat[k])
            break

    return FeishuBriefPayload(
        brand_id=brand,
        sku_id=sku,
        platform=platform,
        asset_type=asset_type,
        selling_points=points,
        size_spec=size,
        deadline_iso=deadline,
        is_new_product=is_new,
        risk_flags=flags,
        requester_id=requester,
        source_message_id=source_message_id or "webhook_intake",
        chat_id=chat_id,
        raw={"source": "feishu_webhook", "flat_keys": sorted(flat.keys()), "payload": payload},
    )


def bitable_field_specs() -> list[dict[str, Any]]:
    """Specs for Feishu Open API field create (skip requester for form brevity)."""
    specs: list[dict[str, Any]] = []
    for f in INTAKE_FIELDS:
        if f.key == "requester_id":
            continue
        spec: dict[str, Any] = {
            "field_name": f.label_zh,
            "type": f.bitable_type,
            "evaw_key": f.key,
        }
        if f.bitable_type in (3, 4) and f.options:
            spec["property"] = {
                "options": [{"name": o} for o in f.options]
            }
        specs.append(spec)
    return specs


