"""Poll / sync Feishu bitable records → EVAW VisualTask.

Primary MVP path when no public webhook URL is available:
  python3 -m evaw.cli feishu-bitable-sync
  python3 -m evaw.cli feishu-bitable-sync --poll --interval 60

Dedupes by Feishu record_id (state file under artifacts/).
Uses FEISHU_APP_ID / FEISHU_APP_SECRET + FEISHU_BITABLE_APP_TOKEN /
FEISHU_BITABLE_TABLE_ID (defaults to the live EVAW 提需 base).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .field_map import payload_to_brief


FEISHU_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)

# Live ops intake base (personal 提需表 with form shrcn3nkmUrA2XYufTexOC3uO5b)
DEFAULT_APP_TOKEN = "B8kubs46saK9ZnsII2IcLNbXntg"
DEFAULT_TABLE_ID = "tblessb0FYqQUYg4"
DEFAULT_FORM_URL = (
    "https://scnjh6x3pkck.feishu.cn/share/base/form/shrcn3nkmUrA2XYufTexOC3uO5b"
)
DEFAULT_BASE_URL = (
    f"https://scnjh6x3pkck.feishu.cn/base/{DEFAULT_APP_TOKEN}"
)


def _load_env() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    for name in (".env.local", ".env"):
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


def resolve_bitable_ids() -> tuple[str, str]:
    """Return (app_token, table_id) from env or live defaults."""
    app = (
        os.environ.get("FEISHU_BITABLE_APP_TOKEN") or DEFAULT_APP_TOKEN
    ).strip()
    table = (
        os.environ.get("FEISHU_BITABLE_TABLE_ID") or DEFAULT_TABLE_ID
    ).strip()
    return app, table


def _tenant_token() -> str:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not secret:
        raise RuntimeError(
            "FEISHU_APP_ID / FEISHU_APP_SECRET required for bitable sync"
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


def _api_get(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"code": e.code, "msg": raw}


def list_tables(app_token: str, token: str) -> list[dict[str, Any]]:
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
        f"{urllib.parse.quote(app_token)}/tables?page_size=50"
    )
    data = _api_get(url, token)
    if data.get("code") != 0:
        raise RuntimeError(f"list tables failed: {data}")
    return list(((data.get("data") or {}).get("items")) or [])


def list_records(
    app_token: str,
    table_id: str,
    token: str,
    *,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """List all records (paginated)."""
    items: list[dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        q = {"page_size": str(page_size)}
        if page_token:
            q["page_token"] = page_token
        qs = urllib.parse.urlencode(q)
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
            f"{urllib.parse.quote(app_token)}/tables/"
            f"{urllib.parse.quote(table_id)}/records?{qs}"
        )
        data = _api_get(url, token)
        if data.get("code") != 0:
            raise RuntimeError(f"list records failed: {data}")
        batch = ((data.get("data") or {}).get("items")) or []
        items.extend(batch)
        if not (data.get("data") or {}).get("has_more"):
            break
        page_token = (data.get("data") or {}).get("page_token")
        if not page_token:
            break
    return items


def _record_has_intake_fields(fields: dict[str, Any]) -> bool:
    """Skip empty / placeholder rows (e.g. only 父记录)."""
    if not isinstance(fields, dict):
        return False
    skip = {"父记录", "文本", "提需日期"}
    for k, v in fields.items():
        if k in skip:
            continue
        if v in (None, "", [], {}):
            continue
        return True
    return False


def record_to_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Wrap a bitable list-records item as ingest_payload-compatible JSON."""
    rid = record.get("record_id") or ""
    fields = record.get("fields") or {}
    return {
        "source": "feishu_bitable_sync",
        "record_id": rid,
        "record": {
            "record_id": rid,
            "fields": fields,
        },
        "fields": fields,
    }


def state_path(artifacts_dir: str) -> Path:
    return Path(artifacts_dir) / "feishu_bitable_sync_state.json"


def load_state(artifacts_dir: str) -> dict[str, Any]:
    p = state_path(artifacts_dir)
    if not p.is_file():
        return {"synced_record_ids": {}, "last_sync_at": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"synced_record_ids": {}, "last_sync_at": None}
    if "synced_record_ids" not in data:
        data["synced_record_ids"] = {}
    return data


