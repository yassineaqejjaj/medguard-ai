/**
 * Builds a clean demo story on a FRESH stack (scripts/down.sh --volumes; scripts/up.sh --demo --http; scripts/seed-demo.sh)
 * and captures the README screenshots into docs/screenshots. The bulk set-up goes through the same API the UI uses.
 */
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { apiAs, login } from "./helpers";

const OUT = path.resolve(__dirname, "../../docs/screenshots");
fs.mkdirSync(OUT, { recursive: true });

type Run = { id: string; status: string };
async function waitRun(page: Page, id: string) {
  for (let i = 0; i < 90; i++) {
    const r = await apiAs<Run>(page, "GET", `/runs/${id}`);
    if (r.status === "completed") return;
    await page.waitForTimeout(1000);
  }
  throw new Error("run did not complete");
}
async function shot(page: Page, url: string, name: string, ready: string | RegExp, full = false) {
  await page.goto(url);
  await expect(page.getByText(ready).first()).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(700); // let charts finish animating
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: full });
}

test("capture the demo story", async ({ browser }) => {
  test.setTimeout(300_000);
  const eng = await login(browser, "engineer");
  const versions = await apiAs<{ id: string; version_label: string; system_name: string }[]>(eng.page, "GET", "/versions");
  const suites = await apiAs<{ id: string; name: string }[]>(eng.page, "GET", "/suites");
  const suite = suites.find((s) => s.name.startsWith("Medical RAG demo"))!;
  const v1 = versions.find((v) => v.system_name === "Demo Clinical Assistant" && v.version_label === "v1.0.0")!;
  const v2 = versions.find((v) => v.system_name === "Demo Clinical Assistant" && v.version_label === "v1.1.0")!;

  // Campaigns: v1.0.0 (behaves) then v1.1.0 (regressions)
  const r1 = await apiAs<Run>(eng.page, "POST", "/runs", { system_version_id: v1.id, suite_id: suite.id });
  await waitRun(eng.page, r1.id);
  const r2 = await apiAs<Run>(eng.page, "POST", "/runs", { system_version_id: v2.id, suite_id: suite.id });
  await waitRun(eng.page, r2.id);

  // Reviewer: accepts v1's flagged results, rejects v1.1.0's critical failures with annotations (one left pending on purpose)
  const rev = await login(browser, "reviewer");
  const q1 = await apiAs<{ id: string }[]>(rev.page, "GET", `/reviews/queue?run_id=${r1.id}`);
  for (const it of q1) await apiAs(rev.page, "POST", `/run-items/${it.id}/reviews`, { decision: "accept", justification: "Answer matches the reference document." });
  const q2 = await apiAs<{ id: string; severity: string; case_key: string }[]>(rev.page, "GET", `/reviews/queue?run_id=${r2.id}`);
  const crit = q2.filter((i) => i.severity === "critical");
  for (const it of crit.slice(0, 2))
    await apiAs(rev.page, "POST", `/run-items/${it.id}/reviews`, { decision: "reject", error_severity: "critical",
      justification: "The response is not supported by the reference document.",
      annotations: [{ kind: "citation_error", note: "Cites a section that does not exist or invents content", quote: "§9.9" }] });

  // Gates, release sign-off, reports
  const g2 = await apiAs<{ id: string }>(eng.page, "POST", `/runs/${r2.id}/gate`, { baseline_run_id: r1.id });
  const g1 = await apiAs<{ id: string }>(eng.page, "POST", `/runs/${r1.id}/gate`, {});
  const adm = await login(browser, "admin");
  await apiAs(adm.page, "POST", `/gates/${g1.id}/decision`, { decision: "release", justification: "All mandatory criteria met and every flagged result reviewed." });
  await apiAs(adm.page, "POST", `/gates/${g2.id}/decision`, { decision: "block", justification: "Three critical regressions against v1.0.0." });
  await apiAs(eng.page, "POST", `/runs/${r1.id}/reports?format=html`);
  await apiAs(eng.page, "POST", `/runs/${r2.id}/reports?format=json`);

  // Screenshots (engineer unless stated)
  const p = eng.page;
  await shot(p, "/", "01-overview", "Pass rate by release");
  await shot(p, "/systems", "02-ai-systems", "Demo Clinical Assistant");
  await p.getByRole("button", { name: "Demo Clinical Assistant" }).click();
  await p.getByRole("tab", { name: "Versions" }).click();
  await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(OUT, "03-application-versions.png"), fullPage: true });
  await shot(p, "/test-studio", "04-test-studio", "TC-0001");
  await shot(p, "/runs", "05-evaluation-runs", "Open results");
  await shot(p, `/runs/view?id=${r2.id}`, "06-evaluation-results", "Scenarios");
  await shot(rev.page, "/reviews", "07-human-review", "Flagged for a human");
  await shot(p, `/compare?candidate=${r2.id}&baseline=${r1.id}`, "08-version-comparison", "3 new critical regressions", true);
  await shot(p, `/gates/view?run=${r2.id}`, "09-release-gate-fail", "Mandatory criteria", true);
  await shot(p, `/gates/view?run=${r1.id}`, "10-release-gate-pass", "Mandatory criteria", true);
  await shot(adm.page, "/evidence", "11-evidence-center", "Manifest SHA-256");
  await adm.page.getByRole("tab", { name: "Audit trail" }).click();
  await expect(adm.page.getByText("Hash chain verified")).toBeVisible();
  await adm.page.screenshot({ path: path.join(OUT, "12-audit-trail.png") });
  await shot(adm.page, "/settings", "13-settings", "Data retention");
  // dark mode
  await p.goto("/");
  await expect(p.getByText("Pass rate by release")).toBeVisible();
  await p.getByRole("button", { name: "Toggle light and dark mode" }).click();
  await p.waitForTimeout(900);
  await p.screenshot({ path: path.join(OUT, "14-overview-dark.png") });
  for (const c of [eng.ctx, rev.ctx, adm.ctx]) await c.close();
});
