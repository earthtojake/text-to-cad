import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { Line2 } from 'three/examples/jsm/lines/Line2.js';
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';

import { normalizeAnnotation } from '@text-to-cad/core/common/annotation.js';
import { annotationDocumentOf, levelOf, mountAnnotations, projectAnnotations } from './annotation3d.js';

/**
 * Annotate's ink in 3D: it lies on the surface it is drawn on. A mark's level is the plane of the surface it
 * starts on; On surface drops each point onto the visible surface under it, On plane keeps it on the level,
 * and off the model both carry on at the level. Always in model coordinates.
 */

// A 20 × 20 × 2 slab, part "slab" (top face at z = 0), and a 2 × 2 post, part "post", standing on it
// to z = 10. Top view (default): an orthographic camera looking straight down, one screen pixel one unit,
// screen pixel (x, y) is world (x − 50, 50 − y). Oblique view: the same lens from (0, −60, 60) looking at the
// origin, z up, and a cylinder part "cyl" (radius 4, axis z, z 0 to 10) at x = 6 beside the post.
function rig({ oblique = false } = {}) {
  const scene = new THREE.Scene();
  const modelGroup = new THREE.Group();
  scene.add(modelGroup);
  const part = (id, geometry, [x, y, z]) => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
    mesh.userData.partId = id;
    mesh.position.set(x, y, z);
    modelGroup.add(mesh);
    return mesh;
  };
  const slab = part('slab', new THREE.BoxGeometry(20, 20, 2), [0, 0, -1]);
  const post = part('post', new THREE.BoxGeometry(2, 2, 10), [0, 0, 5]);
  if (oblique) part('cyl', new THREE.CylinderGeometry(4, 4, 10, 64).rotateX(Math.PI / 2), [6, 0, 5]);
  const camera = new THREE.OrthographicCamera(-50, 50, 50, -50, 0.1, 500);
  if (oblique) { camera.up.set(0, 0, 1); camera.position.set(0, -60, 60); } else camera.position.set(0, 0, 100);
  camera.lookAt(0, 0, 0);
  scene.add(camera);
  scene.updateMatrixWorld(true);
  const renders = { count: 0 };
  const runtime = { THREE, scene, camera, modelGroup, controls: { target: new THREE.Vector3(0, 0, -30) }, modelRadius: 10,
    activeClipPlanes: [], Line2, LineGeometry, LineMaterial, requestRender() { renders.count += 1; } };
  return { runtime, slab, post, renders };
}
const size = { width: 100, height: 100 };
const stroke = (id, points) => ({ kind: 'stroke', id, points: points.map(([x, y]) => ({ x, y })), closed: false, color: '#ff0000', width: 2, opacity: 1 });
const along = (from, to, step = 1) => Array.from({ length: Math.round(Math.abs(to - from) / step) + 1 }, (_, index) => from + Math.sign(to - from) * index * step);
const worldOf = item => Array.from({ length: item.points.length / 3 }, (_, index) => new THREE.Vector3().fromArray(item.points, index * 3));
const rounded = item => worldOf(item).map(point => [point.x, point.y, point.z].map(value => Math.round(value * 1000) / 1000));
const round3 = values => (values.toArray ? values.toArray() : values).map(value => Math.round(value * 1000) / 1000 + 0);
const outline = points => points.map(([x, y]) => ({ x, y }));
const heights = item => rounded(item).map(([, , z]) => z);
// Where a world point falls on the screen, in the viewport's pixels.
const onScreen = (runtime, [x, y, z]) => {
  const ndc = new THREE.Vector3(x, y, z).project(runtime.camera);
  return [(ndc.x + 1) / 2 * size.width, (1 - ndc.y) / 2 * size.height];
};
// An ink point is lifted two screen pixels toward the eye along the view: the oblique rig's, for taking it off.
const liftOf = runtime => runtime.camera.getWorldDirection(new THREE.Vector3()).multiplyScalar(-2);
const unlifted = (runtime, item) => worldOf(item).map(point => point.sub(liftOf(runtime)));
const close = (actual, expected, message, tolerance = 0.02) => assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: ${actual} is not ${expected}`);

test('a mark\'s level is the plane of the surface it starts on, seen from any angle: a flat face\'s own plane, a curved face\'s tangent plane', () => {
  const top = rig().runtime;
  // The slab's top, the post's top: the plane of whatever is under the start, facing the eye.
  assert.deepEqual([round3(levelOf(top, { x: 45, y: 55 }, size).point), round3(levelOf(top, { x: 45, y: 55 }, size).normal)], [[-5, -5, 0], [0, 0, 1]]);
  assert.deepEqual(round3(levelOf(top, { x: 50.5, y: 49.5 }, size).point), [0.5, 0.5, 10]);
  // Oblique, the normal is still the surface's, not the view's: the slab's top is the z = 0 plane.
  const { runtime } = rig({ oblique: true });
  const [slabX, slabY] = onScreen(runtime, [-5, 2, 0]);
  const flat = levelOf(runtime, { x: slabX, y: slabY }, size);
  assert.deepEqual([round3(flat.point), round3(flat.normal)], [[-5, 2, 0], [0, 0, 1]]);
  // The cylinder's side: the tangent plane at the point, its normal the radial direction there.
  const [cylX, cylY] = onScreen(runtime, [6 + 4 * Math.sin(0.4), -4 * Math.cos(0.4), 5]);
  const side = levelOf(runtime, { x: cylX, y: cylY }, size);
  const radial = new THREE.Vector3(side.point.x - 6, side.point.y, 0).normalize();
  close(side.point.clone().setZ(0).sub(new THREE.Vector3(6, 0, 0)).length(), 4, 'on the wall');
  assert.ok(side.normal.dot(radial) > 0.999, `normal ${round3(side.normal.toArray())} is not radial ${round3(radial.toArray())}`);
});

test('a level met nearly edge-on by the view is replaced by the plane facing the view through the same point', () => {
  const { runtime } = rig();
  runtime.camera.position.set(0, -60, 4.2);
  runtime.camera.lookAt(0, 0, 0);
  runtime.scene.updateMatrixWorld(true);
  const [x, y] = onScreen(runtime, [0, 0, 0]);
  const level = levelOf(runtime, { x, y }, size, { cpuBudget: 100 });
  const view = runtime.camera.getWorldDirection(new THREE.Vector3());
  close(level.normal.dot(view), -1, 'facing the view');
  close(Math.abs(level.point.x) + Math.abs(level.point.z), 0, 'through the point under the pen', 0.5);
});

test('started over nothing, the level is the plane of the visible surface nearest to the start on the screen', () => {
  const { runtime } = rig();
  // Beside the slab (x 30): nearest is the slab's top.
  assert.deepEqual([round3(levelOf(runtime, { x: 80, y: 50 }, size, { cpuBudget: 100 }).point)[2], round3(levelOf(runtime, { x: 80, y: 50 }, size, { cpuBudget: 100 }).normal)], [0, [0, 0, 1]]);
  // Oblique, just above the post's top edge and beyond the slab's silhouette: the post is the nearest surface.
  const oblique = rig({ oblique: true }).runtime;
  const [x, y] = onScreen(oblique, [0, 1, 10]);
  const near = levelOf(oblique, { x, y: y - 14 }, size, { cpuBudget: 100 });
  assert.deepEqual([round3(near.point)[2], round3(near.normal)], [10, [0, 0, 1]]);
  // The slab's silhouette, the other way, picks the slab.
  const [sx, sy] = onScreen(oblique, [-8, 10, 0]);
  assert.equal(round3(levelOf(oblique, { x: sx, y: sy - 6 }, size, { cpuBudget: 100 }).point)[2], 0);
});

test('a window that shows nothing takes the plane of the surface nearest to it on the screen; with no model drawn, the plane through the origin facing the view', () => {
  const { runtime, slab } = rig();
  // Panned right: the window shows world x 20 to 120. Nearest to it is the slab's edge (top z 0),
  // not the post (top z 10), which is the model's nearest surface.
  runtime.camera.position.set(70, 0, 100);
  runtime.scene.updateMatrixWorld(true);
  const start = { x: 70, y: 30 };
  const level = levelOf(runtime, start, size, { cpuBudget: 100 });
  assert.deepEqual([round3(level.point)[2], round3(level.normal)], [0, [0, 0, 1]]);
  // A hidden part is not drawn, so does not count: the post alone now, at its own top.
  slab.visible = false;
  assert.equal(round3(levelOf(runtime, start, size, { cpuBudget: 100 }).point)[2], 10);
  // Nothing drawn at all: the plane through the origin, facing the view.
  runtime.modelGroup.visible = false;
  const bare = levelOf(runtime, start, size);
  assert.deepEqual([round3(bare.point), round3(bare.normal)], [[0, 0, 0], [0, 0, 1]]);
  runtime.modelGroup.clear();
  const [mark] = projectAnnotations(runtime, [stroke('bare', [[5, 5], [10, 5]])], size);
  close(Math.max(...heights(mark).map(Math.abs)), 2, 'on the origin plane, lifted');
  assert.ok(heights(mark).every(z => z === heights(mark)[0]));
});

test('started on the slab and run off its edge in an oblique view, ink carries on at the slab\'s level, not on a plane square to the screen', () => {
  const { runtime } = rig({ oblique: true });
  // From the slab\'s top out past its back edge (y 10) into the air: world (-5, 2, 0) to (-5, 30, 0).
  const mark = stroke('off', [onScreen(runtime, [-5, 2, 0]), onScreen(runtime, [-5, 30, 0])]);
  const [surface] = projectAnnotations(runtime, [mark], size, { placement: 'surface', cpuBudget: 100 });
  const [plane] = projectAnnotations(runtime, [mark], size, { placement: 'plane', cpuBudget: 100 });
  const lift = liftOf(runtime);
  for (const item of [surface, plane]) {
    assert.ok(item.points.length / 3 > 4, 'the line is split into pieces');
    // Every point at the z = 0 plane, lifted toward the eye (on a screen-parallel plane z would climb with y).
    for (const [index, point] of worldOf(item).entries()) assert.ok(point.z >= lift.z - 1e-3 && point.z <= lift.z + 1.6, `${item.id} point ${index}: z ${point.z}`);
  }
  // Over the slab On surface stands a hair off it (the stroke\'s reach); past it, and On plane everywhere, exactly at the level.
  assert.ok(worldOf(surface).filter(point => point.y - lift.y > 12).every(point => Math.abs(point.z - lift.z) < 1e-3));
  assert.ok(worldOf(plane).every(point => Math.abs(point.z - lift.z) < 1e-3));
  const ys = worldOf(plane).map(point => point.y - lift.y);
  close(ys[0], 2, 'starts on the slab', 0.05);
  close(ys.at(-1), 30, 'ends in the air, at the same level', 0.05);
});

test('on a curved face the two modes part: On surface follows it, On plane stays on the tangent plane where the mark started', () => {
  const { runtime } = rig({ oblique: true });
  const around = angle => [6 + 4 * Math.sin(angle), -4 * Math.cos(angle), 6];
  const mark = { ...stroke('across', [onScreen(runtime, around(-0.9)), onScreen(runtime, around(0.9))]), width: 1 };
  const [surface] = projectAnnotations(runtime, [mark], size, { placement: 'surface', cpuBudget: 100 });
  const [plane] = projectAnnotations(runtime, [mark], size, { placement: 'plane', cpuBudget: 100 });
  // On surface: every point is at the cylinder's radius from its axis (a hair in front of the wall at worst).
  // (the stroke stands off it by its reach, a pixel or two toward the eye)
  const radii = unlifted(runtime, surface).map(point => Math.hypot(point.x - 6, point.y));
  assert.ok(radii.every(radius => radius > 3.9 && radius < 6), `from the axis: ${radii}`);
  // On plane: every point on the tangent plane at the start (its normal the start's, the radial direction).
  const level = levelOf(runtime, { x: mark.points[0].x, y: mark.points[0].y }, size);
  const points = unlifted(runtime, plane);
  for (const point of points) close(point.clone().sub(level.point).dot(level.normal), 0, 'off the tangent plane', 1e-3);
  assert.ok(points.at(-1).clone().sub(new THREE.Vector3(6, 0, 0)).setZ(0).length() > 8, 'flat across the curve, so well off the wall at the far end');
});

test('On surface steps across faces and onto a part; On plane stays on the level through it', () => {
  const { runtime } = rig({ oblique: true });
  // A line along the screen from the slab, behind the post\'s front face: it meets the post.
  const [startX, startY] = onScreen(runtime, [-9, 0.5, 0]);
  const mark = stroke('through', [[startX, startY], [startX + 18, startY]]);
  const [surface] = projectAnnotations(runtime, [mark], size, { placement: 'surface', cpuBudget: 100 });
  const [plane] = projectAnnotations(runtime, [mark], size, { placement: 'plane', cpuBudget: 100 });
  const lift = liftOf(runtime);
  assert.ok(heights(plane).every(z => Math.abs(z - lift.z) < 1e-3), `on the slab\'s level: ${heights(plane)}`);
  assert.ok(Math.max(...heights(surface)) > lift.z + 0.5, `up onto the post: ${heights(surface)}`);
});

