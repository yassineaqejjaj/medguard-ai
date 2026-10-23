import { describe, expect, it } from "vitest";
import { NAV } from "@/components/nav";

describe("navigation", () => {
  it("has unique routes and every route has a page", async () => {
    const hrefs = NAV.map((n) => n.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    const { existsSync } = await import("node:fs");
    for (const h of hrefs) expect(existsSync(`app${h === "/" ? "" : h}/page.tsx`), h).toBe(true);
  });
});
