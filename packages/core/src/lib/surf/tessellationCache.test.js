import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { Vector3 } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import {
  MESH_INDEX_SCHEMA,
  MESH_PAYLOAD_VERSION,
  TESSELLATION_VERSION,
  createHttpTessellationCacheProvider,
  decodeComponentTessellation,
  decodeTessellationCacheBatch,
  encodeTessellationCacheBatch,
  float64Hex,
  isTessellationCacheProbeMissError,
  meshEdgePolylines,
  meshFaceRanges,
  resolvedTessellationIdentity,
  createTessellationCache,
  surfIndexFromCacheEntry,
  TESS_BATCH_MAX_BYTES,
  tessBatchMaxBytes,
  tessellationCacheKey,
  tessellationQuality,
  tessellationPayloadFacts,
  validateTessellationProbeRow,
} from "./tessellationCache.js";
import { buildMeshDataFromSurf } from "./surfMeshData.js";
import { encodeMeshFixture, memoryMeshProvider, meshFixture, probeRowFor } from "./__tests__/meshFixtures.js";
import { buildComposedPackageMeshData } from "../assembly/meshData.js";

let tessellationCache = createTessellationCache();
function setTessellationCacheProvider(provider) {
  tessellationCache.dispose();
  tessellationCache = createTessellationCache({ provider });
}

const D = "11".repeat(32);
const D2 = "22".repeat(32);
const O = "aa".repeat(32);
const O2 = "bb".repeat(32);
const Q = Object.freeze({ chordTolerance: 0.0015, angleTolerance: 0.005 });

function componentFixture() {
  return {
    positions: new Float32Array([0, 0, 0, 2, 0, 0, 0, 3, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]),
    faceRanges: [{ ord: 7, color: [0.2, 0.4, 0.6, 1], indexStart: 0, indexCount: 3 }],
    edges: [{
      ord: 9,
      visibilityClass: "boundary",
      polyline: new Float32Array([0, 0, 0, 2, 0, 0]),
    }],
    bounds: { min: [0, 0, 0], max: [2, 3, 0] },
    scale: 3.605551275463989,
  };
}

function encodedEntry(overrides = {}) {
  return encodeMeshFixture(componentFixture(), {
    surfaceInput: D,
    surfaceObject: O,
    tessellation: Q,
    partColor: [0.6, 0.5, 0.4, 1],
    ...overrides,
  });
}

// The fixture triangle, decoded: what a render consumer holds.
function solidComponent() {
  return decodeComponentTessellation(encodedEntry()).component;
}

// The body with its JSON chunk rewritten by `mutate` and its BIN chunk kept.
function rewriteJson(bytes, mutate) {
  const source = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = source.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  mutate(gltf);
  const json = new TextEncoder().encode(JSON.stringify(gltf));
  const padded = (json.length + 3) & ~3;
  const bin = bytes.subarray(20 + jsonLength);
  const result = new Uint8Array(20 + padded + bin.length);
  const view = new DataView(result.buffer);
  view.setUint32(0, source.getUint32(0, true), true);
  view.setUint32(4, source.getUint32(4, true), true);
  view.setUint32(8, result.length, true);
  view.setUint32(12, padded, true);
  view.setUint32(16, source.getUint32(16, true), true);
  result.set(json, 20);
  result.fill(0x20, 20 + json.length, 20 + padded);
  result.set(bin, 20 + padded);
  return result;
}

// The body with one u32 of a named table (`cadgen.faces`, `cadgen.edges`) set to `value`.
function rewriteTable(bytes, name, word, value) {
  const result = bytes.slice();
  const view = new DataView(result.buffer);
  const jsonLength = view.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(result.subarray(20, 20 + jsonLength)));
  const entry = gltf.bufferViews.find((bufferView) => bufferView.name === name);
  view.setUint32(28 + jsonLength + entry.byteOffset + 4 * word, value, true);
  return result;
}

function fromF64Hex(hex) {
  const bytes = Uint8Array.from(hex.match(/../g), (pair) => Number.parseInt(pair, 16));
  return new DataView(bytes.buffer).getFloat64(0, false);
}

