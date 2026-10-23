"use client";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "./AuthProvider";
import { Logo, Sidebar } from "./Sidebar";
import { getManager } from "@/lib/auth";

export function AppShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const path = usePathname();

  // The OIDC callback must mount even while anonymous so it can exchange the code.
  if (path.startsWith("/auth/callback")) return <>{children}</>;
  if (auth.status === "loading")
    return (
      <main style={{ padding: 32 }} role="status" aria-label="Loading">
        <div className="skel" style={{ width: 240, height: 20 }} />
        <div className="skel" style={{ width: 420, marginTop: 12 }} />
      </main>
    );
  if (auth.status === "anonymous")
    return (
      <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "var(--bg)" }}>
        <div className="card" style={{ width: "100%", maxWidth: 380, padding: 32, textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "center" }}><Logo size={40} /></div>
          <h1 style={{ margin: "12px 0 0", fontSize: 22, fontWeight: 700 }}>MedGuard <span style={{ color: "var(--ac)" }}>AI</span></h1>
          <p className="mu" style={{ margin: "4px 0 0" }}>Trust every AI decision. Prove every result.</p>
          <button className="btn pri" style={{ marginTop: 24, width: "100%", justifyContent: "center" }} onClick={() => getManager().signinRedirect()}>Sign in</button>
        </div>
      </main>
    );
  if (auth.status === "error")
    return (
      <main style={{ padding: 32 }} role="alert">
        <div className="card" style={{ maxWidth: 520, padding: 24, borderColor: "var(--cr)" }}>
          <h1 className="h2" style={{ color: "var(--cr)" }}>Could not reach the API</h1>
          <p className="mu">{auth.message}</p>
          <button className="btn" onClick={() => getManager().removeUser().then(() => location.reload())}>Sign out and retry</button>
        </div>
      </main>
    );
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg)" }}>
      <Sidebar me={auth.me} />
      <main style={{ flex: 1, minWidth: 0 }}>{children}</main>
    </div>
  );
}
