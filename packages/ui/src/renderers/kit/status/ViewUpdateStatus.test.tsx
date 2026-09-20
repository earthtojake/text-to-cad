import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
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
