import assert from "node:assert/strict";
import test from "node:test";

import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder, MeshoptEncoder } from "meshoptimizer";

import { UNSIGNED_SHORT_VERTEX_LIMIT, weldMesh, writeGlb } from "./writeGlb.js";
import { srgbToLinear } from "./bytes.js";

/** A unit cube as a non-indexed triangle soup: 12 triangles, 36 loose vertices. */
function cubeSoup(size = 10) {
  const s = size / 2;
  const corners = [
    [-s, -s, -s], [s, -s, -s], [s, s, -s], [-s, s, -s],
    [-s, -s, s], [s, -s, s], [s, s, s], [-s, s, s],
  ];
  const quads = [
    [0, 1, 2, 3], [5, 4, 7, 6], [4, 0, 3, 7],
    [1, 5, 6, 2], [4, 5, 1, 0], [3, 2, 6, 7],
  ];
  const out = [];
  for (const [a, b, c, d] of quads) {
    for (const [i, j, k] of [[a, b, c], [a, c, d]]) {
      out.push(...corners[i], ...corners[j], ...corners[k]);
    }
  }
  return new Float32Array(out);
}

function parseGlb(bytes, { withMeshopt = false } = {}) {
  const loader = new GLTFLoader();
  if (withMeshopt) {
    loader.setMeshoptDecoder(MeshoptDecoder);
  }
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return new Promise((resolve, reject) => {
    loader.parse(copy, "", resolve, reject);
  });
}

function collectMeshes(gltf) {
  const meshes = [];
  gltf.scene.traverse((node) => {
    if (node.isMesh) {
      meshes.push(node);
    }
  });
  return meshes;
}

/** World-space bounding box, so a quantized mesh is compared where it actually renders. */
function worldBounds(mesh) {
  const position = mesh.geometry.getAttribute("position");
  mesh.updateWorldMatrix(true, false);
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < position.count; i += 1) {
    const v = [position.getX(i), position.getY(i), position.getZ(i)];
    const e = mesh.matrixWorld.elements;
    const world = [
      e[0] * v[0] + e[4] * v[1] + e[8] * v[2] + e[12],
      e[1] * v[0] + e[5] * v[1] + e[9] * v[2] + e[13],
      e[2] * v[0] + e[6] * v[1] + e[10] * v[2] + e[14],
    ];
    for (let a = 0; a < 3; a += 1) {
      min[a] = Math.min(min[a], world[a]);
      max[a] = Math.max(max[a], world[a]);
    }
  }
  return { min, max };
}

test("weldMesh collapses a cube soup to 24 vertices and keeps creases", () => {
  const welded = weldMesh(cubeSoup(), null);
  // 6 faces x 4 corners: shared positions must NOT merge across faces, because their
  // normals differ. Merging them is the smooth-shading artefact this keying exists to avoid.
  assert.equal(welded.positions.length / 3, 24);
  assert.equal(welded.indices.length, 36);
});

test("weldMesh is deterministic", () => {
  const a = weldMesh(cubeSoup(), null);
  const b = weldMesh(cubeSoup(), null);
  assert.deepEqual([...a.indices], [...b.indices]);
  assert.deepEqual([...a.positions], [...b.positions]);
});

test("export preset loads in a STOCK GLTFLoader with no meshopt decoder", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup(10) }] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 1);
  const geometry = meshes[0].geometry;
  assert.ok(geometry.index, "export preset must be indexed");
  assert.equal(geometry.getAttribute("position").count, 24);
  assert.equal(geometry.index.count, 36);
  const bounds = worldBounds(meshes[0]);
  bounds.min.forEach((v) => assert.ok(Math.abs(v + 5) < 1e-5, `min ${v}`));
  bounds.max.forEach((v) => assert.ok(Math.abs(v - 5) < 1e-5, `max ${v}`));
});

test("export preset declares no required extensions", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export" });
  const json = JSON.parse(
    new TextDecoder().decode(bytes.subarray(20, 20 + new DataView(
      bytes.buffer, bytes.byteOffset, bytes.byteLength
    ).getUint32(12, true)))
  );
  assert.equal(json.extensionsRequired, undefined);
  assert.equal(json.extensionsUsed, undefined);
});

