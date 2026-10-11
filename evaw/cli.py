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
    ReasonCode,
    TaskStatus,
)
from .evalset_v0 import run_evalset_v0
from .task_store import load_task, save_task
from .workflow import (
    RunLog,
    WorkflowConfig,
    WorkflowEngine,
    scenario_feishu_demo,
    scenario_feishu_intake,
    scenario_hitl_chat_demo,
)



def _load_env_local() -> None:
    """Load .env.local / .env into os.environ (export KEY=val or KEY=val)."""
    import os

    root = Path(__file__).resolve().parent.parent
    for name in (".env.local", ".env"):
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


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
    "evalset-v0",
    "hitl-chat-demo",
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



def run_feishu_intake(
    *,
    brand: str,
    sku: str,
    platform: str = "tmall",
    asset_type: str = "hero",
    selling_points: list[str] | None = None,
    size_spec: str = "800x800",
    deadline: str | None = None,
    is_new_product: bool = False,
    risk_flags: list[str] | None = None,
    requester: str = "ops_feishu_form",
    artifacts_dir: str = "artifacts",
    force_mock: bool = False,
) -> int:
    """Simulate Feishu form/card intake: fields → VisualTask → Feishu notify.

    Formal product: Feishu questionnaire / bot collects the same fields.
    MVP: this CLI stands in for the form submit.
    """
    from .feishu import FeishuBriefPayload, describe_feishu_adapter, resolve_feishu_adapter

    _load_env_local()
    mock_root = str(Path(artifacts_dir) / "feishu_mock")
    Path(mock_root).mkdir(parents=True, exist_ok=True)
    store_dir = str(Path(artifacts_dir) / "intakes")

    points = selling_points or ["稳固承重", "快速折叠"]
    flags = list(risk_flags or [])
    if not deadline:
        deadline = _deadline_days(7).isoformat()

    adapter = resolve_feishu_adapter(
        force_mock=True if force_mock else None,
        mock_root=mock_root,
    )
    engine = _make_engine("stub", artifacts_dir, qa_mode="stub")

    brief = FeishuBriefPayload(
        brand_id=brand,
        sku_id=sku,
        platform=platform,
        asset_type=asset_type,
        selling_points=points,
        size_spec=size_spec,
        deadline_iso=deadline,
        is_new_product=is_new_product,
        risk_flags=flags,
        requester_id=requester,
        source_message_id="cli_feishu_intake",
        chat_id=None,
        raw={"source": "cli_feishu_intake", "simulates": "feishu_form_or_bot"},
    )

    task, log, ref = scenario_feishu_intake(
        engine, brief, feishu=adapter, store_dir=store_dir
    )

    print(log.dump())
    print()
    print(f"final_status={task.status.value}")
    print(f"task_id={task.task_id}")
    print(f"intake_id={ref.intake_id}")
    print(f"brand_id={brand}")
    print(f"sku_id={sku}")
    print(f"platform={platform}")
    print(f"asset_type={asset_type}")
    print(f"is_new_product={is_new_product}")
    print(f"feishu_adapter={adapter.name}")
    print(f"feishu={describe_feishu_adapter(adapter)}")
    print(f"connected={'yes' if adapter.name == 'feishu_api' else 'no (mock)'}")
    if ref.mock_path:
        print(f"intake_path={ref.mock_path}")
    print(f"task_snapshot={Path(store_dir) / (task.task_id + '.json')}")
    print()
    print("Note: MVP uses CLI to simulate Feishu form/bot field submit.")
    print("Formal: same fields via Feishu questionnaire or bot card.")
    return 0


def run_feishu_demo(*, artifacts_dir: str = "artifacts", force_mock: bool = False) -> int:
    _load_env_local()
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