test("lossless binary64 keys match Python and separate old decimal collisions", () => {
  const vectors = [
    [Number.MIN_VALUE, "0000000000000001"],
    [0.00001, "3ee4f8b588e368f1"],
    [0.0015, "3f589374bc6a7efa"],
    [0.005, "3f747ae147ae147b"],
    [1, "3ff0000000000000"],
    [Number.MAX_VALUE, "7fefffffffffffff"],
  ];
  for (const [value, expected] of vectors) assert.equal(float64Hex(value), expected);
  for (const value of [0, -0, -1, NaN, Infinity, -Infinity, "0.0015", true]) {
    assert.throws(() => float64Hex(value), /positive finite/);
  }
  for (const invalid of ["11", "A".repeat(64), null]) {
    assert.throws(() => tessellationCacheKey(invalid, Q), /64 lowercase hex/);
    assert.throws(() => resolvedTessellationIdentity(D, invalid, Q), /64 lowercase hex/);
  }

  const closeA = fromF64Hex("3f589374bc6a7efa");
  const closeB = fromF64Hex("3f589374bc6a7efb");
  assert.equal(closeA.toExponential(6), closeB.toExponential(6), "old key collides");
  assert.notEqual(
    tessellationCacheKey(D, { ...Q, chordTolerance: closeA }),
    tessellationCacheKey(D, { ...Q, chordTolerance: closeB }),
    "the key preserves the requested double",
  );

  // The tolerances are the only options a mesh is keyed by: anything else is a request for
  // something no stored mesh is, and never reaches a hit.
  for (const [name, value] of [["loopTolerance", 1e-5], ["maxRefineDepth", 9], ["collectBoundaryDebug", true]]) {
    assert.throws(
      () => tessellationCacheKey(D, { ...Q, [name]: value }),
      new RegExp(`not part of the mesh key: ${name}`),
    );
    assert.throws(() => tessellationQuality({ [name]: value }), /not part of the mesh key/);
  }
  // A quality read back from an entry keys as the request it spells.
  assert.equal(tessellationCacheKey(D, tessellationQuality(Q)), tessellationCacheKey(D, Q));
  assert.equal(tessellationCacheKey(D, { chordTolerance: 0.0015, angleTolerance: 0.35 }),
    `${D}-t${TESSELLATION_VERSION}-p6-l3f589374bc6a7efa-a3fd6666666666666`);
  // A request names both tolerances: which pair a mesh is drawn at is cadgen's, so one that
  // leaves either out is refused, never filled in here.
  for (const partial of [undefined, {}, { chordTolerance: 0.0015 }, { angleTolerance: 0.35 }]) {
    assert.throws(() => tessellationCacheKey(D, partial), /names both tolerances/, JSON.stringify(partial));
    assert.throws(() => resolvedTessellationIdentity(D, O, partial), /names both tolerances/);
  }
});

test("a GLB body round-trips its arrays and tables as views and exposes exact D/O/L/Q/R", () => {
  const source = componentFixture();
  const bytes = encodedEntry();
  const L = tessellationCacheKey(D, Q);
  const R = resolvedTessellationIdentity(D, O, Q);
  const decoded = decodeComponentTessellation(bytes, {
    surfaceInput: D,
    surfaceObject: O,
    tessellationInput: L,
    renderIdentity: R,
    tessellation: Q,
  });
  assert.ok(decoded);
  assert.equal(MESH_PAYLOAD_VERSION, 6);
  assert.deepEqual(decoded.identity, {
    surfaceInput: D,
    surfaceObject: O,
    tessellationInput: L,
    renderIdentity: R,
    quality: tessellationQuality(Q),
    tessellatorVersion: TESSELLATION_VERSION,
    payloadVersion: 6,
  });
  assert.deepEqual(decoded.partColor, [0.6, 0.5, 0.4, 1]);
  const { component } = decoded;
  assert.ok(component.indices instanceof Uint16Array, "a component of at most 65,535 vertices indexes in u16");
  for (const field of ["positions", "normals", "indices"]) {
    assert.deepEqual([...component[field]], [...source[field]], field);
  }
  for (const field of ["positions", "normals", "indices", "faceTable", "edgeTable", "edgePoints"]) {
    assert.equal(component[field].buffer, bytes.buffer, `${field} is zero-copy`);
  }
  assert.deepEqual(meshFaceRanges(component), source.faceRanges);
  assert.deepEqual(meshEdgePolylines(component).map(({ ord, visibilityClass, polyline }) => [ord, visibilityClass, [...polyline]]),
    [[9, "boundary", [0, 0, 0, 2, 0, 0]]]);
  assert.deepEqual(component.bounds, source.bounds);
  assert.equal(component.scale, source.scale);

  const unalignedStorage = new Uint8Array(bytes.length + 1);
  unalignedStorage.set(bytes, 1);
  const unaligned = unalignedStorage.subarray(1);
  const copied = decodeComponentTessellation(unaligned, { surfaceInput: D, surfaceObject: O, tessellation: Q });
  assert.ok(copied);
  assert.deepEqual([...copied.component.positions], [...source.positions]);
  assert.notEqual(copied.component.positions.buffer, unalignedStorage.buffer, "unaligned input safely copies");
});

test("a component past 65,535 vertices indexes in u32, and the render buffers are u32 either way", () => {
  const vertices = 65536;
  const positions = new Float32Array(3 * vertices);
  for (let vertex = 0; vertex < vertices; vertex += 1) positions[3 * vertex] = vertex;
  const component = {
    positions, normals: new Float32Array(3 * vertices).fill(1 / Math.sqrt(3)),
    indices: new Uint32Array([0, 1, vertices - 1]),
    faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }], edges: [],
    bounds: { min: [0, 0, 0], max: [vertices - 1, 0, 0] }, scale: vertices - 1,
  };
  const wide = decodeComponentTessellation(encodeMeshFixture(component, { surfaceInput: D, surfaceObject: O }));
  assert.ok(wide.component.indices instanceof Uint32Array);
  assert.deepEqual([...wide.component.indices], [0, 1, vertices - 1]);
  assert.ok(buildMeshDataFromSurf(surfIndexFromCacheEntry(wide), wide.component).indices instanceof Uint32Array);
  assert.ok(buildMeshDataFromSurf({ partColor: null }, solidComponent()).indices instanceof Uint32Array);
});

