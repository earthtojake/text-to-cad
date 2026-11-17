import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { createXbfConcepts, xbfConceptKey, xbfStructureConcepts } from "./xbfConcepts.js";

// A field as the engine answers one, with one ranged name and nothing to march: enough to build.
const payload = (region = [-20, -20, -4, 20, 20, 0]) => ({
  schema: 1, target: "glsl-es300", code: "", entry: { march: "gsl_march" }, region, uniformBlock: "Field",
  uniforms: [{ name: "time", type: "f32", offset: 0, value: [0] }],
  sliders: [{ name: "t", uniform: "u_t", type: "f32", offset: 4, value: 4, min: 2, max: 8 }], bodies: [{ index: 1, name: "slab" }]
});
const SLAB = { gsl: "/work/slab.gsl", role: "body", digest: "aa" };
const BLOCK = { gsl: "/work/block.gsl", role: "baked", digest: "bb" };

// The scene's instances as `createXbfScene` holds them: a carrier Explode moves, the placed group under it.
function instances(...concepts) {
  return concepts.map((concept, index) => {
    const carrier = new THREE.Group();
    const group = new THREE.Group();
    group.matrixAutoUpdate = false;
    group.matrix.makeTranslation(0, 0, 10 * index);
    carrier.add(group);
    return { index, prototype: { name: `part${index}`, key: `k${index}`, ...(concept ? { concept } : {}) },
      instance: { path: `device/part${index}` }, group, carrier };
  });
}
const fields = (...concepts) => new Map(concepts.map(concept => [xbfConceptKey(concept), { payload: payload(), textures: {} }]));

test("a structure's concepts are named once each, by file and digest", () => {
  const structure = { prototypes: [{ name: "a" }, { name: "b", concept: SLAB }, { name: "c", concept: { ...SLAB, values: { t: 6 } } },
    { name: "d", concept: BLOCK }] };
  assert.deepEqual(xbfStructureConcepts(structure).map(concept => concept.gsl), ["/work/slab.gsl", "/work/block.gsl"]);
  assert.notEqual(xbfConceptKey(SLAB), xbfConceptKey({ ...SLAB, digest: "cc" }));
});

test("a concept is drawn beside its instance's placed group, where the group stands", () => {
  const held = instances(null, SLAB);
  const concepts = createXbfConcepts(THREE, { fields: fields(SLAB) }, held);
  assert.equal(concepts.any, true);
  assert.deepEqual(concepts.list().map(({ index, name, role, representation }) => [index, name, role, representation]),
    [[1, "part1", "body", "concept"]]);
  const holder = held[1].carrier.children.find(child => child !== held[1].group);
  assert.equal(holder.name, "device/part1 concept");
  assert.deepEqual(holder.matrix.elements.slice(12, 15), [0, 0, 10]);
  // A pose moves the group, and the concept with it.
  held[1].group.matrix.makeTranslation(5, 0, 0);
  concepts.pose();
  assert.deepEqual(holder.matrix.elements.slice(12, 15), [5, 0, 0]);
  // Its box is the field's region where it stands: what the camera frames of a part with no triangles.
  const box = concepts.box(1);
  assert.deepEqual([box.min.toArray(), box.max.toArray()], [[-15, -20, -4], [25, 20, 0]]);
  assert.equal(concepts.box(0), null);
  concepts.dispose();
  assert.equal(held[1].carrier.children.length, 1);
});

test("a baked part opens as its exact body and is shown as its concept or both on request", () => {
  const held = instances(BLOCK);
  const concepts = createXbfConcepts(THREE, { fields: fields(BLOCK) }, held);
  const holder = held[0].carrier.children.find(child => child !== held[0].group);
  assert.deepEqual([concepts.representation(0), holder.visible, concepts.exactShown(0)], ["exact", false, true]);
  assert.equal(concepts.setRepresentation(0, "concept"), true);
  assert.deepEqual([holder.visible, concepts.exactShown(0)], [true, false]);
  assert.equal(concepts.setRepresentation(0, "both"), true);
  assert.deepEqual([holder.visible, concepts.exactShown(0)], [true, true]);
  assert.equal(concepts.setRepresentation(0, "both"), false);
  assert.equal(concepts.setRepresentation(0, "sketch"), false);
  // Hidden, or dimmed by an isolation, it is not drawn whichever way it is shown.
  concepts.show(0, false);
  assert.equal(holder.visible, false);
  concepts.show(0, true);
  assert.equal(holder.visible, true);
  // A baked part's box is its exact body's: the concept adds none.
  assert.equal(concepts.box(0), null);
});

test("a part that is its concept has no other way to be shown", () => {
  const concepts = createXbfConcepts(THREE, { fields: fields(SLAB) }, instances(SLAB));
  assert.equal(concepts.setRepresentation(0, "exact"), false);
  assert.equal(concepts.exactShown(0), true);
});

test("the values a part gives its concept are set where it is drawn, a ranged name only", () => {
  const given = createXbfConcepts(THREE, { fields: fields(SLAB) }, instances({ ...SLAB, values: { t: 6 } }));
  assert.equal(given.parameterValue(0, "t"), 6);
  assert.equal(given.setParameter(0, "t", 100), true);
  assert.equal(given.parameterValue(0, "t"), 8);
  assert.equal(given.setParameter(0, "width", 3), false);
  assert.throws(() => createXbfConcepts(THREE, { fields: fields(SLAB) }, instances({ ...SLAB, values: { width: 3 } })),
    /part0 gives \/work\/slab\.gsl the value width=3, and the concept has no ranged name width/);
});

