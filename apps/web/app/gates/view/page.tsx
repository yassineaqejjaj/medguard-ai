"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Chip, Disclaimer, GATE, Kpi, pct, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { api, ApiError, type GateEval, type Run } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const LEAD: Record<string, string> = {
  PASS: "Every mandatory criterion is met and no flagged result is waiting for a human. This is an input to the release decision, not the decision.",
  FAIL: "At least one blocking criterion failed. This cannot be offset by a good average or overridden here; fix the cause and evaluate a new run.",
  REVIEW_REQUIRED: "No blocking criterion failed, but results flagged for human review are still open. Resolve them in Human Reviews, then evaluate again.",
};

function Gate() {
  const params = useSearchParams();
  const runId = params.get("run");
  const baseline = params.get("baseline");
  const auth = useAuth();
  const role = auth.status === "ready" ? auth.me.role : "viewer";
  const run = useApi<Run>(`/runs/${runId}`);
  const [tick, setTick] = useState(0);
  const gate = useApi<GateEval>(`/runs/${runId}/gate?t=${tick}`);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [just, setJust] = useState("");
  const g = gate.data;
  const r = run.data;
  const notGated = !gate.loading && !gate.error && gate.data === null;
  const canEvaluate = role === "admin" || role === "engineer";

  async function evaluate() {
    setBusy(true); setErr(null);
    try { await api(`/runs/${runId}/gate`, { method: "POST", body: JSON.stringify({ baseline_run_id: baseline }) }); setTick((t) => t + 1); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
    setBusy(false);
  }
  async function decide(decision: "release" | "block") {
    if (!g) return;
    setBusy(true); setErr(null);
    try { await api(`/gates/${g.id}/decision`, { method: "POST", body: JSON.stringify({ decision, justification: just }) }); setJust(""); setTick((t) => t + 1); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
    setBusy(false);
  }

  const m = g ? GATE[g.status] : null;
  return (
    <Page current={r ? `${r.system_name}` : "Gate"} trail={[{ label: "Release Gates", href: "/gates" }]}>
      {run.error && <ErrorBox message={run.error} retry={run.reload} />}
      {(run.loading || gate.loading) && <div className="card"><LoadingRows /></div>}
      {r && (
        <header>
          <div className="lbl">Release gate</div>
          <h1 style={{ margin: "4px 0 0", fontSize: 26, fontWeight: 700, letterSpacing: "-0.02em" }}>Is {r.system_name} {r.version} ready for release?</h1>
          <p className="mu" style={{ margin: "4px 0 0" }}>Run <span className="mono">{r.id.slice(0, 8)}</span> · {r.suite_name} · {when(r.started_at)}</p>
        </header>
      )}
      {r && notGated && (
        <div className="card" style={{ padding: 24 }}>
          <strong>This run has not been gated yet.</strong>
          <p className="mu">{r.status === "completed" ? "Evaluate it against the application's gate policy." : "The run must be completed first."}</p>
          {canEvaluate && r.status === "completed" && <button className="btn pri" onClick={evaluate} disabled={busy}>Evaluate gate</button>}
          {!canEvaluate && <p className="mu">Only engineers and admins can evaluate a gate.</p>}
        </div>
      )}
      {gate.error && <ErrorBox message={gate.error} retry={gate.reload} />}
      {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
      {g && m && (
        <>
          <section className="card" aria-label="Gate status" style={{ padding: 24, borderColor: g.status === "FAIL" ? "var(--cr)" : g.status === "REVIEW_REQUIRED" ? "var(--wn)" : "var(--ok)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <span className={`chip ${m.tone}`} style={{ height: 36, fontSize: 18, padding: "0 14px" }}><span className={`gl ${m.shape}`} style={{ width: 14, height: 14 }} aria-hidden />{m.label}</span>
              <span className="mu">Evaluated {when(g.evaluated_at)}{g.is_latest ? "" : " · superseded by a newer evaluation"}</span>
              <div style={{ flex: 1 }} />
              {canEvaluate && <button className="btn" onClick={evaluate} disabled={busy}>Re-evaluate</button>}
            </div>
            <p style={{ margin: "12px 0 0", maxWidth: 760 }}>{LEAD[g.status]}</p>
          </section>
          <section aria-label="Key figures" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(176px, 1fr))", gap: 12 }}>
            <Kpi label="Pass rate" value={pct(g.details.counts.pass_rate)} href="#criteria" note={`${g.details.counts.total} tests`} />
            <Kpi label="Failed" value={g.details.counts.failed} href="#criteria" />
            <Kpi label="Critical" tone={g.details.counts.critical_failures ? "cr" : undefined} value={g.details.counts.critical_failures} href="#critical" />
            <Kpi label="Open reviews" value={g.details.counts.open_reviews} href="/reviews" />
          </section>
          <section id="criteria" className="card" aria-labelledby="mc" style={{ overflow: "hidden" }}>
            <div className="hd" style={{ paddingBottom: 12 }}><h2 className="h2" id="mc">Mandatory criteria</h2><span className="mu" style={{ fontSize: 12 }}>Policy snapshot taken at evaluation time</span></div>
            <div style={{ overflowX: "auto" }}>
              <table className="tbl">
                <thead><tr><th>Criterion</th><th>Threshold</th><th>Result</th><th>Type</th><th>Status</th></tr></thead>
                <tbody>{g.details.criteria.map((c) => (
                  <tr key={c.name}><td>{c.name}</td><td className="mono">{c.threshold}</td><td className="mono">{c.value}</td><td className="mu">{c.kind === "blocking" ? "Blocking" : "Needs human"}</td>
                    <td>{c.status === "pass" ? <Chip tone="ok" shape="dot">PASS</Chip> : c.status === "fail" ? <Chip tone="cr" shape="xx">FAIL</Chip> : <Chip tone="wn" shape="dia">REVIEW</Chip>}</td></tr>))}
                </tbody>
              </table>
            </div>
          </section>
          <section id="critical" className="card" aria-labelledby="ct">
            <div className="hd" style={{ paddingBottom: 12 }}><h2 className="h2" id="ct">Critical tests</h2><Link className="lnk" href={`/runs/view?id=${g.run_id}`}>Open in results →</Link></div>
            {g.details.critical_tests.length === 0 ? <p className="mu" style={{ margin: 0, padding: "8px 20px 16px", borderTop: "1px solid var(--bd)" }}>0 critical failures. No critical scenario failed or awaits review.</p> :
              g.details.critical_tests.map((t) => (
                <div className="row" key={t.case_key}>
                  <Chip tone="cr" shape="tri">Critical</Chip>
                  <div style={{ flex: 1, minWidth: 0 }}><span className="mono">{t.case_key}</span> {t.question}</div>
                  {t.human_decision ? <Chip tone={t.human_decision === "accept" ? "ok" : "cr"}>{t.human_decision === "accept" ? "Human: acceptable" : "Human: rejected"}</Chip> : t.open_review ? <Chip tone="wn" shape="dia">Review pending</Chip> : <Chip tone="ne">{t.effective}</Chip>}
                </div>))}
          </section>
          {g.is_latest && g.decisions.length === 0 && role === "admin" && (
            <section className="card" aria-labelledby="dc" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
              <h2 className="h2" id="dc">Record the release decision</h2>
              <p className="mu" style={{ margin: 0 }}>Recorded under your name with the justification below; it cannot be edited afterwards.{g.status !== "PASS" ? " Releasing is not possible while the gate is not PASS; you can record a block." : ""}</p>
              <label htmlFor="just" className="lbl">Justification (required)</label>
              <textarea id="just" className="inp" rows={3} value={just} onChange={(e) => setJust(e.target.value)} minLength={10} />
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn pri" disabled={busy || just.trim().length < 10 || g.status !== "PASS"} onClick={() => decide("release")}>Sign off release</button>
                <button className="btn" disabled={busy || just.trim().length < 10} onClick={() => decide("block")}>Block release</button>
              </div>
            </section>
          )}
          <section className="card" aria-labelledby="ci" style={{ padding: 20 }}>
            <h2 className="h2" id="ci">CI/CD integration</h2>
            <p className="mu">Pipelines read this status with a CI token (create one in Settings). Map the exit code in the job: 0 PASS · 1 FAIL · 2 REVIEW_REQUIRED · 3 not evaluated.</p>
            <pre className="mono" style={{ background: "var(--sf2)", padding: 12, borderRadius: 8, overflowX: "auto", margin: 0 }}>{`$ MEDGUARD_TOKEN=… scripts/medguard-gate.sh \\
    --url ${typeof window !== "undefined" ? window.location.origin : ""} \\
    --system "${g.system_name}" --version "${g.version}"
→ ${g.status}  (exit ${{ PASS: 0, FAIL: 1, REVIEW_REQUIRED: 2 }[g.status]})`}</pre>
          </section>
          <section className="card" aria-labelledby="dh" style={{ padding: 20 }}>
            <h2 className="h2" id="dh">Decision history</h2>
            <ul style={{ margin: "8px 0 0", padding: 0, listStyle: "none" }}>
              <li style={{ padding: "6px 0" }}>Gate evaluated: <strong>{m.label}</strong> <span className="mu">· {when(g.evaluated_at)}</span></li>
              {g.decisions.map((d, i) => (
                <li key={i} style={{ padding: "6px 0", borderTop: "1px solid var(--bd)" }}>
                  <strong>{d.decision === "release" ? "Release signed off" : "Release blocked"}</strong> <span className="mu">· {d.by} · {when(d.at)}</span>
                  <div className="mu">{d.justification}</div>
                </li>))}
              {g.decisions.length === 0 && <li className="mu" style={{ padding: "6px 0", borderTop: "1px solid var(--bd)" }}>No release decision recorded yet.</li>}
            </ul>
          </section>
        </>
      )}
      <Disclaimer />
    </Page>
  );
}

export default function Page_() {
  return <Suspense fallback={null}><Gate /></Suspense>;
}
