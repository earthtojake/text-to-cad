import * as THREE from 'three';
import { expect, it } from 'vitest';
import { buildGlbDocumentFromBuffer } from '@text-to-cad/core/lib/render/glbMeshData.js';
import { createGlbScene } from '@text-to-cad/core/lib/render/glbScene.js';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { cadFrame, camToolpathObjects, readCamSegments, toolPositionAt } from '../../../dist/renderers/glb/cam/lines.js';
import { camExtras } from './__tests__/camFile';
import { camGlb, gltfPoint } from './__tests__/camGlb';

// The file as the viewer loads it (GLTFLoader through core's GLB document), not a scene built by hand: the job
// arrives on the glTF scene's userData, a node's extras on its object, and `_CAM_T`/`_CAM_OP` lowercased.
it('reads a .cam.glb as GLTFLoader loads it: the job, the lines by setup and kind, their times and operations', async () => {
  const document = await buildGlbDocumentFromBuffer(camGlb(camExtras()), {});
  const scene = createGlbScene(THREE, document);
  const root = document.scene;
  expect(root.userData.generator).toBe('cadgen cam');
  const job = readCamJob(root)!;
  expect(job.operations.map((op: any) => op.plain)).toEqual(['Face', 'Pocket']);
  const lines = camToolpathObjects(root);
  expect(lines.map((entry: any) => [entry.object.isLineSegments, entry.kind, entry.setup])).toEqual([[true, 'feed', 'top'], [true, 'rapid', 'top']]);
  expect(Object.keys(lines[0].object.geometry.attributes).sort()).toEqual(['_cam_op', '_cam_t', 'position']);
  const { groups, timeline } = readCamSegments(THREE, root, job);
  expect(groups.map((group: any) => [group.key, Array.from(group.starts)])).toEqual([['feed:0', [0]], ['feed:1', [40]], ['rapid:1', [10]]]);
  // The moment the pocket's move is half done, the tool is half way along it, in the file's metres.
  const at = toolPositionAt(timeline, 60)!.point;
  gltfPoint([5, 7, -2]).forEach((value, axis) => expect(at[axis]).toBeCloseTo(value, 6));
  // The file's metres are 1000 CAD mm a unit, and CAD's +Z is the file's +Y.
  const frame = cadFrame(THREE, root, scene.object3D);
  expect(frame.mmPerUnit).toBeCloseTo(1000);
  expect(frame.direction([0, 0, 1]).y).toBeCloseTo(1);
  scene.dispose();
});
