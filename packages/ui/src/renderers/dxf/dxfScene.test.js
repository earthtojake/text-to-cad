import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { parseDxf } from "@hardcore/core/lib/dxf/parseDxf.js";

import { isKitScene, sceneFramingBounds } from "../kit/scene.js";
import { createDxfScene } from "./dxfScene.js";

// Inline DXF text. The models corpus has no document, no text and no coloured layer, so the
// only fixtures that exercise those paths are the ones written here.
const dxf = lines => parseDxf(`${lines.join("\n")}\n`, { fileRef: "test/fixture.dxf" });
const rect = (layer, [x, y], [w, h]) => [
  "0", "LWPOLYLINE", "8", layer, "90", "4", "70", "1",
  "10", `${x}`, "20", `${y}`, "10", `${x + w}`, "20", `${y}`,
  "10", `${x + w}`, "20", `${y + h}`, "10", `${x}`, "20", `${y + h}`
];
const line = (layer, [x1, y1], [x2, y2]) => ["0", "LINE", "8", layer, "10", `${x1}`, "20", `${y1}`, "11", `${x2}`, "21", `${y2}`];
const entities = body => dxf(["0", "SECTION", "2", "ENTITIES", ...body, "0", "ENDSEC", "0", "EOF"]);

/** A plain cut layout: one closed rectangle with a hole. */
const PLATE = () => entities([...rect("CUT", [0, 0], [40, 20]), "0", "CIRCLE", "8", "CUT", "10", "20", "20", "10", "40", "3"]);
/** A layout with two creases, a score line and a label. */
const PANEL = () => entities([
  ...rect("CUT", [0, 0], [60, 20]),
  ...line("BEND", [20, 0], [20, 20]),
  ...line("BEND", [40, 0], [40, 20]),
  ...line("ENGRAVE", [5, 10], [15, 10]),
  "0", "TEXT", "8", "ENGRAVE", "10", "5", "20", "4", "40", "3", "1", "PART A"
]);
/** A dimensioned drawing: line-work and a DIMENSION, so no flat pattern exists. */
const SHEET = () => entities([
  ...line("OUTLINE", [0, 0], [50, 0]), ...line("OUTLINE", [50, 0], [50, 30]),
  ...line("OUTLINE", [50, 30], [0, 30]), ...line("OUTLINE", [0, 30], [0, 0]),
  ...line("DIMS", [0, -5], [50, -5]),
  "0", "DIMENSION", "8", "DIMS", "10", "0", "20", "-5", "11", "25", "21", "-8"
]);
/** A cut layer that never closes: no contour to extrude. */
const OPEN = () => entities([...line("CUT", [0, 0], [30, 0]), ...line("CUT", [30, 0], [30, 15])]);

const SETTINGS = Object.freeze({
  thicknessMm: 1, bends: [], bendStyle: "curved", bendRadiusMm: 0, kFactor: 0.5,
  hiddenLayers: [], orientation: { x: 0, y: 0, z: 0 }, tintHex: null
});
const settings = patch => ({ ...SETTINGS, ...patch });
const bends = (count, angleDeg, direction = "up") => Array.from({ length: count }, () => ({ angleDeg, direction }));
// The scene holds ONE presentation group; its parts are that group's children.
const child = (scene, name) => {
  let found = null;
  scene.object3D.traverse(item => { if (item.name === name) found = item; });
  return found;
};
const presentationName = scene => scene.object3D.children.map(item => item.name);
const positions = scene => child(scene, "dxf-sheet").geometry.getAttribute("position").array;
const extent = (array, axis) => {
  let min = Infinity; let max = -Infinity;
  for (let index = axis; index < array.length; index += 3) {
    if (array[index] < min) min = array[index];
    if (array[index] > max) max = array[index];
  }
  return max - min;
};

const INSPECT = Object.freeze({
  defaultColor: "#b6c4ce", fillColors: ["#b6c4ce", "#f4a7a7", "#f8c77e"], cycleColors: false, overrideSourceColors: false,
  tintStrength: 0, roughness: 0.58, metalness: 0.02, clearcoat: 0.12, clearcoatRoughness: 0.42, envMapIntensity: 0.42, emissiveIntensity: 0.02
});
const STUDIO = Object.freeze({ ...INSPECT, roughness: 0.34, metalness: 0, clearcoat: 0.3, emissiveIntensity: 0 });
const look = (patch = {}) => ({ materialSettings: { ...INSPECT, ...patch.materialSettings }, authored: patch.authored === true,
  surface: { style: "shaded", opacity: 1, ...patch.surface } });

