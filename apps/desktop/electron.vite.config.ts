import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import { transformWithEsbuild, type Plugin } from "vite";

import { appVersion } from "./scripts/app-version.mjs";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(appRoot, "..", "..");
const viewerAppRoot = path.join(repoRoot, "apps", "viewer");
const viewerClientRoot = path.join(viewerAppRoot, "src", "client");
const cadJsSource = path.join(repoRoot, "packages", "cadgen-js", "src");
const viewerNodeModules = path.join(viewerAppRoot, "node_modules");

const alias = {
  "@main": path.join(appRoot, "src", "main"),
  "@preload": path.join(appRoot, "src", "preload"),
  "@renderer": path.join(appRoot, "src", "renderer"),
  "@shared": path.join(appRoot, "src", "shared"),
  "@viewer": viewerClientRoot,
};

/**
 * What the CAD Viewer's `./file-view` entry needs resolved, per
 * `apps/viewer/docs/file-view.md`. Renderer only: nothing in main or preload
 * imports the viewer.
 *
 * `"@"` is the viewer client's own root alias. It cannot collide with this
 * app's `@renderer`/`@shared`/`@viewer` or with a scoped package: Vite matches
 * a string alias as `id === key || id.startsWith(key + "/")`, so `"@"` only
 * ever claims `@/…`.
 *
 * `three` is pinned to the viewer's copy on purpose. Two copies of three.js in
 * one bundle is a silent-wrong-render bug rather than a build error — the doc
 * calls it out, and it is the trap worth spending an alias on.
 */
const viewerAlias = {
  "@": viewerClientRoot,
  "cadgen-js": cadJsSource,
  three: path.join(viewerNodeModules, "three"),
  "three/examples": path.join(viewerNodeModules, "three", "examples"),
};

// The CAD Viewer's client is JSX written in `.js` files. `apps/viewer`'s own
// Vite config feeds every source file through esbuild's `jsx` loader:
//
//   esbuild: { loader: "jsx", include: /.*\.[jt]sx?$/, exclude: [] }
//
// Mirroring that verbatim here would be wrong: this app's sources are
// TypeScript, and the `jsx` loader parses `<T>` as an element, so every
// generic and every `.tsx` file would fail to build. Same loader, same intent,
// scoped to the viewer's tree instead of the whole graph. The explorer's CAD
// renderer (features/explorer/renderers/CadRenderer.tsx) is what pulls that
// tree in, lazily.
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

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    resolve: { alias },
    define: { __APP_VERSION__: JSON.stringify(appVersion()) },
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
    resolve: { alias: { ...alias, ...viewerAlias } },
    // The viewer's surf tessellation workers are ES modules, and so are
    // Monaco's. The classic-worker default fails at *run* time, not at build
    // time — a blank pane and a console error, which is the worst kind of
    // default to leave in place.
    worker: { format: "es" },
    define: { __APP_VERSION__: JSON.stringify(appVersion()) },
    plugins: [viewerJsxPlugin(), react(), tailwindcss()],
    // Off Vite's default 5173, which `npm --prefix apps/viewer run dev` claims
    // with strictPort — the two dev servers have to be able to run together.
    // Matches the `desktop-dev` entry in the repo's .claude/launch.json.
    server: {
      host: "127.0.0.1",
      port: 5273,
      strictPort: true,
      // The viewer's client and cadgen-js live outside this app's root, so
      // dev has to be allowed to serve them from there.
      fs: { allow: [appRoot, viewerAppRoot, cadJsSource] },
    },
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