test("a part that is its concept is not drawn without its field; a baked part is, as its exact body", () => {
  assert.throws(() => createXbfConcepts(THREE, { fields: new Map() }, instances(SLAB)),
    /part0 is the concept \/work\/slab\.gsl, and its field was not read/);
  const baked = createXbfConcepts(THREE, {}, instances(BLOCK));
  assert.equal(baked.any, false);
  assert.equal(baked.exactShown(0), true);
});

test("a lit concept wears the selection's colour, and its own again after", () => {
  const held = instances(SLAB);
  const concepts = createXbfConcepts(THREE, { fields: fields(SLAB) }, held);
  const surface = held[0].carrier.children.find(child => child !== held[0].group).children[0].children[0].material.uniforms.uSurface.value;
  const own = surface.map(colour => colour.toArray());
  concepts.ink(new Set(), new Set([0]));
  assert.notDeepEqual(surface.map(colour => colour.toArray()), own);
  concepts.ink(new Set(), new Set());
  assert.deepEqual(surface.map(colour => colour.toArray()), own);
});

test("a pick answers nothing before the scene was drawn: no renderer to march with", () => {
  const concepts = createXbfConcepts(THREE, { fields: fields(SLAB) }, instances(SLAB));
  assert.equal(concepts.hit(new THREE.Ray(new THREE.Vector3(0, 0, 50), new THREE.Vector3(0, 0, -1))), null);
});

test("the concepts' clock and a section reach every concept's field", () => {
  const timedFields = new Map([[xbfConceptKey(SLAB), { payload: { ...payload(), timed: true }, textures: {} }]]);
  const held = instances(SLAB);
  const concepts = createXbfConcepts(THREE, { fields: timedFields }, held);
  assert.equal(concepts.timed, true);
  assert.equal(createXbfConcepts(THREE, { fields: fields(SLAB) }, instances(SLAB)).timed, false);
  const drawn = held[0].carrier.children.find(child => child !== held[0].group).children[0].children[0];
  assert.equal(concepts.setTime(2), true);
  assert.equal(drawn.material.uniformsGroups[0].uniforms[0].value, 2);
  assert.equal(concepts.setTime(2), false);
  concepts.setClipPlanes([new THREE.Plane(new THREE.Vector3(1, 0, 0), 0)]);
  drawn.onBeforeRender({ getCurrentViewport: target => target.set(0, 0, 10, 10) }, null, new THREE.PerspectiveCamera());
  assert.equal(drawn.material.uniforms.uClipCount.value, 1);
  assert.deepEqual(concepts.list()[0].file, "slab.gsl");
});

test("the concepts wear the scene's look: its fill where a body has no colour, its finish, its opacity", () => {
  const held = instances(SLAB, { ...BLOCK });
  held[1].instance.color = [0.5, 0.25, 1, 1];
  const concepts = createXbfConcepts(THREE, { fields: fields(SLAB, BLOCK) }, held);
  const drawn = at => held[at].carrier.children.find(child => child !== held[at].group).children[0].children[0];
  const built = drawn(0).material.uniforms.uSurface.value.map(colour => colour.toArray());
  assert.equal(drawn(0).material.isMeshPhysicalMaterial, true);
  concepts.look({ authored: false, colorPower: 2, surface: { style: "shaded", opacity: 0.3 },
    materialSettings: { defaultColor: "#808080", roughness: 0.6, metalness: 0, envMapIntensity: 1, emissiveIntensity: 0 } });
  // No colour of its own: the look's fill, raised to its power. Its other bodies: the field's, raised too.
  const fill = new THREE.Color("#808080");
  const worn = drawn(0).material.uniforms.uSurface.value;
  assert.deepEqual(worn[1].toArray().map(value => value.toFixed(5)), [fill.r ** 2, fill.g ** 2, fill.b ** 2].map(value => value.toFixed(5)));
  assert.deepEqual(worn[2].toArray().map(value => value.toFixed(5)), built[2].map(value => (value ** 2).toFixed(5)));
  // The part's own colour is its first body's.
  assert.deepEqual(drawn(1).material.uniforms.uSurface.value[1].toArray(), [0.25, 0.0625, 1]);
  assert.deepEqual([drawn(0).material.roughness, drawn(0).material.opacity, drawn(0).material.transparent, drawn(0).material.depthWrite],
    [0.6, 0.3, true, false]);
  // A selection is worn over the look, and the look's colour again after.
  concepts.ink(new Set(), new Set([0]));
  assert.notDeepEqual(worn[1].toArray().map(value => value.toFixed(5)), [fill.r ** 2, fill.g ** 2, fill.b ** 2].map(value => value.toFixed(5)));
  concepts.ink(new Set(), new Set());
  assert.deepEqual(worn[1].toArray().map(value => value.toFixed(5)), [fill.r ** 2, fill.g ** 2, fill.b ** 2].map(value => value.toFixed(5)));
  // No look: as built.
  concepts.look(null);
  assert.deepEqual(worn.map(colour => colour.toArray()), built);
  assert.deepEqual([drawn(0).material.opacity, drawn(0).material.transparent], [1, false]);
});
