"use client";
import { useState } from "react";
import { api, ApiError, JUDGE_CRITERIA, type CaseIn, type CaseRow, type Severity } from "@/lib/api";
import { Dialog, Field } from "./Dialog";

const DEFAULT_PC = { require_json: true, required_fields: ["answer", "citations"], require_citations: false };

export function CaseEditor({ suiteId, existing, onClose, onSaved }: { suiteId: string; existing: CaseRow | null; onClose: () => void; onSaved: () => void }) {
  const [crit, setCrit] = useState<string[]>(existing?.criteria ?? []);
  const [pc, setPc] = useState(JSON.stringify(existing?.pass_conditions ?? DEFAULT_PC, null, 2));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const get = (k: string) => String(f.get(k) ?? "");
    let pass_conditions: Record<string, unknown>;
    try { pass_conditions = JSON.parse(pc); } catch { return setErr("Pass conditions must be valid JSON."); }
    const body: CaseIn = {
      category: get("category").trim(), input: get("input"), reference_context: get("reference_context"),
      expected_behavior: get("expected_behavior"), severity: get("severity") as Severity, criteria: crit, pass_conditions,
    };
    setBusy(true); setErr(null);
    try {
      if (existing) await api(`/cases/${existing.id}`, { method: "PUT", body: JSON.stringify(body) });
      else await api(`/suites/${suiteId}/cases`, { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Request failed");
      setBusy(false);
    }
  }

  return (
    <Dialog title={existing ? `Edit ${existing.case_key} (new version ${existing.version + 1})` : "New scenario"} onClose={onClose} width={720}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", maxHeight: "70vh", paddingRight: 4 }}>
        {existing && <p className="mu" style={{ margin: 0 }}>Saving creates version {existing.version + 1}; earlier runs keep pointing at the version they ran. Editing resets human validation to draft.</p>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 12 }}>
          <Field label="Category" htmlFor="category"><input id="category" name="category" className="inp" required maxLength={80} defaultValue={existing?.category} placeholder="e.g. Citation Accuracy" /></Field>
          <Field label="Severity if it fails" htmlFor="severity">
            <select id="severity" name="severity" className="inp" defaultValue={existing?.severity ?? "medium"}>
              <option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
            </select>
          </Field>
        </div>
        <Field label="Question or test input" htmlFor="input"><textarea id="input" name="input" className="inp" rows={2} required maxLength={8000} defaultValue={existing?.input} /></Field>
        <Field label="Reference document context" htmlFor="reference_context"><textarea id="reference_context" name="reference_context" className="inp" rows={3} defaultValue={existing?.reference_context} /></Field>
        <Field label="Expected answer or behaviour" htmlFor="expected_behavior"><textarea id="expected_behavior" name="expected_behavior" className="inp" rows={2} defaultValue={existing?.expected_behavior} /></Field>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="lbl" style={{ marginBottom: 6 }}>LLM-judge criteria (optional)</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {JUDGE_CRITERIA.map((c) => (
              <button key={c} type="button" className="fb" aria-pressed={crit.includes(c)} onClick={() => setCrit((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]))}>{c.replace(/_/g, " ")}</button>
            ))}
          </div>
        </fieldset>
        <Field label="Deterministic pass conditions (JSON)" htmlFor="pc">
          <textarea id="pc" className="inp mono" rows={8} value={pc} onChange={(e) => setPc(e.target.value)} spellCheck={false} />
        </Field>
        <p className="mu" style={{ margin: 0, fontSize: 12 }}>
          Keys: require_json, required_fields, require_citations, reference_sections, must_contain, must_not_contain, max_chars, max_latency_ms, forbidden_sensitive. Unknown keys are rejected.
        </p>
        {err && <div role="alert" style={{ color: "var(--cr)", fontWeight: 500 }}>{err}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn pri" disabled={busy}>{busy ? "Saving…" : "Save scenario"}</button>
        </div>
      </form>
    </Dialog>
  );
}
