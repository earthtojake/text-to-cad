import { describe, expect, it } from "vitest";

import { resolveAddress } from "@renderer/features/explorer/BrowserTab";
import { fuzzyFilter, fuzzyMatch } from "@renderer/features/explorer/fuzzy";
import { languageFor } from "@renderer/features/explorer/monaco";
import { CAD_PANEL, toggleCadPanel } from "@renderer/features/explorer/renderers/panels";
import { isCadPath, rendererForPath } from "@renderer/features/explorer/renderers/registry";

describe("the tree's fuzzy filter", () => {
  it("finds a path from the initials of its segments", () => {
    expect(fuzzyMatch("srexfs", "src/main/explorer/fs.ts")).not.toBeNull();
  });

  it("rejects a needle whose characters are not in order", () => {
    expect(fuzzyMatch("stf", "fs.ts")).toBeNull();
  });

  it("prefers a match in the filename over one in a directory", () => {
    const ranked = fuzzyFilter(["explorer/vendor/a.ts", "src/explorer.ts"], "explorer");
    expect(ranked[0]?.path).toBe("src/explorer.ts");
  });

  it("prefers the shorter path when the match is otherwise the same", () => {
    const ranked = fuzzyFilter(["a/b/c/d/e/index.ts", "index.ts"], "index");
    expect(ranked[0]?.path).toBe("index.ts");
  });

  it("puts the root file first when several share a name", () => {
    // The case that sent `README.md` third behind `models/README.md`: the
    // camelCase bonus was scoring a capital after a slash but not one at the
    // start of the path.
    const ranked = fuzzyFilter(
      ["models/README.md", "packages/README.md", "README.md", "apps/docs/README.md"],
      "README.md",
    );
    expect(ranked[0]?.path).toBe("README.md");
  });

  it("returns indices so the matched characters can be highlighted", () => {
    expect(fuzzyMatch("abc", "abc")?.indices).toEqual([0, 1, 2]);
  });

  it("passes everything through when the query is blank", () => {
    expect(fuzzyFilter(["a", "b"], "  ").map((match) => match.path)).toEqual(["a", "b"]);
  });

  it("caps its answer", () => {
    const paths = Array.from({ length: 500 }, (_, index) => `src/file${index}.ts`);
    expect(fuzzyFilter(paths, "file", 10)).toHaveLength(10);
  });
});

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
   * The panels contract (`renderers/panels.ts`): a renderer declares what
   * the nav row draws for it, and the row has no per-kind special case left
   * in it. Markdown's source toggle is one of these now.
   */
  it("gives markdown one panel, a CAD file two, and code none", () => {
    const context = {
      viewSource: false,
      setViewSource: () => {},
      open: {},
      setOpen: () => {},
      ready: true,
    };

    const markdown = rendererForPath("README.md");
    expect(markdown.id).toBe("markdown");
    expect(markdown.panels?.(context).map((panel) => [panel.id, panel.label, panel.open])).toEqual([
      ["source", "View source", false],
    ]);
    // The label is the action and `open` is "source is showing", so the two
    // flip together.
    expect(markdown.panels?.({ ...context, viewSource: true }).map((panel) => [panel.label, panel.open])).toEqual([
      ["View preview", true],
    ]);

    const cad = rendererForPath("models/part.step");
    expect(cad.id).toBe("cad");
    expect(cad.panels?.(context).map((panel) => [panel.id, panel.label])).toEqual([
      ["cad-theme", "Theme settings"],
      ["cad-file-sheet", "File sheet"],
    ]);
    // Each reads its own flag out of the record the tab keeps.
    expect(cad.panels?.({ ...context, open: { "cad-theme": true } }).map((panel) => panel.open)).toEqual([true, false]);
    // And there are none at all until the surface behind them is up: two
    // toggles over the runtime's failure card would open nothing.
    expect(cad.panels?.({ ...context, ready: false })).toEqual([]);

    expect(rendererForPath("src/index.ts").id).toBe("code");
    expect(rendererForPath("src/index.ts").panels).toBeNull();
    expect(rendererForPath("build/icon.png").panels).toBeNull();
  });

  it("closes one CAD panel as it opens the other", () => {
    // They are one panel in the viewer's surface, so a press writes both
    // flags at once: the record never has two open, and closing the one you
    // opened leaves nothing open.
    expect(toggleCadPanel({}, CAD_PANEL.theme)).toEqual({ "cad-theme": true, "cad-file-sheet": false });
    expect(toggleCadPanel({ "cad-theme": true }, CAD_PANEL.theme)).toEqual({
      "cad-theme": false,
      "cad-file-sheet": false,
    });
    // A press while the OTHER is up opens this one — the gesture is "show me
    // this instead", not "close something already closed".
    expect(toggleCadPanel({ "cad-file-sheet": true }, CAD_PANEL.theme)).toEqual({
      "cad-theme": true,
      "cad-file-sheet": false,
    });
    expect(toggleCadPanel({ "cad-theme": true }, CAD_PANEL.fileSheet)).toEqual({
      "cad-theme": false,
      "cad-file-sheet": true,
    });
  });

  it("drives the pair through the declaration's own toggles", () => {
    const open: Record<string, boolean> = { "cad-file-sheet": true };
    const panels = rendererForPath("part.step").panels!({
      viewSource: false,
      setViewSource: () => {},
      open,
      setOpen: (patch) => Object.assign(open, patch),
      ready: true,
    });
    expect(panels.map((panel) => panel.open)).toEqual([false, true]);
    panels[0]!.onToggle();
    expect(open).toEqual({ "cad-theme": true, "cad-file-sheet": false });
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
