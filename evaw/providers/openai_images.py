"""OpenAI Images API provider (stdlib urllib; optional openai package unused).

Activates when OPENAI_API_KEY is set. Uses gpt-image-1 / dall-e-3 style endpoint.
On HTTP failure returns error for caller to fall back or mark GenerationFailed.
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

DEFAULT_MODEL = os.environ.get("EVAW_OPENAI_IMAGE_MODEL", "gpt-image-1")
DEFAULT_SIZE = os.environ.get("EVAW_OPENAI_IMAGE_SIZE", "1024x1024")
API_URL = os.environ.get(
    "EVAW_OPENAI_IMAGES_URL", "https://api.openai.com/v1/images/generations"
)


def _build_prompt(req: ProviderGenerateRequest) -> str:
    strategy = req.task.strategy
    scene = strategy.scene_direction if strategy else ""
    composition = strategy.composition_notes if strategy else ""
    selling = (
        ", ".join(strategy.selling_point_priority) if strategy else ""
    )
    return (
        f"Ecommerce product hero image for SKU {req.task.sku_id} "
        f"(brand {req.task.brand_id}), platform {req.task.platform.value}. "
        f"Mode: {req.mode.value}. Scene: {scene}. "
        f"Composition: {composition}. Selling points: {selling}. "
        "Photorealistic, product-accurate structure, marketplace-safe framing, "
        "no fake logos or unreadable text."
    )


class OpenAIImagesProvider(GenerationProvider):
    name = "openai_images"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: str = DEFAULT_MODEL,
        size: str = DEFAULT_SIZE,
        timeout_sec: float = 120.0,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.size = size
        self.timeout_sec = timeout_sec

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        if not self.api_key:
            return ProviderGenerateResult(
                error_code="OPENAI_NO_KEY",
                error_message="OPENAI_API_KEY not set",
            )

        run_dir = req.artifacts_dir / req.task.task_id / req.result_id
        run_dir.mkdir(parents=True, exist_ok=True)
        prompt = _build_prompt(req)
        assets: list[GeneratedAsset] = []

        # OpenAI images API: request one image per candidate for clearer versioning
        for i in range(req.candidate_count):
            idx = i + 1
            body = {
                "model": self.model,
                "prompt": f"{prompt} Variation {idx} of {req.candidate_count}.",
                "n": 1,
                "size": self.size,
            }
            # gpt-image models often return b64; dall-e-3 uses url or b64_json
            if "dall-e" in self.model:
                body["response_format"] = "b64_json"

            try:
                data = self._post(body)
            except Exception as e:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="OPENAI_HTTP_ERROR",
                    error_message=str(e),
                    provider_meta={
                        "kind": "openai_images",
                        "partial": len(assets),
                        "model": self.model,
                    },
                )

            path = run_dir / f"cand_{idx}.png"
            try:
                self._save_image_payload(data, path)
            except Exception as e:
                return ProviderGenerateResult(
                    assets=assets,
                    error_code="OPENAI_SAVE_ERROR",
                    error_message=str(e),
                    provider_meta={"kind": "openai_images", "model": self.model},
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
                "kind": "openai_images",
                "wrote_files": True,
                "artifacts_dir": str(run_dir),
                "model": self.model,
                "external_api": True,
            },
        )

    def _post(self, body: dict) -> dict:
        raw = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "evaw-live-gen/0.2",
        }
        org = (os.environ.get("OPENAI_ORG_ID") or os.environ.get("OPENAI_ORGANIZATION") or "").strip()
        if org:
            headers["OpenAI-Organization"] = org
        project = (os.environ.get("OPENAI_PROJECT_ID") or "").strip()
        if project:
            headers["OpenAI-Project"] = project
        request = urllib.request.Request(
            API_URL,
            data=raw,
            headers=headers,
            method="POST",
        )
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
            raise RuntimeError(f"No data in OpenAI response keys={list(data.keys())}")
        item = items[0]
        if "b64_json" in item:
            path.write_bytes(base64.b64decode(item["b64_json"]))
            return
        if "url" in item:
            with urllib.request.urlopen(item["url"], timeout=60) as resp:
                path.write_bytes(resp.read())
            return
        raise RuntimeError(f"Neither b64_json nor url in item keys={list(item.keys())}")
