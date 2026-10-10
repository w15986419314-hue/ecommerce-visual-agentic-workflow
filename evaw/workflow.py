"""Orchestrator: wires Input → Agents → Knowledge → HITL → Delivery."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .agents import AssetGenerationAgent, BriefStrategyAgent, VisualQAAgent
from .hitl import DEFAULT_AUDIT_SAMPLE_RATE, HitlDecision, evaluate_after_qa
from .knowledge import assert_may_generate, bind_knowledge, issue_exemption
from .schema import (
    STRUCTURE_SENSITIVE,
    DeliveryPackage,
    KnowledgeStatusEnum,
    OperationsInput,
    QAOverall,
    ReasonCode,
    ReviewDecision,
    ReviewDecisionEnum,
    TaskStatus,
    VisualTask,
    new_id,
    utcnow,
)
from .state_machine import IllegalTransition, transition


@dataclass
class WorkflowConfig:
    audit_sample_rate: float = DEFAULT_AUDIT_SAMPLE_RATE
    candidate_count: int = 3
    qa_fail_limit: int = 3
    rng_seed: Optional[int] = None
    gen_mode: str = "stub"  # stub | live
    qa_mode: str = "stub"  # stub | live (live → rules ± multimodal)
    artifacts_dir: str = "artifacts"


@dataclass
class RunLog:
    lines: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.lines.append(msg)

    def dump(self) -> str:
        return "\n".join(self.lines)

    def status_trace(self, task: VisualTask) -> str:
        parts = [f"{h.from_status.value}→{h.to_status.value}" for h in task.history]
        return " → ".join(parts) if parts else "(no transitions)"


class WorkflowEngine:
    def __init__(self, config: Optional[WorkflowConfig] = None):
        self.config = config or WorkflowConfig()
        self.brief_agent = BriefStrategyAgent()
        self.gen_agent = AssetGenerationAgent(
            self.config.candidate_count,
            gen_mode=self.config.gen_mode,  # type: ignore[arg-type]
            artifacts_dir=self.config.artifacts_dir,
        )
        self.qa_agent = VisualQAAgent(
            qa_mode=self.config.qa_mode,  # type: ignore[arg-type]
            artifacts_dir=self.config.artifacts_dir,
        )
        self.rng = random.Random(self.config.rng_seed)

    def create_task(self, ops: OperationsInput, log: RunLog) -> VisualTask:
        task = VisualTask(
            task_id=new_id("task"),
            status=TaskStatus.DRAFT,
            brand_id=ops.brand_id,
            sku_id=ops.sku_id,
            platform=ops.platform,
            asset_type=ops.asset_type,
            deadline=ops.deadline,
            is_new_product=ops.is_new_product,
            risk_flags=list(ops.risk_flags),
            knowledge_status=KnowledgeStatusEnum.MISSING,
            created_by=ops.created_by,
        )
        log.add(f"[create] task_id={task.task_id} status={task.status.value}")
        self._require_ops(ops)
        transition(task, TaskStatus.READY_FOR_STRATEGY, "ops_fields_valid")
        log.add(f"[transition] → {task.status.value} (ops_fields_valid)")
        return task

    @staticmethod
    def _require_ops(ops: OperationsInput) -> None:
        if not ops.brand_id or not ops.sku_id:
            raise ValueError("brand_id and sku_id required")
        if not ops.selling_points:
            raise ValueError("selling_points required")
        if ops.deadline is None:
            raise ValueError("deadline required")

    def run_strategy(self, task: VisualTask, ops: OperationsInput, log: RunLog) -> None:
        brief, strategy = self.brief_agent.run(task, ops)
        task.brief = brief
        task.strategy = strategy
        task.current_strategy_id = strategy.strategy_id
        for f in strategy.risk_flags:
            if f not in task.risk_flags:
                task.risk_flags.append(f)
        transition(task, TaskStatus.STRATEGIZED, "brief_strategy_agent_ok")
        log.add(
            f"[agent:{self.brief_agent.name}] brief={brief.brief_id} "
            f"strategy={strategy.strategy_id} v={strategy.version}"
        )
        log.add(f"[transition] → {task.status.value}")

    def bind_and_gate_knowledge(self, task: VisualTask, log: RunLog) -> bool:
        result = bind_knowledge(task)
        task.knowledge = result.knowledge
        task.knowledge_status = result.knowledge.status

        if result.knowledge.status == KnowledgeStatusEnum.READY:
            transition(task, TaskStatus.KNOWLEDGE_READY, "knowledge_ready")
            log.add(
                f"[knowledge] status=ready snapshot={result.knowledge.snapshot_id}"
            )
            log.add(f"[transition] → {task.status.value}")
            return True

        if result.knowledge.status == KnowledgeStatusEnum.EXEMPTED:
            transition(task, TaskStatus.KNOWLEDGE_READY, "knowledge_exempted")
            log.add(
                f"[knowledge] status=exempted ticket={result.knowledge.exemption_ticket_id}"
            )
            log.add(f"[transition] → {task.status.value}")
            return True

        transition(task, TaskStatus.KNOWLEDGE_PENDING, "knowledge_not_ready")
        task.block_reason = result.block_message
        log.add(f"[knowledge] BLOCKED: {result.block_message}")
        log.add(f"[transition] → {task.status.value}")
        return False

    def apply_exemption_and_ready(
        self, task: VisualTask, log: RunLog, notes: str = "Urgent campaign"
    ) -> None:
        if task.status != TaskStatus.KNOWLEDGE_PENDING:
            raise RuntimeError("Exemption only from KnowledgePending")
        ticket = issue_exemption(task, notes=notes)
        if task.knowledge:
            task.knowledge.status = KnowledgeStatusEnum.EXEMPTED
            task.knowledge.exemption_ticket_id = ticket.ticket_id
            task.knowledge.snapshot_id = (
                task.knowledge.snapshot_id or new_id("ksnap_exempt")
            )
        transition(task, TaskStatus.KNOWLEDGE_READY, "lead_exemption_issued")
        log.add(
            f"[exemption] ticket={ticket.ticket_id} reason={ticket.reason_code.value}"
        )
        log.add(f"[transition] → {task.status.value}")

    def run_generation(
        self, task: VisualTask, log: RunLog, *, force_fail: bool = False
    ) -> bool:
        assert_may_generate(task)
        transition(task, TaskStatus.GENERATING, "start_generation")
        log.add(f"[transition] → {task.status.value}")

        log.add(f"[gen] {self.gen_agent.provider_summary()}")
        result = self.gen_agent.run(task, force_fail=force_fail)
        task.generation = result
        task.current_generation_result_id = result.generation_result_id

        if result.status.value == "failed":
            transition(task, TaskStatus.GENERATION_FAILED, "generation_failed")
            log.add(
                f"[agent:{self.gen_agent.name}] FAILED code={result.error_code} "
                f"msg={result.error_message}"
            )
            log.add(f"[transition] → {task.status.value}")
            return False

        transition(task, TaskStatus.QA_PENDING, "generation_succeeded")
        asset_uris = [a.uri for a in result.assets[:4]]
        log.add(
            f"[agent:{self.gen_agent.name}] status={result.status.value} "
            f"candidates={result.candidate_count} "
            f"snapshot={result.knowledge_snapshot_id} "
            f"strategy_version={result.strategy_version}"
        )
        for u in asset_uris:
            log.add(f"[gen:asset] {u}")
        log.add(f"[transition] → {task.status.value}")
        return True

    def run_qa(
        self,
        task: VisualTask,
        log: RunLog,
        *,
        overall: Optional[QAOverall] = None,
        fixture: Optional[str] = None,
    ) -> HitlDecision:
        if not task.generation:
            raise RuntimeError("No generation result")

        log.add(f"[qa] {self.qa_agent.provider_summary()}")
        # Stub defaults inject PASS when overall omitted; live uses engine result.
        inject = overall
        if self.config.qa_mode == "stub" and inject is None:
            inject = QAOverall.PASS

        report = self.qa_agent.run(
            task, task.generation, overall=inject, fixture=fixture
        )
        task.qa = report
        task.current_qa_id = report.qa_id
        overall_result = report.overall

        dim_summary = ", ".join(
            f"{k}={v.status.value}" for k, v in report.dimensions.items()
        )
        rc = report.reason_code.value if report.reason_code else None
        log.add(
            f"[agent:{self.qa_agent.name}] overall={overall_result.value} "
            f"engine={report.engine} reason_code={rc} "
            f"primary={report.primary_dimension} dims=[{dim_summary}]"
        )
        if self.qa_agent.last_provider_meta:
            meta = self.qa_agent.last_provider_meta
            if meta.get("report_path"):
                log.add(f"[qa:report] {meta['report_path']}")
            if meta.get("multimodal_applied"):
                log.add("[qa:multimodal] external_api=true applied")
            elif meta.get("multimodal_attempted"):
                log.add(
                    f"[qa:multimodal] attempted but fallback "
                    f"err={meta.get('multimodal_error') or meta.get('multimodal_skip')}"
                )

        if overall_result == QAOverall.FAIL:
            task.qa_fail_count += 1
            transition(task, TaskStatus.QA_FAILED, "qa_fail")
            log.add(
                f"[agent:{self.qa_agent.name}] FAIL "
                f"fail_count={task.qa_fail_count} fixes={report.suggested_fixes}"
            )
            log.add(f"[transition] → {task.status.value}")
            return evaluate_after_qa(task, overall_result, audit_sample_rate=0)

        if overall_result == QAOverall.PASS_WITH_RISK:
            transition(task, TaskStatus.QA_PASSED_WITH_RISK, "qa_pass_with_risk")
        else:
            transition(task, TaskStatus.QA_PASSED, "qa_pass")

        log.add(f"[transition] → {task.status.value}")

        decision = evaluate_after_qa(
            task,
            overall_result,
            audit_sample_rate=self.config.audit_sample_rate,
            rng=self.rng,
        )
        log.add(
            f"[hitl] force={decision.force_pending_review} "
            f"auto_eligible={decision.auto_approve_eligible} "
            f"audit_sampled={decision.audit_sampled} "
            f"reasons={decision.reasons} → {decision.next_hint}"
        )
        return decision

    def apply_hitl_gate(
        self, task: VisualTask, decision: HitlDecision, log: RunLog
    ) -> None:
        if decision.next_hint == "PendingReview":
            task.audit_sampled = decision.audit_sampled
            transition(
                task,
                TaskStatus.PENDING_REVIEW,
                "hitl_pending_review",
                meta={
                    "reasons": decision.reasons,
                    "audit_sampled": decision.audit_sampled,
                },
            )
            log.add(
                f"[transition] → {task.status.value} "
                f"(reasons={decision.reasons}, audit_sampled={decision.audit_sampled})"
            )
            return

        if decision.next_hint == "Approved":
            task.auto_approved = True
            transition(
                task,
                TaskStatus.APPROVED,
                "low_risk_auto_approve",
                meta={"reasons": decision.reasons},
            )
            log.add(f"[transition] → {task.status.value} (auto_approved=true)")
            return

        raise RuntimeError(f"Unexpected HITL hint: {decision.next_hint}")

    def lead_approve(
        self,
        task: VisualTask,
        log: RunLog,
        *,
        accept_risk: bool = False,
        notes: str = "Lead approved",
    ) -> None:
        if task.status != TaskStatus.PENDING_REVIEW:
            raise RuntimeError("Lead approve only from PendingReview")
        review = ReviewDecision(
            review_id=new_id("rev"),
            task_id=task.task_id,
            reviewer_id="visual_lead",
            decision=ReviewDecisionEnum.APPROVED,
            accept_risk=accept_risk,
            notes=notes,
            created_at=utcnow(),
        )
        task.review = review
        transition(task, TaskStatus.APPROVED, "lead_approved")
        log.add(
            f"[hitl:lead] approved review={review.review_id} accept_risk={accept_risk}"
        )
        log.add(f"[transition] → {task.status.value}")

    def lead_reject(
        self,
        task: VisualTask,
        log: RunLog,
        *,
        reason_code: ReasonCode = ReasonCode.FIDELITY_STRUCTURE,
        notes: str = "Reject for structure",
    ) -> None:
        if task.status != TaskStatus.PENDING_REVIEW:
            raise RuntimeError("Lead reject only from PendingReview")
        review = ReviewDecision(
            review_id=new_id("rev"),
            task_id=task.task_id,
            reviewer_id="visual_lead",
            decision=ReviewDecisionEnum.REJECTED,
            reason_code=reason_code,
            notes=notes,
            created_at=utcnow(),
        )
        task.review = review
        transition(
            task,
            TaskStatus.REJECTED,
            "lead_rejected",
            meta={"reason_code": reason_code.value},
        )
        log.add(f"[hitl:lead] rejected reason={reason_code.value}")
        log.add(f"[transition] → {task.status.value}")

    def deliver(self, task: VisualTask, log: RunLog) -> None:
        if task.status != TaskStatus.APPROVED:
            raise PermissionError("No Approved → cannot Delivered (hard gate)")
        assets = []
        if task.generation:
            assets = [a.asset_id for a in task.generation.assets]
        notes = ""
        if task.review:
            notes = task.review.notes
        elif task.auto_approved:
            notes = "auto_approved"
        pkg = DeliveryPackage(
            delivery_id=new_id("deliv"),
            task_id=task.task_id,
            asset_ids=assets,
            platform=task.platform,
            review_notes=notes,
        )
        task.delivery = pkg
        transition(task, TaskStatus.DELIVERED, "delivery_archived")
        log.add(f"[delivery] package={pkg.delivery_id} assets={len(assets)}")
        log.add(f"[transition] → {task.status.value}")

    # ------------------------------------------------------------------
    # Scenarios
    # ------------------------------------------------------------------

    def scenario_happy_path(
        self, ops: OperationsInput
    ) -> tuple[VisualTask, RunLog]:
        """Low-risk Pass → auto Approved (audit rate=0 for stable demo) → Delivered."""
        self.config.audit_sample_rate = 0.0
        self.rng = random.Random(0)
        log = RunLog()
        log.add(
            "=== SCENARIO: happy_path "
            "(low-risk Pass → auto Approve → Delivered) ==="
        )
        task = self.create_task(ops, log)
        self.run_strategy(task, ops, log)
        if not self.bind_and_gate_knowledge(task, log):
            log.add("[abort] knowledge blocked unexpected in happy path")
            return task, log
        if not self.run_generation(task, log):
            return task, log
        decision = self.run_qa(task, log, overall=QAOverall.PASS)
        self.apply_hitl_gate(task, decision, log)
        if task.status == TaskStatus.PENDING_REVIEW:
            self.lead_approve(task, log, notes="Audit maintain approve")
        self.deliver(task, log)
        log.add(
            f"=== DONE status={task.status.value} "
            f"auto_approved={task.auto_approved} ==="
        )
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log

    def scenario_knowledge_block(
        self, ops: OperationsInput
    ) -> tuple[VisualTask, RunLog]:
        """Knowledge != ready → block Live Generation at KnowledgePending."""
        log = RunLog()
        log.add(
            "=== SCENARIO: knowledge_block "
            "(missing → block Live Gen) ==="
        )
        task = self.create_task(ops, log)
        self.run_strategy(task, ops, log)
        allowed = self.bind_and_gate_knowledge(task, log)
        if allowed:
            log.add("[unexpected] knowledge allowed; demo misconfigured")
        else:
            log.add(
                "[gate] Live Generation NOT started "
                f"(status={task.status.value})"
            )
            try:
                assert_may_generate(task)
                log.add("[unexpected] assert_may_generate did not raise")
            except PermissionError as e:
                log.add(f"[assert] PermissionError as expected: {e}")
        log.add(
            f"=== DONE status={task.status.value} "
            "(blocked, no Generating) ==="
        )
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log

    def scenario_high_risk_hitl(
        self,
        ops: OperationsInput,
        *,
        qa_overall: QAOverall = QAOverall.PASS_WITH_RISK,
    ) -> tuple[VisualTask, RunLog]:
        """High risk → PendingReview → Lead Approve → Delivered."""
        log = RunLog()
        log.add(
            "=== SCENARIO: high_risk_hitl "
            f"(qa={qa_overall.value} → PendingReview → Lead → Delivered) ==="
        )
        task = self.create_task(ops, log)
        self.run_strategy(task, ops, log)
        if not self.bind_and_gate_knowledge(task, log):
            log.add("[abort] knowledge blocked")
            return task, log
        if not self.run_generation(task, log):
            return task, log

        decision = self.run_qa(task, log, overall=qa_overall)
        self.apply_hitl_gate(task, decision, log)

        if task.status != TaskStatus.PENDING_REVIEW:
            log.add(
                f"[unexpected] expected PendingReview, got {task.status.value}"
            )
            log.add(f"[trace] {log.status_trace(task)}")
            return task, log

        accept = qa_overall == QAOverall.PASS_WITH_RISK
        self.lead_approve(
            task,
            log,
            accept_risk=accept,
            notes=(
                "Lead accepts residual structure risk"
                if accept
                else "Lead approved high-risk Pass"
            ),
        )
        self.deliver(task, log)
        log.add(
            f"=== DONE status={task.status.value} "
            f"auto_approved={task.auto_approved} forced_hitl=true ==="
        )
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log

    def scenario_live_happy(
        self, ops: OperationsInput
    ) -> tuple[VisualTask, RunLog]:
        """Same as happy_path but forces live generation provider path."""
        # Ensure live mode on this engine's gen agent

        self.config.gen_mode = "live"
        self.gen_agent = AssetGenerationAgent(
            self.config.candidate_count,
            gen_mode="live",
            artifacts_dir=self.config.artifacts_dir,
        )
        self.config.audit_sample_rate = 0.0
        self.rng = random.Random(0)
        log = RunLog()
        log.add(
            "=== SCENARIO: live_happy "
            "(Knowledge ready → Live Gen → low-risk Pass → auto Approve → Delivered) ==="
        )
        log.add(f"[gen] {self.gen_agent.provider_summary()}")
        task = self.create_task(ops, log)
        self.run_strategy(task, ops, log)
        if not self.bind_and_gate_knowledge(task, log):
            log.add("[abort] knowledge blocked unexpected in live happy path")
            return task, log
        if not self.run_generation(task, log):
            return task, log
        decision = self.run_qa(task, log, overall=QAOverall.PASS)
        self.apply_hitl_gate(task, decision, log)
        if task.status == TaskStatus.PENDING_REVIEW:
            self.lead_approve(task, log, notes="Audit maintain approve")
        self.deliver(task, log)
        log.add(
            f"=== DONE status={task.status.value} "
            f"auto_approved={task.auto_approved} "
            f"gen_mode=live provider={self.gen_agent.provider.name} ==="
        )
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log

    def scenario_live_knowledge_block(
        self, ops: OperationsInput
    ) -> tuple[VisualTask, RunLog]:
        """Prove live mode cannot bypass Knowledge gate."""
        self.config.gen_mode = "live"
        self.gen_agent = AssetGenerationAgent(
            self.config.candidate_count,
            gen_mode="live",
            artifacts_dir=self.config.artifacts_dir,
        )
        log = RunLog()
        log.add(
            "=== SCENARIO: live_knowledge_block "
            "(live mode still blocked when Knowledge != ready) ==="
        )
        log.add(f"[gen] {self.gen_agent.provider_summary()}")
        task = self.create_task(ops, log)
        self.run_strategy(task, ops, log)
        allowed = self.bind_and_gate_knowledge(task, log)
        if allowed:
            log.add("[unexpected] knowledge allowed; demo misconfigured")
        else:
            log.add(
                "[gate] Live Generation NOT started even in live mode "
                f"(status={task.status.value})"
            )
            try:
                assert_may_generate(task)
                log.add("[unexpected] assert_may_generate did not raise")
            except PermissionError as e:
                log.add(f"[assert] PermissionError as expected: {e}")
            # Also attempt agent.run directly — must raise
            try:
                self.gen_agent.run(task)
                log.add("[unexpected] gen_agent.run did not raise under live")
            except PermissionError as e:
                log.add(f"[assert:live] gen_agent.run blocked: {e}")
        log.add(
            f"=== DONE status={task.status.value} "
            "(blocked under live mode, no Generating) ==="
        )
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log




    def scenario_qa_live_demo(self) -> list[tuple[str, VisualTask, RunLog]]:
        """Live QA rules demo: Pass / PassWithRisk / Fail (no multimodal required).

        Uses stub generation + live QA rules for speed and reproducibility.
        HITL: PassWithRisk → PendingReview; Fail → QAFailed (no auto approve).
        """
        from datetime import datetime, timedelta, timezone

        from .schema import AssetType, Platform

        # Force live QA; keep Gen on current provider (CLI may set stub for reproducibility)
        self.config.qa_mode = "live"
        self.qa_agent = VisualQAAgent(
            qa_mode="live",
            artifacts_dir=self.config.artifacts_dir,
        )
        # Prefer stub gen in this demo so mobile rules are not tied to placeholder PNG size
        self.config.gen_mode = "stub"
        self.gen_agent = AssetGenerationAgent(
            self.config.candidate_count,
            gen_mode="stub",
            artifacts_dir=self.config.artifacts_dir,
        )
        self.config.audit_sample_rate = 0.0
        self.rng = random.Random(0)

        deadline = datetime.now(timezone.utc) + timedelta(days=7)
        cases: list[tuple[str, OperationsInput, Optional[str], str]] = [
            (
                "pass",
                OperationsInput(
                    brand_id="brand_xiu",
                    sku_id="SKU-BED-001",
                    platform=Platform.TMALL,
                    asset_type=AssetType.HERO,
                    selling_points=["稳固承重", "快速折叠", "客房场景"],
                    size_spec="800x800",
                    deadline=deadline,
                    is_new_product=False,
                    risk_flags=[],
                    created_by="ops_qa_live",
                ),
                None,
                "Delivered",
            ),
            (
                "pass_with_risk",
                OperationsInput(
                    brand_id="brand_xiu",
                    sku_id="SKU-BED-STRUCT",
                    platform=Platform.JD,
                    asset_type=AssetType.HERO,
                    selling_points=["结构真实", "侧板完整", "客房场景"],
                    size_spec="800x800",
                    deadline=deadline,
                    is_new_product=False,
                    # structure_sensitive → rules Risk on fidelity → PassWithRisk → HITL
                    risk_flags=[STRUCTURE_SENSITIVE],
                    created_by="ops_qa_live",
                ),
                None,
                "Delivered",
            ),
            (
                "fail",
                OperationsInput(
                    brand_id="brand_xiu",
                    sku_id="SKU-BED-001",
                    platform=Platform.TMALL,
                    asset_type=AssetType.HERO,
                    selling_points=["稳固承重", "快速折叠"],
                    size_spec="800x800",
                    deadline=deadline,
                    is_new_product=False,
                    risk_flags=["qa_fixture:fail_text"],
                    created_by="ops_qa_live",
                ),
                "fail_text",
                "QAFailed",
            ),
        ]

        results: list[tuple[str, VisualTask, RunLog]] = []
        for name, ops, fixture, expected in cases:
            log = RunLog()
            log.add(
                f"=== SCENARIO: qa_live_demo/{name} "
                f"(live rules → expect {expected}) ==="
            )
            log.add(f"[qa] {self.qa_agent.provider_summary()}")
            task = self.create_task(ops, log)
            self.run_strategy(task, ops, log)
            if not self.bind_and_gate_knowledge(task, log):
                log.add("[abort] knowledge blocked")
                results.append((name, task, log))
                continue
            if not self.run_generation(task, log):
                results.append((name, task, log))
                continue

            decision = self.run_qa(task, log, fixture=fixture)
            if task.status == TaskStatus.QA_FAILED:
                log.add(
                    f"=== DONE status={task.status.value} "
                    f"(Fail path; no auto-approve) "
                    f"reason_code="
                    f"{task.qa.reason_code.value if task.qa and task.qa.reason_code else None} ==="
                )
                log.add(f"[trace] {log.status_trace(task)}")
                results.append((name, task, log))
                continue

            self.apply_hitl_gate(task, decision, log)
            if task.status == TaskStatus.PENDING_REVIEW:
                accept = (
                    task.qa is not None
                    and task.qa.overall == QAOverall.PASS_WITH_RISK
                )
                self.lead_approve(
                    task,
                    log,
                    accept_risk=accept,
                    notes="Lead approve after live QA risk" if accept else "Lead approve",
                )
            if task.status == TaskStatus.APPROVED:
                self.deliver(task, log)
            log.add(
                f"=== DONE status={task.status.value} "
                f"auto_approved={task.auto_approved} "
                f"qa_overall={task.qa.overall.value if task.qa else None} "
                f"engine={task.qa.engine if task.qa else None} ==="
            )
            log.add(f"[trace] {log.status_trace(task)}")
            results.append((name, task, log))
        return results


# --- Feishu-aware scenario (imported lazily to keep core free of Feishu) ---

def _feishu_notify(engine: "WorkflowEngine", task, log: RunLog, *, prev, note: str = "", extra=None):
    adapter = getattr(engine, "feishu", None)
    if adapter is None:
        return
    nr = adapter.notify_status(task, previous_status=prev, note=note, extra=extra or {})
    log.add(
        f"[feishu:notify] channel={nr.channel} ok={nr.ok} "
        f"msg={nr.message_id} detail={nr.detail}"
    )


def attach_feishu(engine: "WorkflowEngine", adapter) -> "WorkflowEngine":
    engine.feishu = adapter
    return engine


def scenario_feishu_demo(
    engine: "WorkflowEngine",
    *,
    feishu=None,
) -> tuple:
    """提需 → VisualTask → 状态通知 → 高风险审批跳转 (D3).

    Uses high-risk ops so HITL forces PendingReview and approval_link is emitted.
    Knowledge gate unchanged.
    """
    from datetime import datetime, timedelta, timezone

    from .feishu import (
        FeishuBriefPayload,
        describe_feishu_adapter,
        resolve_feishu_adapter,
    )
    from .schema import STRUCTURE_SENSITIVE, QAOverall, TaskStatus

    adapter = feishu or resolve_feishu_adapter()
    engine.feishu = adapter
    engine.config.audit_sample_rate = 0.0
    engine.rng = random.Random(0)

    log = RunLog()
    log.add("=== SCENARIO: feishu_demo (D3 提需+通知+审批跳转) ===")
    log.add(f"[feishu] {describe_feishu_adapter(adapter)}")

    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    brief = FeishuBriefPayload(
        brand_id="brand_xiu",
        sku_id="SKU-BED-STRUCT",
        platform="jd",
        asset_type="hero",
        selling_points=["结构真实", "侧板完整", "客房场景"],
        size_spec="800x800",
        deadline_iso=deadline,
        is_new_product=True,
        risk_flags=[STRUCTURE_SENSITIVE],
        requester_id="ops_feishu_demo",
        source_message_id="mock_src_msg_feishu_demo",
        chat_id=None,
    )

    ref = adapter.create_task_from_brief(brief)
    log.add(
        f"[feishu:create_task_from_brief] intake={ref.intake_id} "
        f"adapter={ref.adapter} path={ref.mock_path} "
        f"external_ref={ref.external_ref}"
    )

    ops = ref.ops
    task = engine.create_task(ops, log)
    adapter.bind_task_id(ref, task.task_id)
    log.add(f"[feishu] bound intake={ref.intake_id} → task_id={task.task_id}")
    _feishu_notify(
        engine,
        task,
        log,
        prev=None,
        note="提需已建 VisualTask",
        extra={"intake_id": ref.intake_id},
    )

    prev = task.status
    engine.run_strategy(task, ops, log)
    _feishu_notify(engine, task, log, prev=prev, note="Brief & Strategy 完成")

    prev = task.status
    if not engine.bind_and_gate_knowledge(task, log):
        _feishu_notify(
            engine, task, log, prev=prev, note="Knowledge 阻断，未进入生成"
        )
        link = adapter.approval_link(task)
        log.add(
            f"[feishu:approval_link] (knowledge pending) url={link.url} "
            f"console={link.console} {link.detail}"
        )
        log.add(f"=== DONE status={task.status.value} (knowledge blocked) ===")
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log, ref

    _feishu_notify(engine, task, log, prev=prev, note="Knowledge ready")

    prev = task.status
    if not engine.run_generation(task, log):
        _feishu_notify(engine, task, log, prev=prev, note="Generation failed")
        log.add(f"=== DONE status={task.status.value} ===")
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log, ref
    _feishu_notify(engine, task, log, prev=prev, note="Generation → QA")

    prev = task.status
    decision = engine.run_qa(task, log, overall=QAOverall.PASS_WITH_RISK)
    _feishu_notify(
        engine,
        task,
        log,
        prev=prev,
        note=f"QA {QAOverall.PASS_WITH_RISK.value}",
        extra={"hitl_reasons": decision.reasons},
    )

    prev = task.status
    engine.apply_hitl_gate(task, decision, log)
    _feishu_notify(
        engine,
        task,
        log,
        prev=prev,
        note="HITL → PendingReview（新品+structure_sensitive+PassWithRisk）",
    )

    if task.status != TaskStatus.PENDING_REVIEW:
        log.add(f"[unexpected] expected PendingReview, got {task.status.value}")
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log, ref

    link = adapter.approval_link(task)
    log.add(
        f"[feishu:approval_link] url={link.url} console={link.console} "
        f"detail={link.detail}"
    )
    _feishu_notify(
        engine,
        task,
        log,
        prev=TaskStatus.PENDING_REVIEW,
        note=f"请 Lead 审批: {link.url}（细打回走控制台）",
        extra={"approval_url": link.url},
    )

    prev = task.status
    engine.lead_approve(
        task,
        log,
        accept_risk=True,
        notes="Lead accepts residual structure risk (via console)",
    )
    _feishu_notify(engine, task, log, prev=prev, note="Lead Approved")

    prev = task.status
    engine.deliver(task, log)
    _feishu_notify(engine, task, log, prev=prev, note="Delivered")

    log.add(
        f"=== DONE status={task.status.value} auto_approved={task.auto_approved} "
        f"approval_url={link.url} feishu={adapter.name} ==="
    )
    log.add(f"[trace] {log.status_trace(task)}")
    return task, log, ref


def scenario_hitl_chat_demo(
    engine: "WorkflowEngine",
    *,
    feishu=None,
    hitl_dir: str = "artifacts/hitl_pending",
) -> tuple:
    """High-risk path → PendingReview; Feishu chat instructions; NO auto-approve.

    Cici / Lead applies decision later via:
      python3 -m evaw.cli hitl-apply --task <id> --decision approve|reject
    """
    from datetime import datetime, timedelta, timezone

    from .feishu import (
        FeishuBriefPayload,
        describe_feishu_adapter,
        resolve_feishu_adapter,
    )
    from .schema import STRUCTURE_SENSITIVE, QAOverall, TaskStatus
    from .task_store import save_task

    adapter = feishu or resolve_feishu_adapter()
    engine.feishu = adapter
    engine.config.audit_sample_rate = 0.0
    engine.rng = random.Random(0)

    log = RunLog()
    log.add("=== SCENARIO: hitl_chat_demo (停在 PendingReview，等人审) ===")
    log.add(f"[feishu] {describe_feishu_adapter(adapter)}")

    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    brief = FeishuBriefPayload(
        brand_id="brand_xiu",
        sku_id="SKU-BED-STRUCT",
        platform="jd",
        asset_type="hero",
        selling_points=["结构真实", "侧板完整", "客房场景"],
        size_spec="800x800",
        deadline_iso=deadline,
        is_new_product=True,
        risk_flags=[STRUCTURE_SENSITIVE],
        requester_id="ops_hitl_chat",
        source_message_id="mock_src_hitl_chat",
        chat_id=None,
    )

    ref = adapter.create_task_from_brief(brief)
    log.add(
        f"[feishu:create_task_from_brief] intake={ref.intake_id} "
        f"adapter={ref.adapter} path={ref.mock_path}"
    )

    ops = ref.ops
    task = engine.create_task(ops, log)
    adapter.bind_task_id(ref, task.task_id)
    _feishu_notify(
        engine,
        task,
        log,
        prev=None,
        note="提需已建 VisualTask（人审聊天 demo）",
        extra={"intake_id": ref.intake_id},
    )

    prev = task.status
    engine.run_strategy(task, ops, log)
    _feishu_notify(engine, task, log, prev=prev, note="Brief & Strategy 完成")

    prev = task.status
    if not engine.bind_and_gate_knowledge(task, log):
        _feishu_notify(engine, task, log, prev=prev, note="Knowledge 阻断")
        path = save_task(task, hitl_dir)
        log.add(f"[hitl:store] saved={path} (knowledge blocked)")
        log.add(f"=== DONE status={task.status.value} (blocked) ===")
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log, ref

    _feishu_notify(engine, task, log, prev=prev, note="Knowledge ready")

    prev = task.status
    if not engine.run_generation(task, log):
        _feishu_notify(engine, task, log, prev=prev, note="Generation failed")
        path = save_task(task, hitl_dir)
        log.add(f"[hitl:store] saved={path}")
        log.add(f"=== DONE status={task.status.value} ===")
        return task, log, ref
    _feishu_notify(engine, task, log, prev=prev, note="Generation → QA")

    prev = task.status
    decision = engine.run_qa(task, log, overall=QAOverall.PASS_WITH_RISK)
    _feishu_notify(
        engine,
        task,
        log,
        prev=prev,
        note=f"QA {QAOverall.PASS_WITH_RISK.value}",
        extra={"hitl_reasons": decision.reasons},
    )

    prev = task.status
    engine.apply_hitl_gate(task, decision, log)
    _feishu_notify(
        engine,
        task,
        log,
        prev=prev,
        note="HITL → PendingReview（不代审，等人）",
    )

    if task.status != TaskStatus.PENDING_REVIEW:
        path = save_task(task, hitl_dir)
        log.add(f"[unexpected] expected PendingReview, got {task.status.value}")
        log.add(f"[hitl:store] saved={path}")
        log.add(f"[trace] {log.status_trace(task)}")
        return task, log, ref

    path = save_task(task, hitl_dir)
    log.add(f"[hitl:store] saved={path}")

    tid = task.task_id
    lines = [
        f"[EVAW 人审待办] task_id={tid}",
        f"状态=PendingReview  sku={task.sku_id}  QA=PassWithRisk",
        "原因：新品 + structure_sensitive + PassWithRisk",
        "",
        "请人工拍板（本 demo 不会自动代审）：",
        f"· 批准 → 在群里回复：「批准 {tid}」",
        f"  或执行：python3 -m evaw.cli hitl-apply --task {tid} --decision approve",
        f"· 打回 → 在群里回复：「打回 {tid} TEXT_ERROR」（原因码可换）",
        f"  或执行：python3 -m evaw.cli hitl-apply --task {tid} "
        "--decision reject --reason TEXT_ERROR",
        "",
        "常用原因码：FIDELITY_STRUCTURE / TEXT_ERROR / BRAND_VIOLATION / "
        "LAYOUT_PLATFORM / BUSINESS_JUDGEMENT",
    ]
    chat_text = "\n".join(lines)
    nr = adapter.send_chat_text(chat_text)
    log.add(
        f"[feishu:chat_hitl] channel={nr.channel} ok={nr.ok} "
        f"msg={nr.message_id} detail={nr.detail}"
    )
    log.add("[hitl] STOPPED at PendingReview — waiting for human (no auto-approve)")
    log.add(
        f"=== DONE status={task.status.value} auto_approved={task.auto_approved} "
        f"task_id={tid} snapshot={path} feishu={adapter.name} ==="
    )
    log.add(f"[trace] {log.status_trace(task)}")
    return task, log, ref


__all__ = [
    "WorkflowEngine",
    "WorkflowConfig",
    "RunLog",
    "IllegalTransition",
    "attach_feishu",
    "scenario_feishu_demo",
    "scenario_hitl_chat_demo",
]
