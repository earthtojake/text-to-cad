// The package mesh exporter is the color-fidelity REFERENCE for STL/GLB/3MF
// (design/unified-tessellation.md Phases 2-3): these tests pin the color
// resolution priority the retiring native GLB writer implemented, the
// occurrence-transform bake (including mirroring), and the format envelopes.
import assert from "node:assert/strict";
import test from "node:test";
import zlib from "node:zlib";

import {
  buildPackageMeshPrimitives,
  packageMeshTo3mf,
  packageMeshToFormat,
  packageMeshToGlb,
  packageMeshToStl,
} from "./packageMeshExport.js";

// One unit right triangle in the XY plane, +Z normal, as a one-face component.
function triangleTessellation(overrides = {}) {
  return {
    positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2]),
    faceRanges: [{ ord: 0, color: null, indexStart: 0, indexCount: 3 }],
    partColor: null,
    ...overrides,
  };
}

const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

function descriptorWith(occurrences, components = { c0: {} }) {
  return { kind: "assembly-package", components, occurrences };
}

test("color priority: face > occurrence > component > part > default", () => {
  const cases = [
    // [faceColor, occurrenceColor, componentColor, partColor, expected]
    [[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [1, 1, 0, 1], "#ff0000"],
    [null, [0, 1, 0, 1], [0, 0, 1, 1], [1, 1, 0, 1], "#00ff00"],
    [null, null, [0, 0, 1, 1], [1, 1, 0, 1], "#0000ff"],
    [null, null, null, [1, 1, 0, 1], "#ffff00"],
    [null, null, null, null, "#d4d4d8"],
  ];
  for (const [faceColor, occurrenceColor, componentColor, partColor, expected] of cases) {
    const tess = triangleTessellation({ partColor });
    tess.faceRanges[0].color = faceColor;
    const descriptor = descriptorWith(
      [{ id: "o1", component: "c0", transform: IDENTITY, ...(occurrenceColor ? { color: occurrenceColor } : {}) }],
      { c0: componentColor ? { color: componentColor } : {} },
    );
    const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
    assert.equal(mesh.primitives.length, 1);
    assert.equal(mesh.primitives[0].color, expected, `expected ${expected}`);
  }
});

// The regression this suite used to miss entirely: every fixture above is a
// saturated primary, and 0 and 1 are FIXED POINTS of the sRGB transfer
// function, so encoding a linear float as if it were already sRGB looks
// perfect on them. Only midtones show it -- linear 0.5 is sRGB 0xbc, not 0x80.
const MID_LINEAR = 0.5;
const MID_SRGB_HEX = "bc";

test("linear midtones encode as sRGB at every color level", () => {
  // [faceColor, occurrenceColor, componentColor, partColor, expected]
  const cases = [
    [[MID_LINEAR, 0, 0, 1], null, null, null, `#${MID_SRGB_HEX}0000`],
    [null, [MID_LINEAR, MID_LINEAR, MID_LINEAR, 1], null, null, `#${MID_SRGB_HEX.repeat(3)}`],
    [null, null, [0, MID_LINEAR, 0, 1], null, `#00${MID_SRGB_HEX}00`],
    [null, null, null, [0.2, MID_LINEAR, 0.8, 1], "#7cbce7"],
  ];
  for (const [faceColor, occurrenceColor, componentColor, partColor, expected] of cases) {
    const tess = triangleTessellation({ partColor });
    tess.faceRanges[0].color = faceColor;
    const descriptor = descriptorWith(
      [{ id: "o1", component: "c0", transform: IDENTITY, ...(occurrenceColor ? { color: occurrenceColor } : {}) }],
      { c0: componentColor ? { color: componentColor } : {} },
    );
    const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
    assert.equal(mesh.primitives[0].color, expected);
  }
});

test("GLB round-trips a linear midtone back to the same linear baseColorFactor", () => {
  // The whole chain in one assertion: linear in -> sRGB hex -> glTF's LINEAR
  // baseColorFactor. Encoding the hex naively made this land on 0.214, the
  // signature of a double gamma application.
  const descriptor = descriptorWith([
    { id: "o1", component: "c0", transform: IDENTITY, color: [MID_LINEAR, MID_LINEAR, MID_LINEAR, 1] },
  ]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  assert.equal(mesh.primitives[0].color, `#${MID_SRGB_HEX.repeat(3)}`);
  const bytes = packageMeshToGlb(mesh, { name: "mid" });
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + view.getUint32(12, true))));
  const factor = gltf.materials[0].pbrMetallicRoughness.baseColorFactor;
  for (const channel of factor.slice(0, 3)) {
    assert.ok(Math.abs(channel - MID_LINEAR) < 0.004, `expected ~${MID_LINEAR}, got ${channel}`);
  }
});

