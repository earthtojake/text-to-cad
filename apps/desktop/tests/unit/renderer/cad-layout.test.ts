import { describe, expect, it } from "vitest";

import { CAD_SURFACE_MIN_WIDTH, cadSheetWidthFor, cadTabHidesTree } from "@renderer/features/explorer/cad-layout";

describe("the CAD sheet's width", () => {
  it("is a share of the pane between the sheet's floor and ceiling", () => {
    expect(cadSheetWidthFor(560)).toBe(240);
    expect(cadSheetWidthFor(650)).toBe(240);
    expect(cadSheetWidthFor(900)).toBe(324);
    expect(cadSheetWidthFor(1440)).toBe(365);
  });

  it("is null before the pane has been measured", () => {
    expect(cadSheetWidthFor(0)).toBeNull();
    expect(cadSheetWidthFor(Number.NaN)).toBeNull();
  });
});

describe("hiding the tree for a CAD tab", () => {
  it("hides it when the pane minus the tree is too narrow for a surface", () => {
    expect(cadTabHidesTree(650, 248)).toBe(true);
    expect(cadTabHidesTree(CAD_SURFACE_MIN_WIDTH + 248, 248)).toBe(false);
    expect(cadTabHidesTree(1400, 248)).toBe(false);
  });

  it("hides nothing before a measurement", () => {
    expect(cadTabHidesTree(0, 248)).toBe(false);
  });
});
