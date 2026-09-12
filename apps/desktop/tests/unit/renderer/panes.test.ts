import { describe, expect, it } from "vitest";

import { dragOutcome, maxWidthOf, resolvePanes } from "@renderer/lib/panes";
import { PANE_LIMITS } from "@shared/types";

/**
 * The shell's geometry (`src/renderer/lib/panes.ts`): pixels in, pixels out.
 *
 * The three rules the person complained about are all here — a drag stops at
 * a minimum, 40px past it collapses the pane and keeps its width, and a window
 * with no room closes the explorer before the sidebar — because they are the
 * ones that were spread across a library's state, an imperative collapse and
 * a re-derived share, and disagreed.
 */

const open = (width: number) => ({ collapsed: false, width });
const shut = (width: number) => ({ collapsed: true, width });
const SEP = 1;

describe("resolvePanes", () => {
  it("keeps both side panes at their widths and gives the session the rest", () => {
    const resolved = resolvePanes({ width: 1440, sidebar: open(230), explorer: open(560) });
    expect(resolved).toEqual({ sidebar: 230, explorer: 560, collapse: [] });
    // Which is exactly what the flex row has left for the session.
    expect(1440 - 230 - 560 - 2 * SEP).toBeGreaterThanOrEqual(PANE_LIMITS.session.min);
  });

  it("does not render a collapsed pane, and drops the explorer without a project", () => {
    expect(resolvePanes({ width: 1440, sidebar: shut(230), explorer: open(560) })).toEqual({
      sidebar: null,
      explorer: 560,
      collapse: [],
    });
    expect(resolvePanes({ width: 1440, sidebar: open(230), explorer: shut(560) })).toEqual({
      sidebar: 230,
      explorer: null,
      collapse: [],
    });
    expect(resolvePanes({ width: 1440, sidebar: open(230), explorer: null })).toEqual({
      sidebar: 230,
      explorer: null,
      collapse: [],
    });
  });

  it("clamps a stored width to the pane's own limits", () => {
    expect(resolvePanes({ width: 1680, sidebar: open(40), explorer: open(60) })).toMatchObject({
      sidebar: PANE_LIMITS.sidebar.min,
      explorer: PANE_LIMITS.explorer.min,
    });
    expect(resolvePanes({ width: 1680, sidebar: open(900), explorer: open(400) })).toMatchObject({
      sidebar: PANE_LIMITS.sidebar.max,
    });
  });

  // The session's floor is what the widths give way to, and the explorer
  // gives way before the sidebar does.
  it("shrinks the explorer first, then the sidebar, to keep the session's floor", () => {
    // 900 is the window's minimum size. 230 + 560 would leave the session 108.
    const tight = resolvePanes({ width: 900, sidebar: open(230), explorer: open(560) });
    expect(tight.collapse).toEqual([]);
    expect(tight.sidebar).toBe(230);
    expect(tight.explorer).toBe(900 - 2 * SEP - PANE_LIMITS.session.min - 230);
    expect(tight.explorer! + tight.sidebar! + 2 * SEP + PANE_LIMITS.session.min).toBe(900);

    // Narrower still: the explorer is at its floor, so the sidebar gives up
    // the difference — down to its minimum and no further.
    const squeezed = resolvePanes({ width: 800, sidebar: open(230), explorer: open(560) });
    expect(squeezed.collapse).toEqual([]);
    expect(squeezed.explorer).toBe(PANE_LIMITS.explorer.min);
    expect(squeezed.sidebar).toBe(800 - 2 * SEP - PANE_LIMITS.session.min - PANE_LIMITS.explorer.min);
    expect(squeezed.sidebar!).toBeGreaterThanOrEqual(PANE_LIMITS.sidebar.min);
  });

  it("collapses the explorer, then the sidebar, when the minimums do not fit", () => {
    // 782 is the last width all three minimums fit in (320 + 180 + 280 + 2).
    expect(resolvePanes({ width: 782, sidebar: open(230), explorer: open(560) }).collapse).toEqual([]);
    const one = resolvePanes({ width: 781, sidebar: open(230), explorer: open(560) });
    expect(one.collapse).toEqual(["explorer"]);
    expect(one.explorer).toBeNull();
    expect(one.sidebar).toBe(230);

    const both = resolvePanes({ width: 480, sidebar: open(230), explorer: open(560) });
    expect(both.collapse).toEqual(["explorer", "sidebar"]);
    expect(both.explorer).toBeNull();
    expect(both.sidebar).toBeNull();
  });

  it("draws nothing off the first, unmeasured frame", () => {
    expect(resolvePanes({ width: 0, sidebar: open(230), explorer: open(560) }).collapse).toEqual([]);
  });
});

describe("maxWidthOf", () => {
  it("is the window less the session's floor, the other pane and the separators", () => {
    expect(maxWidthOf("explorer", { width: 1440, other: 230 })).toBe(1440 - 320 - 230 - 2);
    expect(maxWidthOf("explorer", { width: 1440, other: null })).toBe(1440 - 320 - 1);
    // The sidebar's own maximum wins while the window is roomy.
    expect(maxWidthOf("sidebar", { width: 1440, other: 560 })).toBe(PANE_LIMITS.sidebar.max);
    expect(maxWidthOf("sidebar", { width: 900, other: 300 })).toBe(900 - 320 - 300 - 2);
    // Never under the pane's own minimum: a maximum below it would make every
    // drag a collapse.
    expect(maxWidthOf("sidebar", { width: 900, other: 400 })).toBe(PANE_LIMITS.sidebar.min);
  });
});

describe("dragOutcome", () => {
  it("stops at the minimum rather than snapping back", () => {
    expect(dragOutcome({ pane: "sidebar", requested: 150, remembered: 230, max: 480 })).toEqual({
      width: PANE_LIMITS.sidebar.min,
      collapsed: false,
    });
    expect(dragOutcome({ pane: "explorer", requested: 260, remembered: 560, max: 900 })).toEqual({
      width: PANE_LIMITS.explorer.min,
      collapsed: false,
    });
  });

  it("collapses only past the overshoot, and keeps the width it had", () => {
    const edge = PANE_LIMITS.sidebar.min - PANE_LIMITS.overshoot;
    expect(dragOutcome({ pane: "sidebar", requested: edge, remembered: 230, max: 480 })).toEqual({
      width: PANE_LIMITS.sidebar.min,
      collapsed: false,
    });
    expect(dragOutcome({ pane: "sidebar", requested: edge - 1, remembered: 230, max: 480 })).toEqual({
      width: 230,
      collapsed: true,
    });
    // The remembered width is the one the toggle brings the pane back at.
    expect(dragOutcome({ pane: "explorer", requested: -4000, remembered: 640, max: 900 })).toEqual({
      width: 640,
      collapsed: true,
    });
  });

  it("clamps at the top and rounds to whole pixels", () => {
    expect(dragOutcome({ pane: "sidebar", requested: 10_000, remembered: 230, max: 480 }).width).toBe(480);
    expect(dragOutcome({ pane: "explorer", requested: 400.6, remembered: 560, max: 900 }).width).toBe(401);
  });
});
