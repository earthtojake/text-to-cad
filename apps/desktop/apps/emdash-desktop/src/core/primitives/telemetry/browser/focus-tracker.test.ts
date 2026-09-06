import { describe, expect, it, vi } from 'vitest';
import { FocusTracker } from './focus-tracker';

describe('FocusTracker', () => {
  it('emits exited focus state on transition', () => {
    const tracker = new FocusTracker();
    const emit = vi.fn();
    tracker.setTransitionEmitter(emit);

    tracker.initialize({ view: 'home', mainPanel: null, focusedRegion: null });
    tracker.transition({ view: 'task', mainPanel: 'agents' }, 'navigation');

    expect(emit).toHaveBeenCalledTimes(1);
    const payload = emit.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.view).toBe('home');
    expect(payload.trigger).toBe('navigation');
    expect(payload).not.toHaveProperty('duration_ms');
  });

  it('does not emit when no tracked focus state changed', () => {
    const tracker = new FocusTracker();
    const emit = vi.fn();
    tracker.setTransitionEmitter(emit);

    tracker.initialize({ view: 'home', mainPanel: null, focusedRegion: null });
    const result = tracker.transition({}, 'navigation');

    expect(result).toBeNull();
    expect(emit).not.toHaveBeenCalled();
  });
});
