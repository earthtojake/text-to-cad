import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

import { appVersion } from "./scripts/app-version.mjs";
const appRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(appRoot, "..", "..");
const alias = {
  "@main": path.join(appRoot, "src", "main"),
  "@preload": path.join(appRoot, "src", "preload"),
  "@renderer": path.join(appRoot, "src", "renderer"),
  "@shared": path.join(appRoot, "src", "shared"),
};

// The Aptabase key is baked in at build time, not read from the environment at
// run time: a packaged app has no build environment to read, and a key that
// could be set by whoever launches the binary is a key anyone can point at
// their own project. Absent (a checkout, a community build) it compiles to "",
// which makes src/main/telemetry.ts inert — no init, no network call.
const aptabaseKey = process.env.HARDCORE_APTABASE_KEY ?? "";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    resolve: { alias },
    define: {
      __APP_VERSION__: JSON.stringify(appVersion()),
      __APTABASE_KEY__: JSON.stringify(aptabaseKey),
    },
    build: {
      rollupOptions: {
        input: { index: path.join(appRoot, "src", "main", "index.ts") },
      },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    resolve: { alias },
    build: {
      rollupOptions: {
        input: { index: path.join(appRoot, "src", "preload", "index.ts") },
      },
    },
  },
  renderer: {
    root: path.join(appRoot, "src", "renderer"),
    // `dedupe` is load-bearing: the viewer's sources sit beside their own
    // node_modules (React 18 there), and Rollup resolves a bare `react` from
    // the importing file's location. Without it the built app carries two
    // Reacts and the file tab dies with React error #525 ("an element from an
    // older version of React was rendered") the moment the CAD surface
    // mounts — in dev, pre-bundling hides it. One React: this app's.
    resolve: {
      alias,
      dedupe: ["react", "react-dom", "three"],
    },
    // The viewer's surf tessellation workers are ES modules, and so are
    // Monaco's. The classic-worker default fails at *run* time, not at build
    // time — a blank pane and a console error, which is the worst kind of
    // default to leave in place.
    worker: { format: "es" },
    define: { __APP_VERSION__: JSON.stringify(appVersion()) },
    plugins: [react(), tailwindcss()],
    // Off Vite's default 5173, which `npm --prefix apps/web run dev` claims
    // with strictPort — the two dev servers have to be able to run together.
    // Matches the `desktop-dev` entry in the repo's .claude/launch.json.
    server: {
      host: "127.0.0.1",
      port: 5273,
      strictPort: true,
      // The viewer's client and @hardcore/core live outside this app's root, so
      // dev has to be allowed to serve them from there.
      fs: { allow: [repoRoot] },
    },
    build: {
      rollupOptions: {
        input: { index: path.join(appRoot, "src", "renderer", "index.html") },
      },
    },
  },
});
