"""Push EVAW task status → Feishu bitable Kanban columns (ops board).

Uses the same intake base as feishu-bitable-sync. Maps record_id ↔ task_id
via artifacts/feishu_bitable_sync_state.json (and optional reverse lookup).

  python3 -m evaw.cli feishu-kanban-sync --ensure-fields
  python3 -m evaw.cli feishu-kanban-sync --all
  python3 -m evaw.cli feishu-kanban-sync --task task_xxx
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .bitable_sync import (
    DEFAULT_APP_TOKEN,
    DEFAULT_BASE_URL,
    DEFAULT_TABLE_ID,
    _load_env,
    load_state,
    resolve_bitable_ids,
    save_state,
)
from .kanban_map import (
    FIELD_KANBAN,
    FIELD_QA,
    FIELD_RAW_STATUS,
    FIELD_TASK_ID,
    FIELD_UPDATED,
    KANBAN_COLUMNS,
    kanban_label,
    mapping_as_dict,
    qa_label,
)



BLOCKER_HINT = (
    "Feishu API 91403 Forbidden：应用能读表，但还不能写字段/记录。"
    "请 Cici：① 打开 Base → 右上角「…」→ 添加应用为「可编辑」协作者；"
    "② 开放平台确认 bitable 读写 scope；"
    "③ 在「数据表」手动加列：看板状态(单选，选项见 docs)、EVAW任务ID、EVAW状态、QA结果、状态更新时间；"
    "④ 再跑 python3 -m evaw.cli feishu-kanban-sync --all"
)

FEISHU_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)


def _tenant_token() -> str:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not secret:
        raise RuntimeError(
            "FEISHU_APP_ID / FEISHU_APP_SECRET required for kanban sync"
        )
    body = json.dumps({"app_id": app_id, "app_secret": secret}).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data}")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Feishu token missing: {data}")
    return str(token)


def _api(
    method: str,
    url: str,
    token: str,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"code": e.code, "msg": raw}


def list_fields(app_token: str, table_id: str, token: str) -> list[dict[str, Any]]:
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
        f"{urllib.parse.quote(app_token)}/tables/"
        f"{urllib.parse.quote(table_id)}/fields?page_size=100"
    )
    data = _api("GET", url, token)
    if data.get("code") != 0:
        raise RuntimeError(f"list fields failed: {data}")
    return list(((data.get("data") or {}).get("items")) or [])


def _field_by_name(fields: list[dict[str, Any]], name: str) -> Optional[dict[str, Any]]:
    for f in fields:
        if f.get("field_name") == name:
            return f
    return None


def ensure_kanban_fields(
    *,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create Kanban progress columns on the intake table if missing."""
    _load_env()
    app = (app_token or "").strip() or resolve_bitable_ids()[0]
    table = (table_id or "").strip() or resolve_bitable_ids()[1]
    token = _tenant_token()
    existing = list_fields(app, table, token)
    names = {f.get("field_name") for f in existing}

    # Feishu single-select options: need color 0..N
    select_options = [
        {"name": col, "color": i % 54} for i, col in enumerate(KANBAN_COLUMNS)
    ]
    wanted: list[dict[str, Any]] = [
        {
            "field_name": FIELD_KANBAN,
            "type": 3,
            "ui_type": "SingleSelect",
            "property": {"options": select_options},
        },
        {"field_name": FIELD_TASK_ID, "type": 1, "ui_type": "Text"},
        {"field_name": FIELD_RAW_STATUS, "type": 1, "ui_type": "Text"},
        {"field_name": FIELD_QA, "type": 1, "ui_type": "Text"},
        {"field_name": FIELD_UPDATED, "type": 1, "ui_type": "Text"},
    ]

    created: list[str] = []
    skipped: list[str] = []
    errors: list[dict[str, Any]] = []

    for spec in wanted:
        name = spec["field_name"]
        if name in names:
            skipped.append(name)
            continue
        if dry_run:
            created.append(name)
            continue
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
            f"{urllib.parse.quote(app)}/tables/"
            f"{urllib.parse.quote(table)}/fields"
        )
        body = {
            "field_name": name,
            "type": spec["type"],
        }
        if "property" in spec:
            body["property"] = spec["property"]
        data = _api("POST", url, token, body)
        if data.get("code") != 0:
            errors.append({"field": name, "error": data})
        else:
            created.append(name)
            names.add(name)

    out = {
        "ok": len(errors) == 0,
        "kind": "kanban_ensure_fields",
        "app_token": app,
        "table_id": table,
        "base_url": DEFAULT_BASE_URL if app == DEFAULT_APP_TOKEN else None,
        "created": created,
        "skipped_existing": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "mapping": mapping_as_dict(),
    }
    if errors:
        out["blocker"] = BLOCKER_HINT
    return out