test("render preset round-trips through GLTFLoader + MeshoptDecoder", async () => {
  await MeshoptEncoder.ready;
  await MeshoptDecoder.ready;
  const bytes = writeGlb(
    { primitives: [{ positions: cubeSoup(10) }] },
    { preset: "render", encoder: MeshoptEncoder }
  );
  const gltf = await parseGlb(bytes, { withMeshopt: true });
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 1);
  const geometry = meshes[0].geometry;
  assert.ok(geometry.index, "render preset must be indexed");
  assert.equal(geometry.getAttribute("position").count, 24);
  assert.equal(geometry.index.count, 36);

  // Quantization is lossy, but the node scale/translation must put the mesh back where it
  // belongs. A 10mm cube quantized over its own bounds should land well inside 0.01mm.
  const bounds = worldBounds(meshes[0]);
  bounds.min.forEach((v) => assert.ok(Math.abs(v + 5) < 0.01, `min ${v}`));
  bounds.max.forEach((v) => assert.ok(Math.abs(v - 5) < 0.01, `max ${v}`));
});

test("render preset refuses to run without an encoder", () => {
  assert.throws(
    () => writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "render" }),
    /requires meshoptimizer/
  );
});

test("multiple primitives become one node each, with occurrence ids", async () => {
  const bytes = writeGlb({
    primitives: [
      { positions: cubeSoup(4), name: "layer:0", occurrenceId: "toolpath:layer:0", color: "#ff0000" },
      { positions: cubeSoup(6), name: "layer:1", occurrenceId: "toolpath:layer:1", color: "#00ff00" },
      { positions: cubeSoup(8), name: "travel", occurrenceId: "toolpath:travel", color: "#0000ff" },
    ],
  }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const meshes = collectMeshes(gltf);
  assert.equal(meshes.length, 3, "one node per primitive drives per-layer visibility");
  assert.deepEqual(
    meshes.map((m) => m.userData?.cadOccurrenceId),
    ["toolpath:layer:0", "toolpath:layer:1", "toolpath:travel"]
  );
  // Per-primitive materials keep constant colour out of the vertex buffer.
  const colors = meshes.map((m) => m.material.color.getHexString());
  assert.equal(new Set(colors).size, 3, `expected 3 distinct materials, got ${colors}`);
});

test("every node DECLARES its coordinate space, defaulting to the glTF convention", async () => {
  const yUp = await parseGlb(writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export" }));
  assert.deepEqual(
    collectMeshes(yUp).map((m) => m.userData?.cadUpAxis),
    ["y"],
    "an unstated space is glTF's own: Y-up"
  );
  const zUp = await parseGlb(
    writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export", upAxis: "z" })
  );
  assert.deepEqual(collectMeshes(zUp).map((m) => m.userData?.cadUpAxis), ["z"]);
});

test("an unknown upAxis is refused rather than written as a space nobody reads", () => {
  assert.throws(
    () => writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export", upAxis: "x" }),
    /upAxis must be "y" \(glTF\) or "z" \(CAD\)/u
  );
});

test("a small primitive indexes in UNSIGNED_SHORT", async () => {
  const bytes = writeGlb({ primitives: [{ positions: cubeSoup() }] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const index = collectMeshes(gltf)[0].geometry.index;
  assert.equal(index.array.constructor, Uint16Array);
  assert.ok(UNSIGNED_SHORT_VERTEX_LIMIT === 65535);
});

test("empty input produces a loadable, empty scene", async () => {
  const bytes = writeGlb({ primitives: [] }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  assert.equal(collectMeshes(gltf).length, 0);
});

test("srgbToLinear matches the sRGB piecewise transfer function", () => {
  assert.equal(srgbToLinear(0), 0);
  assert.equal(srgbToLinear(1), 1);
  // Below the knee the curve is a plain 1/12.92 slope.
  assert.ok(Math.abs(srgbToLinear(0.04) - 0.04 / 12.92) < 1e-12);
  // Mid grey is where treating sRGB as linear is most obviously wrong: 0.5 -> ~0.214.
  assert.ok(Math.abs(srgbToLinear(0.5) - 0.21404114) < 1e-6, srgbToLinear(0.5));
  // Monotonic, and always at or below the input (the curve darkens).
  for (let step = 0; step <= 20; step += 1) {
    const value = step / 20;
    assert.ok(srgbToLinear(value) <= value + 1e-12, `srgbToLinear(${value})`);
  }
});

// The end-to-end statement of what Step 2 is for: an authored sRGB hex must survive the round
// trip and come back as ITSELF. glTF says baseColorFactor is linear and three.js reads it with
// LinearSRGBColorSpace, so writing the sRGB value straight in made every generated GLB render
// brighter than authored. With the conversion, write-then-read is the identity.
test("an authored colour round-trips through GLB as the same sRGB hex", async () => {
  const authored = ["#24e6c2", "#fff45a", "#7c5cff", "#804020", "#000000", "#ffffff"];
  const bytes = writeGlb({
    primitives: authored.map((color, index) => ({
      positions: cubeSoup(4 + index),
      name: `swatch:${index}`,
      color,
    })),
  }, { preset: "export" });
  const gltf = await parseGlb(bytes);
  const readBack = collectMeshes(gltf).map((mesh) => `#${mesh.material.color.getHexString()}`);
  assert.deepEqual(readBack, authored);
});

// --- node grouping and animation ---------------------------------------------

/** The raw glTF JSON out of a .glb, for the structure a loader flattens away. */
function glbJson(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
}

test("primitives sharing a node key become ONE node with several primitives", () => {
  const gltf = glbJson(writeGlb({
    primitives: [
      { positions: cubeSoup(4), node: "o1.1", name: "arm", color: "#ff0000" },
      { positions: cubeSoup(6), node: "o1.1", name: "arm", color: "#00ff00" },
      { positions: cubeSoup(8), node: "o1.2", name: "hand", color: "#0000ff" },
    ],
  }, { preset: "export" }));
  // Two occurrences, not three colours: an animation channel targets a NODE, so
  // a two-coloured occurrence has to stay one of them.
  assert.equal(gltf.nodes.length, 2);
  assert.deepEqual(gltf.meshes.map((mesh) => mesh.primitives.length), [2, 1]);
  assert.deepEqual(gltf.nodes.map((node) => node.name), ["arm", "hand"]);
  // Each primitive keeps its own material.
  assert.equal(gltf.materials.length, 3);
});

test("an animation becomes TRS channels on the nodes its keys name, over one time accessor", () => {
  const times = new Float32Array([0, 0.5, 1]);
  const gltf = glbJson(writeGlb({
    primitives: [
      { positions: cubeSoup(4), node: "o1.1" },
      { positions: cubeSoup(6), node: "o1.2" },
    ],
  }, {
    preset: "export",
    animations: [{
      name: "showcase",
      times,
      channels: [
        {
          node: "o1.2",
          times,
          translation: new Float32Array([0, 0, 0, 1, 0, 0, 2, 0, 0]),
          rotation: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]),
        },
      ],
    }],
    nodeTransforms: new Map([["o1.2", { translation: [0, 0, 0], rotation: [0, 0, 0, 1], scale: null }]]),
  }));
  assert.equal(gltf.animations.length, 1);
  const [animation] = gltf.animations;
  assert.equal(animation.name, "showcase");
  assert.deepEqual(animation.channels.map((channel) => channel.target.path), ["translation", "rotation"]);
  // Node 1 is o1.2; node 0 was never named by a channel and stays untouched.
  assert.deepEqual(animation.channels.map((channel) => channel.target.node), [1, 1]);
  // ONE input accessor for both channels: they are the same schedule, and the
  // file says so rather than repeating it.
  const inputs = new Set(animation.samplers.map((sampler) => sampler.input));
  assert.equal(inputs.size, 1);
  const input = gltf.accessors[[...inputs][0]];
  assert.equal(input.count, 3);
  // REQUIRED on a sampler input: a loader reads the clip's duration off them.
  assert.deepEqual(input.min, [0]);
  assert.deepEqual(input.max, [1]);
  assert.equal(gltf.nodes[0].translation, undefined, "an unanimated node keeps its baked place");
});

test("an animation channel naming a node no primitive declared is refused", () => {
  assert.throws(
    () => writeGlb({ primitives: [{ positions: cubeSoup(), node: "o1.1" }] }, {
      preset: "export",
      animations: [{
        name: "showcase",
        times: new Float32Array([0, 1]),
        channels: [{ node: "o9.9", translation: new Float32Array([0, 0, 0, 1, 0, 0]) }],
      }],
    }),
    /targets node "o9\.9", which no primitive declared/u
  );
});

test("the render preset carries no animation: its node transforms are dequantization", () => {
  assert.throws(
    () => writeGlb({ primitives: [{ positions: cubeSoup() }] }, {
      preset: "render",
      encoder: MeshoptEncoder,
      animations: [{ name: "x", times: new Float32Array([0]), channels: [] }],
    }),
    /use preset 'export' for an animated file/u
  );
  assert.throws(
    () => writeGlb({
      primitives: [
        { positions: cubeSoup(4), node: "o1.1" },
        { positions: cubeSoup(6), node: "o1.1" },
      ],
    }, { preset: "render", encoder: MeshoptEncoder }),
    /cannot put two primitives on node "o1\.1"/u
  );
});

test("an opacity below 1 makes its material BLEND, so an importer honours the alpha", () => {
  const gltf = glbJson(writeGlb({
    primitives: [
      { positions: cubeSoup(4), color: "#ff0000", opacity: 0.25 },
      { positions: cubeSoup(6), color: "#00ff00" },
    ],
  }, { preset: "export" }));
  assert.equal(gltf.materials[0].alphaMode, "BLEND");
  assert.equal(gltf.materials[0].pbrMetallicRoughness.baseColorFactor[3], 0.25);
  // An opaque material says nothing about alphaMode: OPAQUE is the default.
  assert.equal(gltf.materials[1].alphaMode, undefined);
  assert.equal(gltf.materials[1].pbrMetallicRoughness.baseColorFactor[3], 1);
});

// --- the authored PBR finish --------------------------------------------------
//
// A colour is half of what a document says about a surface; the other half is the
// finish. The writer used to hardcode roughness 0.72 / metalness 0.02 on every material
// it emitted, so a model that is 80% metal in the viewer exported as 100% plastic --
// and a metal has no diffuse lobe, so that inverts the shading of most of the file
// rather than merely dulling it.

test("a primitive's material becomes its pbrMetallicRoughness factors", () => {
  const gltf = glbJson(writeGlb({
    primitives: [
      {
        positions: cubeSoup(4),
        color: "#b0b6bb",
        material: { roughness: 0.35, metalness: 0.9 },
      },
    ],
  }, { preset: "export" }));
  const pbr = gltf.materials[0].pbrMetallicRoughness;
  assert.equal(pbr.roughnessFactor, 0.35);
  assert.equal(pbr.metallicFactor, 0.9);
});

test("a primitive with no material keeps the writer's plastic defaults", () => {
  const gltf = glbJson(writeGlb({
    primitives: [{ positions: cubeSoup(4), color: "#b0b6bb" }],
  }, { preset: "export" }));
  const pbr = gltf.materials[0].pbrMetallicRoughness;
  assert.equal(pbr.roughnessFactor, 0.72);
  assert.equal(pbr.metallicFactor, 0.02);
  assert.equal(gltf.materials[0].extensions, undefined);
});

test("a material's channels are independent: an unauthored one falls back, not the whole finish", () => {
  const gltf = glbJson(writeGlb({
    primitives: [{ positions: cubeSoup(4), color: "#b0b6bb", material: { metalness: 1 } }],
  }, { preset: "export" }));
  const pbr = gltf.materials[0].pbrMetallicRoughness;
  assert.equal(pbr.metallicFactor, 1);
  assert.equal(pbr.roughnessFactor, 0.72);
});

test("clearcoat rides KHR_materials_clearcoat, declared USED but never REQUIRED", () => {
  const bytes = writeGlb({
    primitives: [
      {
        positions: cubeSoup(4),
        color: "#c0392b",
        material: { roughness: 0.4, metalness: 0.1, clearcoat: 0.8, clearcoatRoughness: 0.15 },
      },
      { positions: cubeSoup(6), color: "#c0392b" },
    ],
  }, { preset: "export" });
  const gltf = glbJson(bytes);
  assert.deepEqual(gltf.materials[0].extensions.KHR_materials_clearcoat, {
    clearcoatFactor: 0.8,
    clearcoatRoughnessFactor: 0.15,
  });
  // Only USED: a loader that ignores the coat still draws the right geometry in the
  // right colour, so requiring it would make ordinary importers refuse the file.
  assert.deepEqual(gltf.extensionsUsed, ["KHR_materials_clearcoat"]);
  assert.equal(gltf.extensionsRequired, undefined);
  // A material without a coat stays extension-free.
  assert.equal(gltf.materials[1].extensions, undefined);
});

test("clearcoat 0 IS the glTF default, so it writes no extension at all", () => {
  const gltf = glbJson(writeGlb({
    primitives: [{ positions: cubeSoup(4), color: "#c0392b", material: { clearcoat: 0 } }],
  }, { preset: "export" }));
  assert.equal(gltf.materials[0].extensions, undefined);
  assert.equal(gltf.extensionsUsed, undefined);
});

test("a material's opacity is the alpha when the caller overrides nothing, and loses when it does", () => {
  const gltf = glbJson(writeGlb({
    primitives: [
      { positions: cubeSoup(4), color: "#ff0000", material: { opacity: 0.3 } },
      { positions: cubeSoup(6), color: "#00ff00", material: { opacity: 0.3 }, opacity: 0.8 },
    ],
  }, { preset: "export" }));
  assert.equal(gltf.materials[0].alphaMode, "BLEND");
  assert.equal(gltf.materials[0].pbrMetallicRoughness.baseColorFactor[3], 0.3);
  // An explicit `opacity` is a caller's own override (an animation clip's faded
  // occurrence) and wins over the authored one.
  assert.equal(gltf.materials[1].pbrMetallicRoughness.baseColorFactor[3], 0.8);
});

test("GLTFLoader reads the finish back as a physical material", async () => {
  const bytes = writeGlb({
    primitives: [{
      positions: cubeSoup(10),
      color: "#b0b6bb",
      material: { roughness: 0.28, metalness: 0.95, clearcoat: 0.6, clearcoatRoughness: 0.2 },
    }],
  }, { preset: "export" });
  const material = collectMeshes(await parseGlb(bytes))[0].material;
  assert.ok(Math.abs(material.roughness - 0.28) < 1e-6, `roughness ${material.roughness}`);
  assert.ok(Math.abs(material.metalness - 0.95) < 1e-6, `metalness ${material.metalness}`);
  assert.ok(Math.abs(material.clearcoat - 0.6) < 1e-6, `clearcoat ${material.clearcoat}`);
  assert.ok(
    Math.abs(material.clearcoatRoughness - 0.2) < 1e-6,
    `clearcoatRoughness ${material.clearcoatRoughness}`
  );
});

// --- morph targets ----------------------------------------------------------
//
// A deforming tube reaches the writer as ALREADY-INDEXED geometry with a stack
// of per-vertex deltas and a weights schedule. Everything here is a shape the
// writer must refuse or an invariant a loader depends on: glTF weights are per
// MESH, not per primitive, and a weights sampler's output count is
// times x targets rather than the values/stride every TRS track uses.

/** A two-triangle strip as indexed geometry, plus deltas that move one corner. */
function indexedStrip() {
  return {
    positions: new Float32Array([0, 0, 0, 10, 0, 0, 0, 10, 0, 10, 10, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]),
    indices: new Uint32Array([0, 1, 2, 1, 3, 2]),
  };
}

function morphTarget(dy) {
  return {
    positionDeltas: new Float32Array([0, 0, 0, 0, 0, 0, 0, dy, 0, 0, dy, 0]),
    normalDeltas: new Float32Array([0, 0, 0, 0, 0, 0, 0, 0.1, 0, 0, 0.1, 0]),
  };
}

test("morph targets ride the primitive, weights ride the MESH, and both survive a stock loader", async () => {
  const times = new Float32Array([0, 0.5, 1]);
  const bytes = writeGlb({
    primitives: [
      { ...indexedStrip(), node: "o1.2", name: "tendon", color: "#ff0000", targets: [morphTarget(5), morphTarget(-5)] },
    ],
  }, {
    preset: "export",
    animations: [{
      name: "flex",
      channels: [{
        node: "o1.2",
        times,
        // One-hot rows: base, target 0, target 1.
        weights: new Float32Array([0, 0, 1, 0, 0, 1]),
        targetCount: 2,
      }],
    }],
  });
  const gltf = glbJson(bytes);
  const [primitive] = gltf.meshes[0].primitives;
  assert.equal(primitive.targets.length, 2);
  assert.deepEqual(gltf.meshes[0].weights, [0, 0]);
  for (const target of primitive.targets) {
    assert.ok(Number.isInteger(target.POSITION));
    assert.ok(Number.isInteger(target.NORMAL));
    // min/max are the DELTAS' bounds, which is what sizes a morphed bounding box.
    assert.deepEqual(gltf.accessors[target.POSITION].min, [0, target === primitive.targets[0] ? 0 : -5, 0]);
  }
  // The weights sampler's output is times x targets SCALARs, not values/stride.
  const [animation] = gltf.animations;
  assert.deepEqual(animation.channels.map((channel) => channel.target.path), ["weights"]);
  assert.equal(gltf.accessors[animation.samplers[0].output].count, 6);
  assert.equal(gltf.accessors[animation.samplers[0].output].type, "SCALAR");

  const loaded = await parseGlb(bytes);
  const [mesh] = collectMeshes(loaded);
  assert.equal(mesh.geometry.morphAttributes.position.length, 2);
  assert.equal(mesh.geometry.morphAttributes.normal.length, 2);
  assert.equal(mesh.geometry.morphTargetsRelative, true, "deltas, not absolute shapes");
  assert.deepEqual([...mesh.morphTargetInfluences], [0, 0]);
  const track = loaded.animations[0].tracks.find((entry) => entry.name.endsWith(".morphTargetInfluences"));
  assert.ok(track, "the loader found a morph weights track");
  assert.equal(track.getValueSize(), 2);
  assert.equal(track.times.length, 3);
});

test("morph targets on non-indexed input are refused: a weld would break the correspondence", () => {
  assert.throws(
    () => writeGlb({
      primitives: [{ positions: cubeSoup(), node: "o1.1", targets: [{ positionDeltas: new Float32Array(108) }] }],
    }, { preset: "export" }),
    /morph targets need already-indexed input/u,
  );
});

test("two primitives on one node must agree about their target count", () => {
  assert.throws(
    () => writeGlb({
      primitives: [
        { ...indexedStrip(), node: "o1.2", targets: [morphTarget(5), morphTarget(-5)] },
        { ...indexedStrip(), node: "o1.2", targets: [morphTarget(5)] },
      ],
    }, { preset: "export" }),
    /mixes primitives with 2 and 1 morph targets/u,
  );
});

test("a weights channel is checked against the mesh it drives, both ways", () => {
  const base = { ...indexedStrip(), node: "o1.2", targets: [morphTarget(5), morphTarget(-5)] };
  const times = new Float32Array([0, 1]);
  assert.throws(
    () => writeGlb({ primitives: [base] }, {
      preset: "export",
      animations: [{ name: "flex", channels: [{ node: "o1.2", times, weights: new Float32Array(6), targetCount: 3 }] }],
    }),
    /declares 3 morph targets, but its mesh has 2/u,
  );
  assert.throws(
    () => writeGlb({ primitives: [base] }, {
      preset: "export",
      animations: [{ name: "flex", channels: [{ node: "o1.2", times, weights: new Float32Array(6), targetCount: 2 }] }],
    }),
    /has 6 scalars for 2 times x 2 targets/u,
  );
  // A weights channel on a node with no targets at all is the same refusal.
  assert.throws(
    () => writeGlb({ primitives: [{ ...indexedStrip(), node: "o1.2" }] }, {
      preset: "export",
      animations: [{ name: "flex", channels: [{ node: "o1.2", times, weights: new Float32Array(2), targetCount: 1 }] }],
    }),
    /declares 1 morph targets, but its mesh has 0/u,
  );
});

test("a target whose deltas do not cover every vertex is refused", () => {
  assert.throws(
    () => writeGlb({
      primitives: [{ ...indexedStrip(), node: "o1.2", targets: [{ positionDeltas: new Float32Array(9) }] }],
    }, { preset: "export" }),
    /has 9 position deltas for 4 vertices/u,
  );
  assert.throws(
    () => writeGlb({
      primitives: [{
        ...indexedStrip(),
        node: "o1.2",
        targets: [{ positionDeltas: new Float32Array(12), normalDeltas: new Float32Array(9) }],
      }],
    }, { preset: "export" }),
    /has 9 normal deltas for 4 vertices/u,
  );
});

test("the render preset quantizes every attribute, so it carries no morph targets", () => {
  assert.throws(
    () => writeGlb({
      primitives: [{ ...indexedStrip(), node: "o1.1", targets: [morphTarget(5)] }],
    }, { preset: "render", encoder: MeshoptEncoder }),
    /carries no morph targets/u,
  );
});
