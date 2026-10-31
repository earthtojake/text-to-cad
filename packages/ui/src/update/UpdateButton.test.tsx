import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { UPDATE_POLL_MS, UpdateButton, pageHasUnsaved, reloadWhenClean, useUpdate, type UpdateCall, type UpdateReply } from './index.js';

const NOTICE = { latest: '0.9.1', version: '0.9.0' };
const reply = (update: UpdateReply['update'], notice = NOTICE): UpdateReply => ({ notice, release: '0.9.0', update });
const working = (done: number) => reply({ state: 'working', target: '0.9.1', progress: { stage: 'install', done, total: 4 }, error: null });

function Host({ read, start, initial = NOTICE, onFailed }: {
  read: UpdateCall; start: UpdateCall; initial?: typeof NOTICE | null; onFailed?: (error: string) => void;
}) {
  const { notice, phase, update } = useUpdate({ read, start }, initial, { onFailed });
  return notice || phase.phase !== 'idle' ? <UpdateButton notice={notice} phase={phase} onUpdate={update} /> : <p>No notice</p>;
}

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

it('is an icon, and nothing else: no popover, no words beside it', () => {
  render(<Host read={async () => reply(null)} start={async () => reply(null)} />);
  const button = screen.getByRole('button', { name: 'Update to 0.9.1' });
  expect(button.className).toContain('bg-blue-500');
  expect(button.textContent).toBe('');
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('a click updates: a ring that fills while it installs, a spinner while the engine restarts, and no more asking', async () => {
  const start = vi.fn<UpdateCall>(async () => working(0));
  const answers = [working(1), working(2), reply({ state: 'restarting', target: '0.9.1', progress: { stage: 'restart', done: 3, total: 4 } })];
  const read = vi.fn<UpdateCall>(async () => answers.shift() ?? reply(null));
  render(<Host read={read} start={start} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(start).toHaveBeenCalledOnce();
  expect(screen.getByRole('progressbar', { name: 'Updating to 0.9.1' }).getAttribute('aria-valuenow')).toBe('0');
  await act(async () => { await vi.advanceTimersByTimeAsync(UPDATE_POLL_MS); });
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  await act(async () => { await vi.advanceTimersByTimeAsync(2 * UPDATE_POLL_MS); });
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  const asked = read.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(10 * UPDATE_POLL_MS); });
  expect(read.mock.calls.length).toBe(asked);  // the engine goes: the host follows it back, not this button
});

it('a failed update says its one line once and offers itself again', async () => {
  const onFailed = vi.fn();
  const failed = reply({ state: 'failed', target: '0.9.1', error: 'no network' });
  render(<Host read={async () => failed} start={async () => failed} onFailed={onFailed} />);
  await act(async () => { fireEvent.focus(window); });
  expect(onFailed).not.toHaveBeenCalled();  // another page's update, failed before this one looked
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(onFailed).toHaveBeenCalledWith('no network');
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  await act(async () => { fireEvent.focus(window); });
  expect(onFailed).toHaveBeenCalledOnce();  // the engine still says it failed: said once
});

it('draws with the page from what the host knew, and reads the server again only when the person comes back', async () => {
  const read = vi.fn<UpdateCall>(async () => reply(null, null as never));
  render(<Host read={read} start={read} />);
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  expect(read).not.toHaveBeenCalled();
  await act(async () => { fireEvent.focus(window); });
  expect(read).toHaveBeenCalledOnce();
  expect(screen.getByText('No notice')).toBeTruthy();  // the install is current now
});

it('a page opened while another one updates follows that update', async () => {
  const answers = [working(2), reply({ state: 'restarting', target: '0.9.1' })];
  const read = vi.fn<UpdateCall>(async () => answers.shift() ?? reply(null));
  render(<Host read={read} start={read} />);
  await act(async () => { fireEvent.focus(window); });
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');
  await act(async () => { await vi.advanceTimersByTimeAsync(UPDATE_POLL_MS); });
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
});

it('a reload waits while a field holds what the person is typing', () => {
  const input = document.createElement('input');
  document.body.append(input);
  input.focus();
  expect(pageHasUnsaved()).toBe(false);  // an empty field loses nothing
  input.value = 'make the bracket 2 mm thicker';
  expect(pageHasUnsaved()).toBe(true);
  const reload = vi.fn();
  const cancel = reloadWhenClean(reload);
  vi.advanceTimersByTime(5000);
  expect(reload).not.toHaveBeenCalled();
  input.blur();
  vi.advanceTimersByTime(0);
  expect(reload).toHaveBeenCalledOnce();
  cancel();
  input.remove();
});
