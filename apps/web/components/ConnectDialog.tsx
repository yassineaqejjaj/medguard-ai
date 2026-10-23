"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type SystemCreate, type SystemRow } from "@/lib/api";

export function ConnectDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (s: SystemRow) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [auth, setAuth] = useState<"none" | "bearer">("none");

  useEffect(() => { ref.current?.showModal(); }, []);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const get = (k: string) => String(f.get(k) ?? "").trim();
    const body: SystemCreate = {
      name: get("name"), purpose: get("purpose"), owner: get("owner"), model_name: get("model_name") || undefined,
      version_label: get("version_label"), endpoint_url: get("endpoint_url"), auth_type: auth,
      auth_secret: auth === "bearer" ? get("auth_secret") : undefined,
    };
    setBusy(true); setErr(null);
    try {
      onCreated(await api<SystemRow>("/systems", { method: "POST", body: JSON.stringify(body) }));
    } catch (x) {
      setErr(x instanceof ApiError && x.status === 422 ? "Please check the fields: the endpoint must be an http(s) URL and a secret is required for bearer authentication." : x instanceof Error ? x.message : "Request failed");
      setBusy(false);
    }
  }

  const field = (id: string, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label htmlFor={id} className="lbl">{label}</label>
      <input id={id} name={id} className="inp" {...props} />
    </div>
  );

  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="cd-title"
      style={{ border: "1px solid var(--bd)", borderRadius: 16, padding: 0, background: "var(--sf)", color: "var(--tx)", width: "min(560px, 94vw)", boxShadow: "0 12px 32px rgba(11,18,32,.18)" }}>
      <form onSubmit={submit} style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 id="cd-title" style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Connect AI application</h2>
        <p className="mu" style={{ margin: 0 }}>Register an assistant reachable over HTTP. Use synthetic data only: do not point MedGuard at a system holding real patient data.</p>
        {field("name", "Name", { required: true, maxLength: 200, autoFocus: true })}
        {field("purpose", "Intended use", { maxLength: 2000, placeholder: "e.g. Guideline search for clinicians" })}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {field("version_label", "Version", { required: true, maxLength: 80, placeholder: "v1.0.0" })}
          {field("model_name", "AI model (if known)", { maxLength: 200 })}
        </div>
        {field("owner", "Owner", { maxLength: 200 })}
        {field("endpoint_url", "Test endpoint URL", { required: true, type: "url", placeholder: "https://assistant.example.test/ask" })}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label htmlFor="auth_type" className="lbl">Endpoint authentication</label>
          <select id="auth_type" className="inp" value={auth} onChange={(e) => setAuth(e.target.value as "none" | "bearer")}>
            <option value="none">None</option><option value="bearer">Bearer token</option>
          </select>
        </div>
        {auth === "bearer" && field("auth_secret", "Bearer token (stored encrypted)", { type: "password", required: true, autoComplete: "off" })}
        {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn" onClick={() => ref.current?.close()}>Cancel</button>
          <button type="submit" className="btn pri" disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
        </div>
      </form>
    </dialog>
  );
}
