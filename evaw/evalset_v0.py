"""Load evalset/v0 and run Rules QA against expected overall / reason_code."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .qa.base import QAEvaluateRequest
from .qa.rules import RulesQAProvider
from .schema import (
    AssetType,
    CreativeBrief,
    GeneratedAsset,
    GenerationMode,
    GenerationResult,
    GenerationResultStatus,
    KnowledgeStatusEnum,
    Platform,
    TaskStatus,
    VisualStrategyPackage,
    VisualTask,
    new_id,
    utcnow,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES_PATH = REPO_ROOT / "evalset" / "v0" / "cases.json"


def _deadline() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


def _platform(value: str) -> Platform:
    return Platform(value.strip().lower())


def _asset_type(value: str) -> AssetType:
    return AssetType(value.strip().lower())


def build_request(case: dict[str, Any], artifacts_dir: Path) -> QAEvaluateRequest:
    fx = case["fixture"]
    task_id = new_id("eval")
    gen_id = new_id("gen")
    asset_id = new_id("asset")
    brand_id = str(fx.get("brand_id") or "")
    sku_id = str(fx.get("sku_id") or "SKU-DEMO")
    platform = _platform(str(fx.get("platform") or "tmall"))
    asset_type = _asset_type(str(fx.get("asset_type") or "hero"))
    selling = list(fx.get("selling_points") or [])
    risk_flags = list(fx.get("risk_flags") or [])
    snap = str(fx.get("knowledge_snapshot_id") or "")
    strat_ver = str(fx.get("strategy_version") or "v1")
    uri = str(fx.get("uri") or f"stub://eval/{case['id']}.png")
    meta = dict(fx.get("metadata") or {})

    brief = CreativeBrief(
        brief_id=new_id("brief"),
        task_id=task_id,
        summary=case.get("scenario") or case["id"],
        selling_points=selling,
        platform=platform,
        asset_type=asset_type,
        constraints_summary="evalset-v0 synthetic",
    )
    strategy = VisualStrategyPackage(
        strategy_id=new_id("strat"),
        task_id=task_id,
        version=strat_ver,
        scene_direction="evalset synthetic scene",
        composition_notes="evalset",
        selling_point_priority=selling,
        risk_flags=list(risk_flags),
    )
    task = VisualTask(
        task_id=task_id,
        status=TaskStatus.QA_PENDING,
        brand_id=brand_id,
        sku_id=sku_id,
        platform=platform,
        asset_type=asset_type,
        deadline=_deadline(),
        is_new_product=bool(fx.get("is_new_product")),
        risk_flags=risk_flags,
        knowledge_status=KnowledgeStatusEnum.READY,
        current_strategy_id=strategy.strategy_id,
        brief=brief,
        strategy=strategy,
    )
    asset = GeneratedAsset(
        asset_id=asset_id,
        task_id=task_id,
        generation_result_id=gen_id,
        asset_type=asset_type.value,
        uri=uri,
        platform_target=platform.value,
        mode=GenerationMode.HERO,
        knowledge_snapshot_id=snap,
        strategy_version=strat_ver,
        metadata=meta,
    )
    generation = GenerationResult(
        generation_result_id=gen_id,
        task_id=task_id,
        mode=GenerationMode.HERO,
        status=GenerationResultStatus.SUCCEEDED,
        assets=[asset],
        knowledge_snapshot_id=snap or "ks_missing",
        strategy_version=strat_ver,
        started_at=utcnow(),
        finished_at=utcnow(),
        candidate_count=1,
    )
    fixture_name = fx.get("qa_fixture")
    if fixture_name is not None:
        fixture_name = str(fixture_name).strip() or None

    return QAEvaluateRequest(
        task=task,
        generation=generation,
        artifacts_dir=artifacts_dir,
        fixture=fixture_name,
    )


def load_cases(path: Optional[Path] = None) -> dict[str, Any]:
    p = path or DEFAULT_CASES_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data.get("cases"), list):
        raise ValueError(f"Invalid evalset: missing cases in {p}")
    return data


def run_evalset_v0(
    *,
    cases_path: Optional[Path] = None,
    artifacts_dir: str = "artifacts",
) -> tuple[int, list[dict[str, Any]]]:
    """Run Rules QA on each case. Returns (exit_code, row_dicts)."""
    data = load_cases(cases_path)
    cases = data["cases"]
    provider = RulesQAProvider()
    art = Path(artifacts_dir)
    art.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    matched = 0
    for case in cases:
        req = build_request(case, art)
        result = provider.evaluate(req)
        report = result.report
        got_overall = report.overall.value
        got_reason = report.reason_code.value if report.reason_code else None
        exp_overall = case["expected_overall"]
        exp_reason = case.get("expected_reason_code")
        overall_ok = got_overall == exp_overall
        # Pass expects null reason; otherwise require reason match when expected is set
        if exp_overall == "Pass":
            reason_ok = exp_reason in (None, "") or got_reason == exp_reason
        elif exp_reason:
            reason_ok = got_reason == exp_reason
        else:
            reason_ok = True
        ok = overall_ok and reason_ok
        if ok:
            matched += 1
        rows.append(
            {
                "id": case["id"],
                "ok": ok,
                "expected_overall": exp_overall,
                "got_overall": got_overall,
                "expected_reason_code": exp_reason,
                "got_reason_code": got_reason,
                "primary_dimension": report.primary_dimension,
                "dimensions_focus": case.get("dimensions_focus") or [],
                "scenario": case.get("scenario") or "",
            }
        )

    total = len(cases)
    rate = (matched / total * 100.0) if total else 0.0
    print(f"evalset=v0 engine=rules cases={total} matched={matched} pass_rate={rate:.1f}%")
    print(f"cases_path={cases_path or DEFAULT_CASES_PATH}")
    print()
    for row in rows:
        mark = "PASS" if row["ok"] else "FAIL"
        print(
            f"[{mark}] {row['id']}  "
            f"overall={row['got_overall']} (exp {row['expected_overall']})  "
            f"reason={row['got_reason_code']} (exp {row['expected_reason_code']})"
        )
        if not row["ok"]:
            print(f"       focus={row['dimensions_focus']}  {row['scenario'][:60]}")
    print()
    print(f"pass_rate={rate:.1f}%  ({matched}/{total})")
    return (0 if matched == total else 1), rows
