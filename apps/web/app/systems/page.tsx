"use client";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Chip, EmptyState, PageHeader } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { ConnectDialog } from "@/components/ConnectDialog";
import { VersionDialog } from "@/components/VersionDialog";
import { GatePolicyForm } from "@/components/GatePolicyForm";
import type { SystemRow, VersionRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Filter = "all" | "never" | "evaluated";
const TABS = ["Overview", "Versions", "Evaluations", "Test suites", "Configuration", "Evidence"] as const;

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "Never");

function Systems() {
  const auth = useAuth();
  const params = useSearchParams();
  const { data, error, loading, reload } = useApi<SystemRow[]>("/systems");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selId, setSelId] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  const [dialog, setDialog] = useState(params.get("connect") === "1");
  const [addVersion, setAddVersion] = useState(false);
  const isAdmin = auth.status === "ready" && auth.me.role === "admin";
  const canConnect = auth.status === "ready" && (auth.me.role === "admin" || auth.me.role === "engineer");

  const rows = useMemo(() => (data ?? []).filter((r) =>
    r.name.toLowerCase().includes(q.trim().toLowerCase()) &&
    (filter === "all" || (filter === "never" ? r.run_count === 0 : r.run_count > 0))), [data, q, filter]);
  const counts = { all: data?.length ?? 0, never: (data ?? []).filter((r) => r.run_count === 0).length };
  const sel = (data ?? []).find((r) => r.id === selId) ?? null;

  return (
    <Page current="AI Systems">
      <PageHeader title="AI Systems" subtitle="Every application registered for evaluation, with its current version and release posture."
        actions={canConnect && <button className="btn pri" onClick={() => setDialog(true)}>Connect AI application</button>} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
        <div style={{ flex: "1 1 280px", maxWidth: 380 }}>
          <label htmlFor="q" className="sr-only">Filter applications by name</label>
          <input id="q" className="inp" type="search" placeholder="Filter by application name" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div role="group" aria-label="Filter by evaluation status" style={{ display: "flex", gap: 8 }}>
          {([["all", "All"], ["never", "Not evaluated"], ["evaluated", "Evaluated"]] as const).map(([k, label]) => (
            <button key={k} className="fb" type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {label} {k !== "evaluated" && <span className="mu">{counts[k]}</span>}
            </button>
          ))}
        </div>
      </div>
      {error && <ErrorBox message={error} retry={reload} />}
      {loading && <div className="card"><LoadingRows /></div>}
      {data && data.length === 0 && (
        <EmptyState title="No AI application connected yet" action={canConnect && <button className="btn pri" onClick={() => setDialog(true)}>Connect AI application</button>}>
          Register an assistant or RAG system reachable over HTTP to start evaluating it with synthetic test scenarios.
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <section className="card" aria-label="Registered AI systems" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Application</th><th>Intended use</th><th>Version</th><th>AI model</th><th>Last evaluation</th><th>Evaluation status</th><th>Owner</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} style={selId === r.id ? { background: "var(--acbg)" } : undefined}>
                    <td><button type="button" onClick={() => { setSelId(r.id); setTab("Overview"); }} aria-pressed={selId === r.id}
                      style={{ background: "none", border: 0, padding: 0, font: "inherit", fontWeight: 600, color: "var(--ac)", cursor: "pointer", textAlign: "left" }}>{r.name}</button></td>
                    <td className="mu">{r.purpose || "—"}</td>
                    <td className="mono">{r.latest_version ?? "—"}</td>
                    <td>{r.model_name ?? "—"}</td>
                    <td className="mu">{fmt(r.last_run_at)}</td>
                    <td>{r.run_count ? <Chip tone="ac" shape="dot">{r.run_count} run{r.run_count === 1 ? "" : "s"}</Chip> : <Chip tone="ne" shape="sq">NOT EVALUATED</Chip>}</td>
                    <td>{r.owner || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length === 0 && (
            <div style={{ padding: 24, textAlign: "center" }}>
              <div style={{ fontWeight: 600 }}>No application matches these filters</div>
              <p className="mu" style={{ margin: "4px 0 12px" }}>Clear the filters, or connect a new application to start evaluating it.</p>
              <button className="btn" onClick={() => { setQ(""); setFilter("all"); }}>Clear filters</button>
            </div>
          )}
        </section>
      )}
      {sel && (
        <section className="card" aria-labelledby="dt">
          <div className="hd" style={{ paddingBottom: 12 }}>
            <div>
              <div className="lbl">Application detail</div>
              <h2 className="h2" id="dt" style={{ fontSize: 18 }}>{sel.name} <span className="mono mu">{sel.latest_version}</span></h2>
            </div>
          </div>
          <div role="tablist" aria-label="Application sections" style={{ display: "flex", gap: 4, padding: "0 12px", borderBottom: "1px solid var(--bd)" }}>
            {TABS.map((t) => <button key={t} className="tab" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>)}
          </div>
          <div role="tabpanel" style={{ padding: 20 }}>
            {tab === "Overview" && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
                  {[["Latest pass rate", "—"], ["Evaluation runs", String(sel.run_count)], ["Last evaluation", fmt(sel.last_run_at)], ["Registered", fmt(sel.created_at)]].map(([l, v]) => (
                    <div className="card" key={l} style={{ padding: 14 }}><div className="lbl">{l}</div><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></div>
                  ))}
                </div>
                <p className="mu"><strong style={{ color: "var(--tx)" }}>Intended use.</strong> {sel.purpose || "Not provided"}. Owned by {sel.owner || "—"}; model {sel.model_name ?? "unknown"}.</p>
              </>
            )}
            {tab === "Configuration" && (
              <dl style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: "8px 16px", margin: 0 }}>
                <dt className="mu">Version</dt><dd className="mono" style={{ margin: 0 }}>{sel.latest_version}</dd>
                <dt className="mu">AI model</dt><dd style={{ margin: 0 }}>{sel.model_name ?? "—"}</dd>
                <dt className="mu">Owner</dt><dd style={{ margin: 0 }}>{sel.owner || "—"}</dd>
                <dt className="mu">Identifier</dt><dd className="mono" style={{ margin: 0 }}>{sel.id}</dd>
              </dl>
            )}
            {tab === "Configuration" && <div style={{ marginTop: 24 }}><GatePolicyForm systemId={sel.id} canEdit={isAdmin} /></div>}
            {tab === "Versions" && <VersionsTab systemId={sel.id} canAdd={canConnect} onAdd={() => setAddVersion(true)} key={`${sel.id}-${sel.latest_version}`} />}
            {tab !== "Overview" && tab !== "Configuration" && tab !== "Versions" && (
              <p className="mu" style={{ margin: 0 }}>
                {tab} will list real data once the evaluation engine and release gate modules are built. Nothing is shown here until then.
              </p>
            )}
          </div>
        </section>
      )}
      {addVersion && sel && <VersionDialog systemId={sel.id} systemName={sel.name} onClose={() => setAddVersion(false)} onCreated={() => { setAddVersion(false); reload(); }} />}
      {dialog && <ConnectDialog onClose={() => setDialog(false)} onCreated={() => { setDialog(false); reload(); }} />}
    </Page>
  );
}

export default function Page_() {
  return <Suspense fallback={null}><Systems /></Suspense>;
}

function VersionsTab({ systemId, canAdd, onAdd }: { systemId: string; canAdd: boolean; onAdd: () => void }) {
  const v = useApi<VersionRow[]>(`/versions?system_id=${systemId}`);
  if (v.loading) return <LoadingRows />;
  if (v.error) return <ErrorBox message={v.error} retry={v.reload} />;
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span className="mu">Each version has its own test endpoint. Runs and gates are per version.</span>
        {canAdd && <button className="btn sm pri" onClick={onAdd}>Add version</button>}
      </div>
      <table className="tbl">
        <thead><tr><th>Version</th><th>Endpoint</th><th>Runs</th><th>Last run</th></tr></thead>
        <tbody>{(v.data ?? []).map((x) => (
          <tr key={x.id}><td className="mono">{x.version_label}</td><td className="mono mu" style={{ wordBreak: "break-all" }}>{x.endpoint_url}</td><td className="num">{x.run_count}</td><td className="mu">{fmt(x.last_run_at)}</td></tr>))}
        </tbody>
      </table>
    </div>
  );
}
