import { describe, expect, it } from "vitest";
import { errorMessage, pct } from "./format";

describe("errorMessage", () => {
  it("passes plain strings through", () => expect(errorMessage({ detail: "Not found" }, "x")).toBe("Not found"));
  it("joins FastAPI validation errors without the 'body' prefix", () =>
    expect(errorMessage({ detail: [{ loc: ["body", "endpoint_url"], msg: "must be http(s)" }] }, "x")).toBe("endpoint_url: must be http(s)"));
  it("explains per-row import failures", () =>
    expect(errorMessage({ detail: { message: "Import rejected: invalid rows", rows: [{ row: 2, errors: ["severity: bad"] }] } }, "x"))
      .toBe("Import rejected: invalid rows: row 2 (severity: bad)"));
  it("falls back to the title, then the fallback", () => {
    expect(errorMessage({ title: "Internal error" }, "x")).toBe("Internal error");
    expect(errorMessage(null, "Bad Gateway")).toBe("Bad Gateway");
  });
});

describe("pct", () => {
  it("never invents a number", () => expect(pct(null)).toBe("—"));
  it("formats one decimal", () => { expect(pct(0.888)).toBe("88.8%"); expect(pct(1)).toBe("100.0%"); });
});
