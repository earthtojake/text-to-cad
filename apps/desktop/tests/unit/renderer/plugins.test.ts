import { afterEach, describe, expect, it } from "vitest";

import { selectRenderer, type FileMetadata } from "@hardcore/ui/file-viewer";
import { parseTable, tableState } from "@plugins/csv/table";
import { parseGcode } from "@plugins/gcode/parse";
import { plugins } from "@plugins/index.mjs";
import { allRendererPlugins, rendererPlugins, setEnabledPlugins } from "@plugins/renderer";
import { createDesktopRenderers } from "@renderer/features/explorer/renderers";
import cup from "../../fixtures/gcode/cup.gcode?raw";

const file = (path: string, mediaType: string, mime?: string): FileMetadata => ({
  path, name: path.split("/").at(-1) ?? path, kind: "file", size: 12,
  extension: path.split(".").at(-1)?.toLowerCase() ?? "", mediaType, mime,
});
const opens = (path: string, mediaType: string, mime?: string) => {
  const composition = createDesktopRenderers("p", null, "t", { acquire: async () => { throw new Error("no CAD backend in a unit test"); } });
  try { return selectRenderer(composition.renderers, file(path, mediaType, mime)).id; }
  finally { composition.dispose(); }
};

afterEach(() => setEnabledPlugins(plugins.map(plugin => plugin.id)));

describe("plugins, from the page", () => {
  it("the page has one plugin per manifest, in order", () => {
    expect(allRendererPlugins.map(plugin => plugin.manifest)).toEqual([...plugins]);
  });

  it("with every plugin on, each plugin's files open in its viewer, before the code editor", () => {
    expect(opens("cup.gcode", "text", "text/x-gcode")).toBe("gcode");
    expect(opens("paper.pdf", "pdf", "application/pdf")).toBe("pdf");
    expect(opens("sheet.csv", "text", "text/csv")).toBe("csv");
    expect(opens("part.step", "cad", "model/step")).toBe("step");
    expect(opens("notes.txt", "text", "text/plain")).toBe("code");
  });

  it("the base app alone opens text, Markdown and images, and nothing else", () => {
    setEnabledPlugins([]);
    expect(rendererPlugins()).toEqual([]);
    expect(opens("part.step", "cad", "model/step")).toBe("unsupported");
    expect(opens("paper.pdf", "pdf", "application/pdf")).toBe("unsupported");
    expect(opens("sheet.csv", "text", "text/csv")).toBe("code");
    expect(opens("README.md", "text", "text/markdown")).toBe("markdown");
    expect(opens("photo.png", "image", "image/png")).toBe("image");
  });

  it("one plugin on is that plugin's viewers and no other's", () => {
    setEnabledPlugins(["csv"]);
    expect(rendererPlugins().map(plugin => plugin.manifest.id)).toEqual(["csv"]);
    expect(opens("sheet.csv", "text", "text/csv")).toBe("csv");
    expect(opens("part.step", "cad", "model/step")).toBe("unsupported");
  });

  it("a G-code command for a tab with no toolpath showing is refused, not answered from elsewhere", async () => {
    const gcode = allRendererPlugins.find(plugin => plugin.manifest.id === "gcode")!;
    await expect(gcode.perform("gcode-state", { tabId: "t" }, { projectId: "p", root: null, path: "cup.gcode" })).rejects.toThrow(/No G-code toolpath/);
  });

  it("a CAD command for a tab that is not a CAD file is refused", async () => {
    const cad = allRendererPlugins.find(plugin => plugin.manifest.id === "cad")!;
    await expect(cad.perform("viewer-state", { tabId: "t" }, { projectId: "p", root: null, path: "notes.txt" })).rejects.toThrow(/does not contain a CAD model/);
  });
});

describe("the CSV example plugin", () => {
  it("reads quoted fields, separators and newlines inside quotes, and TSV", () => {
    expect(parseTable('name,note\n"Smith, J","said ""hi""\nthen left"\r\nLee,ok\n')).toEqual([
      ["name", "note"], ["Smith, J", 'said "hi"\nthen left'], ["Lee", "ok"],
    ]);
    expect(parseTable("a\tb\n1\t2", "\t")).toEqual([["a", "b"], ["1", "2"]]);
  });

  it("describes a table's shape for the agent", () => {
    expect(tableState("t.csv", [["a", "b"], ["1", "2"], ["3", "4"]])).toEqual({ path: "t.csv", header: ["a", "b"], rows: 2, columns: 2, firstRows: [["1", "2"], ["3", "4"]] });
  });
});

describe("the G-code toolpath", () => {
  it("reads layers, moves, arcs, filament and extents from a sliced file", () => {
    const toolpath = parseGcode(cup);
    expect(toolpath.stats).toMatchObject({ layers: 16, extrudeMoves: 16 * 6, arcMoves: 1 });
    expect(toolpath.layerZ[0]).toBeCloseTo(0.3);
    expect(toolpath.layerZ.at(-1)).toBeCloseTo(4.8);
    // The brim is a full circle of radius 10 about (30, 30), cut into segments on layer 1.
    expect(toolpath.stats.extents!.min[0]).toBeCloseTo(20, 0);
    expect(toolpath.stats.extents!.max[0]).toBeCloseTo(40, 0);
    expect(toolpath.stats.filamentMm).toBeGreaterThan(1.5);
    // Layers only grow, and each ends where the next begins.
    expect([...toolpath.extrudeLayer].every((layer, index, all) => index === 0 || layer >= all[index - 1]!)).toBe(true);
    expect(toolpath.layerEnd.at(-1)).toBe(toolpath.extrudeLayer.length);
    // Each layer's travel ends where that layer's printing does: the final lift comes after.
    expect(toolpath.layerTravelEnd).toHaveLength(16);
    expect(toolpath.layerTravelEnd.at(-1)).toBeLessThan(toolpath.travel.length / 6);
  });

  it("follows relative moves, relative extrusion, G92 and inches", () => {
    const toolpath = parseGcode(["G91", "M83", "G1 Z0.2", "G1 X10 E1", "G1 Y10 E1", "G1 X-10 E-0.5", "G90", "G20", "G92 X0 Y0", "G0 X1", "G21"].join("\n"));
    expect(toolpath.stats).toMatchObject({ layers: 1, extrudeMoves: 2, travelMoves: 3, filamentMm: 2 });
    expect(toolpath.stats.extents).toEqual({ min: [0, 0, 0.2], max: [10, 10, 0.2] });
    // G20 then X1 is 25.4 mm of travel from the G92 origin.
    expect(toolpath.travel.slice(-3)[0]).toBeCloseTo(25.4);
  });
});
