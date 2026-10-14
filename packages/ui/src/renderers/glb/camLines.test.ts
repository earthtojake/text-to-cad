import { Group, Matrix4 } from 'three';
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { expect, it, vi } from 'vitest';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { cadFrame, camToolpathObjects, createCamPaths, readCamSegments, toolPositionAt } from '../../../dist/renderers/glb/cam/lines.js';
import { createCamTool, operationAxis, setupAxis, toolShape } from '../../../dist/renderers/glb/cam/tool.js';
import { FIXTURE_LOOK, camHasFixtures, createCamFixtures, fixtureSetups } from '../../../dist/renderers/glb/cam/fixtures.js';
import { camExtras, camLines, camScene } from './__tests__/camFile';

// What the viewport runtime hands the paths: its screen-space line classes and its material registry.
const runtime = () => ({ LineSegments2, LineSegmentsGeometry, LineMaterial, registerScreenSpaceLineMaterial: vi.fn(), unregisterScreenSpaceLineMaterial: vi.fn() });
const drawnOf = (root: Group) => root.children.filter((child: any) => child.userData.camDrawn && child.isLineSegments2) as any[];

it('groups the file\'s segments by kind and operation, each group in time order, with the setup from the node', () => {
  const root = camScene();
  const job = readCamJob(root)!;
  expect(camToolpathObjects(root).map((entry: any) => [entry.kind, entry.setup])).toEqual([['feed', 'top'], ['rapid', 'top']]);
  const { groups, timeline } = readCamSegments(THREE, root, job);
  expect(groups.map((group: any) => [group.key, group.setup, Array.from(group.starts)])).toEqual([
    ['feed:0', 'top', [0, 10]], ['feed:1', 'top', [40]], ['rapid:1', 'top', [20]]]);
  // The face's second move (written after the pocket's) is its group's second segment.
  expect(Array.from(groups[0].positions)).toEqual([0, 0, 0, 10, 0, 0, 10, 0, 0, 10, 10, 0]);
  expect(Array.from(timeline.starts)).toEqual([0, 10, 20, 40]);
});

it('finds a segment\'s operation by its time when the file has no _CAM_OP, and reads the attributes however they are spelled', () => {
  const root = camScene();
  root.remove(...root.children.filter((child: any) => child.isLineSegments));
  const rapid = camLines([[0, 0, 0], [1, 0, 0], [1, 0, 0], [2, 0, 0]], [5, 6, 50, 60], null, { name: 'top rapids' }, { upper: true });
  root.add(rapid);
  const { groups } = readCamSegments(THREE, root, readCamJob(root)!);
  expect(groups.map((group: any) => [group.key, group.setup])).toEqual([['rapid:0', 'top'], ['rapid:1', 'top']]);
});

it('says where the tool is at a moment: along the move under way, held through a pause, at the start before it', () => {
  const root = camScene();
  const { timeline } = readCamSegments(THREE, root, readCamJob(root)!);
  expect(toolPositionAt(timeline, 5)).toEqual({ point: [5, 0, 0], op: 0, setup: 'top', axis: null });
  expect(toolPositionAt(timeline, 25)!.point).toEqual([7.5, 7.5, 2.5]);
  expect(toolPositionAt(timeline, 35)!.point).toEqual([5, 5, 5]);
  expect(toolPositionAt(timeline, 60)!.point).toEqual([5, 7, -2]);
  expect(toolPositionAt(timeline, -1)!.point).toEqual([0, 0, 0]);
  expect(toolPositionAt(timeline, 5, 'other')).toBeNull();
});

it('draws each operation\'s feed moves and rapids as screen-space lines, puts the file\'s lines away, and gives them back', () => {
  const root = camScene();
  const job = readCamJob(root)!;
  const context = runtime();
  const paths = createCamPaths(THREE, root, job, { context, scheme: 'light' })!;
  const drawn = drawnOf(root);
  expect(paths.count).toBe(3);
  expect(drawn.map((line) => line.name)).toEqual(['cam-feed-0', 'cam-feed-1', 'cam-rapid-1']);
  expect(context.registerScreenSpaceLineMaterial).toHaveBeenCalledTimes(3);
  // Feed moves in their operation's colour, thicker than the dashed rapids.
  const [face, pocket, rapid] = drawn;
  expect(face.material.color.getHexString()).not.toBe(pocket.material.color.getHexString());
  expect(rapid.material.dashed).toBe(true);
  expect(face.material.dashed).toBe(false);
  expect(face.material.linewidth).toBeGreaterThan(rapid.material.linewidth);
  expect(camToolpathObjects(root).every((entry: any) => entry.object.visible === false)).toBe(true);
  paths.dispose();
  expect(drawnOf(root)).toHaveLength(0);
  expect(context.unregisterScreenSpaceLineMaterial).toHaveBeenCalledTimes(3);
  expect(camToolpathObjects(root).every((entry: any) => entry.object.visible === true)).toBe(true);
  expect(createCamPaths(THREE, root, job, { context: {} })).toBeNull();
});

