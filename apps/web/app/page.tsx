"use client";
import Link from "next/link";
import { Chip, Disclaimer, Kpi, PageHeader } from "@/components/ui";
import { ErrorBox, LoadingRows, Panel } from "@/components/Panel";
import { RunStatusChip, SeverityChip, pct, when } from "@/components/ui";
import { TrendChart } from "@/components/TrendChart";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import type { Summary } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function Overview() {
  const auth = useAuth();
  const { data: s, error, loading, reload } = useApi<Summary>("/dashboard/summary");
  const canConnect = auth.status === "ready" && (auth.me.role === "admin" || auth.me.role === "engineer");

  return (
    <Page current="Overview">
      <PageHeader
        title="Overview"
        subtitle={s ? `Release posture of ${s.systems} AI system${s.systems === 1 ? "" : "s"} · ${s.tests_evaluated} test results recorded` : "Loading…"}
        actions={canConnect && <Link className="btn pri" href="/systems?connect=1">Connect AI application</Link>}
      />
      {error && <ErrorBox message={error} retry={reload} />}
      {loading && <div className="card"><LoadingRows /></div>}
      {s && (
        <>
          <Attention s={s} />
          <section aria-label="Key metrics" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(176px, 1fr))", gap: 12 }}>
            <Kpi label="Registered AI systems" value={s.systems} href="/systems" note={s.systems === 0 ? "None connected yet" : undefined} />
            <Kpi label="Evaluation runs" value={s.runs} href="/runs" note={`${s.runs_last_30d} in last 30 days`} />
            <Kpi label="Pass rate" value={s.pass_rate === null ? "—" : `${(s.pass_rate * 100).toFixed(1)}%`} href="/runs"
              note={s.pass_rate === null ? "No results yet" : `${s.tests_evaluated} tests evaluated`} />
            <Kpi label="Critical failures" tone={s.critical_failures ? "cr" : undefined} href="/runs"
              value={s.critical_failures ? <><span className="gl tri" style={{ width: 16, height: 16, display: "inline-block", marginRight: 10 }} aria-hidden />{s.critical_failures}</> : 0}
              note={s.critical_failures ? "Blocking release gates" : "None recorded"} />
            <Kpi label="Pending reviews" value={s.pending_reviews} href="/reviews" note={s.pending_reviews ? "Awaiting a medical reviewer" : "Queue is empty"} />
            <Kpi label="Release readiness" value="—" href="/gates" note="Shown once a release gate is evaluated" />
          </section>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(420px, 1fr))", gap: 16 }}>
            {s.pass_rate_by_release.length === 0 ? (
              <Panel title="Pass rate by release" empty="No completed evaluation runs yet. The trend across releases appears here after the first campaign." />
            ) : (
              <Panel title="Pass rate by release" aside={<Link className="lnk" href="/runs">Open runs →</Link>}>
                <TrendChart points={s.pass_rate_by_release.map((r) => ({ label: `${r.system} ${r.version}`, value: r.pass_rate }))}
                  summary={`Pass rate by release: ${s.pass_rate_by_release.map((r) => `${r.system} ${r.version} ${(r.pass_rate * 100).toFixed(1)} percent`).join(", ")}.`} />
              </Panel>
            )}
            <Panel title="Failures by severity" aside={<span className="mu" style={{ fontSize: 12 }}>{Object.values(s.by_severity).reduce((a, b) => a + b, 0)} failed tests</span>}
              empty={Object.values(s.by_severity).every((n) => n === 0) ? "No failed tests recorded." : undefined}>
              {Object.values(s.by_severity).some((n) => n > 0) && (
                <div style={{ padding: "4px 20px 8px", display: "flex", flexDirection: "column", gap: 14, borderTop: "1px solid var(--bd)", paddingTop: 16 }}>
                  {(["critical", "high", "medium", "low"] as const).map((k) => {
                    const max = Math.max(...Object.values(s.by_severity), 1);
                    const color = { critical: "var(--cr)", high: "var(--wn)", medium: "var(--ac)", low: "var(--mu)" }[k];
                    return (
                      <div key={k} style={{ display: "grid", gridTemplateColumns: "96px 1fr 28px", gap: 10, alignItems: "center" }}>
                        <SeverityChip severity={k} />
                        <span style={{ height: 8, background: "var(--sf2)", borderRadius: 4 }}><span style={{ display: "block", width: `${(s.by_severity[k] / max) * 100}%`, height: "100%", background: color, borderRadius: 4 }} /></span>
                        <strong className="num">{s.by_severity[k]}</strong>
                      </div>
                    );
                  })}
                </div>
              )}
            </Panel>
            <Panel title="Recent evaluation activity" aside={<Link className="lnk" href="/runs">All runs →</Link>} empty={s.recent_runs.length ? undefined : "No evaluation runs yet."}>
              {s.recent_runs.length > 0 && s.recent_runs.map((r) => (
                <Link key={r.id} href={`/runs/view?id=${r.id}`} className="row" style={{ textDecoration: "none", color: "var(--tx)" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500 }}>{r.system} <span className="mono mu">{r.version}</span></div>
                    <div className="mu" style={{ fontSize: 12 }}>{when(r.started_at)} · {r.suite}{r.pass_rate !== null ? ` · ${pct(r.pass_rate)}` : ""}</div>
                  </div>
                  {r.critical_failures > 0 && <span className="chip cr"><span className="gl tri" aria-hidden />{r.critical_failures} critical</span>}
                  <RunStatusChip status={r.status} />
                </Link>
              ))}
            </Panel>
            <Panel title="Pending human validations" aside={<span className="mu" style={{ fontSize: 12 }}>{s.pending_reviews} case{s.pending_reviews === 1 ? "" : "s"}</span>}
              empty={s.pending_reviews ? undefined : "No cases are waiting for a reviewer."}>
              {s.pending_reviews > 0 && (
                <div className="row"><div style={{ flex: 1 }}>{s.pending_reviews} evaluated case{s.pending_reviews === 1 ? "" : "s"} are flagged for human review.
                  <div className="mu" style={{ fontSize: 12 }}>The reviewer workspace itself arrives in the next phase; open a run to see which cases are flagged and why.</div></div>
                  <Link className="btn sm" href="/runs">Open runs</Link></div>
              )}
            </Panel>
          </div>
        </>
      )}
      <Disclaimer />
    </Page>
  );
}

