import { StrictMode, useMemo } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { unavailablePromptContext } from '@cad/core/prompt';
import { readFileSync } from 'node:fs';
import en from '../i18n/locales/en.js';
// The built package, as a host has it: the file viewer, the alert card and its context are one copy of each.
import { UPDATE_CAUSES, UPDATE_POLL_MS, UPDATE_READ_MS, UPDATE_REPORTABLE, UpdateButton, failureWords, useUpdate } from '../../dist/update/index.js';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';
import { hostAlertSlot } from '../../dist/cad-viewer/hostAlert.js';
import ViewerAlertCard, { useAlertDismissal } from '../../dist/renderers/kit/status/ViewerAlertCard.js';
import { I18nProvider, translator } from '../../dist/i18n/index.js';
import type { UpdateCalls, UpdateReply, UpdateState } from './index.js';

const behind = (state: Partial<UpdateState> = {}): UpdateState => ({ version: '0.9.0', latest: '0.9.1', state: 'idle', ...state });
const reply = (update: UpdateState | null, instance = 'first', release = '0.9.0'): UpdateReply => ({ release, instance, cadUpdate: update });
const LOG = '/home/ada/.local/state/cad/auto-update.log';
const failed = (cause: string, at = 100, more: Partial<UpdateState> = {}) => reply(behind({ state: 'failed', cause,
  said: `the server's words for ${cause}`, at, log: LOG, ...more }));

function calls({ read, start, dismiss }: Partial<UpdateCalls> = {}) {
  return {
    read: vi.fn<UpdateCalls['read']>(read ?? (async () => reply(behind()))),
    start: vi.fn<UpdateCalls['start']>(start ?? (async () => reply(behind({ state: 'working' })))),
    dismiss: vi.fn<UpdateCalls['dismiss']>(dismiss ?? (async () => reply(behind()))),
  };
}

const FILE = '/models/a.step';
const plain = defineFileRenderer({ id: 'plain', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
  load: async () => ({ default: () => <p>the model</p> }) });
// A file whose view says its own error, in the one card, put away into the navbar as a view's is.
const FILE_ALERT = { severity: 'error', title: 'Couldn’t update the model', message: 'The model’s latest build failed.', blocking: false };
const failing = defineFileRenderer({ id: 'failing', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
  load: async () => ({ default: ({ onNavigationActionsChange }: { onNavigationActionsChange?: (actions: readonly object[]) => void }) => {
    const { dismissed, dismiss } = useAlertDismissal(FILE_ALERT, { hasContent: true, scope: FILE, onNavigationActionsChange });
    return <div className="relative h-40"><p>the model</p><ViewerAlertCard alert={FILE_ALERT} hasContent dismissed={dismissed} onDismiss={dismiss} /></div>;
  } }) });
const writeText = vi.fn(async (_text: string) => {});
const ports = (locale: string, issues?: string) => ({
  files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file' as const, extension: 'step', size: 1 }) },
  clipboard: { writeText, writeImage: async () => {} }, promptContext: unavailablePromptContext,
  environment: { colorScheme: 'light' as const, locale }, navigation: { openFile() {}, home() {} },
  ...(issues ? { links: { issues, version: '0.9.0' } } : {}),
});

/** A host as the apps are: the update's state, its button in the navbar, its failure the viewer's alert (as `CadViewer` composes it). */
function Host({ server, initial = reply(behind()), followed = null, onRestarted, locale = 'en', file = null, renderer = plain, issues }: {
  server: UpdateCalls; initial?: UpdateReply | null; followed?: string | null; onRestarted?: (reply: UpdateReply) => void;
  locale?: string; file?: string | null; renderer?: typeof plain; issues?: string;
}) {
  const updater = useUpdate(server, initial, { instance: initial?.instance, followed, onRestarted });
  const host = useMemo(() => ports(locale, issues), [locale, issues]);
  const renderers = useMemo(() => [renderer], [renderer]);
  const alert = useMemo(() => hostAlertSlot(updater.alert, translator(locale)), [updater.alert, locale]);
  return <FileViewer file={file} host={host as never} renderers={renderers} state={{}} onStateChange={() => {}}
    presentation={{ home: <p>the home</p> }} alert={alert}
    update={updater.shown ? <UpdateButton state={updater.state} phase={updater.phase} onUpdate={updater.update} /> : null} />;
}
const show = (props: Parameters<typeof Host>[0]) => render(<I18nProvider locale={props.locale ?? 'en'}><Host {...props} /></I18nProvider>);
/** The navbar's right-hand controls, inside out, by name. */
const rightHand = () => [...document.querySelector('[data-viewer-navbar]')!.lastElementChild!.querySelectorAll('button')]
  .map(node => node.getAttribute('aria-label'));