test("a cut layout is one sheet under the kit's contract; nothing is drawn until it is posed", () => {
  const scene = createDxfScene(THREE, PLATE());
  assert.equal(isKitScene(scene), true);
  assert.equal(scene.presentation, "layout");
  assert.equal(scene.meshFailure, null);
  assert.deepEqual(presentationName(scene), ["dxf-layout"]);
  assert.deepEqual(scene.object3D.children[0].children.map(item => item.name), ["dxf-sheet", "dxf-texts"]);
  assert.equal(child(scene, "dxf-sheet").castShadow, true);
  assert.equal(child(scene, "dxf-sheet").material.userData.cadSourceColor, false, "nothing in a DXF says what colour the stock is");
  // The 1 mm reference prism: the box the camera frames and 100% zoom means.
  const framing = sceneFramingBounds(scene);
  assert.deepEqual([framing.min[0], framing.min[1], framing.max[0], framing.max[1]].map(Math.round), [0, 0, 40, 20]);
  assert.equal(Math.round((framing.max[2] - framing.min[2]) * 100) / 100, 1);
  assert.equal(scene.bounds, scene.restBounds);
  scene.dispose();
});

test("a dimensioned drawing is line-work per layer and no mesh at all", () => {
  const scene = createDxfScene(THREE, SHEET());
  assert.equal(scene.presentation, "document");
  assert.deepEqual(presentationName(scene), ["dxf-lines"]);
  const lines = child(scene, "dxf-lines");
  assert.deepEqual(lines.children.map(item => item.userData.dxfDrawingLayer).sort(), ["DIMS", "OUTLINE"]);
  assert.ok(lines.children.every(item => item.isLineSegments));
  // Its own extent stands in for the mesh the camera would otherwise frame.
  const framing = sceneFramingBounds(scene);
  assert.deepEqual([framing.min[0], framing.max[0]].map(Math.round), [0, 50]);

  // Hiding a layer hides its object; nothing is rebuilt.
  const outline = lines.children.find(item => item.userData.dxfDrawingLayer === "OUTLINE");
  scene.update(settings({ hiddenLayers: ["OUTLINE"] }));
  assert.equal(outline.visible, false);
  scene.update(settings({}));
  assert.equal(outline.visible, true);
  assert.equal(lines.children.find(item => item.userData.dxfDrawingLayer === "OUTLINE"), outline, "the same object, not a replacement");
  scene.dispose();
});

test("a cut layer that never closes falls back to its line-work and says why", () => {
  const scene = createDxfScene(THREE, OPEN());
  assert.equal(scene.presentation, "document", "a layout by profile, but with nothing to extrude, is shown as its lines");
  assert.ok(scene.meshFailure instanceof Error);
  assert.equal(child(scene, "dxf-sheet"), null);
  assert.ok(child(scene, "dxf-lines").children.length > 0);
  assert.doesNotThrow(() => scene.update(settings({ thicknessMm: 6, bends: bends(1, 90) })));
  scene.dispose();
});

test("thickness scales the cached prism; 0 mm is flat-thin, never nothing", () => {
  const scene = createDxfScene(THREE, PLATE());
  scene.update(settings({ thicknessMm: 6 }));
  assert.equal(Math.round(extent(positions(scene), 2) * 1000) / 1000, 6);
  scene.update(settings({ thicknessMm: 0 }));
  assert.equal(Math.round(extent(positions(scene), 2) * 1e6) / 1e6, 0.001);
  // Framing never follows the pose: the flat box is what 100% means.
  assert.equal(Math.round((scene.restBounds.max[2] - scene.restBounds.min[2]) * 100) / 100, 1);
  scene.dispose();
});

test("a boxed fold moves the far strip and unfolding restores the flat baseline exactly", () => {
  const scene = createDxfScene(THREE, PANEL());
  assert.equal(scene.bendLines.length, 2);
  scene.update(settings({ thicknessMm: 1 }));
  const flat = Float32Array.from(positions(scene));
  scene.update(settings({ thicknessMm: 1, bendStyle: "boxed", bends: [{ angleDeg: 90, direction: "up" }, { angleDeg: 0, direction: "up" }] }));
  const folded = positions(scene);
  assert.equal(folded, positions(scene), "the same buffer, rewritten in place");
  assert.ok(extent(folded, 2) > 5, `a 90° fold stands part of the sheet up: ${extent(folded, 2)}`);
  scene.update(settings({ thicknessMm: 1, bendStyle: "boxed", bends: bends(2, 0) }));
  assert.deepEqual([...positions(scene)], [...flat], "flat again, bit for bit");
  scene.dispose();
});

