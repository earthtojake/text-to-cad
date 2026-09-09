import { describe, expect, it } from 'vitest';
import { createHeightChangeTracker } from './height-change-tracker';

describe('createHeightChangeTracker', () => {
  it('swallows the first observation even when the height differs', () => {
    const tracker = createHeightChangeTracker(100);
    expect(tracker.observe(180)).toBeNull();
  });

  it('signals a change after the first observation', () => {
    const tracker = createHeightChangeTracker(100);
    tracker.observe(100);
    expect(tracker.observe(180)).toBe(180);
  });

  it('ignores observations equal to the last known height', () => {
    const tracker = createHeightChangeTracker(100);
    tracker.observe(100);
    expect(tracker.observe(100)).toBeNull();
  });

  it('compares against the initial height when the first observation was skipped', () => {
    // The skipped first observation must not overwrite the initial
    // measurement: a later observation matching the initial height is a
    // no-op, not a change.
    const tracker = createHeightChangeTracker(100);
    tracker.observe(240);
    expect(tracker.observe(100)).toBeNull();
  });

  it('tracks the latest signalled height for dedupe', () => {
    const tracker = createHeightChangeTracker(100);
    tracker.observe(100);
    expect(tracker.observe(150)).toBe(150);
    expect(tracker.observe(150)).toBeNull();
    expect(tracker.observe(100)).toBe(100);
  });

  it('handles an unknown initial height', () => {
    const tracker = createHeightChangeTracker(undefined);
    expect(tracker.observe(50)).toBeNull();
    expect(tracker.observe(50)).toBeNull();
    expect(tracker.observe(80)).toBe(80);
  });
});