test("a stored mesh is a glTF 2.0 file a stock GLTFLoader draws", async () => {
  const gltf = await new GLTFLoader().parseAsync(encodedEntry().slice().buffer, "");
  const meshes = [];
  gltf.scene.traverse((object) => { if (object.isMesh) meshes.push(object); });
  assert.equal(meshes.length, 1, "one mesh, one triangle primitive");
  const geometry = meshes[0].geometry;
  assert.deepEqual([...geometry.getAttribute("position").array], [...componentFixture().positions]);
  assert.deepEqual([...geometry.getIndex().array], [0, 1, 2]);
  // Its node turns Z-up millimetres into Y-up metres.
  gltf.scene.updateMatrixWorld(true);
  const corner = geometry.getAttribute("position");
  const world = meshes[0].localToWorld(new Vector3(corner.getX(2), corner.getY(2), corner.getZ(2)));
  assert.deepEqual([world.x, world.y, world.z].map((value) => Math.round(value * 1e6) / 1e6 + 0), [0, 0, -0.003]);
});

test("empty imported components round-trip through the cache without changing assembly bounds", () => {
  // What cadgen stores for a product with no faces and no edges: empty arrays, zero bounds.
  const component = {
    positions: new Float32Array(0), normals: new Float32Array(0),
    indices: new Uint32Array(0), faceRanges: [], edges: [],
    bounds: { min: [0, 0, 0], max: [0, 0, 0] }, scale: 1e-6,
  };
  const bytes = encodeMeshFixture(component, { surfaceInput: D, surfaceObject: O });
  const decoded = decodeComponentTessellation(bytes);
  assert.ok(decoded, "an empty product entry is a valid complete payload");
  assert.equal(tessellationPayloadFacts(bytes).byteLength, bytes.length, "a JSON chunk alone");
  for (const field of ["positions", "normals", "indices", "faceTable", "edgeTable", "edgePoints"]) {
    assert.equal(decoded.component[field].length, 0, field);
  }
  const emptyMesh = buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), decoded.component);
  const solidMesh = buildMeshDataFromSurf({ partColor: null }, solidComponent());
  const descriptor = { assembly: { root: {
    id: "root", nodeType: "assembly", children: [
      { id: "empty", nodeType: "part", children: [] },
      { id: "solid", nodeType: "part", children: [] },
    ],
  } }, occurrences: [
    { id: "empty", component: "empty", transform: [
      1, 0, 0, -1000, 0, 1, 0, -1000, 0, 0, 1, -1000, 0, 0, 0, 1,
    ] },
    { id: "solid", component: "solid" },
  ] };
  const assembly = buildComposedPackageMeshData(descriptor, new Map([
    ["empty", emptyMesh], ["solid", solidMesh],
  ]));
  assert.deepEqual(assembly.parts.map((part) => part.occurrenceId), ["empty", "solid"]);
  assert.deepEqual(assembly.missingComponentIds, []);
  assert.equal(assembly.parts[0].bounds, null);
  assert.equal(assembly.parts[0].triangleCount, 0);
  assert.equal(assembly.parts[1].triangleCount, 1);
  assert.deepEqual(assembly.bounds, solidMesh.bounds, "only real geometry frames the view");
  assert.deepEqual(assembly.assemblyRoot.bounds, solidMesh.bounds);
});

test("a wire-only imported component draws its edges and frames nothing", () => {
  // A STEP product holding only wires (a sketch, a reference curve) has no faces: cadgen stores
  // its edges' polylines, bounded by their points, and no triangles.
  const component = {
    positions: new Float32Array(0), normals: new Float32Array(0),
    indices: new Uint32Array(0), faceRanges: [],
    edges: [
      { ord: 1, visibilityClass: "feature", polyline: new Float32Array([0, 0, 0, 0, 0, 50]) },
      { ord: 2, visibilityClass: "feature", polyline: new Float32Array([10, 0, 50, 0, 10, 50, -10, 0, 50]) },
    ],
    bounds: { min: [-10, 0, 0], max: [10, 10, 50] }, scale: Math.hypot(20, 10, 50),
  };
  const decoded = decodeComponentTessellation(encodeMeshFixture(component, { surfaceInput: D, surfaceObject: O }));
  assert.ok(decoded, "a wire-only product is a valid complete payload");
  assert.deepEqual(meshEdgePolylines(decoded.component).map((edge) => edge.ord), [1, 2]);

  const wireMesh = buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), decoded.component);
  assert.deepEqual([...wireMesh.cadEdgeIndices], [0, 1, 2, 3, 3, 4], "its edges reach the mesh data");
  const solidMesh = buildMeshDataFromSurf({ partColor: null }, solidComponent());
  const assembly = buildComposedPackageMeshData({ assembly: { root: {
    id: "root", nodeType: "assembly", children: [
      { id: "wire", nodeType: "part", children: [] },
      { id: "solid", nodeType: "part", children: [] },
    ],
  } }, occurrences: [
    { id: "wire", component: "wire", transform: [1, 0, 0, 1000, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    { id: "solid", component: "solid" },
  ] }, new Map([["wire", wireMesh], ["solid", solidMesh]]));
  assert.deepEqual(assembly.parts.map((part) => part.occurrenceId), ["wire", "solid"]);
  assert.equal(assembly.parts[0].bounds, null, "nothing draws a part without triangles");
  assert.deepEqual(assembly.bounds, solidMesh.bounds, "so it cannot move the camera");
});

