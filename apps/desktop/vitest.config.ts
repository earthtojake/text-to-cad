import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

import { viewerClientRoot, viewerPeerNames } from "./scripts/viewer-alias.mjs";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(appRoot, "..", "..");

/**
 * The markdown round-trip tests load this repository's own `README.md`,
 * `AGENTS.md` and `CONTRIBUTING.md` through Vite's `?raw`, because a fixture
 * written for those tests would be a fixture written to pass them. Vite serves
 * nothing outside the project root without being told to.
 */
const server = { fs: { allow: [appRoot, repoRoot] } };

/**
 * Aliases as an array, because one of them has to be a pattern.
 *
 * `?worker` is a Vite build feature (`monaco.ts` imports Monaco's five workers
 * that way). Vitest has no worker plugin, so without this every test that
 * reaches that module — including one that only wants `languageFor` — fails to
 * load on an unresolvable import.
 */
const alias = [
  { find: "@main", replacement: path.join(appRoot, "src", "main") },
  { find: "@preload", replacement: path.join(appRoot, "src", "preload") },
  { find: "@renderer", replacement: path.join(appRoot, "src", "renderer") },
  { find: "@shared", replacement: path.join(appRoot, "src", "shared") },
  // The pattern has to match the *whole* id: a RegExp alias is applied with
  // `id.replace(find, replacement)`, so `/\?worker$/` alone would leave the
  // module path glued to the front of the stub's.
  { find: /^.*\?worker$/, replacement: path.join(appRoot, "tests", "stubs", "worker.ts") },
  /**
   * The CAD Viewer client's own root alias. The file tab draws
   * `cad-viewer/shell`, so the renderer suite renders the viewer's sources and
   * has to resolve their `@/…` imports the way the build does. It cannot
   * claim `@renderer`: a string alias matches `id === "@"` or a `"@/"` prefix.
   */
  { find: "@", replacement: viewerClientRoot },
];

/**
 * Two projects, split by folder, matching the two tsconfigs:
 *
 *   tests/unit/{main,shared}  plain Node, no DOM;
 *   tests/unit/renderer       jsdom.
 *
 * The split matters. A main-process test that quietly gets a `window` will
 * pass while the code it covers cannot run, and a renderer test without one
 * fails for the wrong reason.
 *
 * Nothing here loads better-sqlite3 or node-pty: those are built against
 * Electron's ABI by `electron-builder install-app-deps` and will not load in a
 * plain Node process. Anything that needs them belongs in the Playwright e2e,
 * which runs the real app.
 */
/**
 * One copy of every package the viewer's sources import by name — this app's.
 *
 * The build pins them by alias (`scripts/viewer-alias.mjs`, shared with
 * `electron.vite.config.ts`); here they are deduped instead, which is the same
 * statement in the terms Vite's dev/SSR resolver understands. Left alone they
 * resolve from the importing file's location, which is `apps/viewer`'s own
 * `node_modules` — a second React, whose first symptom is "an element from an
 * older version of React was rendered" rather than an import error, and a
 * second radix, whose contexts do not match the first's.
 */
const dedupe = viewerPeerNames();

export default defineConfig({
  resolve: { alias, dedupe },
  define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
  test: {
    projects: [
      {
        resolve: { alias, dedupe },
        define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
        test: {
          name: "node",
          environment: "node",
          include: ["tests/unit/main/**/*.test.ts", "tests/unit/shared/**/*.test.ts"],
          // The git and workspace suites run dozens of real `git` processes
          // per test; on a machine that is also building the app, that is
          // more than five seconds and not a failure.
          testTimeout: 20_000,
        },
      },
      {
        resolve: { alias, dedupe },
        define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
        esbuild: { jsx: "automatic" },
        server,
        test: {
          name: "renderer",
          environment: "jsdom",
          include: ["tests/unit/renderer/**/*.test.{ts,tsx}"],
          setupFiles: [path.join(appRoot, "tests", "setup-jsdom.ts")],
        },
      },
    ],
  },
});
