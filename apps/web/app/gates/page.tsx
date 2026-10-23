"use client";
import Link from "next/link";
import { Chip, Disclaimer, EmptyState, GATE, PageHeader, when } from "@/components/ui";
import { ErrorBox, LoadingRows } from "@/components/Panel";
import { Page } from "@/components/Page";
import type { GateRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function Gates() {
  const gates = useApi<GateRow[]>("/gates");
  return (
    <Page current="Release Gates">
      <PageHeader title="Release Gates" subtitle="Is a version ready for release? Gate statuses are computed from blocking criteria; the release decision stays with an authorised person." />
      {gates.error && <ErrorBox message={gates.error} retry={gates.reload} />}
      {gates.loading && <div className="card"><LoadingRows /></div>}
      {gates.data && gates.data.length === 0 && (
        <EmptyState title="No gate evaluated yet" action={<Link className="btn pri" href="/runs">Open evaluation runs</Link>}>
          Open a completed run and choose &ldquo;Open release gate&rdquo; to evaluate it against the application&rsquo;s policy.
        </EmptyState>
      )}
      {gates.data && gates.data.length > 0 && (
        <section className="card" aria-label="Gate evaluations" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Application</th><th>Gate status</th><th>Release decision</th><th>Evaluated</th><th></th></tr></thead>
              <tbody>
                {gates.data.map((g) => {
                  const m = GATE[g.status];
                  return (
                    <tr key={g.id}>
                      <td><strong>{g.system_name}</strong> <span className="mono mu">{g.version}</span></td>
                      <td><Chip tone={m.tone} shape={m.shape}>{m.label}</Chip></td>
                      <td>{g.decision ? <Chip tone={g.decision === "release" ? "ok" : "cr"} shape={g.decision === "release" ? "dot" : "xx"}>{g.decision === "release" ? "Released" : "Blocked"}</Chip> : <span className="mu">No decision yet</span>}</td>
                      <td className="mu">{when(g.evaluated_at)}</td>
                      <td><Link className="lnk" href={`/gates/view?run=${g.run_id}`}>Open gate</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <Disclaimer />
    </Page>
  );
}