test("3MF displaycolor is the sRGB encoding of the linear part color", () => {
  // displaycolor is spec'd sRGB, so the linear float must be converted exactly
  // once on the way in -- it used to be written verbatim.
  const tess = triangleTessellation({ partColor: [MID_LINEAR, MID_LINEAR, MID_LINEAR, 1] });
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
  const text = new TextDecoder("latin1").decode(packageMeshTo3mf(mesh, { name: "mid" }));
  assert.match(text, new RegExp(`displaycolor="#${MID_SRGB_HEX.repeat(3).toUpperCase()}FF"`));
});

test("per-face colors split one component into color-grouped primitives", () => {
  const tess = triangleTessellation({
    positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0]),
    normals: new Float32Array(Array(6).fill([0, 0, 1]).flat()),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    faceRanges: [
      { ord: 0, color: [1, 0, 0, 1], indexStart: 0, indexCount: 3 },
      { ord: 1, color: null, indexStart: 3, indexCount: 3 },
    ],
  });
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
  assert.deepEqual(
    mesh.primitives.map((p) => p.color).sort(),
    ["#d4d4d8", "#ff0000"],
  );
  assert.equal(mesh.triangleCount, 2);
});

test("occurrence transforms bake absolutely; shared components diverge per occurrence", () => {
  const translate = [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1];
  const descriptor = descriptorWith([
    { id: "o1", component: "c0", transform: IDENTITY },
    { id: "o2", component: "c0", transform: translate },
  ]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  assert.equal(mesh.triangleCount, 2);
  const p = mesh.primitives[0].positions;
  assert.deepEqual([...p.slice(0, 3)], [0, 0, 0]);
  assert.deepEqual([...p.slice(9, 12)], [10, 20, 30]);
  // Pure translation leaves normals untouched.
  assert.deepEqual([...mesh.primitives[0].normals.slice(9, 12)], [0, 0, 1]);
});

test("mirroring flips winding and keeps normals outward", () => {
  const mirrorX = [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: mirrorX }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  const p = mesh.primitives[0].positions;
  const n = mesh.primitives[0].normals;
  // Winding reversed: corners come out v0, v2, v1 (each x-mirrored).
  assert.deepEqual([...p].map((v) => v + 0), [0, 0, 0, 0, 1, 0, -1, 0, 0]);
  // Facet normal of the emitted winding must agree with the transformed
  // vertex normals (both +Z here: mirror across X flips winding, not the
  // plane's outward side).
  const ux = p[3] - p[0], uy = p[4] - p[1], uz = p[5] - p[2];
  const vx = p[6] - p[0], vy = p[7] - p[1], vz = p[8] - p[2];
  const facet = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
  const dot = facet[0] * n[0] + facet[1] * n[1] + facet[2] * n[2];
  assert.ok(dot > 0, `facet normal must agree with shaded normals (dot=${dot})`);
});

test("rotation transforms normals via inverse-transpose", () => {
  // 90 degrees about X: +Z normal -> +Y... wait, row-major: y' = -z, z' = y.
  const rotX90 = [1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1];
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: rotX90 }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  const n = mesh.primitives[0].normals;
  assert.ok(Math.abs(n[0]) < 1e-6 && Math.abs(n[1] + 1) < 1e-6 && Math.abs(n[2]) < 1e-6,
    `+Z normal must rotate to -Y, got [${n[0]}, ${n[1]}, ${n[2]}]`);
});

test("defaultColor option replaces only the end-of-chain fallback", () => {
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]),
    { defaultColor: "#123456" });
  assert.equal(mesh.primitives[0].color, "#123456");
  const colored = triangleTessellation({ partColor: [0, 1, 0, 1] });
  const meshColored = buildPackageMeshPrimitives(descriptor, new Map([["c0", colored]]),
    { defaultColor: "#123456" });
  assert.equal(meshColored.primitives[0].color, "#00ff00");
});

test("GLB is Y-up and meter-scaled: CAD mm (x, y, z) lands at (x, z, -y)/1000", () => {
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  const bytes = packageMeshToGlb(mesh, { name: "tri" });
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  const positionAccessor = gltf.accessors[gltf.meshes[0].primitives[0].attributes.POSITION];
  // CAD verts (0,0,0), (1,0,0), (0,1,0) mm -> glTF (0,0,0), (0.001,0,0), (0,0,-0.001) m.
  assert.deepEqual(positionAccessor.min, [0, 0, -0.0010000000474974513]);
  assert.deepEqual(positionAccessor.max, [0.0010000000474974513, 0, 0]);
});

