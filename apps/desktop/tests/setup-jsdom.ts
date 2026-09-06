import "@testing-library/jest-dom/vitest";

import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * A renderer test runs the real components, so it needs the two things a
 * renderer always has and jsdom does not: the preload bridge and matchMedia.
 *
 * The bridge is a stub rather than a mock of `ipcRenderer` — the point of
 * `window.hardcore` being the only surface is that a test can replace all of
 * it in five lines.
 */
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Radix measures with these; jsdom has neither.
window.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

Object.defineProperty(window, "hardcore", {
  writable: true,
  value: {
    app: {
      info: vi.fn(async () => ({ version: "0.0.0-test", platform: "darwin", isDev: true })),
    },
    projects: {
      list: vi.fn(async () => []),
      add: vi.fn(async () => null),
      addPath: vi.fn(),
      remove: vi.fn(),
      rename: vi.fn(),
    },
    sessions: { list: vi.fn(async () => []) },
    settings: { get: vi.fn(), set: vi.fn() },
    window: { state: vi.fn() },
    shell: { openExternal: vi.fn(), showItemInFolder: vi.fn() },
    on: vi.fn(() => () => {}),
  },
});

afterEach(() => {
  cleanup();
});
