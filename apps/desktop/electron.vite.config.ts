import { readFileSync } from "node:fs";
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
const cadJsSource = path.join(repoRoot, "packages", "cadgen-js", "src");
// The viewer's client on disk. Module ids carry this path, so anything
// matching on a prefix compares against it.
const viewerClientRoots = [path.join(viewerAppRoot, "src", "client")];

const alias = {
  "@main": path.join(appRoot, "src", "main"),
  "@preload": path.join(appRoot, "src", "preload"),
  "@renderer": path.join(appRoot, "src", "renderer"),
  "@shared": path.join(appRoot, "src", "shared"),
};

/**
 * What the CAD Viewer's `./file-view` entry needs resolved.
 *
 * `cad-viewer` and `cadgen-js` are real dependencies of this app now (`file:`
 * links to the siblings), so their sources are build inputs this app installs
 * for rather than borrows. Borrowing was the CI failure: the viewer's imports
 * were resolved by walking up from `apps/viewer`, which a clean `npm ci` here
 * never populates.
 *
 * Resolution is pinned rather than walked. Every package the siblings depend
 * on is aliased to THIS app's copy — the bare name and each subpath its
 * `exports` map publishes, so `meshoptimizer/decoder` still lands on the file
 * that map names. Walking would find the sibling's own `node_modules` first on
 * a developer's machine and this app's on CI, which is how a build passes in
 * one place and fails in the other; it is also how a stale sibling install
 * (`apps/viewer` currently holds packages older than its own manifest asks
 * for) would quietly become what this app ships.
 *
 * `"@"` is the viewer client's own root alias. It cannot collide with this
 * app's `@renderer`/`@shared` or with a scoped package: Vite matches a string
 * alias as `id === key || id.startsWith(key + "/")`, so `"@"` only ever claims
 * `@/…`. One copy of each peer is the point, not a nicety: two copies of
 * three.js in one bundle is a silent-wrong-render bug rather than a build
 * error. `tests/unit/main/viewer-peers.test.ts` checks the versions agree.
 */
function dependenciesOf(manifest: string): string[] {
  return Object.keys(JSON.parse(readFileSync(manifest, "utf8")).dependencies ?? {});
}

/**
 * One alias per specifier a package publishes: every `exports` subpath, then
 * the bare name pointing at the package directory. Vite matches a string alias
 * on `id === key || id.startsWith(key + "/")` and takes the first that hits,
 * so the subpaths are emitted before the bare name — otherwise `react` would
 * claim `react/jsx-runtime` and rewrite it to a path inside a file.
 *
 * The subpaths are what a directory alias alone cannot do: `meshoptimizer`
 * publishes `./decoder` as `meshopt_decoder.mjs`, a name no prefix rewrite
 * would ever produce.
 */
function aliasesForPackage(name: string): Array<[string, string]> {
  const root = path.join(appRoot, "node_modules", name);
  const manifest = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
  const target = (value: unknown): string | null => {
    if (typeof value === "string") {
      return path.join(root, value);
    }
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      return target(record.import ?? record.default ?? record.require ?? record.node);
    }
    return null;
  };
  const entries: Array<[string, string]> = [];
  const exported = manifest.exports;
  if (exported && typeof exported === "object" && !Array.isArray(exported)) {
    for (const [key, value] of Object.entries(exported as Record<string, unknown>)) {
      if (!key.startsWith("./")) {
        continue;
      }
      const resolved = target(value);
      if (!resolved) {
        continue;
      }
      entries.push([
        `${name}/${key.slice(2)}`.replace(/\/\*$/, ""),
        resolved.replace(/[\\/]\*$/, ""),
      ]);
    }
  }
  entries.push([name, root]);
  return entries;
}

// `cadgen-js` is in the list like any other: it is a dependency of this app
// too, and its own `exports` map already points at its sources, so aliasing it
// needs no special case and no separate source path.
const linkedPeers = [
  "cadgen-js",
  ...dependenciesOf(path.join(viewerAppRoot, "package.json")),
  ...dependenciesOf(path.join(repoRoot, "packages", "cadgen-js", "package.json")),
];

const viewerAlias = Object.fromEntries([
  ["@", path.join(viewerAppRoot, "src", "client")] as [string, string],
  ...[...new Set(linkedPeers)]
    .flatMap(aliasesForPackage)
    .sort(([a], [b]) => b.length - a.length),
]);// The CAD Viewer's client is JSX written in `.js` files. `apps/viewer`'s own
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
      if (!file.endsWith(".js") || !viewerClientRoots.some((root) => file.startsWith(root + path.sep))) {
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
    // `dedupe` is load-bearing: the viewer's sources sit beside their own
    // node_modules (React 18 there), and Rollup resolves a bare `react` from
    // the importing file's location. Without it the built app carries two
    // Reacts and the file tab dies with React error #525 ("an element from an
    // older version of React was rendered") the moment the CAD surface
    // mounts — in dev, pre-bundling hides it. One React: this app's.
    resolve: {
      alias: { ...alias, ...viewerAlias },
      dedupe: ["react", "react-dom", "three"],
    },
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
