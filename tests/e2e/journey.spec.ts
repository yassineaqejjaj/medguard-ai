/**
 * The mandatory demonstration journey, end to end, through the real UI against the real stack:
 * login -> create AI app -> connect HTTP RAG assistant -> import 20 synthetic tests -> run a campaign (worker executes)
 * -> results in the dashboard -> a critical test fails -> a reviewer examines it -> second version tested ->
 * regressions/improvements shown -> release gate status -> report generated and archived.
 * Prerequisites: stack up with `scripts/up.sh --demo --http` (judge not required: judge criteria go to human review).
 */
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { apiAs, login } from "./helpers";

const stamp = Date.now().toString(36);
const APP = `E2E Assistant ${stamp}`;
const SUITE = `E2E suite ${stamp}`;
const SUITE_FILE = path.resolve(__dirname, "../../evaluation/test_suites/medical_rag_demo_v1.json");

async function startRun(page: Page, version: string) {
  await page.goto("/runs");
  await page.getByRole("button", { name: "New evaluation run" }).first().click();
  await page.getByLabel("Application version").selectOption({ label: `${APP} · ${version}` });
  await page.getByLabel("Test suite").selectOption({ label: `${SUITE} · 20 scenarios` });
  const created = page.waitForResponse((r) => r.url().endsWith("/api/v1/runs") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Start run" }).click();
  expect((await created).status()).toBe(201); // do not navigate away before the request completed
}

async function waitCompleted(page: Page, version: string) {
  await page.goto("/runs");
  const row = page.getByRole("row").filter({ hasText: APP }).filter({ hasText: version });
  await expect(row.getByText("Completed")).toBeVisible({ timeout: 90_000 });
  return row;
}

test.describe.serial("demo journey", () => {
  let runV1 = "", runV2 = "";

  test("engineer: connect the assistant, import the suite, evaluate v1 and v2", async ({ browser }) => {
    const { ctx, page } = await login(browser, "engineer");
    // 2-3. create the AI application and connect it over HTTP
    await page.goto("/systems");
    await page.getByRole("button", { name: "Connect AI application" }).first().click();
    await page.getByLabel("Name", { exact: true }).fill(APP);
    await page.getByLabel("Intended use").fill("Guideline search (synthetic demo)");
    await page.getByLabel("Version", { exact: true }).fill("v1.0.0");
    await page.getByLabel("Owner").fill("E2E team");
    await page.getByLabel("Test endpoint URL").fill("http://demo-assistant-v1:9000/ask");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.getByRole("button", { name: APP })).toBeVisible();
    // second version of the same application
    await page.getByRole("button", { name: APP }).click();
    await page.getByRole("tab", { name: "Versions" }).click();
    await page.getByRole("button", { name: "Add version" }).click();
    await page.getByLabel("Version label").fill("v1.1.0");
    await page.getByLabel("Test endpoint URL").fill("http://demo-assistant-v2:9000/ask");
    await page.getByRole("button", { name: "Add version", exact: true }).last().click();
    await expect(page.getByRole("tabpanel").getByRole("cell", { name: "v1.1.0" })).toBeVisible();

    // 4. import the 20 synthetic scenarios
    await page.goto("/test-studio");
    await page.getByRole("button", { name: "New suite" }).first().click();
    await page.getByLabel("Name").fill(SUITE);
    await page.getByRole("button", { name: "Create suite" }).click();
    await page.getByRole("button", { name: "Import" }).click();
    await page.getByLabel("Scenario file").setInputFiles(SUITE_FILE);
    await page.getByRole("button", { name: "Import", exact: true }).last().click();
    await expect(page.getByRole("status")).toContainText("Imported: 20 new scenario");

    // 5-7. run both versions, the worker executes them, results are visible
    await startRun(page, "v1.0.0");
    await waitCompleted(page, "v1.0.0");
    await startRun(page, "v1.1.0");
    const row2 = await waitCompleted(page, "v1.1.0");
    await expect(row2).toContainText("55.0%");
    await expect(row2).toContainText("9"); // failed tests
    runV2 = new URL(await row2.getByRole("link", { name: "Open results" }).getAttribute("href").then((h) => `http://x${h}`)).searchParams.get("id")!;
    const row1 = page.getByRole("row").filter({ hasText: APP }).filter({ hasText: "v1.0.0" });
    runV1 = new URL(await row1.getByRole("link", { name: "Open results" }).getAttribute("href").then((h) => `http://x${h}`)).searchParams.get("id")!;

    // 8. a critical test fails: shown first, with its evidence
    await page.goto(`/runs/view?id=${runV2}`);
    await expect(page.getByText("Critical failures").first()).toBeVisible();
    await page.getByRole("button", { name: "Critical", exact: false }).first().click();
    await expect(page.getByRole("table").getByText("Failed").first()).toBeVisible();
    await expect(page.getByText("Flagged for a human")).toBeVisible();

    // 7. dashboard shows the figures
    await page.goto("/");
    await expect(page.getByText("Pass rate by release")).toBeVisible();
    await expect(page.getByLabel(/Pass rate by release:/)).toBeVisible();
    await ctx.close();
  });

  test("reviewer: examines the critical failure, rejects it, and clears v1's flagged results", async ({ browser }) => {
    const { ctx, page } = await login(browser, "reviewer");
    await page.goto("/reviews");
    const critical = page.getByRole("list", { name: "Cases" }).getByRole("button").filter({ hasText: "Critical" }).first();
    await critical.click();
    await expect(page.getByText("Flagged for a human")).toBeVisible();
    await page.getByRole("button", { name: "Response is not acceptable" }).click();
    await page.getByLabel("Severity of the error").selectOption("critical");
    await page.getByRole("button", { name: "Add annotation" }).click();
    await page.getByLabel("Note").fill("Wrong or invented content in the response");
    await page.getByLabel("Justification (required)").fill("The answer is not supported by the reference document.");
    const saved = page.waitForResponse((r) => r.url().includes("/reviews") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Record decision" }).click();
    expect((await saved).status()).toBe(201);
    // the decided case leaves "To review" and appears under "Resolved" with the recorded decision
    await page.getByRole("tab", { name: "Resolved" }).click();
    await expect(page.getByText("Reviewers agree · not acceptable")).toBeVisible();

    // bulk step through the API (same endpoint the form uses): the reviewer accepts the 10 judge-flagged v1 results
    const queue = await apiAs<{ id: string }[]>(page, "GET", `/reviews/queue?run_id=${runV1}`);
    expect(queue.length).toBe(10);
    for (const it of queue)
      await apiAs(page, "POST", `/run-items/${it.id}/reviews`, { decision: "accept", justification: "Answer matches the reference document." });
    await ctx.close();
  });

  test("engineer: compare versions and evaluate the release gates", async ({ browser }) => {
    const { ctx, page } = await login(browser, "engineer");
    // 11. regressions and improvements
    await page.goto(`/compare?candidate=${runV2}&baseline=${runV1}`);
    await expect(page.getByText("3 new critical regressions")).toBeVisible();
    await expect(page.getByRole("region", { name: "New regressions" })).toContainText("9");
    // 12. the gate produces a status
    await page.goto(`/gates/view?run=${runV2}&baseline=${runV1}`);
    await page.getByRole("button", { name: "Evaluate gate" }).click();
    await expect(page.getByRole("region", { name: "Gate status" })).toContainText("FAIL");
    await expect(page.getByRole("table").first()).toContainText("Critical failures");
    await page.goto(`/gates/view?run=${runV1}`);
    await page.getByRole("button", { name: "Evaluate gate" }).click();
    await expect(page.getByRole("region", { name: "Gate status" })).toContainText("PASS");
    await ctx.close();
  });

  test("admin: signs off v1, a failing gate cannot be released, report archived, audit verified", async ({ browser }) => {
    const { ctx, page } = await login(browser, "admin");
    await page.goto(`/gates/view?run=${runV2}`);
    await expect(page.getByRole("button", { name: "Sign off release" })).toBeDisabled(); // FAIL: release impossible
    await page.goto(`/gates/view?run=${runV1}`);
    await page.getByLabel("Justification (required)").fill("All criteria met; reviewed by the medical reviewer.");
    await page.getByRole("button", { name: "Sign off release" }).click();
    await expect(page.getByText("Release signed off")).toBeVisible();

    // 13. report generated and archived
    await page.goto("/evidence");
    await page.getByLabel("Evaluation run").selectOption({ index: 0 });
    const dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Generate HTML" }).click();
    await expect(page.getByRole("row").filter({ hasText: "HTML" }).first()).toBeVisible();
    await page.getByRole("row").filter({ hasText: "HTML" }).first().getByRole("button", { name: "Download" }).click();
    const file = await dl;
    expect(file.suggestedFilename()).toMatch(/medguard-report-.*\.html/);

    await page.getByRole("tab", { name: "Audit trail" }).click();
    await expect(page.getByText("Hash chain verified")).toBeVisible();
    await expect(page.getByRole("table", { name: "" }).first()).toContainText("release.decision");
    await ctx.close();
  });

  test("tenant and role boundaries hold in the UI", async ({ browser }) => {
    const { ctx, page } = await login(browser, "otherAdmin");
    await page.goto("/systems");
    await expect(page.getByRole("button", { name: APP })).toHaveCount(0); // another organisation's data is invisible
    await ctx.close();
    const v = await login(browser, "viewer");
    await v.page.goto("/systems");
    await expect(v.page.getByRole("button", { name: "Connect AI application" })).toHaveCount(0); // read-only role
    await v.ctx.close();
  });
});