def save_state(artifacts_dir: str, state: dict[str, Any]) -> Path:
    p = state_path(artifacts_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def sync_once(
    *,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
    limit: Optional[int] = None,
    dry_run: bool = False,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    include_synced: bool = False,
) -> dict[str, Any]:
    """Fetch bitable records and create EVAW tasks for new ones.

    force_mock=True (default): no live IM. Set notify=True + force_mock=False
    for live Feishu chat notify after intake.
    """
    from .webhook import ingest_payload

    _load_env()
    app = (app_token or "").strip() or resolve_bitable_ids()[0]
    table = (table_id or "").strip() or resolve_bitable_ids()[1]

    token = _tenant_token()
    records = list_records(app, table, token)
    state = load_state(artifacts_dir)
    synced: dict[str, Any] = state.setdefault("synced_record_ids", {})

    candidates: list[dict[str, Any]] = []
    skipped_empty = 0
    skipped_synced = 0
    for rec in records:
        rid = str(rec.get("record_id") or "")
        fields = rec.get("fields") or {}
        if not _record_has_intake_fields(fields):
            skipped_empty += 1
            continue
        if rid and rid in synced and not include_synced:
            skipped_synced += 1
            continue
        candidates.append(rec)

    # Newest first when Feishu returns oldest-first — keep API order but allow limit
    if limit is not None and limit >= 0:
        candidates = candidates[-limit:] if limit else []

    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for rec in candidates:
        rid = str(rec.get("record_id") or "")
        payload = record_to_payload(rec)
        if dry_run:
            try:
                brief = payload_to_brief(payload)
                created.append(
                    {
                        "ok": True,
                        "dry_run": True,
                        "record_id": rid,
                        "brand_id": brief.brand_id,
                        "sku_id": brief.sku_id,
                        "platform": brief.platform,
                        "asset_type": brief.asset_type,
                    }
                )
            except ValueError as e:
                errors.append({"record_id": rid, "error": str(e)})
            continue

        try:
            result = ingest_payload(
                payload,
                artifacts_dir=artifacts_dir,
                force_mock=force_mock,
                notify=notify,
            )
        except ValueError as e:
            errors.append({"record_id": rid, "error": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            errors.append({"record_id": rid, "error": str(e)})
            continue

        entry = {
            "ok": True,
            "record_id": rid,
            "task_id": result.get("task_id"),
            "intake_id": result.get("intake_id"),
            "status": result.get("status"),
            "brand_id": result.get("brand_id"),
            "sku_id": result.get("sku_id"),
            "platform": result.get("platform"),
            "asset_type": result.get("asset_type"),
        }
        created.append(entry)
        if rid:
            synced[rid] = {
                "task_id": result.get("task_id"),
                "intake_id": result.get("intake_id"),
                "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            tid = result.get("task_id")
            if tid:
                try:
                    from .kanban_sync import push_task_status

                    kr = push_task_status(
                        str(tid),
                        artifacts_dir=artifacts_dir,
                        app_token=app,
                        table_id=table,
                        record_id=rid,
                    )
                    synced[rid]["kanban"] = (kr.get("fields") or {}).get("看板状态")
                    synced[rid]["kanban_ok"] = bool(kr.get("ok"))
                    if kr.get("error"):
                        synced[rid]["kanban_error"] = kr.get("error")
                except Exception as ke:  # noqa: BLE001
                    synced[rid]["kanban_ok"] = False
                    synced[rid]["kanban_error"] = str(ke)

    from datetime import datetime, timezone

    state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    state["app_token"] = app
    state["table_id"] = table
    state["form_url"] = os.environ.get("FEISHU_INTAKE_FORM_URL") or DEFAULT_FORM_URL
    if not dry_run:
        save_state(artifacts_dir, state)

    return {
        "ok": len(errors) == 0,
        "kind": "bitable_sync",
        "app_token": app,
        "table_id": table,
        "form_url": state["form_url"],
        "base_url": DEFAULT_BASE_URL if app == DEFAULT_APP_TOKEN else None,
        "records_total": len(records),
        "skipped_empty": skipped_empty,
        "skipped_synced": skipped_synced,
        "candidates": len(candidates),
        "created": created,
        "errors": errors,
        "dry_run": dry_run,
        "notify": notify,
        "force_mock": force_mock,
        "state_path": str(state_path(artifacts_dir)),
    }


def poll_loop(
    *,
    interval_sec: float = 60.0,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
    app_token: Optional[str] = None,
    table_id: Optional[str] = None,
    max_iterations: Optional[int] = None,
) -> None:
    """Blocking poll loop. Ctrl+C to stop."""
    n = 0
    print(
        f"EVAW bitable poll every {interval_sec}s "
        f"(mock={force_mock} notify={notify})"
    )
    while True:
        n += 1
        try:
            report = sync_once(
                artifacts_dir=artifacts_dir,
                force_mock=force_mock,
                notify=notify,
                app_token=app_token,
                table_id=table_id,
            )
            created_n = len(report.get("created") or [])
            err_n = len(report.get("errors") or [])
            print(
                f"[{n}] total={report.get('records_total')} "
                f"new={created_n} errors={err_n} "
                f"skipped_synced={report.get('skipped_synced')} "
                f"skipped_empty={report.get('skipped_empty')}"
            )
            for c in report.get("created") or []:
                print(
                    f"  + task={c.get('task_id')} "
                    f"sku={c.get('sku_id')} record={c.get('record_id')}"
                )
            for e in report.get("errors") or []:
                print(f"  ! record={e.get('record_id')} err={e.get('error')}")
        except Exception as e:  # noqa: BLE001
            print(f"[{n}] sync error: {e}")
        if max_iterations is not None and n >= max_iterations:
            break
        time.sleep(max(5.0, float(interval_sec)))
