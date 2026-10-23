"use client";
import { useState } from "react";
import { Chip, Disclaimer, EmptyState, PageHeader, pct, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { api, apiDownload, ApiError, type AuditList, type EvidenceRow, type ReportRow, type Run } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Tab = "reports" | "evidence" | "audit";
const kb = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export default function Evidence() {
  const auth = useAuth();
  const role = auth.status === "ready" ? auth.me.role : "viewer";
  const [tab, setTab] = useState<Tab>("reports");
  const tabs: [Tab, string][] = [["reports", "Reports"], ...(role !== "viewer" ? [["evidence", "Stored evidence"] as [Tab, string]] : []), ...(role === "admin" ? [["audit", "Audit trail"] as [Tab, string]] : [])];
  return (
    <Page current="Evidence Center">
      <PageHeader title="Evidence Center" subtitle="Reports, stored responses and the audit trail: what was tested, with which versions and settings, and who decided what." />
      <div role="tablist" aria-label="Evidence sections" style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--bd)" }}>
        {tabs.map(([k, l]) => <button key={k} className="tab" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      {tab === "reports" && <Reports canCreate={role === "admin" || role === "engineer"} />}
      {tab === "evidence" && <Stored />}
      {tab === "audit" && <Audit />}
      <Disclaimer />
    </Page>
  );
}

function Reports({ canCreate }: { canCreate: boolean }) {
  const reports = useApi<ReportRow[]>("/reports");
  const runs = useApi<Run[]>("/runs");
  const [runId, setRunId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const done = (runs.data ?? []).filter((r) => r.status === "completed");
  const target = runId || done[0]?.id || "";

  async function create(format: "html" | "json" | "pdf") {
    setBusy(format); setErr(null);
    try { await api(`/runs/${target}/reports?format=${format}`, { method: "POST" }); reports.reload(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
    setBusy(null);
  }
  return (
    <>
      {canCreate && (
        <section className="card" aria-label="Generate a report" style={{ padding: 20, display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label htmlFor="rr" className="lbl">Evaluation run</label>
            <select id="rr" className="inp" style={{ minWidth: 380 }} value={target} onChange={(e) => setRunId(e.target.value)} disabled={done.length === 0}>
              {done.length === 0 && <option>No completed run</option>}
              {done.map((r) => <option key={r.id} value={r.id}>{r.system_name} {r.version} · {when(r.started_at)} · {pct(r.pass_rate)}</option>)}
            </select>
          </div>
          {(["html", "json", "pdf"] as const).map((f) => <button key={f} className="btn" disabled={!target || busy !== null} onClick={() => create(f)}>{busy === f ? "Generating…" : `Generate ${f.toUpperCase()}`}</button>)}
        </section>
      )}
      {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
      {reports.error && <ErrorBox message={reports.error} retry={reports.reload} />}
      {reports.loading && <div className="card"><LoadingRows /></div>}
      {reports.data && reports.data.length === 0 && <EmptyState title="No report generated yet">Generate an HTML, JSON or PDF report for a completed run. Each report records the run, scenario versions, settings, results, reviews, gate decisions and audit entries, and carries an integrity hash.</EmptyState>}
      {reports.data && reports.data.length > 0 && (
        <section className="card" aria-label="Reports" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Run</th><th>Format</th><th>Size</th><th>Generated</th><th>Manifest SHA-256</th><th></th></tr></thead>
              <tbody>{reports.data.map((r) => (
                <tr key={r.id}><td className="mono">{r.run_label}</td><td><Chip tone="ne">{r.format.toUpperCase()}</Chip></td><td className="num">{kb(r.size)}</td><td className="mu">{when(r.created_at)}</td>
                  <td className="mono mu" title={r.manifest_sha256}>{r.manifest_sha256.slice(0, 16)}…</td>
                  <td><button className="btn sm" onClick={() => apiDownload(`/reports/${r.id}/download`, `medguard-report-${r.run_label}.${r.format}`)}>Download</button></td></tr>))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

function Stored() {
  const ev = useApi<EvidenceRow[]>("/evidence?limit=200");
  return (
    <>
      {ev.error && <ErrorBox message={ev.error} retry={ev.reload} />}
      {ev.loading && <div className="card"><LoadingRows /></div>}
      {ev.data && ev.data.length === 0 && <EmptyState title="No stored evidence">Application responses are stored here, with their SHA-256, each time a scenario runs.</EmptyState>}
      {ev.data && ev.data.length > 0 && (
        <section className="card" aria-label="Stored evidence" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Kind</th><th>Run</th><th>Size</th><th>Stored</th><th>SHA-256</th><th></th></tr></thead>
              <tbody>{ev.data.map((e) => (
                <tr key={e.id}><td>{e.kind}</td><td className="mono">{e.run_id?.slice(0, 8) ?? "—"}</td><td className="num">{kb(e.size)}</td><td className="mu">{when(e.created_at)}</td>
                  <td className="mono mu" title={e.sha256}>{e.sha256.slice(0, 16)}…</td>
                  <td><button className="btn sm" onClick={() => apiDownload(`/evidence/${e.id}/download`, `${e.kind}-${e.id.slice(0, 8)}.json`)}>Download</button></td></tr>))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <p className="mu" style={{ margin: 0, fontSize: 12 }}>Every download re-checks the object against its recorded hash; a mismatch is reported as an integrity error.</p>
    </>
  );
}

function Audit() {
  const [filter, setFilter] = useState("");
  const a = useApi<AuditList>(`/audit?limit=200${filter ? `&action=${encodeURIComponent(filter)}` : ""}`);
  return (
    <>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 240px", maxWidth: 340 }}>
          <label htmlFor="af" className="sr-only">Filter by action prefix</label>
          <input id="af" className="inp" type="search" placeholder="Filter by action, e.g. review." value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        {a.data && (a.data.chain_valid ? <Chip tone="ok" shape="dot">Hash chain verified</Chip> : <Chip tone="cr" shape="xx">Hash chain BROKEN at entry {a.data.first_invalid_id}</Chip>)}
      </div>
      {a.error && <ErrorBox message={a.error} retry={a.reload} />}
      {a.loading && <div className="card"><LoadingRows /></div>}
      {a.data && (
        <section className="card" aria-label="Audit trail" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr></thead>
              <tbody>{a.data.entries.map((e) => (
                <tr key={e.id}><td className="mono">{e.id}</td><td className="mu" style={{ whiteSpace: "nowrap" }}>{when(e.ts)}</td><td>{e.actor ?? "system"}</td><td className="mono">{e.action}</td>
                  <td className="mono mu">{e.entity_type}:{e.entity_id.slice(0, 8)}</td><td className="mono mu" style={{ maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={JSON.stringify(e.detail)}>{e.detail ? JSON.stringify(e.detail) : "—"}</td></tr>))}
              </tbody>
            </table>
          </div>
          {a.data.entries.length === 0 && <div style={{ padding: 20 }} className="mu">No entry matches this filter.</div>}
        </section>
      )}
    </>
  );
}
