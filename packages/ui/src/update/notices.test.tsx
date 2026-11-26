import { useMemo } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unavailablePromptContext } from '@cad/core/prompt';
// The built package, as a host has it: the file viewer, the alert card and its context are one copy of each.
import { noticesOf, useUpdate } from '../../dist/update/index.js';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';
import { hostAlertSlot } from '../../dist/cad-viewer/hostAlert.js';
import { I18nProvider, translator } from '../../dist/i18n/index.js';
import type { NoticeDismissals, UpdateCalls, UpdateReply, UpdateState } from './index.js';

// The project's notices (`GET /api/v1/server`'s `cadNotices`), each said in the viewer's alert card until dismissed.
const MOVED = { id: 'install-moved', text: 'cad now installs another way.', url: 'https://texttocad.dev/docs/install' };
const PLAIN = { id: 'plain', text: 'Words <b>alone</b> & <script>no</script>.' };
const current: UpdateState = { version: '0.9.0', latest: null, state: 'idle' };
const reply = (cadNotices?: unknown, update: UpdateState | null = current): UpdateReply =>
  ({ release: '0.9.0', instance: 'first', cadUpdate: update, ...(cadNotices === undefined ? {} : { cadNotices: cadNotices as never }) });
const calls = (read: () => Promise<UpdateReply> = async () => reply([])): UpdateCalls =>
  ({ read: vi.fn(read), start: vi.fn(async () => reply([])), dismiss: vi.fn(async () => reply([])) });

const plain = defineFileRenderer({ id: 'plain', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
  load: async () => ({ default: () => <p>the model</p> }) });
const open = vi.fn(async (_url: string) => {});
const ports = (locale: string, framed: boolean) => ({
  files: { id: 'one', stat: async (path: string) => ({ path, name: path, kind: 'file' as const, extension: 'step', size: 1 }) },
  clipboard: { writeText: async () => {}, writeImage: async () => {} }, promptContext: unavailablePromptContext,
  environment: { colorScheme: 'light' as const, locale }, navigation: { openFile() {}, home() {} },
  // A page in a frame opens a link through its host (the CAD app's); else as an ordinary link.
  ...(framed ? { links: { open } } : {}),
});

// Where the host keeps what was dismissed: the viewer's browser storage, as every page of the browser shares it.
let kept: string[] = [];
const browser: NoticeDismissals = { dismissed: () => [...kept], dismiss: id => { kept = [...kept, id]; } };

function Host({ server, initial, locale = 'en', framed = false, dismissals = browser }: { server: UpdateCalls; initial: UpdateReply | null;
  locale?: string; framed?: boolean; dismissals?: NoticeDismissals | null }) {
  const updater = useUpdate(server, initial, { instance: initial?.instance, ...(dismissals ? { notices: dismissals } : {}) });
  const host = useMemo(() => ports(locale, framed), [locale, framed]);
  const renderers = useMemo(() => [plain], []);
  const alert = useMemo(() => hostAlertSlot(updater.alert, translator(locale)), [updater.alert, locale]);
  return <FileViewer file={null} host={host as never} renderers={renderers} state={{}} onStateChange={() => {}}
    presentation={{ home: <p>the home</p> }} alert={alert} update={null} />;
}
const show = (server: UpdateCalls, initial: UpdateReply | null, more: { locale?: string; framed?: boolean; dismissals?: NoticeDismissals | null } = {}) =>
  render(<I18nProvider locale={more.locale ?? 'en'}><Host server={server} initial={initial} {...more} /></I18nProvider>);
const cards = () => screen.queryAllByRole('alert');

