// Measure on an engine document: main's `measureEntities` tests (what a pair of entities reads)
// taken on core's bracket (`__fixtures__/bracket`: a 40 x 20 x 4 plate on z = -2..2 with its
// vertical corners filleted at R2 and a Ø8 hole at the origin, and two Ø6 pegs of one part, 12
// tall, standing at x = ±12), as Measure picks its faces, edges and vertices off the xbf scene.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import * as THREE from "three";

import { measureLabelText, measurementMark } from "../viewer/measureDimension.js";
import { measureEntityPair, pickEntityKey } from "../viewer/measureEntities.js";
import { measurementFromPicks } from "../viewer/measurement.js";
import { loadXbfDocument } from "./xbfDocument.js";
import { xbfFaceSurface } from "./xbfEntities.js";
import { xbfMeasureEntity, xbfMeasureVertex } from "./xbfMeasure.js";
import { createXbfScene } from "./xbfScene.js";

const FIXTURES = path.join(path.dirname(fileURLToPath(import.meta.url)), "__fixtures__");
const read = file => fs.readFileSync(path.join(FIXTURES, file));
const STRUCTURE = JSON.parse(read("bracket/structure.json"));
const [PLATE, PEG] = STRUCTURE.prototypes;

// The look's environment image: 1 x 1, radiance 1 (RGBE 255, 255, 255, e 128), as `xbf.test.js` serves it.
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode("#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n"), 255, 255, 255, 128]).buffer;

/** The bracket's scene, read from an engine that answers the fixture. */
async function bracket() {
  const fetch = async (url) => {
    if (url.endsWith("/api/look")) return new Response(read("look.json"));
    if (url.endsWith("/api/look/environment")) return new Response(ENVIRONMENT);
    const part = /\/part\/([^/]+)$/.exec(url);
    return new Response(part ? read(`bracket/${part[1]}.xbm`) : JSON.stringify(STRUCTURE));
  };
  const document = await loadXbfDocument("http://127.0.0.1:9/api/doc/bracket", { fetch });
  return createXbfScene(THREE, document);
}

// The plate's faces and edges by ordinal (`instance 0`), and each peg's (instances 1 and 2).
const TOP = "i0/face/2", BOTTOM = "i0/face/5", LEFT = "i0/face/1", RIGHT = "i0/face/10", HOLE = "i0/face/11";
const FRONT = "i0/edge/7", BACK = "i0/edge/8", LEFT_TOP = "i0/edge/1", RIM = "i0/edge/12";
const face = (scene, id, point) => xbfMeasureEntity(scene, { id, kind: "face", point });
const edge = (scene, id, point) => xbfMeasureEntity(scene, { id, kind: "edge", point });
const near = (actual, expected, what = "") => assert.ok(Math.abs(actual - expected) < 1e-4, `${what} ${actual} is not ${expected}`);
const nearPoint = (actual, expected, what = "") => expected.forEach((value, axis) => near(actual[axis], value, `${what}[${axis}]`));

test("a face's surface is read off its mesh: the plate's flats, its fillets, the hole and the pegs' walls", async () => {
  const scene = await bracket();
  const mesh = key => scene.document.parts.get(key).mesh;
  const kinds = Object.keys(PLATE.faceNames).map(ordinal => xbfFaceSurface(mesh(PLATE.key), Number(ordinal)).type);
  assert.deepEqual(kinds, ["plane", "plane", "cylinder", "cylinder", "plane", "plane", "plane", "cylinder", "cylinder", "plane", "cylinder"]);
  const hole = xbfFaceSurface(mesh(PLATE.key), 11);
  near(hole.radius, 4, "the hole's radius");
  nearPoint(hole.origin, [0, 0, 0], "on its axis");
  near(Math.abs(hole.axis[2]), 1, "along z");
  near(xbfFaceSurface(mesh(PLATE.key), 3).radius, 2, "a fillet's radius");
  assert.deepEqual(Object.keys(PEG.faceNames).map(ordinal => xbfFaceSurface(mesh(PEG.key), Number(ordinal)).type), ["cylinder", "plane", "plane"]);
  // Placed: the second peg's wall where its instance stands, its top's normal turned with it.
  const wall = scene.elementGeometry("i2/face/1").surface;
  nearPoint(wall.origin, [-12, 0, 8], "the second peg's axis");
  near(wall.radius, 3, "its radius");
  nearPoint(scene.elementGeometry("i2/vertex/1").point, [-9, 0, 14], "the second peg's top vertex");
  assert.equal(scene.elementGeometry("i0/face/99"), null);
  assert.ok(scene.elementGeometry(TOP, { points: true }).points.length > 4, "a face's nodes where asked for");
  scene.dispose();
});

