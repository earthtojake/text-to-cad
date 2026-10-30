import { expect, it, vi } from 'vitest';
import { readCamJob } from '../../../dist/renderers/glb/cam/extras.js';
import { SIMULATE_SECONDS, STEP_SECONDS, camClips, camReadoutWords, camSceneMeshes, camTimeline, formatClock, playbackSpeedWords, showCamMeshes } from '../../../dist/renderers/glb/cam/playback.js';
import { camExtras, camScene } from './__tests__/camFile';

/** The ready job with a bottom setup after it: a 30 s profile (op 4), 129.533–159.533 s. */
function twoSetups() {
  const extras = camExtras();
  extras.setups.push({ ...extras.setups[0], id: 'bottom', plain: 'bottom', time_s: 30, t0: 129.533, t1: 159.533, orientation: '-Z',
    matrix: [[1, 0, 0], [0, -1, 0], [0, 0, -1]], operations: [{ ...extras.setups[0].operations[2], index: 4, setup: 'bottom', op: 'profile',
      plain: 'Profile', time_s: 30, t0: 129.533, t1: 159.533, summary: 'Profile' }] });
  extras.duration_s = 159.533;
  return readCamJob(camScene({ extras }))!;
}

it('plays the program as Simulate, fast enough to watch, its moment the program\'s time', () => {
  const job = readCamJob(camScene())!;
  expect(camTimeline(job)).toEqual({ from: 0, to: 129.533, pace: SIMULATE_SECONDS / 129.533 });
  const onMoment = vi.fn();
  const clips = camClips(job, onMoment);
  // One setup: Simulate alone.
  expect(clips.map((clip: any) => [clip.id, clip.label, clip.duration])).toEqual([['cam:simulate', 'Simulate', 30]]);
  clips[0].play.apply(15);
  expect(onMoment.mock.lastCall![0].t).toBeCloseTo(129.533 / 2, 6);
  clips[0].play.apply(99);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 129.533, setup: null });
  clips[0].play.release();
  expect(onMoment).toHaveBeenLastCalledWith(null);
});

it('adds a clip per setup when the job has more than one, each at the same pace over its own span', () => {
  const onMoment = vi.fn();
  const clips = camClips(twoSetups(), onMoment);
  expect(clips.map((clip: any) => clip.label)).toEqual(['Simulate', 'Simulate top', 'Simulate bottom']);
  const pace = 30 / 159.533;
  [30, 129.533 * pace, 30 * pace].forEach((duration, i) => expect(clips[i].duration).toBeCloseTo(duration, 6));
  clips[2].play.apply(0);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 129.533, setup: 'bottom' });
  // A real-time program shorter than the cap plays as it runs.
  const short = camExtras();
  short.duration_s = 10;
  short.setups[0].operations.forEach((op: any) => { op.t0 /= 13; op.t1 /= 13; });
  expect(camClips(readCamJob(camScene({ extras: short }))!, onMoment)[0].duration).toBe(10);
  // A setup with no time to play (the refused one, whose operation was never planned) has no clip.
  expect(camClips(readCamJob(camScene({ extras: camExtras('fix') }))!, onMoment).map((clip: any) => clip.label)).toEqual(['Simulate', 'Simulate bottom']);
});

it('shows the part and the stock box as Job\'s Show rows say', () => {
  const meshes = camSceneMeshes(camScene());
  expect([meshes.part.map((mesh: any) => mesh.name), meshes.stock.map((mesh: any) => mesh.name)]).toEqual([['part'], ['stock']]);
  expect(showCamMeshes(meshes, { part: true, stock: false })).toBe(true);
  expect([meshes.part[0].visible, meshes.stock[0].visible]).toEqual([true, false]);
  expect(showCamMeshes(meshes, { part: true, stock: false })).toBe(false);
  expect(showCamMeshes(meshes, { part: false, stock: true })).toBe(true);
  expect([meshes.part[0].visible, meshes.stock[0].visible]).toEqual([false, true]);
});

it('steps one operation a second when motion is reduced, each operation drawn whole', () => {
  const onMoment = vi.fn();
  const clips = camClips(twoSetups(), onMoment, { reducedMotion: true });
  expect(STEP_SECONDS).toBe(1);
  expect(clips.map((clip: any) => [clip.label, clip.duration])).toEqual([['Simulate', 5], ['Simulate top', 4], ['Simulate bottom', 1]]);
  // Nothing sweeps: each second holds the end of one operation.
  clips[0].play.apply(0);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 62.478, setup: null });
  clips[0].play.apply(1.9);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 81.717, setup: null });
  clips[0].play.apply(9);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 159.533, setup: null });
  clips[2].play.apply(0.5);
  expect(onMoment).toHaveBeenLastCalledWith({ t: 159.533, setup: 'bottom' });
  clips[0].play.release();
  expect(onMoment).toHaveBeenLastCalledWith(null);
});

it('says over the playbar the operation under way, the program\'s time over its whole and how fast it plays', () => {
  const job = readCamJob(camScene())!;
  expect([0, 45, 61.6, 754, 3725].map(formatClock)).toEqual(['0:00', '0:45', '1:02', '12:34', '1:02:05']);
  // 129.533 s in Simulate's 30 s: 4.3 times real time, times the playbar's own speed.
  expect(playbackSpeedWords(job)).toBe('4.3× speed');
  expect(playbackSpeedWords(job, { speed: 0.5 })).toBe('2.2× speed');
  expect(playbackSpeedWords(job, { speed: 30 / 129.533 })).toBe('Real time');
  expect(playbackSpeedWords(job, { reducedMotion: true })).toBe('One operation a second');
  expect(camReadoutWords(job, { t: 70, setup: null })).toEqual({ operation: 'Pocket', time: '1:10 / 2:10', speed: '4.3× speed' });
  // At an operation's last moment, that operation; the tool's own operation where the path says.
  expect(camReadoutWords(job, { t: 62.478, setup: null })!.operation).toBe('Face');
  expect(camReadoutWords(job, { t: 0, setup: null })!.operation).toBe('Face');
  expect(camReadoutWords(job, { t: 10, setup: null }, { op: 3 })!.operation).toBe('Drill');
  expect(camReadoutWords(job, null)).toBeNull();
});
