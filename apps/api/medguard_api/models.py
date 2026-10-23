import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org():
    return mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)


def _ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=365)
    created_at: Mapped[datetime] = _ts()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "oidc_sub"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    oidc_sub: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20))  # admin|engineer|reviewer|viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AISystem(Base):
    __tablename__ = "ai_systems"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    usage_context: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(200), default="")
    model_name: Mapped[str | None] = mapped_column(String(200))
    doc_sources: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AISystemVersion(Base):
    __tablename__ = "ai_system_versions"
    __table_args__ = (UniqueConstraint("system_id", "version_label"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_systems.id", ondelete="CASCADE"), index=True)
    version_label: Mapped[str] = mapped_column(String(80))
    endpoint_url: Mapped[str] = mapped_column(String(2000))
    auth_type: Mapped[str] = mapped_column(String(20), default="none")  # none|bearer|header
    auth_header_name: Mapped[str | None] = mapped_column(String(100))
    auth_secret_enc: Mapped[str | None] = mapped_column(Text)
    request_template: Mapped[dict] = mapped_column(JSONType, default=dict)
    response_mapping: Mapped[dict] = mapped_column(JSONType, default=dict)
    timeout_s: Mapped[float] = mapped_column(Float, default=30.0)
    created_at: Mapped[datetime] = _ts()


class TestSuite(Base):
    __tablename__ = "test_suites"
    __test__ = False
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _ts()


class TestCase(Base):
    """One row per (case_key, version); rows are immutable so runs stay reproducible."""

    __tablename__ = "test_cases"
    __test__ = False
    __table_args__ = (UniqueConstraint("suite_id", "case_key", "version"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    suite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_suites.id", ondelete="CASCADE"), index=True)
    case_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(80))
    input: Mapped[str] = mapped_column(Text)
    reference_context: Mapped[str] = mapped_column(Text, default="")
    expected_behavior: Mapped[str] = mapped_column(Text, default="")
    criteria: Mapped[list] = mapped_column(JSONType, default=list)
    severity: Mapped[str] = mapped_column(String(10))  # low|medium|high|critical
    pass_conditions: Mapped[dict] = mapped_column(JSONType, default=dict)
    validation_status: Mapped[str] = mapped_column(String(12), default="draft")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _ts()


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    system_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_system_versions.id"), index=True)
    suite_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_suites.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="queued")
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    judge_model: Mapped[str | None] = mapped_column(String(200))
    judge_model_digest: Mapped[str | None] = mapped_column(String(200))
    judge_prompt_versions: Mapped[dict] = mapped_column(JSONType, default=dict)
    started_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = _ts()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceObject(Base):
    __tablename__ = "evidence_objects"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    s3_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _ts()


class RunItem(Base):
    __tablename__ = "run_items"
    __table_args__ = (UniqueConstraint("run_id", "test_case_id"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("test_cases.id"))
    response_evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence_objects.id"))
    response_text: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(14), default="pending")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list] = mapped_column(JSONType, default=list)


class CriterionResult(Base):
    __tablename__ = "criterion_results"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_items.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(14))  # deterministic|llm_judge
    criterion: Mapped[str] = mapped_column(String(80))
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10))  # pass|fail|error
    justification: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSONType, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    judge_prompt_version: Mapped[str | None] = mapped_column(String(40))


class Review(Base):
    """Append-only: a reviewer's decision is never edited, only superseded."""

    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_items.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(8))  # accept|reject
    error_severity: Mapped[str | None] = mapped_column(String(10))
    annotations: Mapped[list] = mapped_column(JSONType, default=list)
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class ReviewResolution(Base):
    __tablename__ = "review_resolutions"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_items.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(12))  # agreed|disputed|arbitrated
    final_decision: Mapped[str | None] = mapped_column(String(8))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = _ts()


class GatePolicy(Base):
    __tablename__ = "gate_policies"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_systems.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="default")
    rules: Mapped[dict] = mapped_column(JSONType, default=dict)


class GateEvaluation(Base):
    __tablename__ = "gate_evaluations"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evaluation_runs.id"))
    policy_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16))  # PASS|FAIL|REVIEW_REQUIRED
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    evaluated_at: Mapped[datetime] = _ts()


class ReleaseDecision(Base):
    __tablename__ = "release_decisions"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    gate_evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gate_evaluations.id"), index=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))  # release|block
    justification: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = _ts()


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    format: Mapped[str] = mapped_column(String(6))
    evidence_object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_objects.id"))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _ts()


class AuditLog(Base):
    """Hash-chained, insert-only. The app role has no UPDATE/DELETE on this table."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = _org()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(80))
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = _ts()


class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    name: Mapped[str] = mapped_column(String(200))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSONType, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
