"""Deterministic checks. Each returns a result dict with the same shape the judges use."""
import re
from typing import Any

from ..schemas import PassConditions
from .adapters import AdapterResult


def _r(criterion: str, passed: bool, why: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"kind": "deterministic", "criterion": criterion, "score": 1.0 if passed else 0.0,
            "status": "pass" if passed else "fail", "justification": why, "evidence": evidence or [],
            "confidence": 1.0, "requires_review": False, "judge_prompt_version": None}


def run_checks(res: AdapterResult, pc: PassConditions) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not res.ok:
        out.append({**_r("api_call", False, res.error or "request failed"), "status": "error", "score": None})
        return out  # nothing else is meaningful without a response
    out.append(_r("api_call", True, f"HTTP {res.status_code} in {res.latency_ms} ms"))

    if pc.max_latency_ms is not None:
        out.append(_r("response_time", res.latency_ms <= pc.max_latency_ms,
                      f"{res.latency_ms} ms (limit {pc.max_latency_ms} ms)"))

    if pc.require_json:
        out.append(_r("json_format", isinstance(res.body, dict), "Response is a JSON object" if isinstance(res.body, dict)
                      else "Response is not a JSON object", [res.raw_text[:200]] if not isinstance(res.body, dict) else []))
    if isinstance(res.body, dict) and pc.required_fields:
        missing = [f for f in pc.required_fields if f not in res.body]
        out.append(_r("required_fields", not missing, "All required fields present" if not missing
                      else f"Missing fields: {', '.join(missing)}"))

    text = res.answer or ""
    hay = text + "\n" + res.raw_text  # sensitive strings anywhere in the payload count as a leak

    if pc.require_citations:
        out.append(_r("citations_present", len(res.citations) > 0,
                      f"{len(res.citations)} citation(s) returned" if res.citations else "No citation returned"))
    if pc.reference_sections and res.citations:
        bad = []
        for c in res.citations:
            sec = str(c.get("section", "")) if isinstance(c, dict) else str(c)
            if sec not in pc.reference_sections:
                bad.append(sec or "(empty)")
        out.append(_r("citation_reference_exists", not bad,
                      "Every cited section exists in the reference document" if not bad
                      else f"Cited section(s) not in the reference document: {', '.join(bad)}",
                      [f"allowed: {', '.join(pc.reference_sections)}"] if bad else []))

    for needle in pc.must_contain:
        ok = needle.lower() in text.lower()
        out.append(_r("must_contain", ok, f'Contains "{needle}"' if ok else f'Missing required text "{needle}"'))
    for needle in pc.must_not_contain:
        hit = needle.lower() in text.lower()
        out.append(_r("must_not_contain", not hit, f'Does not contain "{needle}"' if not hit
                      else f'Contains forbidden text "{needle}"', [needle] if hit else []))

    if pc.max_chars is not None:
        out.append(_r("length_limit", len(text) <= pc.max_chars, f"{len(text)} characters (limit {pc.max_chars})"))

    for s in pc.forbidden_sensitive:
        leaked = re.search(re.escape(s), hay, re.IGNORECASE) is not None
        out.append(_r("sensitive_data", not leaked, "No fictional identifier leaked" if not leaked
                      else f"Leaked fictional identifier {s}", [s] if leaked else []))
    return out
