"""Asset Generation Agent — stub or live via pluggable providers.

Knowledge gate is ALWAYS enforced before any provider runs (live included).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from ..knowledge import assert_may_generate
from ..providers import (
    GenMode,
    GenerationProvider,
    ProviderGenerateRequest,
    build_provider,
    describe_provider_choice,
)
from ..schema import (
    GenerationMode,
    GenerationResult,
    GenerationResultStatus,
    VisualTask,
    new_id,
    utcnow,
)

# D1 confirmed: 2–4 candidates
DEFAULT_CANDIDATE_COUNT = 3

# Default artifacts root (relative to CWD when running CLI)
DEFAULT_ARTIFACTS_DIR = Path("artifacts")


class AssetGenerationAgent:
    name = "Asset Generation Agent"

    def __init__(
        self,
        candidate_count: int = DEFAULT_CANDIDATE_COUNT,
        *,
        gen_mode: GenMode = "stub",
        provider: Optional[GenerationProvider] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
    ):
        if not 2 <= candidate_count <= 4:
            raise ValueError("candidate_count must be 2–4 (D1 default)")
        self.candidate_count = candidate_count
        self.gen_mode: GenMode = gen_mode
        self.provider = provider or build_provider(gen_mode)
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.last_provider_meta: dict = {}

    def provider_summary(self) -> str:
        return describe_provider_choice(self.gen_mode, self.provider)

    def run(
        self,
        task: VisualTask,
        *,
        mode: GenerationMode | None = None,
        force_fail: bool = False,
    ) -> GenerationResult:
        # Hard gate — live cannot bypass
        assert_may_generate(task)

        if not task.strategy or not task.knowledge:
            raise RuntimeError("Strategy and Knowledge required before generation")

        snapshot_id = task.knowledge.snapshot_id or new_id("ksnap")
        strategy_version = task.strategy.version

        if mode is None:
            if task.asset_type.value == "sku":
                mode = GenerationMode.SKU_EXTEND
            elif task.asset_type.value == "pdp_module":
                mode = GenerationMode.PDP_MODULE
            else:
                mode = GenerationMode.HERO

        started = utcnow()
        result_id = new_id("gen")

        if force_fail:
            return GenerationResult(
                generation_result_id=result_id,
                task_id=task.task_id,
                mode=mode,
                status=GenerationResultStatus.FAILED,
                assets=[],
                knowledge_snapshot_id=snapshot_id,
                strategy_version=strategy_version,
                started_at=started,
                finished_at=utcnow(),
                error_code="GEN_FORCED_FAIL",
                error_message="Forced generation failure for demo",
                candidate_count=0,
            )

        req = ProviderGenerateRequest(
            task=task,
            mode=mode,
            result_id=result_id,
            snapshot_id=snapshot_id,
            strategy_version=strategy_version,
            candidate_count=self.candidate_count,
            artifacts_dir=self.artifacts_dir,
        )
        prov = self.provider.generate(req)
        self.last_provider_meta = dict(prov.provider_meta or {})

        if not prov.ok:
            return GenerationResult(
                generation_result_id=result_id,
                task_id=task.task_id,
                mode=mode,
                status=GenerationResultStatus.FAILED
                if not prov.assets
                else GenerationResultStatus.PARTIAL,
                assets=list(prov.assets),
                knowledge_snapshot_id=snapshot_id,
                strategy_version=strategy_version,
                started_at=started,
                finished_at=utcnow(),
                error_code=prov.error_code or "GEN_PROVIDER_FAIL",
                error_message=prov.error_message or "Provider returned no assets",
                candidate_count=len(prov.assets),
            )

        # Enforce D1 band even if provider misbehaves
        assets = list(prov.assets)[:4]
        if len(assets) < 2:
            return GenerationResult(
                generation_result_id=result_id,
                task_id=task.task_id,
                mode=mode,
                status=GenerationResultStatus.FAILED,
                assets=assets,
                knowledge_snapshot_id=snapshot_id,
                strategy_version=strategy_version,
                started_at=started,
                finished_at=utcnow(),
                error_code="GEN_CANDIDATE_COUNT",
                error_message=f"Expected 2–4 candidates, got {len(assets)}",
                candidate_count=len(assets),
            )

        return GenerationResult(
            generation_result_id=result_id,
            task_id=task.task_id,
            mode=mode,
            status=GenerationResultStatus.SUCCEEDED,
            assets=assets,
            knowledge_snapshot_id=snapshot_id,
            strategy_version=strategy_version,
            started_at=started,
            finished_at=utcnow(),
            candidate_count=len(assets),
        )
