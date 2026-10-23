"use client";
import { Chip, ItemStatusChip, SeverityChip } from "./ui";
import type { CriterionRow, RunItem } from "@/lib/api";

export const REASONS: Record<string, string> = {
  judge_error: "A judge criterion could not be graded automatically",
  low_judge_confidence: "The judge reported low confidence",
  judge_deterministic_disagreement: "The judge failed an answer the deterministic checks accepted",
  judge_only_evidence_on_high_severity: "High-severity pass rests on a judge verdict alone",
  critical_failure: "Critical failure: needs an explicit human decision",
  application_error: "The application did not return a usable response",
  engine_error: "The evaluation engine failed on this scenario",
};

export function CriterionLine({ c }: { c: CriterionRow }) {
  const tone = c.status === "pass" ? "ok" : c.status === "fail" ? "cr" : "wn";
  const shape = c.status === "pass" ? "dot" : c.status === "fail" ? "xx" : "dia";
  return (
    <li style={{ display: "grid", gridTemplateColumns: "92px 1fr", gap: 10, padding: "8px 0", borderTop: "1px solid var(--bd)" }}>
      <Chip tone={tone} shape={shape}>{c.status.toUpperCase()}</Chip>
      <div>
        <div style={{ fontWeight: 500 }}>{c.criterion.replace(/_/g, " ")} <span className="mu" style={{ fontWeight: 400, fontSize: 12 }}>· {c.kind === "llm_judge" ? `LLM judge${c.confidence !== null ? ` · confidence ${c.confidence.toFixed(2)}` : ""}` : "deterministic"}</span></div>
        <div className="mu">{c.justification}</div>
        {c.evidence.length > 0 && <div className="mono mu" style={{ fontSize: 12, marginTop: 2 }}>{c.evidence.join(" · ")}</div>}
      </div>
    </li>
  );
}

export function ItemDetail({ item, versionLabel, trail }: { item: RunItem; versionLabel: string; trail: string }) {
  let shown = item.response_text ?? "";
  try { shown = JSON.stringify(JSON.parse(shown), null, 2); } catch { /* not JSON: show raw */ }
  return (
    <section className="card" aria-labelledby="dt" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <div className="lbl">Test detail · <span className="mono">{item.case_key}</span> v{item.case_version}</div>
        <h2 className="h2" id="dt" style={{ fontSize: 16, marginTop: 4 }}>{item.question}</h2>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <SeverityChip severity={item.severity} /><ItemStatusChip status={item.status} />
          {item.latency_ms !== null && <span className="chip ne">{item.latency_ms} ms</span>}
          {item.human_decision && <Chip tone={item.human_decision === "accept" ? "ok" : "cr"} shape={item.human_decision === "accept" ? "dot" : "xx"}>Human: {item.human_decision === "accept" ? "acceptable" : "not acceptable"}</Chip>}
        </div>
      </div>
      {item.review_reasons.length > 0 && (
        <div role="note" className="card" style={{ padding: 12, borderColor: "var(--wn)", background: "var(--wnbg)" }}>
          <strong style={{ color: "var(--wn)" }}>Flagged for a human</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{item.review_reasons.map((x) => <li key={x}>{REASONS[x] ?? x}</li>)}</ul>
        </div>
      )}
      <div><div className="lbl">Expected behaviour</div><div>{item.expected_behavior || <span className="mu">Not specified</span>}</div></div>
      {item.reference_context && <div><div className="lbl">Reference document</div><div className="mu">{item.reference_context}</div></div>}
      <div><div className="lbl">Actual response from {versionLabel}</div>
        <pre className="mono" style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", background: "var(--sf2)", padding: 12, borderRadius: 8 }}>{shown || "(no response)"}</pre></div>
      <div><div className="lbl">Evaluation and evidence</div>
        <ul style={{ listStyle: "none", margin: "4px 0 0", padding: 0 }}>{item.criteria.map((c, k) => <CriterionLine key={k} c={c} />)}</ul></div>
      <div className="mono mu" style={{ fontSize: 12 }}>TRACE {trail}</div>
    </section>
  );
}
