"use client";
import type { ReactNode } from "react";
import { useAuth } from "./AuthProvider";
import { Topbar } from "./Topbar";

/** Page chrome: breadcrumb top bar + padded content column, as in the design. */
export function Page({ current, trail, bar, children }: { current: string; trail?: { label: string; href: string }[]; bar?: ReactNode; children: ReactNode }) {
  const auth = useAuth();
  if (auth.status !== "ready") return null;
  return (
    <>
      <Topbar org={auth.me.org_name} trail={trail} current={current}>{bar}</Topbar>
      <div style={{ padding: "28px 32px 48px", display: "flex", flexDirection: "column", gap: 24 }}>{children}</div>
    </>
  );
}
