"""Knowledge Constraint layer (NOT an Agent) — Architecture §3 / §G2.

Loads SKU readiness from the filesystem Knowledge directory (default:
``knowledge/`` at repo root). Falls back to an in-code demo map only if
the directory is missing or empty.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .schema import (
    ExemptionTicket,
    KnowledgeStatus,
    KnowledgeStatusEnum,
    ReasonCode,
    VisualTask,
    new_id,
    utcnow,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def knowledge_root() -> Path:
    """Resolve Knowledge directory (EVAW_KNOWLEDGE_ROOT or ``<repo>/knowledge``)."""
    override = (os.environ.get("EVAW_KNOWLEDGE_ROOT") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (_repo_root() / "knowledge").resolve()


# ---------------------------------------------------------------------------
# In-code fallback (used only when filesystem catalog unavailable)
# ---------------------------------------------------------------------------


DEMO_SKU_KNOWLEDGE: dict[str, dict] = {
    "SKU-BED-001": {
        "status": KnowledgeStatusEnum.READY,
        "missing_items": [],
        "has_vis": True,
        "has_structure": True,
        "has_platform_spec": True,
    },
    "SKU-BED-MISSING": {
        "status": KnowledgeStatusEnum.MISSING,
        "missing_items": [
            "product_structure_refs",
            "vis_brand_tokens",
            "platform_safe_zone_tmall",
        ],
        "has_vis": False,
        "has_structure": False,
        "has_platform_spec": False,
    },
    "SKU-BED-STRUCT": {
        "status": KnowledgeStatusEnum.READY,
        "missing_items": [],
        "has_vis": True,
        "has_structure": True,
        "has_platform_spec": True,
    },
}


# ---------------------------------------------------------------------------
# Normalization / lookup helpers
# ---------------------------------------------------------------------------


def normalize_sku_key(sku_id: str) -> str:
    """Case-insensitive key: upper + hyphen/underscore collapsed to hyphen."""
    s = (sku_id or "").strip()
    s = re.sub(r"[\s_]+", "-", s)
    return s.upper()


@dataclass
class SkuCatalogEntry:
    sku_id: str
    status: KnowledgeStatusEnum
    missing_items: list[str] = field(default_factory=list)
    has_vis: bool = False
    has_structure: bool = False
    has_platform_spec: bool = False
    brand_id: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    source_path: Optional[str] = None
    via_prefix: bool = False

    def as_bind_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "missing_items": list(self.missing_items),
            "has_vis": self.has_vis,
            "has_structure": self.has_structure,
            "has_platform_spec": self.has_platform_spec,
            "brand_id": self.brand_id,
            "source_path": self.source_path,
            "via_prefix": self.via_prefix,
        }


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _status_from_str(raw: Any) -> KnowledgeStatusEnum:
    try:
        return KnowledgeStatusEnum(str(raw or "missing").strip().lower())
    except ValueError:
        return KnowledgeStatusEnum.MISSING


def _validate_refs(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Return missing_items for broken/absent refs when claiming ready."""
    missing: list[str] = []
    has_vis = bool(manifest.get("has_vis"))
    has_structure = bool(manifest.get("has_structure"))
    has_platform = bool(manifest.get("has_platform_spec"))

    vis_ref = manifest.get("vis_ref")
    if has_vis:
        if not vis_ref or not (root / str(vis_ref)).is_file():
            missing.append("vis_brand_tokens")
    else:
        missing.append("vis_brand_tokens")

    structure_ref = manifest.get("structure_ref")
    if has_structure:
        if not structure_ref or not (root / str(structure_ref)).is_file():
            missing.append("product_structure_refs")
    else:
        missing.append("product_structure_refs")

    platform_refs = manifest.get("platform_refs") or []
    if has_platform:
        if not platform_refs:
            missing.append("platform_safe_zone")
        else:
            bad = [p for p in platform_refs if not (root / str(p)).is_file()]
            if bad:
                missing.append("platform_safe_zone")
    else:
        missing.append("platform_safe_zone")

    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _entry_from_manifest(
    root: Path, sku_dir: Path, manifest: dict[str, Any]
) -> SkuCatalogEntry:
    sku_id = str(manifest.get("sku_id") or sku_dir.name).strip()
    status = _status_from_str(manifest.get("status"))
    declared_missing = [str(x) for x in (manifest.get("missing_items") or [])]

    has_vis = bool(manifest.get("has_vis"))
    has_structure = bool(manifest.get("has_structure"))
    has_platform = bool(manifest.get("has_platform_spec"))

    if status == KnowledgeStatusEnum.READY:
        ref_missing = _validate_refs(root, manifest)
        if ref_missing:
            status = KnowledgeStatusEnum.MISSING
            # Prefer declared + validation
            merged = list(declared_missing) + [
                m for m in ref_missing if m not in declared_missing
            ]
            declared_missing = merged or ref_missing
            has_vis = has_vis and "vis_brand_tokens" not in ref_missing
            has_structure = (
                has_structure and "product_structure_refs" not in ref_missing
            )
            has_platform = has_platform and "platform_safe_zone" not in ref_missing
    elif status == KnowledgeStatusEnum.MISSING and not declared_missing:
        declared_missing = [
            "product_structure_refs",
            "vis_brand_tokens",
            "platform_safe_zone",
        ]

    aliases = [str(a).strip() for a in (manifest.get("aliases") or []) if str(a).strip()]

    return SkuCatalogEntry(
        sku_id=sku_id,
        status=status,
        missing_items=declared_missing,
        has_vis=has_vis,
        has_structure=has_structure,
        has_platform_spec=has_platform,
        brand_id=(str(manifest["brand_id"]) if manifest.get("brand_id") else None),
        aliases=aliases,
        source_path=str(sku_dir.relative_to(root)) if sku_dir.is_relative_to(root) else str(sku_dir),
        via_prefix=False,
    )