test('text is a card facing the view at the level\'s depth under its anchor corner, in both modes; a fill takes the mode too', () => {
  const { runtime } = rig();
  const card = (id, corners) => ({ kind: 'text', id, corners: outline(corners), text: 'hi', color: '#000', fontPx: 16 });
  for (const placement of ['surface', 'plane']) {
    const [onSlab, onPost, bare] = projectAnnotations(runtime, [
      card('slab', [[42, 52], [48, 52], [48, 58], [42, 58]]),
      // Anchored on the post\'s top, running off it onto the slab: all at the post\'s level.
      card('post', [[49.5, 49.5], [58, 49.5], [58, 56], [49.5, 56]]),
      // Anchored over nothing: the slab beside it.
      card('bare', [[80, 52], [90, 52], [90, 58], [80, 58]]),
    ], size, { placement, cpuBudget: 100 });
    assert.ok(heights(onSlab).every(z => z === 8), `${placement}: eight pixels off the slab: ${heights(onSlab)}`);
    assert.ok(heights(onPost).every(z => z === 18), `${placement}: ${heights(onPost)}`);
    assert.ok(heights(bare).every(z => z === 8), `${placement}: ${heights(bare)}`);
  }
  // A fill started on the slab and reaching the post: On surface it climbs onto the post, On plane it stays on the level.
  const area = { kind: 'area', id: 'fill', outline: outline([[42, 42], [52, 42], [52, 52]]), color: '#0f0', opacity: 0.35 };
  const [onSurface] = projectAnnotations(runtime, [area], size, { placement: 'surface' });
  const [onPlane] = projectAnnotations(runtime, [area], size, { placement: 'plane' });
  assert.ok(onSurface.triangles.length >= 3 && onSurface.outline === 3);
  assert.ok(heights(onSurface).includes(2) && heights(onSurface).includes(12), `slab and post: ${heights(onSurface)}`);
  assert.ok(heights(onPlane).every(z => z === 2), `on the level: ${heights(onPlane)}`);
  // A fill of a shape that lies on a plane of its own is given that plane.
  const [given] = projectAnnotations(runtime, [area], size, { placement: 'plane', level: { point: [0, 0, 5], normal: [0, 0, 1] } });
  assert.ok(heights(given).every(z => z === 7), `on the given plane, lifted: ${heights(given)}`);
});

