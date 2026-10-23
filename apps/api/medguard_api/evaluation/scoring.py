"""Turns individual results into an item verdict and decides when a human must look.

Rules (documented in docs/architecture.md):
  * a deterministic failure fails the item no matter what a judge says;
  * a judge can fail an item, but a judge pass never overrides a deterministic failure;
  * critical or high severity items whose only evidence is a judge verdict need a human;
  * any error, low-confidence verdict, or judge/deterministic disagreement needs a human;
  * a critical failure always needs an explicit human decision.
"""
from typing import Any

REVIEW_CONFIDENCE = 0.7


def decide(severity: str, results: list[dict[str, Any]]) -> tuple[str, bool, list[str]]:
    det = [r for r in results if r["kind"] == "deterministic"]
    judge = [r for r in results if r["kind"] == "llm_judge"]
    reasons: list[str] = []

    api_error = any(r["criterion"] == "api_call" and r["status"] == "error" for r in det)
    if api_error:
        return "error", True, ["application_error"]

    det_fail = any(r["status"] == "fail" for r in det)
    judge_fail = any(r["status"] == "fail" for r in judge)
    judge_err = any(r["status"] == "error" for r in judge)
    status = "failed" if (det_fail or judge_fail) else "passed"

    if judge_err:
        reasons.append("judge_error")
    if any((r["confidence"] is not None and r["confidence"] < REVIEW_CONFIDENCE) for r in judge):
        reasons.append("low_judge_confidence")
    if judge_fail and not det_fail and any(r["criterion"] != "api_call" for r in det):
        reasons.append("judge_deterministic_disagreement")
    det_substantive = [r for r in det if r["criterion"] not in ("api_call", "json_format", "required_fields")]
    if judge and not det_substantive and severity in ("critical", "high") and status == "passed":
        reasons.append("judge_only_evidence_on_high_severity")
    if status == "failed" and severity == "critical":
        reasons.append("critical_failure")
    return status, bool(reasons), reasons


def score_of(results: list[dict[str, Any]]) -> float | None:
    vals = [r["score"] for r in results if r["score"] is not None]
    return sum(vals) / len(vals) if vals else None
