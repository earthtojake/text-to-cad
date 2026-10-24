// Explode of an engine document, pinned to one layout for the viewer and cadgen's stills.
//
// `__fixtures__/explode.json` holds, for two documents the engine served -- the material fixture
// (`tests/python/packages/cadgen/engine/test_materials.py`'s bench) and the corpus's motorbike --
// what this scene explodes: the document's tree, each instance's prototype and matrix, and each
// prototype's box (every node, edge point and vertex of its mesh, which is all of a part the layout
// measures); and where each instance's carrier stood at each amount when the fixture was made, by
// this scene over the served part buffers themselves. A part here is two nodes at its box's corners:
// the box the scene measures, so the carriers stand where they stood over the real meshes. It holds
// too the layout's nested branch, which an xbf scene does not reach (it hands the layout no
// hierarchy), over a set of records with one. cadgen's stills port the layout to Python
// (`cadgen/engine/render/explode.py`) and are held to this same file
// (`tests/python/packages/cadgen/engine/test_render_explode.py`), so the two explode alike: a
// deliberate change to the layout changes the fixture's offsets, and the port follows it.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import * as THREE from "three";

import { applyExplodedViewProgress, computeExplodedViewLayout } from "../viewer/explodedView.js";
import { loadXbfDocument } from "./xbfDocument.js";
import { XBM_HEADER_BYTES, XBM_MAGIC, XBM_VERSION } from "./xbm.js";
import { createXbfScene } from "./xbfScene.js";

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__");
const GOLDEN = JSON.parse(fs.readFileSync(path.join(FIXTURES, "explode.json"), "utf8"));
// The engine's look, which a document is read with (`xbfLook.js`); Explode does not depend on it.
const LOOK = fs.readFileSync(path.join(FIXTURES, "look.json"), "utf8");
// Its environment image: 1 x 1, radiance 1 (RGBE 255, 255, 255, e 128).
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode("#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n"),
  255, 255, 255, 128]).buffer;
const URL_BASE = "http://127.0.0.1:9/api/doc/explode";
const TOLERANCE = 1e-6;

/** An XBM2 part buffer of two nodes, a box's corners; none for a part that draws nothing. */
function boxPart(box) {
  const nodes = box ? 2 : 0;
  const buffer = new ArrayBuffer(XBM_HEADER_BYTES + nodes * 24);
  const head = new DataView(buffer);
  head.setUint32(0, XBM_MAGIC, true);
  head.setUint32(4, XBM_VERSION, true);
  head.setUint32(8, nodes, true);
  const after = XBM_HEADER_BYTES + nodes * 12;
  [XBM_HEADER_BYTES, after, ...Array(5).fill(after + nodes * 12)].forEach((offset, at) => head.setUint32(32 + at * 4, offset, true));
  if (box) new Float32Array(buffer, XBM_HEADER_BYTES, 6).set([...box[0], ...box[1]]);
  return buffer;
}

/** The scene the fixture describes: its instances where the fixture places them, each part its box. */
async function sceneOf(fixture) {
  const structure = {
    name: "explode", version: "1",
    prototypes: fixture.boxes.map((_box, index) => ({ key: `p${index}`, name: `p${index}` })),
    instances: fixture.instances.map((instance, index) => ({ ...instance, path: `i${index}` })),
    tree: fixture.tree
  };
  const fetch = async (url) => {
    if (url.endsWith("/api/look")) return new Response(LOOK);
    if (url.endsWith("/api/look/environment")) return new Response(ENVIRONMENT);
    const rest = url.slice(URL_BASE.length);
    if (rest === "") return new Response(JSON.stringify(structure));
    const part = /^\/part\/p(\d+)$/.exec(rest);
    if (part) return new Response(boxPart(fixture.boxes[Number(part[1])]));
    return new Response(JSON.stringify({ error: "not found" }), { status: 404 });
  };
  const document = await loadXbfDocument(URL_BASE, { fetch });
  const scene = createXbfScene(THREE, document);
  const carriers = new Map();
  for (const carrier of scene.object3D.children) {
    const index = carrier.children[0]?.userData?.xbfInstance;
    if (Number.isInteger(index)) carriers.set(index, carrier);
  }
  return { scene, document, carriers };
}

function near(found, expected, label) {
  assert.equal(found.length, expected.length, label);
  found.forEach((value, at) => assert.ok(Math.abs(value - expected[at]) <= TOLERANCE, `${label}[${at}]: ${value} is not ${expected[at]}`));
}

test("an engine document's instances explode where the fixture holds them, at every amount", async () => {
  for (const [name, fixture] of Object.entries(GOLDEN.scenes)) {
    const { scene, document, carriers } = await sceneOf(fixture);
    assert.equal(scene.explodeParts, fixture.instances.length, name);
    for (const amount of GOLDEN.amounts) {
      scene.setExplode(amount);
      fixture.instances.forEach((_instance, index) => near(carriers.get(index).position.toArray(), fixture.offsets[amount][index],
        `${name} at ${amount}, instance ${index}`));
    }
    assert.ok(fixture.offsets[1].every(offset => Math.hypot(...offset) > 0), `${name}: every instance moves at the full amount`);
    scene.dispose();
    document.release();
  }
});

test("the layout's nested branch (a hierarchy) moves each record where the fixture holds it", () => {
  const { records: rows, amounts, offsets } = GOLDEN.nested;
  const records = rows.map(row => ({ partId: row.partId, mesh: true, partBounds: { min: row.min, max: row.max } }));
  const hierarchy = new Map(rows.map(row => [row.partId, row.path]));
  const layout = computeExplodedViewLayout(records, null, { hierarchy });
  assert.equal(layout.levelCount, 3, "three levels move; a fourth moves with its level-three ancestor");
  for (const amount of amounts) {
    applyExplodedViewProgress(THREE, layout, amount);
    for (const record of records) {
      const matrix = record.explodedViewMatrix;
      const found = matrix ? [matrix.elements[12], matrix.elements[13], matrix.elements[14]] : [0, 0, 0];
      near(found, offsets[amount][record.partId], `nested at ${amount}, ${record.partId}`);
    }
  }
});
