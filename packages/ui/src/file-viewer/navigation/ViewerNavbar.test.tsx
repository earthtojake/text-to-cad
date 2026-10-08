import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewerNavbar } from '../../../dist/file-viewer/navigation/ViewerNavbar.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FILE = '/home/me/models/a.step';
const chevron = () => document.querySelector('[data-file-name] svg');

it('marks the file name with a chevron where it opens the explorer, and leaves a plain name bare', () => {
  const explorer = { source: { list: async () => [], search: vi.fn() }, onOpen: vi.fn() };
  const { rerender } = render(<ViewerNavbar file={FILE} explorer={explorer} />);
  const trigger = document.querySelector('[data-file-name]')!;
  expect(trigger.tagName).toBe('BUTTON');
  expect(trigger.textContent).toBe('a.step');
  expect(chevron()?.getAttribute('aria-hidden')).toBe('true');
  expect(chevron()?.getAttribute('class')).toContain('shrink-0');
  rerender(<ViewerNavbar file={FILE} explorer={null} />);
  expect(document.querySelector('[data-file-name]')!.tagName).toBe('SPAN');
  expect(chevron()).toBeNull();
});