def _scan_sku_dirs(root: Path) -> dict[str, SkuCatalogEntry]:
    """Map normalized sku keys → entry (primary id + aliases)."""
    index: dict[str, SkuCatalogEntry] = {}
    skus_dir = root / "skus"
    if not skus_dir.is_dir():
        return index

    for child in sorted(skus_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        manifest = _read_json(child / "manifest.json")
        if not manifest:
            continue
        entry = _entry_from_manifest(root, child, manifest)
        keys = {normalize_sku_key(entry.sku_id), normalize_sku_key(child.name)}
        for alias in entry.aliases:
            keys.add(normalize_sku_key(alias))
        for key in keys:
            # First wins; do not overwrite MISSING demo with prefix later
            if key not in index:
                index[key] = entry
    return index


def _apply_prefix_defaults(
    root: Path,
    sku_id: str,
    index: dict[str, SkuCatalogEntry],
) -> Optional[SkuCatalogEntry]:
    catalog = _read_json(root / "catalog.json") or {}
    rules = catalog.get("prefix_defaults") or []
    norm = normalize_sku_key(sku_id)

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        prefix = str(rule.get("prefix") or "")
        if not prefix:
            continue
        case_insensitive = bool(rule.get("match_case_insensitive", True))
        if case_insensitive:
            if not norm.startswith(normalize_sku_key(prefix)):
                continue
        elif not sku_id.startswith(prefix):
            continue

        except_ids = {
            normalize_sku_key(str(x)) for x in (rule.get("except_sku_ids") or [])
        }
        if norm in except_ids:
            return None

        clone_from = str(rule.get("clone_from") or "").strip()
        if not clone_from:
            continue
        template = index.get(normalize_sku_key(clone_from))
        if template is None:
            continue
        return SkuCatalogEntry(
            sku_id=sku_id,
            status=template.status,
            missing_items=list(template.missing_items),
            has_vis=template.has_vis,
            has_structure=template.has_structure,
            has_platform_spec=template.has_platform_spec,
            brand_id=template.brand_id,
            aliases=[],
            source_path=template.source_path,
            via_prefix=True,
        )
    return None


def _fallback_index() -> dict[str, SkuCatalogEntry]:
    index: dict[str, SkuCatalogEntry] = {}
    for sku_id, meta in DEMO_SKU_KNOWLEDGE.items():
        entry = SkuCatalogEntry(
            sku_id=sku_id,
            status=meta["status"],
            missing_items=list(meta["missing_items"]),
            has_vis=bool(meta["has_vis"]),
            has_structure=bool(meta["has_structure"]),
            has_platform_spec=bool(meta["has_platform_spec"]),
            source_path="DEMO_SKU_KNOWLEDGE",
        )
        index[normalize_sku_key(sku_id)] = entry
    return index


@lru_cache(maxsize=4)
def load_sku_catalog(root_str: Optional[str] = None) -> dict[str, SkuCatalogEntry]:
    """Load and cache SKU catalog keyed by normalize_sku_key."""
    root = Path(root_str) if root_str else knowledge_root()
    index = _scan_sku_dirs(root)
    if not index:
        return _fallback_index()
    return index


def clear_catalog_cache() -> None:
    load_sku_catalog.cache_clear()


def lookup_sku_catalog(sku_id: str) -> Optional[dict[str, Any]]:
    """Public helper: resolve sku → bind dict, or None if unknown."""
    root = knowledge_root()
    index = load_sku_catalog(str(root) if root.is_dir() else None)
    key = normalize_sku_key(sku_id)
    entry = index.get(key)
    if entry is None and root.is_dir():
        entry = _apply_prefix_defaults(root, sku_id, index)
    if entry is None:
        return None
    return entry.as_bind_dict()


def list_catalog_skus() -> list[str]:
    root = knowledge_root()
    index = load_sku_catalog(str(root) if root.is_dir() else None)
    # Unique by primary sku_id
    seen: set[str] = set()
    out: list[str] = []
    for entry in index.values():
        if entry.sku_id not in seen:
            seen.add(entry.sku_id)
            out.append(entry.sku_id)
    return sorted(out)


# ---------------------------------------------------------------------------
# Bind / gate / exemption (unchanged contracts)
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeBindResult:
    knowledge: KnowledgeStatus
    allowed_for_live: bool
    block_message: Optional[str] = None


def _resolve_catalog_row(sku_id: str) -> Optional[dict[str, Any]]:
    return lookup_sku_catalog(sku_id)


def bind_knowledge(task: VisualTask) -> KnowledgeBindResult:
    """Resolve KnowledgeStatus for task. Does not mutate status machine."""
    catalog = _resolve_catalog_row(task.sku_id)
    if catalog is None:
        ks = KnowledgeStatus(
            task_id=task.task_id,
            sku_id=task.sku_id,
            status=KnowledgeStatusEnum.MISSING,
            missing_items=["unknown_sku_knowledge_bundle"],
            snapshot_id=None,
        )
        return KnowledgeBindResult(
            knowledge=ks,
            allowed_for_live=False,
            block_message=(
                f"KnowledgeStatus=missing for sku={task.sku_id}; "
                f"missing_items={ks.missing_items}"
            ),
        )

    status = catalog["status"]
    missing = list(catalog["missing_items"])
    snapshot = None
    if status == KnowledgeStatusEnum.READY:
        snapshot = new_id("ksnap")

    # Preserve exemption if already issued
    if task.knowledge_status == KnowledgeStatusEnum.EXEMPTED and task.exemption_ticket_id:
        ks = KnowledgeStatus(
            task_id=task.task_id,
            sku_id=task.sku_id,
            status=KnowledgeStatusEnum.EXEMPTED,
            missing_items=missing,
            exemption_ticket_id=task.exemption_ticket_id,
            snapshot_id=snapshot or new_id("ksnap_exempt"),
        )
        return KnowledgeBindResult(knowledge=ks, allowed_for_live=True)

    ks = KnowledgeStatus(
        task_id=task.task_id,
        sku_id=task.sku_id,
        status=status,
        missing_items=missing,
        snapshot_id=snapshot,
    )
    allowed = status == KnowledgeStatusEnum.READY
    block = None
    if not allowed:
        block = (
            f"KnowledgeStatus={status.value} blocks Live Generation; "
            f"missing_items={missing}"
        )
    return KnowledgeBindResult(
        knowledge=ks, allowed_for_live=allowed, block_message=block
    )


def issue_exemption(
    task: VisualTask,
    *,
    issuer_id: str = "visual_lead",
    reason_code: ReasonCode = ReasonCode.KNOWLEDGE_EXEMPT,
    notes: str = "Lead exemption for urgent deadline",
) -> ExemptionTicket:
    ticket = ExemptionTicket(
        ticket_id=new_id("exempt"),
        task_id=task.task_id,
        issuer_id=issuer_id,
        reason_code=reason_code,
        notes=notes,
        created_at=utcnow(),
    )
    task.exemption_ticket_id = ticket.ticket_id
    task.knowledge_status = KnowledgeStatusEnum.EXEMPTED
    if task.knowledge:
        task.knowledge.status = KnowledgeStatusEnum.EXEMPTED
        task.knowledge.exemption_ticket_id = ticket.ticket_id
        task.knowledge.snapshot_id = task.knowledge.snapshot_id or new_id("ksnap_exempt")
        task.knowledge.updated_at = utcnow()
    return ticket


def assert_may_generate(task: VisualTask) -> None:
    """Hard gate: KnowledgeStatus must be ready or exempted."""
    ks = task.knowledge_status
    if ks == KnowledgeStatusEnum.READY:
        return
    if ks == KnowledgeStatusEnum.EXEMPTED and task.exemption_ticket_id:
        return
    raise PermissionError(
        f"Live Generation blocked: knowledge_status={ks.value} "
        f"(only ready|exempted with ticket allowed)"
    )


# ---------------------------------------------------------------------------
# Structure / VIS constraints for generation prompts + I2I
# ---------------------------------------------------------------------------


@dataclass
class StructureConstraints:
    sku_id: str
    must_show: list[str] = field(default_factory=list)
    must_not: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)
    views: list[str] = field(default_factory=list)
    structure_image: Optional[Path] = None
    structure_json_path: Optional[Path] = None
    platform_notes: list[str] = field(default_factory=list)
    brand_forbidden: list[str] = field(default_factory=list)
    product_name: Optional[str] = None
    structure_sensitive: bool = False


