"""Optional multimodal QA — wraps Rules engine; extends when vision API key present.

Without a usable vision call, behaves as rules-only (no silent fake multimodal scores).
With OPENAI_API_KEY and EVAW_QA_MULTIMODAL=1 (or auto when mode=live + key),
attempts a lightweight vision note; on failure falls back to rules result unchanged.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from ..schema import DimensionStatus, QAOverall
from .base import QAEvaluateRequest, QAEvaluateResult, QAProvider
from .rules import RulesQAProvider, _uri_to_path


def multimodal_enabled() -> bool:
    flag = (os.environ.get("EVAW_QA_MULTIMODAL") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return bool(os.environ.get("OPENAI_API_KEY"))
    # auto: key present → eligible
    return bool(os.environ.get("OPENAI_API_KEY"))


def _file_data_url(path: Path) -> Optional[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > 4_000_000:
        return None  # skip huge
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


class MultimodalQAProvider(QAProvider):
    """Rules first; optional OpenAI vision enrichment."""

    name = "multimodal"
    engine = "multimodal"

    def __init__(self, rules: Optional[RulesQAProvider] = None):
        self.rules = rules or RulesQAProvider()

    def evaluate(self, req: QAEvaluateRequest) -> QAEvaluateResult:
        base = self.rules.evaluate(req)
        meta = dict(base.provider_meta)
        meta["multimodal_attempted"] = False
        meta["multimodal_applied"] = False
        meta["external_api"] = False

        if not multimodal_enabled():
            meta["multimodal_skip"] = "no_api_key_or_disabled"
            # Keep engine label honest: still rules underneath
            base.report.engine = "rules"
            meta["kind"] = "rules_fallback"
            return QAEvaluateResult(report=base.report, provider_meta=meta)

        asset = req.generation.assets[0]
        path = _uri_to_path(asset.uri)
        if path is None or not path.exists():
            meta["multimodal_skip"] = "no_local_image"
            base.report.engine = "rules"
            return QAEvaluateResult(report=base.report, provider_meta=meta)

        data_url = _file_data_url(path)
        if not data_url:
            meta["multimodal_skip"] = "image_unreadable_or_too_large"
            base.report.engine = "rules"
            return QAEvaluateResult(report=base.report, provider_meta=meta)

        meta["multimodal_attempted"] = True
        vision_note, err = self._call_vision(data_url, req)
        if err:
            meta["multimodal_error"] = err
            base.report.engine = "rules"
            return QAEvaluateResult(report=base.report, provider_meta=meta)

        meta["multimodal_applied"] = True
        meta["external_api"] = True
        meta["kind"] = "multimodal"
        base.report.engine = "multimodal"

        # Enrich notes only — do not silently invent Fail from free-text unless
        # the model returns a structured signal we trust. Conservative: append note.
        if vision_note:
            for dim, dr in base.report.dimensions.items():
                dr.notes = f"{dr.notes} | vision: {vision_note[:120]}"
            # Soft upgrade: if vision says FAIL_FIDELITY and rules was Pass, bump Risk
            upper = vision_note.upper()
            if "FAIL_FIDELITY" in upper and base.report.overall == QAOverall.PASS:
                fid = base.report.dimensions.get("product_fidelity")
                if fid and fid.status == DimensionStatus.PASS:
                    fid.status = DimensionStatus.RISK
                    fid.notes += " (vision suggested FAIL_FIDELITY → Risk pending Lead)"
                    base.report.overall = QAOverall.PASS_WITH_RISK
                    from ..schema import ReasonCode

                    base.report.reason_code = ReasonCode.FIDELITY_STRUCTURE
                    base.report.primary_dimension = "product_fidelity"
                    base.report.suggested_fixes.append(
                        "Vision flagged fidelity — Lead confirm or regenerate"
                    )

        return QAEvaluateResult(report=base.report, provider_meta=meta)

    def _call_vision(
        self, data_url: str, req: QAEvaluateRequest
    ) -> tuple[Optional[str], Optional[str]]:
        api_key = os.environ.get("OPENAI_API_KEY") or ""
        model = os.environ.get("EVAW_QA_VISION_MODEL") or "gpt-4o-mini"
        url = os.environ.get(
            "EVAW_QA_VISION_URL"
        ) or "https://api.openai.com/v1/chat/completions"

        prompt = (
            "You are an ecommerce visual QA assistant. Reply in ONE short line. "
            "If product structure looks wrong, include token FAIL_FIDELITY. "
            "Otherwise summarize brand/text/layout/mobile risks briefly. "
            f"SKU={req.task.sku_id} platform={req.task.platform.value}."
        )
        body = {
            "model": model,
            "max_tokens": 120,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            return None, f"HTTP_{e.code}:{detail}"
        except Exception as e:  # noqa: BLE001
            return None, f"{type(e).__name__}:{e}"

        try:
            content = payload["choices"][0]["message"]["content"]
            return str(content).strip(), None
        except (KeyError, IndexError, TypeError):
            return None, "malformed_vision_response"
