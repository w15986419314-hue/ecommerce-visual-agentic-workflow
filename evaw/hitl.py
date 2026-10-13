"""HITL risk gate + sampling audit (PRD Confirmed policy)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from .schema import (
    KnowledgeStatusEnum,
    QAOverall,
    STRUCTURE_SENSITIVE,
    VisualTask,
)


# Default audit sample rate for low-risk auto-approve pool (D1 confirmed 10–20%)
DEFAULT_AUDIT_SAMPLE_RATE = 0.15


@dataclass
class HitlDecision:
    """Decision after QAPassed / QAPassedWithRisk."""

    force_pending_review: bool
    auto_approve_eligible: bool
    audit_sampled: bool
    reasons: list[str]
    next_hint: str  # PendingReview | Approved


def evaluate_after_qa(
    task: VisualTask,
    overall: QAOverall,
    *,
    audit_sample_rate: float = DEFAULT_AUDIT_SAMPLE_RATE,
    rng: Optional[random.Random] = None,
) -> HitlDecision:
    """
    Rules (Confirmed):
    - PassWithRisk → always PendingReview
    - Pass + (new product OR structure_sensitive OR exempted) → PendingReview
    - Pass + low risk → eligible for auto Approve; sample into PendingReview
    """
    reasons: list[str] = []
    rng = rng or random.Random()

    if overall == QAOverall.PASS_WITH_RISK:
        return HitlDecision(
            force_pending_review=True,
            auto_approve_eligible=False,
            audit_sampled=False,
            reasons=["qa_pass_with_risk"],
            next_hint="PendingReview",
        )

    if overall == QAOverall.FAIL:
        return HitlDecision(
            force_pending_review=False,
            auto_approve_eligible=False,
            audit_sampled=False,
            reasons=["qa_fail"],
            next_hint="QAFailed",
        )

    # overall == Pass
    force = False
    if task.is_new_product:
        force = True
        reasons.append("is_new_product")
    if STRUCTURE_SENSITIVE in (task.risk_flags or []):
        force = True
        reasons.append("structure_sensitive")
    if task.knowledge_status == KnowledgeStatusEnum.EXEMPTED or task.exemption_ticket_id:
        force = True
        reasons.append("knowledge_exempted")

    if force:
        return HitlDecision(
            force_pending_review=True,
            auto_approve_eligible=False,
            audit_sampled=False,
            reasons=reasons,
            next_hint="PendingReview",
        )

    # Low-risk auto-approve pool + sampling audit
    sampled = False
    if audit_sample_rate > 0:
        sampled = rng.random() < audit_sample_rate

    if sampled:
        return HitlDecision(
            force_pending_review=False,
            auto_approve_eligible=True,
            audit_sampled=True,
            reasons=["audit_sampled"],
            next_hint="PendingReview",
        )

    return HitlDecision(
        force_pending_review=False,
        auto_approve_eligible=True,
        audit_sampled=False,
        reasons=["low_risk_auto_approve"],
        next_hint="Approved",
    )


# Chinese labels for the five QA dimensions (Feishu chat readability)
QA_DIM_LABELS_ZH: dict[str, str] = {
    "product_fidelity": "产品保真",
    "brand": "品牌规范",
    "text": "文案准确",
    "layout": "版式/平台",
    "mobile_readability": "移动端可读",
}


def _hitl_risk_summary(task: VisualTask, hitl_reasons: Optional[list[str]] = None) -> str:
    """One-line why this task stopped for human review."""
    bits: list[str] = []
    if task.is_new_product:
        bits.append("新品")
    if STRUCTURE_SENSITIVE in (task.risk_flags or []):
        bits.append("结构敏感")
    if task.knowledge_status == KnowledgeStatusEnum.EXEMPTED or task.exemption_ticket_id:
        bits.append("知识豁免")
    if task.qa and task.qa.overall == QAOverall.PASS_WITH_RISK:
        bits.append("QA=PassWithRisk")
    elif hitl_reasons and "qa_pass_with_risk" in hitl_reasons:
        bits.append("QA=PassWithRisk")
    if hitl_reasons and "audit_sampled" in hitl_reasons:
        bits.append("抽检审计")
    if not bits:
        bits.append("强制人审闸门")
    return " + ".join(bits)


def format_hitl_pending_chat(
    task: VisualTask,
    *,
    hitl_reasons: Optional[list[str]] = None,
) -> str:
    """Rich Feishu PendingReview message: QA five dims, reason_code, candidates, risk.

    Used by hitl-chat-demo so Lead can see what they are approving/rejecting.
    """
    tid = task.task_id
    qa = task.qa
    overall = qa.overall.value if qa else "—"
    reason = qa.reason_code.value if qa and qa.reason_code else "—"
    risk_line = _hitl_risk_summary(task, hitl_reasons)

    lines: list[str] = [
        f"[EVAW 人审待办] task_id={tid}",
        f"状态=PendingReview  sku={task.sku_id}  platform={task.platform.value}",
        f"风险说明：{risk_line}（系统不代审，需你拍板）",
        "",
        f"QA overall={overall}  reason_code={reason}"
        + (f"  primary={qa.primary_dimension}" if qa and qa.primary_dimension else ""),
    ]

    # Five-dimensional detail
    if qa and qa.dimensions:
        lines.append("五维 QA：")
        order = [
            "product_fidelity",
            "brand",
            "text",
            "layout",
            "mobile_readability",
        ]
        seen: set[str] = set()
        for key in order + [k for k in qa.dimensions if k not in order]:
            if key in seen or key not in qa.dimensions:
                continue
            seen.add(key)
            dr = qa.dimensions[key]
            label = QA_DIM_LABELS_ZH.get(key, key)
            note = (dr.notes or "").strip()
            if len(note) > 72:
                note = note[:69] + "…"
            lines.append(f"  · {label}({key})={dr.status.value} — {note or '—'}")
        if qa.suggested_fixes:
            lines.append("建议修复：")
            for fix in qa.suggested_fixes[:3]:
                lines.append(f"  · {fix}")
    else:
        lines.append("五维 QA：（无报告）")

    # Candidate assets
    lines.append("")
    if task.generation and task.generation.assets:
        n = task.generation.candidate_count or len(task.generation.assets)
        lines.append(f"候选图（{n}）：")
        for i, a in enumerate(task.generation.assets, 1):
            uri = a.uri or "—"
            ver = a.version or "—"
            lines.append(f"  {i}. version={ver}  uri={uri}")
        lines.append(
            "说明：stub/simulated 的 uri 是占位路径；正式版会附可点开的预览。"
        )
    else:
        lines.append("候选图：（无）")

    lines.extend(
        [
            "",
            "请人工拍板（本 demo 不会自动代审）：",
            f"· 批准 → 在群里回复：「批准 {tid}」",
            f"  或执行：python3 -m evaw.cli hitl-apply --task {tid} --decision approve",
            f"· 打回 → 在群里回复：「打回 {tid} TEXT_ERROR」（原因码可换）",
            f"  或执行：python3 -m evaw.cli hitl-apply --task {tid} "
            "--decision reject --reason TEXT_ERROR",
            f"· 打回后改完再审 → 群里：「改完再审 {tid}」",
            f"  或执行：python3 -m evaw.cli hitl-rework --task {tid}",
            "",
            "常用原因码：FIDELITY_STRUCTURE / TEXT_ERROR / BRAND_VIOLATION / "
            "LAYOUT_PLATFORM / BUSINESS_JUDGEMENT",
        ]
    )
    return "\n".join(lines)