const cards = () => screen.queryAllByRole('alert');
/** A click on the button, by its name. */
async function confirm(name = 'Update to 0.9.1') {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
}
/** Which lucide icon a button draws: lucide marks each svg with its name. */
const icon = (button: HTMLElement) => [...button.querySelector('svg')!.classList].find(name => /^lucide-(?!icon)/.test(name));

vi.mock('sonner', async original => ({ ...await original<object>(), toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(toast.success).mockClear();
  writeText.mockClear();
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); seen(true); });
/** The page shown or hidden, as a browser says it; `visibilitychange` sent where it changes. */
function seen(visible: boolean, { tell = false } = {}) {
  if (visible) delete (document as { visibilityState?: string }).visibilityState;
  else Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
  if (tell) document.dispatchEvent(new Event('visibilitychange'));
}

const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
/** The file's view up: its renderer loaded, the page's timers running meanwhile. */
async function opened() {
  for (let tries = 0; tries < 50 && !screen.queryByText('the model'); tries += 1) await advance(10);
  expect(screen.getByText('the model')).toBeTruthy();
}

it('is a blue icon, and nothing else, while the install is behind; nothing where it is current or cannot update itself', async () => {
  show({ server: calls() });
  const button = screen.getByRole('button', { name: 'Update to 0.9.1' });
  expect(button.className).toContain('bg-brand');
  expect(button.className).not.toContain('blue-');
  expect(button.textContent).toBe('');
  expect(cards()).toEqual([]);
  cleanup();
  show({ server: calls(), initial: reply(behind({ latest: null })) });
  expect(screen.queryByRole('button', { name: /^Update/ })).toBeNull();
  cleanup();
  show({ server: calls(), initial: reply(null) });
  expect(screen.queryByRole('button', { name: /^Update/ })).toBeNull();
});

