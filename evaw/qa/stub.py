"""Stub QA — injectable overall outcome (Phase 0 / default)."""

from __future__ import annotations

from ..schema import (
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


class StubQAProvider(QAProvider):
    name = "stub"
    engine = "stub"

    def evaluate(self, req: QAEvaluateRequest) -> QAEvaluateResult:
        if not req.generation.assets:
            raise RuntimeError("No assets to QA")

        asset: GeneratedAsset = req.generation.assets[0]
        overall = req.inject_overall or QAOverall.PASS
        risk_note = "Structure angle near-miss on side rail; needs Lead confirm"

        dims: dict[str, DimensionResult] = {}
        suggested: list[str] = []
        reason: ReasonCode | None = None
        primary: str | None = None

        if overall == QAOverall.PASS:
            for d in QA_DIMENSIONS:
                dims[d] = DimensionResult(
                    status=DimensionStatus.PASS,
                    notes=f"{d}: ok (stub)",
                )
        elif overall == QAOverall.PASS_WITH_RISK:
            for d in QA_DIMENSIONS:
                if d == "product_fidelity":
                    dims[d] = DimensionResult(
                        status=DimensionStatus.RISK,
                        notes=risk_note,
                        evidence_refs=[asset.uri],
                    )
                    suggested.append("Tighten side-rail structure ref; re-gen candidate 1")
                    reason = ReasonCode.FIDELITY_STRUCTURE
                    primary = d
                else:
                    dims[d] = DimensionResult(
                        status=DimensionStatus.PASS,
                        notes=f"{d}: ok (stub)",
                    )
        else:  # FAIL
            for d in QA_DIMENSIONS:
                if d == "product_fidelity":
                    dims[d] = DimensionResult(
                        status=DimensionStatus.FAIL,
                        notes="Front/side confusion on headboard (stub fail)",
                        evidence_refs=[asset.uri],
                    )
                    suggested.append("Re-anchor structure refs; regenerate with front lock")
                    reason = ReasonCode.FIDELITY_STRUCTURE
                    primary = d
                else:
                    dims[d] = DimensionResult(
                        status=DimensionStatus.PASS,
                        notes=f"{d}: ok (stub)",
                    )

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
            mode="stub",
            primary_dimension=primary,
        )
        return QAEvaluateResult(
            report=report,
            provider_meta={"kind": "stub", "inject_overall": overall.value},
        )
