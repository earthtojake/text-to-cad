import { describe, expect, it } from "vitest";

import type { FileMetadata } from "../file-viewer/types.js";
import { selectRenderer } from "../file-viewer/registry.js";
import { createStepRenderer } from "./step/index.js";
import { createDxfRenderer } from "./dxf/index.js";

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
    // Fullscreen is each viewer's own presentation, never a flag a registration offers a host.
    expect("fullscreen" in dxf || "fullscreen" in step).toBe(false);
  });
});
