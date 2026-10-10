"""Create or document Feishu 多维表格「提需」表 + field map via Open API.

If app has bitable:app scopes, creates a Base named EVAW 提需 and adds columns
aligned with field_map.INTAKE_FIELDS. Form view must be enabled manually in UI
(Open API cannot fully create form-view share links in all tenants).

Always writes docs/feishu_intake_field_map.json + artifacts report (local).
Never sends IM messages.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from .field_map import bitable_field_specs, field_map_as_dict


FEISHU_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
BITABLE_CREATE_APP = "https://open.feishu.cn/open-apis/bitable/v1/apps"
BITABLE_LIST_FIELDS = (
    "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
)
BITABLE_CREATE_FIELD = (
    "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
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


def _token() -> str:
    app_id = (os.environ.get("FEISHU_APP_ID") or "").strip()
    secret = (os.environ.get("FEISHU_APP_SECRET") or "").strip()
    if not app_id or not secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET missing")
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
        raise RuntimeError(f"token error: {data}")
    return data["tenant_access_token"]


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


def write_field_map_doc(repo_root: Path) -> Path:
    out = repo_root / "docs" / "feishu_intake_field_map.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(field_map_as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out


def setup_bitable(
    *,
    name: str = "EVAW 提需",
    folder_token: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Try live bitable create; always document field map. No IM send."""
    _load_env()
    root = repo_root or Path(__file__).resolve().parent.parent.parent
    map_path = write_field_map_doc(root)

    report: dict[str, Any] = {
        "ok": False,
        "field_map_path": str(map_path.relative_to(root)),
        "fields": bitable_field_specs(),
        "operator_fill_where": field_map_as_dict()["operator_fill_where"],
        "manual_steps": [
            "在飞书打开多维表格 → 对该数据表「生成表单」/ 新建「表单视图」",
            "表单分享链接发给运营；运营只在该链接填字段并提交",
            "在飞书开发者后台为应用开通 bitable 读记录 / 事件订阅（record.created）",
            "将事件回调 URL 指到公网可达的 POST /feishu/event（或用自动化把新行 webhook 到 stub）",
            "本地无公网时：导出一行 JSON，用 feishu-intake-from-json 建任务",
        ],
        "api": {},
    }

    if not (os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET")):
        report["api"] = {"skipped": True, "reason": "no FEISHU credentials"}
        report["ok"] = True  # docs still written
        report["mode"] = "document_only"
        _write_report(root, report)
        return report

    try:
        token = _token()
    except Exception as e:  # noqa: BLE001
        report["api"] = {"skipped": True, "reason": f"token_failed: {e}"}
        report["mode"] = "document_only"
        report["ok"] = True
        _write_report(root, report)
        return report

    body: dict[str, Any] = {"name": name, "time_zone": "Asia/Singapore"}
    if folder_token or os.environ.get("FEISHU_BITABLE_FOLDER_TOKEN"):
        body["folder_token"] = folder_token or os.environ.get(
            "FEISHU_BITABLE_FOLDER_TOKEN"
        )

    created = _api("POST", BITABLE_CREATE_APP, token, body)
    report["api"]["create_app"] = created

    if created.get("code") != 0:
        # Do not persist app auth URLs / tenant identifiers into docs
        violations = ((created.get("error") or {}).get("permission_violations"))
        report["api"]["create_app"] = {
            "code": created.get("code"),
            "msg": (
                "Access denied: need scopes bitable:app or base:app:create "
                "(grant in Feishu developer console)"
            ),
            "permission_violations": violations,
        }
        report["mode"] = "document_only_api_denied"
        report["ok"] = True
        report["api"]["hint"] = (
            "应用可能缺少「创建多维表格 / bitable:app」权限，"
            "或需在开发者后台开通并发布。字段映射已写入 docs；"
            "可手工新建多维表后按 fields[] 建列。"
        )
        _write_report(root, report)
        return report

    app = (created.get("data") or {}).get("app") or {}
    app_token = app.get("app_token")
    table_id = app.get("default_table_id")
    url = app.get("url")
    report["app_token"] = app_token
    report["table_id"] = table_id
    report["url"] = url

    # List existing fields then create missing EVAW columns
    existing_names: set[str] = set()
    if app_token and table_id:
        listed = _api(
            "GET",
            BITABLE_LIST_FIELDS.format(app_token=app_token, table_id=table_id)
            + "?page_size=100",
            token,
        )
        report["api"]["list_fields"] = {
            "code": listed.get("code"),
            "msg": listed.get("msg"),
        }
        items = ((listed.get("data") or {}).get("items")) or []
        for it in items:
            if isinstance(it, dict) and it.get("field_name"):
                existing_names.add(str(it["field_name"]))

        created_fields = []
        for spec in bitable_field_specs():
            fname = spec["field_name"]
            if fname in existing_names:
                created_fields.append({"field_name": fname, "skipped": True})
                continue
            payload = {"field_name": fname, "type": spec["type"]}
            if "property" in spec:
                payload["property"] = spec["property"]
            res = _api(
                "POST",
                BITABLE_CREATE_FIELD.format(app_token=app_token, table_id=table_id),
                token,
                payload,
            )
            created_fields.append(
                {
                    "field_name": fname,
                    "evaw_key": spec.get("evaw_key"),
                    "code": res.get("code"),
                    "msg": res.get("msg"),
                    "field_id": ((res.get("data") or {}).get("field") or {}).get(
                        "field_id"
                    ),
                }
            )
        report["api"]["create_fields"] = created_fields

    report["mode"] = "live_bitable_created"
    report["ok"] = True
    report["operator_fill_where"]["bitable_url"] = url
    report["operator_fill_where"][
        "preferred_after_setup"
    ] = "打开多维表格 → 生成表单视图 → 把表单链接发给运营；运营在表单链接填表"
    _write_report(root, report)

    # Persist tokens for env hint (not secrets) under docs
    hint = {
        "FEISHU_BITABLE_APP_TOKEN": app_token,
        "FEISHU_BITABLE_TABLE_ID": table_id,
        "FEISHU_BITABLE_URL": url,
        "note": "把表单视图分享链接给运营；webhook 用 feishu-intake-webhook / from-json",
    }
    hint_path = root / "docs" / "feishu_bitable_intake_env.example.json"
    hint_path.write_text(
        json.dumps(hint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report["env_example_path"] = str(hint_path.relative_to(root))
    _write_report(root, report)
    return report


def _write_report(root: Path, report: dict[str, Any]) -> Path:
    # Prefer docs (committed); also try artifacts if present
    path = root / "docs" / "feishu_bitable_setup_report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        art = root / "artifacts" / "feishu_bitable_setup_report.json"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass
    return path


