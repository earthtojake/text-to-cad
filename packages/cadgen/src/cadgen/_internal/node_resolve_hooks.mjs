/**
 * ESM resolve hook: make bare `implicitjs/...` / `cadjs/...` specifiers resolvable in a
 * builder child that has no `node_modules`.
 *
 * The published skill runtime ships `packages/implicitjs` and `packages/cadjs` as SOURCE
 * with no `node_modules` anywhere, so a builder's `import … from "implicitjs/glb/…"` has
 * nothing to resolve against. `NODE_PATH=<packages>` fixes that for CommonJS -- a NODE_PATH
 * entry is treated as a `node_modules` directory, so `packages/implicitjs` resolves as the
 * package `implicitjs` *through its exports map* -- but **Node's ESM resolver ignores
 * NODE_PATH entirely** (verified on v22.22.0: the import throws ERR_MODULE_NOT_FOUND while
 * `require.resolve` on the same specifier, same env, returns the right file). esbuild honors
 * NODE_PATH itself, which is why the bundling path in `bundle-cad.sh` never hit this.
 *
 * So this hook forwards the specifier the ESM resolver could not see to the CJS resolver,
 * which CAN see NODE_PATH and which applies the package's exports map for us. Nothing about
 * the exports map is re-implemented here -- reimplementing it is exactly the mistake a
 * directory alias makes.
 *
 * Order matters: `nextResolve` runs FIRST, so a real `node_modules` (the dev checkout, where
 * `packages/cadjs/node_modules/implicitjs` is a workspace link), relative imports, `node:`
 * builtins and everything else behave exactly as they would without the hook. This is a
 * fallback for the one case that would otherwise be fatal, not a new resolution policy.
 */

import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);

// Relative/absolute paths and anything with a scheme (node:, file:, data:) are the ESM
// resolver's business alone; only BARE specifiers can be helped by NODE_PATH.
const NOT_BARE = /^(?:\.{1,2}\/|\/|#|[a-zA-Z][a-zA-Z0-9+.-]*:)/;

export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (error) {
    if (NOT_BARE.test(specifier)) throw error;
    let filename;
    try {
      filename = require.resolve(specifier);
    } catch {
      // Re-throw the ESM resolver's error, not ours: it names the importing module.
      throw error;
    }
    // No `format`: let Node decide from the resolved package's own `type`.
    return { url: pathToFileURL(filename).href, shortCircuit: true };
  }
}