test("each edge class draws as its line class, and none draws nothing", () => {
  const classes = ["feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown", "none"];
  const component = {
    ...componentFixture(),
    edges: classes.map((visibilityClass, index) => ({
      ord: index + 1, visibilityClass, polyline: new Float32Array([index, 0, 0, index, 1, 0]),
    })),
  };
  const decoded = decodeComponentTessellation(encodeMeshFixture(component, { surfaceInput: D, surfaceObject: O }));
  const { cadEdgePositions, cadEdgeClassRanges } = buildMeshDataFromSurf({ partColor: null }, decoded.component);
  assert.deepEqual(cadEdgeClassRanges.map(({ classId, pointCount, segmentCount }) => [classId, pointCount, segmentCount]),
    [["feature", 8, 4], ["tangent", 2, 1], ["seam", 2, 1], ["degenerate", 2, 1]]);
  // Feature first, in edge order, with the classes that draw as features (boundary,
  // nonManifold, unknown) after the feature edge itself.
  assert.deepEqual([0, 1, 2, 3].map((point) => cadEdgePositions[6 * point]), [0, 4, 5, 6]);
});

test("cadgen's stored meshes decode as the bodies their probe rows describe", () => {
  for (const [name, level] of [["sun_gear", 0], ["sun_gear", 1], ["cam_follower_roller", 1], ["mixed", 0]]) {
    const fixture = meshFixture(name, level);
    const row = validateTessellationProbeRow(fixture.row, {
      tessellationInput: tessellationCacheKey(fixture.surfaceInput, fixture.tessellation),
    });
    assert.ok(row, `${name} L${level} row`);
    const decoded = decodeComponentTessellation(fixture.bytes, {
      surfaceInput: fixture.surfaceInput, surfaceObject: fixture.surfaceObject, tessellation: fixture.tessellation,
    });
    assert.ok(decoded, `${name} L${level} decodes`);
    assert.equal(decoded.component.positions.length, 3 * row.vertexCount);
    assert.equal(decoded.component.normals.length, 3 * row.vertexCount);
    assert.equal(decoded.component.indices.length, row.indexCount);
    assert.ok(row.faceCount > 0 && row.edgeCount > 0);
    assert.ok(surfIndexFromCacheEntry(decoded), "every stored mesh carries its part colour");
  }
});

test("decode rejects expected and embedded identity mismatches as cache misses", () => {
  const bytes = encodedEntry();
  const L = tessellationCacheKey(D, Q);
  assert.equal(decodeComponentTessellation(bytes, { surfaceInput: D2 }), null);
  assert.equal(decodeComponentTessellation(bytes, { surfaceObject: O2 }), null);
  assert.equal(decodeComponentTessellation(bytes, { tessellationInput: `${L}x` }), null);
  assert.equal(decodeComponentTessellation(bytes, {
    renderIdentity: resolvedTessellationIdentity(D, O2, Q),
  }), null);
  assert.equal(decodeComponentTessellation(bytes, {
    tessellation: { ...Q, chordTolerance: fromF64Hex("3f589374bc6a7efb") },
  }), null);

  const cad = (mutate) => rewriteJson(bytes, (gltf) => mutate(gltf.extras.cadgen));
  assert.equal(decodeComponentTessellation(cad((c) => { c.surfaceInput = D2; })), null);
  assert.equal(decodeComponentTessellation(cad((c) => { c.surfaceObject = O2; }), { surfaceObject: O }), null);
  assert.equal(decodeComponentTessellation(cad((c) => { c.quality.chordToleranceF64 = "3f589374bc6a7efb"; })), null);
  assert.equal(decodeComponentTessellation(cad((c) => {
    c.tessellationInput = `${c.tessellationInput.slice(0, -1)}0`;
  })), null);
  assert.equal(decodeComponentTessellation(cad((c) => { c.payloadVersion = 5; })), null, "another format version is a miss");
  assert.equal(decodeComponentTessellation(cad((c) => { delete c.surfaceInput; })), null);
});