test('a two-point line is split into pieces of a few pixels in both modes, the pen\'s widths with it', () => {
  const { runtime } = rig();
  const marks = [stroke('line', [[45, 55], [5, 55]]), { ...stroke('pen', [[45, 57], [5, 57]]), widths: [1, 0.5] }];
  const [line, pen] = projectAnnotations(runtime, marks, size, { placement: 'surface', cpuBudget: 100 });
  // From the slab (z 2, lifted) out into the air: the slab\'s level, never anything else.
  assert.deepEqual(heights(line), [2, 2, 2, 2, 2, 2, 2, 2]);
  assert.equal(pen.widths.length, pen.points.length / 3);
  assert.deepEqual([pen.widths[0], pen.widths.at(-1)], [1, 0.5]);
  assert.equal(projectAnnotations(runtime, [marks[0]], size, { placement: 'plane' })[0].points.length / 3, 8);
});

test('what a mark touches: each face or edge the renderer names under it, most first, with its part', () => {
  const { runtime } = rig();
  const touchesAt = ({ x }) => (x < 45 ? [{ part: 'slab', ref: '@cad[s.step#f1]' }] : x < 50 ? [{ part: 'slab', ref: '@cad[s.step#e2]' }] : [{ part: 'slab' }]);
  const [item] = projectAnnotations(runtime, [stroke('t', along(41, 46).map(x => [x, 58]))], size, { touchesAt });
  assert.deepEqual(item.touches, [{ part: 'slab', ref: '@cad[s.step#f1]' }, { part: 'slab', ref: '@cad[s.step#e2]' }]);
  // Without the renderer's names, the parts under it.
  const [parts] = projectAnnotations(runtime, [stroke('p', along(46, 54).map(x => [x, 50]))], size);
  assert.deepEqual(parts.touches.map(touch => touch.part).sort(), ['post', 'slab']);
});

