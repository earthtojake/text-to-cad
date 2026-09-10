import assert from 'node:assert/strict';
import test from 'node:test';
import { assemblyPlaybackFrames, composeAssemblyPlayback } from './reconstructionAssembly.js';
const mesh = n => ({ vertices: [n, 0, 0, n, 1, 0, n, 0, 1], normals: [1,0,0,1,0,0,1,0,0] });
const track = n => ({ reference: mesh(n), steps: [
  { id: 'sketch', label: 'Profile', kind: 'sketch', dependsOn: [], lines: [[[0,0,0],[1,0,0]]], measurements: [], solidFrame: null },
  { ...mesh(n), id: 'extrude', label: 'Extrude', kind: 'extrude', dependsOn: ['sketch'], lines: [], measurements: [], solidFrame: 1 },
] });
const occurrence = (id, component) => ({ id, component, name: component, transform: [1,0,0,10,0,1,0,20,0,0,1,30,0,0,0,1] });

test('14 verified components play with all 15 components and repeated instances visible', () => {
  const tracks = Object.fromEntries(Array.from({ length: 14 }, (_,i) => [`c${i}`, track(i)]));
  tracks.c14 = { reference: mesh(14) };
  const occurrences = Object.keys(tracks).map(id => occurrence(id, id));
  occurrences.push(occurrence('repeat', 'c0'));
  const data = composeAssemblyPlayback({ occurrences, bbox: {min:[0,0,0],max:[100,100,100]} }, tracks);
  assert.equal(data.verified, 14); assert.equal(data.staticParts, 1);
  assert.equal(data.steps.length, 28, 'one shared sequence per component, not just the selected part');
  assert.equal(new Set(data.steps.map(s => s.id)).size, 28);
  assert.deepEqual(data.steps[1].dependsOn, ['c0/sketch']);
  for (let i=0; i<data.steps.length; i++) {
    const frames = assemblyPlaybackFrames(data, i);
    assert.equal(frames.length, 16);
    assert.equal(frames.find(f=>f.occurrence.component==='c14').mesh, tracks.c14.reference);
    assert.equal(new Set(frames.filter(f=>f.active).map(f=>f.occurrence.component)).size, 1);
    assert.deepEqual(frames[0].occurrence.transform, occurrences[0].transform);
  }
  assert.equal(assemblyPlaybackFrames(data, 0)[0].mesh, null, 'sketch frames show a profile, not a fabricated solid');
  assert.equal(assemblyPlaybackFrames(data, 0).at(-2).context, true);
  assert.ok(assemblyPlaybackFrames(data, 27).every(f => !f.context), 'final assembly is fully visible');
  const first = assemblyPlaybackFrames(data, 1);
  assert.equal(first[0].mesh, first.at(-1).mesh, 'instances reuse geometry');
  assert.equal(first[0].mesh, tracks.c0.steps[1]);
  const original = assemblyPlaybackFrames(data, 1, true);
  assert.ok(original.every(f=>!f.active && !f.lines.length));
  assert.equal(original[0].mesh, tracks.c0.reference);
});

test('an unsupported component does not prevent other component playback', () => {
  const data = composeAssemblyPlayback({occurrences:[occurrence('a','a'),occurrence('b','b')],bbox:{min:[0,0,0],max:[1,1,1]}}, {a:{reference:mesh(0)},b:track(1)});
  assert.equal(data.steps.length,2);assert.equal(data.steps[0].component,'b');
  assert.equal(data.staticParts,1);assert.equal(data.verified,1);
});