def _find_task_snapshot(
    task_id: str, artifacts_dir: str
) -> Optional[dict[str, Any]]:
    """Load task dict from hitl_pending or intakes."""
    root = Path(artifacts_dir)
    for sub in ("hitl_pending", "intakes"):
        path = root / sub / f"{task_id}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        task = payload.get("task") if isinstance(payload, dict) else None
        if isinstance(task, dict) and task.get("task_id"):
            return task
        if isinstance(payload, dict) and payload.get("task_id"):
            return payload
    return None


def _record_id_for_task(
    task_id: str, artifacts_dir: str
) -> Optional[str]:
    state = load_state(artifacts_dir)
    synced = state.get("synced_record_ids") or {}
    for rid, meta in synced.items():
        if isinstance(meta, dict) and meta.get("task_id") == task_id:
            return str(rid)
        if meta == task_id:
            return str(rid)
    return None


def _task_id_for_record(record_id: str, artifacts_dir: str) -> Optional[str]:
    state = load_state(artifacts_dir)
    synced = state.get("synced_record_ids") or {}
    meta = synced.get(record_id)
    if isinstance(meta, dict):
        tid = meta.get("task_id")
        return str(tid) if tid else None
    if isinstance(meta, str):
        return meta
    return None


def _qa_from_task(task: dict[str, Any]) -> str:
    qa = task.get("qa") or task.get("qa_report")
    if isinstance(qa, dict):
        overall = qa.get("overall")
        if overall:
            return qa_label(str(overall))
    return qa_label(task.get("qa_overall"))


def build_status_fields(task: dict[str, Any]) -> dict[str, Any]:
    status = str(task.get("status") or "")
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return {
        FIELD_KANBAN: kanban_label(status),
        FIELD_TASK_ID: str(task.get("task_id") or ""),
        FIELD_RAW_STATUS: status,
        FIELD_QA: _qa_from_task(task),
        FIELD_UPDATED: now,
    }


def update_record_fields(
    app_token: str,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
        f"{urllib.parse.quote(app_token)}/tables/"
        f"{urllib.parse.quote(table_id)}/records/"
        f"{urllib.parse.quote(record_id)}"
    )
    return _api("PUT", url, token, {"fields": fields})