test('drawn, ink stays where it was drawn whatever the parts do and is cut where the model is; updated, only what changed is redrawn; disposed, the scene is as it was', () => {
  const { runtime, slab } = rig();
  const [first, second] = projectAnnotations(runtime, [stroke('a', [[42, 55], [45, 55]]), stroke('b', [[42, 58], [45, 58]])], size);
  const before = runtime.scene.onBeforeRender;
  const ink = mountAnnotations(runtime);
  ink.update([first]);
  const [line] = ink.group.children.filter(child => child.isLine2);
  // The model hides none of it: the same line drawn faint over everything, under it.
  const [hidden] = line.children;
  assert.equal(hidden.material.depthTest, false);
  assert.ok(hidden.material.opacity < line.material.opacity && hidden.renderOrder < line.renderOrder);
  ink.update([first, second]);
  const lines = ink.group.children.filter(child => child.isLine2);
  assert.equal(lines.length, 2);
  assert.equal(lines[0], line, 'the mark already drawn keeps its object');
  ink.update([second]);
  assert.deepEqual(ink.group.children.filter(child => child.isLine2), [lines[1]]);
  // What Select picked is haloed behind its ink, and lets go with it.
  ink.update([first, second], [second.id]);
  const halos = () => ink.group.children.filter(child => child.isLine2 && child.renderOrder < lines[1].renderOrder);
  assert.equal(halos().length, 1);
  // What the pointer rests on, fainter; picking it brightens the halo.
  ink.update([first, second], [second.id], [first.id]);
  const opacities = () => halos().map(halo => halo.material.opacity).sort();
  assert.deepEqual(opacities(), [0.25, 0.5]);
  ink.update([first, second], [first.id, second.id], [first.id]);
  assert.deepEqual(opacities(), [0.5, 0.5]);
  ink.update([first, second], []);
  assert.equal(halos().length, 0);
  const drawn = ink.group.children.find(child => child.isLine2 && child !== lines[1]);
  // The part moves (an explode, a pose): the ink stays.
  slab.position.set(30, 0, -1);
  runtime.scene.updateMatrixWorld(true);
  ink.group.children[0].onBeforeRender();
  assert.deepEqual(drawn.matrixWorld.elements, new THREE.Matrix4().elements);
  // Clip: the model's planes are the ink's.
  runtime.activeClipPlanes = [new THREE.Plane(new THREE.Vector3(1, 0, 0), 0)];
  ink.group.children[0].onBeforeRender();
  assert.equal(drawn.material.clippingPlanes, runtime.activeClipPlanes);
  // The part hidden: the ink is not.
  slab.visible = false;
  ink.group.children[0].onBeforeRender();
  assert.equal(drawn.visible, true);
  ink.dispose();
  assert.equal(ink.group.parent, null);
  assert.equal(runtime.scene.onBeforeRender, before);
});

