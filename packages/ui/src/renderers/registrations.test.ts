import { describe, expect, it, vi } from "vitest";

import type { FileMetadata, FileSource, TextDocument } from "../file-viewer/types.js";
import { selectRenderer } from "../file-viewer/registry.js";
import { languageFor, monacoModelUri } from "./code/editor/monaco.js";
import { codeRenderer } from "./code/index.js";
import { imageRenderer } from "./image/index.js";
import { markdownRenderer } from "./markdown/index.js";
import { pdfRenderer } from "./pdf/index.js";
import { unsupportedRenderer } from "./unsupported/index.js";

const file = (path: string, mediaType: string, mime?: string): FileMetadata => ({
  path,
  name: path.split("/").at(-1) ?? path,
  kind: "file",
  size: 12,
  extension: path.split(".").at(-1)?.toLowerCase() ?? "",
  mediaType,
  mime,
});

const source = (overrides: Partial<FileSource> = {}): FileSource => ({
  id: "root-a",
  rootName: "Fixture",
  stat: async (path) => file(path, "text"),
  ...overrides,
});

describe("non-CAD renderer registrations", () => {
  it("selects specific formats before text and has an explicit fallback", () => {
    const renderers = [codeRenderer, markdownRenderer, imageRenderer, pdfRenderer, unsupportedRenderer];
    expect(selectRenderer(renderers, file("README.md", "text", "text/markdown")).id).toBe("markdown");
    expect(selectRenderer(renderers, file("photo.png", "image", "image/png")).id).toBe("image");
    expect(selectRenderer(renderers, file("paper.pdf", "pdf", "application/pdf")).id).toBe("pdf");
    expect(selectRenderer(renderers, file("main.ts", "text", "text/plain")).id).toBe("code");
    expect(selectRenderer(renderers, file("archive.zip", "binary", "application/zip")).id).toBe("unsupported");
  });

  it("preserves Markdown's preview/source switch", () => {
    expect(markdownRenderer.panels?.({ open: "", ready: true, file: file("README.md", "text") }))
      .toMatchObject([{ id: "source", label: "View source", content: "body" }]);
    expect(markdownRenderer.panels?.({ open: "source", ready: true, file: file("README.md", "text") }))
      .toMatchObject([{ id: "source", label: "View preview", content: "body" }]);
  });

  it("prepares editable text through the source without changing its metadata", async () => {
    const text: TextDocument = { content: "# Exact bytes\n", revision: "r1", truncated: true };
    const readText = vi.fn(async () => text);
    const prepared = await markdownRenderer.prepare({
      file: file("README.md", "text"),
      source: source({ readText }),
      signal: new AbortController().signal,
    });
    expect(readText).toHaveBeenCalledWith("README.md", { signal: expect.any(AbortSignal) });
    expect(prepared.text).toBe(text);
  });

  it.each([imageRenderer, pdfRenderer])("releases every managed asset lease", async (renderer) => {
    const release = vi.fn();
    const readAsset = vi.fn(async () => ({ url: "blob:fixture", mime: "application/octet-stream", release }));
    const prepared = await renderer.prepare({
      file: file(renderer.id === "image" ? "photo.png" : "paper.pdf", renderer.id),
      source: source({ readAsset }),
      signal: new AbortController().signal,
    });
    prepared.dispose?.();
    expect(release).toHaveBeenCalledOnce();
  });

  it("releases an asset when its request is cancelled after acquisition", async () => {
    const controller = new AbortController();
    const release = vi.fn();
    const readAsset = vi.fn(async () => {
      controller.abort();
      return { url: "blob:cancelled", release };
    });
    await expect(imageRenderer.prepare({
      file: file("photo.png", "image"),
      source: source({ readAsset }),
      signal: controller.signal,
    })).rejects.toMatchObject({ name: "AbortError" });
    expect(release).toHaveBeenCalledOnce();
  });
});

describe("shared Monaco identity", () => {
  it("keeps one view stable and isolates views and roots", () => {
    const first = monacoModelUri("root-a", "src/main.ts", "document-1", "view-1");
    expect(monacoModelUri("root-a", "src/main.ts", "document-1", "view-1")).toBe(first);
    expect(monacoModelUri("root-a", "src/main.ts", "document-1", "view-2")).not.toBe(first);
    expect(monacoModelUri("root-b", "src/main.ts", "document-1", "view-1")).not.toBe(first);
  });

  it("preserves the editor language table", () => {
    expect(languageFor("Dockerfile.dev")).toBe("dockerfile");
    expect(languageFor("robot.urdf")).toBe("xml");
    expect(languageFor("data.unknownext")).toBe("plaintext");
  });
});
