import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { UPDATE_POLL_MS, UpdateButton, pageHasUnsaved, reloadWhenClean, useUpdate, type UpdateCall, type UpdateReply } from './index.js';

const NOTICE = { latest: '0.9.1', version: '0.9.0' };
const reply = (update: UpdateReply['update'], notice = NOTICE): UpdateReply => ({ notice, release: '0.9.0', update });
const working = (done: number) => reply({ state: 'working', target: '0.9.1', progress: { stage: 'install', done, total: 4 }, error: null });

function Host({ read, start, initial = NOTICE, onFailed, followed }: {
  read: UpdateCall; start: UpdateCall; initial?: typeof NOTICE | null; onFailed?: (error: string) => void; followed?: boolean;
}) {
  const { notice, phase, update } = useUpdate({ read, start }, initial, { onFailed, followed });
  return notice || phase.phase !== 'idle' ? <UpdateButton notice={notice} phase={phase} onUpdate={update} /> : <p>No notice</p>;
}

vi.mock('sonner', async original => ({ ...await original<object>(), toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

beforeEach(() => { vi.useFakeTimers(); vi.mocked(toast.success).mockClear(); });
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

it('a page reloaded into the engine its update restarted says the switch failed, once, and offers itself again', async () => {
  // The engine the failed switch started again says so (`update.Update.recall`); the page that followed the
  // update loads anew into it (the host keeps that it followed: `followed`), in React's strict mode as the viewer is.
  const onFailed = vi.fn();
  const error = "text-to-cad 0.9.1's engine did not start";
  const read = vi.fn<UpdateCall>(async () => reply({ state: 'failed', target: '0.9.1', error }));
  render(<StrictMode><Host read={read} start={read} onFailed={onFailed} followed /></StrictMode>);
  await act(async () => {});
  expect(read).toHaveBeenCalledOnce();
  expect(onFailed).toHaveBeenCalledWith(error);
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  await act(async () => { fireEvent.focus(window); });
  expect(onFailed).toHaveBeenCalledOnce();
});

it('a page reloaded into the engine its update moved to says it is updated, once, as a toast', async () => {
  // The web page that followed the update loads anew into the new release's engine, whose update is idle.
  const onFailed = vi.fn();
  const read = vi.fn<UpdateCall>(async () => ({ notice: null, release: '0.9.1', update: { state: 'idle' } }));
  render(<StrictMode><Host read={read} start={read} onFailed={onFailed} followed /></StrictMode>);
  await act(async () => {});
  expect(read).toHaveBeenCalledOnce();
  expect(toast.success).toHaveBeenCalledWith('Updated to 0.9.1.');
  expect(screen.getByText('No notice')).toBeTruthy();  // the install is current
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).toHaveBeenCalledOnce();
  expect(onFailed).not.toHaveBeenCalled();
});

it('a page loaded with nothing followed says nothing of the release it runs', async () => {
  const read = vi.fn<UpdateCall>(async () => ({ notice: null, release: '0.9.1', update: { state: 'idle' } }));
  render(<Host read={read} start={read} />);
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).not.toHaveBeenCalled();
});

it('a host that keeps its page through the restart ends it on a switch that failed: said once, offered again', async () => {
  // A CAD card keeps its frame while the engine restarts and reads the engine itself (`settle`): the engine
  // the failed switch started again answers with the card's own release, the update failed.
  const onFailed = vi.fn();
  const restarting = reply({ state: 'restarting', target: '0.9.1' });
  const failed = reply({ state: 'failed', target: '0.9.1', error: "text-to-cad 0.9.1's engine did not start" });
  let settle: (answer: UpdateReply) => void = () => {};
  function Card() {
    const updater = useUpdate({ read: async () => restarting, start: async () => restarting }, NOTICE, { onFailed });
    settle = updater.settle;
    return <UpdateButton notice={updater.notice} phase={updater.phase} onUpdate={updater.update} />;
  }
  render(<Card />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  await act(async () => { settle(restarting); });  // the engine before, still draining: the restart goes on
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  await act(async () => { settle(failed); });
  expect(onFailed).toHaveBeenCalledWith("text-to-cad 0.9.1's engine did not start");
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  await act(async () => { settle(failed); });
  expect(onFailed).toHaveBeenCalledOnce();
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
