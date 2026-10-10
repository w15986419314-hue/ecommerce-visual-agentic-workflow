"""Resolve Live / Stub generation providers.

Env:
  EVAW_GEN_MODE=stub|live   (default stub)
  OPENAI_API_KEY            → real OpenAI Images when mode=live
  EVAW_FORCE_SIMULATED_LIVE=1 → even with key, use simulated live (tests)
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult
from .openai_images import OpenAIImagesProvider
from .simulated_live import SimulatedLiveGenerationProvider
from .stub import StubGenerationProvider

GenMode = Literal["stub", "live"]


def detect_api_keys() -> dict[str, bool]:
    return {
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "REPLICATE_API_TOKEN": bool(os.environ.get("REPLICATE_API_TOKEN")),
        "FAL_KEY": bool(os.environ.get("FAL_KEY")),
        "STABILITY_API_KEY": bool(os.environ.get("STABILITY_API_KEY")),
    }


def resolve_gen_mode(
    cli_live: Optional[bool] = None,
    explicit: Optional[str] = None,
) -> GenMode:
    """CLI --live wins; else EVAW_GEN_MODE; else stub."""
    if cli_live is True:
        return "live"
    if cli_live is False:
        return "stub"
    if explicit in ("stub", "live"):
        return explicit  # type: ignore[return-value]
    env = (os.environ.get("EVAW_GEN_MODE") or "stub").strip().lower()
    if env == "live":
        return "live"
    return "stub"


def build_provider(mode: GenMode) -> GenerationProvider:
    if mode == "stub":
        return StubGenerationProvider()

    # live mode
    if os.environ.get("EVAW_FORCE_SIMULATED_LIVE", "").strip() in ("1", "true", "yes"):
        return SimulatedLiveGenerationProvider()

    keys = detect_api_keys()
    if keys["OPENAI_API_KEY"]:
        return OpenAIImagesProvider()

    # Other keys detected but no adapter yet → simulated with note
    # (interface is ready; OpenAI is the first wired adapter)
    return SimulatedLiveGenerationProvider()


def describe_provider_choice(mode: GenMode, provider: GenerationProvider) -> str:
    keys = detect_api_keys()
    present = [k for k, v in keys.items() if v]
    if mode == "stub":
        return f"mode=stub provider={provider.name}"
    if provider.name == "openai_images":
        return f"mode=live provider={provider.name} external_api=true keys={present}"
    return (
        f"mode=live provider={provider.name} external_api=false "
        f"(no supported image API key; keys_present={present or 'none'})"
    )


__all__ = [
    "GenerationProvider",
    "ProviderGenerateRequest",
    "ProviderGenerateResult",
    "StubGenerationProvider",
    "SimulatedLiveGenerationProvider",
    "OpenAIImagesProvider",
    "GenMode",
    "resolve_gen_mode",
    "build_provider",
    "describe_provider_choice",
    "detect_api_keys",
]
