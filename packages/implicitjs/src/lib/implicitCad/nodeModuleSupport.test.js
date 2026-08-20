import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { loadImplicitCadModelFromPath } from "./export.js";
import {
  IMPLICIT_JS_MIN_NODE_MAJOR,
  isAmbiguousModuleSyntaxError,
  nodeMajorVersion,
  unsupportedNodeVersionMessage
} from "./nodeModuleSupport.js";

function ambiguousSyntaxError() {
  const error = new SyntaxError("Unexpected token 'export'");
  return error;
}

test("an old Node is named as the cause instead of the model file", () => {
  const message = unsupportedNodeVersionMessage(ambiguousSyntaxError(), {
    inputPath: "/models/orb.implicit.js",
    version: "20.10.0"
  });
  assert.match(message, /Node 20\.10\.0 cannot load a \.implicit\.js model/u);
  assert.match(message, new RegExp(`Node ${IMPLICIT_JS_MIN_NODE_MAJOR} or newer`, "u"));
  assert.match(message, /orb\.implicit\.js/u);
});

test("Node 18, which has no flag to offer, gets the same answer", () => {
  // The runner used to pass --experimental-default-type=module here and die with
  // `bad option`, so this version is the one that most needs a sentence.
  assert.ok(unsupportedNodeVersionMessage(ambiguousSyntaxError(), {
    inputPath: "/models/orb.implicit.js",
    version: "18.17.0"
  }));
});

test("a supported Node keeps the model's own syntax error", () => {
  // The whole value of the message is that it is TRUE. On a Node that can read the
  // syntax, an "Unexpected token 'export'" really is the model's problem, and relabelling
  // it would send the author looking at their interpreter instead of their code.
  assert.equal(
    unsupportedNodeVersionMessage(ambiguousSyntaxError(), {
      inputPath: "/models/orb.implicit.js",
      version: `${IMPLICIT_JS_MIN_NODE_MAJOR}.0.0`
    }),
    null
  );
});

test("a .mjs model is unambiguous to every Node, so nothing is claimed about it", () => {
  assert.equal(
    unsupportedNodeVersionMessage(ambiguousSyntaxError(), {
      inputPath: "/models/orb.implicit.mjs",
      version: "20.10.0"
    }),
    null
  );
});

test("only the two ambiguous-module errors are recognized", () => {
  assert.equal(isAmbiguousModuleSyntaxError(ambiguousSyntaxError()), true);
  assert.equal(
    isAmbiguousModuleSyntaxError(new SyntaxError("Cannot use import statement outside a module")),
    true
  );
  assert.equal(isAmbiguousModuleSyntaxError(new SyntaxError("Unexpected end of input")), false);
  assert.equal(isAmbiguousModuleSyntaxError(new TypeError("not a syntax error")), false);
  assert.equal(isAmbiguousModuleSyntaxError(null), false);
});

test("an unparseable version reads as unsupported rather than as newest", () => {
  assert.equal(nodeMajorVersion("not-a-version"), 0);
});

test("loading a genuinely broken model still reports the model's syntax error", async () => {
  // Wiring: the guard sits around the dynamic import, so it must not swallow the errors it
  // does not explain. This runs on a supported Node, where the error IS the model's.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "implicit-syntax-"));
  const modelPath = path.join(dir, "broken.implicit.js");
  fs.writeFileSync(modelPath, "export default { schema: 'implicit.js/0.1.0',\n", "utf-8");
  await assert.rejects(
    loadImplicitCadModelFromPath(modelPath),
    (error) => error.name === "SyntaxError" && !/cannot load a \.implicit\.js model/u.test(error.message)
  );
});
