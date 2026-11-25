import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { ViewerHostContext } from '../host/context.js';
import { I18nProvider } from '../i18n/index.js';
import en from '../i18n/locales/en.js';
import { UPDATE_CAUSES, UPDATE_POLL_MS, UpdateButton, failureWords, useUpdate,
  type UpdateCalls, type UpdateReply, type UpdateState } from './index.js';

const behind = (state: Partial<UpdateState> = {}): UpdateState => ({ version: '0.9.0', latest: '0.9.1', state: 'idle', ...state });
const reply = (update: UpdateState | null, instance = 'first', release = '0.9.0'): UpdateReply => ({ release, instance, cadUpdate: update });
const failed = (cause: string, at = 100) => reply(behind({ state: 'failed', cause, said: `the server's words for ${cause}`, installer: 'uv', at }));

function calls({ read, start, dismiss }: Partial<UpdateCalls> = {}) {
  return {
    read: vi.fn<UpdateCalls['read']>(read ?? (async () => reply(behind()))),
    start: vi.fn<UpdateCalls['start']>(start ?? (async () => reply(behind({ state: 'waiting' })))),
    dismiss: vi.fn<UpdateCalls['dismiss']>(dismiss ?? (async () => reply(behind()))),
  };
}

function Host({ server, initial = reply(behind()), followed = null, onRestarted, locale = 'en' }: {
  server: UpdateCalls; initial?: UpdateReply | null; followed?: string | null; onRestarted?: (reply: UpdateReply) => void; locale?: string;
}) {
  const { state, phase, failure, shown, update, dismiss } = useUpdate(server, initial,
    { instance: initial?.instance, followed, onRestarted });
  return <I18nProvider locale={locale}>{shown
    ? <UpdateButton state={state} phase={phase} failure={failure} onUpdate={update} onDismiss={dismiss} />
    : <p>Nothing to update</p>}</I18nProvider>;
}

