"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Chip, Disclaimer, EmptyState, Kpi, PageHeader, SeverityChip, pct } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import type { Comparison, Delta, Run } from "@/lib/api";
import { useApi } from "@/lib/useApi";

function DeltaTable({ title, rows, count, tone, empty, limit = 8 }: { title: string; rows: Delta[]; count: number; tone: "cr" | "ok" | "ne"; empty: string; limit?: number }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, limit);
  return (
    <section className="card" aria-label={title} style={{ overflow: "hidden" }}>
      <div className="hd" style={{ paddingBottom: 12 }}><h2 className="h2">{title} <Chip tone={tone}>{count}</Chip></h2>{tone === "cr" && <span className="mu" style={{ fontSize: 12 }}>Critical first</span>}</div>
      {rows.length === 0 ? <p className="mu" style={{ margin: 0, padding: "8px 20px 16px", borderTop: "1px solid var(--bd)" }}>{empty}</p> : (
        <div style={{ overflowX: "auto" }}>
          <table className="tbl">
            <thead><tr><th>Test</th><th>Category</th><th>Severity</th><th>Baseline → candidate</th></tr></thead>
            <tbody>{shown.map((d) => (
              <tr key={d.case_key}><td><span className="mono">{d.case_key}</span> <span className="mu">{d.question}</span></td><td className="mu">{d.category}</td><td><SeverityChip severity={d.severity} /></td>
                <td>{d.baseline === "passed" ? "Passed" : "Failed"} → {d.candidate === "passed" ? "Passed" : "Failed"}</td></tr>))}
            </tbody>
          </table>
          {rows.length > limit && <div style={{ padding: "10px 16px" }}><button className="btn sm" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</button></div>}
        </div>
      )}
    </section>
  );
}

