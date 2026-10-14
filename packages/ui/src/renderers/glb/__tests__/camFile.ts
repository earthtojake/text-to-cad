import { BufferAttribute, BufferGeometry, Group, LineBasicMaterial, LineSegments, Mesh } from 'three';

/** The extras `cadgen cam plan` writes on the scene (spec §10, schema 1): one setup, a face and a pocket, one error. */
export const camExtras = () => ({
  schema: 1,
  verdict: { status: 'fix', headline: '1 to fix', errors: 1, warnings: 2, gcode: 'G-code not written: fix 1 error first' },
  machine: { kind: 'mill', post: 'grbl' },
  material: 'aluminum-6061',
  document: 'part.step',
  setups: [{ id: 'top', plain: 'Top', time_s: 90, orientation: '+Z', operations: [
    { index: 0, op: 'face', plain: 'Face', tool: 'T1', tool_plain: '6 mm flat', rpm: 12000, feed_mm_min: 1440, time_s: 30, t0: 0, t1: 30,
      summary: 'Face the stock top with T1 6 mm flat, 30 s', limits: [] },
    { index: 1, op: 'pocket', plain: 'Pocket', tool: 'T3', tool_plain: '4 mm ball', rpm: 15000, feed_mm_min: 900, time_s: 60, t0: 30, t1: 90,
      summary: 'Pocket #o1.f12 with T3 4 mm ball, 60 s', faces: ['#o1.f12', '#o1.f13'], limits: ['lite: engagement capped'] },
  ] }],
  findings: [
    { check: 'corner_radius', level: 'warning', message: 'An inside corner is tighter than the tool', operation: 1, at: [1, 2, 3] },
    { check: 'reach', level: 'error', message: 'Tool too long for this pocket', operation: 1, at: [4, 5, 6] },
    { check: 'material_left', level: 'warning', message: 'Material left on the floor', operation: 1 },
  ],
  adapted: [{ step: 'stock_grid', note: 'stock grid 0.5 mm -> 1 mm' }],
  posts: [{ setup: 'top', file: 'part.top.nc', post: 'grbl' }],
  duration_s: 90,
});

/** A LINES node as GLTFLoader builds one: positions, then `_cam_t` and `_cam_op` lowercased, and the node's extras. */
export function camLines(points: number[][], times: number[], ops: number[] | null, extras: Record<string, unknown>, { upper = false } = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(points.flat()), 3));
  geometry.setAttribute(upper ? '_CAM_T' : '_cam_t', new BufferAttribute(new Float32Array(times), 1));
  if (ops) geometry.setAttribute(upper ? '_CAM_OP' : '_cam_op', new BufferAttribute(new Float32Array(ops), 1));
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
 * A scene as `cadgen cam plan` writes one, in mm: the part, the stock after the job, the top setup's feed moves
 * (three segments, written out of time order: the face's two, then the pocket's one) and its rapids (one).
 */
export function camScene({ extras = camExtras() as Record<string, unknown> | null, generator = 'cadgen cam' } = {}) {
  const root = new Group();
  if (generator) root.userData.generator = generator;
  if (extras) root.userData.cam = extras;
  const part = new Mesh(triangle());
  part.name = 'part';
  const stock = new Mesh(triangle());
  stock.userData.kind = 'stock';
  root.add(part, stock);
  root.add(camLines(
    [[0, 0, 0], [10, 0, 0], [5, 5, -2], [5, 9, -2], [10, 0, 0], [10, 10, 0]],
    [0, 10, 40, 80, 10, 20],
    [0, 0, 1, 1, 0, 0],
    { generator, setup: 'top', kind: 'feed' },
  ));
  root.add(camLines([[10, 10, 0], [5, 5, 5]], [20, 30], [1, 1], { generator, setup: 'top', kind: 'rapid' }));
  return root;
}
