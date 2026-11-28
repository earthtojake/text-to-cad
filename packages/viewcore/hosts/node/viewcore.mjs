// Node host of the view core (viewcore.wasm): the browser host's own loader and WASI shim (../web/viewcore.js),
// with the module read from a file. The same module and the same shim, so a page and Node answer the same bytes.
//
//   import { loadCore } from "./viewcore.mjs";
//   const core = await loadCore();                      // ../../dist/viewcore.wasm, or loadCore(path)
//   const doc = core.openXbf(fs.readFileSync("m.xbf"), "m");      // a document: structure, parts, exports
//   const part = core.openShape(shapeBytes);                      // a part's canonical shape bytes by themselves
//   part.mesh(0); part.unmeshed(0); part.tableBytes(0, [3, 7]); part.measureBytes(0); part.close();
//
// The module uses the standard (exnref) WebAssembly exceptions, which Node loads from 22: an earlier Node is
// refused in one line.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { Core, Doc, EXPORTS, ViewCoreError } from "../web/viewcore.js";

export { Core, Doc, EXPORTS, ViewCoreError };

/** The Node this host needs, by its major version. */
export const NODE_MAJOR = 22;

/** Where the build puts the module (scripts/core.sh). */
export const DEFAULT_WASM = fileURLToPath(new URL("../../dist/viewcore.wasm", import.meta.url));

/** The core loaded from `path`; its log lines (the module's stdout and stderr) go to `log(fd, line)`, stderr by default. */
export async function loadCore(path = DEFAULT_WASM, { log = (_fd, line) => process.stderr.write(`[core] ${line}\n`) } = {}) {
  const major = Number(process.versions.node.split(".")[0]);
  if (major < NODE_MAJOR) {
    throw new ViewCoreError(`the view core needs Node ${NODE_MAJOR} or later (this is ${process.versions.node}): it uses WebAssembly exceptions an earlier Node does not load`);
  }
  return Core.load(readFileSync(path), { log });
}