test("a sphere is round about one centre; a cone and a torus are surfaces a reading does not take", () => {
  // Rings of nodes about the z axis, each node with its surface's normal: a patch of a sphere and of a cone.
  const patch = (place) => {
    const points = [], normals = [];
    for (let ring = 1; ring <= 4; ring += 1) {
      for (let step = 0; step < 8; step += 1) {
        const [point, normal] = place(ring * 0.2, (step / 8) * Math.PI * 2);
        points.push(point); normals.push(normal);
      }
    }
    const indices = [];
    for (let at = 0; at + 2 < points.length; at += 1) indices.push(at, at + 1, at + 2);
    return { positions: Float32Array.from(points.flat()), normals: Float32Array.from(normals.flat()), indices: Uint32Array.from(indices),
      faces: Uint32Array.from([1, 0, indices.length]) };
  };
  const sphere = patch((polar, around) => {
    const normal = [Math.sin(polar) * Math.cos(around), Math.sin(polar) * Math.sin(around), Math.cos(polar)];
    return [[5 + 10 * normal[0], 10 * normal[1], -3 + 10 * normal[2]], normal];
  });
  const round = xbfFaceSurface(sphere, 1);
  assert.equal(round.type, "sphere");
  near(round.radius, 10, "its radius");
  nearPoint(round.center, [5, 0, -3], "its centre");
  const cone = patch((height, around) => {
    const radius = 2 + height;
    const normal = [Math.cos(around) / Math.SQRT2, Math.sin(around) / Math.SQRT2, -1 / Math.SQRT2];
    return [[radius * Math.cos(around), radius * Math.sin(around), height], normal];
  });
  assert.deepEqual(xbfFaceSurface(cone, 1), { type: "surface" });
});

test("what two entities measure follows from the pair, not from where on each the pointer was", async () => {
  const scene = await bracket();
  const thickness = measureEntityPair(face(scene, TOP, [15, 5, 2]), face(scene, BOTTOM, [-5, -5, -2]));
  assert.equal(thickness.kind, "normal");
  near(thickness.distance, 4, "the plate's thickness");
  nearPoint(thickness.end, [15, 5, -2], "drawn square to the faces, from the first pick");
  const wide = measureEntityPair(face(scene, LEFT, [-20, 3, 1]), face(scene, RIGHT, [20, -6, -1]));
  assert.equal(wide.kind, "normal");
  near(wide.distance, 40, "the plate's length");
  const square = measureEntityPair(face(scene, TOP, [5, 5, 2]), face(scene, LEFT, [-20, 0, 0]));
  assert.deepEqual([square.kind, Math.round(square.angleDeg * 1e6) / 1e6], ["angle", 90]);
  const vertices = measureEntityPair(xbfMeasureVertex(scene, "i0/vertex/1"), xbfMeasureVertex(scene, "i0/vertex/17"));
  assert.equal(vertices.kind, "distance");
  near(vertices.distance, Math.hypot(40, 16, 4), "corner to corner");
  near(measureEntityPair(xbfMeasureVertex(scene, "i0/vertex/1"), face(scene, BOTTOM, [0, 5, -2])).distance, 4, "a vertex to a face");
  scene.dispose();
});

