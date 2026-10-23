"use client";
import { useEffect, useState } from "react";
import { api, ApiError, type GateRules } from "@/lib/api";
import { Field } from "./Dialog";

export function GatePolicyForm({ systemId, canEdit }: { systemId: string; canEdit: boolean }) {
  const [rules, setRules] = useState<GateRules | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<GateRules>(`/systems/${systemId}/gate-policy`).then(setRules).catch((e) => setErr(e.message)); }, [systemId]);
  if (!rules) return <p className="mu">{err ?? "Loading policy…"}</p>;
  const num = (k: keyof GateRules, v: string, nullable = false) => setRules({ ...rules, [k]: v === "" && nullable ? null : Number(v) } as GateRules);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setMsg(null);
    try { setRules(await api<GateRules>(`/systems/${systemId}/gate-policy`, { method: "PUT", body: JSON.stringify(rules) })); setMsg("Policy saved. Existing evaluations keep the policy they were run with."); }
    catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); }
  }
  return (
    <form onSubmit={save} style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 520 }}>
      <h3 className="h2">Release gate policy</h3>
      <Field label="Maximum critical failures" htmlFor="gp1"><input id="gp1" className="inp" type="number" min={0} disabled={!canEdit} value={rules.max_critical_failures} onChange={(e) => num("max_critical_failures", e.target.value)} /></Field>
      <Field label="Maximum high-severity failures (blank = no limit)" htmlFor="gp2"><input id="gp2" className="inp" type="number" min={0} disabled={!canEdit} value={rules.max_high_failures ?? ""} onChange={(e) => num("max_high_failures", e.target.value, true)} /></Field>
      <Field label="Minimum overall pass rate (0–1)" htmlFor="gp3"><input id="gp3" className="inp" type="number" min={0} max={1} step={0.01} disabled={!canEdit} value={rules.min_pass_rate} onChange={(e) => num("min_pass_rate", e.target.value)} /></Field>
      <Field label="Maximum new regressions vs baseline (blank = no limit)" htmlFor="gp4"><input id="gp4" className="inp" type="number" min={0} disabled={!canEdit} value={rules.max_new_regressions ?? ""} onChange={(e) => num("max_new_regressions", e.target.value, true)} /></Field>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" disabled={!canEdit} checked={rules.require_reviews_resolved} onChange={(e) => setRules({ ...rules, require_reviews_resolved: e.target.checked })} /> Require all flagged results to be reviewed</label>
      {msg && <div role="status" style={{ color: "var(--ok)" }}>{msg}</div>}
      {err && <div role="alert" style={{ color: "var(--cr)" }}>{err}</div>}
      {canEdit ? <div><button className="btn pri" type="submit">Save policy</button></div> : <p className="mu" style={{ margin: 0 }}>Only admins can change the policy.</p>}
    </form>
  );
}