test("decode rejects corrupt, truncated and foreign containers", () => {
  const bytes = encodedEntry();
  assert.equal(decodeComponentTessellation(null), null);
  assert.equal(decodeComponentTessellation(new Uint8Array(4)), null);
  assert.equal(decodeComponentTessellation(bytes.subarray(0, bytes.length - 4)), null);
  const wrongMagic = bytes.slice();
  new DataView(wrongMagic.buffer).setUint32(0, 0x53534554, true);
  assert.equal(decodeComponentTessellation(wrongMagic), null, "a TESS body is not one");
  const glTF1 = bytes.slice();
  new DataView(glTF1.buffer).setUint32(4, 1, true);
  assert.equal(decodeComponentTessellation(glTF1), null);
  const longer = new Uint8Array(bytes.length + 4);
  longer.set(bytes);
  assert.equal(decodeComponentTessellation(longer), null, "the header's length is the body's");
  const badCount = rewriteJson(bytes, (gltf) => { gltf.accessors[0].count = -1; });
  assert.equal(decodeComponentTessellation(badCount), null);
});

test("decode rejects a JSON chunk that is not the canonical one for its values", () => {
  const bytes = encodedEntry();
  const mutations = [
    (g) => { g.extras.cadgen.bounds.min = [null, 0, 0]; },
    (g) => { g.extras.cadgen.bounds.min[0] = g.extras.cadgen.bounds.max[0] + 1; },
    (g) => { g.extras.cadgen.scale = 0; },
    (g) => { g.extras.cadgen.partColor = [1, 0, 0]; },
    (g) => { g.extras.cadgen.faceColors = [[1, 0, 0]]; },
    (g) => { g.extras.cadgen.edgeClasses = ["none"]; },
    (g) => { g.extras.cadgen.faces.count = 2; },
    (g) => { g.extras.cadgen.edges = null; },
    (g) => { g.extras.cadgen.extension = "refused"; },
    (g) => { g.extras.other = {}; },
    (g) => { g.accessors[0].max = [2, 3, 1]; },
    (g) => { g.accessors[2].componentType = 5125; },
    (g) => { g.accessors[2].count = 6; },
    (g) => { g.bufferViews[3].byteOffset += 4; },
    (g) => { g.buffers[0].byteLength += 4; },
    (g) => { g.nodes[0].scale = [1, 1, 1]; },
    (g) => { g.meshes[0].primitives[0].mode = 1; },
    (g) => { g.extensionsUsed = ["KHR_mesh_quantization"]; },
  ];
  for (const [index, mutate] of mutations.entries()) {
    const mutated = rewriteJson(bytes, mutate);
    assert.equal(decodeComponentTessellation(mutated), null, `JSON mutation ${index}`);
    assert.equal(tessellationPayloadFacts(mutated), null, `JSON mutation ${index} has no facts`);
  }
  assert.ok(decodeComponentTessellation(rewriteJson(bytes, () => {})), "the canonical JSON, re-spelled, reads");
  assert.equal(surfIndexFromCacheEntry(null), null, "nothing decoded is nothing to draw");
});

test("decode rejects face and edge tables that do not cover their arrays in order", () => {
  const bytes = encodedEntry();
  const faces = (word, value) => rewriteTable(bytes, "cadgen.faces", word, value);
  const edges = (word, value) => rewriteTable(bytes, "cadgen.edges", word, value);
  const mutations = {
    "face ordinal 0": faces(0, 0),
    "face range start": faces(1, 3),
    "face partial triangle": faces(2, 2),
    "face range short of the indices": faces(2, 0),
    "face colour past the palette": faces(3, 2),
    "edge ordinal 0": edges(0, 0),
    "edge points start": edges(1, 1),
    "edge of one point": edges(2, 1),
    "edge class past the names": edges(3, 8),
  };
  for (const [label, mutated] of Object.entries(mutations)) {
    assert.equal(decodeComponentTessellation(mutated), null, label);
  }
  const twoFaces = encodeMeshFixture({
    ...componentFixture(),
    positions: new Float32Array([0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 1]),
    normals: new Float32Array(12).fill(0.5),
    indices: new Uint32Array([0, 1, 2, 0, 1, 3]),
    faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }, { ord: 2, indexStart: 3, indexCount: 3 }],
    bounds: { min: [0, 0, 0], max: [2, 3, 1] },
  }, { surfaceInput: D, surfaceObject: O });
  assert.ok(decodeComponentTessellation(twoFaces));
  assert.equal(decodeComponentTessellation(rewriteTable(twoFaces, "cadgen.faces", 4, 1)), null,
    "face ordinals rise");
});

