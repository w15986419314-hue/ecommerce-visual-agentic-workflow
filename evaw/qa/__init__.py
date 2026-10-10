"""Resolve Live / Stub QA providers.

Env:
  EVAW_QA_MODE=stub|live|rules   (default stub; live and rules both use rules engine)
  OPENAI_API_KEY + EVAW_QA_MULTIMODAL=1 → multimodal wrap when mode=live
  EVAW_FORCE_RULES_QA=1 → never call vision even with key
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from .base import QAEvaluateRequest, QAEvaluateResult, QAProvider
from .multimodal import MultimodalQAProvider, multimodal_enabled
from .rules import RulesQAProvider
from .stub import StubQAProvider

QAMode = Literal["stub", "live"]


def resolve_qa_mode(
    cli_qa_live: Optional[bool] = None,
    explicit: Optional[str] = None,
) -> QAMode:
    """CLI --qa-live wins; else EVAW_QA_MODE; else stub."""
    if cli_qa_live is True:
        return "live"
    if cli_qa_live is False:
        return "stub"
    if explicit in ("stub", "live", "rules"):
        return "stub" if explicit == "stub" else "live"
    env = (os.environ.get("EVAW_QA_MODE") or "stub").strip().lower()
    if env in ("live", "rules"):
        return "live"
    return "stub"


def build_qa_provider(mode: QAMode) -> QAProvider:
    if mode == "stub":
        return StubQAProvider()

    # live → rules, optionally multimodal
    if os.environ.get("EVAW_FORCE_RULES_QA", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return RulesQAProvider()

    if multimodal_enabled():
        return MultimodalQAProvider()

    return RulesQAProvider()


def describe_qa_provider(mode: QAMode, provider: QAProvider) -> str:
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    mm = multimodal_enabled()
    if mode == "stub":
        return f"qa_mode=stub provider={provider.name} engine={provider.engine}"
    if provider.name == "multimodal" and mm:
        return (
            f"qa_mode=live provider={provider.name} engine={provider.engine} "
            f"external_api=true (vision eligible) openai_key={'yes' if has_key else 'no'}"
        )
    return (
        f"qa_mode=live provider={provider.name} engine={provider.engine} "
        f"external_api=false (rules only; openai_key={'yes' if has_key else 'no'}; "
        f"set EVAW_QA_MULTIMODAL=1 with OPENAI_API_KEY for vision)"
    )


__all__ = [
    "QAProvider",
    "QAEvaluateRequest",
    "QAEvaluateResult",
    "StubQAProvider",
    "RulesQAProvider",
    "MultimodalQAProvider",
    "QAMode",
    "resolve_qa_mode",
    "build_qa_provider",
    "describe_qa_provider",
    "multimodal_enabled",
]
