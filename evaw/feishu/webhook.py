"""Webhook stub: receive Feishu form / bitable / bot intake callbacks → VisualTask.

Usage:
  # HTTP stub (local / reverse-proxy)
  python3 -m evaw.cli feishu-intake-webhook --port 8787 --feishu-mock

  # One-shot from saved payload (CI / no public URL)
  python3 -m evaw.cli feishu-intake-from-json --file docs/samples/feishu_intake_webhook_example.json --feishu-mock

Endpoints (HTTP stub):
  GET  /health
  GET  /field-map
  POST /feishu/intake          — JSON body (form / bitable record / event envelope)
  POST /feishu/event          — Feishu event subscription (url_verification + record.created)

Does not require public Feishu event subscription for MVP: use from-json or CLI.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .field_map import field_map_as_dict, payload_to_brief


def ingest_payload(
    payload: dict[str, Any],
    *,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
) -> dict[str, Any]:
    """Parse webhook JSON → create VisualTask via scenario_feishu_intake.

    force_mock=True (default) avoids accidental live IM while developing.
    Set force_mock=False and notify=True only when intentionally live.
    """
    from ..cli import _load_env_local, _make_engine
    from ..workflow import scenario_feishu_intake
    from . import describe_feishu_adapter, resolve_feishu_adapter

    _load_env_local()

    # url_verification challenge — return as-is for Feishu event setup
    if payload.get("type") == "url_verification" or "challenge" in payload:
        return {
            "ok": True,
            "kind": "url_verification",
            "challenge": payload.get("challenge"),
        }

    brief = payload_to_brief(payload)
    mock_root = str(Path(artifacts_dir) / "feishu_mock")
    Path(mock_root).mkdir(parents=True, exist_ok=True)
    store_dir = str(Path(artifacts_dir) / "intakes")

    # Prefer mock unless explicitly live; even then notify can be suppressed
    use_mock = force_mock or not notify
    adapter = resolve_feishu_adapter(
        force_mock=True if use_mock else None,
        mock_root=mock_root,
    )
    engine = _make_engine("stub", artifacts_dir, qa_mode="stub")

    # If live adapter but notify=False, still create task; scenario sends chat —
    # wrap adapter notify/send to noop when notify=False and live.
    if not notify and adapter.name == "feishu_api":
        adapter = resolve_feishu_adapter(force_mock=True, mock_root=mock_root)

    task, log, ref = scenario_feishu_intake(
        engine, brief, feishu=adapter, store_dir=store_dir
    )
    return {
        "ok": True,
        "kind": "intake",
        "task_id": task.task_id,
        "intake_id": ref.intake_id,
        "status": task.status.value,
        "brand_id": brief.brand_id,
        "sku_id": brief.sku_id,
        "platform": brief.platform,
        "asset_type": brief.asset_type,
        "is_new_product": brief.is_new_product,
        "feishu_adapter": adapter.name,
        "feishu": describe_feishu_adapter(adapter),
        "intake_path": ref.mock_path,
        "log_tail": log.dump().splitlines()[-12:],
    }


def make_handler(
    *,
    artifacts_dir: str,
    force_mock: bool,
    notify: bool,
    verification_token: Optional[str] = None,
):
    class IntakeHandler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/health", "/"):
                self._send(
                    200,
                    {
                        "ok": True,
                        "service": "evaw-feishu-intake-webhook",
                        "endpoints": [
                            "GET /health",
                            "GET /field-map",
                            "POST /feishu/intake",
                            "POST /feishu/event",
                        ],
                    },
                )
                return
            if path == "/field-map":
                self._send(200, field_map_as_dict())
                return
            self._send(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as e:
                self._send(400, {"ok": False, "error": f"invalid_json: {e}"})
                return

            if path not in ("/feishu/intake", "/feishu/event", "/"):
                self._send(404, {"ok": False, "error": "not_found"})
                return

            # Optional token check (Feishu event subscription)
            token = verification_token or os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
            if token and payload.get("token") and payload.get("token") != token:
                self._send(403, {"ok": False, "error": "bad_verification_token"})
                return

            if payload.get("type") == "url_verification" or (
                path == "/feishu/event" and "challenge" in payload and "event" not in payload
            ):
                self._send(200, {"challenge": payload.get("challenge")})
                return

            try:
                result = ingest_payload(
                    payload,
                    artifacts_dir=artifacts_dir,
                    force_mock=force_mock,
                    notify=notify,
                )
            except ValueError as e:
                self._send(400, {"ok": False, "error": str(e)})
                return
            except Exception as e:  # noqa: BLE001
                self._send(500, {"ok": False, "error": str(e)})
                return

            if result.get("kind") == "url_verification":
                self._send(200, {"challenge": result.get("challenge")})
                return
            self._send(200, result)

        def log_message(self, fmt: str, *args: Any) -> None:
            # quieter stub logs
            sys_stderr = __import__("sys").stderr
            sys_stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    return IntakeHandler


def serve_webhook(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
) -> None:
    handler = make_handler(
        artifacts_dir=artifacts_dir,
        force_mock=force_mock,
        notify=notify,
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    print(
        f"EVAW Feishu intake webhook stub on http://{host}:{port} "
        f"(mock={force_mock} notify={notify})"
    )
    print("  GET  /health  /field-map")
    print("  POST /feishu/intake  /feishu/event")
    httpd.serve_forever()