function Attention({ s }: { s: Summary }) {
  type Item = { tone: "cr" | "wn" | "ne"; shape: "tri" | "dia" | "sq"; label: string; body: React.ReactNode; href: string; cta: string };
  const items: Item[] = [];
  if (s.critical_failures)
    items.push({ tone: "cr", shape: "tri", label: "Blocked", href: "/runs", cta: "Inspect",
      body: <><strong>{s.critical_failures} critical failure{s.critical_failures === 1 ? "" : "s"}</strong> recorded. A critical failure blocks a release regardless of the average score.</> });
  if (s.pending_reviews)
    items.push({ tone: "wn", shape: "dia", label: "Review", href: "/reviews", cta: "Start reviewing",
      body: <><strong>{s.pending_reviews} case{s.pending_reviews === 1 ? "" : "s"}</strong> await a medical reviewer.</> });
  for (const n of s.never_evaluated.slice(0, 3))
    items.push({ tone: "ne", shape: "sq", label: "Not run", href: "/systems", cta: "Open",
      body: <><strong>{n}</strong> has never been evaluated.</> });

  if (!items.length)
    return (
      <section className="card" aria-label="Needs your attention" style={{ padding: "16px 20px" }}>
        <h2 className="h2">Needs your attention</h2>
        <p className="mu" style={{ margin: "4px 0 0" }}>Nothing needs attention right now.</p>
      </section>
    );
  const hot = items.some((i) => i.tone === "cr");
  return (
    <section className="card" aria-labelledby="na" style={hot ? { borderColor: "var(--cr)" } : undefined}>
      <div className="hd" style={{ paddingBottom: 12 }}>
        <h2 className="h2" id="na">Needs your attention · {items.length} action{items.length === 1 ? "" : "s"}</h2>
      </div>
      {items.map((i, k) => (
        <div className="row" key={k}>
          <span style={{ width: 86, display: "inline-flex", justifyContent: "center" }}><Chip tone={i.tone} shape={i.shape}>{i.label}</Chip></span>
          <div style={{ flex: 1, minWidth: 0 }}>{i.body}</div>
          <Link className="btn sm" href={i.href}>{i.cta}</Link>
        </div>
      ))}
    </section>
  );
}
