import { describe, expect, it } from "vitest";

import { selectRenderer, type FileMetadata } from "@hardcore/ui/file-viewer";
import { parseGcode } from "@plugins/gcode/parse";
import { plugins } from "@plugins/index.mjs";
import { rendererPlugins } from "@plugins/renderer";
import { codeRenderer } from "@renderer/features/explorer/renderers/code";
import cup from "../../fixtures/gcode/cup.gcode?raw";

const file = (path: string, mediaType: string, mime?: string): FileMetadata => ({
  path, name: path.split("/").at(-1) ?? path, kind: "file", size: 12,
  extension: path.split(".").at(-1)?.toLowerCase() ?? "", mediaType, mime,
});
const tab = { projectId: "p", root: null, tabId: "t" };

describe("plugins, from the page", () => {
  it("the page composes one plugin per manifest, in order", () => {
    expect(rendererPlugins.map(plugin => plugin.manifest)).toEqual([...plugins]);
  });

  it("a plugin's viewer takes its files before the code editor does", () => {
    const renderers = [codeRenderer, ...rendererPlugins.flatMap(plugin => plugin.renderers(tab))];
    expect(selectRenderer(renderers, file("cup.gcode", "text", "text/x-gcode")).id).toBe("gcode");
    expect(selectRenderer(renderers, file("paper.pdf", "pdf", "application/pdf")).id).toBe("pdf");
    expect(selectRenderer(renderers, file("notes.txt", "text", "text/plain")).id).toBe("code");
  });

  it("a G-code command for a tab with no toolpath showing is refused, not answered from elsewhere", async () => {
    const gcode = rendererPlugins.find(plugin => plugin.manifest.id === "gcode")!;
    await expect(gcode.perform("gcode-state", { tabId: "t" }, { projectId: "p", root: null, path: "cup.gcode" })).rejects.toThrow(/No G-code toolpath/);
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
