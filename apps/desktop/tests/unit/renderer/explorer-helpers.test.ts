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
    expect(resolveAddress("LOCALHOST/app")).toBe("http://LOCALHOST/app");
  });

  it("uses http for IP literals, .local hosts and any host with an explicit port", () => {
    expect(resolveAddress("127.0.0.1:5173")).toBe("http://127.0.0.1:5173");
    expect(resolveAddress("192.168.0.4/status")).toBe("http://192.168.0.4/status");
    expect(resolveAddress("10.0.0.2")).toBe("http://10.0.0.2");
    expect(resolveAddress("[::1]:3000/x")).toBe("http://[::1]:3000/x");
    expect(resolveAddress("myhost.local:3000")).toBe("http://myhost.local:3000");
    expect(resolveAddress("printer.local")).toBe("http://printer.local");
    expect(resolveAddress("example.com:3000/a")).toBe("http://example.com:3000/a");
    expect(resolveAddress("example.local.com")).toBe("https://example.local.com");
    expect(resolveAddress("1.2.3.example.com")).toBe("https://1.2.3.example.com");
  });

  it("keeps https on TLS ports, and treats word:port as a dev host", () => {
    expect(resolveAddress("example.com:443")).toBe("https://example.com:443");
    expect(resolveAddress("example.com:8443/a")).toBe("https://example.com:8443/a");
    expect(resolveAddress("192.168.0.4:443")).toBe("https://192.168.0.4:443");
    expect(resolveAddress("devbox:8080")).toBe("http://devbox:8080");
    expect(resolveAddress("web:3000/api?x=1")).toBe("http://web:3000/api?x=1");
    // The accepted cost: a `word:digits` search becomes an address.
    expect(resolveAddress("note:1")).toBe("http://note:1");
    expect(resolveAddress("note:a")).toMatch(/^https:\/\/duckduckgo\.com\//);
    expect(resolveAddress("devbox")).toMatch(/^https:\/\/duckduckgo\.com\//);
  });

  it("searches for anything that is not an address", () => {
    expect(resolveAddress("build123d fillet")).toMatch(/^https:\/\/duckduckgo\.com\/\?q=/);
  });

  it("does nothing with an empty field", () => {
    expect(resolveAddress("   ")).toBeNull();
  });
});
