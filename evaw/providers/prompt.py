"""Shared ecommerce generation prompts with Knowledge structure constraints."""

from __future__ import annotations

from typing import Optional

from ..knowledge import StructureConstraints, load_structure_constraints
from .base import ProviderGenerateRequest


def _join_cn(items: list[str], sep: str = "、") -> str:
    return sep.join(x.strip() for x in items if x and str(x).strip())


def format_structure_block(constraints: StructureConstraints, *, max_chars: int = 280) -> str:
    """Compact structure / platform constraints for T2I/I2I prompts."""
    parts: list[str] = []
    if constraints.product_name:
        parts.append(f"商品：{constraints.product_name}")
    if constraints.must_show:
        parts.append(f"必须呈现：{_join_cn(constraints.must_show)}")
    if constraints.must_not:
        parts.append(f"禁止：{_join_cn(constraints.must_not)}")
    if constraints.materials:
        parts.append(f"材质：{_join_cn(constraints.materials)}")
    if constraints.views:
        parts.append(f"参考视角：{_join_cn(constraints.views[:3])}")
    if constraints.platform_notes:
        parts.append(f"平台：{_join_cn(constraints.platform_notes, sep='；')}")
    if constraints.brand_forbidden:
        parts.append(f"品牌禁忌：{_join_cn(constraints.brand_forbidden)}")
    text = "。".join(parts)
    if text and not text.endswith("。"):
        text += "。"
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def build_ecommerce_prompt(
    req: ProviderGenerateRequest,
    *,
    lang: str = "zh",
    max_chars: int = 480,
    constraints: Optional[StructureConstraints] = None,
) -> str:
    """Build a structure-aware ecommerce prompt.

    Injects must_show / must_not / materials / platform notes from Knowledge
    so even pure T2I describes the real product.
    """
    strategy = req.task.strategy
    scene = strategy.scene_direction if strategy else ""
    composition = strategy.composition_notes if strategy else ""
    selling = (
        "、".join(strategy.selling_point_priority)
        if strategy and lang == "zh"
        else (", ".join(strategy.selling_point_priority) if strategy else "")
    )

    cons = constraints or load_structure_constraints(
        req.task.sku_id, platform=req.task.platform.value
    )
    structure_block = format_structure_block(
        cons, max_chars=max(80, max_chars // 2)
    )

    if lang == "en":
        base = (
            f"Ecommerce product hero image for SKU {req.task.sku_id} "
            f"(brand {req.task.brand_id}), platform {req.task.platform.value}. "
            f"Mode: {req.mode.value}. Scene: {scene}. "
            f"Composition: {composition}. Selling points: {selling}. "
        )
        if structure_block:
            base += f"Structure constraints: {structure_block} "
        base += (
            "Photorealistic, product-accurate structure, marketplace-safe framing, "
            "no fake logos or unreadable text."
        )
    else:
        base = (
            f"电商主图，SKU {req.task.sku_id}，品牌 {req.task.brand_id}，"
            f"平台 {req.task.platform.value}，模式 {req.mode.value}。"
            f"场景：{scene}。构图：{composition}。卖点：{selling}。"
        )
        if structure_block:
            base += structure_block
        base += (
            "严格按实物结构生成，写实商品摄影，电商安全构图，"
            "无虚假 logo、无可读乱码文字。"
        )
        if cons.structure_image:
            base += "已提供结构参考图，保持腿数、铰链、面料与配色一致。"

    if len(base) > max_chars:
        base = base[: max_chars - 1] + "…"
    return base


# ---------------------------------------------------------------------------
# Structure-sensitive I2I: short lock prompt (PM rule — no hand-tuning)
# ---------------------------------------------------------------------------

# Default negative prompt baked for structure-sensitive / structure_ref I2I
STRUCTURE_LOCK_NEGATIVE_PROMPT = "文字, logo, 水印, 缺腿, 车轮, 单板无折痕, 乱码"


def is_structure_sensitive_gen(
    req: ProviderGenerateRequest,
    *,
    constraints: Optional[StructureConstraints] = None,
) -> bool:
    """True when Knowledge marks structure_sensitive OR structure_ref image exists.

    Also respects task.risk_flags containing structure_sensitive.
    """
    from ..schema import STRUCTURE_SENSITIVE

    cons = constraints or load_structure_constraints(
        req.task.sku_id, platform=req.task.platform.value
    )
    if cons.structure_sensitive:
        return True
    if cons.structure_image is not None and cons.structure_image.is_file():
        return True
    if STRUCTURE_SENSITIVE in (req.task.risk_flags or []):
        return True
    return False


def build_structure_lock_prompt(
    req: ProviderGenerateRequest,
    *,
    constraints: Optional[StructureConstraints] = None,
    max_chars: int = 220,
) -> str:
    """Short I2I structure-lock prompt — no lifestyle / sell-point copy.

    Product rule: structure-sensitive SKUs use this instead of the long
    ecommerce prompt so PMs do not hand-tune knobs per run.
    """
    cons = constraints or load_structure_constraints(
        req.task.sku_id, platform=req.task.platform.value
    )
    name = cons.product_name or req.task.sku_id
    must = _join_cn(cons.must_show[:5]) if cons.must_show else "六条支撑腿、双折床面中缝"
    mats = _join_cn(cons.materials[:4]) if cons.materials else ""
    parts = [
        f"白底全身商品摄影，{name}",
        f"完整呈现：{must}",
    ]
    if mats:
        parts.append(f"材质：{mats}")
    parts.append("六腿双折，严格保持参考图结构与比例，无文字无logo无水印无角标")
    base = "。".join(parts) + "。"
    if len(base) > max_chars:
        base = base[: max_chars - 1] + "…"
    return base
