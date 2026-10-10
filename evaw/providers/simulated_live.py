"""Simulated live provider — closer to real Live Gen without an API key.

Writes per-run artifact folder with:
- candidates.json (metadata)
- cand_N.png placeholder images (Pillow if available, else minimal PNG)
"""

from __future__ import annotations

import json
from pathlib import Path

from ..schema import GeneratedAsset, new_id, utcnow
from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult


def _write_minimal_png(path: Path, width: int = 512, height: int = 512) -> None:
    """Write a valid solid-color PNG without Pillow (fallback)."""
    # 1x1 PNG expanded is complex; use Pillow when present, else a tiny fixed PNG.
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (width, height), color=(32, 48, 72))
        draw = ImageDraw.Draw(img)
        label = path.stem
        draw.rectangle([24, 24, width - 24, height - 24], outline=(90, 140, 200), width=4)
        draw.text((40, 40), f"EVAW simulated live\n{label}", fill=(220, 230, 240))
        img.save(path, format="PNG")
        return
    except Exception:
        pass

    # Minimal 1x1 PNG bytes
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"\x00" + b"\xff\x00\x00"  # filter + RGB red pixel
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


class SimulatedLiveGenerationProvider(GenerationProvider):
    name = "simulated_live"

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        run_dir = (
            req.artifacts_dir
            / req.task.task_id
            / req.result_id
        )
        run_dir.mkdir(parents=True, exist_ok=True)

        strategy = req.task.strategy
        scene = strategy.scene_direction if strategy else ""
        composition = strategy.composition_notes if strategy else ""
        selling = list(strategy.selling_point_priority) if strategy else []

        assets: list[GeneratedAsset] = []
        meta_candidates = []

        for i in range(req.candidate_count):
            idx = i + 1
            filename = f"cand_{idx}.png"
            path = run_dir / filename
            _write_minimal_png(path)

            prompt_echo = {
                "sku_id": req.task.sku_id,
                "brand_id": req.task.brand_id,
                "mode": req.mode.value,
                "scene_direction": scene,
                "composition_notes": composition,
                "selling_point_priority": selling,
                "platform": req.task.platform.value,
                "size_hint": "800x800",
                "candidate_index": idx,
            }
            uri = path.resolve().as_uri()
            asset = GeneratedAsset(
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
            assets.append(asset)
            meta_candidates.append(
                {
                    "asset_id": asset.asset_id,
                    "version": asset.version,
                    "path": str(path),
                    "uri": uri,
                    "prompt_echo": prompt_echo,
                }
            )

        manifest = {
            "provider": self.name,
            "task_id": req.task.task_id,
            "generation_result_id": req.result_id,
            "knowledge_snapshot_id": req.snapshot_id,
            "strategy_version": req.strategy_version,
            "mode": req.mode.value,
            "candidate_count": len(assets),
            "created_at": utcnow().isoformat(),
            "candidates": meta_candidates,
            "note": (
                "Simulated live — no external image API called. "
                "Set OPENAI_API_KEY (or other supported key) for real Live Gen."
            ),
        }
        manifest_path = run_dir / "candidates.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return ProviderGenerateResult(
            assets=assets,
            provider_meta={
                "kind": "simulated_live",
                "wrote_files": True,
                "artifacts_dir": str(run_dir),
                "manifest": str(manifest_path),
            },
        )
