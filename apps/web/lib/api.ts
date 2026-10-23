"use client";
import { getManager } from "./auth";
import { errorMessage } from "./format";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const user = await getManager().getUser();
  if (!user || user.expired) throw new ApiError(401, "Not signed in");
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${user.access_token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage(body, res.statusText));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type Me = {
  id: string; org_id: string; org_name: string; email: string; display_name: string;
  role: "admin" | "engineer" | "reviewer" | "viewer";
};
export type Summary = {
  systems: number; runs: number; runs_last_30d: number; pass_rate: number | null; tests_evaluated: number;
  critical_failures: number; pending_reviews: number; never_evaluated: string[];
  by_severity: Record<"critical" | "high" | "medium" | "low", number>;
  recent_runs: { id: string; system: string; version: string; suite: string; status: string; started_at: string; pass_rate: number | null; critical_failures: number }[];
  pass_rate_by_release: { system: string; version: string; pass_rate: number; started_at: string; run_id: string }[];
};
export type SystemRow = {
  id: string; name: string; purpose: string; owner: string; model_name: string | null;
  latest_version: string | null; latest_version_id: string | null; created_at: string; last_run_at: string | null; run_count: number;
};
export type SystemCreate = {
  name: string; purpose?: string; owner?: string; model_name?: string; version_label: string;
  endpoint_url: string; auth_type: "none" | "bearer"; auth_secret?: string;
};

export type Suite = { id: string; name: string; description: string; case_count: number; created_at: string };
export type Severity = "critical" | "high" | "medium" | "low";
export type CaseRow = {
  id: string; suite_id: string; case_key: string; version: number; category: string; input: string;
  reference_context: string; expected_behavior: string; criteria: string[]; severity: Severity;
  pass_conditions: Record<string, unknown>; validation_status: "draft" | "validated" | "rejected"; position: number;
};
export type CaseIn = Pick<CaseRow, "category" | "input" | "reference_context" | "expected_behavior" | "criteria" | "severity" | "pass_conditions">;
export const JUDGE_CRITERIA = ["faithfulness", "relevance", "citation_accuracy", "unjustified_claims", "uncertainty", "boundaries", "sensitive_requests", "consistency"] as const;

export type Run = {
  id: string; system_id: string; system_name: string; version: string; suite_name: string; status: string;
  started_at: string; finished_at: string | null; total: number; passed: number; failed: number; errors: number;
  pending: number; critical_failures: number; needs_review: number; pass_rate: number | null;
  judge_model: string | null; params: Record<string, unknown>; judge_prompt_versions: Record<string, string>;
};
export type CriterionRow = {
  kind: "deterministic" | "llm_judge"; criterion: string; score: number | null; status: "pass" | "fail" | "error";
  justification: string; evidence: string[]; confidence: number | null; requires_review: boolean; judge_prompt_version: string | null;
};
export type RunItem = {
  id: string; case_key: string; case_version: number; category: string; severity: Severity; question: string;
  status: "pending" | "passed" | "failed" | "error"; needs_review: boolean; review_reasons: string[]; latency_ms: number | null;
  response_text: string | null; reference_context: string; expected_behavior: string; score: number | null; criteria: CriterionRow[];
  run_id: string; review_status: "pending" | "agreed" | "disputed" | "arbitrated" | null; human_decision: "accept" | "reject" | null;
};
export type ReviewRow = { id: string; reviewer_id: string; reviewer: string; decision: "accept" | "reject"; error_severity: Severity | null; annotations: { kind: string; note: string; quote?: string | null }[]; justification: string; created_at: string };
export type ReviewDetail = { item: RunItem; run_label: string; reviews: ReviewRow[]; status: string; final_decision: "accept" | "reject" | null; my_decision: string | null };
export type VersionRow = { id: string; system_id: string; system_name: string; version_label: string; endpoint_url: string; auth_type: string; created_at: string; run_count: number; last_run_at: string | null };
export type Delta = { case_key: string; category: string; severity: Severity; question: string; baseline: string; candidate: string };
export type Side = { run_id: string; version: string; pass_rate: number | null; failed: number; critical_failures: number; open_reviews: number; total: number };
export type Comparison = { system: string; suite: string; baseline: Side; candidate: Side; categories: { category: string; baseline: number | null; candidate: number | null }[]; regressions: Delta[]; fixed: Delta[]; unchanged_failures: Delta[]; only_in_one: string[]; verdict: "worse" | "better" | "same"; critical_regressions: number };
export type GateStatus = "PASS" | "FAIL" | "REVIEW_REQUIRED";
export type GateEval = { id: string; run_id: string; baseline_run_id: string | null; system_id: string; system_name: string; version: string; status: GateStatus; details: { criteria: { name: string; threshold: string; value: string; kind: string; status: "pass" | "fail" | "review" }[]; counts: { total: number; failed: number; critical_failures: number; open_reviews: number; pass_rate: number | null }; critical_tests: { case_key: string; question: string; effective: string; auto_status: string; human_decision: string | null; open_review: boolean }[] }; policy: Record<string, unknown>; evaluated_at: string; is_latest: boolean; decisions: { decision: string; justification: string; by: string; at: string }[] };
export type GateRow = { id: string; run_id: string; system_name: string; version: string; status: GateStatus; evaluated_at: string; decision: string | null };
export type GateRules = { max_critical_failures: number; max_high_failures: number | null; min_pass_rate: number; min_category_pass_rate: Record<string, number>; max_new_regressions: number | null; require_reviews_resolved: boolean };

/** Authenticated download (exports). */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const user = await getManager().getUser();
  if (!user || user.expired) throw new ApiError(401, "Not signed in");
  const res = await fetch(`/api/v1${path}`, { headers: { Authorization: `Bearer ${user.access_token}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export type ReportRow = { id: string; run_id: string; format: "html" | "json" | "pdf"; manifest_sha256: string; created_at: string; size: number; run_label: string };
export type EvidenceRow = { id: string; run_id: string | null; kind: string; sha256: string; size: number; created_at: string };
export type AuditEntry = { id: number; ts: string; actor: string | null; action: string; entity_type: string; entity_id: string; detail: Record<string, unknown> | null };
export type AuditList = { chain_valid: boolean; first_invalid_id: number | null; entries: AuditEntry[] };
export type SettingsOut = { org_name: string; retention_days: number };
export type TokenRow = { id: string; name: string; scopes: string[]; last_used_at: string | null };
