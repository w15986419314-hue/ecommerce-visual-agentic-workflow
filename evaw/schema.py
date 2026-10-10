"""Locked enums and core Schema (aligned with PRD v0.2.1 / Architecture v0.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Locked enums
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    DRAFT = "Draft"
    READY_FOR_STRATEGY = "ReadyForStrategy"
    STRATEGIZED = "Strategized"
    KNOWLEDGE_PENDING = "KnowledgePending"
    KNOWLEDGE_READY = "KnowledgeReady"
    GENERATING = "Generating"
    GENERATION_FAILED = "GenerationFailed"
    QA_PENDING = "QAPending"
    QA_FAILED = "QAFailed"
    QA_PASSED = "QAPassed"
    QA_PASSED_WITH_RISK = "QAPassedWithRisk"
    PENDING_REVIEW = "PendingReview"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    DELIVERED = "Delivered"
    FEEDBACK_LINKED = "FeedbackLinked"
    CANCELLED = "Cancelled"


class KnowledgeStatusEnum(str, Enum):
    READY = "ready"
    MISSING = "missing"
    OUTDATED = "outdated"
    EXEMPTED = "exempted"


class GenerationMode(str, Enum):
    HERO = "hero"
    SCENE = "scene"
    SKU_EXTEND = "sku_extend"
    PDP_MODULE = "pdp_module"


class GenerationResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class Platform(str, Enum):
    TMALL = "tmall"
    JD = "jd"
    AMAZON = "amazon"
    DTC = "dtc"


class AssetType(str, Enum):
    HERO = "hero"
    SKU = "sku"
    PDP_MODULE = "pdp_module"


class QAOverall(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    PASS_WITH_RISK = "PassWithRisk"


class DimensionStatus(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    RISK = "Risk"


class ReviewDecisionEnum(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ReasonCode(str, Enum):
    FIDELITY_STRUCTURE = "FIDELITY_STRUCTURE"
    FIDELITY_MATERIAL = "FIDELITY_MATERIAL"
    BRAND_VIOLATION = "BRAND_VIOLATION"
    TEXT_ERROR = "TEXT_ERROR"
    LAYOUT_PLATFORM = "LAYOUT_PLATFORM"
    MOBILE_READABILITY = "MOBILE_READABILITY"
    BUSINESS_JUDGEMENT = "BUSINESS_JUDGEMENT"
    LEAD_FAIL_EXEMPT = "LEAD_FAIL_EXEMPT"
    KNOWLEDGE_EXEMPT = "KNOWLEDGE_EXEMPT"
    AUDIT_FIDELITY = "AUDIT_FIDELITY"
    AUDIT_BRAND = "AUDIT_BRAND"
    AUDIT_OTHER = "AUDIT_OTHER"
    OTHER = "OTHER"


# Default reject → next status mapping (architecture §5.4)
REASON_DEFAULT_REFLOW: dict[ReasonCode, TaskStatus] = {
    ReasonCode.FIDELITY_STRUCTURE: TaskStatus.GENERATING,
    ReasonCode.FIDELITY_MATERIAL: TaskStatus.GENERATING,
    ReasonCode.BRAND_VIOLATION: TaskStatus.STRATEGIZED,
    ReasonCode.TEXT_ERROR: TaskStatus.GENERATING,
    ReasonCode.LAYOUT_PLATFORM: TaskStatus.GENERATING,
    ReasonCode.MOBILE_READABILITY: TaskStatus.GENERATING,
    ReasonCode.BUSINESS_JUDGEMENT: TaskStatus.STRATEGIZED,
    ReasonCode.AUDIT_FIDELITY: TaskStatus.GENERATING,
    ReasonCode.AUDIT_BRAND: TaskStatus.STRATEGIZED,
}


STRUCTURE_SENSITIVE = "structure_sensitive"


# ---------------------------------------------------------------------------
# Core objects
# ---------------------------------------------------------------------------


@dataclass
class OperationsInput:
    brand_id: str
    sku_id: str
    platform: Platform
    asset_type: AssetType
    selling_points: list[str]
    size_spec: str
    deadline: datetime
    is_new_product: bool = False
    risk_flags: list[str] = field(default_factory=list)
    created_by: str = "ops_demo"


@dataclass
class CreativeBrief:
    brief_id: str
    task_id: str
    summary: str
    selling_points: list[str]
    platform: Platform
    asset_type: AssetType
    constraints_summary: str
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class VisualStrategyPackage:
    strategy_id: str
    task_id: str
    version: str
    scene_direction: str
    composition_notes: str
    selling_point_priority: list[str]
    risk_flags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class KnowledgeStatus:
    task_id: str
    sku_id: str
    status: KnowledgeStatusEnum
    missing_items: list[str] = field(default_factory=list)
    exemption_ticket_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class ExemptionTicket:
    ticket_id: str
    task_id: str
    issuer_id: str
    reason_code: ReasonCode
    notes: str
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class GeneratedAsset:
    asset_id: str
    task_id: str
    generation_result_id: str
    asset_type: str
    uri: str
    platform_target: str
    mode: GenerationMode
    knowledge_snapshot_id: str  # SHALL
    strategy_version: str  # SHALL
    version: str = "v1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    generation_result_id: str
    task_id: str
    mode: GenerationMode
    status: GenerationResultStatus
    assets: list[GeneratedAsset]
    knowledge_snapshot_id: str  # SHALL
    strategy_version: str  # SHALL
    started_at: datetime
    finished_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    candidate_count: int = 0


@dataclass
class DimensionResult:
    status: DimensionStatus
    notes: str
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class QAReport:
    """Visual QA report (PRD: VisualQAReport) — five dims + overall + reason_code."""

    qa_id: str
    asset_id: str
    generation_result_id: str
    dimensions: dict[str, DimensionResult]
    overall: QAOverall
    suggested_fixes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    reason_code: Optional[ReasonCode] = None
    engine: str = "stub"  # stub | rules | multimodal
    mode: str = "stub"  # stub | live
    primary_dimension: Optional[str] = None


@dataclass
class ReviewDecision:
    review_id: str
    task_id: str
    reviewer_id: str
    decision: ReviewDecisionEnum
    reason_code: Optional[ReasonCode] = None
    accept_risk: bool = False
    notes: str = ""
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class DeliveryPackage:
    delivery_id: str
    task_id: str
    asset_ids: list[str]
    platform: Platform
    archived_at: datetime = field(default_factory=utcnow)
    review_notes: str = ""


@dataclass
class StatusTransition:
    from_status: TaskStatus
    to_status: TaskStatus
    trigger: str
    at: datetime = field(default_factory=utcnow)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualTask:
    task_id: str
    status: TaskStatus
    brand_id: str
    sku_id: str
    platform: Platform
    asset_type: AssetType
    deadline: datetime
    is_new_product: bool = False
    risk_flags: list[str] = field(default_factory=list)
    knowledge_status: KnowledgeStatusEnum = KnowledgeStatusEnum.MISSING
    current_strategy_id: Optional[str] = None
    current_generation_result_id: Optional[str] = None
    current_qa_id: Optional[str] = None
    exemption_ticket_id: Optional[str] = None
    auto_approved: bool = False
    audit_sampled: bool = False
    qa_fail_count: int = 0
    created_by: str = "ops_demo"
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    # attached objects (in-memory)
    brief: Optional[CreativeBrief] = None
    strategy: Optional[VisualStrategyPackage] = None
    knowledge: Optional[KnowledgeStatus] = None
    generation: Optional[GenerationResult] = None
    qa: Optional[QAReport] = None
    review: Optional[ReviewDecision] = None
    delivery: Optional[DeliveryPackage] = None
    history: list[StatusTransition] = field(default_factory=list)
    block_reason: Optional[str] = None

    def touch(self) -> None:
        self.updated_at = utcnow()

    def requires_forced_review(self) -> bool:
        """High-risk gate: new product OR structure_sensitive OR exempted."""
        if self.is_new_product:
            return True
        if STRUCTURE_SENSITIVE in (self.risk_flags or []):
            return True
        if self.knowledge_status == KnowledgeStatusEnum.EXEMPTED:
            return True
        if self.exemption_ticket_id:
            return True
        return False

# Alias used in PRD / architecture naming
VisualQAReport = QAReport