test("holes and pegs are measured by their centres and axes, as a CAD tool locates them", async () => {
  const scene = await bracket();
  const spacing = measureEntityPair(face(scene, "i1/face/1", [15, 0, 8]), face(scene, "i2/face/1", [-9, 0, 8]));
  assert.equal(spacing.kind, "centers");
  near(spacing.distance, 24, "the two pegs, instances of one part, where each stands");
  near(measureEntityPair(face(scene, HOLE, [4, 0, 0]), face(scene, "i1/face/1", [15, 0, 8])).distance, 12, "the hole to a peg");
  const fromSide = measureEntityPair(face(scene, HOLE, [0, 4, 1]), face(scene, LEFT, [-20, 0, 0]));
  assert.deepEqual([fromSide.kind, Math.round(fromSide.distance * 1e6) / 1e6], ["normal", 20], "the hole's axis from the side face, not its wall");
  const rims = measureEntityPair(edge(scene, RIM, [4, 0, 2]), edge(scene, "i1/edge/1", [15, 0, 14]));
  assert.equal(rims.kind, "centers");
  near(rims.distance, Math.hypot(12, 12), "the hole's rim to a peg's top rim, centre to centre");
  nearPoint(rims.start, [0, 0, 2], "from the rim's centre");
  near(measureEntityPair(xbfMeasureVertex(scene, "i0/vertex/1"), edge(scene, RIM, [4, 0, 2])).distance, Math.hypot(20, 8), "a vertex to a rim's centre");
  near(measureEntityPair(xbfMeasureVertex(scene, "i0/vertex/1"), face(scene, HOLE, [4, 0, 0])).distance, Math.hypot(20, 8), "a vertex to a hole's axis");
  near(measureEntityPair(edge(scene, RIM, [4, 0, 2]), edge(scene, FRONT, [0, -10, 2])).distance, 10, "a rim's centre to a straight edge");
  scene.dispose();
});

test("straight edges read as an angle, or square across when parallel", async () => {
  const scene = await bracket();
  const across = measureEntityPair(edge(scene, FRONT, [3, -10, 2]), edge(scene, BACK, [-7, 10, 2]));
  assert.deepEqual([across.kind, across.distance], ["normal", 20]);
  const turned = measureEntityPair(edge(scene, FRONT, [3, -10, 2]), edge(scene, LEFT_TOP, [-20, 0, 2]));
  assert.deepEqual([turned.kind, turned.angleDeg], ["angle", 90]);
  near(measureEntityPair(edge(scene, BACK, [0, 10, 2]), face(scene, BOTTOM, [0, 0, -2])).distance, 4, "an edge to a face it runs along");
  // A straight edge's length is its polyline's; an arc's is the kernel's, where the engine's facts are in.
  assert.equal(edge(scene, FRONT, [0, -10, 2]).reference.pickData.length, 36);
  assert.equal(edge(scene, RIM, [4, 0, 2]).reference.pickData.length, undefined, "no length guessed off the chords");
  const facts = { curve: "circle", length: 8 * Math.PI, radius: 4 };
  assert.deepEqual(xbfMeasureEntity(scene, { id: RIM, kind: "edge", point: [4, 0, 2] }, { facts }).reference.pickData,
    { selectorType: "edge", params: { radius: 4 }, length: 8 * Math.PI });
  scene.dispose();
});

