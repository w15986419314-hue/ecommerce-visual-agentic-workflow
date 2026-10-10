"""Visual QA Agent — stub (injectable) or live (rules ± multimodal)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from ..qa import (
    QAEvaluateRequest,
    QAMode,
    QAProvider,
    build_qa_provider,
    describe_qa_provider,
)
from ..schema import (
    GenerationResult,
    QAOverall,
    QAReport,
    VisualTask,
)

DEFAULT_ARTIFACTS_DIR = Path("artifacts")


class VisualQAAgent:
    name = "Visual QA Agent"

    def __init__(
        self,
        *,
        qa_mode: QAMode = "stub",
        provider: Optional[QAProvider] = None,
        artifacts_dir: Optional[Union[str, Path]] = None,
    ):
        self.qa_mode: QAMode = qa_mode
        self.provider = provider or build_qa_provider(qa_mode)
        self.artifacts_dir = Path(artifacts_dir or DEFAULT_ARTIFACTS_DIR)
        self.last_provider_meta: dict = {}

    def provider_summary(self) -> str:
        return describe_qa_provider(self.qa_mode, self.provider)

    def run(
        self,
        task: VisualTask,
        generation: GenerationResult,
        *,
        overall: Optional[QAOverall] = None,
        fixture: Optional[str] = None,
        risk_note: str = "Structure angle near-miss on side rail; needs Lead confirm",
    ) -> QAReport:
        """Run QA. `overall` inject works in stub always; in live only if provided (P0)."""
        del risk_note  # retained for call-site compat; stub provider has its own note
        if not generation.assets:
            raise RuntimeError("No assets to QA")

        req = QAEvaluateRequest(
            task=task,
            generation=generation,
            artifacts_dir=self.artifacts_dir,
            inject_overall=overall,
            fixture=fixture,
        )
        result = self.provider.evaluate(req)
        self.last_provider_meta = dict(result.provider_meta)
        return result.report