vi.mock('sonner', async original => ({ ...await original<object>(), toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

beforeEach(() => { vi.useFakeTimers(); vi.mocked(toast.success).mockClear(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

it('is a blue icon, and nothing else, while the install is behind; nothing where it is current or cannot update itself', async () => {
  render(<Host server={calls()} />);
  const button = screen.getByRole('button', { name: 'Update to 0.9.1' });
  expect(button.className).toContain('bg-brand');
  expect(button.className).not.toContain('blue-');
  expect(button.textContent).toBe('');
  expect(screen.queryByRole('alert')).toBeNull();
  cleanup();
  render(<Host server={calls()} initial={reply(behind({ latest: null }))} />);
  expect(screen.getByText('Nothing to update')).toBeTruthy();
  cleanup();
  render(<Host server={calls()} initial={reply(null)} />);
  expect(screen.getByText('Nothing to update')).toBeTruthy();
});

it('a click updates: a ring that fills a stage at a time, the server gone while it installs, then a spinner and the host reloads', async () => {
  const answers: Array<UpdateReply | Error> = [reply(behind({ state: 'working', at: 5, asked: true })), new TypeError('Failed to fetch'),
    reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1')];
  const server = calls({ read: async () => { const next = answers.shift() ?? reply(behind()); if (next instanceof Error) throw next; return next; } });
  const onRestarted = vi.fn();
  render(<Host server={server} onRestarted={onRestarted} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(server.start).toHaveBeenCalledOnce();
  expect(screen.getByRole('progressbar', { name: 'Updating to 0.9.1' }).getAttribute('aria-valuenow')).toBe('0');
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');  // the server gone: installing
  await advance(UPDATE_POLL_MS);
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  expect(onRestarted).toHaveBeenCalledOnce();  // another start of the server, of another release: the host reloads
  const asked = server.read.mock.calls.length;
  await advance(10 * UPDATE_POLL_MS);
  expect(server.read.mock.calls.length).toBe(asked);
});

it('an automatic update the page finds underway shows its progress and is followed the same way', async () => {
  const server = calls({ read: async () => reply(behind({ state: 'working', at: 5 })) });
  render(<Host server={server} initial={reply(behind({ state: 'working', at: 5 }))} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  await advance(UPDATE_POLL_MS);
  expect(server.read).toHaveBeenCalledOnce();
  expect(server.start).not.toHaveBeenCalled();
});

it('a failure says why and what to do, with cad update to copy, stays through a press elsewhere, and a click tries again', async () => {
  const writeText = vi.fn(async () => {});
  const server = calls({ start: async () => reply(behind({ state: 'waiting' })) });
  render(<ViewerHostContext.Provider value={{ clipboard: { writeText } } as never}>
    <Host server={server} initial={failed('in_use')} /></ViewerHostContext.Provider>);
  const card = screen.getByRole('alert');
  expect(card.textContent).toContain('Couldn’t update to 0.9.1');
  expect(card.textContent).toContain('cad is in use by another program: close the apps using cad, then try again.');
  expect(card.textContent).toContain('cad update');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy command' })); });
  expect(writeText).toHaveBeenCalledWith('cad update');
  expect(screen.getByRole('button', { name: 'Copied' })).toBeTruthy();
  await act(async () => { fireEvent.pointerDown(document.body); fireEvent.mouseDown(document.body); });
  expect(screen.getByRole('alert')).toBeTruthy();
  expect(server.dismiss).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Try again' })); });
  expect(server.start).toHaveBeenCalledOnce();
  expect(screen.queryByRole('alert')).toBeNull();  // a new attempt: the failure gone
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0');
});

it('a failure put away is put away on the server, for every page and through a reload', async () => {
  const server = calls();
  render(<Host server={server} initial={failed('network', 42)} />);
  expect(screen.getByRole('alert').textContent).toContain('Couldn’t reach the package index');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Dismiss' })); });
  expect(server.dismiss).toHaveBeenCalledWith(42);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();  // offered again
});

it('the failure comes from the server: a page loaded afresh says it, and one that comes back to the page reads it', async () => {
  const server = calls({ read: async () => failed('disk_full') });
  render(<Host server={server} />);
  expect(screen.queryByRole('alert')).toBeNull();
  await act(async () => { fireEvent.focus(window); });
  expect(screen.getByRole('alert').textContent).toContain('The disk is full: free some space, then try again.');
});

it('a refusal no attempt began from says why, from the answer', async () => {
  const refusal = Object.assign(new Error('HTTP 409'), { failure: { payload: {
    error: 'uv cannot be found, so no update can begin', cause: 'no_installer', installer: 'uv' } } });
  const server = calls({ start: async () => { throw refusal; } });
  render(<Host server={server} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(screen.getByRole('alert').textContent).toContain('uv can’t be found, so cad can’t update itself: update in a terminal.');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Dismiss' })); });
  expect(server.dismiss).not.toHaveBeenCalled();  // nothing to put away on the server
  expect(screen.queryByRole('alert')).toBeNull();
});

it('the server restarted on the release before (the update failed): the page goes on following it and says why', async () => {
  const answers: Array<UpdateReply | Error> = [new TypeError('Failed to fetch'),
    reply(behind({ state: 'working', at: 5 }), 'second'), failed('kept', 5)];
  const server = calls({ read: async () => { const next = answers.shift() ?? failed('kept', 5); if (next instanceof Error) throw next; return next; } });
  const onRestarted = vi.fn();
  render(<Host server={server} initial={reply(behind({ state: 'working', at: 5 }))} onRestarted={onRestarted} />);
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();  // its end not written yet
  await advance(UPDATE_POLL_MS);
  expect(onRestarted).not.toHaveBeenCalled();
  expect(screen.getByRole('alert').textContent).toContain('uv kept the release you have, though a newer one is out');
});

it('a page loaded after the restart it followed: the spinner while the end is written, then that it is updated, once', async () => {
  const answers = [reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1')];
  const server = calls({ read: async () => answers.shift() ?? reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1') });
  render(<StrictMode><Host server={server} initial={reply(behind({ state: 'working', at: 5, version: '0.9.0' }), 'second', '0.9.1')}
    followed="0.9.0" /></StrictMode>);
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  await advance(UPDATE_POLL_MS);
  expect(toast.success).toHaveBeenCalledWith('Updated to 0.9.1.');
  expect(screen.getByText('Nothing to update')).toBeTruthy();
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).toHaveBeenCalledOnce();
});

it('a page loaded with nothing followed says nothing of the release it runs', async () => {
  render(<Host server={calls({ read: async () => reply(behind({ latest: null })) })} initial={reply(behind({ latest: null }))} />);
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).not.toHaveBeenCalled();
});

it('says every cause in its own words, in every language, and one it does not know in the server\'s', () => {
  const t = (key: string, params?: Record<string, unknown>) => String((en as Record<string, string>)[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ''));
  for (const cause of UPDATE_CAUSES) {
    const words = failureWords({ cause, installer: 'pipx' }, t);
    expect(words, cause).not.toBe(`update.cause.${cause}`);
    expect(words, cause).not.toContain('{');
  }
  expect(failureWords({ cause: 'config_exclude', installer: 'uv' }, t)).toBe(
    'Your uv settings exclude this release (exclude-newer): remove that setting, then try again.');
  expect(failureWords({ cause: 'a word of a later release', said: 'it says so' }, t)).toBe('it says so');
  expect(failureWords({ cause: '' }, t)).toBe(en['update.cause.other']);
  render(<Host server={calls()} initial={failed('network')} locale="ja" />);
  expect(screen.getByRole('alert').textContent).toContain('パッケージインデックスに接続できませんでした');
});
