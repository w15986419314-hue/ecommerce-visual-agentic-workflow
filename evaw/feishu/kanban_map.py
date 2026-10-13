"""EVAW TaskStatus → ops-facing Feishu Kanban columns (Chinese).

Ops board is status progress for visual demand — separate from AI gen/QA engines.
Kanban columns are a collapsed, readable set; raw EVAW status is also written
for debugging.
"""

from __future__ import annotations

from typing import Optional

from ..schema import TaskStatus


# Field names written to the intake bitable (ops Kanban view groups by 看板状态)
FIELD_KANBAN = "看板状态"
FIELD_TASK_ID = "EVAW任务ID"
FIELD_RAW_STATUS = "EVAW状态"
FIELD_QA = "QA结果"
FIELD_UPDATED = "状态更新时间"

# Single-select options = Kanban columns (order ≈ pipeline left→right)
KANBAN_COLUMNS: tuple[str, ...] = (
    "待策略",
    "策略完成",
    "待补知识",
    "知识就绪",
    "生成中",
    "生成失败",
    "质检中",
    "质检未过",
    "质检通过",
    "质检有风险",
    "待人审",
    "已批准",
    "已打回",
    "已交付",
    "已反馈",
    "已取消",
)

# Fine-grained EVAW → Kanban column
STATUS_TO_KANBAN: dict[str, str] = {
    TaskStatus.DRAFT.value: "待策略",
    TaskStatus.READY_FOR_STRATEGY.value: "待策略",
    TaskStatus.STRATEGIZED.value: "策略完成",
    TaskStatus.KNOWLEDGE_PENDING.value: "待补知识",
    TaskStatus.KNOWLEDGE_READY.value: "知识就绪",
    TaskStatus.GENERATING.value: "生成中",
    TaskStatus.GENERATION_FAILED.value: "生成失败",
    TaskStatus.QA_PENDING.value: "质检中",
    TaskStatus.QA_FAILED.value: "质检未过",
    TaskStatus.QA_PASSED.value: "质检通过",
    TaskStatus.QA_PASSED_WITH_RISK.value: "质检有风险",
    TaskStatus.PENDING_REVIEW.value: "待人审",
    TaskStatus.APPROVED.value: "已批准",
    TaskStatus.REJECTED.value: "已打回",
    TaskStatus.DELIVERED.value: "已交付",
    TaskStatus.FEEDBACK_LINKED.value: "已反馈",
    TaskStatus.CANCELLED.value: "已取消",
}


def kanban_label(status: TaskStatus | str) -> str:
    """Map EVAW TaskStatus (enum or value string) → Chinese Kanban column."""
    key = status.value if isinstance(status, TaskStatus) else str(status)
    return STATUS_TO_KANBAN.get(key, key)


def mapping_table_rows() -> list[dict[str, str]]:
    """Rows for docs / CLI print."""
    rows: list[dict[str, str]] = []
    for st in TaskStatus:
        rows.append(
            {
                "evaw_status": st.value,
                "kanban_zh": STATUS_TO_KANBAN[st.value],
            }
        )
    return rows


def mapping_as_dict() -> dict:
    return {
        "version": "1.0",
        "fields": {
            "kanban": FIELD_KANBAN,
            "task_id": FIELD_TASK_ID,
            "raw_status": FIELD_RAW_STATUS,
            "qa": FIELD_QA,
            "updated_at": FIELD_UPDATED,
        },
        "columns": list(KANBAN_COLUMNS),
        "status_to_kanban": dict(STATUS_TO_KANBAN),
        "notes": (
            "运营看板按「看板状态」建看板视图即可；"
            "EVAW 细状态写在「EVAW状态」；"
            "提需表单字段不变，本套为回写进度列。"
        ),
    }


def qa_label(overall: Optional[str]) -> str:
    if not overall:
        return ""
    return str(overall)
