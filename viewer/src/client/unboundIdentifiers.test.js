// Every identifier the client READS must be bound somewhere: imported, declared, a
// parameter, or a real browser global.
//
// This exists because nothing else in the toolchain asks that question. A bundler treats an
// unbound identifier as a global reference and emits it without complaint, and a unit suite
// only covers modules it imports — so `normalizeThemeSettings`, called twice in
// ThemeSettingsPopover.js with no import, shipped through a clean `vite build` and a green
// test run and threw a ReferenceError that crashed <CadWorkspace> the moment anyone changed
// a theme colour. The same commit that removed the import removed the callers of the one
// helper that used it, which is exactly how the survivor went unnoticed.
//
// It is a whole-tree check rather than a test of that one function on purpose: the failure
// mode is "a deletion left a reference behind", and that can land in any file. A large merge
// is when it happens most — the G-code and client-DXF removals left six such references
// across two files.
//
// Scope is what makes this precise rather than a grep: Babel resolves each reference against
// its enclosing scopes, so shadowing, hoisting, destructuring and JSX all behave correctly
// and locals never look like globals.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parse } from "@babel/parser";
import traverseModule from "@babel/traverse";

// @babel/traverse is CJS; its ESM default is the namespace under some resolvers.
const traverse = traverseModule.default ?? traverseModule;

const CLIENT_ROOT = path.dirname(fileURLToPath(import.meta.url));

// Globals the browser (and the test runner, for the few node-facing modules here) provides.
// Deliberately explicit: an allowlist that grows by hand is the point — a new name showing up
// here should be a decision, not a silent pass.
const RUNTIME_GLOBALS = new Set([
  // Core language
  "globalThis", "undefined", "NaN", "Infinity", "Object", "Array", "Function", "Boolean",
  "Number", "String", "Symbol", "BigInt", "Math", "JSON", "Date", "RegExp", "Error",
  "TypeError", "RangeError", "SyntaxError", "Promise", "Proxy", "Reflect", "Intl",
  "Map", "Set", "WeakMap", "WeakSet", "isNaN", "isFinite", "parseInt", "parseFloat",
  "encodeURIComponent", "decodeURIComponent", "encodeURI", "decodeURI", "structuredClone",
  // Typed arrays and buffers
  "ArrayBuffer", "SharedArrayBuffer", "DataView", "Int8Array", "Uint8Array",
  "Uint8ClampedArray", "Int16Array", "Uint16Array", "Int32Array", "Uint32Array",
  "Float32Array", "Float64Array", "BigInt64Array", "BigUint64Array",
  // DOM and BOM
  "window", "document", "navigator", "location", "history", "screen", "customElements",
  "HTMLElement", "HTMLInputElement", "HTMLCanvasElement", "Element", "Node", "NodeList",
  "Event", "CustomEvent", "MouseEvent", "KeyboardEvent", "PointerEvent", "WheelEvent",
  "DOMParser", "XMLSerializer", "DOMException", "CSS", "getComputedStyle", "matchMedia",
  "localStorage", "sessionStorage", "alert", "confirm", "prompt",
  // Timers and scheduling
  "setTimeout", "clearTimeout", "setInterval", "clearInterval", "queueMicrotask",
  "requestAnimationFrame", "cancelAnimationFrame", "requestIdleCallback", "cancelIdleCallback",
  "performance", "console",
  // Network and workers
  "fetch", "Request", "Response", "Headers", "FormData", "AbortController", "AbortSignal",
  "URL", "URLSearchParams", "WebSocket", "EventSource", "Worker", "MessageChannel",
  "BroadcastChannel", "postMessage", "self", "crypto",
  // Files and encoding
  "Blob", "File", "FileReader", "FileList", "Image", "ImageData", "OffscreenCanvas",
  "TextEncoder", "TextDecoder", "atob", "btoa", "ReadableStream", "WritableStream",
  // Observers
  "ResizeObserver", "IntersectionObserver", "MutationObserver", "PerformanceObserver",
  // Node-facing (a few modules under src/ run in the test runner, not the browser)
  "process", "Buffer", "__dirname", "__filename",
]);

function clientSourceFiles(dir, found = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "node_modules") {
        clientSourceFiles(entryPath, found);
      }
    } else if (/\.jsx?$/u.test(entry.name)) {
      found.push(entryPath);
    }
  }
  return found;
}

function unboundReferences(filePath) {
  const source = fs.readFileSync(filePath, "utf8");
  const ast = parse(source, {
    sourceType: "module",
    plugins: ["jsx", "classProperties", "classPrivateProperties", "topLevelAwait"],
  });

  const unbound = [];
  traverse(ast, {
    ReferencedIdentifier(nodePath) {
      const { name } = nodePath.node;
      if (RUNTIME_GLOBALS.has(name)) {
        return;
      }
      // A lowercase JSX tag is an intrinsic element (`div`), not an identifier reference.
      const parentType = nodePath.parent.type;
      if ((parentType === "JSXOpeningElement" || parentType === "JSXClosingElement")
        && /^[a-z]/u.test(name)) {
        return;
      }
      // `true` walks up through every enclosing scope, so a name bound in any ancestor —
      // module import, outer closure, function parameter — counts as bound.
      if (nodePath.scope.hasBinding(name, true)) {
        return;
      }
      unbound.push(`${path.relative(CLIENT_ROOT, filePath)}:${nodePath.node.loc.start.line} ${name}`);
    },
  });
  return unbound;
}

test("every identifier the client reads is bound", () => {
  const files = clientSourceFiles(CLIENT_ROOT);
  assert.ok(files.length > 50, `expected the client tree at ${CLIENT_ROOT}, found ${files.length} files`);

  const offenders = files.flatMap((file) => unboundReferences(file));
  assert.deepEqual(
    offenders,
    [],
    "unbound identifiers — each is a ReferenceError the bundler will happily ship:\n  "
    + offenders.join("\n  ")
    + "\nImport it, declare it, delete the dead reference, or add a real browser global to "
    + "RUNTIME_GLOBALS.",
  );
});

test("the check fails on an unbound reference", () => {
  // Guards the guard. A scope walk that silently matched nothing would pass this file's real
  // test forever, so pin the positive case: an identifier that is used and never bound is
  // reported, and the same identifier is NOT reported once a binding exists.
  const withoutBinding = "export const run = () => missingHelper(1);\n";
  const withBinding = "import { missingHelper } from \"x\";\nexport const run = () => missingHelper(1);\n";
  const probe = path.join(CLIENT_ROOT, ".unbound-identifiers-probe.js");

  try {
    fs.writeFileSync(probe, withoutBinding);
    assert.deepEqual(
      unboundReferences(probe).map((entry) => entry.split(" ").pop()),
      ["missingHelper"],
    );

    fs.writeFileSync(probe, withBinding);
    assert.deepEqual(unboundReferences(probe), []);
  } finally {
    fs.rmSync(probe, { force: true });
  }
});
