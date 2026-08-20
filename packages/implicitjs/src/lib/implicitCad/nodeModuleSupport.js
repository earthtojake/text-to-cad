/** Why a `.implicit.js` model fails to import on an older Node, said out loud.
 *
 * An implicit model is a bare `.js` file whose body is `export default { ... }`, and it
 * normally sits in a model folder with no `package.json` above it -- so nothing tells Node
 * it is a module. Node 22 works that out by DETECTING module syntax in an ambiguous `.js`.
 * Earlier versions compile it as CommonJS and throw `SyntaxError: Unexpected token 'export'`,
 * which reads as "your model file is broken" when the model is fine and the interpreter is
 * the problem.
 *
 * Node 20 and 21 have `--experimental-default-type=module`, which fixes the import in the
 * process that passes it -- and nothing else. It does not reach a child process, so a CLI
 * spawned by that process fails anyway; and Node 18 does not have the flag at all, where
 * passing it kills the process with `bad option`. That is the whole reason this is reported
 * rather than worked around.
 */

/** The first Node major that reads module syntax out of an extensionless-intent `.js`. */
export const IMPLICIT_JS_MIN_NODE_MAJOR = 22;

export function nodeMajorVersion(version = process.versions.node) {
  const major = Number.parseInt(String(version || "").split(".")[0], 10);
  return Number.isFinite(major) ? major : 0;
}

/** True when ``error`` is Node refusing to read module syntax out of a plain `.js`. */
export function isAmbiguousModuleSyntaxError(error) {
  if (!error || error.name !== "SyntaxError") {
    return false;
  }
  const message = String(error.message || "");
  return (
    message.includes("Unexpected token 'export'")
    || message.includes("Cannot use import statement outside a module")
  );
}

/** The message to raise instead of the SyntaxError, or null to let the original stand.
 *
 * Null for a `.mjs` input, or on a Node that supports the syntax: there the SyntaxError is
 * about the model's own code and replacing it would hide a real authoring mistake. */
export function unsupportedNodeVersionMessage(error, {
  inputPath,
  version = process.versions.node,
} = {}) {
  if (!isAmbiguousModuleSyntaxError(error)) {
    return null;
  }
  if (/\.mjs$/i.test(String(inputPath || ""))) {
    return null;
  }
  if (nodeMajorVersion(version) >= IMPLICIT_JS_MIN_NODE_MAJOR) {
    return null;
  }
  return (
    `Node ${version} cannot load a .implicit.js model: reading module syntax out of a plain `
    + `.js file needs Node ${IMPLICIT_JS_MIN_NODE_MAJOR} or newer. Upgrade Node, or rename `
    + `the model to .implicit.mjs. (${inputPath})`
  );
}