def run_hitl_chat_demo(
    *, artifacts_dir: str = "artifacts", force_mock: bool = False
) -> int:
    """Run to PendingReview, notify Feishu with chat instructions, do NOT auto-approve."""
    _load_env_local()
    mock_root = str(Path(artifacts_dir) / "feishu_mock")
    Path(mock_root).mkdir(parents=True, exist_ok=True)
    hitl_dir = str(Path(artifacts_dir) / "hitl_pending")

    adapter = resolve_feishu_adapter(
        force_mock=True if force_mock else None,
        mock_root=mock_root,
    )
    engine = _make_engine("stub", artifacts_dir, qa_mode="stub")
    task, log, ref = scenario_hitl_chat_demo(
        engine, feishu=adapter, hitl_dir=hitl_dir
    )

    print(log.dump())
    print()
    print(f"final_status={task.status.value}")
    print(f"task_id={task.task_id}")
    print(f"intake_id={ref.intake_id}")
    print(f"auto_approved={task.auto_approved}")
    print(f"waiting_for_human={task.status == TaskStatus.PENDING_REVIEW}")
    print(f"hitl_snapshot={Path(hitl_dir) / (task.task_id + '.json')}")
    print(f"feishu_adapter={adapter.name}")
    print(f"feishu={describe_feishu_adapter(adapter)}")
    print(f"connected={'yes' if adapter.name == 'feishu_api' else 'no (mock)'}")
    print()
    print("Next (human):")
    print(
        f"  python3 -m evaw.cli hitl-apply --task {task.task_id} --decision approve"
    )
    print(
        f"  python3 -m evaw.cli hitl-apply --task {task.task_id} "
        "--decision reject --reason TEXT_ERROR"
    )
    if task.status != TaskStatus.PENDING_REVIEW:
        return 1
    return 0


