"use client";
import { useState } from "react";
import { PageHeader, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import { useAuth } from "@/components/AuthProvider";
import { api, ApiError, type SettingsOut, type TokenRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function Settings() {
  const auth = useAuth();
  const isAdmin = auth.status === "ready" && auth.me.role === "admin";
  const s = useApi<SettingsOut>("/settings");
  const [days, setDays] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function saveRetention(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setMsg(null);
    try { await api("/settings/retention", { method: "PUT", body: JSON.stringify({ retention_days: Number(days) }) }); setMsg("Retention updated."); s.reload(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  async function purge() {
    if (!window.confirm("Delete stored responses and reports of runs older than the retention period? Decisions and the audit trail are kept. This cannot be undone.")) return;
    setErr(null); setMsg(null);
    try { const r = await api<{ runs: number; objects: number }>("/settings/retention/purge", { method: "POST" }); setMsg(`Purged ${r.objects} stored object(s) from ${r.runs} run(s).`); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  return (
    <Page current="Settings">
      <PageHeader title="Settings" subtitle="Organisation, data retention and CI/CD access." />
      {s.error && <ErrorBox message={s.error} retry={s.reload} />}
      {s.loading && <div className="card"><LoadingRows /></div>}
      {s.data && (
        <section className="card" aria-labelledby="ret" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12, maxWidth: 640 }}>
          <h2 className="h2" id="ret">Data retention · {s.data.org_name}</h2>
          <p className="mu" style={{ margin: 0 }}>Stored application responses and generated reports are deleted after this many days when a purge runs. Run metadata, review and release decisions and the audit trail are kept.</p>
          <form onSubmit={saveRetention} style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label htmlFor="rd" className="lbl">Retention (days)</label>
              <input id="rd" className="inp" type="number" min={1} max={3650} style={{ width: 160 }} disabled={!isAdmin} value={days ?? s.data.retention_days} onChange={(e) => setDays(e.target.value)} />
            </div>
            {isAdmin && <button className="btn pri" type="submit">Save</button>}
            {isAdmin && <button className="btn" type="button" onClick={purge}>Purge expired data now</button>}
          </form>
          {!isAdmin && <p className="mu" style={{ margin: 0 }}>Only admins can change retention.</p>}
          {msg && <div role="status" style={{ color: "var(--ok)" }}>{msg}</div>}
          {err && <div role="alert" style={{ color: "var(--cr)" }}>{err}</div>}
        </section>
      )}
      {isAdmin && <Tokens />}
    </Page>
  );
}

function Tokens() {
  const t = useApi<TokenRow[]>("/tokens");
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try { const r = await api<{ token: string }>("/tokens", { method: "POST", body: JSON.stringify({ name }) }); setCreated(r.token); setName(""); t.reload(); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  async function revoke(id: string) {
    setErr(null);
    if (!window.confirm("Revoke this token? Pipelines using it will stop working.")) return;
    try { await api(`/tokens/${id}`, { method: "DELETE" }); t.reload(); } catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  return (
    <section className="card" aria-labelledby="tk" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
      <h2 className="h2" id="tk">CI/CD tokens</h2>
      <p className="mu" style={{ margin: 0 }}>Read-only tokens (scope <span className="mono">gate:read</span>) let a pipeline fetch a version&rsquo;s release-gate status. They cannot open anything else.</p>
      <form onSubmit={create} style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label htmlFor="tn" className="lbl">Token name</label>
          <input id="tn" className="inp" style={{ width: 260 }} required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. gitlab-ci" />
        </div>
        <button className="btn pri" type="submit">Create token</button>
      </form>
      {created && <div role="status" className="card" style={{ padding: 12, borderColor: "var(--wn)", background: "var(--wnbg)" }}><strong>Copy it now, it is shown once:</strong><div className="mono" style={{ wordBreak: "break-all", marginTop: 4 }}>{created}</div></div>}
      {err && <div role="alert" style={{ color: "var(--cr)" }}>{err}</div>}
      {t.data && t.data.length > 0 && (
        <table className="tbl"><thead><tr><th>Name</th><th>Scopes</th><th>Last used</th><th></th></tr></thead>
          <tbody>{t.data.map((k) => <tr key={k.id}><td>{k.name}</td><td className="mono">{k.scopes.join(", ")}</td><td className="mu">{when(k.last_used_at)}</td><td><button className="btn sm" onClick={() => revoke(k.id)}>Revoke</button></td></tr>)}</tbody></table>
      )}
    </section>
  );
}
