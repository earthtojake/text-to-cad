import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import * as THREE from 'three';
import { expect, it } from 'vitest';
import { buildGlbDocumentFromBuffer } from '@text-to-cad/core/lib/render/glbMeshData.js';
import { createGlbScene } from '@text-to-cad/core/lib/render/glbScene.js';
import { carriesCamJob } from '../../../dist/renderers/glb/cam/detect.js';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { cadFrame, camToolpathObjects, readCamSegments, toolPositionAt } from '../../../dist/renderers/glb/cam/lines.js';
import { camSceneMeshes, camTimeline } from '../../../dist/renderers/glb/cam/playback.js';
import { createCamTool, setupAxis } from '../../../dist/renderers/glb/cam/tool.js';

/*
 * `__tests__/boss.cam.glb` is a real result, written by `cadgen cam plan` (not by hand): a 20 x 15 x 3 plate with an
 * 11 x 7 boss 6 mm tall whose walls lean in 15°, on a mill5 (linuxcnc), stock box margin [1, 1, 0.5], tolerance 0.1,
 * one 8 mm flat (T1). Setup `top` (+Z): a region pocket clearing round the boss (op 0), then swarf on its four walls
 * (op 1, continuous A/C: its lines carry `_CAM_AXIS`); setup `tilt` ({"a_deg": 30}, 3+2): a face 0.5 mm deep (op 2).
 * To regenerate it, build that part with build123d (Box(20, 15, 3) + loft of Rectangle(11, 7) at z 3 to the inset
 * rectangle at z 9), plan it with that job (the swarf faces are the four walls `cadgen cam features` lists at z ~6),
 * and keep it under 200 KB.
 */
const load = async () => {
  const bytes = readFileSync(join(__dirname, '__tests__', 'boss.cam.glb'));
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const document = await buildGlbDocumentFromBuffer(copy.buffer, {});
  return { document, scene: createGlbScene(THREE, document), root: document.scene };
};

const degreesBetween = (a: number[], b: number[]) => {
  const dot = a.reduce((sum, value, i) => sum + value * b[i], 0) / (Math.hypot(...a) * Math.hypot(...b));
  return (Math.acos(Math.min(1, Math.max(-1, dot))) * 180) / Math.PI;
};

it('reads a real .cam.glb: the job, every operation\'s lines, the program\'s clock, the part and the stock', async () => {
  const { scene, root } = await load();
  expect(carriesCamJob(root)).toBe(true);
  const job = readCamJob(root)!;
  expect(job.machine).toBe('mill5');
  expect(job.verdict.status).toBe('ready');
  expect(job.setups.map((setup: any) => [setup.id, setup.orientation, setup.operations.map((op: any) => op.op)]))
    .toEqual([['top', '+Z', ['pocket', 'swarf']], ['tilt', 'A 30°', ['face']]]);
  const lines = camToolpathObjects(root);
  expect(lines.map((entry: any) => [entry.setup, entry.kind])).toEqual([['top', 'feed'], ['top', 'rapid'], ['tilt', 'feed'], ['tilt', 'rapid']]);
  // GLTFLoader lowercases the custom attributes; only the continuous setup's lines carry an axis.
  expect(Object.keys(lines[0].object.geometry.attributes).sort()).toEqual(['_cam_axis', '_cam_op', '_cam_t', 'position']);
  expect(Object.keys(lines[2].object.geometry.attributes).sort()).toEqual(['_cam_op', '_cam_t', 'position']);
  const { groups, timeline } = readCamSegments(THREE, root, job);
  const ops = new Set(groups.map((group: any) => group.op));
  expect([...ops].sort()).toEqual([0, 1, 2]);
  for (const op of ops) expect(job.operations.some((row: any) => row.index === op)).toBe(true);
  expect(groups.filter((group: any) => group.kind === 'feed').map((group: any) => group.op).sort()).toEqual([0, 1, 2]);
  const last = Math.max(...timeline.segments.map((segment: any) => segment.t1));
  expect(last).toBeLessThanOrEqual(job.durationS + 1e-2);
  expect(last).toBeGreaterThan(job.durationS * 0.9);
  expect(camTimeline(job).to).toBeCloseTo(job.durationS, 3);
  for (const op of job.operations) {
    const own = timeline.segments.filter((segment: any) => segment.op === op.index);
    expect(Math.min(...own.map((segment: any) => segment.t0))).toBeGreaterThanOrEqual(op.t0 - 1e-2);
    expect(Math.max(...own.map((segment: any) => segment.t1))).toBeLessThanOrEqual(op.t1 + 1e-2);
  }
  const meshes = camSceneMeshes(root);
  expect([meshes.part.length, meshes.stock.length]).toEqual([1, 1]);
  scene.dispose();
});

it('stands the tool along a 3+2 setup\'s tilted axis and along each move\'s own axis where the file carries one', async () => {
  const { scene, root } = await load();
  const job = readCamJob(root)!;
  const frame = cadFrame(THREE, root, scene.object3D);
  // The tilted setup's axis is its matrix's third row: the part's (0, sin 30°, cos 30°), not +Z.
  const tilt = job.setups[1];
  setupAxis(tilt).forEach((value: number, i: number) => expect(value).toBeCloseTo([0, 0.5, Math.sqrt(3) / 2][i], 6));
  const { timeline } = readCamSegments(THREE, root, job);
  const up = frame.direction([0, 0, 1]).toArray();
  // Swarf: the tool lies along the 15° walls while it cuts them.
  const swarf = timeline.segments.filter((segment: any) => segment.op === 1);
  expect(swarf.every((segment: any) => segment.axis)).toBe(true);
  const tilts = swarf.map((segment: any) => degreesBetween(segment.axis[1], up));
  expect(Math.max(...tilts)).toBeCloseTo(15, 1);
  expect(tilts.filter((value: number) => value > 14).length).toBeGreaterThan(10);
  const tool = createCamTool(THREE, root, job, frame);
  const along = (place: any) => new THREE.Vector3(0, 1, 0).applyQuaternion(tool.object3D.quaternion).toArray();
  const cutting = swarf.find((segment: any) => degreesBetween(segment.axis[1], up) > 14)!;
  const place = toolPositionAt(timeline, (cutting.t0 + cutting.t1) / 2)!;
  expect(place.axis).not.toBeNull();
  tool.show(place);
  expect(degreesBetween(along(place), place.axis!)).toBeLessThan(1e-3);
  // The 3+2 face: no axis on its lines, so the tool stands along the setup's.
  const face = job.operations.find((op: any) => op.op === 'face')!;
  const tilted = toolPositionAt(timeline, (face.t0 + face.t1) / 2)!;
  expect([tilted.op, tilted.axis]).toEqual([face.index, null]);
  tool.show(tilted);
  expect(degreesBetween(along(tilted), frame.direction(setupAxis(tilt)).toArray())).toBeLessThan(1e-3);
  expect(degreesBetween(along(tilted), up)).toBeCloseTo(30, 3);
  tool.dispose();
  scene.dispose();
});
