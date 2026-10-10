"""Knowledge Constraint layer (NOT an Agent) — Architecture §3 / §G2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .schema import (
    ExemptionTicket,
    KnowledgeStatus,
    KnowledgeStatusEnum,
    ReasonCode,
    VisualTask,
    new_id,
    utcnow,
)


# Demo SKU knowledge registry: sku_id → ready? missing_items
DEMO_SKU_KNOWLEDGE: dict[str, dict] = {
    # Happy path — full knowledge
    "SKU-BED-001": {
        "status": KnowledgeStatusEnum.READY,
        "missing_items": [],
        "has_vis": True,
        "has_structure": True,
        "has_platform_spec": True,
    },
    # Knowledge block demo
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
    # High-risk HITL demo (structure sensitive, knowledge ready)
    "SKU-BED-STRUCT": {
        "status": KnowledgeStatusEnum.READY,
        "missing_items": [],
        "has_vis": True,
        "has_structure": True,
        "has_platform_spec": True,
    },
}


@dataclass
class KnowledgeBindResult:
    knowledge: KnowledgeStatus
    allowed_for_live: bool
    block_message: Optional[str] = None


def bind_knowledge(task: VisualTask) -> KnowledgeBindResult:
    """Resolve KnowledgeStatus for task. Does not mutate status machine."""
    catalog = DEMO_SKU_KNOWLEDGE.get(task.sku_id)
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
