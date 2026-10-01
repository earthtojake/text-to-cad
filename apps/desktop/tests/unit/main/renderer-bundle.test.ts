/**
 * The built renderer carries each module once. Two copies of one library
 * resolved from two places (`@streamdown/code`'s nested shiki 3 beside this
 * app's shiki 4 was ~230 grammars and themes, ~6 MB) come out as chunk pairs
 * with the same name and the same bytes under different hashes — nothing
 * fails, the app is just that much larger. `electron.vite.config.ts`'s
 * `dedupe` is what keeps them one.
 *
 * It reads `out/renderer`, so it has something to say only after
 * `npm run build`. A plain run without a build, or with one older than the
 * config it checks (a unit run before the build step sees the previous
 * build), logs why and passes. CI's Desktop job runs its unit tests before
 * it builds, so it runs this file again after the build with
 * `TEXT_TO_CAD_BUNDLE_CHECK=1`, under which a missing bundle fails instead:
 * a check that can always stand aside is a check no job runs. The age guard
 * is not applied there — a build restored from cache keeps its old times
 * under a fresh checkout's, and the cache key is the build's inputs.
 */
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const app = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const assets = path.join(app, "out", "renderer", "assets");
const config = path.join(app, "electron.vite.config.ts");
const required = process.env.TEXT_TO_CAD_BUNDLE_CHECK === "1";

/** `abap-B7h4dtBh.js` → `abap.js`: Rollup's eight-character hash dropped. */
const baseName = (file: string) => file.replace(/-[A-Za-z0-9_-]{8}(\.[a-z0-9]+)$/, "$1");

/**
 * The chunks emitted more than once, as `a = b` lines; or `null` when there
 * is no build to read (or only a stale one) and the run did not require one.
 */
function bundleTwins(options: { assets: string; config: string; required: boolean }): string[] | null {
  if (!existsSync(options.assets)) {
    if (options.required) throw new Error(`renderer-bundle: no ${options.assets}; the bundle check runs after \`npm run build\``);
    console.info(`renderer-bundle: no ${options.assets}; run \`npm run build\` to check the bundle`);
    return null;
  }
  if (!options.required && statSync(options.assets).mtimeMs < statSync(options.config).mtimeMs) {
    console.info(`renderer-bundle: ${options.assets} predates electron.vite.config.ts; run \`npm run build\` to check the bundle`);
    return null;
  }
  const seen = new Map<string, string[]>();
  const chunks = readdirSync(options.assets).filter((file) => /\.(js|css|wasm)$/.test(file));
  // No chunks is no bundle, and an empty list of twins would call it clean.
  if (chunks.length === 0) {
    if (options.required) throw new Error(`renderer-bundle: ${options.assets} holds no js, css or wasm chunks`);
    console.info(`renderer-bundle: ${options.assets} holds no chunks; run \`npm run build\` to check the bundle`);
    return null;
  }
  for (const file of chunks) {
    const key = `${baseName(file)} ${statSync(path.join(options.assets, file)).size}`;
    seen.set(key, [...(seen.get(key) ?? []), file]);
  }
  return [...seen.values()].filter((files) => files.length > 1).map((files) => files.join(" = "));
}

it("emits no two chunks with one name and one size", () => {
  const twins = bundleTwins({ assets, config, required });
  if (twins === null) return;
  expect(twins, `${twins.length} chunk(s) emitted more than once`).toEqual([]);
});

it("fails without a bundle when the run requires one, and stands aside when it does not", () => {
  const missing = path.join(app, "out", "no-such-renderer", "assets");
  expect(() => bundleTwins({ assets: missing, config, required: true })).toThrow(/no .*no-such-renderer/);
  expect(bundleTwins({ assets: missing, config, required: false })).toBeNull();
});

it("fails an empty assets directory when the run requires a bundle, and stands aside when it does not", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "renderer-bundle-"));
  try {
    const empty = path.join(dir, "assets");
    mkdirSync(empty);
    writeFileSync(path.join(empty, "index.html"), "");
    expect(() => bundleTwins({ assets: empty, config, required: true })).toThrow(/holds no js, css or wasm chunks/);
    expect(bundleTwins({ assets: empty, config, required: false })).toBeNull();
    writeFileSync(path.join(empty, "a-B7h4dtBh.js"), "x");
    writeFileSync(path.join(empty, "a-C8i5euCi.js"), "x");
    expect(bundleTwins({ assets: empty, config, required: true })).toEqual(["a-B7h4dtBh.js = a-C8i5euCi.js"]);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
