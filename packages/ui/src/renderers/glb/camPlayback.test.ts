import { Mesh } from 'three';
import { expect, it, vi } from 'vitest';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { SIMULATE_SECONDS, STEP_SECONDS, camClips, camReadoutWords, camSceneMeshes, camTimeline, formatClock, playbackSpeedWords, showCamMeshes } from '../../../dist/renderers/glb/cam/playback.js';
import { camExtras, camScene } from './__tests__/camFile';

it('plays the program as Simulate, fast enough to watch, its moment the program\'s time', () => {
  const job = readCamJob(camScene())!;
  expect(camTimeline(job)).toEqual({ from: 0, to: 90, pace: SIMULATE_SECONDS / 90 });
  const onMoment = vi.fn();
  const clips = camClips(job, onMoment);
  // One setup: Simulate alone.
  expect(clips.map((clip: any) => [clip.id, clip.label, clip.duration])).toEqual([['cam:simulate', 'Simulate', 30]]);
  clips[0].play.apply(15);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 45, setup: null });
  clips[0].play.apply(99);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 90, setup: null });
  clips[0].play.release();
  expect(onMoment).toHaveBeenLastCalledWith(null);
});

it('adds a clip per setup when the job has more than one, each at the same pace over its own span', () => {
  const extras = camExtras();
  extras.setups.push({ id: 'bottom', plain: 'Bottom', time_s: 30, orientation: '-Z', operations: [
    { index: 2, op: 'contour', plain: 'Profile', tool: 'T1', tool_plain: '6 mm flat', time_s: 30, t0: 90, t1: 120, summary: 'Profile', limits: [] } as any] });
  extras.duration_s = 120;
  const onMoment = vi.fn();
  const clips = camClips(readCamJob(camScene({ extras }))!, onMoment);
  expect(clips.map((clip: any) => [clip.label, clip.duration])).toEqual([['Simulate', 30], ['Simulate Top', 22.5], ['Simulate Bottom', 7.5]]);
  clips[2].play.apply(0);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 90, setup: 'bottom' });
  // A real-time program shorter than the cap plays as it runs.
  const short = camExtras();
  short.duration_s = 10;
  short.setups[0].operations.forEach((op: any) => { op.t0 /= 9; op.t1 /= 9; });
  expect(camClips(readCamJob(camScene({ extras: short }))!, onMoment)[0].duration).toBe(10);
});

it('shows the part and the stock as Display says, and the stock an operation leaves while it plays', () => {
  const root = camScene();
  const job = readCamJob(root)!;
  const meshes = camSceneMeshes(root);
  expect([meshes.part.length, meshes.stock.length]).toEqual([1, 1]);
  expect(showCamMeshes(meshes, job, { part: true, stock: false })).toBe(true);
  expect([meshes.part[0].visible, meshes.stock[0].object.visible]).toEqual([true, false]);
  expect(showCamMeshes(meshes, job, { part: true, stock: false })).toBe(false);
  // Stock stored after each operation: the one after the last finished, the final one at rest.
  const afterFace = new Mesh();
  Object.assign(afterFace.userData, { kind: 'stock', operation: 0 });
  const afterPocket = new Mesh();
  Object.assign(afterPocket.userData, { kind: 'stock', operation: 1 });
  root.remove(meshes.stock[0].object);
  root.add(afterFace, afterPocket);
  const staged = camSceneMeshes(root);
  showCamMeshes(staged, job, { stock: true, time: 40 });
  expect([afterFace.visible, afterPocket.visible]).toEqual([true, false]);
  showCamMeshes(staged, job, { stock: true, time: null });
  expect([afterFace.visible, afterPocket.visible]).toEqual([false, true]);
});

it('steps one operation a second when motion is reduced, each operation drawn whole', () => {
  const extras = camExtras();
  extras.setups.push({ id: 'bottom', plain: 'Bottom', time_s: 30, orientation: '-Z', operations: [
    { index: 2, op: 'contour', plain: 'Profile', tool: 'T1', tool_plain: '6 mm flat', time_s: 30, t0: 90, t1: 120, summary: 'Profile', limits: [] } as any] });
  extras.duration_s = 120;
  const onMoment = vi.fn();
  const clips = camClips(readCamJob(camScene({ extras }))!, onMoment, { reducedMotion: true });
  expect(STEP_SECONDS).toBe(1);
  expect(clips.map((clip: any) => [clip.label, clip.duration])).toEqual([['Simulate', 3], ['Simulate Top', 2], ['Simulate Bottom', 1]]);
  // Nothing sweeps: each second holds the end of one operation.
  clips[0].play.apply(0);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 30, setup: null });
  clips[0].play.apply(1.9);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 90, setup: null });
  clips[0].play.apply(3);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 120, setup: null });
  clips[2].play.apply(0.5);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 120, setup: 'bottom' });
  clips[0].play.release();
  expect(onMoment).toHaveBeenLastCalledWith(null);
});

it('says over the playbar the operation under way, the program\'s time over its whole and how fast it plays', () => {
  const job = readCamJob(camScene())!;
  expect([0, 45, 61.6, 754, 3725].map(formatClock)).toEqual(['0:00', '0:45', '1:02', '12:34', '1:02:05']);
  // 90 s in Simulate's 30 s: three times real time, times the playbar's own speed.
  expect(playbackSpeedWords(job)).toBe('3× speed');
  expect(playbackSpeedWords(job, { speed: 0.5 })).toBe('1.5× speed');
  expect(playbackSpeedWords(job, { speed: 1 / 3 })).toBe('Real time');
  expect(playbackSpeedWords(job, { reducedMotion: true })).toBe('One operation a second');
  expect(camReadoutWords(job, { t: 45, setup: null })).toEqual({ operation: 'Pocket', time: '0:45 / 1:30', speed: '3× speed' });
  // At an operation's last moment, that operation; the tool's own operation where the path says.
  expect(camReadoutWords(job, { t: 30, setup: null })!.operation).toBe('Face');
  expect(camReadoutWords(job, { t: 0, setup: null })!.operation).toBe('Face');
  expect(camReadoutWords(job, { t: 10, setup: null }, { op: 1 })!.operation).toBe('Pocket');
  expect(camReadoutWords(job, null)).toBeNull();
});