it('a click updates: a ring that fills a stage at a time (asked, underway), the server gone while it restarts, then a spinner and the host reloads', async () => {
  const answers: Array<UpdateReply | Error> = [reply(behind({ state: 'working', at: 5, asked: true })), new TypeError('Failed to fetch'),
    reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1')];
  const server = calls({ start: async () => { await new Promise(resolve => setTimeout(resolve, 10)); return reply(behind({ state: 'working', at: 5, asked: true })); },
    read: async () => { const next = answers.shift() ?? reply(behind()); if (next instanceof Error) throw next; return next; } });
  const onRestarted = vi.fn();
  show({ server, onRestarted });
  await confirm();
  expect(server.start).toHaveBeenCalledOnce();
  expect(screen.getByRole('progressbar', { name: 'Updating to 0.9.1' }).getAttribute('aria-valuenow')).toBe('0');  // asked
  await advance(10);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');  // underway
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');  // the server gone: restarting
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
  show({ server, initial: reply(behind({ state: 'working', at: 5 })) });
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
  await advance(UPDATE_POLL_MS);
  expect(server.read).toHaveBeenCalledOnce();
  expect(server.start).not.toHaveBeenCalled();
});

it('one look: the download icon whenever a release is out, a failure too, its hint "Update"', async () => {
  for (const initial of [reply(behind()), failed('network')]) {
    show({ server: calls(), initial });
    const button = screen.getByRole('button', { name: 'Update to 0.9.1' });
    expect([icon(button), button.getAttribute('data-update'), button.textContent]).toEqual(['lucide-download', '', '']);
    expect(button.className).toContain('size-6');
    expect(button.className).toContain('bg-brand');
    // Its hint, under a resting pointer.
    await act(async () => { fireEvent.pointerMove(button, { pointerType: 'mouse' }); });
    await advance(450);
    expect(screen.queryAllByRole('tooltip').map(node => node.textContent)).toContain('Update');
    cleanup();
  }
});

it('a click acts at once and opens nothing; while an update installs or the server restarts there is no button', async () => {
  const onUpdate = vi.fn();
  const draw = (state: UpdateState, phase: Parameters<typeof UpdateButton>[0]['phase']) => <I18nProvider locale="en">
    <UpdateButton state={state} phase={phase} onUpdate={onUpdate} /></I18nProvider>;
  const view = render(draw(behind(), { phase: 'idle' }));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Update to 0.9.1' })); });
  expect(onUpdate).toHaveBeenCalledOnce();
  expect([screen.queryByRole('dialog'), screen.queryByRole('menu')]).toEqual([null, null]);
  for (const phase of [{ phase: 'working', done: 0, total: 3 }, { phase: 'restarting' }] as const) {
    view.rerender(draw(behind(), phase));
    expect(screen.queryByRole('button')).toBeNull();
  }
});

it('a refused click goes back to the button and says why', async () => {
  const refusal = Object.assign(new Error('HTTP 409'), { failure: { payload: { error: 'cad is pinned', cause: 'pinned' } } });
  show({ server: calls({ start: async () => { throw refusal; } }) });
  await confirm();
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  const [card] = cards();
  expect(within(card).getByRole('heading').textContent).toBe('Couldn’t update to 0.9.1');
  expect(card.textContent).toContain('cad is pinned to its release, so it doesn’t update itself: install it unpinned with `uv tool install --force cad`');
  expect(within(card).getByRole('button', { name: 'Try again' })).toBeTruthy();
});

it('a page that is seen reads the server again once a minute, and as it is shown again; a hidden one asks nothing', async () => {
  const answers = [reply(behind({ latest: null }))];
  const server = calls({ read: async () => answers.shift() ?? reply(behind()) });
  show({ server, initial: null });
  await advance(0);
  expect(server.read).toHaveBeenCalledOnce();  // nothing read before: read as the page starts
  expect(screen.queryByRole('button', { name: 'Update to 0.9.1' })).toBeNull();
  await advance(UPDATE_READ_MS);
  expect(server.read).toHaveBeenCalledTimes(2);
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();  // out meanwhile, shown by itself
  seen(false, { tell: true });
  await advance(3 * UPDATE_READ_MS);
  expect(server.read).toHaveBeenCalledTimes(2);
  // Shown again (a tab brought back fires no window focus): read at once, and each minute after.
  seen(true, { tell: true });
  await advance(0);
  expect(server.read).toHaveBeenCalledTimes(3);
  await advance(UPDATE_READ_MS);
  expect(server.read).toHaveBeenCalledTimes(4);
});

it('a page following an update asks where it is, and nothing besides', async () => {
  // The update's own read, never answered: any other read would be the minute's.
  const server = calls({ read: () => new Promise<UpdateReply>(() => {}) });
  show({ server, initial: reply(behind({ state: 'working', at: 5 })) });
  await advance(UPDATE_POLL_MS);
  expect(server.read).toHaveBeenCalledOnce();
  await advance(2 * UPDATE_READ_MS);
  expect(server.read).toHaveBeenCalledOnce();
});

it('a failed update is the viewer\'s alert over the home: its title, why and what to do, Try again, and Details with cad update and the log', async () => {
  const server = calls({ start: async () => reply(behind({ state: 'working' })) });
  show({ server, initial: failed('in_use') });
  const [card] = cards();
  // The card every error is said in, centred over the home: the red icon, the title, the words, and an X.
  expect(screen.getByText('the home')).toBeTruthy();
  expect(card.closest('[data-host-alert]')).toBeTruthy();
  expect(within(card).getByRole('heading').textContent).toBe('Couldn’t update to 0.9.1');
  expect(card.querySelector('h2 svg')!.getAttribute('class')).toContain('text-destructive');
  expect(card.textContent).toContain('A file uv was writing was in use by another program: try again.');
  expect(within(card).getByRole('button', { name: 'Dismiss' })).toBeTruthy();
  expect(card.querySelector('[data-report-issue]')).toBeNull();  // the person's to fix
  // Details: the terminal's way on and the update's log, copied whole, as a terminal can run it.
  expect(card.querySelector('[data-alert-details] pre')!.textContent).toBe(`cad update\n# The update's log: ${LOG}`);
  await act(async () => { fireEvent.click(within(card).getByRole('button', { name: 'Copy error details' })); });
  expect(writeText).toHaveBeenCalledWith(`cad update\n# The update's log: ${LOG}`);
  // The button stays, as it is offered; the card's Try again is its click.
  expect(screen.getByRole('button', { name: 'Update to 0.9.1' })).toBeTruthy();
  await act(async () => { fireEvent.click(within(card).getByRole('button', { name: 'Try again' })); });
  expect(server.start).toHaveBeenCalledOnce();
  expect(cards()).toEqual([]);  // a new attempt: the failure gone
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');  // the server's answer: underway
});

it('Report Issue is offered for cad\'s own causes alone, never for one that is the person\'s to fix', async () => {
  expect([...UPDATE_REPORTABLE].sort()).toEqual(['broken', 'helper_crash', 'helper_start', 'lost', 'start_failed', 'unknown']);
  for (const cause of [...UPDATE_CAUSES, 'a word of a later release']) {
    show({ server: calls(), initial: failed(cause), issues: 'https://example.test/issues/new' });
    const report = cards()[0].querySelector<HTMLAnchorElement>('[data-report-issue]');
    expect(Boolean(report), cause).toBe((UPDATE_REPORTABLE as readonly string[]).includes(cause));
    if (report) {
      const body = new URL(report.href).searchParams.get('body')!;
      expect(body, cause).toContain('**Couldn’t update to 0.9.1**');
      expect(body, cause).toContain('# The update\'s log: ~/.local/state/cad/auto-update.log');  // no home of this machine
    }
    cleanup();
  }
});

it('put away by its X or Escape it waits behind its icon, first of the navbar\'s right-hand controls, for every page; a new failure brings it back', async () => {
  let answer = failed('network', 42, { dismissed: true });
  // The server's answer to a read, and to the put away: it keeps the failure, put away.
  const server = calls({ read: async () => answer, dismiss: async () => failed('network', 42, { dismissed: true }) });
  show({ server, initial: failed('network', 42) });
  expect(rightHand()).toEqual(['Update to 0.9.1']);
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect(server.dismiss).toHaveBeenCalledWith(42);
  expect(cards()).toEqual([]);
  expect(rightHand()).toEqual(['Couldn’t update to 0.9.1', 'Update to 0.9.1']);
  // The server keeps it put away: a read says so, and the card stays away.
  await act(async () => { fireEvent.focus(window); });
  expect(cards()).toEqual([]);
  // Its icon brings it back, on this page; Escape puts it away again.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Couldn’t update to 0.9.1' })); });
  expect(cards()[0].textContent).toContain('Couldn’t reach the package index');
  expect(rightHand()).toEqual(['Update to 0.9.1']);
  await act(async () => { fireEvent.focus(window); });
  expect(cards()).toHaveLength(1);  // brought back: a read does not put it away again
  await act(async () => { fireEvent.keyDown(document.body, { key: 'Escape' }); });
  expect(cards()).toEqual([]);
  expect(server.dismiss).toHaveBeenCalledTimes(2);
  cleanup();
  // Another page, or this one reloaded: put away from the start, behind its icon.
  show({ server, initial: failed('network', 42, { dismissed: true }) });
  expect([cards(), rightHand()]).toEqual([[], ['Couldn’t update to 0.9.1', 'Update to 0.9.1']]);
  // A new attempt's failure is a new alert: it shows.
  answer = failed('disk_full', 50);
  await act(async () => { fireEvent.focus(window); });
  expect(cards()[0].textContent).toContain('The disk is full: free some space, then try again.');
  expect(rightHand()).toEqual(['Update to 0.9.1']);
});

it('over a file, the same card; one card at a time: a file\'s own error wins, and the update\'s waits behind it', async () => {
  show({ server: calls(), initial: failed('disk_full'), file: FILE });
  await opened();
  expect(cards().map(card => card.querySelector('h2')!.textContent)).toEqual(['Couldn’t update to 0.9.1']);
  expect(cards()[0].closest('[data-host-alert]')).toBeTruthy();
  cleanup();
  show({ server: calls({ dismiss: async () => failed('disk_full', 100, { dismissed: true }) }), initial: failed('disk_full'), file: FILE,
    renderer: failing });
  await opened();
  expect(cards().map(card => card.querySelector('h2')!.textContent)).toEqual(['Couldn’t update the model']);
  // The file's put away: its icon first, and the update's card, which waited, shows.
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect(cards().map(card => card.querySelector('h2')!.textContent)).toEqual(['Couldn’t update to 0.9.1']);
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect([cards(), rightHand()]).toEqual([[], ['Couldn’t update the model', 'Couldn’t update to 0.9.1', 'Update to 0.9.1']]);
  // The file's brought back: it takes the screen, and the update's stays behind its icon.
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Couldn’t update the model' })); });
  expect(cards().map(card => card.querySelector('h2')!.textContent)).toEqual(['Couldn’t update the model']);
});

it('the failure comes from the server: a page loaded afresh says it, and one that comes back to the page reads it', async () => {
  const server = calls({ read: async () => failed('disk_full') });
  show({ server });
  expect(cards()).toEqual([]);
  await act(async () => { fireEvent.focus(window); });
  expect(cards()[0].textContent).toContain('The disk is full: free some space, then try again.');
});

it('a refusal no attempt began from says why, from the answer, and is put away on this page alone', async () => {
  const refusal = Object.assign(new Error('HTTP 409'), { failure: { payload: {
    error: 'uv cannot be found, so no update can begin', cause: 'no_installer' } } });
  const server = calls({ start: async () => { throw refusal; } });
  show({ server });
  await confirm();
  const [card] = cards();
  expect(card.textContent).toContain('uv can’t be found, so cad can’t update itself: install cad again with `uv tool install --force cad` in a terminal.');
  expect(card.querySelector('[data-alert-details] pre')!.textContent).toBe('cad update');  // no attempt, no log
  await act(async () => { fireEvent.click(within(card).getByRole('button', { name: 'Dismiss' })); });
  expect(server.dismiss).not.toHaveBeenCalled();  // nothing to put away on the server
  expect(cards()).toEqual([]);
});

it('the reinstall sentences name the one command that installs cad again, from the server and from a refusal', async () => {
  const t = (key: string, params?: Record<string, unknown>) => String((en as Record<string, string>)[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ''));
  const uv = '`uv tool install --force cad`';
  for (const [cause, words] of [
    ['python', 'The release needs a newer Python than this cad runs on: install cad again with COMMAND in a terminal.'],
    ['no_installer', 'uv can’t be found, so cad can’t update itself: install cad again with COMMAND in a terminal.'],
    ['no_switch', 'This install of cad can’t switch to a newer release by itself: install cad again with COMMAND in a terminal.'],
  ]) {
    expect(failureWords({ cause }, t), cause).toBe(words.replace('COMMAND', uv));
  }
  // From the server's record of a failed attempt.
  show({ server: calls(), initial: failed('no_switch', 100) });
  expect(cards()[0].textContent).toContain(uv);
  cleanup();
  // From the refusal's answer.
  const refusal = Object.assign(new Error('HTTP 409'), { failure: { payload: { error: 'x', cause: 'python' } } });
  show({ server: calls({ start: async () => { throw refusal; } }) });
  await confirm();
  expect(cards()[0].textContent).toContain(uv);
});

it('every language\'s reinstall sentences take the command as a value, never spelling one', () => {
  for (const locale of ['en', 'ja', 'ko', 'zh-CN', 'zh-TW']) {
    const source = readFileSync(`src/i18n/locales/${locale}.js`, 'utf8');
    for (const cause of ['python', 'no_installer', 'no_switch', 'broken', 'pinned']) {
      const line = source.split('\n').find(row => row.includes(`"update.cause.${cause}"`))!;
      expect(line, `${locale} ${cause}`).toContain('`{command}`');
      expect(line, `${locale} ${cause}`).not.toMatch(/uv tool install|pipx install/);
    }
  }
});

it('the server restarted on the release before (the update failed): the page goes on following it and says why', async () => {
  const answers: Array<UpdateReply | Error> = [new TypeError('Failed to fetch'),
    reply(behind({ state: 'working', at: 5 }), 'second'), failed('start_failed', 5)];
  const server = calls({ read: async () => { const next = answers.shift() ?? failed('start_failed', 5); if (next instanceof Error) throw next; return next; } });
  const onRestarted = vi.fn();
  show({ server, initial: reply(behind({ state: 'working', at: 5 })), onRestarted });
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('2');
  await advance(UPDATE_POLL_MS);
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();  // its end not written yet
  await advance(UPDATE_POLL_MS);
  expect(onRestarted).not.toHaveBeenCalled();
  expect(cards()[0].textContent).toContain('The new release didn’t start, so cad went back to the release you had.');
});

it('a page loaded after the restart it followed: the spinner while the end is written, then that it is updated, once', async () => {
  const answers = [reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1')];
  const server = calls({ read: async () => answers.shift() ?? reply(behind({ latest: null, version: '0.9.1' }), 'second', '0.9.1') });
  render(<StrictMode><I18nProvider locale="en"><Host server={server} initial={reply(behind({ state: 'working', at: 5, version: '0.9.0' }), 'second', '0.9.1')}
    followed="0.9.0" /></I18nProvider></StrictMode>);
  expect(screen.getByRole('status', { name: 'Restarting with 0.9.1' })).toBeTruthy();
  await advance(UPDATE_POLL_MS);
  expect(toast.success).toHaveBeenCalledWith('Updated to 0.9.1.');
  expect(screen.queryByRole('button', { name: /^Update/ })).toBeNull();
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).toHaveBeenCalledOnce();
});

it('a page loaded with nothing followed says nothing of the release it runs', async () => {
  show({ server: calls({ read: async () => reply(behind({ latest: null })) }), initial: reply(behind({ latest: null })) });
  await act(async () => { fireEvent.focus(window); });
  expect(toast.success).not.toHaveBeenCalled();
});

it('says every cause in its own words, in every language, and one it does not know in the server\'s', () => {
  const t = (key: string, params?: Record<string, unknown>) => String((en as Record<string, string>)[key] ?? key)
    .replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ''));
  for (const cause of UPDATE_CAUSES) {
    const words = failureWords({ cause }, t);
    expect(words, cause).not.toBe(`update.cause.${cause}`);
    expect(words, cause).not.toContain('{');
  }
  expect(failureWords({ cause: 'config_exclude' }, t)).toBe(
    'Your uv settings exclude this release (exclude-newer): remove that setting, then try again.');
  expect(failureWords({ cause: 'a word of a later release', said: 'it says so' }, t)).toBe('it says so');
  expect(failureWords({ cause: '' }, t)).toBe(en['update.cause.other']);
  show({ server: calls(), initial: failed('network'), locale: 'ja' });
  expect(cards()[0].textContent).toContain('パッケージインデックスに接続できませんでした');
  expect(within(cards()[0]).getByRole('heading').textContent).toBe('0.9.1 にアップデートできませんでした');
  expect(within(cards()[0]).getByRole('button', { name: 'もう一度試す' })).toBeTruthy();
});
