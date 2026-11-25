// Box selection is ONE gesture and ONE look in every viewer (`useBoxSelectGesture.js`): a 3D view's
// Box select through `RendererShell`, every flat view's Select through `useFlatBoxSelect`. A renderer
// that grows its own drag-to-box (a drag handler on the flat canvas, a box painted on its canvas, an
// element of its own) is the drift this holds off.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const RENDERERS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const FLAT = ["board/BoardRenderer.jsx", "schematic/SchematicRenderer.jsx", "dxf/DxfRenderer.jsx"];
const read = file => fs.readFileSync(path.join(RENDERERS, file), "utf8");
const sources = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
  const at = path.join(dir, entry.name);
  return entry.isDirectory() ? sources(at) : /\.(jsx?|tsx?)$/.test(entry.name) && !/\.test\./.test(entry.name) ? [at] : [];
});

test("every flat renderer draws its box through the shared gesture, and none keeps a drag box of its own", () => {
  for (const file of FLAT) {
    const source = read(file);
    assert.match(source, /useFlatBoxSelect\(/, `${file} adopts the shared box`);
    assert.doesNotMatch(source, /\bonDrag\b|\bdraftRef\b/, `${file} has no drag box of its own`);
  }
  assert.doesNotMatch(read("kit/viewport/useFlatCanvasView.js"), /\bonDrag\b/, "the flat canvas hands no drag to a tool");
});

test("the box is drawn in one place", () => {
  const drawers = sources(RENDERERS).filter(file => fs.readFileSync(file, "utf8").includes("data-box-select"))
    .map(file => path.relative(RENDERERS, file));
  assert.deepEqual(drawers, [path.join("kit", "tools", "select", "useBoxSelectGesture.js")]);
});