function Compare() {
  const router = useRouter();
  const params = useSearchParams();
  const runs = useApi<Run[]>("/runs");
  const candId = params.get("candidate");
  const candidate = runs.data?.find((r) => r.id === candId) ?? null;
  const peers = (runs.data ?? []).filter((r) => candidate && r.status === "completed" && r.system_id === candidate.system_id && r.id !== candidate.id && r.suite_name === candidate.suite_name);
  const baseId = params.get("baseline") ?? peers[0]?.id ?? null;
  const cmp = useApi<Comparison>(baseId && candId ? `/compare?baseline_run=${baseId}&candidate_run=${candId}` : null);
  const c = baseId && candId ? cmp.data : null;
  const completed = (runs.data ?? []).filter((r) => r.status === "completed");

  const pts = (a: number | null, b: number | null) => (a === null || b === null ? "—" : `${b >= a ? "▲" : "▼"} ${Math.abs((b - a) * 100).toFixed(1)} pts`);

  return (
    <Page current="Compare versions" trail={[{ label: "AI Systems", href: "/systems" }]}>
      <PageHeader title="Version comparison" subtitle={c ? `${c.system} · both versions evaluated on ${c.suite}` : "Choose a candidate run to compare against a baseline."} />
      {runs.error && <ErrorBox message={runs.error} retry={runs.reload} />}
      {runs.loading && <div className="card"><LoadingRows /></div>}
      {runs.data && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label htmlFor="b" className="lbl">Baseline version</label>
            <select id="b" className="inp" style={{ minWidth: 280 }} value={baseId ?? ""} onChange={(e) => router.replace(`/compare?candidate=${candId}&baseline=${e.target.value}`)} disabled={!candidate || peers.length === 0}>
              {peers.length === 0 && <option value="">No other completed run of this suite</option>}
              {peers.map((r) => <option key={r.id} value={r.id}>{r.version} · {new Date(r.started_at).toLocaleDateString()} · {pct(r.pass_rate)}</option>)}
            </select>
          </div>
          <span className="mu" style={{ paddingBottom: 8 }}>vs</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label htmlFor="c" className="lbl">Candidate version</label>
            <select id="c" className="inp" style={{ minWidth: 280 }} value={candId ?? ""} onChange={(e) => router.replace(`/compare?candidate=${e.target.value}`)}>
              {!candId && <option value="">Select a run…</option>}
              {completed.map((r) => <option key={r.id} value={r.id}>{r.system_name} {r.version} · {new Date(r.started_at).toLocaleDateString()} · {pct(r.pass_rate)}</option>)}
            </select>
          </div>
          {candidate && <Link className="btn pri" href={`/gates/view?run=${candidate.id}${baseId ? `&baseline=${baseId}` : ""}`}>Open release gate</Link>}
        </div>
      )}
      {runs.data && !candId && <EmptyState title="Pick a candidate run">Compare is available between two completed runs of the same application and test suite. Open a run and choose &ldquo;Compare with another version&rdquo;.</EmptyState>}
      {candidate && peers.length === 0 && <EmptyState title="Nothing to compare with yet">Run the same suite on another version of this application to get a baseline.</EmptyState>}
      {cmp.error && baseId && <ErrorBox message={cmp.error} retry={cmp.reload} />}
      {c && (
        <>
          <div role="status" className="card" style={{ padding: "14px 20px", borderColor: c.verdict === "worse" ? "var(--cr)" : c.verdict === "better" ? "var(--ok)" : "var(--bd)" }}>
            <strong style={{ color: c.verdict === "worse" ? "var(--cr)" : c.verdict === "better" ? "var(--ok)" : undefined }}>
              {c.critical_regressions > 0 ? `${c.critical_regressions} new critical regression${c.critical_regressions === 1 ? "" : "s"}` : c.verdict === "worse" ? "Candidate is worse than the baseline" : c.verdict === "better" ? "Candidate improves on the baseline" : "No material change"}
            </strong>
            <div className="mu">
              {c.candidate.version} vs {c.baseline.version}: pass rate {pts(c.baseline.pass_rate, c.candidate.pass_rate)}, {c.regressions.length} test{c.regressions.length === 1 ? "" : "s"} regressed and {c.fixed.length} fixed.
              {c.baseline.critical_failures === 0 ? " The baseline had no critical failures." : ""} A critical regression is never offset by a better average.
            </div>
          </div>
          <section aria-label="Key deltas" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}>
            <Kpi label="Pass rate" value={<>{pct(c.baseline.pass_rate)} → {pct(c.candidate.pass_rate)}</>} href="#cats" note={pts(c.baseline.pass_rate, c.candidate.pass_rate)} />
            <Kpi label="Failed tests" value={<>{c.baseline.failed} → {c.candidate.failed}</>} href="#reg" note={`${c.candidate.failed - c.baseline.failed >= 0 ? "▲" : "▼"} ${Math.abs(c.candidate.failed - c.baseline.failed)}`} />
            <Kpi label="Critical failures" tone={c.candidate.critical_failures > c.baseline.critical_failures ? "cr" : undefined} value={<>{c.baseline.critical_failures} → {c.candidate.critical_failures}</>} href="#reg" note="Never averaged away" />
            <Kpi label="Requiring review" value={<>{c.baseline.open_reviews} → {c.candidate.open_reviews}</>} href="/reviews" note="Open human validations" />
          </section>
          <section id="cats" className="card" aria-label="Pass rate by category" style={{ padding: "16px 20px" }}>
            <h2 className="h2" style={{ marginBottom: 12 }}>Pass rate by category <span className="mu" style={{ fontWeight: 400, fontSize: 12 }}>baseline {c.baseline.version} · candidate {c.candidate.version}</span></h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {c.categories.map((k) => (
                <div key={k.category}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}><span>{k.category}</span><span className="num mu">{pct(k.baseline)} → <strong style={{ color: (k.candidate ?? 0) < (k.baseline ?? 0) ? "var(--cr)" : "var(--tx)" }}>{pct(k.candidate)}</strong></span></div>
                  <div style={{ height: 6, background: "var(--sf2)", borderRadius: 3, marginTop: 4 }}><div style={{ width: `${(k.baseline ?? 0) * 100}%`, height: "100%", background: "var(--mu)", borderRadius: 3 }} /></div>
                  <div style={{ height: 6, background: "var(--sf2)", borderRadius: 3, marginTop: 3 }}><div style={{ width: `${(k.candidate ?? 0) * 100}%`, height: "100%", background: (k.candidate ?? 0) < (k.baseline ?? 0) ? "var(--cr)" : "var(--ac)", borderRadius: 3 }} /></div>
                </div>
              ))}
            </div>
          </section>
          <div id="reg" style={{ display: "contents" }}>
            <DeltaTable title="New regressions" rows={c.regressions} count={c.regressions.length} tone="cr" empty="No test passed in the baseline and fails in the candidate." />
            <DeltaTable title="Resolved issues" rows={c.fixed} count={c.fixed.length} tone="ok" empty="No test failed in the baseline and passes in the candidate." />
            <DeltaTable title="Unchanged failures" rows={c.unchanged_failures} count={c.unchanged_failures.length} tone="ne" empty="No test fails in both versions." />
          </div>
          {c.only_in_one.length > 0 && <p className="mu" style={{ margin: 0 }}>Not comparable (present in only one run): <span className="mono">{c.only_in_one.join(", ")}</span></p>}
        </>
      )}
      <Disclaimer />
    </Page>
  );
}

export default function Page_() {
  return <Suspense fallback={null}><Compare /></Suspense>;
}
