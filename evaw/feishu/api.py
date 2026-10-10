"""Live Feishu Open API adapter (when FEISHU_APP_ID / FEISHU_APP_SECRET set).

MVP behaviour:
- Obtain tenant_access_token
- notify_status → IM message if FEISHU_CHAT_ID set; else token-ok + noop send
- create_task_from_brief → same intake shape as mock + optional echo message
- approval_link → FEISHU_APPROVAL_BASE_URL or local console URL
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from ..schema import TaskStatus, VisualTask, new_id
from .base import (
    ApprovalLinkResult,
    FeishuAdapter,
    FeishuBriefPayload,
    FeishuTaskRef,
    NotifyResult,
    utcnow_iso,
)
from .mock import MockFeishuAdapter, brief_to_ops


FEISHU_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
FEISHU_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


class FeishuApiAdapter(FeishuAdapter):
    name = "feishu_api"

    def __init__(
        self,
        *,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        chat_id: Optional[str] = None,
        approval_base_url: Optional[str] = None,
        mock_fallback_root: str = "artifacts/feishu_mock",
    ):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self.chat_id = chat_id or os.environ.get("FEISHU_CHAT_ID", "")
        self.approval_base_url = (
            approval_base_url
            or os.environ.get("FEISHU_APPROVAL_BASE_URL")
            or "http://localhost:8765/review"
        ).rstrip("/")
        # Keep a local intake trail even when live (audit / debug)
        self._local = MockFeishuAdapter(
            mock_fallback_root, console_base_url=self.approval_base_url
        )
        self._token: Optional[str] = None

    def _get_tenant_token(self) -> str:
        if self._token:
            return self._token
        body = json.dumps(
            {"app_id": self.app_id, "app_secret": self.app_secret}
        ).encode("utf-8")
        req = urllib.request.Request(
            FEISHU_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Feishu token HTTP {e.code}: {raw}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Feishu token network error: {e}") from e

        if data.get("code") != 0:
            raise RuntimeError(f"Feishu token error: {data}")
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"Feishu token missing in response: {data}")
        self._token = token
        return token

    def _send_text(self, text: str) -> NotifyResult:
        if not self.chat_id:
            return NotifyResult(
                ok=True,
                channel="noop",
                message_id=None,
                detail=(
                    "tenant token ok; FEISHU_CHAT_ID unset — "
                    "skip IM send (set chat id to push)"
                ),
            )
        token = self._get_tenant_token()
        content = json.dumps({"text": text}, ensure_ascii=False)
        payload = json.dumps(
            {
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": content,
            }
        ).encode("utf-8")
        url = FEISHU_MESSAGE_URL + "?receive_id_type=chat_id"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            return NotifyResult(
                ok=False,
                channel="feishu_im",
                detail=f"HTTP {e.code}: {raw}",
            )
        except urllib.error.URLError as e:
            return NotifyResult(
                ok=False,
                channel="feishu_im",
                detail=f"network: {e}",
            )
        if data.get("code") != 0:
            return NotifyResult(
                ok=False,
                channel="feishu_im",
                detail=str(data),
            )
        msg_id = (data.get("data") or {}).get("message_id")
        return NotifyResult(
            ok=True,
            channel="feishu_im",
            message_id=msg_id,
            detail="sent",
        )

    def create_task_from_brief(self, brief: FeishuBriefPayload) -> FeishuTaskRef:
        # Always keep local intake; try live echo if chat configured
        ref = self._local.create_task_from_brief(brief)
        ref.adapter = self.name
        try:
            self._get_tenant_token()
            text = (
                f"[EVAW 提需已收] intake={ref.intake_id} "
                f"sku={brief.sku_id} platform={brief.platform}"
            )
            nr = self._send_text(text)
            if nr.message_id:
                ref.external_ref = nr.message_id
            elif nr.ok and nr.channel == "noop":
                ref.external_ref = f"token_ok_no_chat:{ref.intake_id}"
        except Exception as e:  # noqa: BLE001 — surface in external_ref
            ref.external_ref = f"api_error:{e}"
        return FeishuTaskRef(
            intake_id=ref.intake_id,
            task_id=None,
            ops=brief_to_ops(brief),
            adapter=self.name,
            external_ref=ref.external_ref,
            mock_path=ref.mock_path,
        )

    def notify_status(
        self,
        task: VisualTask,
        *,
        previous_status: Optional[TaskStatus] = None,
        note: str = "",
        extra: Optional[dict[str, Any]] = None,
    ) -> NotifyResult:
        # Dual-write: local audit trail + live IM when possible
        local = self._local.notify_status(
            task, previous_status=previous_status, note=note, extra=extra
        )
        prev = previous_status.value if previous_status else "-"
        text = (
            f"[EVAW] task={task.task_id} {prev}→{task.status.value} "
            f"sku={task.sku_id}"
        )
        if note:
            text += f" | {note}"
        if task.block_reason:
            text += f" | block={task.block_reason}"
        try:
            live = self._send_text(text)
        except Exception as e:  # noqa: BLE001
            return NotifyResult(
                ok=False,
                channel="feishu_im",
                message_id=local.message_id,
                detail=f"local ok; live failed: {e}",
                path=local.path,
            )
        if live.channel == "noop":
            return NotifyResult(
                ok=True,
                channel="noop",
                message_id=local.message_id,
                detail=f"{live.detail}; local={local.path}",
                path=local.path,
            )
        return NotifyResult(
            ok=live.ok,
            channel=live.channel,
            message_id=live.message_id or local.message_id,
            detail=live.detail,
            path=local.path,
        )

    def approval_link(self, task: VisualTask) -> ApprovalLinkResult:
        # Prefer configured base; still write console placeholder for 细打回
        local = self._local.approval_link(task)
        url = f"{self.approval_base_url}/{task.task_id}"
        return ApprovalLinkResult(
            url=url,
            task_id=task.task_id,
            console=True,
            detail=local.detail,
        )

    def send_chat_text(self, text: str) -> NotifyResult:
        """Live IM free-form text (also dual-writes to local mock trail)."""
        local = self._local.send_chat_text(text)
        try:
            live = self._send_text(text)
        except Exception as e:  # noqa: BLE001
            return NotifyResult(
                ok=False,
                channel="feishu_im",
                message_id=local.message_id,
                detail=f"local ok; live failed: {e}",
                path=local.path,
            )
        if live.channel == "noop":
            return NotifyResult(
                ok=True,
                channel="noop",
                message_id=local.message_id,
                detail=f"{live.detail}; local={local.path}",
                path=local.path,
            )
        return NotifyResult(
            ok=live.ok,
            channel=live.channel,
            message_id=live.message_id or local.message_id,
            detail=live.detail,
            path=local.path,
        )

