import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ViewerMobileContext } from '../../../file-viewer/responsive.js';
import { I18nProvider } from '@text-to-cad/ui/i18n';
import { loadingProgress } from './loadingState.js';
import { MODEL_UPDATE_STATUS, modelUpdateStatus, ViewUpdateStatus } from './ViewUpdateStatus.jsx';
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
it('names cadgen meshing a cold load behind the view, counted, and calls anything else updating', () => {
  expect(modelUpdateStatus({ label: 'Meshing parts', counts: '37/256' })).toEqual({ pending: true, label: 'Meshing parts 37/256…' });
  expect(modelUpdateStatus({ label: 'Loading geometry', counts: '37/256' })).toBe(MODEL_UPDATE_STATUS);
  expect(modelUpdateStatus(null)).toBe(MODEL_UPDATE_STATUS);
});

// The engine's one progress event (`cad/engine/progress.py`), as the version wait or the import hands it to the page.
const event = (kind: string, stage: string, done = 0, total: number | null = null, detail = '') =>
  ({ kind, stage, job: 'hand.py::hand', outputs: [], detail, done, total, elapsedMs: 120 });

it('says the stage of the engine\'s progress event behind the view, for every kind, counted where it has units', () => {
  vi.useFakeTimers();
  expect(modelUpdateStatus(loadingProgress(event('build', 'body', 2, null, 'finger')))).toEqual({ pending: true, label: 'progress.build.body', counts: '' });
  const said: Record<string, string> = {};
  for (const [kind, stage, done, total, line] of [
    ['build', 'body', 2, null, 'Building geometry…'], ['build', 'write', 1, 2, 'Writing files 1/2…'],
    ['import', 'collect', 120, 628, 'Collecting parts 120/628…'], ['export', 'read', 0, null, 'Reading the document…'],
    ['snapshot', 'draw', 0, null, 'Drawing the picture…'], ['inspect-measure', 'measure', 37, 256, 'Measuring parts 37/256…'],
  ] as const) {
    const { unmount } = render(<ViewUpdateStatus status={modelUpdateStatus(loadingProgress(event(kind, stage, done, total)))} />);
    act(() => vi.advanceTimersByTime(150));
    said[`${kind}.${stage}`] = screen.getByRole('status').textContent ?? '';
    expect(said[`${kind}.${stage}`]).toBe(line);
    unmount();
  }
  // In the view's language: the key's words, the count beside them.
  render(<I18nProvider locale="ja"><ViewUpdateStatus status={modelUpdateStatus(loadingProgress(event('build', 'write', 1, 2)))} /></I18nProvider>);
  act(() => vi.advanceTimersByTime(150));
  expect(screen.getByRole('status').textContent).toBe('ファイルを書き込んでいます 1/2…');
});
