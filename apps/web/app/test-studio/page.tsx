"use client";
import { useMemo, useRef, useState } from "react";
import { Chip, EmptyState, PageHeader, SeverityChip } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { CaseEditor } from "@/components/CaseEditor";
import { Dialog, Field } from "@/components/Dialog";
import { api, apiDownload, ApiError, type CaseRow, type Suite } from "@/lib/api";
import { useApi } from "@/lib/useApi";


export default function TestStudio() {
  const auth = useAuth();
  const role = auth.status === "ready" ? auth.me.role : "viewer";
  const canEdit = role === "admin" || role === "engineer";
  const canValidate = role === "admin" || role === "reviewer";
  const suites = useApi<Suite[]>("/suites");
  const [selected, setSelected] = useState<string | null>(null);
  const suiteId = selected ?? suites.data?.[0]?.id ?? null;
  const cases = useApi<CaseRow[]>(suiteId ? `/suites/${suiteId}` : null);
  const [q, setQ] = useState("");
  const [sev, setSev] = useState<string>("all");
  const [editor, setEditor] = useState<{ existing: CaseRow | null } | null>(null);
  const [importing, setImporting] = useState(false);
  const [newSuite, setNewSuite] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const suite = suites.data?.find((s) => s.id === suiteId) ?? null;
  const rows = useMemo(() => (suiteId && cases.data ? cases.data : []).filter((c) =>
    (sev === "all" || c.severity === sev) &&
    (`${c.case_key} ${c.category} ${c.input}`.toLowerCase().includes(q.trim().toLowerCase()))), [cases.data, q, sev, suiteId]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setErr(null); setMsg(null);
    try { await fn(); if (ok) setMsg(ok); suites.reload(); cases.reload(); } catch (e) { setErr(e instanceof ApiError ? e.message : "Request failed"); }
  };
  const move = (i: number, d: -1 | 1) => {
    if (!cases.data) return;
    const ids = cases.data.map((c) => c.id);
    [ids[i], ids[i + d]] = [ids[i + d], ids[i]];
    act(() => api(`/suites/${suiteId}/order`, { method: "PUT", body: JSON.stringify({ case_ids: ids }) }));
  };
  const validate = (c: CaseRow, status: "validated" | "rejected") => {
    const justification = window.prompt(`Justification for marking ${c.case_key} as ${status} (required):`);
    if (justification?.trim()) act(() => api(`/cases/${c.id}/validation`, { method: "POST", body: JSON.stringify({ status, justification }) }), `${c.case_key} ${status}`);
  };

  return (
    <Page current="Test Studio">
      <PageHeader title="Test Studio" subtitle="Author, import and export synthetic evaluation scenarios. Every edit creates a new immutable version."
        actions={canEdit && <button className="btn" onClick={() => setNewSuite(true)}>New suite</button>} />
      {suites.error && <ErrorBox message={suites.error} retry={suites.reload} />}
      {suites.loading && <div className="card"><LoadingRows /></div>}
      {suites.data && suites.data.length === 0 && (
        <EmptyState title="No test suite yet" action={canEdit && <button className="btn pri" onClick={() => setNewSuite(true)}>New suite</button>}>
          Create a suite, then add scenarios by hand or import a JSON or CSV file of synthetic cases.
        </EmptyState>
      )}
      {suites.data && suites.data.length > 0 && suite && (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end" }}>
            <Field label="Suite" htmlFor="suite">
              <select id="suite" className="inp" style={{ minWidth: 280 }} value={suiteId ?? ""} onChange={(e) => setSelected(e.target.value)}>
                {suites.data.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.case_count} scenarios</option>)}
              </select>
            </Field>
            <div style={{ flex: 1 }} />
            <button className="btn" onClick={() => act(() => apiDownload(`/suites/${suiteId}/export?format=json`, `${suite.name}.json`))}>Export JSON</button>
            <button className="btn" onClick={() => act(() => apiDownload(`/suites/${suiteId}/export?format=csv`, `${suite.name}.csv`))}>Export CSV</button>
            {canEdit && <button className="btn" onClick={() => setImporting(true)}>Import</button>}
            {canEdit && <button className="btn pri" onClick={() => setEditor({ existing: null })}>New scenario</button>}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
            <div style={{ flex: "1 1 260px", maxWidth: 380 }}>
              <label htmlFor="cq" className="sr-only">Search scenarios</label>
              <input id="cq" className="inp" type="search" placeholder="Search by ID, category or text" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div role="group" aria-label="Filter by severity" style={{ display: "flex", gap: 8 }}>
              {["all", "critical", "high", "medium", "low"].map((s) => (
                <button key={s} className="fb" aria-pressed={sev === s} onClick={() => setSev(s)} style={{ textTransform: "capitalize" }}>{s}</button>
              ))}
            </div>
          </div>
          <div aria-live="polite">
            {msg && <div role="status" style={{ color: "var(--ok)", fontWeight: 500 }}>{msg}</div>}
            {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
          </div>
          {cases.error && <ErrorBox message={cases.error} retry={cases.reload} />}
          <section className="card" aria-label="Scenarios" style={{ overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="tbl">
                <thead><tr><th>ID</th><th>Scenario</th><th>Category</th><th>Severity</th><th>Judge criteria</th><th>Human validation</th><th>Version</th><th>Actions</th></tr></thead>
                <tbody>
                  {rows.map((c) => {
                    const i = cases.data!.findIndex((x) => x.id === c.id);
                    return (
                      <tr key={c.id}>
                        <td className="mono">{c.case_key}</td>
                        <td style={{ maxWidth: 360 }}>{c.input}</td>
                        <td className="mu">{c.category}</td>
                        <td><SeverityChip severity={c.severity} /></td>
                        <td className="mu">{c.criteria.length ? c.criteria.map((x) => x.replace(/_/g, " ")).join(", ") : "—"}</td>
                        <td>{c.validation_status === "validated" ? <Chip tone="ok" shape="dot">Validated</Chip> : c.validation_status === "rejected" ? <Chip tone="cr" shape="xx">Rejected</Chip> : <Chip tone="ne" shape="sq">Draft</Chip>}</td>
                        <td className="mono">v{c.version}</td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {canEdit && <button className="btn sm" onClick={() => setEditor({ existing: c })}>Edit</button>}{" "}
                          {canEdit && <button className="btn sm" onClick={() => act(() => api(`/cases/${c.id}/duplicate`, { method: "POST" }), `${c.case_key} duplicated`)}>Duplicate</button>}{" "}
                          {canEdit && sev === "all" && !q && <>
                            <button className="btn sm" aria-label={`Move ${c.case_key} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>{" "}
                            <button className="btn sm" aria-label={`Move ${c.case_key} down`} disabled={i === cases.data!.length - 1} onClick={() => move(i, 1)}>↓</button>{" "}
                          </>}
                          {canValidate && <button className="btn sm" onClick={() => validate(c, "validated")}>Validate</button>}{" "}
                          {canValidate && <button className="btn sm" onClick={() => validate(c, "rejected")}>Reject</button>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {cases.data && rows.length === 0 && (
              <div style={{ padding: 24, textAlign: "center" }} className="mu">{cases.data.length === 0 ? "This suite has no scenarios yet." : "No scenario matches these filters."}</div>
            )}
          </section>
          <p className="mu" style={{ margin: 0, fontSize: 12 }}>
            {cases.data ? `${cases.data.length} scenarios · ${cases.data.filter((c) => c.severity === "critical").length} critical · ${cases.data.filter((c) => c.validation_status === "validated").length} validated by a reviewer.` : ""}{" "}
            Scenarios in the &ldquo;rejected&rdquo; state are skipped by new runs. Use synthetic data only.
          </p>
        </>
      )}
      {editor && suiteId && <CaseEditor suiteId={suiteId} existing={editor.existing} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); cases.reload(); suites.reload(); }} />}
      {importing && suiteId && <ImportDialog suiteId={suiteId} onClose={() => setImporting(false)} onDone={(m) => { setImporting(false); setMsg(m); cases.reload(); suites.reload(); }} />}
      {newSuite && <SuiteDialog onClose={() => setNewSuite(false)} onCreated={(s) => { setNewSuite(false); setSelected(s.id); suites.reload(); }} />}
    </Page>
  );
}

function ImportDialog({ suiteId, onClose, onDone }: { suiteId: string; onClose: () => void; onDone: (m: string) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    const file = ref.current?.files?.[0];
    if (!file) return setErr("Choose a .json or .csv file.");
    const format = file.name.toLowerCase().endsWith(".csv") ? "csv" : "json";
    setBusy(true); setErr(null);
    try {
      const r = await api<{ created: number; new_versions: number }>(`/suites/${suiteId}/import`, { method: "POST", body: JSON.stringify({ format, content: await file.text() }) });
      onDone(`Imported: ${r.created} new scenario(s), ${r.new_versions} new version(s).`);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Import failed"); setBusy(false); }
  }
  return (
    <Dialog title="Import scenarios" onClose={onClose}>
      <p className="mu" style={{ margin: 0 }}>
        JSON (<span className="mono">{`{"cases": [...]}`}</span>) or CSV with columns category, input, severity and optionally case_key, reference_context, expected_behavior, criteria (semicolon-separated) and pass_conditions (JSON).
        A row whose case_key already exists becomes a new version. The whole file is rejected if any row is invalid.
      </p>
      <input ref={ref} type="file" accept=".json,.csv" aria-label="Scenario file" />
      {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn pri" onClick={go} disabled={busy}>{busy ? "Importing…" : "Import"}</button>
      </div>
    </Dialog>
  );
}

function SuiteDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (s: Suite) => void }) {
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try { onCreated(await api<Suite>("/suites", { method: "POST", body: JSON.stringify({ name: String(f.get("name")).trim(), description: String(f.get("description") ?? "") }) })); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  return (
    <Dialog title="New test suite" onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Field label="Name" htmlFor="sname"><input id="sname" name="name" className="inp" required maxLength={200} autoFocus /></Field>
        <Field label="Description" htmlFor="sdesc"><input id="sdesc" name="description" className="inp" maxLength={4000} /></Field>
        {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn pri">Create suite</button>
        </div>
      </form>
    </Dialog>
  );
}