it('isolates operations, hides a kind, and reveals the paths up to a moment, the move under way cut at the tool', () => {
  const root = camScene();
  const paths = createCamPaths(THREE, root, readCamJob(root)!, { context: runtime() })!;
  const [face, pocket, rapid] = drawnOf(root);
  expect(paths.update({ isolate: new Set([1]) })).toBe(true);
  expect(paths.update({ isolate: new Set([1]) })).toBe(false);
  expect(face.material.opacity).toBeLessThan(0.2);
  expect(pocket.material.opacity).toBe(1);
  paths.update({ rapids: false });
  expect([face.visible, pocket.visible, rapid.visible]).toEqual([true, true, false]);
  paths.update({ time: 5 });
  expect([face.geometry.instanceCount, pocket.geometry.instanceCount, rapid.geometry.instanceCount]).toEqual([1, 0, 0]);
  const ends = () => Array.from(face.geometry.attributes.instanceStart.data.array.slice(3, 6));
  expect(ends()).toEqual([5, 0, 0]);
  paths.update({ time: 15 });
  expect(face.geometry.instanceCount).toBe(2);
  expect(ends()).toEqual([10, 0, 0]);
  paths.update({ time: null });
  expect(face.geometry.instanceCount).toBe(Infinity);
  expect(Array.from(face.geometry.attributes.instanceStart.data.array.slice(9, 12))).toEqual([10, 10, 0]);
  // A setup's clip shows that setup's paths alone.
  paths.update({ time: 50, setup: 'other' });
  expect(face.visible).toBe(false);
  // An operation hidden by its eye is put away, feed moves and rapids, whatever is isolated.
  paths.update({ isolate: new Set([1]), hidden: new Set([1]) });
  expect([face.visible, pocket.visible, rapid.visible]).toEqual([true, false, false]);
  paths.update({ hidden: null });
  expect([face.visible, pocket.visible, rapid.visible]).toEqual([true, true, true]);
  paths.dispose();
});

it('draws each setup\'s fixtures as see-through steel boxes, in the file\'s metres, only those of the setup in view', () => {
  const placed = new Group();
  placed.matrix.copy(new Matrix4().makeScale(1000, 1000, 1000).multiply(new Matrix4().makeRotationX(Math.PI / 2)));
  placed.matrixAutoUpdate = false;
  const extras = camExtras() as any;
  extras.setups[0].fixtures = [{ name: 'vise jaw', min_mm: [-5, -10, -20], max_mm: [5, 10, 0] }];
  extras.setups.push({ id: 'bottom', plain: 'Bottom', orientation: '-Z', operations: [
    { index: 2, op: 'contour', plain: 'Profile', tool: 'T1', time_s: 10, t0: 90, t1: 100, limits: [] }],
    fixtures: [{ name: 'soft jaw', min_mm: [0, 0, 0], max_mm: [1, 1, 1] }] });
  const root = camScene({ extras });
  placed.add(root);
  const job = readCamJob(root)!;
  expect(camHasFixtures(job)).toBe(true);
  expect(camHasFixtures(readCamJob(camScene())!)).toBe(false);
  const fixtures = createCamFixtures(THREE, root, job, cadFrame(THREE, root, placed), 'light');
  expect(fixtures.count).toBe(2);
  const [jaw, soft] = fixtures.object3D.children as any[];
  // The box in the file's frame: 10 x 20 x 20 mm about (0, 0, -10) in the part's Z-up mm is 0.01 x 0.02 x 0.02 about (0, -0.01, 0).
  const box = new THREE.Box3().setFromBufferAttribute(jaw.geometry.attributes.position).applyMatrix4(jaw.matrix);
  const round = (vector: any) => vector.toArray().map((value: number) => Math.round(value * 1e6) / 1e6 + 0);
  expect(round(box.getCenter(new THREE.Vector3()))).toEqual([0, -0.01, 0]);
  expect(round(box.getSize(new THREE.Vector3()))).toEqual([0.01, 0.02, 0.02]);
  // Steel blue, see-through and matte, so the part stands out.
  expect(`#${jaw.material.color.getHexString()}`).toBe(FIXTURE_LOOK.light.colour);
  expect([jaw.material.opacity, jaw.material.transparent, jaw.material.depthWrite, jaw.material.metalness, jaw.material.roughness]).toEqual([0.2, true, false, 0, 0.9]);
  fixtures.style('dark');
  expect([`#${jaw.material.color.getHexString()}`, jaw.material.opacity]).toEqual([FIXTURE_LOOK.dark.colour, 0.28]);
  expect(jaw.userData.camDrawn).toBe(true);
  // Which setups' fixtures are up: the one a clip plays (the tool's place first), a chosen row's, or at rest the
  // first setup's that has any (two setups' holds drawn round one part would show a hold no setup has).
  expect(fixtureSetups(job, { moment: { t: 95, setup: null }, playing: 'bottom' })).toEqual(new Set(['bottom']));
  expect(fixtureSetups(job, { moment: { t: 95, setup: 'top' } })).toEqual(new Set(['top']));
  expect(fixtureSetups(job, { isolate: new Set([0, 2]) })).toEqual(new Set(['top', 'bottom']));
  expect(fixtureSetups(job, {})).toEqual(new Set(['top']));
  expect(fixtureSetups({ ...job, setups: job.setups.map((setup: any) => ({ ...setup, fixtures: [] })) }, {})).toBeNull();
  expect(fixtures.update({ setups: new Set(['bottom']) })).toBe(true);
  expect([jaw.visible, soft.visible]).toEqual([false, true]);
  expect(fixtures.update({ setups: new Set(['bottom']) })).toBe(false);
  fixtures.update({ shown: false });
  expect([jaw.visible, soft.visible]).toEqual([false, false]);
  fixtures.update({});
  expect([jaw.visible, soft.visible]).toEqual([true, true]);
  fixtures.dispose();
  expect(root.children.includes(fixtures.object3D)).toBe(false);
});

