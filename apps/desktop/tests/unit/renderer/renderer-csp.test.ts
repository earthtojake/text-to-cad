import { describe, expect, it } from "vitest";

import indexHtml from "@renderer/index.html?raw";

/**
 * The renderer's Content-Security-Policy, as the shipped document declares it.
 *
 * Two things in the embedded viewer run code the page did not load as a file:
 * a STEP's authored animation is compiled into an in-memory module (a `blob:`
 * URL — a `data:` module was the regression that rendered an error in place of
 * the playbar), and the geometry kernels are WebAssembly. The policy admits
 * exactly those — not `data:`, not `unsafe-eval`, not a remote origin — and the
 * feature-recognition worker is the app's own file.
 */
function directives(): Map<string, string[]> {
  const content = /http-equiv="Content-Security-Policy"\s+content="([^"]+)"/.exec(indexHtml)?.[1];
  if (!content) throw new Error("index.html declares no Content-Security-Policy");
  return new Map(content.split(";").map((part) => part.trim().split(/\s+/)).filter((words) => words[0]).map(([name, ...values]) => [name!, values]));
}

describe("the renderer's Content-Security-Policy", () => {
  it("runs its own scripts, compiled WebAssembly and in-memory modules, and nothing else", () => {
    expect(directives().get("script-src")).toEqual(["'self'", "'wasm-unsafe-eval'", "blob:"]);
  });

  it("starts workers only from the app's own files", () => {
    expect(directives().get("worker-src")).toEqual(["'self'"]);
  });

  it("connects to itself and to loopback services only", () => {
    expect(directives().get("connect-src")).toEqual(["'self'", "http://127.0.0.1:*", "ws://127.0.0.1:*"]);
  });
});
