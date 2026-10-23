"use client";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Dialog, Field } from "./Dialog";

export function VersionDialog({ systemId, systemName, onClose, onCreated }: { systemId: string; systemName: string; onClose: () => void; onCreated: () => void }) {
  const [auth, setAuth] = useState<"none" | "bearer">("none");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true); setErr(null);
    try {
      await api(`/systems/${systemId}/versions`, { method: "POST", body: JSON.stringify({
        version_label: String(f.get("label")).trim(), endpoint_url: String(f.get("url")).trim(), auth_type: auth,
        auth_secret: auth === "bearer" ? String(f.get("secret")) : undefined }) });
      onCreated();
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Request failed"); setBusy(false); }
  }
  return (
    <Dialog title={`Add a version of ${systemName}`} onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Field label="Version label" htmlFor="vl"><input id="vl" name="label" className="inp" required maxLength={80} placeholder="v1.1.0" autoFocus /></Field>
        <Field label="Test endpoint URL" htmlFor="vu"><input id="vu" name="url" className="inp" type="url" required placeholder="https://assistant.example.test/ask" /></Field>
        <Field label="Endpoint authentication" htmlFor="va">
          <select id="va" className="inp" value={auth} onChange={(e) => setAuth(e.target.value as "none" | "bearer")}><option value="none">None</option><option value="bearer">Bearer token</option></select>
        </Field>
        {auth === "bearer" && <Field label="Bearer token (stored encrypted)" htmlFor="vs"><input id="vs" name="secret" className="inp" type="password" required autoComplete="off" /></Field>}
        {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn pri" disabled={busy}>{busy ? "Adding…" : "Add version"}</button>
        </div>
      </form>
    </Dialog>
  );
}
