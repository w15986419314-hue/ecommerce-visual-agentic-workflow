#!/usr/bin/env python3
"""CLI: run demo scenarios and print status traces."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .feishu import describe_feishu_adapter, resolve_feishu_adapter
from .providers import resolve_gen_mode
from .qa import describe_qa_provider, resolve_qa_mode
from .schema import (
    STRUCTURE_SENSITIVE,
    AssetType,
    OperationsInput,
    Platform,
    QAOverall,
)
from .workflow import WorkflowConfig, WorkflowEngine, scenario_feishu_demo


def _deadline_days(n: int = 7) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=n)


def ops_happy() -> OperationsInput:
    return OperationsInput(
        brand_id="brand_xiu",
        sku_id="SKU-BED-001",
        platform=Platform.TMALL,
        asset_type=AssetType.HERO,
        selling_points=["稳固承重", "快速折叠", "客房场景"],
        size_spec="800x800",
        deadline=_deadline_days(),
        is_new_product=False,
        risk_flags=[],
        created_by="ops_demo",
    )


def ops_knowledge_missing() -> OperationsInput:
    return OperationsInput(
        brand_id="brand_xiu",
        sku_id="SKU-BED-MISSING",
        platform=Platform.TMALL,
        asset_type=AssetType.HERO,
        selling_points=["稳固承重"],
        size_spec="800x800",
        deadline=_deadline_days(),
        is_new_product=False,
        risk_flags=[],
        created_by="ops_demo",
    )


def ops_high_risk() -> OperationsInput:
    return OperationsInput(
        brand_id="brand_xiu",
        sku_id="SKU-BED-STRUCT",
        platform=Platform.JD,
        asset_type=AssetType.HERO,
        selling_points=["结构真实", "侧板完整", "客房场景"],
        size_spec="800x800",
        deadline=_deadline_days(),
        is_new_product=True,  # also forces HITL
        risk_flags=[STRUCTURE_SENSITIVE],
        created_by="ops_demo",
    )


SCENARIOS = (
    "all",
    "happy",
    "knowledge-block",
    "high-risk",
    "live-happy",
    "live-knowledge-block",
    "feishu-demo",
    "qa-live-demo",
)


def _make_engine(
    gen_mode: str, artifacts_dir: str, *, qa_mode: str = "stub"
) -> WorkflowEngine:
    return WorkflowEngine(
        WorkflowConfig(
            audit_sample_rate=0.15,
            rng_seed=42,
            candidate_count=3,
            gen_mode=gen_mode,
            qa_mode=qa_mode,
            artifacts_dir=artifacts_dir,
        )
    )


def run_feishu_demo(*, artifacts_dir: str = "artifacts", force_mock: bool = False) -> int:
    mock_root = str(Path(artifacts_dir) / "feishu_mock")
    Path(mock_root).mkdir(parents=True, exist_ok=True)
    Path(artifacts_dir, "console_placeholder").mkdir(parents=True, exist_ok=True)

    adapter = resolve_feishu_adapter(
        force_mock=True if force_mock else None,
        mock_root=mock_root,
    )
    engine = _make_engine("stub", artifacts_dir, qa_mode="stub")
    task, log, ref = scenario_feishu_demo(engine, feishu=adapter)

    print(log.dump())
    print()
    print(f"final_status={task.status.value}")
    print(f"task_id={task.task_id}")
    print(f"intake_id={ref.intake_id}")
    print(f"auto_approved={task.auto_approved}")
    print(f"feishu_adapter={adapter.name}")
    print(f"feishu={describe_feishu_adapter(adapter)}")
    print(f"connected={'yes' if adapter.name == 'feishu_api' else 'no (mock)'}")
    if ref.mock_path:
        print(f"intake_path={ref.mock_path}")
    # Re-emit approval link for summary
    if task.status.value in ("Delivered", "PendingReview", "Approved", "KnowledgePending"):
        link = adapter.approval_link(task)
        print(f"approval_url={link.url}")
        print(f"approval_console={link.console}")
        if link.detail:
            print(f"approval_detail={link.detail}")
    return 0


def run_qa_live_demo(*, artifacts_dir: str = "artifacts", gen_mode: str = "stub") -> int:
    engine = _make_engine(gen_mode, artifacts_dir, qa_mode="live")
    results = engine.scenario_qa_live_demo()
    code = 0
    expected = {
        "pass": ("Delivered", "Pass"),
        "pass_with_risk": ("Delivered", "PassWithRisk"),
        "fail": ("QAFailed", "Fail"),
    }
    for i, (name, task, log) in enumerate(results):
        if i:
            print("\n" + "=" * 72 + "\n")
        print(log.dump())
        print()
        exp_status, exp_overall = expected[name]
        qa_overall = task.qa.overall.value if task.qa else None
        ok = task.status.value == exp_status and qa_overall == exp_overall
        if not ok:
            code = 1
        print(f"case={name}")
        print(f"final_status={task.status.value} expected_status={exp_status}")
        print(f"qa_overall={qa_overall} expected_overall={exp_overall}")
        print(f"qa_engine={task.qa.engine if task.qa else None}")
        print(
            f"reason_code={task.qa.reason_code.value if task.qa and task.qa.reason_code else None}"
        )
        print(f"qa_mode=live")
        print(f"provider={engine.qa_agent.provider.name}")
        print(f"qa={describe_qa_provider('live', engine.qa_agent.provider)}")
        print(f"multimodal_connected=no (rules default without EVAW_QA_MULTIMODAL+key)")
        print(f"ok={ok}")
        if task.qa:
            for dim, dr in task.qa.dimensions.items():
                print(f"  dim.{dim}={dr.status.value} — {dr.notes[:80]}")
    return code


def run_one(
    name: str,
    *,
    gen_mode: str = "stub",
    qa_mode: str = "stub",
    artifacts_dir: str = "artifacts",
    force_feishu_mock: bool = False,
) -> int:
    if name == "feishu-demo":
        return run_feishu_demo(
            artifacts_dir=artifacts_dir, force_mock=force_feishu_mock
        )
    if name == "qa-live-demo":
        return run_qa_live_demo(artifacts_dir=artifacts_dir, gen_mode=gen_mode)

    # live-* scenarios always use live generation regardless of default mode
    effective_mode = gen_mode
    if name.startswith("live-"):
        effective_mode = "live"

    engine = _make_engine(effective_mode, artifacts_dir, qa_mode=qa_mode)

    if name == "happy":
        task, log = engine.scenario_happy_path(ops_happy())
    elif name == "knowledge-block":
        task, log = engine.scenario_knowledge_block(ops_knowledge_missing())
    elif name == "high-risk":
        task, log = engine.scenario_high_risk_hitl(
            ops_high_risk(), qa_overall=QAOverall.PASS_WITH_RISK
        )
    elif name == "live-happy":
        task, log = engine.scenario_live_happy(ops_happy())
    elif name == "live-knowledge-block":
        task, log = engine.scenario_live_knowledge_block(ops_knowledge_missing())
    elif name == "all":
        return run_all(gen_mode=gen_mode, qa_mode=qa_mode, artifacts_dir=artifacts_dir)
    else:
        print(f"Unknown scenario: {name}", file=sys.stderr)
        return 2

    print(log.dump())
    print()
    print(f"final_status={task.status.value}")
    print(f"task_id={task.task_id}")
    print(f"auto_approved={task.auto_approved}")
    print(f"audit_sampled={task.audit_sampled}")
    print(f"knowledge_status={task.knowledge_status.value}")
    print(f"gen_mode={effective_mode}")
    print(f"provider={engine.gen_agent.provider.name}")
    print(f"qa_mode={qa_mode}")
    print(f"qa_provider={engine.qa_agent.provider.name}")
    print(f"qa={describe_qa_provider(qa_mode, engine.qa_agent.provider)}")  # type: ignore[arg-type]
    if task.qa:
        print(f"qa_overall={task.qa.overall.value}")
        print(f"qa_engine={task.qa.engine}")
        print(
            f"reason_code={task.qa.reason_code.value if task.qa.reason_code else None}"
        )
    if task.generation:
        print(f"candidate_count={task.generation.candidate_count}")
        print(f"knowledge_snapshot_id={task.generation.knowledge_snapshot_id}")
        print(f"strategy_version={task.generation.strategy_version}")
    if task.block_reason:
        print(f"block_reason={task.block_reason}")
    return 0


def run_all(
    *, gen_mode: str = "stub", qa_mode: str = "stub", artifacts_dir: str = "artifacts"
) -> int:
    names = ["happy", "knowledge-block", "high-risk"]
    code = 0
    for i, name in enumerate(names):
        if i:
            print("\n" + "=" * 72 + "\n")
        rc = run_one(
            name, gen_mode=gen_mode, qa_mode=qa_mode, artifacts_dir=artifacts_dir
        )
        if rc != 0:
            code = rc
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ecommerce Visual Agentic Workflow — demo scenarios "
            "(Schema + state machine + 3 Agents + HITL + Live Gen + Live QA + Feishu D3)"
        )
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default="all",
        choices=list(SCENARIOS),
        help="Which path to run (default: all). qa-live-demo = Live QA rules.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Force Live Gen mode for stub scenarios (EVAW_GEN_MODE=live equivalent)",
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help="Force stub Gen mode (overrides EVAW_GEN_MODE)",
    )
    parser.add_argument(
        "--qa-live",
        action="store_true",
        help="Force Live QA (rules ± multimodal). EVAW_QA_MODE=live equivalent",
    )
    parser.add_argument(
        "--qa-stub",
        action="store_true",
        help="Force stub QA (overrides EVAW_QA_MODE)",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Directory for live/simulated candidate files (default: artifacts)",
    )
    parser.add_argument(
        "--feishu-mock",
        action="store_true",
        help="Force Feishu mock adapter even if FEISHU_APP_ID/SECRET are set",
    )
    args = parser.parse_args(argv)

    cli_live = None
    if args.live and args.stub:
        print("Cannot combine --live and --stub", file=sys.stderr)
        return 2
    if args.live:
        cli_live = True
    elif args.stub:
        cli_live = False

    cli_qa_live = None
    if args.qa_live and args.qa_stub:
        print("Cannot combine --qa-live and --qa-stub", file=sys.stderr)
        return 2
    if args.qa_live:
        cli_qa_live = True
    elif args.qa_stub:
        cli_qa_live = False

    gen_mode = resolve_gen_mode(cli_live=cli_live)
    qa_mode = resolve_qa_mode(cli_qa_live=cli_qa_live)

    # Ensure artifacts dir exists for live runs
    Path(args.artifacts_dir).mkdir(parents=True, exist_ok=True)

    return run_one(
        args.scenario,
        gen_mode=gen_mode,
        qa_mode=qa_mode,
        artifacts_dir=args.artifacts_dir,
        force_feishu_mock=args.feishu_mock,
    )


if __name__ == "__main__":
    raise SystemExit(main())
