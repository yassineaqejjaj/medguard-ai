import type { ReactNode } from "react";

export function Panel({ title, aside, children, empty }: { title: string; aside?: ReactNode; children?: ReactNode; empty?: string }) {
  return (
    <section className="card" aria-label={title} style={{ paddingBottom: 12 }}>
      <div className="hd" style={{ paddingBottom: 12 }}>
        <h2 className="h2">{title}</h2>
        {aside}
      </div>
      {children ?? <p className="mu" style={{ margin: 0, padding: "8px 20px 12px", borderTop: "1px solid var(--bd)" }}>{empty}</p>}
    </section>
  );
}

export function LoadingRows() {
  return (
    <div role="status" aria-label="Loading" style={{ padding: "8px 20px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="skel" /><div className="skel" style={{ width: "80%" }} /><div className="skel" style={{ width: "60%" }} />
    </div>
  );
}

export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="card" style={{ padding: 16, borderColor: "var(--cr)" }}>
      <strong style={{ color: "var(--cr)" }}>Something went wrong</strong>
      <p className="mu" style={{ margin: "4px 0 8px" }}>{message}</p>
      {retry && <button className="btn sm" onClick={retry}>Retry</button>}
    </div>
  );
}
