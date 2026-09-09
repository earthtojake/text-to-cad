import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * What the CAD Viewer's sources need resolved — for the app's bundler and for
 * the test runner, from one implementation.
 *
 * `cad-viewer` and `cadgen-js` are real dependencies of this app (`file:`
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
 * (`apps/viewer` can hold packages older than its own manifest asks for) would
 * quietly become what this app ships.
 *
 * `"@"` is the viewer client's own root alias. It cannot collide with this
 * app's `@renderer`/`@shared` or with a scoped package: Vite matches a string
 * alias as `id === key || id.startsWith(key + "/")`, so `"@"` only ever claims
 * `@/…`. One copy of each peer is the point, not a nicety: two copies of
 * three.js in one bundle is a silent-wrong-render bug rather than a build
 * error, and two Reacts is "an element from an older version of React" the
 * moment a viewer component mounts.
 * `tests/unit/main/viewer-peers.test.ts` checks the versions agree.
 *
 * Shared with `vitest.config.ts` because the unit tests render the file tab,
 * and the file tab draws `cad-viewer/shell`. A test run resolving the viewer's
 * peers differently from the build is a test run of different code.
 */

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const viewerAppRoot = path.join(repoRoot, "apps", "viewer");

/** @param {string} manifest */
function dependenciesOf(manifest) {
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
 *
 * @param {string} name
 * @returns {Array<[string, string]>}
 */
function aliasesForPackage(name) {
  const root = path.join(appRoot, "node_modules", name);
  const manifest = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
  /** @param {unknown} value @returns {string | null} */
  const target = (value) => {
    if (typeof value === "string") {
      return path.join(root, value);
    }
    if (value && typeof value === "object") {
      const record = /** @type {Record<string, unknown>} */ (value);
      return target(record.import ?? record.default ?? record.require ?? record.node);
    }
    return null;
  };
  /** @type {Array<[string, string]>} */
  const entries = [];
  const exported = manifest.exports;
  if (exported && typeof exported === "object" && !Array.isArray(exported)) {
    for (const [key, value] of Object.entries(exported)) {
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

/** The viewer client's own root. */
export const viewerClientRoot = path.join(viewerAppRoot, "src", "client");

/**
 * The alias pairs, longest key first so a subpath is never eaten by its
 * package's bare name.
 *
 * @returns {Array<[string, string]>}
 */
export function viewerAliasEntries() {
  return [
    ["@", viewerClientRoot],
    ...viewerPeerNames()
      .flatMap(aliasesForPackage)
      .sort(([a], [b]) => b.length - a.length),
  ];
}

/** The same pairs as the object form Vite's `resolve.alias` takes. */
export function viewerAlias() {
  return Object.fromEntries(viewerAliasEntries());
}

/**
 * Every package the siblings’ sources import by name.
 *
 * The build pins these by alias; the test runner names them for
 * `resolve.dedupe` instead. Two ways to say "one copy, this app’s", and which
 * one works depends on the resolver: Rollup resolves an alias pointing at a
 * package DIRECTORY through its `package.json`, and Vite’s dev/SSR pipeline —
 * which is what Vitest runs — does not, so rewriting `radix-ui` to a directory
 * there is an unresolvable import. `dedupe` says the same thing in terms that
 * pipeline understands: a bare specifier for one of these resolves from the
 * project root, wherever it was imported from.
 *
 * `cadgen-js` is in the list like any other: it is a dependency of this app
 * too, and its own `exports` map already points at its sources, so it needs no
 * special case and no separate source path.
 *
 * @returns {string[]}
 */
export function viewerPeerNames() {
  return [
    ...new Set([
      "cadgen-js",
      ...dependenciesOf(path.join(viewerAppRoot, "package.json")),
      ...dependenciesOf(path.join(repoRoot, "packages", "cadgen-js", "package.json")),
    ]),
  ];
}
