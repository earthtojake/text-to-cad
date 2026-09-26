import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createAnimationClock } from './animationClockStore.js';

test('playback clocks and subscriptions belong to one renderer', () => {
  const first = createAnimationClock(), second = createAnimationClock();
  let firstNotifications = 0, secondNotifications = 0;
  const release = first.subscribe(() => firstNotifications++);
  second.subscribe(() => secondNotifications++);
  first.setAnimationClock(2.5);
  assert.equal(first.getAnimationClock(), 2.5);
  assert.equal(second.getAnimationClock(), 0);
  assert.equal(firstNotifications, 1);
  assert.equal(secondNotifications, 0);
  second.setAnimationClock(9);
  first.resetAnimationClock();
  assert.equal(second.getAnimationClock(), 9);
  assert.equal(secondNotifications, 1);
  release();
  first.setAnimationClock(4);
  assert.equal(firstNotifications, 2);
});
