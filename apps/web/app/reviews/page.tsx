"use client";
import { useState } from "react";
import { Chip, Disclaimer, EmptyState, PageHeader, SeverityChip, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { ItemDetail } from "@/components/ItemDetail";
import { api, ApiError, type ReviewDetail, type RunItem, type Severity } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Tab = "pending" | "disputed" | "resolved";
type Agreement = { n: number; observed: number | null; kappa: number | null; judge_false_pass: number; judge_false_fail: number; sufficient: boolean; min_samples: number; note: string };
const KINDS = ["citation_error", "unsupported_claim", "safety_issue", "out_of_scope", "technical", "other"] as const;

export default function Reviews() {
  const auth = useAuth();
  const role = auth.status === "ready" ? auth.me.role : "viewer";
  const canReview = role === "reviewer" || role === "admin";
  const [tab, setTab] = useState<Tab>("pending");
  const queue = useApi<RunItem[]>(`/reviews/queue?status=${tab}`);
  const pendingCount = useApi<RunItem[]>("/reviews/queue?status=pending");
  const disputedCount = useApi<RunItem[]>("/reviews/queue?status=disputed");
  const [selId, setSelId] = useState<string | null>(null);
  const sel = queue.data?.find((i) => i.id === selId) ?? queue.data?.[0] ?? null;
  const detail = useApi<ReviewDetail>(sel ? `/run-items/${sel.id}/review` : null);
  const refresh = () => { queue.reload(); pendingCount.reload(); disputedCount.reload(); detail.reload(); };

  return (
    <Page current="Human Reviews">
      <PageHeader title="Human Reviews" subtitle="Results flagged for a qualified reviewer. Critical failures are never closed by the machine: they wait here for an explicit human decision." />
      <div role="tablist" aria-label="Review queue" style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--bd)" }}>
        {([["pending", `To review${pendingCount.data ? ` (${pendingCount.data.length})` : ""}`], ["disputed", `Disputed${disputedCount.data ? ` (${disputedCount.data.length})` : ""}`], ["resolved", "Resolved"]] as const).map(([k, l]) => (
          <button key={k} className="tab" role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setSelId(null); }}>{l}</button>
        ))}
      </div>
      {canReview && <AgreementCard />}
      {queue.error && <ErrorBox message={queue.error} retry={queue.reload} />}
      {queue.loading && <div className="card"><LoadingRows /></div>}
      {queue.data && queue.data.length === 0 && (
        <EmptyState title={tab === "pending" ? "Nothing waiting for review" : tab === "disputed" ? "No disputed case" : "No resolved review yet"}>
          {tab === "pending" ? "Results appear here when the engine flags them: critical failures, low judge confidence, judge errors, or high-severity passes backed by a judge verdict alone." : "Disputed cases need an admin to arbitrate; resolved cases show the final human decision."}
        </EmptyState>
      )}
      {queue.data && queue.data.length > 0 && sel && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 340px) minmax(0, 1fr)", gap: 16, alignItems: "start" }}>
          <ul className="card" aria-label="Cases" style={{ listStyle: "none", margin: 0, padding: 0, overflow: "hidden" }}>
            {queue.data.map((i) => (
              <li key={i.id}>
                <button onClick={() => setSelId(i.id)} aria-pressed={sel.id === i.id}
                  style={{ width: "100%", textAlign: "left", background: sel.id === i.id ? "var(--acbg)" : "none", border: 0, borderBottom: "1px solid var(--bd)", padding: "12px 16px", cursor: "pointer", color: "var(--tx)", font: "inherit" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="mono" style={{ fontWeight: 600 }}>{i.case_key}</span><SeverityChip severity={i.severity} />
                    {i.review_status === "disputed" && <Chip tone="cr" shape="dia">Disputed</Chip>}
                  </div>
                  <div className="mu" style={{ marginTop: 4, fontSize: 13 }}>{i.category}</div>
                  <div style={{ marginTop: 2, fontSize: 13, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{i.question}</div>
                </button>
              </li>
            ))}
          </ul>
          <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
            <ItemDetail item={sel} versionLabel="the application" trail={`${sel.run_id.slice(0, 8)} → ${sel.case_key} v${sel.case_version}`} />
            {detail.data && <ReviewPanel d={detail.data} canReview={canReview} isAdmin={role === "admin"} onDone={refresh} />}
          </div>
        </div>
      )}
      <Disclaimer />
    </Page>
  );
}