test('transmission and nested draws update ink without replacing another owner’s scene hook', () => {
  const { runtime } = rig();
  let scenes = 0;
  const before = runtime.scene.onBeforeRender = () => { scenes += 1; };
  const ink = mountAnnotations(runtime);
  const [item] = projectAnnotations(runtime, [stroke('glass', [[42, 55], [45, 55]])], size);
  ink.update([item]);
  const sentinel = ink.group.children[0];
  const line = ink.group.children.find(child => child.isLine2);
  const draw = () => {
    runtime.scene.onBeforeRender();
    sentinel.onBeforeRender(); // transmission buffer
    sentinel.onBeforeRender(); // main opaque pass, with no second scene callback
  };
  draw();
  runtime.activeClipPlanes = [new THREE.Plane(new THREE.Vector3(1, 0, 0), 0)];
  draw();
  assert.equal(line.material.clippingPlanes, runtime.activeClipPlanes);
  assert.equal(runtime.scene.onBeforeRender, before);
  assert.equal(scenes, 2);
  // Another owner may wrap and later restore its own hook; ink never changes that chain.
  runtime.scene.onBeforeRender = () => { before(); sentinel.onBeforeRender(); };
  const wrapper = runtime.scene.onBeforeRender;
  draw();
  ink.dispose();
  assert.equal(runtime.scene.onBeforeRender, wrapper);
});