test("a curved fold swaps in a meshed geometry and never leaves a stale normal buffer", () => {
  const scene = createDxfScene(THREE, PANEL());
  const sheet = child(scene, "dxf-sheet");
  scene.update(settings({ thicknessMm: 2 }));
  const flatGeometry = sheet.geometry;
  scene.update(settings({ thicknessMm: 2, bends: [{ angleDeg: 90, direction: "up" }, { angleDeg: 0, direction: "up" }] }));
  const curved = sheet.geometry;
  assert.notEqual(curved, flatGeometry, "a curved bend is a fresh mesh, not a transform of the prism");
  assert.ok(curved.getIndex(), "and an indexed one");
  const firstCount = curved.getAttribute("position").count;
  // Each bend's band adds vertices. A normal attribute kept from the previous build is at
  // the wrong count, and the draw is rejected outright and silently.
  scene.update(settings({ thicknessMm: 2, bends: bends(2, 90) }));
  assert.equal(sheet.geometry, curved, "the geometry object is reused");
  assert.notEqual(curved.getAttribute("position").count, firstCount);
  assert.equal(curved.getAttribute("normal").count, curved.getAttribute("position").count);
  // Leaving Curved puts the prism back.
  scene.update(settings({ thicknessMm: 2, bendStyle: "boxed", bends: bends(2, 90) }));
  assert.equal(sheet.geometry, flatGeometry);
  scene.dispose();
});

test("a fold the mesher cannot band falls back to the sharp fold rather than rendering nothing", () => {
  // A hole straddling the crease is exactly what the bend mesher refuses.
  const straddled = entities([
    ...rect("CUT", [0, 0], [40, 20]),
    "0", "CIRCLE", "8", "CUT", "10", "20", "20", "10", "40", "6",
    ...line("BEND", [20, 0], [20, 20])
  ]);
  const scene = createDxfScene(THREE, straddled);
  const sheet = child(scene, "dxf-sheet");
  scene.update(settings({ thicknessMm: 2 }));
  const flatGeometry = sheet.geometry;
  scene.update(settings({ thicknessMm: 2, bends: bends(1, 90) }));
  assert.equal(sheet.geometry, flatGeometry, "the prism, folded sharply");
  assert.ok(extent(sheet.geometry.getAttribute("position").array, 2) > 5, "and it really is folded");
  scene.dispose();
});

test("hiding a layer takes its marks with it: creases with BEND, scores with ENGRAVE", () => {
  const scene = createDxfScene(THREE, PANEL());
  scene.update(settings({ thicknessMm: 1, bends: bends(2, 30), bendStyle: "boxed" }));
  const guides = child(scene, "dxf-bend-guides");
  const scores = child(scene, "dxf-score-lines");
  assert.equal(guides.visible, true);
  assert.equal(guides.geometry.getAttribute("position").count, 4, "two creases, two segments");
  assert.equal(scores.visible, true);
  scene.update(settings({ thicknessMm: 1, bends: bends(2, 30), bendStyle: "boxed", hiddenLayers: ["BEND"] }));
  assert.equal(guides.visible, false, "the crease marks ARE that layer");
  scene.update(settings({ thicknessMm: 1, bends: bends(2, 30), bendStyle: "boxed", hiddenLayers: ["ENGRAVE"] }));
  assert.equal(scores.visible, false);
  assert.equal(guides.visible, true);
  scene.dispose();
});

test("hiding a cut layer re-meshes the solid from what is left of it", () => {
  // Two cut layers: the outline, and a window inside it. (Any layer whose name says nothing
  // else is a cut layer.)
  const windowed = entities([
    ...rect("CUT", [0, 0], [40, 20]),
    "0", "CIRCLE", "8", "WINDOW", "10", "20", "20", "10", "40", "4"
  ]);
  const scene = createDxfScene(THREE, windowed);
  const sheet = child(scene, "dxf-sheet");
  scene.update(settings({ thicknessMm: 2 }));
  const flatGeometry = sheet.geometry;
  const withWindow = flatGeometry.getAttribute("position").count;
  scene.update(settings({ thicknessMm: 2, hiddenLayers: ["WINDOW"] }));
  assert.notEqual(sheet.geometry, flatGeometry, "the baked prism has the hole welded in: only a re-mesh can fill it");
  assert.ok(sheet.geometry.getAttribute("position").count < withWindow, "a plate without its hole has fewer vertices");
  scene.update(settings({ thicknessMm: 2 }));
  assert.equal(sheet.geometry, flatGeometry, "and showing it again is the prism back");
  scene.dispose();
});

