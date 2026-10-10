"""Brief & Strategy Agent — stub with deterministic output."""

from __future__ import annotations

from ..schema import (
    CreativeBrief,
    OperationsInput,
    VisualStrategyPackage,
    VisualTask,
    new_id,
    utcnow,
)


class BriefStrategyAgent:
    name = "Brief & Strategy Agent"

    def run(self, task: VisualTask, ops: OperationsInput) -> tuple[CreativeBrief, VisualStrategyPackage]:
        brief = CreativeBrief(
            brief_id=new_id("brief"),
            task_id=task.task_id,
            summary=(
                f"{ops.brand_id}/{ops.sku_id} {ops.asset_type.value} for {ops.platform.value}: "
                f"highlight {', '.join(ops.selling_points[:3])}"
            ),
            selling_points=list(ops.selling_points),
            platform=ops.platform,
            asset_type=ops.asset_type,
            constraints_summary="Inject VIS + structure refs before generation",
            created_at=utcnow(),
        )
        risk_flags = list(ops.risk_flags)
        strategy = VisualStrategyPackage(
            strategy_id=new_id("strat"),
            task_id=task.task_id,
            version="v1",
            scene_direction=(
                "Bedroom lifestyle: guest-room context, full use experience"
                if ops.asset_type.value != "sku"
                else "Clean product cutout with structure-accurate angles"
            ),
            composition_notes="Hero center; safe zone for platform badges; mobile-first crop",
            selling_point_priority=list(ops.selling_points),
            risk_flags=risk_flags,
            created_at=utcnow(),
        )
        return brief, strategy
