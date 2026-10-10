"""QA provider interface (Live QA — rules + optional multimodal)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..schema import GenerationResult, QAOverall, QAReport, VisualTask


@dataclass
class QAEvaluateRequest:
    task: VisualTask
    generation: GenerationResult
    artifacts_dir: Path
    # Optional inject (P0 / demos): overrides engine overall when set
    inject_overall: Optional[QAOverall] = None
    # Demo fixture: pass | fail_fidelity | fail_text | fail_brand | fail_layout | risk_mobile
    fixture: Optional[str] = None


@dataclass
class QAEvaluateResult:
    report: QAReport
    provider_meta: dict = field(default_factory=dict)


class QAProvider(ABC):
    name: str = "base"
    engine: str = "base"

    @abstractmethod
    def evaluate(self, req: QAEvaluateRequest) -> QAEvaluateResult:
        ...
