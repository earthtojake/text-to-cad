import { describe, expect, it } from "vitest";

import { paneShares } from "@renderer/app/Shell";
import { PANE_LIMITS } from "@shared/types";

/** The shares back to pixels, rounded, so the assertions read as widths. */
function px(width: number, shares: { sidebar: number; session: number; explorer: number }) {
  return {
    sidebar: Math.round((shares.sidebar / 100) * width),
    session: Math.round((shares.session / 100) * width),
    explorer: Math.round((shares.explorer / 100) * width),
  };
}

const defaults = { sidebarWidth: 230, sessionWidth: 560, sidebarCollapsed: false, explorerCollapsed: false };

describe("the shell's pane shares", () => {
  it("keeps the sidebar and the session at their widths and gives the explorer the rest", () => {
    expect(px(1440, paneShares({ width: 1440, ...defaults }))).toEqual({ sidebar: 230, session: 560, explorer: 650 });
    expect(px(1280, paneShares({ width: 1280, ...defaults }))).toEqual({ sidebar: 230, session: 560, explorer: 490 });
    expect(px(1680, paneShares({ width: 1680, ...defaults }))).toEqual({ sidebar: 230, session: 560, explorer: 890 });
  });

  it("gives a collapsed pane's width to the session", () => {
    expect(px(1440, paneShares({ width: 1440, ...defaults, explorerCollapsed: true }))).toEqual({ sidebar: 230, session: 1210, explorer: 0 });
    expect(px(1440, paneShares({ width: 1440, ...defaults, sidebarCollapsed: true }))).toEqual({ sidebar: 0, session: 560, explorer: 880 });
  });

  it("keeps the session's floor before the explorer's when the window has room for only one", () => {
    // A stored session wider than the window can hold: the explorer keeps
    // its floor and the session takes what is left, as long as that is not
    // below the session's own floor.
    const roomy = px(1200, paneShares({ width: 1200, ...defaults, sessionWidth: 800 }));
    expect(roomy).toEqual({ sidebar: 230, session: 1200 - 230 - PANE_LIMITS.explorer.min, explorer: PANE_LIMITS.explorer.min });
    // Not enough for both floors: the session keeps its minimum — it is the
    // app — and the explorer takes what is left rather than the session
    // going under.
    const tight = px(1000, paneShares({ width: 1000, ...defaults }));
    expect(tight.session).toBe(PANE_LIMITS.session.min);
    expect(tight.explorer).toBe(1000 - 230 - PANE_LIMITS.session.min);
  });

  it("honours a wider stored session", () => {
    expect(px(1680, paneShares({ width: 1680, ...defaults, sessionWidth: 720 }))).toEqual({ sidebar: 230, session: 720, explorer: 730 });
  });
});
