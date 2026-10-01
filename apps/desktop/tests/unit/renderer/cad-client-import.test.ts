import { expect, it, vi } from "vitest";
import type { PrepareContext } from "@text-to-cad/ui/file-viewer";
import { CadRuntimeError, createDesktopCadConnection } from "@renderer/features/explorer/adapters/cadRuntime";

/**
 * The CAD client is a chunk of its own, imported with the first CAD file. A
 * chunk that does not load (a packaged app whose asset is gone, a dev server
 * that restarted) is a viewer that did not start, and the CAD tab says so on
 * its failure card — not with the loader's words as an unexpected error.
 */
vi.mock("@text-to-cad/core/client", () => {
  throw new TypeError("Failed to fetch dynamically imported module: core-client.js");
});

function context(): PrepareContext {
  const file = { path: "part.stl", name: "part.stl", kind: "file" as const, extension: "stl", mediaType: "cad", size: 12 };
  return { file, source: { id: "project", rootName: "project", stat: async () => file }, signal: new AbortController().signal };
}

it("reports a CAD client that did not load as the viewer failing, with the loader's words", async () => {
  vi.mocked(window.textToCad.cad.viewerOrigin).mockResolvedValue({ origin: "http://127.0.0.1:3010" });
  const failure = await createDesktopCadConnection("project", null).acquire(context()).catch((error: unknown) => error);
  expect(failure).toBeInstanceOf(CadRuntimeError);
  expect((failure as CadRuntimeError).answer).toMatchObject({ origin: null, reason: "viewer-failed" });
  // Vitest wraps a throwing factory's error in its own; the loader's words follow the prefix.
  expect((failure as CadRuntimeError).answer.message).toMatch(/^The CAD viewer's code did not load: \S/);
});
