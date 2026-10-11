"""Feishu/Lark adapter interface (Architecture D3 minimal loop).

Must: 提需 + 状态通知 + 审批跳转
Out of scope for MVP: 飞书内细打回评论（细打回走控制台）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from ..schema import OperationsInput, TaskStatus, VisualTask


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FeishuBriefPayload:
    """Inbound brief from Feishu form / bot / card (提需)."""

    brand_id: str
    sku_id: str
    platform: str
    asset_type: str
    selling_points: list[str]
    size_spec: str
    deadline_iso: str
    is_new_product: bool = False
    risk_flags: list[str] = field(default_factory=list)
    requester_id: str = "ops_feishu"
    # Pack / multi-deliverable (v1.1) — optional; kept on brief for intake + raw
    image_count: Optional[int] = None
    sku_variants: list[str] = field(default_factory=list)
    pack_slots: list[str] = field(default_factory=list)
    pdp_modules: list[str] = field(default_factory=list)
    source_message_id: Optional[str] = None
    chat_id: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeishuTaskRef:
    """Handle returned after create_task_from_brief."""

    intake_id: str
    task_id: Optional[str]  # filled after VisualTask is created
    ops: OperationsInput
    adapter: str
    external_ref: Optional[str] = None  # Feishu message/bitable id when live
    mock_path: Optional[str] = None


@dataclass
class NotifyResult:
    ok: bool
    channel: str  # mock_file | feishu_im | noop
    message_id: Optional[str] = None
    detail: str = ""
    path: Optional[str] = None


@dataclass
class ApprovalLinkResult:
    url: str
    task_id: str
    console: bool  # True = local console placeholder (细打回在此)
    detail: str = ""


class FeishuAdapter(ABC):
    """Pluggable Feishu surface for D3."""

    name: str = "base"

    @abstractmethod
    def create_task_from_brief(self, brief: FeishuBriefPayload) -> FeishuTaskRef:
        """Parse Feishu brief → OperationsInput + intake record (提需入口)."""
        ...

    @abstractmethod
    def notify_status(
        self,
        task: VisualTask,
        *,
        previous_status: Optional[TaskStatus] = None,
        note: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> NotifyResult:
        """Push status-change notification to Feishu (or mock)."""
        ...

    @abstractmethod
    def approval_link(self, task: VisualTask) -> ApprovalLinkResult:
        """URL for Lead to review/approve (跳转控制台；细打回不在飞书内)."""
        ...


    def send_chat_text(self, text: str) -> NotifyResult:
        """Send free-form IM text (chat HITL instructions). Default: noop."""
        return NotifyResult(ok=True, channel="noop", detail="send_chat_text not implemented")

    def bind_task_id(self, ref: FeishuTaskRef, task_id: str) -> FeishuTaskRef:
        ref.task_id = task_id
        return ref
