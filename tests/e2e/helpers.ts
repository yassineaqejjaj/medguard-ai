import { expect, type Browser, type BrowserContext, type Page } from "@playwright/test";

// Demo-only credentials, defined in infrastructure/compose/keycloak/medguard-realm.json (synthetic users).
export const USERS = {
  engineer: { name: "engineer@demo.test", pass: "demo-engineer" },
  reviewer: { name: "reviewer@demo.test", pass: "demo-reviewer" },
  admin: { name: "admin@demo.test", pass: "demo-admin" },
  viewer: { name: "viewer@demo.test", pass: "demo-viewer" },
  otherAdmin: { name: "other-admin@other.test", pass: "other-admin" },
} as const;

export async function login(browser: Browser, who: keyof typeof USERS): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log(`[pageerror ${who}]`, e.message));
  page.on("console", (m) => m.type() === "error" && console.log(`[console.error ${who}]`, m.text().slice(0, 300)));
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.locator("#username").fill(USERS[who].name);
  await page.locator("#password").fill(USERS[who].pass);
  await page.locator("#kc-login").click();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible({ timeout: 30_000 });
  return { ctx, page };
}

/** Calls the API as the signed-in user (token taken from the app's own session). Used only for bulk set-up steps. */
export async function apiAs<T = unknown>(page: Page, method: string, path: string, body?: unknown): Promise<T> {
  return page.evaluate(async ({ method, path, body }) => {
    const key = Object.keys(sessionStorage).find((k) => k.startsWith("oidc.user:"))!;
    const token = JSON.parse(sessionStorage.getItem(key)!).access_token;
    const res = await fetch(`/api/v1${path}`, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    if (!res.ok) throw new Error(`${method} ${path} -> ${res.status} ${await res.text()}`);
    return res.status === 204 ? null : res.json();
  }, { method, path, body });
}