it('sizes the riding tool in mm and stands it along the setup\'s axis, in a scene the file placed in metres', () => {
  const placed = new Group();
  placed.matrix.copy(new Matrix4().makeScale(1000, 1000, 1000).multiply(new Matrix4().makeRotationX(Math.PI / 2)));
  placed.matrixAutoUpdate = false;
  const root = camScene();
  placed.add(root);
  const frame = cadFrame(THREE, root, placed);
  expect(frame.mmPerUnit).toBeCloseTo(1000);
  // CAD +Z is the file's +Y once its Y-up frame is turned to Z-up.
  expect(frame.direction([0, 0, 1]).toArray().map((value: number) => Math.round(value * 1e6) / 1e6)).toEqual([0, 1, 0]);
  const job = readCamJob(root)!;
  const tool = createCamTool(THREE, root, job, frame);
  tool.show({ point: [0.01, 0, 0], op: 1, setup: 'top' });
  expect(tool.object3D.visible).toBe(true);
  expect(tool.object3D.position.toArray()).toEqual([0.01, 0, 0]);
  const shown = tool.object3D.children[0];
  // A 4 mm ball: its cutter's radius is 2 mm, 0.002 of the file's metres.
  shown.updateMatrixWorld(true);
  const cutter = shown.children[0] as any;
  expect(cutter.geometry.parameters.radiusTop * shown.scale.x).toBeCloseTo(0.002);
  expect(shown.children).toHaveLength(3);
  tool.hide();
  expect(tool.object3D.visible).toBe(false);
  tool.dispose();
  expect(root.children.includes(tool.object3D)).toBe(false);
});

it('stands a lathe\'s turning tools across the spindle and its drill along it, and draws a beam or a wire, not a cutter', () => {
  const lathe = { machine: 'lathe', setups: [], operations: [] };
  const setup = { id: 'turn', axis: [0, 0, 1], across: [1, 0, 0] };
  expect(operationAxis(lathe, setup, { op: 'turn_rough' })).toEqual([1, 0, 0]);
  expect(operationAxis(lathe, setup, { op: 'turn_drill' })).toEqual([0, 0, 1]);
  expect(operationAxis({ machine: 'mill' }, setup, { op: 'pocket' })).toEqual([0, 0, 1]);
  expect(setupAxis({ orientation: '-X' })).toEqual([-1, 0, 0]);
  expect(toolShape({ machine: 'laser' }, { kerfMm: 0.2, toolDiameterMm: null })).toEqual({ kind: 'beam', radius: 0.15, ball: false });
  expect(toolShape({ machine: 'plasma' }, { kerfMm: 1.5 })).toEqual({ kind: 'beam', radius: 0.75, ball: false });
  expect(toolShape({ machine: 'wire_edm' }, { toolDiameterMm: 0.25 })).toEqual({ kind: 'wire', radius: 0.15, ball: false });
  expect(toolShape({ machine: 'mill' }, { toolDiameterMm: 4, toolType: 'ball' })).toEqual({ kind: 'cutter', radius: 2, ball: true });
});

it('rides a segment\'s own axis where the file carries one per vertex, turning it along the move', () => {
  const root = camScene();
  const feed = root.children.find((child: any) => child.isLineSegments && child.userData.kind === 'feed') as any;
  const tilt = Math.SQRT1_2;
  // The face's first move turns the tool from upright to 45° about X as it goes.
  feed.geometry.setAttribute('_cam_axis', new THREE.BufferAttribute(new Float32Array([0, 0, 1, 0, -tilt, tilt, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]), 3));
  const { timeline } = readCamSegments(THREE, root, readCamJob(root)!);
  expect(toolPositionAt(timeline, 0)!.axis).toEqual([0, 0, 1]);
  const half = toolPositionAt(timeline, 5)!.axis!;
  expect(Math.hypot(...half)).toBeCloseTo(1, 6);
  expect(half[1]).toBeLessThan(0);
  // At its end, the turned axis (the next move, upright again, starts at 10).
  toolPositionAt(timeline, 10 - 1e-9)!.axis!.forEach((value: number, i: number) => expect(value).toBeCloseTo([0, -tilt, tilt][i], 6));
  expect(toolPositionAt(timeline, 10)!.axis).toEqual([0, 0, 1]);
});
