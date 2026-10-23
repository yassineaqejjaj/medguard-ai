"use client";
import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({ title, onClose, children, width = 560 }: { title: string; onClose: () => void; children: ReactNode; width?: number }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby="dlg-title"
      style={{ border: "1px solid var(--bd)", borderRadius: 16, padding: 0, background: "var(--sf)", color: "var(--tx)", width: `min(${width}px, 94vw)`, maxHeight: "92vh", boxShadow: "0 12px 32px rgba(11,18,32,.18)" }}>
      <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 id="dlg-title" style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{title}</h2>
        {children}
      </div>
    </dialog>
  );
}

export function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label htmlFor={htmlFor} className="lbl">{label}</label>
      {children}
    </div>
  );
}