beforeEach(() => {
  kept = [];
  open.mockClear();
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('no notice, no card: an empty list, an older server that says none, or nothing it can show', async () => {
  for (const given of [[], undefined, null, 'x', [{ id: '', text: 'no id' }, { id: 'x' }, 5]]) {
    show(calls(async () => reply(given)), reply(given));
    await act(async () => { fireEvent.focus(window); });
    expect(cards(), JSON.stringify(given)).toEqual([]);
    expect(screen.getByText('the home')).toBeTruthy();
    cleanup();
  }
});

it('a notice is the viewer\'s alert card: its words as text, Learn more to its link, and Dismiss, which this browser keeps', async () => {
  show(calls(async () => reply([MOVED, PLAIN])), reply([MOVED, PLAIN]));
  const [card] = cards();
  expect(card.closest('[data-host-alert]')).toBeTruthy();
  expect(within(card).getByRole('heading').textContent).toBe('cad now installs another way.');
  expect(card.querySelector('h2 svg')!.getAttribute('class')).toContain('text-warning');
  const link = within(card).getByRole('link', { name: 'Learn more' }) as HTMLAnchorElement;
  expect([link.href, link.target]).toEqual(['https://texttocad.dev/docs/install', '_blank']);
  expect(card.querySelector('[data-report-issue]')).toBeNull();  // the project's own word: no issue
  expect(within(card).getAllByRole('button').map(button => button.textContent)).toEqual(['Dismiss']);
  await act(async () => { fireEvent.click(within(card).getByRole('button', { name: 'Dismiss' })); });
  expect(kept).toEqual(['install-moved']);
  // The next, one card at a time: its words shown as given, as text and never as HTML; no link, none offered.
  const [next] = cards();
  expect(within(next).getByRole('heading').textContent).toBe(PLAIN.text);
  expect(next.querySelector('b, script')).toBeNull();
  expect(within(next).queryByRole('link')).toBeNull();
  await act(async () => { fireEvent.keyDown(document.body, { key: 'Escape' }); });
  expect(cards()).toEqual([]);
  expect(kept).toEqual(['install-moved', 'plain']);
  // A read that says them again, or another page of this browser: dismissed stays dismissed.
  await act(async () => { fireEvent.focus(window); });
  expect(cards()).toEqual([]);
  cleanup();
  show(calls(async () => reply([MOVED, PLAIN])), reply([MOVED, PLAIN]));
  expect(cards()).toEqual([]);
  // A new notice, under a new id, is shown.
  cleanup();
  show(calls(), reply([MOVED, { ...PLAIN, id: 'plain-2' }]));
  expect(within(cards()[0]).getByRole('heading').textContent).toBe(PLAIN.text);
});

it('a notice posted while the page is open shows at its next read; one taken down goes', async () => {
  let answer = reply([]);
  show(calls(async () => answer), answer);
  expect(cards()).toEqual([]);
  answer = reply([MOVED]);
  await act(async () => { fireEvent.focus(window); });
  expect(within(cards()[0]).getByRole('heading').textContent).toBe(MOVED.text);
  answer = reply([]);
  await act(async () => { fireEvent.focus(window); });
  expect(cards()).toEqual([]);
});

it('Learn more opens as the viewer opens every link: through the host where the page is in a frame', async () => {
  show(calls(), reply([MOVED]), { framed: true });
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('link', { name: 'Learn more' })); });
  expect(open).toHaveBeenCalledWith('https://texttocad.dev/docs/install');
});

it('a link that is not the project\'s own is never offered', () => {
  expect(noticesOf([{ ...MOVED, url: 'https://example.com/' }, { ...MOVED, id: 'b', url: 'javascript:alert(1)' },
    { ...MOVED, id: 'c', url: 'http://texttocad.dev/' }, { ...MOVED, id: 'd' }]))
    .toEqual([{ id: MOVED.id, text: MOVED.text }, { id: 'b', text: MOVED.text }, { id: 'c', text: MOVED.text }, { id: 'd', text: MOVED.text, url: MOVED.url }]);
});

it('a browser whose storage throws shows the notice, puts it away on this page, and shows it again next time, never failing', async () => {
  const refuse = () => { throw new DOMException('denied', 'SecurityError'); };
  const refusing: NoticeDismissals = { dismissed: refuse, dismiss: refuse };
  show(calls(async () => reply([MOVED])), reply([MOVED]), { dismissals: refusing });
  expect(cards()).toHaveLength(1);
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect(cards()).toEqual([]);
  cleanup();
  show(calls(async () => reply([MOVED])), reply([MOVED]), { dismissals: refusing });
  expect(cards()).toHaveLength(1);
});

it('a host that keeps no dismissals shows no notice', async () => {
  show(calls(async () => reply([MOVED])), reply([MOVED]), { dismissals: null });
  await act(async () => { fireEvent.focus(window); });
  expect(cards()).toEqual([]);
});

it('a failed update comes first; put away, the notices are said, and it waits behind its icon once they are dismissed', async () => {
  const failed = (dismissed: boolean): UpdateState => ({ version: '0.9.0', latest: '0.9.1', state: 'failed', cause: 'network', at: 7, dismissed });
  const server = { ...calls(async () => reply([MOVED], failed(true))), dismiss: vi.fn(async () => reply([MOVED], failed(true))) };
  show(server, reply([MOVED], failed(false)));
  expect(within(cards()[0]).getByRole('heading').textContent).toBe('Couldn’t update to 0.9.1');
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect(within(cards()[0]).getByRole('heading').textContent).toBe(MOVED.text);
  await act(async () => { fireEvent.click(within(cards()[0]).getByRole('button', { name: 'Dismiss' })); });
  expect(cards()).toEqual([]);
  expect(screen.getByRole('button', { name: 'Couldn’t update to 0.9.1' })).toBeTruthy();
});

it('its words in every language: Learn more and Dismiss, the notice\'s own as given', async () => {
  for (const [locale, learn, dismiss] of [['ja', '詳しく見る', '閉じる'], ['ko', '자세히 알아보기', '닫기'], ['zh-CN', '了解更多', '关闭'],
    ['zh-TW', '了解更多', '關閉']]) {
    show(calls(), reply([MOVED]), { locale });
    const [card] = cards();
    expect(within(card).getByRole('heading').textContent).toBe(MOVED.text);
    expect([within(card).getByRole('link').textContent, within(card).getByRole('button').textContent]).toEqual([learn, dismiss]);
    cleanup();
  }
});
