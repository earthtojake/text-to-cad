import * as THREE from 'three';
import { expect, it } from 'vitest';
import { buildGlbDocumentFromBuffer } from '@text-to-cad/core/lib/render/glbMeshData.js';
import { createGlbScene } from '@text-to-cad/core/lib/render/glbScene.js';
import { carriesCamJob } from '../../../dist/renderers/glb/cam/detect.js';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { cadFrame, camToolpathObjects, readCamSegments, toolPositionAt } from '../../../dist/renderers/glb/cam/lines.js';
import { camSceneMeshes, camTimeline } from '../../../dist/renderers/glb/cam/playback.js';
import { createCamTool } from '../../../dist/renderers/glb/cam/tool.js';
import { camSample, type Sample } from './__tests__/camFile';

// The samples as the viewer loads them (GLTFLoader through core's GLB document), not scenes built by hand: the job
// arrives on the glTF scene's userData, a node's extras on its object, and `_CAM_T`/`_CAM_OP` lowercased.
const load = async (name: Sample) => {
  const document = await buildGlbDocumentFromBuffer(camSample(name), {});
  return { scene: createGlbScene(THREE, document), root: document.scene };
};

/** A point of the file (glTF metres, Y up) in CAD mm, Z up. */
const cadPoint = ([x, y, z]: number[]) => [x * 1000, -z * 1000, y * 1000];

it('reads a real ready result: the job, every operation\'s lines on the program\'s clock, the part and the stock box', async () => {
  const { scene, root } = await load('ready');
  expect(carriesCamJob(root)).toBe(true);
  const job = readCamJob(root)!;
  expect([job.verdict.status, job.post]).toEqual(['ready', 'grbl']);
  const lines = camToolpathObjects(root);
  expect(lines.map((entry: any) => [entry.setup, entry.kind])).toEqual([['top', 'feed'], ['top', 'rapid']]);
  expect(Object.keys(lines[0].object.geometry.attributes).sort()).toEqual(['_cam_op', '_cam_t', 'position']);
  const { groups, timeline } = readCamSegments(THREE, root);
  expect([...new Set(groups.filter((group: any) => group.kind === 'feed').map((group: any) => group.op))].sort()).toEqual([0, 1, 2, 3]);
  const last = Math.max(...timeline.segments.map((segment: any) => segment.t1));
  expect(last).toBeLessThanOrEqual(job.durationS + 1e-2);
  expect(last).toBeGreaterThan(job.durationS * 0.9);
  expect(camTimeline(job).to).toBeCloseTo(job.durationS, 3);
  for (const op of job.operations) {
    const own = timeline.segments.filter((segment: any) => segment.op === op.index);
    expect(Math.min(...own.map((segment: any) => segment.t0))).toBeGreaterThanOrEqual(op.t0 - 1e-2);
    expect(Math.max(...own.map((segment: any) => segment.t1))).toBeLessThanOrEqual(op.t1 + 1e-2);
  }
  // Every cut is over the stock box (within the tool's radius of it), in the file's metres turned to CAD mm.
  const { min_mm: min, max_mm: max } = root.userData.cam.stock;
  const cuts = groups.filter((entry: any) => entry.kind === 'feed').flatMap((group: any) =>
    Array.from({ length: group.positions.length / 3 }, (_, i) => cadPoint(Array.from(group.positions.subarray(i * 3, i * 3 + 3)))));
  for (const axis of [0, 1]) {
    expect(Math.min(...cuts.map((at: number[]) => at[axis]))).toBeGreaterThanOrEqual(min[axis] - 3.01);
    expect(Math.max(...cuts.map((at: number[]) => at[axis]))).toBeLessThanOrEqual(max[axis] + 3.01);
  }
  const meshes = camSceneMeshes(root);
  expect([meshes.part.map((mesh: any) => mesh.name), meshes.stock.map((mesh: any) => mesh.name)]).toEqual([['part'], ['stock']]);
  // The file's metres are 1000 CAD mm a unit, and CAD's +Z is the file's +Y: the tool stands up out of the top setup.
  const frame = cadFrame(THREE, root, scene.object3D);
  expect(frame.mmPerUnit).toBeCloseTo(1000);
  const tool = createCamTool(THREE, root, job, frame);
  const place = toolPositionAt(timeline, (job.operations[1].t0 + job.operations[1].t1) / 2)!;
  expect(place.op).toBe(1);
  tool.show(place);
  expect(new THREE.Vector3(0, 1, 0).applyQuaternion(tool.object3D.quaternion).y).toBeCloseTo(1, 6);
  tool.dispose();
  scene.dispose();
});

it('reads a real refused result: its error on the operation it names, and the -Z setup\'s tool from below', async () => {
  const { scene, root } = await load('fix');
  const job = readCamJob(root)!;
  expect([job.verdict.status, job.verdict.errors, job.findings[0].check, job.findings[0].operation]).toEqual(['fix', 1, 'reach', 0]);
  expect(camToolpathObjects(root).map((entry: any) => [entry.setup, entry.kind])).toEqual([['bottom', 'feed'], ['bottom', 'rapid']]);
  const { timeline } = readCamSegments(THREE, root);
  expect(new Set(timeline.segments.map((segment: any) => segment.op))).toEqual(new Set([1]));
  const tool = createCamTool(THREE, root, job, cadFrame(THREE, root, scene.object3D));
  tool.show(toolPositionAt(timeline, job.durationS / 2)!);
  expect(new THREE.Vector3(0, 1, 0).applyQuaternion(tool.object3D.quaternion).y).toBeCloseTo(-1, 6);
  tool.dispose();
  scene.dispose();
});
