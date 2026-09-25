import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ViewerMobileContext } from '../../../file-viewer/responsive.js';
import { ViewUpdateStatus } from './ViewUpdateStatus.jsx';
Object.assign(globalThis, { React });
afterEach(() => { cleanup(); vi.useRealTimers(); });
it('delays fast changes, announces preparation, and leaves placement to its caller', () => {
  vi.useFakeTimers();
  const pending = { pending: true, error: null, label: 'Preparing section view…' };
  const { rerender } = render(<ViewUpdateStatus status={pending} className="bottom-3" />);
  act(() => vi.advanceTimersByTime(149));
  expect(screen.queryByRole('status')).toBeNull();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByRole('status').textContent).toBe(pending.label);
  expect(screen.getByRole('status').className).toContain('bottom-3');
  rerender(<ViewUpdateStatus status={{ ...pending, pending: false }} />);
  expect(screen.queryByRole('status')).toBeNull();
});
it('presents errors and retries without owning any viewer state', () => {
  const retry = vi.fn();
  render(<ViewUpdateStatus status={{ pending: false, error: 'WebGL failed' }} onRetry={retry} />);
  expect(screen.getByRole('alert').textContent).toContain('Couldn’t update view');
  fireEvent.click(screen.getByRole('button', { name: 'Retry view update' }));
  expect(retry).toHaveBeenCalledOnce();
});

it('mobile progress is a compact icon with tap-to-read detail and a retry for failures', () => {
  vi.useFakeTimers();
  const retry = vi.fn();
  const wrap = status => <ViewerMobileContext.Provider value={true}><ViewUpdateStatus status={status} onRetry={retry} /></ViewerMobileContext.Provider>;
  const { rerender } = render(wrap({ pending: true, error: null, label: 'Preparing surfaces…' }));
  act(() => vi.advanceTimersByTime(150));
  const trigger = screen.getByRole('button', { name: 'Preparing surfaces…' });
  expect(trigger.textContent).toBe('');
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(trigger);
  expect(screen.getByRole('status').textContent).toBe('Preparing surfaces…');
  rerender(wrap({ pending: false, error: 'WebGL failed' }));
  fireEvent.click(screen.getByRole('button', { name: 'Retry', exact: true }));
  expect(retry).toHaveBeenCalledOnce();
});
