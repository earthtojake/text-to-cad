import test from 'node:test';
import assert from 'node:assert/strict';
import { douglasPeucker, pixelDecimals, quarterPixel, snapshotPacket, snapshotPacketText } from './snapshotPacket.js';
import { snapshotPacket as exported, snapshotPacketText as exportedText } from './index.js';

// A view as a prompt carries it (`annotation/views.js`'s `promptView`): 968.27 half-height over 1160 pixels, so a
// quarter pixel is 0.417 units and one decimal says it.
const camera = { position: [1684.7442631095366, -1260.5132201786464, 725.5995354348008], target: [59.42248463398347, 16.525320052145076, -110.28023635262646],
  up: [0, 0.00001234, 0.99999999], orthographicHalfHeight: 968.2754056727326 };
const view = (label, fields = {}) => ({ camera, display: { mode: 'solid', grid: false, camera: { projection: 'orthographic' } }, width: 1600, height: 1160, ...fields, label });
const stroke = (fields = {}) => ({ id: 'ink-1', kind: 'stroke', points: [0, 0, 0, 10, 0, 0], color: '#ff2d55', view: 'view 1', touches: [], width: 3, opacity: 1, closed: false, ...fields });
const marks = packet => packet.annotation.marks;

test('a job per view: its camera and what it shows, a 3D view framed as it was, its picture by its label and size, never a path', () => {
  const posed = view('view 1', { kinematics: { arm: 1 }, jointValues: { elbow: 0.5 }, animation: { clip: 'wave', time: 1.25 }, selection: { hide: ['link:v1'] } });
  const packet = snapshotPacket({ input: '98427829-14ec-563f-a02d-9372a85cecef', type: 'model', views: [posed, view('current view', { animation: null })] });
  assert.deepEqual(Object.keys(packet), ['input', 'jobs']);
  assert.equal(packet.input, '98427829-14ec-563f-a02d-9372a85cecef');
  assert.deepEqual(Object.keys(packet.jobs[0]), ['camera', 'display', 'kinematics', 'jointValues', 'animation', 'selection', 'output', 'outputs']);
  assert.deepEqual(packet.jobs[0].output, { padding: 0, tightFrame: false });
  assert.deepEqual(packet.jobs.map(job => job.outputs), [[{ label: 'view 1', width: 1600, height: 1160 }], [{ label: 'current view', width: 1600, height: 1160 }]]);
  // What a view does not say, its job does not either.
  assert.deepEqual(Object.keys(packet.jobs[1]), ['camera', 'display', 'output', 'outputs']);
  // A drawing's view, a DXF's, a board's or a schematic's, is its plan view as the pane framed it: no 3D framing.
  for (const type of ['dxf', 'kicad_pcb', 'kicad_sch']) {
    assert.equal('output' in snapshotPacket({ input: 'panel.dxf', type, views: [view('current view')] }).jobs[0], false);
  }
  for (const type of ['step', 'xbf', 'glb', 'stl', 'threemf', 'urdf']) {
    assert.deepEqual(snapshotPacket({ input: 'part', type, views: [view('current view')] }).jobs[0].output, { padding: 0, tightFrame: false });
  }
  // No view, no packet; and the prompt module's own.
  assert.equal(snapshotPacket({ input: 'a.step', type: 'step', views: [] }), null);
  assert.equal(exported, snapshotPacket);
  assert.equal(exportedText, snapshotPacketText);
});

test("a board's references, the ink, and the parts hidden and isolated where the ink was last drawn, by their selectors in the file", () => {
  const hiding = view('view 1', { display: { mode: 'solid', grid: false, hidden: ['98427829-14ec-563f-a02d-9372a85cecef#juno/skin'], isolated: ['https://cad.example/AbCdEfGhIjKlMnOpQrSt_-#juno/arm'] } });
  const later = view('view 2', { display: { mode: 'solid', grid: false, hidden: ['"/Users/a/my #2 parts/kit.step"#kit/"lid #3"'], isolated: ['*/screw'] } });
  const annotation = { units: 'mm', marks: [stroke({ view: 'view 2' }), stroke({ id: 'ink-2', view: 'view 1' }), stroke({ id: 'ink-3', view: undefined })] };
  const packet = snapshotPacket({ input: 'kit.step', type: 'step', views: [later, hiding], annotation, references: ['#R1.1'] });
  assert.deepEqual(Object.keys(packet), ['input', 'jobs', 'references', 'annotation', 'hidden', 'isolated']);
  assert.deepEqual(packet.references, ['#R1.1']);
  // The last mark that names a view names view 1: its parts, each within the file, whatever named the file.
  assert.deepEqual([packet.hidden, packet.isolated], [['juno/skin'], ['juno/arm']]);
  // Each view's display says them the same way; a glob, or a quoted label's own `#`, is as it was.
  assert.deepEqual([packet.jobs[0].display.hidden, packet.jobs[0].display.isolated], [['kit/"lid #3"'], ['*/screw']]);
  assert.deepEqual(snapshotPacket({ input: 'kit.step', type: 'step', views: [view('view 1', { display: { hidden: ['kit/"a#b"/c', 'link:v1/object/0'] } })] }).jobs[0].display.hidden,
    ['kit/"a#b"/c', 'link:v1/object/0']);
  // No ink: no annotation, and nothing of where it was drawn; no references, no list of none.
  assert.deepEqual(Object.keys(snapshotPacket({ input: 'kit.step', type: 'step', views: [hiding], references: [] })), ['input', 'jobs']);
});