def _manifest_for_sku(sku_id: str) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    """Return (sku_dir, manifest) for a catalogued SKU, or (None, None)."""
    root = knowledge_root()
    if not root.is_dir():
        return None, None
    index = load_sku_catalog(str(root))
    entry = index.get(normalize_sku_key(sku_id))
    if entry is None:
        entry = _apply_prefix_defaults(root, sku_id, index)
    if entry is None or not entry.source_path or entry.source_path == "DEMO_SKU_KNOWLEDGE":
        # Try direct folder name
        direct = root / "skus" / sku_id
        if direct.is_dir():
            manifest = _read_json(direct / "manifest.json")
            return (direct, manifest) if manifest else (None, None)
        return None, None
    sku_dir = root / entry.source_path
    if not sku_dir.is_dir():
        # source_path may be relative like skus/folding-bed-01
        alt = root / str(entry.source_path)
        sku_dir = alt if alt.is_dir() else sku_dir
    manifest = _read_json(sku_dir / "manifest.json") if sku_dir.is_dir() else None
    if not manifest:
        return None, None
    return sku_dir, manifest


def load_structure_constraints(sku_id: str, platform: Optional[str] = None) -> StructureConstraints:
    """Load must_show / must_not / materials / structure_ref image for prompt + I2I."""
    root = knowledge_root()
    sku_dir, manifest = _manifest_for_sku(sku_id)
    out = StructureConstraints(sku_id=sku_id)
    if not sku_dir or not manifest:
        return out

    struct_rel = manifest.get("structure_ref")
    struct_path: Optional[Path] = None
    if struct_rel:
        candidate = root / str(struct_rel)
        if candidate.is_file():
            struct_path = candidate
        elif (sku_dir / "structure.json").is_file():
            struct_path = sku_dir / "structure.json"
    elif (sku_dir / "structure.json").is_file():
        struct_path = sku_dir / "structure.json"

    structure: dict[str, Any] = {}
    if struct_path and struct_path.is_file():
        loaded = _read_json(struct_path)
        if loaded:
            structure = loaded
            out.structure_json_path = struct_path

    out.must_show = [str(x) for x in (structure.get("must_show") or []) if str(x).strip()]
    out.must_not = [str(x) for x in (structure.get("must_not") or []) if str(x).strip()]
    out.materials = [str(x) for x in (structure.get("materials") or []) if str(x).strip()]
    out.views = [
        str(x)
        for x in (structure.get("views") or structure.get("camera_refs") or [])
        if str(x).strip()
    ]
    out.product_name = (
        str(structure["product_name"]).strip()
        if structure.get("product_name")
        else (str(manifest.get("title") or "").strip() or None)
    )
    out.structure_sensitive = bool(
        manifest.get("structure_sensitive") or structure.get("structure_sensitive")
    )

    # Prefer manifest.structure_image, else structure.reference_image next to structure.json
    img: Optional[Path] = None
    img_rel = manifest.get("structure_image")
    if img_rel:
        cand = root / str(img_rel)
        if cand.is_file():
            img = cand
    if img is None:
        ref_name = structure.get("reference_image") or "structure_ref.png"
        cand2 = sku_dir / str(ref_name)
        if cand2.is_file():
            img = cand2
    out.structure_image = img

    # Platform safe-zone / text rules
    plat = (platform or "").strip().lower()
    if plat:
        plat_path = root / "platforms" / f"{plat}.json"
        plat_data = _read_json(plat_path)
        if plat_data:
            safe = plat_data.get("safe_zone") or {}
            if isinstance(safe, dict) and safe.get("notes"):
                out.platform_notes.append(str(safe["notes"]))
            for rule in plat_data.get("text_rules") or []:
                out.platform_notes.append(str(rule))
            canvas = plat_data.get("hero_canvas") or {}
            if isinstance(canvas, dict) and canvas.get("recommended"):
                out.platform_notes.append(f"推荐画布 {canvas['recommended']}")

    # Brand forbidden from VIS
    vis_rel = manifest.get("vis_ref")
    if vis_rel:
        vis = _read_json(root / str(vis_rel))
        if vis:
            out.brand_forbidden = [str(x) for x in (vis.get("forbidden") or []) if str(x).strip()]

    return out
