"""Generation provider interface (Phase 1 Live Gen)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..schema import GeneratedAsset, GenerationMode, VisualTask


@dataclass
class ProviderGenerateRequest:
    task: VisualTask
    mode: GenerationMode
    result_id: str
    snapshot_id: str
    strategy_version: str
    candidate_count: int
    artifacts_dir: Path


@dataclass
class ProviderGenerateResult:
    assets: list[GeneratedAsset] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    provider_meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error_code is None and len(self.assets) > 0


class GenerationProvider(ABC):
    """Pluggable image/candidate generation backend."""

    name: str = "base"

    @abstractmethod
    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        """Produce 2–4 candidates. Caller has already passed Knowledge gate."""
        ...
