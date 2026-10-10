"""Rules QA engine — reproducible checks on candidate metadata / placeholder images.

No multimodal API required. Five dimensions (PRD):
  product_fidelity / brand / text / layout / mobile_readability

Overall aggregation:
  any Fail → Fail; else any Risk → PassWithRisk; else Pass

Fixtures (via req.fixture, risk_flags `qa_fixture:<name>`, or asset.metadata["qa_fixture"]):
  fail_fidelity | fail_text | fail_brand | fail_layout | risk_mobile
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, unquote

from ..schema import (
    STRUCTURE_SENSITIVE,
    DimensionResult,
    DimensionStatus,
    GeneratedAsset,
    QAOverall,
    QAReport,
    ReasonCode,
    new_id,
    utcnow,
)
from .base import QAEvaluateRequest, QAEvaluateResult, QAProvider

QA_DIMENSIONS = (
    "product_fidelity",
    "brand",
    "text",
    "layout",
    "mobile_readability",
)

# Dimension → default reason_code when that dim is the primary issue
DIM_REASON: dict[str, ReasonCode] = {
    "product_fidelity": ReasonCode.FIDELITY_STRUCTURE,
    "brand": ReasonCode.BRAND_VIOLATION,
    "text": ReasonCode.TEXT_ERROR,
    "layout": ReasonCode.LAYOUT_PLATFORM,
    "mobile_readability": ReasonCode.MOBILE_READABILITY,
}

KNOWN_BRANDS = {"brand_xiu", "brand_demo", "brand_acme"}

# Platform preferred hero sizes (soft check)
PLATFORM_SIZE_HINTS: dict[str, set[str]] = {
    "tmall": {"800x800", "750x1000"},
    "jd": {"800x800", "750x1000"},
    "amazon": {"1600x1600", "2000x2000", "800x800"},
    "dtc": {"800x800", "1080x1080", "1200x1200"},
}


def _fixture_from_request(req: QAEvaluateRequest, asset: GeneratedAsset) -> Optional[str]:
    if req.fixture:
        return req.fixture.strip().lower()
    meta_fx = (asset.metadata or {}).get("qa_fixture")
    if meta_fx:
        return str(meta_fx).strip().lower()
    for flag in req.task.risk_flags or []:
        if flag.startswith("qa_fixture:"):
            return flag.split(":", 1)[1].strip().lower()
    return None


def _uri_to_path(uri: str) -> Optional[Path]:
    if not uri:
        return None
    if uri.startswith("stub://"):
        return None
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return Path(unquote(parsed.path))
    p = Path(uri)
    if p.exists():
        return p
    return None


def _png_size(path: Path) -> Optional[tuple[int, int]]:
    """Read IHDR width/height from PNG without Pillow."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    # IHDR: length(4) + b'IHDR'(4) + width(4) + height(4)
    if data[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def _load_manifest_meta(req: QAEvaluateRequest, asset: GeneratedAsset) -> dict[str, Any]:
    """Merge asset.metadata with candidates.json prompt_echo when present."""
    merged: dict[str, Any] = dict(asset.metadata or {})
    path = _uri_to_path(asset.uri)
    if path is None:
        return merged
    manifest = path.parent / "candidates.json"
    if not manifest.exists():
        return merged
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return merged
    for cand in data.get("candidates") or []:
        if cand.get("asset_id") == asset.asset_id or cand.get("uri") == asset.uri:
            echo = cand.get("prompt_echo") or {}
            merged.setdefault("prompt_echo", echo)
            for k, v in echo.items():
                merged.setdefault(k, v)
            break
    return merged


def _aggregate(
    dims: dict[str, DimensionResult],
) -> tuple[QAOverall, Optional[ReasonCode], Optional[str], list[str]]:
    suggested: list[str] = []
    fail_dim: Optional[str] = None
    risk_dim: Optional[str] = None
    for name in QA_DIMENSIONS:
        dr = dims[name]
        if dr.status == DimensionStatus.FAIL and fail_dim is None:
            fail_dim = name
            suggested.append(f"Fix {name}: {dr.notes}")
        elif dr.status == DimensionStatus.RISK and risk_dim is None:
            risk_dim = name
            suggested.append(f"Review {name}: {dr.notes}")

    if fail_dim:
        return (
            QAOverall.FAIL,
            DIM_REASON.get(fail_dim, ReasonCode.OTHER),
            fail_dim,
            suggested,
        )
    if risk_dim:
        return (
            QAOverall.PASS_WITH_RISK,
            DIM_REASON.get(risk_dim, ReasonCode.OTHER),
            risk_dim,
            suggested,
        )
    return QAOverall.PASS, None, None, suggested


class RulesQAProvider(QAProvider):
    name = "rules"
    engine = "rules"

    def evaluate(self, req: QAEvaluateRequest) -> QAEvaluateResult:
        if not req.generation.assets:
            raise RuntimeError("No assets to QA")

        # Evaluate primary (first) candidate; note others in meta
        asset = req.generation.assets[0]
        fixture = _fixture_from_request(req, asset)
        meta = _load_manifest_meta(req, asset)
        path = _uri_to_path(asset.uri)
        dims = self._check_dimensions(req, asset, meta, path, fixture)

        overall, reason, primary, suggested = _aggregate(dims)

        # Optional inject overrides engine (P0 injectable results)
        if req.inject_overall is not None:
            overall = req.inject_overall
            # Keep dims unless inject asks for a clean pass rewrite is not done;
            # inject only forces overall for workflow demos that need stub-like control.
            if overall == QAOverall.PASS:
                reason, primary = None, None
            elif reason is None and overall == QAOverall.PASS_WITH_RISK:
                reason, primary = ReasonCode.FIDELITY_STRUCTURE, "product_fidelity"
            elif reason is None and overall == QAOverall.FAIL:
                reason, primary = ReasonCode.FIDELITY_STRUCTURE, "product_fidelity"

        report = QAReport(
            qa_id=new_id("qa"),
            asset_id=asset.asset_id,
            generation_result_id=req.generation.generation_result_id,
            dimensions=dims,
            overall=overall,
            suggested_fixes=suggested,
            created_at=utcnow(),
            reason_code=reason,
            engine=self.engine,
            mode="live",
            primary_dimension=primary,
        )

        # Persist report next to artifacts when possible
        report_path = self._maybe_write_report(req, report, path)

        return QAEvaluateResult(
            report=report,
            provider_meta={
                "kind": "rules",
                "fixture": fixture,
                "asset_uri": asset.uri,
                "image_path": str(path) if path else None,
                "candidates_evaluated": 1,
                "candidates_total": len(req.generation.assets),
                "report_path": report_path,
                "inject_overall": (
                    req.inject_overall.value if req.inject_overall else None
                ),
                "multimodal": False,
            },
        )

    def _maybe_write_report(
        self,
        req: QAEvaluateRequest,
        report: QAReport,
        path: Optional[Path],
    ) -> Optional[str]:
        out_dir: Optional[Path] = None
        if path is not None:
            out_dir = path.parent
        else:
            out_dir = (
                req.artifacts_dir
                / req.task.task_id
                / req.generation.generation_result_id
            )
            out_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = {
                "qa_id": report.qa_id,
                "asset_id": report.asset_id,
                "generation_result_id": report.generation_result_id,
                "overall": report.overall.value,
                "reason_code": report.reason_code.value if report.reason_code else None,
                "primary_dimension": report.primary_dimension,
                "engine": report.engine,
                "mode": report.mode,
                "suggested_fixes": report.suggested_fixes,
                "dimensions": {
                    k: {
                        "status": v.status.value,
                        "notes": v.notes,
                        "evidence_refs": v.evidence_refs,
                    }
                    for k, v in report.dimensions.items()
                },
                "created_at": report.created_at.isoformat(),
            }
            rp = out_dir / f"{report.qa_id}.json"
            rp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return str(rp)
        except OSError:
            return None

    def _check_dimensions(
        self,
        req: QAEvaluateRequest,
        asset: GeneratedAsset,
        meta: dict[str, Any],
        path: Optional[Path],
        fixture: Optional[str],
    ) -> dict[str, DimensionResult]:
        task = req.task
        evidence = [asset.uri] if asset.uri else []

        # --- product_fidelity ---
        if fixture == "fail_fidelity":
            fidelity = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Fixture fail_fidelity: structure/front confusion (rules)",
                evidence_refs=evidence,
            )
        elif not asset.knowledge_snapshot_id:
            fidelity = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Missing knowledge_snapshot_id on asset (SHALL)",
                evidence_refs=evidence,
            )
        elif not asset.strategy_version:
            fidelity = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Missing strategy_version on asset (SHALL)",
                evidence_refs=evidence,
            )
        elif STRUCTURE_SENSITIVE in (task.risk_flags or []):
            fidelity = DimensionResult(
                status=DimensionStatus.RISK,
                notes=(
                    "structure_sensitive SKU: side-rail / angle near-miss residual risk "
                    "(rules); Lead confirm required"
                ),
                evidence_refs=evidence,
            )
        elif meta.get("fidelity_issue") == "structure":
            fidelity = DimensionResult(
                status=DimensionStatus.FAIL,
                notes=f"Metadata fidelity_issue=structure: {meta.get('fidelity_note', '')}",
                evidence_refs=evidence,
            )
        else:
            fidelity = DimensionResult(
                status=DimensionStatus.PASS,
                notes="Snapshot+strategy bound; no structure risk flags (rules)",
                evidence_refs=evidence,
            )

        # --- brand ---
        brand_id = task.brand_id or meta.get("brand_id") or ""
        if fixture == "fail_brand" or meta.get("brand_violation"):
            brand = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Brand token / VIS violation (fixture or metadata)",
                evidence_refs=evidence,
            )
        elif not brand_id or brand_id in ("brand_unknown", "unknown"):
            brand = DimensionResult(
                status=DimensionStatus.FAIL,
                notes=f"Unknown or empty brand_id={brand_id!r}",
                evidence_refs=evidence,
            )
        elif brand_id not in KNOWN_BRANDS:
            brand = DimensionResult(
                status=DimensionStatus.RISK,
                notes=f"brand_id={brand_id} not in demo VIS registry (soft)",
                evidence_refs=evidence,
            )
        else:
            brand = DimensionResult(
                status=DimensionStatus.PASS,
                notes=f"brand_id={brand_id} ok (rules)",
                evidence_refs=evidence,
            )

        # --- text ---
        selling = []
        if task.strategy:
            selling = list(task.strategy.selling_point_priority or [])
        if not selling and task.brief:
            selling = list(task.brief.selling_points or [])
        echo_selling = meta.get("selling_point_priority") or meta.get("selling_points")
        if echo_selling and not selling:
            selling = list(echo_selling)

        if fixture == "fail_text" or meta.get("text_error"):
            text = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Copy / claim text error (fixture or metadata text_error)",
                evidence_refs=evidence,
            )
        elif not selling:
            text = DimensionResult(
                status=DimensionStatus.RISK,
                notes="No selling points bound for text QA",
                evidence_refs=evidence,
            )
        else:
            # Soft: forbidden placeholder tokens
            joined = " ".join(str(s) for s in selling)
            if re.search(r"TODO|TBD|占位|xxx", joined, re.I):
                text = DimensionResult(
                    status=DimensionStatus.FAIL,
                    notes=f"Placeholder copy detected in selling points: {joined[:80]}",
                    evidence_refs=evidence,
                )
            else:
                text = DimensionResult(
                    status=DimensionStatus.PASS,
                    notes=f"Selling points present ({len(selling)}) (rules)",
                    evidence_refs=evidence,
                )

        # --- layout ---
        platform = task.platform.value if task.platform else meta.get("platform", "")
        size_hint = str(meta.get("size_hint") or meta.get("size_spec") or "")
        if not size_hint and task.brief:
            # brief has no size; ops size not on task — use platform default expectation
            size_hint = ""

        if fixture == "fail_layout" or meta.get("layout_platform_fail"):
            layout = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Platform safe-zone / layout fail (fixture or metadata)",
                evidence_refs=evidence,
            )
        else:
            allowed = PLATFORM_SIZE_HINTS.get(platform, set())
            if size_hint and allowed and size_hint not in allowed:
                layout = DimensionResult(
                    status=DimensionStatus.RISK,
                    notes=(
                        f"size_hint={size_hint} unusual for platform={platform} "
                        f"(allowed≈{sorted(allowed)})"
                    ),
                    evidence_refs=evidence,
                )
            else:
                layout = DimensionResult(
                    status=DimensionStatus.PASS,
                    notes=f"layout ok for platform={platform} size_hint={size_hint or 'n/a'}",
                    evidence_refs=evidence,
                )

        # --- mobile_readability ---
        if fixture == "risk_mobile":
            mobile = DimensionResult(
                status=DimensionStatus.RISK,
                notes="Fixture risk_mobile: crop / type size near threshold",
                evidence_refs=evidence,
            )
        elif fixture == "fail_mobile":
            mobile = DimensionResult(
                status=DimensionStatus.FAIL,
                notes="Fixture fail_mobile: unreadable on mobile viewport",
                evidence_refs=evidence,
            )
        elif path is not None and path.exists():
            dims_wh = _png_size(path)
            if dims_wh is None:
                mobile = DimensionResult(
                    status=DimensionStatus.RISK,
                    notes=f"Could not read image dims at {path}",
                    evidence_refs=evidence + [str(path)],
                )
            else:
                w, h = dims_wh
                if w < 200 or h < 200:
                    mobile = DimensionResult(
                        status=DimensionStatus.FAIL,
                        notes=f"Image too small for mobile QA: {w}x{h}",
                        evidence_refs=evidence + [str(path)],
                    )
                elif w < 400 or h < 400:
                    mobile = DimensionResult(
                        status=DimensionStatus.RISK,
                        notes=(
                            f"Image {w}x{h} below preferred 400px edge "
                            "(placeholder / low-res)"
                        ),
                        evidence_refs=evidence + [str(path)],
                    )
                else:
                    mobile = DimensionResult(
                        status=DimensionStatus.PASS,
                        notes=f"Image {w}x{h} meets mobile min edge (rules)",
                        evidence_refs=evidence + [str(path)],
                    )
        else:
            # stub:// or missing file — skip hard dim check
            mobile = DimensionResult(
                status=DimensionStatus.PASS,
                notes="No local image bytes (stub URI); mobile dims unchecked (rules)",
                evidence_refs=evidence,
            )

        return {
            "product_fidelity": fidelity,
            "brand": brand,
            "text": text,
            "layout": layout,
            "mobile_readability": mobile,
        }
