"""Mock Feishu adapter: local files simulate 提需 / 通知 / 审批链接."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from ..schema import (
    AssetType,
    OperationsInput,
    Platform,
    TaskStatus,
    VisualTask,
    new_id,
)
from .base import (
    ApprovalLinkResult,
    FeishuAdapter,
    FeishuBriefPayload,
    FeishuTaskRef,
    NotifyResult,
    utcnow_iso,
)


def _parse_platform(s: str) -> Platform:
    key = (s or "tmall").strip().lower()
    for p in Platform:
        if p.value == key:
            return p
    return Platform.TMALL


def _parse_asset(s: str) -> AssetType:
    key = (s or "hero").strip().lower()
    for a in AssetType:
        if a.value == key:
            return a
    return AssetType.HERO


def brief_to_ops(brief: FeishuBriefPayload) -> OperationsInput:
    deadline = datetime.fromisoformat(brief.deadline_iso.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    flags = list(brief.risk_flags or [])
    return OperationsInput(
        brand_id=brief.brand_id,
        sku_id=brief.sku_id,
        platform=_parse_platform(brief.platform),
        asset_type=_parse_asset(brief.asset_type),
        selling_points=list(brief.selling_points),
        size_spec=brief.size_spec or "800x800",
        deadline=deadline,
        is_new_product=bool(brief.is_new_product),
        risk_flags=flags,
        created_by=brief.requester_id or "ops_feishu",
    )


class MockFeishuAdapter(FeishuAdapter):
    """Writes intake / notifications under artifacts/feishu_mock/."""

    name = "mock"

    def __init__(
        self,
        root: str | Path = "artifacts/feishu_mock",
        *,
        console_base_url: str = "http://localhost:8765/review",
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "intakes").mkdir(exist_ok=True)
        (self.root / "notifications").mkdir(exist_ok=True)
        self.console_base_url = console_base_url.rstrip("/")
        self._messages_path = self.root / "messages.jsonl"

    def create_task_from_brief(self, brief: FeishuBriefPayload) -> FeishuTaskRef:
        intake_id = new_id("feishu_intake")
        ops = brief_to_ops(brief)
        path = self.root / "intakes" / f"{intake_id}.json"
        record = {
            "intake_id": intake_id,
            "adapter": self.name,
            "created_at": utcnow_iso(),
            "brief": {
                "brand_id": brief.brand_id,
                "sku_id": brief.sku_id,
                "platform": brief.platform,
                "asset_type": brief.asset_type,
                "selling_points": brief.selling_points,
                "size_spec": brief.size_spec,
                "deadline_iso": brief.deadline_iso,
                "is_new_product": brief.is_new_product,
                "risk_flags": brief.risk_flags,
                "requester_id": brief.requester_id,
                "source_message_id": brief.source_message_id,
                "chat_id": brief.chat_id,
            },
            "ops": {
                "brand_id": ops.brand_id,
                "sku_id": ops.sku_id,
                "platform": ops.platform.value,
                "asset_type": ops.asset_type.value,
                "selling_points": ops.selling_points,
                "size_spec": ops.size_spec,
                "deadline": ops.deadline.isoformat(),
                "is_new_product": ops.is_new_product,
                "risk_flags": ops.risk_flags,
                "created_by": ops.created_by,
            },
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return FeishuTaskRef(
            intake_id=intake_id,
            task_id=None,
            ops=ops,
            adapter=self.name,
            external_ref=brief.source_message_id,
            mock_path=str(path),
        )

    def notify_status(
        self,
        task: VisualTask,
        *,
        previous_status: Optional[TaskStatus] = None,
        note: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> NotifyResult:
        msg_id = f"mock_msg_{uuid4().hex[:10]}"
        payload = {
            "message_id": msg_id,
            "adapter": self.name,
            "at": utcnow_iso(),
            "task_id": task.task_id,
            "sku_id": task.sku_id,
            "status": task.status.value,
            "previous_status": previous_status.value if previous_status else None,
            "note": note,
            "auto_approved": task.auto_approved,
            "block_reason": task.block_reason,
            "extra": extra or {},
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._messages_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        per_task = self.root / "notifications" / f"{task.task_id}.jsonl"
        with per_task.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return NotifyResult(
            ok=True,
            channel="mock_file",
            message_id=msg_id,
            detail=f"appended to {self._messages_path}",
            path=str(self._messages_path),
        )

    def approval_link(self, task: VisualTask) -> ApprovalLinkResult:
        # 细打回在本地控制台占位；飞书只负责跳转
        url = f"{self.console_base_url}/{task.task_id}"
        placeholder = Path("artifacts/console_placeholder") / f"{task.task_id}.html"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_text(
            (
                f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>Review {task.task_id}</title></head><body>"
                f"<h1>Visual Lead Console (placeholder)</h1>"
                f"<p>task_id={task.task_id}</p>"
                f"<p>status={task.status.value}</p>"
                f"<p>sku={task.sku_id}</p>"
                f"<p>细打回请在此控制台操作；飞书内评论后置。</p>"
                f"<p>Approve / Reject with reason_code — stub UI.</p>"
                f"</body></html>"
            ),
            encoding="utf-8",
        )
        return ApprovalLinkResult(
            url=url,
            task_id=task.task_id,
            console=True,
            detail=f"console_placeholder={placeholder}",
        )

    def send_chat_text(self, text: str) -> NotifyResult:
        msg_id = f"mock_msg_{uuid4().hex[:10]}"
        payload = {
            "message_id": msg_id,
            "adapter": self.name,
            "at": utcnow_iso(),
            "kind": "chat_text",
            "text": text,
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._messages_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return NotifyResult(
            ok=True,
            channel="mock_file",
            message_id=msg_id,
            detail=f"chat_text appended to {self._messages_path}",
            path=str(self._messages_path),
        )

