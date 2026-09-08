import {
  CAD_PANEL,
  cadPanels,
  markdownPanels,
  panelsFor,
  resolveOpenPanel,
  SOURCE_PANEL,
} from "cad-viewer/shell";
import { describe, expect, it } from "vitest";

import { resolveAddress } from "@renderer/features/explorer/BrowserTab";
import { languageFor } from "@renderer/features/explorer/monaco";
import { isCadPath, rendererForPath } from "@renderer/features/explorer/renderers/registry";

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

describe("the renderer registry", () => {
  it("routes the nine CAD extensions to the CAD surface", () => {
    for (const extension of ["step", "stp", "glb", "stl", "3mf", "dxf", "urdf", "srdf", "sdf"]) {
      expect(isCadPath(`models/part.${extension}`)).toBe(true);
      expect(rendererForPath(`models/part.${extension}`).id).toBe("cad");
    }
  });

  /**
   * A renderer declares what the nav row draws for it, and the declarations
   * are the SHARED ones (`cad-viewer/shell`'s `panels.js`) — the standalone
   * CAD Viewer's row is built from the same call, so the two apps cannot come
   * to disagree about a panel's name, glyph or default. The rule those
   * declarations obey — one open at a time, the tree last — is tested where it
   * lives, in `apps/viewer/src/client/shell/panels.test.js`. What is this
   * app's own is which renderer gets which of them.
   */
  it("gives markdown the shared source panel, a CAD file the shared pair, and code none", () => {
    const context = { open: "", ready: true };

    const markdown = rendererForPath("README.md");
    expect(markdown.id).toBe("markdown");
    expect(markdown.panels?.(context)).toEqual(markdownPanels(""));
    // The label is the action, so it flips with the panel it opens.
    expect(markdown.panels?.({ ...context, open: SOURCE_PANEL }).map((panel) => panel.label)).toEqual([
      "View preview",
    ]);

    const cad = rendererForPath("models/part.step");
    expect(cad.id).toBe("cad");
    expect(cad.panels?.(context)).toEqual(cadPanels(true));
    // And there are none at all until the surface behind them is up: two
    // toggles over the runtime's failure card would open nothing.
    expect(cad.panels?.({ ...context, ready: false })).toEqual([]);

    expect(rendererForPath("src/index.ts").id).toBe("code");
    expect(rendererForPath("src/index.ts").panels).toBeNull();
    expect(rendererForPath("build/icon.png").panels).toBeNull();
  });

  it("puts the files toggle last in every list, and names it by what it does", () => {
    const cad = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: true }), "");
    expect(cad.map((panel) => panel.id)).toEqual(["cad-theme", "cad-file-sheet", "tree"]);
    expect(cad.at(-1)?.label).toBe("Show files");
    // A kind with no panels of its own has the tree alone.
    const code = panelsFor(rendererForPath("src/index.ts").panels?.({ open: "", ready: true }) ?? [], "tree");
    expect(code.map((panel) => [panel.id, panel.label])).toEqual([["tree", "Hide files"]]);
  });

  it("opens a CAD file with its Inspector and everything else with the tree", () => {
    // The renderer's default is what a tab opens with when nobody has said.
    // The tree is last, so its default never wins over a renderer's own.
    const cad = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: true }), "");
    expect(resolveOpenPanel(cad, null)?.id).toBe(CAD_PANEL.fileSheet);
    expect(resolveOpenPanel(panelsFor([], ""), null)?.id).toBe("tree");
    // A CAD tab whose surface has not come up has the tree and nothing else.
    const notReady = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: false }), "");
    expect(resolveOpenPanel(notReady, CAD_PANEL.fileSheet)).toBeNull();
    expect(resolveOpenPanel(notReady, null)?.id).toBe("tree");
  });
});


describe("Monaco's language", () => {
  it("reads it off the extension", () => {
    expect(languageFor("a/b.ts")).toBe("typescript");
    expect(languageFor("a/b.py")).toBe("python");
    expect(languageFor("robot.urdf")).toBe("xml");
  });

  it("knows Dockerfile has no extension to read", () => {
    expect(languageFor("Dockerfile")).toBe("dockerfile");
    expect(languageFor("Dockerfile.dev")).toBe("dockerfile");
  });

  it("falls back to plain text rather than guessing", () => {
    expect(languageFor("data.unknownext")).toBe("plaintext");
  });
});
