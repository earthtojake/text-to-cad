import { describe, expect, it } from "vitest";

import { resolveAddress } from "@renderer/features/explorer/BrowserTab";
import { fuzzyFilter, fuzzyMatch } from "@renderer/features/explorer/fuzzy";
import { languageFor } from "@renderer/features/explorer/monaco";
import {
  CAD_PANEL,
  nextOpenPanel,
  panelsFor,
  resolveOpenPanel,
  SOURCE_PANEL,
} from "@renderer/features/explorer/renderers/panels";
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
   * the nav row draws for it, the tree is the last entry in the same list,
   * and one of them is open. There is no per-kind special case left in the
   * row — markdown's source toggle and the files toggle are both entries.
   */
  it("gives markdown one panel, a CAD file two, and code none", () => {
    const context = { open: "", ready: true };

    const markdown = rendererForPath("README.md");
    expect(markdown.id).toBe("markdown");
    expect(markdown.panels?.(context).map((panel) => [panel.id, panel.label, panel.content])).toEqual([
      ["source", "View source", "body"],
    ]);
    // The label is the action, so it flips with the panel it opens.
    expect(markdown.panels?.({ ...context, open: SOURCE_PANEL }).map((panel) => panel.label)).toEqual([
      "View preview",
    ]);

    const cad = rendererForPath("models/part.step");
    expect(cad.id).toBe("cad");
    expect(cad.panels?.(context).map((panel) => [panel.id, panel.label, panel.content])).toEqual([
      ["cad-theme", "Theme settings", "slot"],
      // "Inspector" is the name; the id stays `cad-file-sheet`, because the
      // tab's stored `panel` field holds it and the viewer's host contract
      // calls the same panel `fileSheetOpen`.
      ["cad-file-sheet", "Inspector", "slot"],
    ]);
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

  /**
   * One panel open at a time, and the field that says which. This is the
   * whole rule the file tab draws from: the CAD pair used to enforce their
   * own exclusivity in a record of flags, beside a file tree that was
   * exempt from it.
   */
  it("opens one panel at a time, whichever was up before", () => {
    const cad = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: true }), "");

    // The renderer's default is what a tab opens with when nobody has said:
    // a CAD file's Inspector, and the tree for everything else. The tree is
    // last, so its default never wins over a renderer's own.
    expect(resolveOpenPanel(cad, null)?.id).toBe(CAD_PANEL.fileSheet);
    expect(resolveOpenPanel(panelsFor([], ""), null)?.id).toBe("tree");

    // A press names its panel; pressing the open one closes it and leaves
    // nothing open.
    expect(nextOpenPanel("", CAD_PANEL.theme)).toBe(CAD_PANEL.theme);
    expect(nextOpenPanel(CAD_PANEL.theme, CAD_PANEL.theme)).toBe("");
    // A press while ANOTHER panel is up opens this one — "show me this
    // instead" — whether the other is the surface's or this app's own tree.
    expect(nextOpenPanel(CAD_PANEL.fileSheet, CAD_PANEL.theme)).toBe(CAD_PANEL.theme);
    expect(nextOpenPanel("tree", CAD_PANEL.theme)).toBe(CAD_PANEL.theme);
    expect(nextOpenPanel(CAD_PANEL.theme, "tree")).toBe("tree");
    expect(nextOpenPanel(SOURCE_PANEL, "tree")).toBe("tree");
    expect(nextOpenPanel("tree", SOURCE_PANEL)).toBe(SOURCE_PANEL);
  });

  it("shows nothing for a panel this file does not have", () => {
    // `""` is nothing open, and so is an id that is not in the list: a tab
    // that was reading markdown's source and is pointed at a `.step`, or a
    // CAD tab whose surface has not come up, names a panel that is not
    // there.
    const cad = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: true }), "");
    expect(resolveOpenPanel(cad, "")).toBeNull();
    expect(resolveOpenPanel(cad, SOURCE_PANEL)).toBeNull();
    const notReady = panelsFor(rendererForPath("part.step").panels!({ open: "", ready: false }), "");
    expect(resolveOpenPanel(notReady, CAD_PANEL.fileSheet)).toBeNull();
    // ...and with nobody having said, the tree is what is left.
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
