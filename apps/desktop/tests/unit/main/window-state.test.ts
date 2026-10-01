import { EventEmitter } from "node:events";

import { describe, expect, it, vi } from "vitest";

const saved = vi.hoisted(() => ({ calls: 0, closed: false, state: {} as Record<string, unknown> }));
const displays = vi.hoisted(() => ({ all: [] as { workArea: { x: number; y: number; width: number; height: number } }[] }));

vi.mock("electron", () => ({
  screen: { getAllDisplays: () => displays.all, getPrimaryDisplay: () => displays.all[0] },
}));
vi.mock("@main/db/repositories", () => ({
  settings: {
    windowState: () => saved.state,
    setWindowState: () => {
      if (saved.closed) {
        throw new Error("database used after close");
      }
      saved.calls += 1;
    },
  },
}));

import { flushWindowStates, restoreWindowState, trackWindowState } from "@main/window-state";

function fakeWindow() {
  return Object.assign(new EventEmitter(), {
    isDestroyed: () => false,
    isMaximized: () => false,
    getNormalBounds: () => ({ x: 1, y: 2, width: 900, height: 600 }),
  });
}

describe("window state on quit", () => {
  it("saves in before-quit, and the later close does not touch the closed database", () => {
    const window = fakeWindow();
    trackWindowState(window as never);
    flushWindowStates();
    expect(saved.calls).toBe(1);
    saved.closed = true;
    expect(() => window.emit("close")).not.toThrow();
    expect(saved.calls).toBe(1);
  });
});

// A laptop's screen alone, after the monitor the window was last on has gone.
describe("window state on launch", () => {
  const laptop = { workArea: { x: 0, y: 0, width: 1440, height: 900 } };
  const restore = (state: Record<string, unknown>) => {
    displays.all = [laptop];
    saved.state = { maximized: false, ...state };
    return restoreWindowState();
  };

  it("keeps a window that is on a display", () => {
    expect(restore({ x: 100, y: 50, width: 1200, height: 800 })).toMatchObject({ x: 100, y: 50, width: 1200, height: 800 });
  });

  // One pixel of it on the laptop's right edge is not a window anyone can
  // grab: it opens centred instead.
  it("centres a window with only a sliver left on any display", () => {
    const state = restore({ x: 1439, y: 0, width: 1200, height: 800 });
    expect(state.x).toBeUndefined();
    expect(state.y).toBeUndefined();
  });

  it("shrinks a window saved on a bigger display to the one it opens on", () => {
    const placed = restore({ x: 0, y: 0, width: 3000, height: 1400 });
    expect(placed.width).toBeLessThanOrEqual(1440);
    expect(placed.height).toBeLessThanOrEqual(900);
    const centred = restore({ width: 3000, height: 1400 });
    expect(centred.width).toBeLessThanOrEqual(1440);
    expect(centred.height).toBeLessThanOrEqual(900);
  });

  // A work area smaller than the window's minimum (900×600): Electron sizes
  // the window up to the minimum whatever it is asked for, so the slide back
  // on screen has to be worked out with the size it will really have.
  it("slides a window back by the size it will have, not one under the minimum", () => {
    displays.all = [{ workArea: { x: 0, y: 0, width: 880, height: 560 } }];
    saved.state = { maximized: false, x: 30, y: 30, width: 850, height: 520 };
    expect(restoreWindowState()).toMatchObject({ x: 0, y: 0, width: 900, height: 600 });
  });
});

// The e2e suite's window is never shown (`TEXT_TO_CAD_E2E_HIDDEN=1`), so it is
// on no display to fit. Fitted anyway, it took the size of whatever screen the
// CI runner happened to have — 1024 wide — and the explorer came out under the
// file viewer's 720px breakpoint, where the tree is a sheet a picked file shuts.
describe("window state for a window that is never shown", () => {
  it("keeps the stored size and place whatever the displays are", () => {
    vi.stubEnv("TEXT_TO_CAD_E2E_HIDDEN", "1");
    try {
      displays.all = [{ workArea: { x: 0, y: 25, width: 1024, height: 743 } }];
      saved.state = { maximized: false, width: 1440, height: 900 };
      expect(restoreWindowState()).toEqual({ maximized: false, width: 1440, height: 900 });
    } finally {
      vi.unstubAllEnvs();
    }
  });
});
