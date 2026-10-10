"""Persist VisualTask snapshots for cross-CLI HITL (chat approve/reject)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .schema import (
    AssetType,
    CreativeBrief,
    DeliveryPackage,
    DimensionResult,
    DimensionStatus,
    GeneratedAsset,
    GenerationMode,
    GenerationResult,
    GenerationResultStatus,
    KnowledgeStatus,
    KnowledgeStatusEnum,
    Platform,
    QAOverall,
    QAReport,
    ReasonCode,
    ReviewDecision,
    ReviewDecisionEnum,
    StatusTransition,
    TaskStatus,
    VisualStrategyPackage,
    VisualTask,
)


DEFAULT_HITL_DIR = "artifacts/hitl_pending"


def _dt_to_iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _enum_val(v: Any) -> Any:
    if hasattr(v, "value"):
        return v.value
    return v


def task_to_dict(task: VisualTask) -> dict[str, Any]:
    """Serialize VisualTask for HITL round-trip (JSON-safe)."""
    d: dict[str, Any] = {
        "task_id": task.task_id,
        "status": task.status.value,
        "brand_id": task.brand_id,
        "sku_id": task.sku_id,
        "platform": task.platform.value,
        "asset_type": task.asset_type.value,
        "deadline": _dt_to_iso(task.deadline),
        "is_new_product": task.is_new_product,
        "risk_flags": list(task.risk_flags or []),
        "knowledge_status": task.knowledge_status.value,
        "current_strategy_id": task.current_strategy_id,
        "current_generation_result_id": task.current_generation_result_id,
        "current_qa_id": task.current_qa_id,
        "exemption_ticket_id": task.exemption_ticket_id,
        "auto_approved": task.auto_approved,
        "audit_sampled": task.audit_sampled,
        "qa_fail_count": task.qa_fail_count,
        "created_by": task.created_by,
        "created_at": _dt_to_iso(task.created_at),
        "updated_at": _dt_to_iso(task.updated_at),
        "block_reason": task.block_reason,
        "brief": None,
        "strategy": None,
        "knowledge": None,
        "generation": None,
        "qa": None,
        "review": None,
        "delivery": None,
        "history": [],
    }
    if task.brief:
        b = task.brief
        d["brief"] = {
            "brief_id": b.brief_id,
            "task_id": b.task_id,
            "summary": b.summary,
            "selling_points": list(b.selling_points),
            "platform": b.platform.value,
            "asset_type": b.asset_type.value,
            "constraints_summary": b.constraints_summary,
            "created_at": _dt_to_iso(b.created_at),
        }
    if task.strategy:
        s = task.strategy
        d["strategy"] = {
            "strategy_id": s.strategy_id,
            "task_id": s.task_id,
            "version": s.version,
            "scene_direction": s.scene_direction,
            "composition_notes": s.composition_notes,
            "selling_point_priority": list(s.selling_point_priority),
            "risk_flags": list(s.risk_flags),
            "created_at": _dt_to_iso(s.created_at),
        }
    if task.knowledge:
        k = task.knowledge
        d["knowledge"] = {
            "task_id": k.task_id,
            "sku_id": k.sku_id,
            "status": k.status.value,
            "missing_items": list(k.missing_items),
            "exemption_ticket_id": k.exemption_ticket_id,
            "snapshot_id": k.snapshot_id,
            "updated_at": _dt_to_iso(k.updated_at),
        }
    if task.generation:
        g = task.generation
        d["generation"] = {
            "generation_result_id": g.generation_result_id,
            "task_id": g.task_id,
            "mode": g.mode.value,
            "status": g.status.value,
            "knowledge_snapshot_id": g.knowledge_snapshot_id,
            "strategy_version": g.strategy_version,
            "started_at": _dt_to_iso(g.started_at),
            "finished_at": _dt_to_iso(g.finished_at),
            "error_code": g.error_code,
            "error_message": g.error_message,
            "candidate_count": g.candidate_count,
            "assets": [
                {
                    "asset_id": a.asset_id,
                    "task_id": a.task_id,
                    "generation_result_id": a.generation_result_id,
                    "asset_type": a.asset_type,
                    "uri": a.uri,
                    "platform_target": a.platform_target,
                    "mode": a.mode.value,
                    "knowledge_snapshot_id": a.knowledge_snapshot_id,
                    "strategy_version": a.strategy_version,
                    "version": a.version,
                    "metadata": dict(a.metadata or {}),
                }
                for a in g.assets
            ],
        }
    if task.qa:
        q = task.qa
        d["qa"] = {
            "qa_id": q.qa_id,
            "asset_id": q.asset_id,
            "generation_result_id": q.generation_result_id,
            "overall": q.overall.value,
            "suggested_fixes": list(q.suggested_fixes),
            "created_at": _dt_to_iso(q.created_at),
            "reason_code": q.reason_code.value if q.reason_code else None,
            "engine": q.engine,
            "mode": q.mode,
            "primary_dimension": q.primary_dimension,
            "dimensions": {
                name: {
                    "status": dr.status.value,
                    "notes": dr.notes,
                    "evidence_refs": list(dr.evidence_refs),
                }
                for name, dr in q.dimensions.items()
            },
        }
    if task.review:
        r = task.review
        d["review"] = {
            "review_id": r.review_id,
            "task_id": r.task_id,
            "reviewer_id": r.reviewer_id,
            "decision": r.decision.value,
            "reason_code": r.reason_code.value if r.reason_code else None,
            "accept_risk": r.accept_risk,
            "notes": r.notes,
            "created_at": _dt_to_iso(r.created_at),
        }
    if task.delivery:
        p = task.delivery
        d["delivery"] = {
            "delivery_id": p.delivery_id,
            "task_id": p.task_id,
            "asset_ids": list(p.asset_ids),
            "platform": p.platform.value,
            "archived_at": _dt_to_iso(p.archived_at),
            "review_notes": p.review_notes,
        }
    d["history"] = [
        {
            "from_status": h.from_status.value,
            "to_status": h.to_status.value,
            "trigger": h.trigger,
            "at": _dt_to_iso(h.at),
            "meta": dict(h.meta or {}),
        }
        for h in task.history
    ]
    return d


def task_from_dict(d: dict[str, Any]) -> VisualTask:
    """Rehydrate VisualTask from task_to_dict output."""
    task = VisualTask(
        task_id=d["task_id"],
        status=TaskStatus(d["status"]),
        brand_id=d["brand_id"],
        sku_id=d["sku_id"],
        platform=Platform(d["platform"]),
        asset_type=AssetType(d["asset_type"]),
        deadline=_parse_dt(d["deadline"]) or datetime.now(timezone.utc),
        is_new_product=bool(d.get("is_new_product")),
        risk_flags=list(d.get("risk_flags") or []),
        knowledge_status=KnowledgeStatusEnum(
            d.get("knowledge_status") or KnowledgeStatusEnum.MISSING.value
        ),
        current_strategy_id=d.get("current_strategy_id"),
        current_generation_result_id=d.get("current_generation_result_id"),
        current_qa_id=d.get("current_qa_id"),
        exemption_ticket_id=d.get("exemption_ticket_id"),
        auto_approved=bool(d.get("auto_approved")),
        audit_sampled=bool(d.get("audit_sampled")),
        qa_fail_count=int(d.get("qa_fail_count") or 0),
        created_by=d.get("created_by") or "ops_demo",
        created_at=_parse_dt(d.get("created_at")) or datetime.now(timezone.utc),
        updated_at=_parse_dt(d.get("updated_at")) or datetime.now(timezone.utc),
        block_reason=d.get("block_reason"),
    )
    if d.get("brief"):
        b = d["brief"]
        task.brief = CreativeBrief(
            brief_id=b["brief_id"],
            task_id=b["task_id"],
            summary=b["summary"],
            selling_points=list(b["selling_points"]),
            platform=Platform(b["platform"]),
            asset_type=AssetType(b["asset_type"]),
            constraints_summary=b.get("constraints_summary") or "",
            created_at=_parse_dt(b.get("created_at")) or datetime.now(timezone.utc),
        )
    if d.get("strategy"):
        s = d["strategy"]
        task.strategy = VisualStrategyPackage(
            strategy_id=s["strategy_id"],
            task_id=s["task_id"],
            version=s["version"],
            scene_direction=s.get("scene_direction") or "",
            composition_notes=s.get("composition_notes") or "",
            selling_point_priority=list(s.get("selling_point_priority") or []),
            risk_flags=list(s.get("risk_flags") or []),
            created_at=_parse_dt(s.get("created_at")) or datetime.now(timezone.utc),
        )
    if d.get("knowledge"):
        k = d["knowledge"]
        task.knowledge = KnowledgeStatus(
            task_id=k["task_id"],
            sku_id=k["sku_id"],
            status=KnowledgeStatusEnum(k["status"]),
            missing_items=list(k.get("missing_items") or []),
            exemption_ticket_id=k.get("exemption_ticket_id"),
            snapshot_id=k.get("snapshot_id"),
            updated_at=_parse_dt(k.get("updated_at")) or datetime.now(timezone.utc),
        )
    if d.get("generation"):
        g = d["generation"]
        assets = [
            GeneratedAsset(
                asset_id=a["asset_id"],
                task_id=a["task_id"],
                generation_result_id=a["generation_result_id"],
                asset_type=a.get("asset_type") or "hero",
                uri=a.get("uri") or "",
                platform_target=a.get("platform_target") or "",
                mode=GenerationMode(a.get("mode") or GenerationMode.HERO.value),
                knowledge_snapshot_id=a.get("knowledge_snapshot_id") or "",
                strategy_version=a.get("strategy_version") or "",
                version=a.get("version") or "v1",
                metadata=dict(a.get("metadata") or {}),
            )
            for a in (g.get("assets") or [])
        ]
        task.generation = GenerationResult(
            generation_result_id=g["generation_result_id"],
            task_id=g["task_id"],
            mode=GenerationMode(g.get("mode") or GenerationMode.HERO.value),
            status=GenerationResultStatus(
                g.get("status") or GenerationResultStatus.SUCCEEDED.value
            ),
            assets=assets,
            knowledge_snapshot_id=g.get("knowledge_snapshot_id") or "",
            strategy_version=g.get("strategy_version") or "",
            started_at=_parse_dt(g.get("started_at")) or datetime.now(timezone.utc),
            finished_at=_parse_dt(g.get("finished_at")),
            error_code=g.get("error_code"),
            error_message=g.get("error_message"),
            candidate_count=int(g.get("candidate_count") or len(assets)),
        )
    if d.get("qa"):
        q = d["qa"]
        dims = {
            name: DimensionResult(
                status=DimensionStatus(dr["status"]),
                notes=dr.get("notes") or "",
                evidence_refs=list(dr.get("evidence_refs") or []),
            )
            for name, dr in (q.get("dimensions") or {}).items()
        }
        rc = q.get("reason_code")
        task.qa = QAReport(
            qa_id=q["qa_id"],
            asset_id=q["asset_id"],
            generation_result_id=q["generation_result_id"],
            dimensions=dims,
            overall=QAOverall(q["overall"]),
            suggested_fixes=list(q.get("suggested_fixes") or []),
            created_at=_parse_dt(q.get("created_at")) or datetime.now(timezone.utc),
            reason_code=ReasonCode(rc) if rc else None,
            engine=q.get("engine") or "stub",
            mode=q.get("mode") or "stub",
            primary_dimension=q.get("primary_dimension"),
        )
    if d.get("review"):
        r = d["review"]
        rc = r.get("reason_code")
        task.review = ReviewDecision(
            review_id=r["review_id"],
            task_id=r["task_id"],
            reviewer_id=r.get("reviewer_id") or "visual_lead",
            decision=ReviewDecisionEnum(r["decision"]),
            reason_code=ReasonCode(rc) if rc else None,
            accept_risk=bool(r.get("accept_risk")),
            notes=r.get("notes") or "",
            created_at=_parse_dt(r.get("created_at")) or datetime.now(timezone.utc),
        )
    if d.get("delivery"):
        p = d["delivery"]
        task.delivery = DeliveryPackage(
            delivery_id=p["delivery_id"],
            task_id=p["task_id"],
            asset_ids=list(p.get("asset_ids") or []),
            platform=Platform(p["platform"]),
            archived_at=_parse_dt(p.get("archived_at")) or datetime.now(timezone.utc),
            review_notes=p.get("review_notes") or "",
        )
    task.history = [
        StatusTransition(
            from_status=TaskStatus(h["from_status"]),
            to_status=TaskStatus(h["to_status"]),
            trigger=h.get("trigger") or "",
            at=_parse_dt(h.get("at")) or datetime.now(timezone.utc),
            meta=dict(h.get("meta") or {}),
        )
        for h in (d.get("history") or [])
    ]
    return task


def save_task(task: VisualTask, root: str | Path = DEFAULT_HITL_DIR) -> Path:
    root_p = Path(root)
    root_p.mkdir(parents=True, exist_ok=True)
    path = root_p / f"{task.task_id}.json"
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "task": task_to_dict(task),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_task(task_id: str, root: str | Path = DEFAULT_HITL_DIR) -> VisualTask:
    path = Path(root) / f"{task_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"No pending HITL snapshot for {task_id} at {path}. "
            "Run hitl-chat-demo first."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return task_from_dict(payload["task"])


def hitl_snapshot_path(task_id: str, root: str | Path = DEFAULT_HITL_DIR) -> Path:
    return Path(root) / f"{task_id}.json"
