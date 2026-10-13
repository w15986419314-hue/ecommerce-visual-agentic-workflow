"""Volcengine Ark 豆包 Seedream image generation — preferred CN Live Gen.

Sync HTTP (stdlib urllib):
  POST https://ark.cn-beijing.volces.com/api/v3/images/generations
  Authorization: Bearer $ARK_API_KEY

Env:
  ARK_API_KEY              required (火山方舟 API Key；也可写 DOUBAO_API_KEY)
  DOUBAO_API_KEY           alias for ARK_API_KEY
  EVAW_DOUBAO_MODEL        default doubao-seedream-4-0-250828
  EVAW_DOUBAO_SIZE         default 2K  (or e.g. 2048x2048)
  EVAW_DOUBAO_BASE_URL     default https://ark.cn-beijing.volces.com/api/v3
  EVAW_DOUBAO_WATERMARK    default false
  EVAW_DOUBAO_TIMEOUT_SEC  default 120
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from ..schema import GeneratedAsset, new_id
from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult
from .prompt import build_ecommerce_prompt

DEFAULT_BASE = os.environ.get(
    "EVAW_DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
).rstrip("/")
# Stable Seedream 4.0 Model ID from Ark docs; override via env for 5.0 etc.
DEFAULT_MODEL = os.environ.get("EVAW_DOUBAO_MODEL", "doubao-seedream-4-0-250828")
DEFAULT_SIZE = os.environ.get("EVAW_DOUBAO_SIZE", "2K")
DEFAULT_TIMEOUT = float(os.environ.get("EVAW_DOUBAO_TIMEOUT_SEC", "120"))


def _resolve_api_key(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    return (
        os.environ.get("ARK_API_KEY")
        or os.environ.get("DOUBAO_API_KEY")
        or os.environ.get("VOLCENGINE_API_KEY")
        or ""
    ).strip()


def _watermark_flag() -> bool:
    v = (os.environ.get("EVAW_DOUBAO_WATERMARK") or "false").strip().lower()
    return v in ("1", "true", "yes", "on")


def _build_prompt(req: ProviderGenerateRequest) -> str:
    return build_ecommerce_prompt(req, lang="zh", max_chars=480)


class DoubaoArkProvider(GenerationProvider):
    """豆包 Seedream 文生图（火山方舟 Ark，国内可达）。"""

    name = "doubao_ark"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        size: str = DEFAULT_SIZE,
        base_url: str = DEFAULT_BASE,
        timeout_sec: float = DEFAULT_TIMEOUT,
        watermark: Optional[bool] = None,
    ):
        self.api_key = _resolve_api_key(api_key)
        self.model = model
        self.size = size
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.watermark = _watermark_flag() if watermark is None else watermark

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        if not self.api_key:
            return ProviderGenerateResult(
                error_code="DOUBAO_NO_KEY",
                error_message=(
                    "ARK_API_KEY (or DOUBAO_API_KEY) not set. "
                    "Create a key in 火山方舟控制台 → API Key，写入 .env.local。"
                ),
            )

        run_dir = req.artifacts_dir / req.task.task_id / req.result_id
        run_dir.mkdir(parents=True, exist_ok=True)
        prompt = _build_prompt(req)
        assets: list[GeneratedAsset] = []

        for i in range(req.candidate_count):
            idx = i + 1
            variation = f"{prompt} 变体 {idx}/{req.candidate_count}。"
            try:
                data = self._post_images(variation)
                path = run_dir / f"cand_{idx}.png"
                self._save_image_payload(data, path)
            except Exception as e:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="DOUBAO_HTTP_ERROR",
                    error_message=str(e),
                    provider_meta={
                        "kind": self.name,
                        "partial": len(assets),
                        "model": self.model,
                        "external_api": True,
                    },
                )

            uri = path.resolve().as_uri()
            assets.append(
                GeneratedAsset(
                    asset_id=new_id("asset"),
                    task_id=req.task.task_id,
                    generation_result_id=req.result_id,
                    asset_type=req.task.asset_type.value,
                    uri=uri,
                    platform_target=req.task.platform.value,
                    mode=req.mode,
                    knowledge_snapshot_id=req.snapshot_id,
                    strategy_version=req.strategy_version,
                    version=f"v{idx}",
                )
            )

        manifest = {
            "provider": self.name,
            "model": self.model,
            "size": self.size,
            "task_id": req.task.task_id,
            "generation_result_id": req.result_id,
            "knowledge_snapshot_id": req.snapshot_id,
            "strategy_version": req.strategy_version,
            "candidate_count": len(assets),
            "prompt": prompt,
            "assets": [
                {"asset_id": a.asset_id, "uri": a.uri, "version": a.version}
                for a in assets
            ],
        }
        (run_dir / "candidates.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return ProviderGenerateResult(
            assets=assets,
            provider_meta={
                "kind": self.name,
                "wrote_files": True,
                "artifacts_dir": str(run_dir),
                "model": self.model,
                "external_api": True,
                "domestic": True,
            },
        )

    def _post_images(self, prompt: str) -> dict:
        url = f"{self.base_url}/images/generations"
        body = {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "response_format": "url",
            "watermark": self.watermark,
            "stream": False,
            "sequential_image_generation": "disabled",
        }
        raw = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "evaw-live-gen/0.2-doubao",
        }
        request = urllib.request.Request(url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {err_body}") from e

    @staticmethod
    def _save_image_payload(data: dict, path: Path) -> None:
        items = data.get("data") or []
        if not items:
            # Some error shapes put message at top level
            raise RuntimeError(
                f"No data in Doubao response keys={list(data.keys())} "
                f"error={data.get('error')}"
            )
        item = items[0]
        if "b64_json" in item and item["b64_json"]:
            path.write_bytes(base64.b64decode(item["b64_json"]))
            return
        if "url" in item and item["url"]:
            request = urllib.request.Request(
                item["url"],
                headers={"User-Agent": "evaw-live-gen/0.2-doubao"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=60) as resp:
                path.write_bytes(resp.read())
            return
        raise RuntimeError(f"Neither b64_json nor url in item keys={list(item.keys())}")
