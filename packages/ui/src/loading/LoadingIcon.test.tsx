import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import LoadingIcon from './LoadingIcon.jsx';
Object.assign(globalThis, { React });

let reduce = false;
beforeEach(() => {
  reduce = false;
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') && reduce, addEventListener() {}, removeEventListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); document.documentElement.className = ''; });
const animated = (image: HTMLImageElement) => !/still/.test(image.getAttribute('src') || '');

it('animates unless the system or the host asks for reduced motion, and reads no host class', () => {
  const { container, rerender } = render(<LoadingIcon />);
  expect(animated(container.querySelector('img')!)).toBe(true);
  // A host's own class on <html> is the host's business: only the explicit prop counts.
  document.documentElement.classList.add('reduce-motion');
  rerender(<LoadingIcon key="class" />);
  expect(animated(container.querySelector('img')!)).toBe(true);
  rerender(<LoadingIcon key="prop" reducedMotion />);
  expect(animated(container.querySelector('img')!)).toBe(false);
  reduce = true;
  rerender(<LoadingIcon key="system" />);
  expect(animated(container.querySelector('img')!)).toBe(false);
});
