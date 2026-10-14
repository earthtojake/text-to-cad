/**
 * A `.cam.glb` written byte for byte as glTF says (JSON and BIN chunks), the way `cadgen cam plan` lays one out
 * (spec §10): the part as triangles, then per setup a LINES primitive of feed moves and one of rapids, each with
 * `_CAM_T` (float seconds) and `_CAM_OP` (an unsigned short operation index), node extras `{ generator, setup,
 * kind }`, and the job on the scene's extras. Positions are glTF's: metres, Y up.
 */

type Attribute = { data: Float32Array | Uint16Array; type: 'SCALAR' | 'VEC3'; componentType: number; minmax?: boolean };

const FLOAT = 5126;
const UNSIGNED_SHORT = 5123;

/** CAD mm, Z up, as glTF metres, Y up. */
export const gltfPoint = ([x, y, z]: number[]) => [x / 1000, z / 1000, -y / 1000];

export function camGlb(cam: Record<string, unknown>, { generator = 'cadgen cam' } = {}) {
  const chunks: Uint8Array[] = [];
  const accessors: object[] = [];
  const bufferViews: object[] = [];
  let offset = 0;
  const add = ({ data, type, componentType, minmax }: Attribute) => {
    const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
    const padded = new Uint8Array(Math.ceil(bytes.byteLength / 4) * 4);
    padded.set(bytes);
    bufferViews.push({ buffer: 0, byteOffset: offset, byteLength: bytes.byteLength });
    const count = type === 'VEC3' ? data.length / 3 : data.length;
    const accessor: Record<string, unknown> = { bufferView: bufferViews.length - 1, componentType, count, type };
    if (minmax) {
      const min = [Infinity, Infinity, Infinity];
      const max = [-Infinity, -Infinity, -Infinity];
      for (let i = 0; i < data.length; i += 1) { min[i % 3] = Math.min(min[i % 3], data[i]); max[i % 3] = Math.max(max[i % 3], data[i]); }
      Object.assign(accessor, { min, max });
    }
    accessors.push(accessor);
    chunks.push(padded);
    offset += padded.byteLength;
    return accessors.length - 1;
  };
  const vec3 = (points: number[][]) => add({ data: new Float32Array(points.flatMap(gltfPoint)), type: 'VEC3', componentType: FLOAT, minmax: true });
  const lines = (points: number[][], times: number[], ops: number[]) => ({ primitives: [{ mode: 1, attributes: {
    POSITION: vec3(points),
    _CAM_T: add({ data: new Float32Array(times), type: 'SCALAR', componentType: FLOAT }),
    _CAM_OP: add({ data: new Uint16Array(ops), type: 'SCALAR', componentType: UNSIGNED_SHORT }),
  } }] });
  const meshes = [
    { primitives: [{ mode: 4, attributes: { POSITION: vec3([[0, 0, 0], [10, 0, 0], [0, 10, 0]]) } }] },
    lines([[0, 0, 0], [10, 0, 0], [5, 5, -2], [5, 9, -2]], [0, 10, 40, 80], [0, 0, 1, 1]),
    lines([[10, 0, 0], [5, 5, 5]], [10, 40], [1, 1]),
  ];
  const json = {
    asset: { version: '2.0', generator },
    scene: 0,
    scenes: [{ nodes: [0, 1, 2], extras: { generator, cam } }],
    nodes: [
      { name: 'part', mesh: 0 },
      { name: 'top feed', mesh: 1, extras: { generator, setup: 'top', kind: 'feed' } },
      { name: 'top rapids', mesh: 2, extras: { generator, setup: 'top', kind: 'rapid' } },
    ],
    meshes, accessors, bufferViews, buffers: [{ byteLength: offset }],
  };
  const text = new TextEncoder().encode(JSON.stringify(json));
  const jsonChunk = new Uint8Array(Math.ceil(text.byteLength / 4) * 4).fill(0x20);
  jsonChunk.set(text);
  const total = 12 + 8 + jsonChunk.byteLength + 8 + offset;
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonChunk.byteLength, true);
  view.setUint32(16, 0x4e4f534a, true);
  out.set(jsonChunk, 20);
  let at = 20 + jsonChunk.byteLength;
  view.setUint32(at, offset, true);
  view.setUint32(at + 4, 0x004e4942, true);
  at += 8;
  for (const chunk of chunks) { out.set(chunk, at); at += chunk.byteLength; }
  return out.buffer;
}
