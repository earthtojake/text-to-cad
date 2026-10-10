import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import TreeRowEye from '../../../../dist/renderers/kit/inspector/TreeRowEye.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

it('a Hide eye hides, and once on is crossed out and reveals; a press never reaches the row', () => {
  const toggled = vi.fn();
  const row = vi.fn();
  const { rerender } = render(<div onClick={row}><TreeRowEye on={false} label="base_link" onToggle={toggled} /></div>);
  const eye = screen.getByRole('button', { name: 'Hide base_link' });
  expect(eye.getAttribute('aria-pressed')).toBeNull();
  fireEvent.click(eye);
  expect(toggled).toHaveBeenCalledTimes(1);
  expect(row).not.toHaveBeenCalled();
  rerender(<div onClick={row}><TreeRowEye on label="base_link" onToggle={toggled} /></div>);
  expect(screen.getByRole('button', { name: 'Reveal base_link' })).not.toBeNull();
  expect(document.querySelector('[data-row-actions]')!.className).toMatch(/opacity-100/);
});

it('an Isolate eye isolates, and once on is lit and pressed, and exits', () => {
  const toggled = vi.fn();
  const { rerender } = render(<TreeRowEye kind="isolate" on={false} label="U3" onToggle={toggled} />);
  expect(screen.getByRole('button', { name: 'Isolate U3' }).getAttribute('aria-pressed')).toBe('false');
  rerender(<TreeRowEye kind="isolate" on label="U3" onToggle={toggled} />);
  const lit = screen.getByRole('button', { name: 'Exit isolate U3' });
  expect(lit.getAttribute('aria-pressed')).toBe('true');
  expect(lit.className).toMatch(/text-foreground/);
  fireEvent.click(lit);
  expect(toggled).toHaveBeenCalledTimes(1);
});
