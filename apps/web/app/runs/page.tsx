"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, PageHeader, RunStatusChip, pct, when } from "@/components/ui";
import { Chip } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { Dialog, Field } from "@/components/Dialog";
import { api, ApiError, type Run, type Suite, type VersionRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function Runs() {
  const auth = useAuth();
  const canRun = auth.status === "ready" && (auth.me.role === "admin" || auth.me.role === "engineer");
  const runs = useApi<Run[]>("/runs");
  const [dialog, setDialog] = useState(false);
  const active = runs.data?.some((r) => r.status === "queued" || r.status === "running");

  const { reload } = runs;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, 3000);  // follow queued/running campaigns until they finish
    return () => clearInterval(t);
  }, [active, reload]);

  return (
    <Page current="Evaluation Runs">
      <PageHeader title="Evaluation Runs" subtitle="Campaigns executed against your applications, with pass rates and critical failures."
        actions={canRun && <button className="btn pri" onClick={() => setDialog(true)}>New evaluation run</button>} />
      {runs.error && <ErrorBox message={runs.error} retry={runs.reload} />}
      {runs.loading && <div className="card"><LoadingRows /></div>}
      {runs.data && runs.data.length === 0 && (
        <EmptyState title="No evaluation run yet" action={canRun && <button className="btn pri" onClick={() => setDialog(true)}>New evaluation run</button>}>
          Launch a campaign to execute a test suite against a connected application. You need at least one application and one suite.
        </EmptyState>
      )}
      {runs.data && runs.data.length > 0 && (
        <section className="card" aria-label="Evaluation runs" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Application</th><th>Suite</th><th>Status</th><th>Pass rate</th><th>Failed</th><th>Critical</th><th>Needs review</th><th>Started</th><th></th></tr></thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id}>
                    <td><strong>{r.system_name}</strong> <span className="mono mu">{r.version}</span></td>
                    <td className="mu">{r.suite_name}</td>
                    <td><RunStatusChip status={r.status} /></td>
                    <td className="num">{r.status === "running" || r.status === "queued" ? `${r.total - r.pending}/${r.total} done` : pct(r.pass_rate)}</td>
                    <td className="num">{r.failed + r.errors}</td>
                    <td>{r.critical_failures ? <Chip tone="cr" shape="tri">{r.critical_failures}</Chip> : <span className="mu">0</span>}</td>
                    <td className="num">{r.needs_review}</td>
                    <td className="mu">{when(r.started_at)}</td>
                    <td><Link className="lnk" href={`/runs/view?id=${r.id}`}>Open results</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {dialog && <NewRun onClose={() => setDialog(false)} onCreated={() => { setDialog(false); runs.reload(); }} />}
    </Page>
  );
}

function NewRun({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const systems = useApi<VersionRow[]>("/versions");
  const suites = useApi<Suite[]>("/suites");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = systems.data && suites.data;
  const none = ready && (systems.data!.length === 0 || suites.data!.length === 0);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setErr(null);
    try {
      await api("/runs", { method: "POST", body: JSON.stringify({ system_version_id: f.get("version"), suite_id: f.get("suite") }) });
      onCreated();
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); setBusy(false); }
  }
  return (
    <Dialog title="New evaluation run" onClose={onClose}>
      {!ready && <LoadingRows />}
      {none && <p className="mu" style={{ margin: 0 }}>Connect an application and create a suite with at least one scenario first.</p>}
      {ready && !none && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Field label="Application version" htmlFor="version">
            <select id="version" name="version" className="inp" required>
              {systems.data!.map((v) => <option key={v.id} value={v.id}>{v.system_name} · {v.version_label}</option>)}
            </select>
          </Field>
          <Field label="Test suite" htmlFor="suite">
            <select id="suite" name="suite" className="inp" required>
              {suites.data!.filter((s) => s.case_count > 0).map((s) => <option key={s.id} value={s.id}>{s.name} · {s.case_count} scenarios</option>)}
            </select>
          </Field>
          <p className="mu" style={{ margin: 0, fontSize: 12 }}>
            The run executes the current version of every scenario that is not rejected, calling the application&rsquo;s endpoint from the worker.
            Use synthetic data only.
          </p>
          {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn pri" disabled={busy}>{busy ? "Starting…" : "Start run"}</button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
