import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import { transformWithEsbuild, type Plugin } from "vite";

import { appVersion } from "./scripts/app-version.mjs";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const viewerClientRoot = path.resolve(appRoot, "..", "viewer", "src", "client");

const alias = {
  "@main": path.join(appRoot, "src", "main"),
  "@preload": path.join(appRoot, "src", "preload"),
  "@renderer": path.join(appRoot, "src", "renderer"),
  "@shared": path.join(appRoot, "src", "shared"),
  "@viewer": viewerClientRoot,
};

// The CAD Viewer's client is JSX written in `.js` files. `apps/viewer`'s own
// Vite config feeds every source file through esbuild's `jsx` loader:
//
//   esbuild: { loader: "jsx", include: /.*\.[jt]sx?$/, exclude: [] }
//
// Mirroring that verbatim here would be wrong: this app's sources are
// TypeScript, and the `jsx` loader parses `<T>` as an element, so every
// generic and every `.tsx` file would fail to build. Same loader, same intent,
// scoped to the viewer's tree instead of the whole graph. P4 (viewer
// extraction) turns this on for real; nothing imports `@viewer/*` yet.
function viewerJsxPlugin(): Plugin {
  return {
    name: "hardcore:viewer-jsx",
    enforce: "pre",
    async transform(code, id) {
      const file = id.split("?")[0] ?? id;
      if (!file.endsWith(".js") || !file.startsWith(viewerClientRoot + path.sep)) {
        return null;
      }
      const result = await transformWithEsbuild(code, file, {
        loader: "jsx",
        jsx: "automatic",
        jsxImportSource: "react",
      });
      // esbuild's SourceMap allows null entries in `sourcesContent`; Rollup's
      // does not. Handing the map straight back is a type error, and the map
      // itself is of no use for a file we did not author.
      return { code: result.code, map: null };
    },
  };
}

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
    resolve: { alias },
    define: { __APP_VERSION__: JSON.stringify(appVersion()) },
    plugins: [viewerJsxPlugin(), react(), tailwindcss()],
    // Off Vite's default 5173, which `npm --prefix apps/viewer run dev` claims
    // with strictPort — the two dev servers have to be able to run together.
    // Matches the `desktop-dev` entry in the repo's .claude/launch.json.
    server: { host: "127.0.0.1", port: 5273, strictPort: true },
    optimizeDeps: {
      // The viewer's `.js` sources again, this time for dependency
      // pre-bundling. Copied from apps/viewer/vite.config.mjs unchanged.
      esbuildOptions: {
        loader: { ".js": "jsx" },
      },
    },
    build: {
      rollupOptions: {
        input: { index: path.join(appRoot, "src", "renderer", "index.html") },
      },
    },
  },
});
