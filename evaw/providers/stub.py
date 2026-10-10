"""Stub provider — in-memory fake URIs, no files written."""

from __future__ import annotations

from ..schema import GeneratedAsset, new_id
from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult


class StubGenerationProvider(GenerationProvider):
    name = "stub"

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        assets: list[GeneratedAsset] = []
        for i in range(req.candidate_count):
            assets.append(
                GeneratedAsset(
                    asset_id=new_id("asset"),
                    task_id=req.task.task_id,
                    generation_result_id=req.result_id,
                    asset_type=req.task.asset_type.value,
                    uri=(
                        f"stub://generated/{req.task.sku_id}/"
                        f"{req.mode.value}/cand_{i + 1}.png"
                    ),
                    platform_target=req.task.platform.value,
                    mode=req.mode,
                    knowledge_snapshot_id=req.snapshot_id,
                    strategy_version=req.strategy_version,
                    version=f"v{i + 1}",
                )
            )
        return ProviderGenerateResult(
            assets=assets,
            provider_meta={"kind": "stub", "wrote_files": False},
        )