def run_hitl_apply(
    *,
    task_id: str,
    decision: str,
    reason: str = "FIDELITY_STRUCTURE",
    artifacts_dir: str = "artifacts",
    force_mock: bool = False,
) -> int:
    """Apply Lead approve/reject on a PendingReview snapshot; notify Feishu."""
    _load_env_local()
    hitl_dir = str(Path(artifacts_dir) / "hitl_pending")
    mock_root = str(Path(artifacts_dir) / "feishu_mock")

    try:
        task = load_task(task_id, hitl_dir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    if task.status != TaskStatus.PENDING_REVIEW:
        print(
            f"Task {task_id} status={task.status.value}; "
            "hitl-apply requires PendingReview",
            file=sys.stderr,
        )
        return 1

    adapter = resolve_feishu_adapter(
        force_mock=True if force_mock else None,
        mock_root=mock_root,
    )
    engine = _make_engine("stub", artifacts_dir, qa_mode="stub")
    engine.feishu = adapter
    log = RunLog()
    log.add(
        f"=== HITL APPLY decision={decision} task={task_id} "
        f"reason={reason} ==="
    )

    prev = task.status
    dec = (decision or "").strip().lower()
    if dec in ("approve", "approved", "yes"):
        accept = bool(task.qa and task.qa.overall.value == "PassWithRisk")
        engine.lead_approve(
            task,
            log,
            accept_risk=accept,
            notes="Lead approved via Feishu chat / hitl-apply",
        )
        nr = adapter.notify_status(
            task,
            previous_status=prev,
            note="Lead 已批准（聊天/CLI）",
        )
        log.add(
            f"[feishu:notify] channel={nr.channel} ok={nr.ok} detail={nr.detail}"
        )
        prev = task.status
        engine.deliver(task, log)
        nr = adapter.notify_status(
            task, previous_status=prev, note="Delivered after chat approve"
        )
        log.add(
            f"[feishu:notify] channel={nr.channel} ok={nr.ok} detail={nr.detail}"
        )
        chat_lines = [
            f"[EVAW 人审结果] {task.task_id} → Approved → Delivered",
            f"sku={task.sku_id}（聊天/CLI 批准）",
        ]
        cr = adapter.send_chat_text(chr(10).join(chat_lines))
        log.add(f"[feishu:chat] ok={cr.ok} channel={cr.channel}")
    elif dec in ("reject", "rejected", "no"):
        try:
            rc = ReasonCode(reason.strip().upper())
        except ValueError:
            print(
                f"Unknown reason_code={reason!r}. "
                f"Valid: {[c.value for c in ReasonCode]}",
                file=sys.stderr,
            )
            return 2
        engine.lead_reject(
            task,
            log,
            reason_code=rc,
            notes=f"Lead rejected via Feishu chat / hitl-apply ({rc.value})",
        )
        nr = adapter.notify_status(
            task,
            previous_status=prev,
            note=f"Lead 已打回 reason={rc.value}",
            extra={"reason_code": rc.value},
        )
        log.add(
            f"[feishu:notify] channel={nr.channel} ok={nr.ok} detail={nr.detail}"
        )
        chat_lines = [
            f"[EVAW 人审结果] {task.task_id} → Rejected",
            f"sku={task.sku_id} reason={rc.value}（聊天/CLI 打回）",
        ]
        cr = adapter.send_chat_text(chr(10).join(chat_lines))
        log.add(f"[feishu:chat] ok={cr.ok} channel={cr.channel}")
    else:
        print(
            f"Unknown decision={decision!r}; use approve|reject",
            file=sys.stderr,
        )
        return 2

    snap = save_task(task, hitl_dir)
    log.add(f"[hitl:store] updated={snap}")
    log.add(f"=== DONE status={task.status.value} ===")
    log.add(f"[trace] {log.status_trace(task)}")

    print(log.dump())
    print()
    print(f"final_status={task.status.value}")
    print(f"task_id={task.task_id}")
    print(f"decision={dec}")
    if task.review:
        print(f"review_decision={task.review.decision.value}")
        if task.review.reason_code:
            print(f"reason_code={task.review.reason_code.value}")
    print(f"hitl_snapshot={snap}")
    print(f"feishu_adapter={adapter.name}")
    print(f"feishu={describe_feishu_adapter(adapter)}")
    return 0


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
    if name == "hitl-chat-demo":
        return run_hitl_chat_demo(
            artifacts_dir=artifacts_dir, force_mock=force_feishu_mock
        )
    if name == "qa-live-demo":
        return run_qa_live_demo(artifacts_dir=artifacts_dir, gen_mode=gen_mode)
    if name == "evalset-v0":
        code, _rows = run_evalset_v0(artifacts_dir=artifacts_dir)
        return code

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



def run_feishu_intake_from_json(
    *,
    file_path: str,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
) -> int:
    """Ingest a Feishu form/bitable/webhook JSON payload → VisualTask."""
    import json
    from .feishu.webhook import ingest_payload

    _load_env_local()
    p = Path(file_path)
    if not p.is_file():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 2
    payload = json.loads(p.read_text(encoding="utf-8"))
    try:
        result = ingest_payload(
            payload,
            artifacts_dir=artifacts_dir,
            force_mock=force_mock,
            notify=notify,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def run_feishu_intake_webhook(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
) -> int:
    """Start local HTTP stub for Feishu intake callbacks."""
    from .feishu.webhook import serve_webhook

    _load_env_local()
    serve_webhook(
        host=host,
        port=port,
        artifacts_dir=artifacts_dir,
        force_mock=force_mock,
        notify=notify,
    )
    return 0


def run_feishu_bitable_setup(*, name: str = "EVAW 提需") -> int:
    """Create/document Feishu bitable intake fields. Never sends IM."""
    import json
    from .feishu.bitable_setup import setup_bitable

    _load_env_local()
    report = setup_bitable(name=name)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def run_feishu_bitable_sync(
    *,
    artifacts_dir: str = "artifacts",
    force_mock: bool = True,
    notify: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
    poll: bool = False,
    interval: float = 60.0,
    app_token: str | None = None,
    table_id: str | None = None,
    include_synced: bool = False,
) -> int:
    """Pull new Feishu bitable records → create VisualTask (deduped by record_id)."""
    import json
    from .feishu.bitable_sync import poll_loop, sync_once

    _load_env_local()
    if poll:
        poll_loop(
            interval_sec=interval,
            artifacts_dir=artifacts_dir,
            force_mock=force_mock,
            notify=notify,
            app_token=app_token,
            table_id=table_id,
        )
        return 0
    report = sync_once(
        artifacts_dir=artifacts_dir,
        force_mock=force_mock,
        notify=notify,
        limit=limit,
        dry_run=dry_run,
        app_token=app_token,
        table_id=table_id,
        include_synced=include_synced,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1



def main(argv: list[str] | None = None) -> int:
    _load_env_local()
    argv_list = list(argv) if argv is not None else sys.argv[1:]



    # Dedicated: feishu-bitable-sync — poll/sync bitable records → VisualTask
    if argv_list and argv_list[0] == "feishu-bitable-sync":
        p = argparse.ArgumentParser(
            prog="evaw.cli feishu-bitable-sync",
            description=(
                "Sync Feishu 多维表格 new records → EVAW VisualTask. "
                "Uses FEISHU_APP_ID/SECRET + FEISHU_BITABLE_APP_TOKEN/TABLE_ID "
                "(defaults to live EVAW 提需 base). Dedupes by record_id. "
                "Default mock (no IM); --live-notify for group chat."
            ),
        )
        p.add_argument("--artifacts-dir", default="artifacts")
        p.add_argument(
            "--app-token",
            default=None,
            help="Bitable app_token (default: env or live EVAW base)",
        )
        p.add_argument(
            "--table-id",
            default=None,
            help="Bitable table_id (default: env or live EVAW table)",
        )
        p.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only process the last N unsynced filled records",
        )
        p.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse briefs only; do not create tasks or update state",
        )
        p.add_argument(
            "--include-synced",
            action="store_true",
            help="Re-process records already in sync state (creates new tasks)",
        )
        p.add_argument(
            "--poll",
            action="store_true",
            help="Keep polling (blocking loop)",
        )
        p.add_argument(
            "--interval",
            type=float,
            default=60.0,
            help="Poll interval seconds (default 60)",
        )
        p.add_argument(
            "--live-notify",
            action="store_true",
            help="Allow live Feishu IM on intake (default: mock only)",
        )
        a = p.parse_args(argv_list[1:])
        return run_feishu_bitable_sync(
            artifacts_dir=a.artifacts_dir,
            force_mock=not a.live_notify,
            notify=a.live_notify,
            limit=a.limit,
            dry_run=a.dry_run,
            poll=a.poll,
            interval=a.interval,
            app_token=a.app_token,
            table_id=a.table_id,
            include_synced=a.include_synced,
        )


    # Dedicated: feishu-intake-from-json — webhook/bitable payload → task
    if argv_list and argv_list[0] == "feishu-intake-from-json":
        p = argparse.ArgumentParser(
            prog="evaw.cli feishu-intake-from-json",
            description=(
                "Parse Feishu form/bitable/bot webhook JSON → create VisualTask. "
                "Default --feishu-mock (no live IM)."
            ),
        )
        p.add_argument("--file", "-f", required=True, help="JSON payload path")
        p.add_argument("--artifacts-dir", default="artifacts")
        p.add_argument(
            "--feishu-mock",
            action="store_true",
            default=True,
            help="Force mock adapter (default True)",
        )
        p.add_argument(
            "--live-notify",
            action="store_true",
            help="Allow live Feishu adapter + IM notify (off by default)",
        )
        a = p.parse_args(argv_list[1:])
        return run_feishu_intake_from_json(
            file_path=a.file,
            artifacts_dir=a.artifacts_dir,
            force_mock=not a.live_notify,
            notify=a.live_notify,
        )

    # Dedicated: feishu-intake-webhook — local HTTP stub
    if argv_list and argv_list[0] == "feishu-intake-webhook":
        p = argparse.ArgumentParser(
            prog="evaw.cli feishu-intake-webhook",
            description="Local HTTP stub: POST /feishu/intake → VisualTask",
        )
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=8787)
        p.add_argument("--artifacts-dir", default="artifacts")
        p.add_argument(
            "--live-notify",
            action="store_true",
            help="Allow live Feishu IM on intake (default: mock only)",
        )
        a = p.parse_args(argv_list[1:])
        return run_feishu_intake_webhook(
            host=a.host,
            port=a.port,
            artifacts_dir=a.artifacts_dir,
            force_mock=not a.live_notify,
            notify=a.live_notify,
        )

    # Dedicated: feishu-bitable-setup — create/document 提需多维表格
    if argv_list and argv_list[0] == "feishu-bitable-setup":
        p = argparse.ArgumentParser(
            prog="evaw.cli feishu-bitable-setup",
            description=(
                "Create Feishu bitable + fields if API allows; always write field map. "
                "Does not send IM."
            ),
        )
        p.add_argument("--name", default="EVAW 提需", help="Base app name")
        a = p.parse_args(argv_list[1:])
        return run_feishu_bitable_setup(name=a.name)

    # Dedicated subcommand: feishu-intake --brand ... --sku ... (form simulate)
    if argv_list and argv_list[0] == "feishu-intake":
        p = argparse.ArgumentParser(
            prog="evaw.cli feishu-intake",
            description=(
                "Simulate Feishu form/card brief submit → create VisualTask → notify. "
                "Formal product uses Feishu questionnaire / bot with the same fields."
            ),
        )
        p.add_argument("--brand", required=True, help="brand_id (品牌)")
        p.add_argument("--sku", required=True, help="sku_id (SKU)")
        p.add_argument(
            "--platform",
            default="tmall",
            choices=["tmall", "jd", "amazon", "dtc"],
            help="平台 (default: tmall)",
        )
        p.add_argument(
            "--asset-type",
            default="hero",
            choices=["hero", "sku", "pdp_module"],
            help="图型 (default: hero)",
        )
        p.add_argument(
            "--selling-points",
            default="稳固承重,快速折叠",
            help="卖点，逗号分隔 (default: 稳固承重,快速折叠)",
        )
        p.add_argument("--size", default="800x800", help="尺寸规格 (default: 800x800)")
        p.add_argument(
            "--deadline",
            default=None,
            help="Deadline ISO date/datetime; default = now+7d",
        )
        p.add_argument(
            "--new-product",
            action="store_true",
            help="是否新品（是 → 后续强制人审）",
        )
        p.add_argument(
            "--risk-flags",
            default="",
            help="风险标记，逗号分隔（如 structure_sensitive）",
        )
        p.add_argument("--requester", default="ops_feishu_form", help="提需人 id")
        p.add_argument("--artifacts-dir", default="artifacts")
        p.add_argument(
            "--feishu-mock",
            action="store_true",
            help="Force Feishu mock adapter (do not send live IM)",
        )
        a = p.parse_args(argv_list[1:])
        points = [s.strip() for s in a.selling_points.split(",") if s.strip()]
        flags = [s.strip() for s in a.risk_flags.split(",") if s.strip()]
        return run_feishu_intake(
            brand=a.brand,
            sku=a.sku,
            platform=a.platform,
            asset_type=a.asset_type,
            selling_points=points,
            size_spec=a.size,
            deadline=a.deadline,
            is_new_product=a.new_product,
            risk_flags=flags,
            requester=a.requester,
            artifacts_dir=a.artifacts_dir,
            force_mock=a.feishu_mock,
        )

    # Dedicated subcommand: hitl-apply --task ... --decision ...
    if argv_list and argv_list[0] == "hitl-apply":
        p = argparse.ArgumentParser(
            prog="evaw.cli hitl-apply",
            description="Apply Lead approve/reject on a PendingReview task",
        )
        p.add_argument("--task", required=True, help="task_id from hitl-chat-demo")
        p.add_argument(
            "--decision",
            required=True,
            choices=["approve", "reject"],
            help="approve | reject",
        )
        p.add_argument(
            "--reason",
            default="FIDELITY_STRUCTURE",
            help="ReasonCode when rejecting (default: FIDELITY_STRUCTURE)",
        )
        p.add_argument("--artifacts-dir", default="artifacts")
        p.add_argument(
            "--feishu-mock",
            action="store_true",
            help="Force Feishu mock adapter",
        )
        a = p.parse_args(argv_list[1:])
        return run_hitl_apply(
            task_id=a.task,
            decision=a.decision,
            reason=a.reason,
            artifacts_dir=a.artifacts_dir,
            force_mock=a.feishu_mock,
        )

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
        help="Which path to run (default: all). qa-live-demo / evalset-v0 = Live QA rules.",
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
