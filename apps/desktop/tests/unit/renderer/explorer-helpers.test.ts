import { describe, expect, it } from "vitest";

import { resolveAddress } from "@renderer/features/explorer/BrowserTab";

describe("the address bar", () => {
  it("passes a full URL through", () => {
    expect(resolveAddress("https://example.com/a")).toBe("https://example.com/a");
    expect(resolveAddress("http://127.0.0.1:3250")).toBe("http://127.0.0.1:3250");
  });

  it("adds a scheme to a bare host", () => {
    expect(resolveAddress("example.com")).toBe("https://example.com");
    expect(resolveAddress("example.com/path")).toBe("https://example.com/path");
  });

  it("keeps localhost on http, where a dev server actually is", () => {
    expect(resolveAddress("localhost:5273")).toBe("http://localhost:5273");
  });

  it("searches for anything that is not an address", () => {
    expect(resolveAddress("build123d fillet")).toMatch(/^https:\/\/duckduckgo\.com\/\?q=/);
  });

  it("does nothing with an empty field", () => {
    expect(resolveAddress("   ")).toBeNull();
  });
});
