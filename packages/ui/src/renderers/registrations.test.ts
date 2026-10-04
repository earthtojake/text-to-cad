import { describe, expect, it, vi } from "vitest";

import type { FileMetadata } from "../file-viewer/types.js";
import { selectRenderer } from "../file-viewer/registry.js";
import { createStepRenderer } from "./step/index.js";
import { createDxfRenderer } from "./dxf/index.js";
import { createGlbRenderer } from "./glb/index.js";
import { createMeshRenderer } from "./mesh/index.js";
import { createRobotRenderer } from "./robot/index.js";

// A registration loads its component beside its document; these tests are about the document.
vi.mock("./step/StepRenderer.js", () => ({ default: () => null }));
vi.mock("./dxf/DxfRenderer.jsx", () => ({ default: () => null }));
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
  it("gives .dxf its own renderer", () => {
    const dxf = createDxfRenderer({ client });
    const step = createStepRenderer({ client });
    expect([dxf.id, step.id]).toEqual(["dxf", "step"]);
    expect(selectRenderer([step, dxf], file("plate.dxf", "cad"))).toBe(dxf);
    expect(selectRenderer([step, dxf], file("part.step", "cad"))).toBe(step);
    // Preview is each viewer's own mode, never a flag a registration offers a host.
    expect(["fullscreen", "preview", "previewing"].some(key => key in dxf || key in step)).toBe(false);
  });

  it("prepares every workspace file from its catalog entry alone, and its document releases the render session it opened", async () => {
    let disposed = 0;
    // What opening a file reads: its catalog entry, and a render session.
    const client = {
      resolveEntry: async (path: string) => ({ file: path, kind: "part" }),
      createRenderSession: () => ({ dispose: () => { disposed += 1; } }),
    } as never;
    const renderers = [createStepRenderer({ client }), createDxfRenderer({ client }), createGlbRenderer({ client }),
      createMeshRenderer({ client }), createRobotRenderer({ client })];
    for (const renderer of renderers) {
      const prepared = await renderer.prepare({ file: file("part.step", "cad"), source: {} as never, signal: new AbortController().signal });
      prepared.dispose?.();
    }
    expect(disposed).toBe(renderers.length);
  });
});
