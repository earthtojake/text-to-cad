import { describe, expect, it, vi } from "vitest";

import type { FileMetadata } from "../file-viewer/types.js";
import { selectRenderer } from "../file-viewer/registry.js";
import { createStepRenderer } from "./step/index.js";
import { createDxfRenderer } from "./dxf/index.js";
import { createPlotRenderer } from "./plot/index.js";
import { createGlbRenderer } from "./glb/index.js";
import { createMeshRenderer } from "./mesh/index.js";
import { createRobotRenderer } from "./robot/index.js";

// A registration loads its component beside its document; these tests are about the document.
vi.mock("./step/StepRenderer.js", () => ({ default: () => null }));
vi.mock("./dxf/DxfRenderer.jsx", () => ({ default: () => null }));
vi.mock("./plot/PlotRenderer.jsx", () => ({ default: () => null }));
vi.mock("./glb/GlbRenderer.jsx", () => ({ default: () => null }));
vi.mock("./mesh/MeshRenderer.jsx", () => ({ default: () => null }));
vi.mock("./robot/RobotRenderer.jsx", () => ({ default: () => null }));

const file = (path: string, mediaType: string, mime?: string): FileMetadata => ({
  path,
  name: path.split("/").at(-1) ?? path,
  kind: "file",
  size: 12,
  extension: path.split(".").at(-1)?.toLowerCase() ?? "",
  mediaType,
  mime,
});

describe("viewer renderer registrations", () => {
  const client = {} as never;
  it("gives .dxf its own renderer, and declares no panel for it", () => {
    const dxf = createDxfRenderer({ client });
    const step = createStepRenderer({ client });
    expect([dxf.id, step.id]).toEqual(["dxf", "step"]);
    expect(selectRenderer([step, dxf], file("plate.dxf", "cad"))).toBe(dxf);
    expect(selectRenderer([step, dxf], file("part.step", "cad"))).toBe(step);
    // A DXF is a straight render: it declares no panels, so the navbar offers no toggle
    // but the file tree's, which is the only panel a drawing tab can open.
    expect("panels" in dxf).toBe(false);
    // Preview is each viewer's own mode, never a flag a registration offers a host.
    expect(["fullscreen", "preview", "previewing"].some(key => key in dxf || key in step)).toBe(false);
  });

  it("gives a KiCad board and schematic, and a wiring harness, their own renderer, which the STEP renderer leaves alone", () => {
    const plot = createPlotRenderer({ client });
    const step = createStepRenderer({ client });
    const dxf = createDxfRenderer({ client });
    expect(plot.id).toBe("plot");
    // A catalog lists every file as `cad`: the suffix is what decides, never the media type.
    for (const path of ["boards/blinky.kicad_pcb", "boards/blinky.kicad_sch", "BLINKY.KICAD_PCB", "harness/cable.harness.yml"]) {
      expect(selectRenderer([step, dxf, plot], file(path, "cad"))).toBe(plot);
    }
    // A harness is the two suffixes together: a plain YAML file is no plot.
    expect(plot.matches(file("config.yml", "cad"))).toBe(false);
    expect("panels" in plot).toBe(false);
  });

  it("prepares a live document for every workspace file: an edit updates the open model, never reopens it", async () => {
    let disposed = 0;
    const client = {
      refresh: async () => {},
      resolveEntry: async (path: string) => ({ file: path, kind: "part" }),
      serverInfo: async () => ({}),
      createRenderSession: () => ({ dispose: () => { disposed += 1; } }),
    } as never;
    const renderers = [createStepRenderer({ client }), createDxfRenderer({ client }), createPlotRenderer({ client }),
      createGlbRenderer({ client }), createMeshRenderer({ client }), createRobotRenderer({ client })];
    for (const renderer of renderers) {
      const prepared = await renderer.prepare({ file: file("part.step", "cad"), source: {} as never, signal: new AbortController().signal });
      expect([renderer.id, prepared.live]).toEqual([renderer.id, true]);
      prepared.dispose?.();
    }
    expect(disposed).toBe(renderers.length);
  });
});
