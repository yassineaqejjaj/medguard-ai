import Link from "next/link";
import type { ReactNode } from "react";

export type Tone = "cr" | "wn" | "ok" | "ne" | "ac";
export type Shape = "tri" | "dia" | "dot" | "sq" | "xx";

/** Every status is label + shape + colour (design principle: never colour alone). */
export function Chip({ tone, shape, children }: { tone: Tone; shape?: Shape; children: ReactNode }) {
  return (
    <span className={`chip ${tone}`}>
      {shape && <span className={`gl ${shape}`} aria-hidden />}
      {children}
    </span>
  );
}

export const SEVERITY: Record<string, { tone: Tone; shape: Shape; label: string }> = {
  critical: { tone: "cr", shape: "tri", label: "Critical" },
  high: { tone: "wn", shape: "dia", label: "High" },
  medium: { tone: "ac", shape: "sq", label: "Medium" },
  low: { tone: "ne", shape: "dot", label: "Low" },
};

export const GATE: Record<string, { tone: Tone; shape: Shape; label: string }> = {
  PASS: { tone: "ok", shape: "dot", label: "PASS" },
  FAIL: { tone: "cr", shape: "tri", label: "FAIL" },
  REVIEW_REQUIRED: { tone: "wn", shape: "dia", label: "REVIEW REQUIRED" },
};

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, letterSpacing: "-0.02em", lineHeight: "32px" }}>{title}</h1>
        {subtitle && <p className="mu" style={{ margin: "4px 0 0" }}>{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Kpi({ label, value, note, href, tone }: { label: string; value: ReactNode; note?: ReactNode; href: string; tone?: "cr" | "wn" }) {
  return (
    <Link href={href} className="card kpi" style={tone === "cr" ? { borderColor: "var(--cr)" } : undefined}>
      <span className="lbl">{label}</span>
      <span className="num" style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.1, color: tone === "cr" ? "var(--cr)" : undefined }}>{value}</span>
      {note && <span className="mu" style={{ fontSize: 12 }}>{note}</span>}
    </Link>
  );
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="card" style={{ padding: "32px 24px", textAlign: "center" }}>
      <div style={{ fontWeight: 600, fontSize: 15 }}>{title}</div>
      <p className="mu" style={{ margin: "6px auto 0", maxWidth: 520 }}>{children}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function Disclaimer() {
  return (
    <p className="mu" style={{ margin: 0, fontSize: 12, maxWidth: 760 }}>
      A PASS means a version met the criteria configured for its campaign. It is not a guarantee of clinical safety or a
      regulatory certification, and it does not replace medical experts.
    </p>
  );
}

/** Honest placeholder for a designed screen whose backend module is not built yet. */
export function NotBuilt({ what, phase, children }: { what: string; phase: string; children: ReactNode }) {
  return (
    <EmptyState title={`${what} is not available yet`}>
      {children} <span className="mono">({phase})</span>
    </EmptyState>
  );
}

export function SeverityChip({ severity }: { severity: string }) {
  const m = SEVERITY[severity] ?? SEVERITY.low;
  return <Chip tone={m.tone} shape={m.shape}>{m.label}</Chip>;
}

const ITEM: Record<string, { tone: Tone; shape: Shape; label: string }> = {
  passed: { tone: "ok", shape: "dot", label: "Passed" },
  failed: { tone: "cr", shape: "xx", label: "Failed" },
  error: { tone: "cr", shape: "xx", label: "Error" },
  pending: { tone: "ne", shape: "sq", label: "Pending" },
};
export function ItemStatusChip({ status }: { status: string }) {
  const m = ITEM[status] ?? ITEM.pending;
  return <Chip tone={m.tone} shape={m.shape}>{m.label}</Chip>;
}

const RUN: Record<string, { tone: Tone; shape: Shape; label: string }> = {
  queued: { tone: "ne", shape: "sq", label: "Queued" },
  running: { tone: "ac", shape: "dot", label: "Running" },
  completed: { tone: "ok", shape: "dot", label: "Completed" },
  failed: { tone: "cr", shape: "xx", label: "Failed" },
};
export function RunStatusChip({ status }: { status: string }) {
  const m = RUN[status] ?? RUN.queued;
  return <Chip tone={m.tone} shape={m.shape}>{m.label}</Chip>;
}

export { pct } from "@/lib/format";
export const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");