def push_task_status(
    task_id: str,
    *,
    artifacts_dir: str = "artifacts",
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    dry_run: bool = False,
    record_id: Optional[str] = None,
    ensure_fields: bool = False,
) -> dict[str, Any]:
    """Push one task's status to its linked bitable row."""
    _load_env()
    app = (app_token or "").strip() or resolve_bitable_ids()[0]
    table = (table_id or "").strip() or resolve_bitable_ids()[1]

    ensure_report = None
    if ensure_fields and not dry_run:
        ensure_report = ensure_kanban_fields(app_token=app, table_id=table)

    task = _find_task_snapshot(task_id, artifacts_dir)
    if not task:
        return {
            "ok": False,
            "kind": "kanban_push",
            "task_id": task_id,
            "error": f"no snapshot in hitl_pending/intakes for {task_id}",
        }

    rid = (record_id or "").strip() or _record_id_for_task(task_id, artifacts_dir)
    if not rid:
        return {
            "ok": False,
            "kind": "kanban_push",
            "task_id": task_id,
            "status": task.get("status"),
            "kanban": kanban_label(str(task.get("status") or "")),
            "error": (
                "no Feishu record_id linked in "
                "artifacts/feishu_bitable_sync_state.json — "
                "only form-synced tasks map to board rows"
            ),
        }

    fields = build_status_fields(task)
    if dry_run:
        return {
            "ok": True,
            "kind": "kanban_push",
            "dry_run": True,
            "task_id": task_id,
            "record_id": rid,
            "fields": fields,
            "app_token": app,
            "table_id": table,
            "ensure_fields": ensure_report,
        }

    token = _tenant_token()
    data = update_record_fields(app, table, rid, fields, token)
    ok = data.get("code") == 0
    # Remember last kanban push on sync state
    if ok:
        state = load_state(artifacts_dir)
        synced = state.setdefault("synced_record_ids", {})
        entry = synced.get(rid) or {}
        if not isinstance(entry, dict):
            entry = {"task_id": task_id}
        entry["task_id"] = task_id
        entry["kanban"] = fields.get(FIELD_KANBAN)
        entry["evaw_status"] = fields.get(FIELD_RAW_STATUS)
        entry["kanban_pushed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        synced[rid] = entry
        state["last_kanban_push_at"] = datetime.now(timezone.utc).isoformat()
        save_state(artifacts_dir, state)

    out = {
        "ok": ok,
        "kind": "kanban_push",
        "task_id": task_id,
        "record_id": rid,
        "fields": fields,
        "app_token": app,
        "table_id": table,
        "feishu": data if not ok else {"code": 0, "msg": "success"},
        "ensure_fields": ensure_report,
        "base_url": DEFAULT_BASE_URL if app == DEFAULT_APP_TOKEN else None,
    }
    if not ok and isinstance(data, dict) and data.get("code") == 91403:
        out["blocker"] = BLOCKER_HINT
    return out


def push_all_synced(
    *,
    artifacts_dir: str = "artifacts",
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    dry_run: bool = False,
    ensure_fields: bool = False,
) -> dict[str, Any]:
    """Push status for every record↔task pair in sync state."""
    _load_env()
    app = (app_token or "").strip() or resolve_bitable_ids()[0]
    table = (table_id or "").strip() or resolve_bitable_ids()[1]

    ensure_report = None
    if ensure_fields:
        ensure_report = ensure_kanban_fields(
            app_token=app, table_id=table, dry_run=dry_run
        )

    state = load_state(artifacts_dir)
    synced = state.get("synced_record_ids") or {}
    results: list[dict[str, Any]] = []
    for rid, meta in synced.items():
        tid = None
        if isinstance(meta, dict):
            tid = meta.get("task_id")
        elif isinstance(meta, str):
            tid = meta
        if not tid:
            results.append(
                {"ok": False, "record_id": rid, "error": "missing task_id"}
            )
            continue
        results.append(
            push_task_status(
                str(tid),
                artifacts_dir=artifacts_dir,
                app_token=app,
                table_id=table,
                dry_run=dry_run,
                record_id=str(rid),
                ensure_fields=False,
            )
        )

    ok = all(r.get("ok") for r in results) if results else True
    return {
        "ok": ok and (ensure_report is None or ensure_report.get("ok")),
        "kind": "kanban_push_all",
        "app_token": app,
        "table_id": table,
        "base_url": DEFAULT_BASE_URL if app == DEFAULT_APP_TOKEN else None,
        "count": len(results),
        "results": results,
        "ensure_fields": ensure_report,
        "dry_run": dry_run,
        "mapping": mapping_as_dict(),
    }


def try_push_after_status_change(
    task_id: str,
    *,
    artifacts_dir: str = "artifacts",
) -> Optional[dict[str, Any]]:
    """Best-effort hook after HITL / deliver. Never raises."""
    try:
        if not _record_id_for_task(task_id, artifacts_dir):
            return None
        return push_task_status(task_id, artifacts_dir=artifacts_dir)
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "kind": "kanban_push",
            "task_id": task_id,
            "error": str(e),
        }
