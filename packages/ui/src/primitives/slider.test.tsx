import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Slider } from './slider.jsx';

Object.assign(globalThis, { React });

// The browser's pointer capture, as it answers: an id it knows (a pointer pressed now) is captured, any
// other throws NotFoundError -- what a synthetic press's id gets, as an automation's script dispatches one.
const ACTIVE = 1;
const captured = new Map<number, Element>();
const restores: Array<() => void> = [];
const listenerErrors: unknown[] = [];
const recordError = (event: ErrorEvent) => { listenerErrors.push(event.error); event.preventDefault(); };
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const capture = {
    setPointerCapture(this: Element, pointerId: number) {
      if (pointerId !== ACTIVE) throw new DOMException('No active pointer with the given id is found.', 'NotFoundError');
      captured.set(pointerId, this);
    },
    hasPointerCapture(this: Element, pointerId: number) { return captured.get(pointerId) === this; },
    releasePointerCapture(pointerId: number) { captured.delete(pointerId); },
  };
  for (const [name, value] of Object.entries(capture)) {
    const previous = Object.getOwnPropertyDescriptor(Element.prototype, name);
    Object.defineProperty(Element.prototype, name, { configurable: true, value });
    restores.push(() => previous ? Object.defineProperty(Element.prototype, name, previous) : delete (Element.prototype as any)[name]);
  }
  window.addEventListener('error', recordError);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  while (restores.length) restores.pop()!();
  captured.clear();
  window.removeEventListener('error', recordError);
  expect(listenerErrors.splice(0)).toEqual([]);
});

// Radix's slider captures every press's pointer and then slides; a press it cannot capture would
// throw out of its handler as the page's crash, and a slide it began uncaptured would never end
// (its lift commits only a captured one). So that press is no slide.
it('a press whose pointer the browser does not know neither throws nor slides', () => {
  const onValueChange = vi.fn(), onPointerDown = vi.fn();
  render(<Slider value={[40]} min={0} max={100} thumbProps={{ 'aria-label': 'Opacity' }}
    onValueChange={onValueChange} onPointerDown={onPointerDown} />);
  const thumb = screen.getByRole('slider', { name: 'Opacity' });
  fireEvent.pointerDown(thumb, { pointerId: 7, button: 0 });
  expect(listenerErrors).toEqual([]);
  expect(onPointerDown).toHaveBeenCalledTimes(1);
  expect(captured.size).toBe(0);
  expect(onValueChange).not.toHaveBeenCalled();
  // A pressed pointer is captured and slides, as Radix's own.
  fireEvent.pointerDown(thumb, { pointerId: ACTIVE, button: 0 });
  expect(captured.get(ACTIVE)).toBe(thumb);
  fireEvent.pointerUp(thumb, { pointerId: ACTIVE, button: 0 });
  expect(captured.size).toBe(0);
});