test("a body that leaves a face no mesher covered names it, and its probe row counts it", () => {
  const leftOut = encodeMeshFixture({
    ...componentFixture(),
    faceRanges: [{ ord: 1, indexStart: 0, indexCount: 3 }, { ord: 2, indexStart: 3, indexCount: 0 }],
    unmeshedFaces: [2],
  }, { surfaceInput: D, surfaceObject: O, tessellation: Q });
  const decoded = decodeComponentTessellation(leftOut);
  assert.ok(decoded);
  assert.deepEqual([...decoded.component.unmeshedFaces], [2]);
  assert.deepEqual([...solidComponent().unmeshedFaces], [], "a whole body names none");
  // The render data carries them, for the viewer to name the part drawn without them.
  assert.deepEqual(buildMeshDataFromSurf(surfIndexFromCacheEntry(decoded), decoded.component).unmeshedFaces, [2]);
  const row = probeRowFor(leftOut);
  assert.equal(row.unmeshedFaceCount, 1);
  assert.equal(tessellationPayloadFacts(leftOut).unmeshedFaceCount, 1);
  assert.deepEqual(validateTessellationProbeRow(row), row);
  assert.equal("unmeshedFaceCount" in probeRowFor(encodedEntry()), false, "a whole body's row counts none");
  for (const count of [0, 3, 1.5]) {
    assert.equal(validateTessellationProbeRow({ ...row, unmeshedFaceCount: count }), null, `count ${count}`);
  }
  // A named face is one of the table's empty faces, named once, in order.
  for (const [label, value] of Object.entries({
    "a face with triangles": [1], "an empty list": [], "out of order": [2, 2], "not a face": [3],
  })) {
    assert.equal(decodeComponentTessellation(rewriteJson(leftOut, (gltf) => {
      gltf.extras.cadgen.unmeshedFaces = value;
    })), null, label);
  }
});

test("batch container preserves aligned zero-copy hits, misses and odd payloads", () => {
  const entry = encodedEntry();
  const odd = new Uint8Array([1, 2, 3]);
  const batch = encodeTessellationCacheBatch([entry, null, odd]);
  const decoded = decodeTessellationCacheBatch(batch);
  assert.equal(decoded.length, 3);
  assert.equal(decoded[1], null);
  assert.deepEqual([...decoded[2]], [1, 2, 3]);
  assert.equal(decoded[0].byteOffset % 4, 0);
  const component = decodeComponentTessellation(decoded[0], {
    surfaceInput: D,
    surfaceObject: O,
    tessellation: Q,
  });
  assert.ok(component);
  assert.equal(component.component.positions.buffer, batch.buffer, "batch hit stays zero-copy");
  assert.equal(decodeTessellationCacheBatch(batch.subarray(0, 14)), null);
  const corrupt = batch.slice();
  new DataView(corrupt.buffer).setUint32(0, 0, true);
  assert.equal(decodeTessellationCacheBatch(corrupt), null);
});

test("probes and reads accept only entries bound to the requested L", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const entry = encodedEntry();
  const row = probeRowFor(entry);
  setTessellationCacheProvider({
    // A provider answering every key with D's row: only D's key may adopt it.
    async probeMany(keys) { return keys.map(() => row); },
    async getProbed() { return entry; },
  });
  const probes = await tessellationCache.probeCachedTessellationEntries([D, D2], Q);
  assert.deepEqual([...probes.keys()], [D], "only the bound entry is readable");
  const hit = await tessellationCache.getCachedComponentEntry(D, Q, { probe: probes.get(D) });
  assert.equal(hit.identity.surfaceObject, O);
  assert.equal(await tessellationCache.getCachedEntryBytes(D2, Q), null);
});

test("a host that meshes on request answers what a probe found missing, as a probe would", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const stored = encodedEntry();
  const made = encodedEntry({ surfaceInput: D2 });
  const provider = memoryMeshProvider([stored], { produce: [made] });
  setTessellationCacheProvider(provider);
  const probed = await tessellationCache.probeCachedTessellationEntries([D, D2], Q);
  assert.deepEqual([...probed.keys()], [D]);
  const produced = await tessellationCache.produceTessellationEntries([D2], Q);
  assert.deepEqual([...produced.keys()], [D2]);
  assert.equal(provider.counts.produced, 1);
  const bytes = await tessellationCache.getCachedEntryBytes(D2, Q, { probe: produced.get(D2), strictProbe: true });
  assert.deepEqual(bytes, made, "the produced mesh reads as a stored one");
  const unknown = "33".repeat(32);
  assert.deepEqual([...(await tessellationCache.produceTessellationEntries([unknown], Q)).keys()], [],
    "a mesh the host cannot make stays missing");

  // A host that only reads (the viewer) offers no produce request: nothing is asked.
  setTessellationCacheProvider(memoryMeshProvider([stored]));
  assert.equal((await tessellationCache.produceTessellationEntries([D2], Q)).size, 0);
});

test("an HTTP produce request names its keys, and a refusal is an error with the host's reason", async () => {
  const entry = encodedEntry();
  const row = probeRowFor(entry);
  const key = tessellationCacheKey(D, Q);
  const calls = [];
  let answer = new Response(JSON.stringify({ entries: { [key]: row } }), { status: 200 });
  const provider = createHttpTessellationCacheProvider({
    origin: "http://snapshot.test", produceUrl: "http://snapshot.test/__tess_cache/produce",
    fetch: async (url, options) => { calls.push({ url: String(url), body: JSON.parse(options.body) }); return answer; },
  });
  assert.deepEqual(await provider.produceMany([key]), [row]);
  assert.deepEqual(calls, [{ url: "http://snapshot.test/__tess_cache/produce", body: { tessellationInputs: [key] } }]);
  answer = new Response("cadgen could not mesh a component: OCCT did not mesh 1 face(s)", { status: 500 });
  await assert.rejects(provider.produceMany([key]), /OCCT did not mesh 1 face/);
  assert.equal(createHttpTessellationCacheProvider({ origin: "http://viewer.test" }).produceMany, undefined,
    "a provider names a produce route only where its host serves one");
});

