"""Feishu/Lark integration — resolve mock vs live API."""

from __future__ import annotations

import os
from typing import Optional

from .api import FeishuApiAdapter
from .base import (
    ApprovalLinkResult,
    FeishuAdapter,
    FeishuBriefPayload,
    FeishuTaskRef,
    NotifyResult,
)
from .mock import MockFeishuAdapter, brief_to_ops
from .field_map import INTAKE_FIELDS, field_map_as_dict, payload_to_brief
from .webhook import ingest_payload, serve_webhook
from .bitable_setup import setup_bitable, write_field_map_doc
from .bitable_sync import sync_once, poll_loop, DEFAULT_FORM_URL, DEFAULT_APP_TOKEN
from .kanban_map import STATUS_TO_KANBAN, kanban_label, mapping_as_dict
from .kanban_sync import ensure_kanban_fields, push_task_status, push_all_synced


def has_feishu_credentials() -> bool:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    return bool(app_id and secret)


def resolve_feishu_adapter(
    *,
    force_mock: Optional[bool] = None,
    mock_root: str = "artifacts/feishu_mock",
    console_base_url: Optional[str] = None,
) -> FeishuAdapter:
    """
    Priority:
      1. force_mock=True / EVAW_FEISHU_FORCE_MOCK=1 → mock
      2. FEISHU_APP_ID + FEISHU_APP_SECRET → FeishuApiAdapter
      3. else → mock
    """
    if force_mock is True:
        return MockFeishuAdapter(
            mock_root,
            console_base_url=console_base_url
            or os.environ.get("FEISHU_APPROVAL_BASE_URL")
            or "http://localhost:8765/review",
        )
    if force_mock is False and has_feishu_credentials():
        return FeishuApiAdapter(mock_fallback_root=mock_root)

    env_force = (os.environ.get("EVAW_FEISHU_FORCE_MOCK") or "").strip().lower()
    if env_force in ("1", "true", "yes"):
        return MockFeishuAdapter(
            mock_root,
            console_base_url=console_base_url
            or os.environ.get("FEISHU_APPROVAL_BASE_URL")
            or "http://localhost:8765/review",
        )

    if has_feishu_credentials():
        return FeishuApiAdapter(mock_fallback_root=mock_root)

    return MockFeishuAdapter(
        mock_root,
        console_base_url=console_base_url
        or os.environ.get("FEISHU_APPROVAL_BASE_URL")
        or "http://localhost:8765/review",
    )


def describe_feishu_adapter(adapter: FeishuAdapter) -> str:
    creds = has_feishu_credentials()
    chat = bool((os.environ.get("FEISHU_CHAT_ID") or "").strip())
    return (
        f"adapter={adapter.name} credentials={'yes' if creds else 'no'} "
        f"chat_id={'set' if chat else 'unset'} "
        f"connected={'live_api' if adapter.name == 'feishu_api' else 'mock_only'}"
    )


__all__ = [
    "FeishuAdapter",
    "FeishuBriefPayload",
    "FeishuTaskRef",
    "NotifyResult",
    "ApprovalLinkResult",
    "MockFeishuAdapter",
    "FeishuApiAdapter",
    "brief_to_ops",
    "has_feishu_credentials",
    "resolve_feishu_adapter",
    "describe_feishu_adapter",
    "INTAKE_FIELDS",
    "field_map_as_dict",
    "payload_to_brief",
    "ingest_payload",
    "serve_webhook",
    "setup_bitable",
    "write_field_map_doc",
    "sync_once",
    "poll_loop",
    "DEFAULT_FORM_URL",
    "DEFAULT_APP_TOKEN",
    "STATUS_TO_KANBAN",
    "kanban_label",
    "mapping_as_dict",
    "ensure_kanban_fields",
    "push_task_status",
    "push_all_synced",
]
