import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const appRoot = path.dirname(fileURLToPath(import.meta.url));

const alias = {
  "@main": path.join(appRoot, "src", "main"),
  "@preload": path.join(appRoot, "src", "preload"),
  "@renderer": path.join(appRoot, "src", "renderer"),
  "@shared": path.join(appRoot, "src", "shared"),
  "@viewer": path.resolve(appRoot, "..", "viewer", "src", "client"),
};

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
export default defineConfig({
  resolve: { alias },
  define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
  test: {
    projects: [
      {
        resolve: { alias },
        define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
        test: {
          name: "node",
          environment: "node",
          include: ["tests/unit/main/**/*.test.ts", "tests/unit/shared/**/*.test.ts"],
        },
      },
      {
        resolve: { alias },
        define: { __APP_VERSION__: JSON.stringify("0.0.0-test") },
        esbuild: { jsx: "automatic" },
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