test('each number to a quarter pixel of the view it was seen in: q = 2 × half height / height / 4, d = max(0, ceil(-log10 q)) decimals', () => {
  assert.equal(quarterPixel(view('v')), 2 * camera.orthographicHalfHeight / 1160 / 4);
  assert.deepEqual([0.41733, 0.4, 0.04, 0.00025, 1, 25, 4000].map(pixelDecimals), [1, 1, 2, 4, 0, 0, 0]);
  assert.deepEqual([quarterPixel({ camera: 'front', height: 100 }), quarterPixel({ camera, height: 0 }), pixelDecimals(null), pixelDecimals(0)], [null, null, null, null]);
  // The camera: its position, target and half height to d, its up to four.
  const near = { position: [1.234567, 2.345678, 3.456789], target: [0.1234567, 0, -0.98766], up: [0.123456, 0, 0.987654], orthographicHalfHeight: 0.5555555 };
  const packet = snapshotPacket({ input: 'a.step', type: 'step', views: [view('view 1'), view('current view', { camera: near, height: 1000 })],
    annotation: { units: 'mm', marks: [
      stroke({ points: [1.23456, 2.34567, 3.45678, 100.98765, 2.34567, 3.45678], widths: [1, 0.954321] }),
      stroke({ id: 'ink-2', view: 'current view', points: [1.23456, 2.34567, 3.45678, 1.98766, 2.34567, 3.45678] }),
      stroke({ id: 'ink-3', view: 'a view no job has', points: [1.23456, 2.34567, 3.45678, 1.98766, 2.34567, 3.45678] }),
    ] } });
  assert.deepEqual(packet.jobs[0].camera, { position: [1684.7, -1260.5, 725.6], target: [59.4, 16.5, -110.3], up: [0, 0, 1], orthographicHalfHeight: 968.3 });
  // Zoomed in, a quarter pixel is 0.00014 units: four decimals.
  assert.deepEqual(packet.jobs[1].camera, { position: [1.2346, 2.3457, 3.4568], target: [0.1235, 0, -0.9877], up: [0.1235, 0, 0.9877], orthographicHalfHeight: 0.5556 });
  // A mark's points to the decimals of its view: its own label's job, else the last; a stroke's widths to two.
  assert.deepEqual(marks(packet).map(mark => mark.points), [[1.2, 2.3, 3.5, 101, 2.3, 3.5], [1.2346, 2.3457, 3.4568, 1.9877, 2.3457, 3.4568],
    [1.2346, 2.3457, 3.4568, 1.9877, 2.3457, 3.4568]]);
  assert.deepEqual(marks(packet)[0].widths, [1, 0.95]);
  // Zoomed out past a unit a quarter pixel, whole numbers.
  const far = snapshotPacket({ input: 'a.step', type: 'step', views: [view('view 1', { camera: { ...camera, orthographicHalfHeight: 60000 }, height: 1000 })],
    annotation: { units: 'mm', marks: [stroke({ points: [1234.56, -0.4, 7.5, 2345.67, 0.6, -7.5] })] } });
  assert.deepEqual([far.jobs[0].camera.position, marks(far)[0].points], [[1685, -1261, 726], [1235, -0, 8, 2346, 1, -8]]);
  assert.equal(snapshotPacketText(far).includes('-0,'), false);
});