test("a vanished probed body is an explicit retry boundary only when requested", async (t) => {
  t.after(() => setTessellationCacheProvider(null));
  const entry = encodedEntry();
  const key = tessellationCacheKey(D, Q);
  const facts = tessellationPayloadFacts(entry, { tessellationInput: key });
  const object = createHash("sha256").update(entry).digest("hex");
  const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA, object, ...facts });
  setTessellationCacheProvider({
    async probeMany() { return [row]; },
    async getProbed() { return null; },
  });
  assert.equal(await tessellationCache.getCachedEntryBytes(D, Q, { probe: row }), null);
  await assert.rejects(
    tessellationCache.getCachedEntryBytes(D, Q, { probe: row, strictProbe: true }),
    (error) => isTessellationCacheProbeMissError(error) && error.probe.object === row.object,
  );
});

test("strict probe admission also rejects a provider lost before body read", async () => {
  setTessellationCacheProvider(null);
  await assert.rejects(
    tessellationCache.getCachedEntryBytes(D, Q, { probe: { object: "gone" }, strictProbe: true }),
    isTessellationCacheProbeMissError,
  );
});

test("HTTP provider probes metadata before an exact bounded object read", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const entry = encodedEntry();
  const key = tessellationCacheKey(D, Q);
  const facts = tessellationPayloadFacts(entry, { tessellationInput: key });
  const object = createHash("sha256").update(entry).digest("hex");
  const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA, object, ...facts });
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).endsWith("/probe")) {
      return new Response(JSON.stringify({ entries: { [key]: row } }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    }
    return new Response(entry.slice(), {
      status: 200, headers: { "content-length": String(entry.byteLength) },
    });
  };
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", fetch: (...args) => globalThis.fetch(...args) });
  const [probed] = await provider.probeMany([key]);
  assert.deepEqual(probed, row);
  const body = await provider.getProbed(probed, { maxBytes: row.byteLength });
  assert.deepEqual(body, entry);
  const readUrl = new URL(calls[1].url);
  assert.equal(readUrl.searchParams.get("object"), object);
  assert.equal(readUrl.searchParams.get("maxBytes"), String(row.byteLength));

  globalThis.fetch = async () => new Response(entry.slice(), {
    status: 200, headers: { "content-length": String(entry.byteLength + 1) },
  });
  assert.equal(await provider.getProbed(probed, { maxBytes: row.byteLength }), null,
    "an observed body larger than admission is rejected before adoption");
});


test("an HTTP batch read verifies each entry on its own: a damaged one is a miss for its component alone", async () => {
  const entries = [encodedEntry(), encodedEntry({ surfaceInput: D2 })];
  const rows = entries.map((entry) => validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
    object: createHash("sha256").update(entry).digest("hex"), ...tessellationPayloadFacts(entry) }));
  const damaged = entries[1].slice();
  damaged[damaged.length - 1] ^= 0xff;
  const container = encodeTessellationCacheBatch([entries[0], damaged]);
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", fetch: async () => new Response(container.slice(), {
    status: 200, headers: { "content-length": String(container.byteLength) },
  }) });
  const bodies = await provider.getManyProbed(rows, { maxBytes: container.byteLength });
  assert.deepEqual(bodies[0], entries[0]);
  assert.equal(bodies[1], null);
});

test("a transport's batch ceiling lowers the server's bound and never raises it", async () => {
  const MIB = 1024 * 1024;
  assert.equal(TESS_BATCH_MAX_BYTES, 32 * MIB);
  assert.deepEqual([8 * MIB, 64 * MIB, undefined, 0, -1, Number.NaN, 2.5].map(tessBatchMaxBytes),
    [8 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB, 32 * MIB]);
  // A client's provider declares its transport's ceiling; the cache and its sessions report it.
  let fetched = 0;
  const provider = createHttpTessellationCacheProvider({ origin: "http://cache.test", maxBatchBytes: 8 * MIB,
    fetch: async () => { fetched += 1; return new Response(null, { status: 500 }); } });
  const cache = createTessellationCache({ provider });
  assert.deepEqual([provider.maxBatchBytes, cache.batchMaxBytes, cache.createSession().batchMaxBytes], [8 * MIB, 8 * MIB, 8 * MIB]);
  assert.equal(createTessellationCache({ provider: createHttpTessellationCacheProvider() }).batchMaxBytes, 32 * MIB);
  // And the provider asks for no batch over it, whatever its caller allows.
  const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
    object: createHash("sha256").update(encodedEntry()).digest("hex"), ...tessellationPayloadFacts(encodedEntry()) });
  const over = Array.from({ length: Math.ceil((8 * MIB) / row.byteLength) + 1 }, () => row);
  assert.equal(await provider.getManyProbed(over, { maxBytes: 32 * MIB }), null);
  assert.equal(fetched, 0);
  cache.dispose();
});

