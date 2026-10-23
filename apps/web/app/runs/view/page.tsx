"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Chip, Disclaimer, ItemStatusChip, Kpi, PageHeader, RunStatusChip, SeverityChip, pct, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { ItemDetail } from "@/components/ItemDetail";
import type { Run, RunItem } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Filter = "all" | "failed" | "critical" | "review";
function duration(r: Run) {
  if (!r.finished_at) return "—";
  const s = Math.round((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000);
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

function Results() {
  const id = useSearchParams().get("id");
  const run = useApi<Run>(`/runs/${id}`);
  const items = useApi<RunItem[]>(`/runs/${id}/items`);
  const [filter, setFilter] = useState<Filter>("all");
  const [selId, setSelId] = useState<string | null>(null);
  const active = run.data?.status === "queued" || run.data?.status === "running";
  const { reload: rr } = run;
  const { reload: ir } = items;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => { rr(); ir(); }, 3000);
    return () => clearInterval(t);
  }, [active, rr, ir]);

  const r = run.data;
  const all = items.data ?? [];
  const shown = all.filter((i) => filter === "all" || (filter === "failed" ? i.status === "failed" || i.status === "error" : filter === "critical" ? i.severity === "critical" && i.status === "failed" : i.needs_review));
  const sel = all.find((i) => i.id === selId) ?? shown[0] ?? null;
  const count = (f: Filter) => all.filter((i) => f === "all" || (f === "failed" ? i.status === "failed" || i.status === "error" : f === "critical" ? i.severity === "critical" && i.status === "failed" : i.needs_review)).length;
  const inf = (r?.params?.inference ?? {}) as Record<string, number>;

  return (
    <Page current={r ? r.id.slice(0, 8) : "Run"} trail={[{ label: "Evaluation Runs", href: "/runs" }]}>
      {run.error && <ErrorBox message={run.error} retry={run.reload} />}
      {run.loading && <div className="card"><LoadingRows /></div>}
      {r && (
        <>
          <PageHeader title={`${r.system_name} ${r.version}`}
            subtitle={<><RunStatusChip status={r.status} /> <span className="mono">{r.id.slice(0, 8)}</span> · {r.suite_name} · {when(r.started_at)}</>}
            actions={r.status === "completed" && <>
              <Link className="btn" href={`/compare?candidate=${r.id}`}>Compare with another version</Link>
              <Link className="btn pri" href={`/gates/view?run=${r.id}`}>Open release gate</Link></>} />
          <section aria-label="Run summary" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(176px, 1fr))", gap: 12 }}>
            <Kpi label="Pass rate" value={pct(r.pass_rate)} href="#scenarios" note={`${r.passed} of ${r.total} tests passed`} />
            <Kpi label="Failed tests" value={r.failed + r.errors} href="#scenarios" note={r.errors ? `${r.errors} application errors` : undefined} />
            <Kpi label="Critical failures" tone={r.critical_failures ? "cr" : undefined} href="#scenarios"
              value={r.critical_failures ? <><span className="gl tri" style={{ width: 16, height: 16, display: "inline-block", marginRight: 10 }} aria-hidden />{r.critical_failures}</> : 0}
              note={r.critical_failures ? "Always need a human decision" : "None"} />
            <Kpi label="Requiring review" value={r.needs_review} href="#scenarios" note="Human validation pending" />
            <Kpi label="Duration" value={duration(r)} href="#scenarios" note={`${r.total} tests`} />
          </section>
          <section className="card" aria-label="Parameters" style={{ padding: "14px 20px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "8px 24px" }}>
            <div><div className="lbl">Judge model</div><div>{r.judge_model ?? <span className="mu">None configured — judge criteria are routed to human review</span>}</div></div>
            <div><div className="lbl">Inference</div><div className="mono">{inf.temperature !== undefined ? `temperature ${inf.temperature} · seed ${inf.seed} · max ${inf.max_tokens} tokens` : "—"}</div></div>
            <div><div className="lbl">Judge prompt</div><div className="mono">{Object.values(r.judge_prompt_versions).join(", ") || "—"}</div></div>
            <div><div className="lbl">Run ID</div><div className="mono" style={{ wordBreak: "break-all" }}>{r.id}</div></div>
          </section>

          <section id="scenarios" aria-labelledby="sc" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <h2 className="h2" id="sc" style={{ fontSize: 18 }}>Scenarios <span className="mu" style={{ fontWeight: 400, fontSize: 13 }}>failures first, critical before the rest</span></h2>
              <div role="group" aria-label="Filter scenarios" style={{ display: "flex", gap: 8 }}>
                {([["all", "All"], ["failed", "Failed"], ["critical", "Critical"], ["review", "Needs review"]] as const).map(([k, l]) => (
                  <button key={k} className="fb" aria-pressed={filter === k} onClick={() => setFilter(k)}>{l} <span className="mu">{count(k)}</span></button>
                ))}
              </div>
            </div>
            {items.loading && <div className="card"><LoadingRows /></div>}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 16, alignItems: "start" }}>
              <div className="card" style={{ overflow: "hidden" }}>
                <div style={{ overflowX: "auto" }}>
                  <table className="tbl">
                    <thead><tr><th>ID</th><th>Category</th><th>Severity</th><th>Score</th><th>Status</th><th>Review</th></tr></thead>
                    <tbody>
                      {shown.map((i) => (
                        <tr key={i.id} style={sel?.id === i.id ? { background: "var(--acbg)" } : undefined}>
                          <td><button onClick={() => setSelId(i.id)} className="mono" aria-pressed={sel?.id === i.id}
                            style={{ background: "none", border: 0, padding: 0, color: "var(--ac)", fontWeight: 600, cursor: "pointer" }}>{i.case_key}</button></td>
                          <td className="mu">{i.category}</td>
                          <td><SeverityChip severity={i.severity} /></td>
                          <td className="num">{i.score === null ? "—" : i.score.toFixed(2)}</td>
                          <td><ItemStatusChip status={i.status} /></td>
                          <td>{i.review_status === "agreed" || i.review_status === "arbitrated" ? <Chip tone="ok" shape="dot">Reviewed</Chip> : i.review_status === "disputed" ? <Chip tone="cr" shape="dia">Disputed</Chip> : i.needs_review ? <Chip tone="wn" shape="dia">Needs review</Chip> : <span className="mu">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {items.data && shown.length === 0 && <div style={{ padding: 20 }} className="mu">No scenario matches this filter.</div>}
              </div>
              {sel && <ItemDetail item={sel} versionLabel={r.version} trail={`${r.id.slice(0, 8)} → ${r.suite_name} → ${sel.case_key} v${sel.case_version} → ${r.system_name} ${r.version}`} />}
            </div>
          </section>
        </>
      )}
      <Disclaimer />
    </Page>
  );
}

export default function Page_() {
  return <Suspense fallback={null}><Results /></Suspense>;
}
