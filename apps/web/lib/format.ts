/** Turns the API's error bodies (RFC 7807-ish, FastAPI validation arrays, import row errors) into one readable line. */
export function errorMessage(body: unknown, fallback: string): string {
  const b = body as { detail?: unknown; title?: string } | null;
  const d = b?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d)) {
    const o = d as { message?: string; rows?: { row: number; errors: string[] }[] };
    if (o.message) return `${o.message}: ${(o.rows ?? []).map((r) => `row ${r.row} (${r.errors.join("; ")})`).join(", ")}`;
  }
  if (Array.isArray(d)) return d.map((e: { loc: (string | number)[]; msg: string }) => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ");
  return b?.title ?? fallback;
}

export const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);
