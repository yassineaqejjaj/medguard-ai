"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Moon, Sun } from "lucide-react";
import { useEffect } from "react";
import { NAV } from "./nav";
import type { Me } from "@/lib/api";
import { getManager } from "@/lib/auth";

function initials(s: string) {
  return s.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("") || "?";
}

const ROLE_LABEL: Record<Me["role"], string> = { admin: "Admin", engineer: "AI Engineer", reviewer: "Medical Reviewer", viewer: "Viewer" };

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden>
      <rect width="30" height="30" rx="8" fill="#0D9488" />
      <path d="M11 8H8.5v14H11M19 8h2.5v14H19" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="15" cy="15" r="2.6" fill="#fff" />
    </svg>
  );
}

function ThemeToggle() {
  // No React state: the icon is chosen by CSS from the active theme, so there is no effect-driven re-render.
  const flip = () => {
    const el = document.documentElement;
    const dark = el.dataset.theme ? el.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    el.dataset.theme = next;
    try { localStorage.setItem("mg-theme", next); } catch {}
  };
  return (
    <button onClick={flip} aria-label="Toggle light and dark mode" className="theme-toggle"
      style={{ background: "none", border: 0, color: "#94A3B8", cursor: "pointer", padding: 4 }}>
      <Sun size={16} aria-hidden className="icon-sun" />
      <Moon size={16} aria-hidden className="icon-moon" />
    </button>
  );
}

export function Sidebar({ me }: { me: Me }) {
  const path = usePathname();
  useEffect(() => {
    try {
      const t = localStorage.getItem("mg-theme");
      if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
    } catch {}
  }, []);

  return (
    <nav aria-label="Primary" className="hidden md:flex" style={{ width: 248, flex: "0 0 248px", minHeight: "100vh", background: "var(--nav)",
      color: "var(--navtx)", flexDirection: "column", padding: "20px 12px 16px", gap: 20, position: "sticky", top: 0, alignSelf: "flex-start", height: "100vh", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 6px" }}>
        <Logo />
        <span style={{ fontSize: 17, fontWeight: 700, color: "#fff", letterSpacing: "-0.01em" }}>
          MedGuard <span style={{ color: "#5EEAD4", fontWeight: 600 }}>AI</span>
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", border: "1px solid #22304A", borderRadius: 10 }}>
        <span style={{ width: 28, height: 28, borderRadius: 7, background: "#1B2A44", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "#5EEAD4" }}>{initials(me.org_name)}</span>
        <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.25, minWidth: 0, color: "#fff", fontWeight: 600, fontSize: 14 }}>
          <span className="truncate">{me.org_name}</span>
          <span style={{ fontSize: 12, fontWeight: 400, color: "#94A3B8" }}>Organisation</span>
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: ".06em", color: "#94A3B8", padding: "0 12px 8px" }}>WORKSPACE</div>
        {NAV.map(({ href, label, icon: Icon, later }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} className="ni" aria-current={active ? "page" : undefined}>
              <Icon size={18} strokeWidth={1.8} aria-hidden />
              <span style={{ flex: 1 }}>{label}</span>
              {later && <span style={{ fontSize: 12, fontWeight: 500, border: "1px solid #475569", color: "#CBD5E1", padding: "0 6px", borderRadius: 6 }}>Post-MVP</span>}
            </Link>
          );
        })}
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ borderTop: "1px solid #22304A", paddingTop: 16, display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 36, height: 36, borderRadius: "50%", background: "#1B2A44", color: "#fff", fontSize: 13, fontWeight: 600, display: "inline-flex", alignItems: "center", justifyContent: "center", flex: "none" }}>{initials(me.display_name)}</span>
        <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.3, minWidth: 0, flex: 1 }}>
          <span className="truncate" style={{ color: "#fff", fontSize: 14, fontWeight: 600 }}>{me.display_name}</span>
          <span style={{ fontSize: 12, color: "#94A3B8" }}>Signed in as {ROLE_LABEL[me.role]}</span>
        </span>
        <ThemeToggle />
        <button onClick={() => getManager().signoutRedirect()} aria-label="Sign out" style={{ background: "none", border: 0, color: "#94A3B8", cursor: "pointer", padding: 4 }}>
          <LogOut size={16} aria-hidden />
        </button>
      </div>
    </nav>
  );
}
