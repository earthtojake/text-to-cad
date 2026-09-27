import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_PLAYBACK, normalizePlayback } from './playbackPreferences.js';

test('playback is orbit on at speed 1 and Autoplay off by default, and a speed and a loop only once they were chosen', () => {
  assert.deepEqual(DEFAULT_PLAYBACK, { orbit: true, orbitSpeed: 1, autoplay: false });
  for (const value of [null, undefined, {}, 'yes', { autoplay: 'yes', orbit: 'no', orbitSpeed: 'fast' }]) assert.deepEqual(normalizePlayback(value), DEFAULT_PLAYBACK);
  assert.deepEqual(normalizePlayback({ orbit: false, orbitSpeed: 2, autoplay: true, speed: 2, loop: false }), { orbit: false, orbitSpeed: 2, autoplay: true, speed: 2, loop: false });
});

test('the orbit speed keeps stopped and fractional speeds and bounds a corrupt one; a chosen speed is bounded as the clock bounds it', () => {
  for (const orbitSpeed of [0, 0.05, 1.37, 5]) assert.equal(normalizePlayback({ orbitSpeed }).orbitSpeed, orbitSpeed);
  assert.equal(normalizePlayback({ orbitSpeed: -1 }).orbitSpeed, 0);
  assert.equal(normalizePlayback({ orbitSpeed: 100 }).orbitSpeed, 5);
  for (const orbitSpeed of [null, 'fast', Infinity, NaN]) assert.equal(normalizePlayback({ orbitSpeed }).orbitSpeed, 1);
  assert.equal(normalizePlayback({ speed: 99 }).speed, 3);
  for (const speed of [0, -1, 'fast', NaN, Infinity]) assert.equal('speed' in normalizePlayback({ speed }), false);
  assert.equal('loop' in normalizePlayback({ loop: 'yes' }), false);
});
