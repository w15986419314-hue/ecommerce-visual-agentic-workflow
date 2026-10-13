"""Resolve Live / Stub generation providers.

Env:
  EVAW_GEN_MODE=stub|live
  EVAW_GEN_PROVIDER=auto|doubao|dashscope|openai|simulated
  DASHSCOPE_API_KEY                → 通义万相（国内默认优先）
  ARK_API_KEY / DOUBAO_API_KEY     → 豆包 Seedream（可选备用）
  OPENAI_API_KEY                   → OpenAI Images（CN 常 403）
  EVAW_FORCE_SIMULATED_LIVE=1
  EVAW_GEN_FALLBACK_SIMULATED=1    （默认开：外部失败 → simulated）

Auto priority when mode=live:
  1) EVAW_FORCE_SIMULATED_LIVE
  2) EVAW_GEN_PROVIDER explicit
  3) DASHSCOPE_API_KEY → dashscope_wanx
  4) ARK/DOUBAO key → doubao_ark
  5) OPENAI_API_KEY → openai_images
  6) else simulated_live
"""

from __future__ import annotations

import os
from typing import Literal, Optional

from .base import GenerationProvider, ProviderGenerateRequest, ProviderGenerateResult
from .dashscope_wanx import DashScopeWanxProvider
from .doubao_ark import DoubaoArkProvider
from .openai_images import OpenAIImagesProvider
from .simulated_live import SimulatedLiveGenerationProvider
from .stub import StubGenerationProvider

GenMode = Literal["stub", "live"]
GenProviderName = Literal["auto", "doubao", "dashscope", "openai", "simulated"]

_EXTERNAL_NAMES = frozenset({"doubao_ark", "dashscope_wanx", "openai_images"})


def _has_doubao_key() -> bool:
    return bool(
        (os.environ.get("ARK_API_KEY") or "").strip()
        or (os.environ.get("DOUBAO_API_KEY") or "").strip()
        or (os.environ.get("VOLCENGINE_API_KEY") or "").strip()
    )


def detect_api_keys() -> dict[str, bool]:
    return {
        "ARK_API_KEY": _has_doubao_key(),
        "DASHSCOPE_API_KEY": bool(os.environ.get("DASHSCOPE_API_KEY")),
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


def resolve_gen_provider_name() -> GenProviderName:
    raw = (os.environ.get("EVAW_GEN_PROVIDER") or "auto").strip().lower()
    if raw in ("doubao", "doubao_ark", "ark", "seedream", "volc", "volcengine"):
        return "doubao"
    if raw in ("dashscope", "wanx", "tongyi"):
        return "dashscope"
    if raw in ("openai", "openai_images"):
        return "openai"
    if raw in ("simulated", "simulated_live"):
        return "simulated"
    return "auto"


def _fallback_enabled() -> bool:
    v = (os.environ.get("EVAW_GEN_FALLBACK_SIMULATED") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


class LiveWithSimulatedFallback(GenerationProvider):
    """Wrap an external live provider; on failure write simulated candidates."""

    def __init__(self, primary: GenerationProvider):
        self.primary = primary
        self.name = primary.name
        self._last_fallback = False

    def generate(self, req: ProviderGenerateRequest) -> ProviderGenerateResult:
        self._last_fallback = False
        primary_result = self.primary.generate(req)
        if primary_result.ok:
            return primary_result
        if not _fallback_enabled():
            return primary_result

        self._last_fallback = True
        fb = SimulatedLiveGenerationProvider().generate(req)
        meta = dict(fb.provider_meta)
        meta.update(
            {
                "kind": "simulated_live",
                "fallback_from": self.primary.name,
                "primary_error_code": primary_result.error_code,
                "primary_error_message": primary_result.error_message,
                "external_api": False,
                "note": (
                    f"Primary provider {self.primary.name} failed; "
                    "fell back to simulated_live placeholders."
                ),
            }
        )
        return ProviderGenerateResult(
            assets=fb.assets,
            error_code=None,
            error_message=None,
            provider_meta=meta,
        )


def _pick_primary_live() -> GenerationProvider:
    if os.environ.get("EVAW_FORCE_SIMULATED_LIVE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return SimulatedLiveGenerationProvider()

    choice = resolve_gen_provider_name()
    keys = detect_api_keys()

    if choice == "simulated":
        return SimulatedLiveGenerationProvider()
    if choice == "doubao":
        return DoubaoArkProvider()
    if choice == "dashscope":
        return DashScopeWanxProvider()
    if choice == "openai":
        return OpenAIImagesProvider()

    # auto: DashScope 万相 (preferred) → Doubao → OpenAI → simulated
    if keys["DASHSCOPE_API_KEY"]:
        return DashScopeWanxProvider()
    if keys["ARK_API_KEY"]:
        return DoubaoArkProvider()
    if keys["OPENAI_API_KEY"]:
        return OpenAIImagesProvider()
    return SimulatedLiveGenerationProvider()


def build_provider(mode: GenMode) -> GenerationProvider:
    if mode == "stub":
        return StubGenerationProvider()

    primary = _pick_primary_live()
    if primary.name in _EXTERNAL_NAMES and _fallback_enabled():
        return LiveWithSimulatedFallback(primary)
    return primary


def describe_provider_choice(mode: GenMode, provider: GenerationProvider) -> str:
    keys = detect_api_keys()
    present = [k for k, v in keys.items() if v]
    forced = resolve_gen_provider_name()
    if mode == "stub":
        return f"mode=stub provider={provider.name}"

    inner = provider
    if isinstance(provider, LiveWithSimulatedFallback):
        inner = provider.primary

    if inner.name == "doubao_ark":
        return (
            f"mode=live provider={inner.name} external_api=true "
            f"domestic=true gen_provider={forced} keys={present} "
            f"fallback_simulated={_fallback_enabled()}"
        )
    if inner.name == "dashscope_wanx":
        return (
            f"mode=live provider={inner.name} external_api=true "
            f"domestic=true gen_provider={forced} keys={present} "
            f"fallback_simulated={_fallback_enabled()}"
        )
    if inner.name == "openai_images":
        return (
            f"mode=live provider={inner.name} external_api=true "
            f"domestic=false gen_provider={forced} keys={present} "
            f"fallback_simulated={_fallback_enabled()}"
        )
    return (
        f"mode=live provider={inner.name} external_api=false "
        f"gen_provider={forced} "
        f"(no supported image API key or forced simulated; "
        f"keys_present={present or 'none'})"
    )


__all__ = [
    "GenerationProvider",
    "ProviderGenerateRequest",
    "ProviderGenerateResult",
    "StubGenerationProvider",
    "SimulatedLiveGenerationProvider",
    "OpenAIImagesProvider",
    "DashScopeWanxProvider",
    "DoubaoArkProvider",
    "LiveWithSimulatedFallback",
    "GenMode",
    "GenProviderName",
    "resolve_gen_mode",
    "resolve_gen_provider_name",
    "build_provider",
    "describe_provider_choice",
    "detect_api_keys",
]
