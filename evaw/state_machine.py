"""Task status machine — legal transitions only (Architecture §4.2)."""

from __future__ import annotations

from typing import Optional

from .schema import StatusTransition, TaskStatus, VisualTask, utcnow


# Allowed edges: current → frozenset of next
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.DRAFT: frozenset({TaskStatus.READY_FOR_STRATEGY, TaskStatus.CANCELLED}),
    TaskStatus.READY_FOR_STRATEGY: frozenset(
        {TaskStatus.STRATEGIZED, TaskStatus.DRAFT, TaskStatus.CANCELLED}
    ),
    TaskStatus.STRATEGIZED: frozenset(
        {
            TaskStatus.KNOWLEDGE_READY,
            TaskStatus.KNOWLEDGE_PENDING,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.KNOWLEDGE_PENDING: frozenset(
        {
            TaskStatus.KNOWLEDGE_READY,
            TaskStatus.STRATEGIZED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.KNOWLEDGE_READY: frozenset(
        {
            TaskStatus.GENERATING,
            TaskStatus.KNOWLEDGE_PENDING,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.GENERATING: frozenset(
        {
            TaskStatus.QA_PENDING,
            TaskStatus.GENERATION_FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.GENERATION_FAILED: frozenset(
        {
            TaskStatus.GENERATING,
            TaskStatus.KNOWLEDGE_READY,
            TaskStatus.STRATEGIZED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.QA_PENDING: frozenset(
        {
            TaskStatus.QA_FAILED,
            TaskStatus.QA_PASSED,
            TaskStatus.QA_PASSED_WITH_RISK,
        }
    ),
    TaskStatus.QA_FAILED: frozenset(
        {
            TaskStatus.GENERATING,
            TaskStatus.STRATEGIZED,
            TaskStatus.PENDING_REVIEW,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.QA_PASSED: frozenset(
        {TaskStatus.APPROVED, TaskStatus.PENDING_REVIEW}
    ),
    TaskStatus.QA_PASSED_WITH_RISK: frozenset({TaskStatus.PENDING_REVIEW}),
    TaskStatus.PENDING_REVIEW: frozenset(
        {TaskStatus.APPROVED, TaskStatus.REJECTED, TaskStatus.CANCELLED}
    ),
    TaskStatus.REJECTED: frozenset(
        {
            TaskStatus.GENERATING,
            TaskStatus.STRATEGIZED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.APPROVED: frozenset({TaskStatus.DELIVERED}),
    TaskStatus.DELIVERED: frozenset({TaskStatus.FEEDBACK_LINKED}),
    TaskStatus.FEEDBACK_LINKED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class IllegalTransition(Exception):
    def __init__(self, current: TaskStatus, target: TaskStatus):
        self.current = current
        self.target = target
        super().__init__(
            f"Illegal transition: {current.value} → {target.value}"
        )


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def transition(
    task: VisualTask,
    target: TaskStatus,
    trigger: str,
    *,
    meta: Optional[dict] = None,
) -> StatusTransition:
    if not can_transition(task.status, target):
        raise IllegalTransition(task.status, target)
    edge = StatusTransition(
        from_status=task.status,
        to_status=target,
        trigger=trigger,
        at=utcnow(),
        meta=meta or {},
    )
    task.status = target
    task.touch()
    task.history.append(edge)
    return edge