test("a pair with no gap between it reads as the two points picked, never a 0.00 mm reading", async () => {
  const scene = await bracket();
  assert.equal(measureEntityPair(edge(scene, FRONT, [0, -10, 2]), face(scene, TOP, [5, 5, 2])), null, "an edge lying in the face");
  assert.equal(measureEntityPair(xbfMeasureVertex(scene, "i0/vertex/1"), face(scene, TOP, [5, 5, 2])), null, "a vertex on the face");
  assert.equal(measureEntityPair(face(scene, TOP, [5, 5, 2]), face(scene, TOP, [-5, 8, 2])), null, "one face twice");
  assert.equal(measureEntityPair(face(scene, "i1/face/2", [12, 1, 14]), face(scene, "i2/face/2", [-12, 1, 14])), null, "two flats at one height");
  const along = measurementFromPicks(face(scene, TOP, [10, 5, 2]), face(scene, TOP, [13, 9, 2]));
  assert.deepEqual([along.kind, along.euclidean, measureLabelText(along)], ["points", 5, "5.00 mm"]);
  scene.dispose();
});

test("a reading is labelled by what it is, and drawn where its instance stands, Explode included", async () => {
  const scene = await bracket();
  assert.equal(measureLabelText(measurementFromPicks(face(scene, TOP, [5, 5, 2]), face(scene, BOTTOM, [5, 5, -2]))), "⟂ 4.00 mm");
  assert.equal(measureLabelText(measurementFromPicks(face(scene, "i1/face/1", [15, 0, 8]), face(scene, "i2/face/1", [-9, 0, 8]))), "C-C 24.00 mm");
  assert.equal(measureLabelText(measurementFromPicks(face(scene, TOP, [5, 5, 2]), face(scene, RIGHT, [20, 0, 0]))), "∠ 90.0°");
  // Taken, it is one mark -- what `cadgen snapshot --measurements` draws, `{start, end, label, color}` --
  // between the ends its dimension is drawn between: square across the plate, not between the points pressed.
  const [pickA, pickB] = [face(scene, TOP, [15, 5, 2]), face(scene, BOTTOM, [-5, -5, -2])];
  const mark = measurementMark({ pickA, pickB, measurement: measurementFromPicks(pickA, pickB), colorIndex: 0 });
  assert.deepEqual(Object.keys(mark).sort(), ["color", "end", "label", "start"]);
  assert.deepEqual([mark.start, mark.end.map(value => Math.round(value * 1e6) / 1e6 + 0), mark.label], [[15, 5, 2], [15, 5, -2], "⟂ 4.00 mm"]);
  assert.match(mark.color, /^#[0-9a-f]{6}$/);
  // Exploded, each peg's wall is read where its instance went: centre to centre is where they stand now.
  assert.ok(scene.setExplode(1));
  const middle = id => { const box = scene.selectionBounds([id]); return [0, 1].map(axis => (box.min[axis] + box.max[axis]) / 2); };
  const [one, two] = [middle("i1"), middle("i2")];
  const apart = measureEntityPair(face(scene, "i1/face/1", [one[0] + 3, one[1], 8]), face(scene, "i2/face/1", [two[0] + 3, two[1], 8]));
  assert.equal(apart.kind, "centers");
  near(apart.distance, Math.hypot(one[0] - two[0], one[1] - two[1]), "between the pegs' axes as they stand");
  scene.dispose();
});

test("an entity's key tells a second press on what is held from a press on something else", async () => {
  const scene = await bracket();
  assert.equal(pickEntityKey(face(scene, TOP, [1, 2, 2])), pickEntityKey(face(scene, TOP, [-9, 5, 2])), "a face, wherever on it");
  assert.notEqual(pickEntityKey(face(scene, "i1/face/2", [12, 0, 14])), pickEntityKey(face(scene, "i2/face/2", [-12, 0, 14])),
    "one face of one part in two instances is two faces");
  assert.notEqual(pickEntityKey(xbfMeasureVertex(scene, "i0/vertex/1")), pickEntityKey(xbfMeasureVertex(scene, "i0/vertex/2")),
    "two ends of one edge are two vertices");
  assert.equal(xbfMeasureEntity(scene, { id: "i0/face/99", kind: "face", point: [0, 0, 0] }), null, "no such face");
  scene.dispose();
});
