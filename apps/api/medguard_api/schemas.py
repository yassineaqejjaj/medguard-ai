"""Shared request/response models for suites, cases and runs."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["low", "medium", "high", "critical"]
Validation = Literal["draft", "validated", "rejected"]
JUDGE_CRITERIA = ("faithfulness", "relevance", "citation_accuracy", "unjustified_claims", "uncertainty",
                  "boundaries", "sensitive_requests", "consistency")


class PassConditions(BaseModel):
    """Deterministic rules attached to a scenario. Unknown keys are rejected so typos cannot silently disable a check."""
    model_config = ConfigDict(extra="forbid")

    require_json: bool = True
    required_fields: list[str] = Field(default_factory=lambda: ["answer"], max_length=20)
    require_citations: bool = False
    reference_sections: list[str] = Field(default_factory=list, max_length=200)  # cited sections must be one of these
    must_contain: list[str] = Field(default_factory=list, max_length=50)
    must_not_contain: list[str] = Field(default_factory=list, max_length=50)
    max_chars: int | None = Field(default=None, ge=1, le=100_000)
    max_latency_ms: int | None = Field(default=None, ge=1, le=600_000)
    forbidden_sensitive: list[str] = Field(default_factory=list, max_length=50)  # fictional identifiers that must not appear


class CaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=80)
    input: str = Field(min_length=1, max_length=8000)
    reference_context: str = Field(default="", max_length=50_000)
    expected_behavior: str = Field(default="", max_length=4000)
    criteria: list[str] = Field(default_factory=list, max_length=10)
    severity: Severity
    pass_conditions: PassConditions = Field(default_factory=PassConditions)

    @field_validator("criteria")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in JUDGE_CRITERIA]
        if bad:
            raise ValueError(f"unknown judge criteria: {bad}; allowed: {list(JUDGE_CRITERIA)}")
        return v


class CaseOut(BaseModel):
    id: uuid.UUID
    suite_id: uuid.UUID
    case_key: str
    version: int
    category: str
    input: str
    reference_context: str
    expected_behavior: str
    criteria: list
    severity: str
    pass_conditions: dict
    validation_status: str
    position: int


class SuiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class SuiteOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    case_count: int
    created_at: datetime


class RunCreate(BaseModel):
    system_version_id: uuid.UUID
    suite_id: uuid.UUID