function AgreementCard() {
  const a = useApi<Agreement>("/judge/agreement");
  if (!a.data) return null;
  const d = a.data;
  return (
    <section className="card" aria-label="Judge versus human agreement" style={{ padding: "12px 20px", display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
      <div><div className="lbl">LLM judge vs human decisions</div>
        <div className="mu" style={{ fontSize: 13 }}>{d.n === 0 ? "No case has both a judge verdict and a human decision yet." : `${d.n} case${d.n === 1 ? "" : "s"} · agreement ${(d.observed! * 100).toFixed(0)}% · kappa ${d.kappa === null ? "—" : d.kappa.toFixed(2)} · ${d.judge_false_pass} judge pass the human rejected`}</div></div>
      <Chip tone={d.sufficient ? "ok" : "wn"} shape={d.sufficient ? "dot" : "dia"}>{d.sufficient ? "Enough data" : `Fewer than ${d.min_samples} cases: indicative only`}</Chip>
    </section>
  );
}

function ReviewPanel({ d, canReview, isAdmin, onDone }: { d: ReviewDetail; canReview: boolean; isAdmin: boolean; onDone: () => void }) {
  const [decision, setDecision] = useState<"accept" | "reject">("reject");
  const [sev, setSev] = useState<Severity>("high");
  const [notes, setNotes] = useState<{ kind: string; note: string; quote: string }[]>([]);
  const [just, setJust] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const closed = d.status === "arbitrated";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api(`/run-items/${d.item.id}/reviews`, { method: "POST", body: JSON.stringify({
        decision, error_severity: decision === "reject" ? sev : null, justification: just,
        annotations: notes.filter((n) => n.note.trim()).map((n) => ({ kind: n.kind, note: n.note, quote: n.quote || null })) }) });
      setJust(""); setNotes([]);
      onDone();
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
    setBusy(false);
  }
  async function arbitrate(final: "accept" | "reject") {
    const justification = window.prompt(`Arbitration: mark this response as ${final === "accept" ? "acceptable" : "not acceptable"}. Justification (required, 10+ characters):`);
    if (!justification) return;
    try { await api(`/run-items/${d.item.id}/arbitrate`, { method: "POST", body: JSON.stringify({ final_decision: final, justification }) }); onDone(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }

  return (
    <section className="card" aria-labelledby="rv" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h2 className="h2" id="rv" style={{ fontSize: 16 }}>Review</h2>
        {d.status === "agreed" && <Chip tone="ok" shape="dot">Reviewers agree · {d.final_decision === "accept" ? "acceptable" : "not acceptable"}</Chip>}
        {d.status === "disputed" && <Chip tone="cr" shape="dia">Reviewers disagree · admin arbitration needed</Chip>}
        {d.status === "arbitrated" && <Chip tone="ac" shape="sq">Arbitrated · {d.final_decision === "accept" ? "acceptable" : "not acceptable"}</Chip>}
        {d.status === "pending" && <Chip tone="wn" shape="dia">Awaiting a human decision</Chip>}
      </div>
      {d.reviews.length > 0 && (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {d.reviews.map((r) => (
            <li key={r.id} style={{ padding: "10px 0", borderTop: "1px solid var(--bd)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{r.reviewer}</strong>
                <Chip tone={r.decision === "accept" ? "ok" : "cr"} shape={r.decision === "accept" ? "dot" : "xx"}>{r.decision === "accept" ? "Acceptable" : "Not acceptable"}</Chip>
                {r.error_severity && <SeverityChip severity={r.error_severity} />}
                <span className="mu" style={{ fontSize: 12 }}>{when(r.created_at)}</span>
              </div>
              <div style={{ marginTop: 4 }}>{r.justification}</div>
              {r.annotations.map((a, k) => <div key={k} className="mu" style={{ fontSize: 13 }}>• {a.kind.replace(/_/g, " ")}: {a.note}{a.quote ? <> — <span className="mono">{a.quote}</span></> : null}</div>)}
            </li>
          ))}
        </ul>
      )}
      {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
      {d.status === "disputed" && isAdmin && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="btn" onClick={() => arbitrate("accept")}>Arbitrate: acceptable</button>
          <button className="btn" onClick={() => arbitrate("reject")}>Arbitrate: not acceptable</button>
        </div>
      )}
      {canReview && !closed && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12, borderTop: "1px solid var(--bd)", paddingTop: 14 }}>
          <div className="lbl">{d.my_decision ? "Change your decision (history is kept)" : "Your decision"}</div>
          <div role="group" aria-label="Decision" style={{ display: "flex", gap: 8 }}>
            <button type="button" className="fb" aria-pressed={decision === "accept"} onClick={() => setDecision("accept")}>Response is acceptable</button>
            <button type="button" className="fb" aria-pressed={decision === "reject"} onClick={() => setDecision("reject")}>Response is not acceptable</button>
          </div>
          {decision === "reject" && (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxWidth: 220 }}>
                <label htmlFor="esev" className="lbl">Severity of the error</label>
                <select id="esev" className="inp" value={sev} onChange={(e) => setSev(e.target.value as Severity)}>
                  <option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
                </select>
              </div>
              <div>
                <div className="lbl" style={{ marginBottom: 4 }}>Annotate errors</div>
                {notes.map((n, k) => (
                  <div key={k} style={{ display: "grid", gridTemplateColumns: "170px 1fr 1fr", gap: 8, marginBottom: 6 }}>
                    <select aria-label="Error type" className="inp" value={n.kind} onChange={(e) => setNotes((p) => p.map((x, j) => (j === k ? { ...x, kind: e.target.value } : x)))}>
                      {KINDS.map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
                    </select>
                    <input aria-label="Note" className="inp" placeholder="What is wrong" value={n.note} onChange={(e) => setNotes((p) => p.map((x, j) => (j === k ? { ...x, note: e.target.value } : x)))} />
                    <input aria-label="Quote" className="inp" placeholder="Quote from the response (optional)" value={n.quote} onChange={(e) => setNotes((p) => p.map((x, j) => (j === k ? { ...x, quote: e.target.value } : x)))} />
                  </div>
                ))}
                <button type="button" className="btn sm" onClick={() => setNotes((p) => [...p, { kind: "citation_error", note: "", quote: "" }])}>Add annotation</button>
              </div>
            </>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label htmlFor="just" className="lbl">Justification (required)</label>
            <textarea id="just" className="inp" rows={3} value={just} onChange={(e) => setJust(e.target.value)} required minLength={10} />
          </div>
          <div><button className="btn pri" type="submit" disabled={busy}>{busy ? "Saving…" : "Record decision"}</button></div>
        </form>
      )}
      {!canReview && <p className="mu" style={{ margin: 0 }}>Only reviewers and admins can record a review. You can read the decisions here.</p>}
    </section>
  );
}