test("bounded probes retain other chunks when one metadata response is unavailable", async (t) => {
  const inputs = Array.from({ length: 513 }, (_, n) => createHash("sha256").update(`input-${n}`).digest("hex"));
  const rows = new Map(inputs.map((surfaceInput) => {
    const entry = encodedEntry({ surfaceInput });
    const facts = tessellationPayloadFacts(entry);
    return [facts.tessellationInput, validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
      object: createHash("sha256").update(entry).digest("hex"), ...facts })];
  }));
  const calls = [];
  setTessellationCacheProvider({ async getProbed() { return null; }, async probeMany(keys) {
    calls.push(keys.length);
    if (calls.length === 2) return null;
    return keys.map((key) => rows.get(key));
  } });
  t.after(() => setTessellationCacheProvider(null));
  const hits = await tessellationCache.probeCachedTessellationEntries(inputs, Q);
  assert.deepEqual(calls, [256, 256, 1]);
  assert.equal(hits.size, 257);
  assert.ok(hits.has(inputs[0]));
  assert.ok(hits.has(inputs[512]));
  assert.equal(hits.has(inputs[256]), false);
});

test("render-session caches isolate exact objects and disposal", async () => {
  const entries = [encodedEntry(), encodedEntry({ surfaceObject: O2 })];
  const caches = entries.map((bytes) => {
    const row = probeRowFor(bytes);
    return createTessellationCache({
      provider: {
        probeMany: async () => [row],
        getProbed: async () => bytes,
      },
    });
  });
  try {
    const decoded = await Promise.all(caches.map((cache) => cache.getCachedComponentEntry(D, Q)));
    assert.equal(decoded[0].identity.surfaceObject, O);
    assert.equal(decoded[1].identity.surfaceObject, O2);
    caches[0].dispose();
    assert.equal(await caches[0].getCachedEntryBytes(D, Q), null);
    assert.deepEqual(await caches[1].getCachedEntryBytes(D, Q), entries[1]);
  } finally {
    for (const cache of caches) cache.dispose();
  }
});

test("cache disposal rejects a late custom-provider response without affecting another session", async () => {
  const entry = encodedEntry();
  const facts = tessellationPayloadFacts(entry);
  const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
    object: createHash("sha256").update(entry).digest("hex"), ...facts });
  let finish;
  const a = createTessellationCache({ provider: {
    probeMany: async () => [row],
    getProbed: () => new Promise((resolve) => { finish = resolve; }),
  } });
  const b = createTessellationCache({ provider: {
    probeMany: async () => [row], getProbed: async () => entry,
  } });
  try {
    const pending = a.getCachedEntryBytes(D, Q, { probe: row });
    const cancelled = assert.rejects(pending, { name: "AbortError" });
    a.dispose();
    finish(entry);
    await cancelled;
    assert.deepEqual(await b.getCachedEntryBytes(D, Q), entry);
  } finally {
    a.dispose(); b.dispose();
  }
});

test("borrowed view cancellation is independent while owner disposal aborts every read", async () => {
  const bytes = encodedEntry();
  const row = validateTessellationProbeRow({ schemaVersion: MESH_INDEX_SCHEMA,
    object: createHash("sha256").update(bytes).digest("hex"), ...tessellationPayloadFacts(bytes) });
  const pending = [];
  const owner = createTessellationCache({ provider: {
    probeMany: async () => [row],
    // Ignore AbortSignal in the provider to prove late adoption is checked too.
    getProbed: (_row, { signal }) => new Promise(resolve => pending.push({ signal, resolve })),
  } });
  try {
    const lifetime = new AbortController();
    const previous = owner.createSession({ signal: lifetime.signal });
    const current = owner.createSession();
    const oldRead = previous.getCachedEntryBytes(D, Q, { probe: row });
    const rejectedOld = assert.rejects(oldRead, { name: "AbortError" });
    const currentRead = current.getCachedEntryBytes(D, Q, { probe: row });
    lifetime.abort();
    assert.equal(pending[0].signal.aborted, true);
    assert.equal(pending[1].signal.aborted, false, "another view retains its own read lifetime");
    pending[0].resolve(bytes);
    pending[1].resolve(bytes);
    await rejectedOld;
    assert.deepEqual(await currentRead, bytes);
    await assert.rejects(previous.getCachedEntryBytes(D, Q, { probe: row }), { name: "AbortError" });
    assert.equal(pending.length, 2, "an already-cancelled view never asks the provider again");

    const lastRead = current.getCachedEntryBytes(D, Q, { probe: row });
    const rejectedLast = assert.rejects(lastRead, { name: "AbortError" });
    owner.dispose();
    assert.equal(pending[2].signal.aborted, true);
    pending[2].resolve(bytes);
    await rejectedLast;
  } finally {
    owner.dispose();
  }
});