test("an exported GLB round-trips through the viewer's loader back to the CAD it came from", async () => {
  // The writer test above pins the bytes; this pins the WHOLE loop, which is where the
  // "GLBs render on their side" bug lived. The exported file was always a conformant
  // Y-up one — the reader inferred its space from cadOccurrenceId (stamped on every node
  // cadgen writes), decided it was already CAD, skipped the -90-degrees-about-X
  // correction, and put a flat plate on its edge at the right size.
  //
  // A 40 x 20 x 4 mm plate: the giveaway is which axis carries the 4 mm.
  const plate = {
    // Two triangles of the plate's top face plus one of a side wall: enough for the
    // bounding box to have a distinct extent on all three CAD axes.
    positions: new Float32Array([
      0, 0, 4, 40, 0, 4, 40, 20, 4,
      0, 0, 4, 40, 20, 4, 0, 20, 4,
      0, 0, 0, 40, 0, 0, 40, 0, 4,
    ]),
    normals: new Float32Array([
      0, 0, 1, 0, 0, 1, 0, 0, 1,
      0, 0, 1, 0, 0, 1, 0, 0, 1,
      0, -1, 0, 0, -1, 0, 0, -1, 0,
    ]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5, 6, 7, 8]),
    faceRanges: [{ ord: 0, color: null, indexStart: 0, indexCount: 9 }],
    partColor: null,
  };
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", plate]]));
  const bytes = packageMeshToGlb(mesh, { name: "plate" });

  const { buildMeshDataFromGlbBuffer } = await import("../render/glbMeshData.js");
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
  const size = [0, 1, 2].map((axis) => meshData.bounds.max[axis] - meshData.bounds.min[axis]);
  size.forEach((value, axis) => assert.ok(
    Math.abs(value - [40, 20, 4][axis]) < 1e-3,
    `axis ${axis}: ${value} mm, expected ${[40, 20, 4][axis]} mm — the plate came back rotated`,
  ));
});

test("STL: valid binary envelope, colorless, deterministic", () => {
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  const bytes = packageMeshToStl(mesh, { name: "tri" });
  assert.equal(bytes.length, 84 + 50);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(80, true), 1);
  assert.deepEqual(packageMeshToStl(mesh, { name: "tri" }), bytes);
});

test("GLB: one material per color, base color factors match", () => {
  const tess = triangleTessellation({
    positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0]),
    normals: new Float32Array(Array(6).fill([0, 0, 1]).flat()),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    faceRanges: [
      { ord: 0, color: [1, 0, 0, 1], indexStart: 0, indexCount: 3 },
      { ord: 1, color: [0, 0, 1, 1], indexStart: 3, indexCount: 3 },
    ],
  });
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
  const bytes = packageMeshToGlb(mesh, { name: "two-colors" });
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(0, true), 0x46546c67, "glTF magic");
  const jsonLength = view.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  assert.equal(gltf.materials.length, 2);
  // writeGlb emits one mesh+node per colored primitive.
  assert.equal(gltf.meshes.length, 2);
  assert.equal(gltf.meshes.flatMap((m) => m.primitives).length, 2);
  const factors = gltf.materials
    .map((m) => m.pbrMetallicRoughness.baseColorFactor.slice(0, 3).map((c) => Math.round(c * 255)));
  assert.deepEqual(factors.sort(), [[0, 0, 255], [255, 0, 0]]);
});

test("3MF: stored zip with a basematerials group and per-object material refs", () => {
  const tess = triangleTessellation({ partColor: [1, 0, 0, 1] });
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", tess]]));
  const bytes = packageMeshTo3mf(mesh, { name: "red tri" });
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(view.getUint32(0, true), 0x04034b50, "zip local header magic");
  const text = new TextDecoder("latin1").decode(bytes);
  assert.match(text, /basematerials id="1"/);
  assert.match(text, /displaycolor="#FF0000FF"/);
  assert.match(text, /object id="2" type="model" pid="1" pindex="0"/);
  assert.match(text, /<triangle v1="0" v2="1" v3="2"\/>/);
  assert.match(text, /Title">red tri</);
  // Deterministic bytes (zipStore stamps a fixed timestamp).
  assert.deepEqual(packageMeshTo3mf(mesh, { name: "red tri" }), bytes);
});

test("packageMeshToFormat maps formats and rejects unknown ones", () => {
  const descriptor = descriptorWith([{ id: "o1", component: "c0", transform: IDENTITY }]);
  const mesh = buildPackageMeshPrimitives(descriptor, new Map([["c0", triangleTessellation()]]));
  assert.equal(packageMeshToFormat(mesh, "stl").extension, ".stl");
  assert.equal(packageMeshToFormat(mesh, "GLB").contentType, "model/gltf-binary");
  assert.equal(packageMeshToFormat(mesh, "3mf").contentType, "model/3mf");
  assert.throws(() => packageMeshToFormat(mesh, "obj"), /Unsupported/);
});

// zlib is imported to keep this suite honest if zipStore ever grows deflate
// support: stored entries must remain readable without inflation.
void zlib;
