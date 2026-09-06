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

// Monaco probes `document.execCommand("paste")` support at import time, and
// jsdom implements neither method. Without these two, importing anything that
// transitively reaches `monaco-editor` throws before a test runs.
document.queryCommandSupported ??= () => false;
document.execCommand ??= () => false;

// jsdom has no layout, so it has no `scrollIntoView`. The tab strip and the
// file tree both use it to keep the selected thing on screen.
Element.prototype.scrollIntoView ??= () => {};

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
    explorer: {
      list: vi.fn(async () => []),
      paths: vi.fn(async () => ({ paths: [], truncated: false })),
      stat: vi.fn(),
      readText: vi.fn(),
      writeText: vi.fn(),
      readBinary: vi.fn(),
      absolutePath: vi.fn(async ({ path }: { path: string }) => ({ path })),
      openDefault: vi.fn(),
      watch: vi.fn(async () => undefined),
      unwatch: vi.fn(async () => undefined),
      loadTabs: vi.fn(async () => []),
      saveTabs: vi.fn(async () => undefined),
    },
    // Every stub answers with a promise: the stores treat IPC as async and
    // attach a `.catch`, so a `vi.fn()` returning undefined fails at the call
    // site rather than at the assertion.
    terminal: {
      create: vi.fn(async () => ({
        id: "pty-test",
        cwd: "/tmp",
        shell: "/bin/zsh",
        cols: 80,
        rows: 24,
        exitCode: null,
      })),
      write: vi.fn(async () => undefined),
      resize: vi.fn(async () => undefined),
      attach: vi.fn(async () => null),
      kill: vi.fn(async () => undefined),
    },
    git: {
      status: vi.fn(async () => ({
        isRepository: false,
        branch: null,
        unborn: false,
        ahead: 0,
        behind: 0,
        files: [],
        insertions: 0,
        deletions: 0,
      })),
      fileDiff: vi.fn(async () => null),
      unifiedDiff: vi.fn(async () => ({ patch: "" })),
      commit: vi.fn(async () => ({ sha: "0".repeat(40) })),
    },
    cad: { viewerOrigin: vi.fn(async () => ({ origin: null, reason: "runtime-not-ready" })) },
    on: vi.fn(() => () => {}),
  },
});

afterEach(() => {
  cleanup();
});
