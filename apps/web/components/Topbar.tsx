import Link from "next/link";
import type { ReactNode } from "react";

export function Topbar({ org, trail = [], current, children }: { org: string; trail?: { label: string; href: string }[]; current: string; children?: ReactNode }) {
  return (
    <header style={{ background: "var(--bg)", borderBottom: "1px solid var(--bd)", padding: "16px 32px 12px", display: "flex", flexDirection: "column", gap: 12 }}>
      <nav aria-label="Breadcrumb" style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Link href="/" className="mu" style={{ textDecoration: "none" }}>{org}</Link>
        <span className="mu" aria-hidden>/</span>
        {trail.map((t) => (
          <span key={t.href} style={{ display: "contents" }}>
            <Link href={t.href} className="mu" style={{ textDecoration: "none" }}>{t.label}</Link>
            <span className="mu" aria-hidden>/</span>
          </span>
        ))}
        <span aria-current="page" style={{ fontWeight: 600 }}>{current}</span>
      </nav>
      {children}
    </header>
  );
}