test("a mark says what a reader outside the page needs: no id, opacity only when not 1, closed only when true, an area its outline", () => {
  const area = { id: 'ink-a', kind: 'area', points: [0, 0, 0, 4, 0, 0, 4, 4, 0, 0, 4, 0, 2, 2, 0], outline: 4, triangles: [0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4], color: '#00ff00', view: 'view 1' };
  const text = { id: 'ink-t', kind: 'text', points: [0.04, 0, 0, 5.06, 0, 0, 5.06, 1.94, 0, 0.04, 1.94, 0], color: '#000000', text: 'here', fontPx: 14, view: 'view 1', group: 'g1' };
  const packet = snapshotPacket({ input: 'a.step', type: 'step', views: [view('view 1')], annotation: { units: 'mm', marks: [
    stroke(), stroke({ id: 'ink-2', opacity: 0.4, closed: true, points: [0, 0, 0, 10, 0, 0, 10, 10, 0] }), area, text] } });
  assert.deepEqual(marks(packet), [
    { kind: 'stroke', points: [0, 0, 0, 10, 0, 0], color: '#ff2d55', view: 'view 1', touches: [], width: 3 },
    { kind: 'stroke', points: [0, 0, 0, 10, 0, 0, 10, 10, 0], color: '#ff2d55', view: 'view 1', touches: [], width: 3, opacity: 0.4, closed: true },
    // An area's points are its outline alone, which the renderer reads as all of them.
    { kind: 'area', points: [0, 0, 0, 4, 0, 0, 4, 4, 0, 0, 4, 0], color: '#00ff00', view: 'view 1' },
    // A text mark as it was: its four corners.
    { kind: 'text', points: [0, 0, 0, 5.1, 0, 0, 5.1, 1.9, 0, 0, 1.9, 0], color: '#000000', text: 'here', fontPx: 14, view: 'view 1', group: 'g1' },
  ]);
  assert.equal(packet.annotation.units, 'mm');
});

test("what a mark touches is the selectors it was drawn over in the file, once each, as found; a touch with no ref names nothing", () => {
  const touches = [
    { part: 'i130', ref: '98427829-14ec-563f-a02d-9372a85cecef#juno/shoulder_pod_left/e:actuator_solids.can_bnpmie~866c77ce3d1b' },
    { part: 'i34', ref: 'https://cad.example/AbCdEfGhIjKlMnOpQrSt_-#head_shell/f:build_head.helmet~5df450b1dd03' },
    { part: 'i34' },
    { part: 'i130', ref: '/work/juno.step#juno/shoulder_pod_left/e:actuator_solids.can_bnpmie~866c77ce3d1b' },
    { part: 'i7', ref: '"/Users/a/my #2 parts/kit.step"#kit/"lid #3"/face 2' },
  ];
  const packet = snapshotPacket({ input: 'a.step', type: 'step', views: [view('view 1')], annotation: { units: 'mm', marks: [stroke({ touches })] } });
  assert.deepEqual(marks(packet)[0].touches, ['juno/shoulder_pod_left/e:actuator_solids.can_bnpmie~866c77ce3d1b',
    'head_shell/f:build_head.helmet~5df450b1dd03', 'kit/"lid #3"/face 2']);
});

test('Douglas–Peucker keeps a line within its tolerance: its ends, and what strays past it, farthest first', () => {
  const flat = points => points.flat();
  // A straight line, however many points, is its ends; a point off it by more than the tolerance stays.
  assert.deepEqual(douglasPeucker(flat(Array.from({ length: 50 }, (_, index) => [index, 0.001 * (index % 2), 0])), 0.01), [0, 49]);
  assert.deepEqual(douglasPeucker(flat([[0, 0, 0], [5, 0.2, 0], [10, 0, 0]]), 0.1), [0, 1, 2]);
  assert.deepEqual(douglasPeucker(flat([[0, 0, 0], [5, 0.2, 0], [10, 0, 0]]), 0.25), [0, 2]);
  // In 3D: a point off the line in z alone counts the same.
  assert.deepEqual(douglasPeucker(flat([[0, 0, 0], [5, 0, 0.3], [10, 0, 0]]), 0.25), [0, 1, 2]);
  // Measured to the segment between the kept points, so a stroke that runs on past its end and back keeps the turn.
  assert.deepEqual(douglasPeucker(flat([[0, 0, 0], [10, 0, 0], [14, 0, 0], [12, 0, 0]]), 0.5), [0, 2, 3]);
  // A loop's ends are one point: it is measured from its start, its farthest point first.
  const square = flat([[0, 0, 0], [5, 0, 0], [10, 0, 0], [10, 5, 0], [10, 10, 0], [5, 10, 0], [0, 10, 0], [0, 5, 0], [0, 0, 0]]);
  assert.deepEqual(douglasPeucker(square, 0.5), [0, 2, 4, 6, 8]);
  assert.deepEqual(douglasPeucker(flat([[1, 1, 1], [1, 1, 1], [1, 1, 1]]), 0.5), [0, 2]);
  assert.deepEqual([douglasPeucker([], 1), douglasPeucker([0, 0, 0], 1), douglasPeucker([0, 0, 0, 1, 1, 1], 1)], [[], [0], [0, 1]]);
  // Every point it drops lies within the tolerance of the line it keeps (a seeded random walk).
  let seed = 7;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const walk = [[0, 0, 0]];
  for (let index = 1; index < 400; index += 1) walk.push(walk.at(-1).map(value => value + random() - 0.5));
  const kept = douglasPeucker(flat(walk), 0.3);
  const toSegment = (p, a, b) => {
    const ab = b.map((value, axis) => value - a[axis]), ap = p.map((value, axis) => value - a[axis]);
    const length2 = ab.reduce((sum, value) => sum + value * value, 0);
    const t = length2 ? Math.min(1, Math.max(0, ap.reduce((sum, value, axis) => sum + value * ab[axis], 0) / length2)) : 0;
    return Math.hypot(...ap.map((value, axis) => value - t * ab[axis]));
  };
  for (let span = 0; span + 1 < kept.length; span += 1) {
    for (let index = kept[span] + 1; index < kept[span + 1]; index += 1) assert.ok(toSegment(walk[index], walk[kept[span]], walk[kept[span + 1]]) <= 0.3);
  }
  assert.ok(kept.length > 2 && kept.length < walk.length);
});

