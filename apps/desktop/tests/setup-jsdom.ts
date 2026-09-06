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
    agents: {
      list: vi.fn(async () => []),
      refresh: vi.fn(async () => []),
      install: vi.fn(async () => ({ jobId: "job" })),
      login: vi.fn(async () => ({ jobId: "job" })),
      writeJob: vi.fn(),
      cancelJob: vi.fn(),
    },
    plugins: {
      status: vi.fn(),
      statusAll: vi.fn(async () => []),
      install: vi.fn(),
    },
    runtime: {
      status: vi.fn(async () => ({
        state: "missing",
        python: null,
        cadgenVersion: null,
        viewerBuilt: false,
        overridden: false,
        log: null,
      })),
      repair: vi.fn(),
    },
    dialogs: { chooseDirectory: vi.fn(async () => null), chooseFile: vi.fn(async () => null) },
    settings: { get: vi.fn(), set: vi.fn() },
    window: { state: vi.fn() },
    shell: { openExternal: vi.fn(), showItemInFolder: vi.fn() },
    on: vi.fn(() => () => {}),
  },
});

afterEach(() => {
  cleanup();
});
