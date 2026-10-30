import { Group, Matrix4 } from 'three';
import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { expect, it, vi } from 'vitest';
import { CamResultError, readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { cadFrame, camToolpathObjects, createCamPaths, readCamSegments, toolPositionAt } from '../../../dist/renderers/glb/cam/lines.js';
import { createCamTool, toolShape } from '../../../dist/renderers/glb/cam/tool.js';
import { camExtras, camLines, camScene } from './__tests__/camFile';

// What the viewport runtime hands the paths: its screen-space line classes and its material registry.
const runtime = () => ({ LineSegments2, LineSegmentsGeometry, LineMaterial, registerScreenSpaceLineMaterial: vi.fn(), unregisterScreenSpaceLineMaterial: vi.fn() });
const drawnOf = (root: Group) => root.children.filter((child: any) => child.userData.camDrawn && child.isLineSegments2) as any[];

it('groups the file\'s segments by kind and operation, each group in time order, with the setup from the node', () => {
  const root = camScene();
  expect(camToolpathObjects(root).map((entry: any) => [entry.kind, entry.setup])).toEqual([['feed', 'top'], ['rapid', 'top']]);
  const { groups, timeline } = readCamSegments(THREE, root);
  expect(groups.map((group: any) => [group.key, group.setup, Array.from(group.starts)])).toEqual([
    ['feed:0', 'top', [0, 10]], ['feed:1', 'top', [70]], ['rapid:1', 'top', [63]]]);
  // The face's second move (written after the pocket's) is its group's second segment.
  expect(Array.from(groups[0].positions)).toEqual([0, 0, 0, 10, 0, 0, 10, 0, 0, 10, 10, 0]);
  expect(Array.from(timeline.starts)).toEqual([0, 10, 63, 70]);
  // A line without a time and an operation per vertex is no toolpath.
  root.add(new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3))));
  expect(camToolpathObjects(root)).toHaveLength(2);
});

it('reads a job of hundreds of thousands of segments without overflowing the stack', () => {
  // A 23-minute five-operation job on an 80 x 60 x 25 mm block passed 100k segments in one group, which
  // overflowed V8's argument limit when they were spread into one push().
  const count = 300_000;
  const root = camScene();
  root.remove(...root.children.filter((child: any) => child.isLineSegments));
  const points: number[][] = [];
  const times: number[] = [];
  for (let i = 0; i < count; i += 1) {
    points.push([i * 0.01, 0, 0], [(i + 1) * 0.01, 0, 0]);
    times.push(i, i + 1);
  }
  root.add(camLines(points, times, new Array(times.length).fill(0), { setup: 'top', kind: 'feed' }));
  const { groups, timeline } = readCamSegments(THREE, root);
  expect(groups.map((group: any) => [group.key, group.starts.length])).toEqual([['feed:0', count]]);
  expect(timeline.segments.length).toBe(count);
  expect(timeline.starts[count - 1]).toBe(count - 1);
});

it('says where the tool is at a moment: along the move under way, held through a pause, at the start before it', () => {
  const root = camScene();
  const { timeline } = readCamSegments(THREE, root);
  expect(toolPositionAt(timeline, 5)).toEqual({ point: [5, 0, 0], op: 0, setup: 'top' });
  expect(toolPositionAt(timeline, 66.5)!.point).toEqual([7.5, 7.5, 2.5]);
  expect(toolPositionAt(timeline, 40)!.point).toEqual([10, 10, 0]);
  expect(toolPositionAt(timeline, 75)!.point).toEqual([5, 7, -2]);
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

it('sizes the riding tool in mm and stands it along the setup\'s axis, in a scene the file placed in metres', () => {
  const placed = new Group();
  placed.matrix.copy(new Matrix4().makeScale(1000, 1000, 1000).multiply(new Matrix4().makeRotationX(Math.PI / 2)));
  placed.matrixAutoUpdate = false;
  const root = camScene({ extras: camExtras('fix') });
  placed.add(root);
  const frame = cadFrame(THREE, root, placed);
  expect(frame.mmPerUnit).toBeCloseTo(1000);
  // CAD +Z is the file's +Y once its Y-up frame is turned to Z-up.
  expect(frame.direction([0, 0, 1]).toArray().map((value: number) => Math.round(value * 1e6) / 1e6)).toEqual([0, 1, 0]);
  const job = readCamJob(root)!;
  const tool = createCamTool(THREE, root, job, frame);
  const along = () => new THREE.Vector3(0, 1, 0).applyQuaternion(tool.object3D.quaternion).toArray().map((value: number) => Math.round(value * 1e6) / 1e6 + 0);
  tool.show({ point: [0.01, 0, 0], op: 0, setup: 'top' });
  expect(tool.object3D.visible).toBe(true);
  expect(tool.object3D.position.toArray()).toEqual([0.01, 0, 0]);
  expect(along()).toEqual([0, 1, 0]);
  const shown = tool.object3D.children[0];
  // A 5 mm flat: its cutter's radius is 2.5 mm, 0.0025 of the file's metres; the cutter, then the holder.
  const cutter = shown.children[0] as any;
  expect(cutter.geometry.parameters.radiusTop * shown.scale.x).toBeCloseTo(0.0025);
  expect(shown.children).toHaveLength(2);
  // The bottom setup's tool comes from -Z.
  tool.show({ point: [0, 0, 0], op: 1, setup: 'bottom' });
  expect(along()).toEqual([0, -1, 0]);
  tool.hide();
  expect(tool.object3D.visible).toBe(false);
  tool.dispose();
  expect(root.children.includes(tool.object3D)).toBe(false);
});

it('draws a ball end mill with a ball at its tip, and refuses a path whose operation or setup the job does not list', () => {
  expect(toolShape({ toolDiameterMm: 4, toolType: 'ball' })).toEqual({ radius: 2, ball: true });
  expect(toolShape({ toolDiameterMm: 6, toolType: 'drill' })).toEqual({ radius: 3, ball: false });
  // It once stood a 6 mm tool there: no result cadgen writes names either.
  const root = camScene();
  const tool = createCamTool(THREE, root, readCamJob(root)!, cadFrame(THREE, root, root));
  expect(() => tool.show({ point: [0, 0, 0], op: 9, setup: 'top' })).toThrow(CamResultError);
  expect(() => tool.show({ point: [0, 0, 0], op: 0, setup: 'side' })).toThrow("a toolpath's setup side names a setup the result does not list");
  tool.dispose();
});
