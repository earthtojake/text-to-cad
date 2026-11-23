import assert from 'node:assert/strict';
import test from 'node:test';
import { DEFAULT_PLAYBACK, normalizePlayback } from './playbackPreferences.js';

test('playback is orbit speed 1 by default, with no Orbit on or off and no Autoplay (an old record\'s is dropped), and a speed and a loop only once they were chosen', () => {
  assert.deepEqual(DEFAULT_PLAYBACK, { orbitSpeed: 1 });
  for (const value of [null, undefined, {}, 'yes', { autoplay: 'yes', orbit: true, orbitSpeed: 'fast' }]) assert.deepEqual(normalizePlayback(value), DEFAULT_PLAYBACK);
  assert.deepEqual(normalizePlayback({ orbitSpeed: 2, autoplay: true, speed: 2, loop: false }), { orbitSpeed: 2, speed: 2, loop: false });
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

test("a record's playbar put away is dropped: the tools view has no playbar, its routines are the Animation tab's", () => {
  // A record from when the tools view had a playbar to put away: no playbar now, and its `collapsed` is dropped.
  for (const collapsed of [true, false, 'yes', 1, null]) assert.equal('collapsed' in normalizePlayback({ collapsed }), false);
});
