/**
 * @vitest-environment jsdom
 */
import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AnimatedHeight } from '.';
import { HEIGHT_TRANSITION_DURATION_MS } from './constants';

let observerCallbacks: ResizeObserverCallback[] = [];
let measuredHeight = 0;

class FakeResizeObserver implements ResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    observerCallbacks.push(callback);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

function fireResize() {
  act(() => {
    for (const callback of [...observerCallbacks]) {
      callback([], undefined as unknown as ResizeObserver);
    }
  });
}

describe('AnimatedHeight', () => {
  const originalResizeObserver = globalThis.ResizeObserver;
  const originalOffsetHeight = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    'offsetHeight'
  );

  beforeEach(() => {
    observerCallbacks = [];
    measuredHeight = 100;
    vi.useFakeTimers();
    globalThis.ResizeObserver = FakeResizeObserver;
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get: () => measuredHeight,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    globalThis.ResizeObserver = originalResizeObserver;
    if (originalOffsetHeight) {
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight);
    }
  });

  function renderAnimatedHeight(onAnimatingChange?: (isAnimating: boolean) => void) {
    const { container } = render(
      <AnimatedHeight onAnimatingChange={onAnimatingChange}>content</AnimatedHeight>
    );
    const root = container.firstElementChild as HTMLElement;
    return root;
  }

  it('pins the row to the measured height on mount without animating', () => {
    const onAnimatingChange = vi.fn();
    const root = renderAnimatedHeight(onAnimatingChange);

    expect(root.style.gridTemplateRows).toBe('100px');
    expect(root.hasAttribute('data-animating')).toBe(false);
    expect(onAnimatingChange).toHaveBeenCalledTimes(1);
    expect(onAnimatingChange).toHaveBeenLastCalledWith(false);
  });

  it('ignores the first ResizeObserver callback', () => {
    const root = renderAnimatedHeight();

    fireResize();

    expect(root.style.gridTemplateRows).toBe('100px');
    expect(root.hasAttribute('data-animating')).toBe(false);
  });

  it('animates height changes and settles via the fallback timer', () => {
    const onAnimatingChange = vi.fn();
    const root = renderAnimatedHeight(onAnimatingChange);
    fireResize(); // swallowed first callback

    measuredHeight = 180;
    fireResize();

    expect(root.style.gridTemplateRows).toBe('180px');
    expect(root.hasAttribute('data-animating')).toBe(true);
    expect(onAnimatingChange).toHaveBeenLastCalledWith(true);

    act(() => {
      vi.advanceTimersByTime(HEIGHT_TRANSITION_DURATION_MS + 50);
    });

    expect(root.hasAttribute('data-animating')).toBe(false);
    expect(onAnimatingChange).toHaveBeenLastCalledWith(false);
  });

  it('settles as soon as the grid-template-rows transition ends', () => {
    const root = renderAnimatedHeight();
    fireResize();

    measuredHeight = 180;
    fireResize();
    expect(root.hasAttribute('data-animating')).toBe(true);

    fireEvent.transitionEnd(root, { propertyName: 'grid-template-rows' });

    expect(root.hasAttribute('data-animating')).toBe(false);
  });

  it('ignores transitionend events for other properties and from children', () => {
    const root = renderAnimatedHeight();
    fireResize();

    measuredHeight = 180;
    fireResize();

    fireEvent.transitionEnd(root, { propertyName: 'opacity' });
    expect(root.hasAttribute('data-animating')).toBe(true);

    fireEvent.transitionEnd(root.firstElementChild as HTMLElement, {
      propertyName: 'grid-template-rows',
    });
    expect(root.hasAttribute('data-animating')).toBe(true);
  });

  it('does not restart the animation when the observed height is unchanged', () => {
    const root = renderAnimatedHeight();
    fireResize();
    fireResize();

    expect(root.hasAttribute('data-animating')).toBe(false);
  });

  it('re-arms the settle timer when the height changes mid-animation', () => {
    const root = renderAnimatedHeight();
    fireResize();

    measuredHeight = 180;
    fireResize();
    act(() => {
      vi.advanceTimersByTime(200);
    });

    measuredHeight = 240;
    fireResize();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    // 400ms after the first change, but only 200ms after the retarget.
    expect(root.hasAttribute('data-animating')).toBe(true);

    act(() => {
      vi.advanceTimersByTime(HEIGHT_TRANSITION_DURATION_MS + 50 - 200);
    });
    expect(root.hasAttribute('data-animating')).toBe(false);
  });
});