test("each mark keeps its group and the view it was drawn in; the annotation writes as an annotation file, in model coordinates", () => {
  const { runtime } = rig();
  // The line lies mostly on the slab; the head's wings are over nothing.
  const marks = [
    { ...stroke('line', [[44, 56], [56, 56], [62, 56]]), group: 'arrow', view: 'view 1' },
    { ...stroke('wing', [[61, 57], [64, 59]]), group: 'arrow', view: 'view 1' },
  ];
  const items = projectAnnotations(runtime, marks, size);
  assert.deepEqual(items.map(item => [item.view, item.group]), [['view 1', 'arrow'], ['view 1', 'arrow']]);
  assert.deepEqual(items[0].touches.map(touch => touch.part), ['slab']);
  const annotation = normalizeAnnotation(JSON.parse(JSON.stringify(annotationDocumentOf(items))));
  assert.deepEqual(Object.keys(annotation), ['units', 'marks']);
  assert.deepEqual(annotation.marks.map(mark => [mark.id, mark.kind, mark.view]), [['line', 'stroke', 'view 1'], ['wing', 'stroke', 'view 1']]);
  assert.deepEqual(annotation.marks[0].points, Array.from(items[0].points));
});

test("the ink drawn in a runtime says where it is, for the camera's depth range, and only the ink: ink beyond the model is not cut by a near plane fitted to the model", () => {
  const { runtime } = rig();
  const [item] = projectAnnotations(runtime, [stroke('far', [[5, 5], [95, 95]])], size, { placement: 'plane' });
  const ink = mountAnnotations(runtime);
  ink.update([item]);
  // On the slab's level (z 0, lifted), however far it runs; nothing else is drawn round it.
  assert.deepEqual(runtime.annotationBounds.min.map(Math.round), [-45, -45, 2]);
  assert.deepEqual(runtime.annotationBounds.max.map(Math.round), [45, 45, 2]);
  assert.deepEqual(ink.group.children.filter(child => child.userData.pane), []);
  ink.update([]);
  assert.equal(runtime.annotationBounds, null);
  ink.dispose();
  assert.equal(runtime.annotationBounds, null);
});
