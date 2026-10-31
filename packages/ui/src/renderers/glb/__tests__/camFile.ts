import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { BufferAttribute, BufferGeometry, Group, LineBasicMaterial, LineSegments, Mesh } from 'three';

/*
 * Two real results, written by `cadgen cam plan` (FreeCAD plans, cadgen checks), not by hand:
 * - `ready.cam.glb`: a bracket from `bracket.step`, ready to cut on GRBL: one setup `top` (+Z) of face,
 *   pocket, profile (T1, a 6 mm flat) and drill (T2, a 6 mm drill), 2 min, two G-code files, one per tool.
 * - `fix.cam.glb`: a bridge from `bridge.step` on LinuxCNC, refused: setup `top`'s pocket (op 0) cannot
 *   reach a face under an overhang (one `reach` error), so no G-code; setup `bottom` (-Z) faces it (op 1).
 */
export type Sample = 'ready' | 'fix';

/** A sample's bytes, as an ArrayBuffer of its own. */
export function camSample(name: Sample): ArrayBuffer {
  const bytes = readFileSync(join(__dirname, `${name}.cam.glb`));
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

/** The extras a sample carries on its scene (`cam`, schema 1), read from its JSON chunk; a fresh copy each call. */
export function camExtras(name: Sample = 'ready'): Record<string, any> {
  const view = new DataView(camSample(name));
  const length = view.getUint32(12, true);
  return JSON.parse(new TextDecoder().decode(new Uint8Array(view.buffer, 20, length))).scenes[0].extras.cam;
}

/** A LINES node as GLTFLoader builds one: positions, then `_cam_t` and `_cam_op` lowercased, and the node's extras. */
export function camLines(points: number[][], times: number[], ops: number[], extras: Record<string, unknown>) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(points.flat()), 3));
  geometry.setAttribute('_cam_t', new BufferAttribute(new Float32Array(times), 1));
  geometry.setAttribute('_cam_op', new BufferAttribute(new Float32Array(ops), 1));
  const line = new LineSegments(geometry, new LineBasicMaterial());
  Object.assign(line.userData, extras);
  return line;
}

const triangle = () => {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 10, 0, 0, 0, 10, 0]), 3));
  return geometry;
};

/**
 * A scene laid out as `cadgen cam plan` writes one, in mm, with the ready sample's job (face 0–62.478 s, pocket
 * –81.717 s, profile –123.859 s, drill –129.533 s): the part, the stock box, the top setup's feed moves (three
 * segments, written out of time order: the face's first, the pocket's, then the face's second) and its rapids (one,
 * the pocket's).
 */
export function camScene({ extras = camExtras() as Record<string, unknown> | null, generator = 'cadgen cam' } = {}) {
  const root = new Group();
  if (generator) root.userData.generator = generator;
  if (extras) root.userData.cam = extras;
  const part = new Mesh(triangle());
  part.name = 'part';
  part.userData.kind = 'part';
  const stock = new Mesh(triangle());
  stock.name = 'stock';
  stock.userData.kind = 'stock';
  root.add(part, stock);
  root.add(camLines(
    [[0, 0, 0], [10, 0, 0], [5, 5, -2], [5, 9, -2], [10, 0, 0], [10, 10, 0]],
    [0, 10, 70, 80, 10, 20],
    [0, 0, 1, 1, 0, 0],
    { generator, setup: 'top', kind: 'feed' },
  ));
  root.add(camLines([[10, 10, 0], [5, 5, 5]], [63, 70], [1, 1], { generator, setup: 'top', kind: 'rapid' }));
  return root;
}
