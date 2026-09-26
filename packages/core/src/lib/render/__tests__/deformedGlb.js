// A tiny GLB whose rest shape is NOT its vertex buffer: a square bar 2 units tall (glTF,
// Y up) whose top ring is skinned to a joint that rests turned 90 degrees about Z from where
// it was bound, and whose bottom ring a morph target, weighted 1 by default, pulls down by
// half a unit. Drawn as three draws it (skin and morph on the GPU) the bar is an L:
//
//   x in [-1, 0.1], y in [-0.5, 1.1], z in [-0.1, 0.1]     (glTF units)
//
// Read as a plain vertex buffer it is a straight bar, x and z in [-0.1, 0.1], y in [0, 2].
// That is the case a flattened copy of a GLB gets wrong and the native scene does not.

const RING = [[-0.1, -0.1], [0.1, -0.1], [0.1, 0.1], [-0.1, 0.1]];
export const DEFORMED_EXTENT = Object.freeze({ min: [-1, -0.5, -0.1], max: [0.1, 1.1, 0.1] });
export const BIND_EXTENT = Object.freeze({ min: [-0.1, 0, -0.1], max: [0.1, 2, 0.1] });

function barIndices() {
  const indices = [];
  for (let ring = 0; ring < 2; ring += 1) {
    for (let side = 0; side < 4; side += 1) {
      const a = ring * 4 + side, b = ring * 4 + ((side + 1) % 4), c = a + 4, d = b + 4;
      indices.push(a, b, d, a, d, c);
    }
  }
  indices.push(0, 2, 1, 0, 3, 2, 8, 9, 10, 8, 10, 11);
  return indices;
}

/**
 * @param {{ skinned?: boolean, morphWeight?: number | null, color?: [number, number, number] }} [options]
 *   `skinned: false` and `morphWeight: null` write the plain bar.
 * @returns {ArrayBuffer}
 */
export function deformedGlb({ skinned = true, morphWeight = 1, color = [0.18, 0.5, 0.82] } = {}) {
  const positions = [0, 1, 2].flatMap(level => RING.flatMap(([x, z]) => [x, level, z]));
  const chunks = [];
  const bufferViews = [];
  const accessors = [];
  let length = 0;
  const add = (typed, accessor) => {
    const bytes = new Uint8Array(typed.buffer, typed.byteOffset, typed.byteLength);
    const padded = new Uint8Array(Math.ceil(bytes.length / 4) * 4);
    padded.set(bytes);
    bufferViews.push({ buffer: 0, byteOffset: length, byteLength: bytes.length });
    chunks.push(padded);
    length += padded.length;
    accessors.push({ bufferView: bufferViews.length - 1, ...accessor });
    return accessors.length - 1;
  };
  const extent = values => [0, 1, 2].map(axis => values.filter((_, index) => index % 3 === axis));
  const vec3 = (values) => {
    const axes = extent(values);
    return { componentType: 5126, count: values.length / 3, type: "VEC3",
      min: axes.map(axis => Math.min(...axis)), max: axes.map(axis => Math.max(...axis)) };
  };
  const primitive = { attributes: { POSITION: add(new Float32Array(positions), vec3(positions)) } };
  const indices = barIndices();
  primitive.indices = add(new Uint16Array(indices), { componentType: 5123, count: indices.length, type: "SCALAR" });
  primitive.material = 0;
  const mesh = { name: "bar", primitives: [primitive] };
  if (morphWeight !== null) {
    const deltas = positions.map((_, index) => (index < 12 && index % 3 === 1 ? -0.5 : 0));
    primitive.targets = [{ POSITION: add(new Float32Array(deltas), vec3(deltas)) }];
    mesh.weights = [morphWeight];
  }
  const nodes = [{ name: "bar", mesh: 0 }];
  const document = {
    asset: { version: "2.0", generator: "deformedGlb test fixture" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes,
    meshes: [mesh],
    materials: [{ name: "blue", pbrMetallicRoughness: { baseColorFactor: [...color, 1], metallicFactor: 0, roughnessFactor: 0.6 },
      extras: { cadSourceColor: true } }],
    accessors,
    bufferViews,
    buffers: [{ byteLength: 0 }]
  };
  if (skinned) {
    const joints = positions.map((_, index) => index).filter(index => index % 3 === 0)
      .flatMap(index => [index >= 24 ? 1 : 0, 0, 0, 0]);
    primitive.attributes.JOINTS_0 = add(new Uint8Array(joints), { componentType: 5121, count: 12, type: "VEC4" });
    primitive.attributes.WEIGHTS_0 = add(new Float32Array(Array.from({ length: 12 }, () => [1, 0, 0, 0]).flat()),
      { componentType: 5126, count: 12, type: "VEC4" });
    // Column-major: the root joint is bound at the origin, the tip one unit up and unturned.
    const inverseBind = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1];
    const ibm = add(new Float32Array(inverseBind), { componentType: 5126, count: 2, type: "MAT4" });
    nodes[0].skin = 0;
    nodes.push({ name: "root_joint", children: [2] },
      { name: "tip_joint", translation: [0, 1, 0], rotation: [0, 0, Math.SQRT1_2, Math.SQRT1_2] });
    document.scenes[0].nodes.push(1);
    document.skins = [{ joints: [1, 2], inverseBindMatrices: ibm, skeleton: 1 }];
  }
  document.buffers[0].byteLength = length;
  const json = new TextEncoder().encode(JSON.stringify(document));
  const jsonPadded = new Uint8Array(Math.ceil(json.length / 4) * 4).fill(0x20);
  jsonPadded.set(json);
  const total = 12 + 8 + jsonPadded.length + 8 + length;
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonPadded.length, true);
  view.setUint32(16, 0x4e4f534a, true);
  out.set(jsonPadded, 20);
  let offset = 20 + jsonPadded.length;
  view.setUint32(offset, length, true);
  view.setUint32(offset + 4, 0x004e4942, true);
  offset += 8;
  for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.length; }
  return out.buffer;
}