test("hiding the ONLY cut layer leaves the sheet as it was: there is nothing left to mesh", () => {
  const scene = createDxfScene(THREE, PANEL());
  const sheet = child(scene, "dxf-sheet");
  scene.update(settings({ thicknessMm: 2 }));
  const flatGeometry = sheet.geometry;
  scene.update(settings({ thicknessMm: 2, hiddenLayers: ["ENGRAVE"] }));
  assert.equal(sheet.geometry, flatGeometry, "an annotation layer never touches the solid");
  // The re-mesh raises ("requires one outer contour") and the prism stands. Today's
  // behaviour, kept deliberately: an empty viewport would be a worse answer than the part.
  scene.update(settings({ thicknessMm: 2, hiddenLayers: ["CUT"] }));
  assert.equal(sheet.geometry, flatGeometry);
  scene.dispose();
});

test("orientation turns the part about the flat pattern's own centre", () => {
  const scene = createDxfScene(THREE, PLATE());
  scene.update(settings({ thicknessMm: 1 }));
  const before = Float32Array.from(positions(scene));
  scene.update(settings({ thicknessMm: 1, orientation: { x: 0, y: 0, z: 1 } }));
  const after = positions(scene);
  // A quarter turn about Z swaps the footprint's width and height, around the same centre.
  assert.equal(Math.round(extent(after, 0)), Math.round(extent(before, 1)));
  assert.equal(Math.round(extent(after, 1)), Math.round(extent(before, 0)));
  assert.deepEqual(sceneFramingBounds(scene), scene.restBounds, "framing stays on the flat box");
  scene.dispose();
});

test("Render is a look, not a finish kept: the sheet never shows the white it was built with", () => {
  const scene = createDxfScene(THREE, PLATE());
  const sheet = child(scene, "dxf-sheet");
  const viewerSurface = new THREE.Color(INSPECT.defaultColor).getHexString();
  scene.setSurfaceLook(look());
  assert.equal(sheet.material.color.getHexString(), viewerSurface, "Solid: the viewer's surface colour");
  // A DXF authors no colour, so photographic Render must not "keep" one. Keeping it left the
  // sheet the bare white its material is constructed with, which reads as a different part.
  scene.setSurfaceLook(look({ authored: true, materialSettings: STUDIO }));
  assert.equal(sheet.material.color.getHexString(), viewerSurface, "Render: the same colour, under the studio");
  assert.notEqual(sheet.material.color.getHexString(), "ffffff");
  scene.dispose();
});

test("a material preset beats every colour mode, and letting it go gives the look back", () => {
  const scene = createDxfScene(THREE, PLATE());
  const sheet = child(scene, "dxf-sheet");
  scene.update(settings({ tintHex: "#c9a94f" }));
  scene.setSurfaceLook(look());
  assert.equal(sheet.material.color.getHexString(), new THREE.Color("#c9a94f").getHexString());
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, defaultColor: "#00c040", fillColors: ["#00c040"] } }));
  assert.equal(sheet.material.color.getHexString(), new THREE.Color("#c9a94f").getHexString(), "Single colour does not win over a chosen stock");
  scene.update(settings({ tintHex: null }));
  assert.equal(sheet.material.color.getHexString(), new THREE.Color("#00c040").getHexString());
  scene.dispose();
});

test("dispose releases what the scene made, once, and a late call changes nothing", () => {
  const scene = createDxfScene(THREE, PANEL());
  scene.update(settings({ thicknessMm: 2, bends: bends(2, 45), bendStyle: "boxed" }));
  const host = new THREE.Group();
  host.add(scene.object3D);
  const released = [];
  for (const name of ["dxf-sheet", "dxf-bend-guides", "dxf-score-lines"]) {
    const object = child(scene, name);
    object.geometry.dispose = () => released.push(`${name}:geometry`);
    object.material.dispose = () => released.push(`${name}:material`);
  }
  scene.dispose();
  scene.dispose();
  assert.equal(scene.object3D.parent, null);
  assert.deepEqual(released.sort(), [
    "dxf-bend-guides:geometry", "dxf-bend-guides:material",
    "dxf-score-lines:geometry", "dxf-score-lines:material",
    "dxf-sheet:geometry", "dxf-sheet:material"
  ]);
  assert.doesNotThrow(() => scene.setSurfaceLook(look()));
  assert.doesNotThrow(() => scene.update(settings({ thicknessMm: 3 })));
});
