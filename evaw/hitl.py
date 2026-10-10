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