test("a stroke goes within half a pixel of its view, each point it keeps with its width; a loop drawn round keeps its round", () => {
  // A circle of 141 points 100 units across in the view whose quarter pixel is 0.417: half a pixel is 0.83 units.
  const round = Array.from({ length: 141 }, (_, index) => {
    const angle = (2 * Math.PI * index) / 140;
    return [Math.round(50 * Math.cos(angle) * 1e4) / 1e4 + 0, 188.0811, Math.round(50 * Math.sin(angle) * 1e4) / 1e4 + 0];
  });
  const widths = round.map((_, index) => 1 + index / 1000);
  const line = Array.from({ length: 47 }, (_, index) => [index * 10, 0.05 * Math.sin(index), 0]);
  const packet = snapshotPacket({ input: 'a.step', type: 'step', views: [view('view 1')], annotation: { units: 'mm', marks: [
    stroke({ points: round.flat(), widths }), stroke({ id: 'ink-2', points: line.flat(), widths: line.map(() => 1) })] } });
  const [circle, straight] = marks(packet);
  const count = circle.points.length / 3;
  assert.ok(count > 8 && count < 141, `${count} points`);
  assert.deepEqual(circle.points.slice(0, 3), circle.points.slice(-3));
  assert.equal(circle.widths.length, count);
  // Each kept point keeps its own width: the widths a point's index gave it, to two decimals.
  const index = round.findIndex(([x, , z]) => Math.abs(x - circle.points[3]) < 0.06 && Math.abs(z - circle.points[5]) < 0.06);
  assert.equal(circle.widths[1], Number(widths[index].toFixed(2)));
  assert.deepEqual([straight.points, straight.widths], [[0, 0, 0, 460, 0, 0], [1, 1]]);
});

test("the same views and ink give the same packet whatever the file's address, and its text carries no quote a shell's single quotes end at", () => {
  const annotation = { units: 'mm', marks: [
    { id: 'ink-t', kind: 'text', points: [0, 0, 0, 5, 0, 0, 5, 2, 0, 0, 2, 0], color: '#000000', text: "Jake's lid isn't ‘right’", fontPx: 14, view: 'view 1' },
    stroke({ touches: [{ part: 'i3', ref: `98427829-14ec-563f-a02d-9372a85cecef#"Jake's bracket"/f:base.make_box1.6` }] }),
  ] };
  const views = [view('view 1', { display: { mode: 'solid', grid: false, hidden: ["98427829-14ec-563f-a02d-9372a85cecef#\"O'Brien's arm\""] } })];
  const local = snapshotPacket({ input: '98427829-14ec-563f-a02d-9372a85cecef', type: 'model', views, annotation });
  const shared = snapshotPacket({ input: 'https://cad.example/AbCdEfGhIjKlMnOpQrSt_-', type: 'model', views, annotation });
  assert.deepEqual({ ...local, input: shared.input }, shared);
  const text = snapshotPacketText(local);
  assert.equal(/['‘-‛]/.test(text), false);
  assert.ok(text.includes('Jake\\u0027s lid isn\\u0027t \\u2018right\\u2019'));
  // Compact, and the same values when read back.
  assert.equal(text, JSON.stringify(local).replace(/['‘-‛]/g, quote => `\\u${quote.charCodeAt(0).toString(16).padStart(4, '0')}`));
  assert.equal(text.includes(' "') || text.includes('": '), false);
  assert.deepEqual(JSON.parse(text), local);
  assert.deepEqual([JSON.parse(text).annotation.marks[1].touches, JSON.parse(text).hidden], [[`"Jake's bracket"/f:base.make_box1.6`], [`"O'Brien's arm"`]]);
});
