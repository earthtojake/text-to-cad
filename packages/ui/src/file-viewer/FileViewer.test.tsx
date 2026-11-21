import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { isMissingFileError } from '@cad/core/client';
import { unavailablePromptContext } from '@cad/core/prompt';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';
import { DropdownMenuItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger } from '../../dist/primitives/dropdown-menu.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';
import { usePanelToggles } from '../../dist/file-viewer/panelToggles.js';
import { PANEL_PEEK_DELAY_MS } from '../../dist/file-viewer/panelPeek.js';
import { ModelLibrary } from '../../dist/library/ModelLibrary.js';
import { readFileSync } from 'node:fs';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FILE = '/models/parts/a.step';
const renderer = defineFileRenderer({
  id: 'plain', priority: 1, matches: () => true,
  load: async () => ({ default: () => <p>shown</p> }),
  prepare: async () => ({ data: null }),
});
// A host that shows one file and browses nothing, has no home and can do nothing with the file.
const host = {
  files: { id: 'one', stat: async (path: string) => ({ path, name: path.split('/').pop()!, kind: 'file' as const, extension: 'step', size: 1 }) },
  clipboard: { writeText: async () => {}, writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, navigation: { openFile(_path: string) {} },
};
const open = (props: { host?: object; file?: string | null; presentation?: object }) =>
  render(<FileViewer file={FILE} host={host as any} renderers={[renderer]} state={{}} onStateChange={() => {}} {...props as any} />);
const navbar = () => document.querySelector('[data-viewer-navbar]');
const fileName = () => document.querySelector<HTMLElement>('[data-file-name]')!;
const labels = (selector = '[data-viewer-navbar]') => [...document.querySelectorAll(`${selector} a, ${selector} button`)].map(node => node.getAttribute('aria-label'));

it('never names a document by its id: while it opens, the name the host hands, else none; once read, its own', async () => {
  const ID = '906f6bff-80e7-5331-b842-dd377b720a7b';
  let answer = (_name: string) => {};
  const slow = { ...host, files: { id: 'slow', stat: (path: string) => new Promise(resolve => {
    answer = name => resolve({ path, name, kind: 'file', extension: 'xbf', size: 1, navigationPath: null }); }) } };
  const view = open({ host: slow, file: ID });
  expect(fileName().textContent).toBe('');
  view.rerender(<FileViewer file={ID} name="qdd_actuator" host={slow as any} renderers={[renderer]} state={{}} onStateChange={() => {}} />);
  expect(fileName().textContent).toBe('qdd_actuator');
  await act(async () => answer('qdd actuator'));
  await screen.findByText('shown');
  expect(fileName().textContent).toBe('qdd actuator');
});

it('has the panel\'s toggle from a document page\'s first frame, in the state its view opens with, and its frame where it is open', async () => {
  const ID = '906f6bff-80e7-5331-b842-dd377b720a7b';
  let answer = () => {};
  const slow = { ...host, files: { id: 'slow', stat: (path: string) => new Promise(resolve => {
    answer = () => resolve({ path, name: 'qdd_actuator', kind: 'file', extension: 'xbf', size: 1, navigationPath: null }); }) } };
  // A view with a frame says its toggle, open, as the frame would: the panel open by default.
  const framed = defineFileRenderer({ id: 'framed', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: () => { usePanelToggles(React.useMemo(() => ({ left: { open: true, label: 'Hide panel', toggle() {} } }), [])); return <p>shown</p>; } }) });
  const toggle = () => document.querySelector<HTMLElement>('[data-navbar-panel="left"]');
  const look = () => [toggle()?.getAttribute('aria-expanded'), toggle()?.getAttribute('aria-disabled'), Boolean(document.querySelector('aside[data-panel-loading]')), fileName().textContent];
  const view = render(<FileViewer file={ID} host={slow as any} renderers={[framed]} state={{}} onStateChange={() => {}} />);
  // The first frame: the toggle, open and pressable already, the panel's frame in its place, and no id for a name. The
  // frame is drawn as the view's loading panel is: the head's one block (a bar for the title not known yet), then the
  // placeholder rows, busy (their places against the view's are `PanelInset.browser.test.mjs`'s).
  expect(look()).toEqual(['true', null, true, '']);
  const frame = document.querySelector('aside[data-panel-loading]')!;
  expect([frame.getAttribute('aria-busy'), Boolean(frame.querySelector('[data-panel-head] [data-panel-loading-title]')),
    frame.querySelectorAll('[data-tree-row-placeholder]').length, within(frame as HTMLElement).getByRole('status').textContent]).toEqual(['true', true, 6, 'Loading']);
  await act(async () => answer());
  await screen.findByText('shown');
  expect(look()).toEqual(['true', null, false, 'qdd_actuator']);
  view.unmount();
  // The file's choice for this session, closed: the toggle says so, and no frame is drawn.
  render(<FileViewer file={ID} host={slow as any} renderers={[framed]} state={{ renderers: { [JSON.stringify([ID, 'framed'])]: { panel: { open: false } } } }} onStateChange={() => {}} />);
  expect(look()).toEqual(['false', null, false, '']);
  cleanup();
  // The view's own rule (`sidebars.js`): with no choice, an 800px view (under 640px + the default 232px) has it
  // collapsed; the person's choice, open, holds there all the same, its frame at the width the view will draw (a
  // stored 660px within the grip's 480px bound).
  const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 800, height: 700, top: 0, left: 0, right: 800, bottom: 700, x: 0, y: 0, toJSON() {} } as DOMRect);
  render(<FileViewer file={ID} host={slow as any} renderers={[framed]} state={{}} onStateChange={() => {}} layout="desktop" />);
  expect(look()).toEqual(['false', null, false, '']);
  cleanup();
  render(<FileViewer file={ID} host={slow as any} renderers={[framed]} state={{ renderers: { [JSON.stringify([ID, 'framed'])]: { panel: { open: true, width: 660 } } } }} onStateChange={() => {}} layout="desktop" />);
  expect([...look(), document.querySelector<HTMLElement>('aside[data-panel-loading]')?.style.width]).toEqual(['true', null, true, '', '480px']);
  rect.mockRestore();
  cleanup();
  // A file that will not open has neither.
  render(<FileViewer file={ID} host={{ ...host, files: { id: 'gone', stat: async () => { throw new Error('gone'); } } } as any} renderers={[framed]} state={{}} onStateChange={() => {}} />);
  await screen.findByText('gone');
  expect(toggle()).toBeNull();
});

it('peeks the stand-in panel from a page\'s first frame, a mouse resting on the collapsed toggle, and a press there pins it as the view\'s toggle does', async () => {
  const ID = '906f6bff-80e7-5331-b842-dd377b720a7b';
  let answer = () => {};
  const slow = { ...host, files: { id: 'slow', stat: (path: string) => new Promise(resolve => {
    answer = () => resolve({ path, name: 'qdd_actuator', kind: 'file', extension: 'xbf', size: 1, navigationPath: null }); }) } };
  const framed = defineFileRenderer({ id: 'framed', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: () => { usePanelToggles(React.useMemo(() => ({ left: { open: true, label: 'Hide panel', toggle() {} } }), [])); return <p>shown</p>; } }) });
  const toggle = () => document.querySelector<HTMLElement>('[data-navbar-panel="left"]')!;
  const writes: unknown[] = [];
  vi.useFakeTimers();
  try {
    // The file's choice, collapsed: nothing of the panel over the page until a mouse rests on the toggle.
    render(<FileViewer file={ID} host={slow as any} renderers={[framed]} state={{ renderers: { [JSON.stringify([ID, 'framed'])]: { panel: { open: false } } } }}
      onStateChange={next => writes.push(next)} layout="desktop" />);
    expect(document.querySelector('aside[data-panel-loading]')).toBeNull();
    fireEvent.pointerEnter(toggle(), { pointerType: 'mouse' });
    act(() => { vi.advanceTimersByTime(PANEL_PEEK_DELAY_MS - 1); });
    expect(document.querySelector('aside[data-panel-peek]')).toBeNull();
    act(() => { vi.advanceTimersByTime(1); });
    const card = document.querySelector<HTMLElement>('aside[data-panel-peek][data-panel-loading]')!;
    expect([Boolean(card.querySelector('[data-panel-peek-card]')), Boolean(card.querySelector('[data-panel-head] [data-panel-loading-title]')),
      card.querySelectorAll('[data-tree-row-placeholder]').length, toggle().getAttribute('aria-expanded')]).toEqual([true, true, 6, 'false']);
    // A press pins it: the stand-in docked in its place, open, the peek gone.
    fireEvent.click(toggle());
    expect([toggle().getAttribute('aria-expanded'), document.querySelector('aside[data-panel-peek]'), Boolean(document.querySelector('aside[data-panel-loading]'))])
      .toEqual(['true', null, true]);
  } finally {
    vi.useRealTimers();
  }
  // The view opens with that choice and writes it, as its own toggle would.
  await act(async () => answer());
  await screen.findByText('shown');
  const last = writes.at(-1) as { renderers: Record<string, { panel?: { open?: boolean } }> };
  expect(last.renderers[JSON.stringify([ID, 'framed'])].panel).toEqual({ open: true });
});

it('draws the navbar over every file, named by its name, and over the home with only its menu, Back and Forward, the host\'s actions; never over a view shown small', async () => {
  open({});
  await screen.findByText('shown');
  // The name, as words where nothing can be browsed; no logo with no home, no ⋯ where the host can do nothing.
  expect([fileName().textContent, fileName().tagName]).toEqual(['a.step', 'SPAN']);
  expect(labels()).toEqual([]);
  cleanup();
  open({ host: { ...host, environment: { colorScheme: 'light', compact: true } } });
  await screen.findByText('shown');
  expect(navbar()).toBeNull();
  cleanup();
  // The home has the same navbar: the logo's menu, Back and Forward where the host keeps the view's
  // history, and the host's actions, as over a file; no file, no box for view controls.
  const back = vi.fn();
  open({ host: { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home() {} } }, file: null,
    history: { canGoBack: true, canGoForward: false, back, forward() {} },
    navbarActions: <button type="button" aria-label="Full size" />,
    presentation: { home: <p>home</p> } } as any);
  await screen.findByText('home');
  expect([labels(), document.querySelector('[data-file-name]'), document.querySelector('[data-view-controls]')])
    .toEqual([['Menu', 'Back', 'Forward', 'Full size'], null, null]);
  expect((screen.getByRole('button', { name: 'Forward' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Back' }));
  expect(back).toHaveBeenCalledOnce();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Menu' }));
  expect(screen.queryByRole('menuitem', { name: 'Back to home' })).toBeNull();
});

it('draws the view\'s panel toggle first in the navbar, before the logo: the same neutral button open or shut, its state aria-expanded, its icon the sidebar\'s; none over the home', async () => {
  const user = userEvent.setup();
  const left = vi.fn();
  // A view whose frame says its toggle, as `ViewFrame.jsx` does.
  const toggling = defineFileRenderer({ id: 'panels', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: function Panels() {
      const [shown, setShown] = React.useState(false);
      // The panel peeking under the toggle (`usePanelPeek.js`), as a rest on it makes it.
      const [peeking, setPeeking] = React.useState(false);
      usePanelToggles(React.useMemo(() => ({ left: { open: shown, label: shown ? 'Hide panel' : 'Show panel', shortcut: '⌘\\', peeking,
        toggle: () => { left(); setShown(value => !value); } } }), [shown, peeking]));
      return <><p>shown</p><button type="button" aria-label="Peek" onClick={() => setPeeking(value => !value)} /></>;
    } }) });
  const actionsHost = { ...host, navigation: { ...(host as any).navigation, home() {} }, fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } } };
  render(<FileViewer file={FILE} host={actionsHost as any} renderers={[toggling]} state={{}} onStateChange={() => {}} navbarActions={<button type="button" aria-label="Full size" />} />);
  await screen.findByText('shown');
  const toggle = () => navbar()!.querySelector<HTMLElement>('[data-navbar-panel="left"]')!;
  await waitFor(() => expect(toggle()).not.toBeNull());
  // The toggle, then the logo, then the name and its ⋯; nothing of it at the row's right.
  const order = [...navbar()!.querySelectorAll('[data-navbar-menu], [data-file-name], [data-testid="file-actions"], [data-navbar-panel], [aria-label="Full size"]')]
    .map(node => node.getAttribute('data-navbar-panel') ?? (node.hasAttribute('data-navbar-menu') ? 'logo' : null) ?? node.getAttribute('aria-label') ?? (node.hasAttribute('data-file-name') ? 'name' : '?'));
  expect(order).toEqual(['left', 'logo', 'name', 'File actions', 'Full size']);
  const look = () => [toggle().getAttribute('aria-label'), toggle().getAttribute('aria-expanded'), toggle().getAttribute('aria-pressed'), toggle().getAttribute('data-variant')];
  expect(look()).toEqual(['Show panel', 'false', null, 'ghost']);
  // Its icon: the sidebar's own (a rounded rectangle and a short line), not lucide's panel.
  expect([Boolean(toggle().querySelector('svg[data-sidebar-icon] rect[rx="3"]')), toggle().querySelector('.lucide-panel-left'),
    toggle().className.includes('size-control'), toggle().getAttribute('aria-keyshortcuts')]).toEqual([true, null, true, '⌘\\']);
  // Its tooltip shows on a rest on it; once the panel peeks under it, it goes (the pointer still on it): the panel is
  // showing, which is what the tip offered.
  await user.hover(toggle());
  expect((await screen.findByRole('tooltip')).textContent).toContain('Show panel');
  fireEvent.click(screen.getByRole('button', { name: 'Peek' }));
  await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull());
  fireEvent.click(screen.getByRole('button', { name: 'Peek' }));
  await user.click(toggle());
  // Open, the same neutral button: only its name and aria-expanded say so.
  expect(look()).toEqual(['Hide panel', 'true', null, 'ghost']);
  expect(left.mock.calls.length).toBe(1);
  cleanup();
  // The home: no toggle.
  open({ host: { ...host, navigation: { openFile() {}, home() {} } }, file: null, presentation: { home: <p>home</p> } } as any);
  await screen.findByText('home');
  expect(navbar()!.querySelector('[data-navbar-panel]')).toBeNull();
});

it('draws the home\'s own controls in its navbar on the grid\'s column: the logo, then Recent and its count, at the left, the search and Open at the right; the filter and the layout in a row over the grid', async () => {
  const user = userEvent.setup();
  const models = [{ path: '/work/a.step', name: 'a.step', folder: '/work', opened: 1, updated: 1, created: null, pinned: false, missing: false, thumbnail: null, pictured: null },
    { path: 'model-1', name: 'bracket', folder: null, opened: 1, updated: 1, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, kind: 'model' }];
  const library = { list: async () => models, change: async () => models, thumbnail: async () => null, open: async () => {}, pick: async () => {} };
  // A 1440px row: the grid's column is 1128px, centred, on 24px gutters.
  const boxes = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const width = this.hasAttribute('data-viewer-navbar') ? 1440 : this.matches('nav') ? 36 : 0;
    return { x: 0, y: 0, left: 0, top: 0, right: width, bottom: 40, width, height: 40, toJSON() {} } as DOMRect;
  });
  open({ host: { ...host, navigation: { openFile() {}, home() {} } }, file: null,
    presentation: { home: <ModelLibrary library={library as any} onLayoutChange={() => {}} /> } } as any);
  await screen.findByText('a.step');
  const home = navbar()!.querySelector<HTMLElement>('[data-navbar-home]')!;
  const left = home.querySelector('[data-navbar-home-left]')!, right = home.querySelector('[data-navbar-home-right]')!;
  expect([left.querySelector('h1')!.textContent, right.querySelector('input')!.getAttribute('aria-label'), within(right as HTMLElement).getByRole('button', { name: 'Open' }) !== null])
    .toEqual(['Recent2', 'Search models', true]);
  // On the grid's column at 1440, (1440 − 1128) / 2 + 24 = 180px from either edge, the background full width: the
  // logo's mark (16px into its row) at 180, "Recent" after it, and Open ending at 180 from the right: the row's padding.
  await waitFor(() => expect([navbar()!.style.paddingLeft, navbar()!.style.paddingRight]).toEqual(['172px', '180px']));
  const lead = navbar()!.querySelector('nav')!;
  expect([lead.nextElementSibling === home, home.firstElementChild === left]).toEqual([true, true]);
  // No panel toggles and no ⋯ on the home; the app menu is the logo's.
  expect([navbar()!.querySelector('[data-navbar-panel]'), navbar()!.querySelector('[data-testid="file-actions"]')]).toEqual([null, null]);
  // The page's own row: the filter at its left and the layout switch at its right, no heading, no search.
  const row = document.querySelector<HTMLElement>('.cad-library-toolbar')!;
  expect([row.getAttribute('data-library-toolbar'), row.querySelector('h1'), row.querySelector('input'), row.querySelector('.cad-library-kind')!.textContent,
    within(row).getByRole('group', { name: 'Layout' }) !== null]).toEqual(['filters', null, null, 'All', true]);
  // Under 700px of navbar the search is its icon until pressed, then the field with the keyboard in it.
  const css = readFileSync(`${process.cwd()}/src/styles/globals.css`, 'utf8');
  expect(css).toMatch(/@container cad-navbar \(max-width: 699px\) \{[^@]*\.cad-home-search:not\(\[data-open\]\) \.cad-library-search \{ display: none; \}/);
  expect((navbar() as HTMLElement).style.containerName).toBe('cad-navbar');
  const search = right.querySelector<HTMLElement>('.cad-home-search')!;
  expect(search.hasAttribute('data-open')).toBe(false);
  await user.click(within(search).getByRole('button', { name: 'Search models' }));
  expect(search.hasAttribute('data-open')).toBe(true);
  boxes.mockRestore();
});

it('heads the home and a document with the one C mark, in one button that never changes', async () => {
  const homed = { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home() {} } };
  const view = (file: string | null) => <FileViewer file={file} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}}
    presentation={{ home: <p>home</p> } as any} />;
  const { rerender } = render(view(null));
  await screen.findByText('home');
  const logo = screen.getByRole('button', { name: 'Menu' });
  // One mark, the C: no wordmark beside or behind it, and nothing that moves between the two.
  const images = () => [...logo.querySelectorAll('img')].map(image => image.getAttribute('src'));
  expect([logo.getAttribute('data-logo'), images()]).toEqual(['mark', [expect.stringMatching(/C(%20| )logo/)]]);
  rerender(view(FILE));
  await screen.findByText('shown');
  expect(screen.getByRole('button', { name: 'Menu' })).toBe(logo);
  expect([logo.getAttribute('data-logo'), images()]).toEqual(['mark', [expect.stringMatching(/C(%20| )logo/)]]);
  expect(document.querySelector('.cad-navbar-wordmark, .cad-navbar-logo-box')).toBeNull();
});

it('draws no navbar where the host asks for the view alone (`chrome: "bare"`): over a file or the home, whatever it hands the navbar', async () => {
  const homed = { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home() {} } };
  const everything = { host: homed, chrome: 'bare', history: { canGoBack: true, canGoForward: false, back() {}, forward() {} },
    navbarActions: <button type="button" aria-label="Full size" />, presentation: { home: <p>home</p> } };
  open(everything);
  await screen.findByText('shown');
  expect([navbar(), document.querySelector('[data-file-name]'), screen.queryAllByRole('button').map(button => button.getAttribute('aria-label'))]).toEqual([null, null, []]);
  cleanup();
  open({ ...everything, file: null });
  await screen.findByText('home');
  expect([navbar(), screen.queryAllByRole('button')]).toEqual([null, []]);
  cleanup();
  // The default is the page's chrome: the same props draw the navbar.
  open({ ...everything, chrome: undefined });
  await screen.findByText('shown');
  expect(labels()).toEqual(['Menu', 'Back', 'Forward', 'Full size']);
});

it('keeps the right of the navbar for the host\'s actions (Full size) alone, and hides the navbar while the renderer says its Preview is up', async () => {
  // A renderer whose Preview a test opens and closes, as the CAD shell reports it.
  let report: ((previewing: boolean) => void) | undefined;
  const previewed = defineFileRenderer({
    id: 'previewed', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: (props: any) => {
      report = props.onPreviewChange;
      expect(['navbarSlot' in props, 'onFullscreenChange' in props]).toEqual([false, false]);
      return <p>shown</p>;
    } }),
  });
  render(<FileViewer file={FILE} host={host as any} renderers={[previewed]} state={{}} onStateChange={() => {}}
    navbarActions={<button type="button" aria-label="Full size" />} />);
  await screen.findByText('shown');
  expect([labels(), document.querySelector('[data-view-controls]')]).toEqual([['Full size'], null]);
  act(() => report!(true));
  expect([navbar(), screen.getByText('shown')]).toEqual([null, expect.anything()]);
  act(() => report!(false));
  expect(navbar()).not.toBeNull();
});

it('draws Back and Forward between the logo and the file\'s name where the host keeps the view\'s own history, each disabled where it has nowhere to go, and none on a phone', async () => {
  const back = vi.fn(), forward = vi.fn();
  const homed = { ...host, navigation: { openFile(_path: string) {}, home() {} } };
  // The row's left, in order: its buttons by name, and the file's name.
  const left = () => [...document.querySelectorAll('nav[aria-label="Viewer"] button, nav[aria-label="Viewer"] [data-file-name]')]
    .map(node => node.hasAttribute('data-file-name') ? `name:${node.textContent}` : node.getAttribute('aria-label'));
  const view = render(<FileViewer file={FILE} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}}
    history={{ canGoBack: true, canGoForward: false, back, forward }} />);
  await screen.findByText('shown');
  expect(left()).toEqual(['Menu', 'Back', 'Forward', 'name:a.step']);
  const [backButton, forwardButton] = [screen.getByRole('button', { name: 'Back' }), screen.getByRole('button', { name: 'Forward' })];
  expect([backButton.hasAttribute('disabled'), forwardButton.hasAttribute('disabled')]).toEqual([false, true]);
  act(() => { backButton.click(); forwardButton.click(); });
  expect([back.mock.calls.length, forward.mock.calls.length]).toEqual([1, 0]);
  view.unmount();
  // A host that keeps none (a browser's page has its own) gets neither.
  open({ host: homed });
  await screen.findByText('shown');
  expect(left()).toEqual(['Menu', 'name:a.step']);
  cleanup();
  // A phone's row has no room for them: a view under 600px wide draws neither, its history kept.
  const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 390, height: 700, top: 0, left: 0, right: 390, bottom: 700, x: 0, y: 0, toJSON() {} } as DOMRect);
  render(<FileViewer file={FILE} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}}
    history={{ canGoBack: true, canGoForward: true, back, forward }} />);
  await screen.findByText('shown');
  await waitFor(() => expect(document.querySelector('[data-viewer-layout]')?.getAttribute('data-viewer-layout')).toBe('mobile'));
  expect(left()).toEqual(['Menu', 'name:a.step']);
  rect.mockRestore();
});

it('opens the app menu from the logo: Back to home where the host has a home, the person\'s settings and the host\'s links; its ⋯ offers what the host can do with the file', async () => {
  const user = userEvent.setup({ skipHover: true });
  const home = vi.fn();
  const share = vi.fn();
  const perform = { 'copy-path': vi.fn(), reveal: vi.fn() };
  const links = viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' });
  open({ host: { ...host, links, environment: { colorScheme: 'light', platform: 'win32' }, navigation: { openFile() {}, home }, fileActions: { platform: 'win32', perform } },
    appSettings: [{ id: 'analytics', label: 'Share anonymous usage data', checked: true, onCheckedChange: share }] } as any);
  await screen.findByText('shown');
  expect(labels()).toEqual(['Menu', 'File actions']);
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const menu = document.querySelector('[data-app-menu]')!;
  expect([...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent)).toEqual(['Back to home', 'Share anonymous usage data', 'Send feedback', 'GitHub', 'Discord']);
  expect(menu.querySelector('[data-menu-footer]')?.textContent).toContain('v0.7.4');
  // Send feedback: a new issue on the project's tracker, begun "Feedback: ", for the person to
  // finish, naming the version and the platform; no label: the project has none for feedback.
  const feedback = new URL(screen.getByRole('menuitem', { name: 'Send feedback' }).getAttribute('href')!);
  expect([`${feedback.origin}${feedback.pathname}`, feedback.searchParams.get('title'), feedback.searchParams.get('labels')])
    .toEqual(['https://github.com/earthtojake/text-to-cad/issues/new', 'Feedback: ', null]);
  expect(feedback.searchParams.get('body')).toMatch(/- CAD: 0\.7\.4\n- Platform: win32$/);
  // A setting turns without closing the menu; Back to home goes home.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Share anonymous usage data' }));
  expect([share.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[[false]], true]);
  await user.click(screen.getByRole('menuitem', { name: 'Back to home' }));
  expect(home).toHaveBeenCalledOnce();
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  // Copy path, then Open in: the file manager by its name (Windows': File Explorer), no Browser where the host has none.
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in']);
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(within(screen.getByRole('menu', { name: 'Open in' })).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['File Explorer']);
  await user.click(screen.getByRole('menuitem', { name: 'File Explorer' }));
  expect(perform.reveal).toHaveBeenCalledWith({ path: FILE, kind: 'file' });
  cleanup();
  // A host with no home still has the menu, without Back to home; one that can only copy offers only that.
  open({ host: { ...host, links, fileActions: { perform: { 'copy-path': perform['copy-path'] } } } });
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  expect(screen.queryByRole('menuitem', { name: 'Back to home' })).toBeNull();
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path']);
});

it('the app menu holds the person\'s theme in one row: System, Light and Dark as segments, the one in force checked, a press keeping the menu open', async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  open({ host, colorScheme: { preference: 'system', onPreferenceChange: change } } as any);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const rows = screen.getAllByRole('menuitemradio');
  expect(rows.map(row => [row.getAttribute('aria-label'), row.getAttribute('aria-checked')])).toEqual([['System', 'true'], ['Light', 'false'], ['Dark', 'false']]);
  expect(new Set(rows.map(row => row.closest('[data-menu-theme]')))).toEqual(new Set([document.querySelector('[data-menu-theme]')]));
  await user.click(screen.getByRole('menuitemradio', { name: 'Dark' }));
  expect([change.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[['dark']], true]);
});

it('the app menu holds the person\'s language: the one in force, Automatic naming what it infers, then each language under its own name', async () => {
  const user = userEvent.setup();
  const change = vi.fn();
  const language = (choice: string | null, inferred = 'ja') => ({ locale: choice ?? inferred, inferred, choice, onChoiceChange: change });
  // The view reads in the language the host names (`environment.locale`): the whole menu, Theme and all.
  open({ host: { ...host, environment: { colorScheme: 'light', locale: 'ja' } }, colorScheme: { preference: 'system', onPreferenceChange() {} },
    language: language(null) } as any);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'メニュー' }));
  const row = document.querySelector<HTMLElement>('[data-menu-language]')!;
  expect(row.textContent).toBe('言語日本語');
  expect(screen.getAllByRole('menuitemradio').map(item => item.getAttribute('aria-label'))).toEqual(['システム', 'ライト', 'ダーク']);
  await user.hover(row);
  const options = await screen.findAllByRole('menuitemradio', { name: /自動|English|中文|日本語|한국어/ });
  expect(options.map(option => [option.textContent, option.getAttribute('aria-checked')])).toEqual([
    ['自動（日本語）', 'true'], ['English', 'false'], ['简体中文', 'false'], ['繁體中文', 'false'], ['日本語', 'false'], ['한국어', 'false']]);
  fireEvent.click(screen.getByRole('menuitemradio', { name: '繁體中文' }));
  expect(change.mock.calls).toEqual([['zh-TW']]);
  cleanup();
  // A choice made: it is checked, and Automatic gives the choice back to the context.
  open({ host: { ...host, environment: { colorScheme: 'light', locale: 'zh-TW' } }, language: language('zh-TW') } as any);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: '選單' }));
  await user.hover(document.querySelector<HTMLElement>('[data-menu-language]')!);
  fireEvent.click(await screen.findByRole('menuitemradio', { name: '自動（日本語）' }));
  expect(change.mock.calls.at(-1)).toEqual([null]);
});

it('ends the app menu with the version the host runs, a link to its release notes: the release as it is, a custom build with its id', async () => {
  const user = userEvent.setup();
  const footer = async (links: object) => {
    open({ host: { ...host, links } });
    await screen.findByText('shown');
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    const version = document.querySelector('[data-app-menu] [data-menu-version]')!;
    const shown = [document.querySelector('[data-app-menu] [data-menu-footer]')!.textContent, version.getAttribute('href')];
    cleanup();
    return shown;
  };
  const notes = 'https://github.com/earthtojake/text-to-cad/releases/tag/v0.7.15';
  expect(await footer(viewerLinks({ version: '0.7.15' }))).toEqual(['v0.7.15Made by @earthtojake', notes]);
  expect(await footer(viewerLinks({ version: '0.7.15', build: 'b80844940-dirty' }))).toEqual(['v0.7.15-dev.b80844940-dirtyMade by @earthtojake', notes]);
  // Its links are muted, 11/16, the foreground and underlined under the pointer or the keyboard: never the brand's blue.
  open({ host: { ...host, links: viewerLinks({ version: '0.7.15' }) } });
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const links = [...document.querySelectorAll<HTMLElement>('[data-app-menu] [data-menu-footer] a')];
  expect(links.length).toBe(2);
  for (const link of links) {
    expect(link.className).not.toMatch(/brand/);
    expect(['text-muted-foreground', 'hover:text-foreground', 'hover:underline', 'focus-visible:underline'].every(name => link.className.split(' ').includes(name))).toBe(true);
  }
  expect(document.querySelector('[data-app-menu] [data-menu-footer]')!.className).toContain('text-tiny');
});

it('opens the explorer from the file\'s name where the host\'s files can be browsed, and a pick there is shown through the host', async () => {
  const user = userEvent.setup();
  const opened: string[] = [];
  const browsing = { ...host, navigation: { openFile: (path: string) => { opened.push(path); } }, files: { ...host.files,
    list: async (folder: string) => folder === '/models/parts' ? [{ path: FILE, name: 'a.step', kind: 'file' }, { path: '/models/parts/b.step', name: 'b.step', kind: 'file' }] : [],
    search: async () => ({ paths: [], truncated: false }) } };
  open({ host: browsing });
  await screen.findByText('shown');
  expect(fileName().tagName).toBe('BUTTON');
  await user.click(fileName());
  await screen.findByText('b.step');
  // It opens in the file's folder: the pick is the host's to show, and the explorer goes.
  await user.click(document.querySelector<HTMLElement>('[data-file-explorer] [data-path="/models/parts/b.step"]')!);
  expect([opened, document.querySelector('[data-file-explorer]')]).toEqual([['/models/parts/b.step'], null]);
  cleanup();
  // A source that lists but cannot search has no explorer: its name is a name.
  open({ host: { ...host, files: { ...host.files, list: browsing.files.list } } });
  await screen.findByText('shown');
  expect(fileName().tagName).toBe('SPAN');
});

it('has no file menu on a document with no file of its own, which its name names, and no name menu where it has nothing to list', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const list = vi.fn(async () => []);
  const model = { ...host, fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } }, files: { id: 'one', list,
    search: async () => ({ paths: [], truncated: false }),
    stat: async (path: string) => ({ path, name: 'bracket', navigationPath: null, kind: 'file' as const, extension: 'xbf', size: 0 }) } };
  open({ host: model, file: id });
  await screen.findByText('shown');
  // Its name is the model's, a name and no button; no file menu; nothing is listed.
  expect([fileName().tagName, fileName().textContent]).toEqual(['SPAN', 'bracket']);
  expect(labels()).not.toContain('File actions');
  expect(list).not.toHaveBeenCalled();
  cleanup();
  // With the host's library and where the explorer was last: the name opens Models first, and Files
  // lists that folder -- never the folder of the script the model was registered from -- and says
  // each folder it is in, for the host to keep.
  const user = userEvent.setup();
  const registered = { ...model, navigation: { openFile: vi.fn() }, files: { ...model.files,
    stat: async (path: string) => ({ path, name: 'bracket', navigationPath: null, kind: 'file' as const, extension: 'xbf', size: 0 }) } };
  const rows = [{ path: id, name: 'bracket', kind: 'model', opened: null, updated: Date.now() / 1000 }];
  const kept = vi.fn();
  render(<FileViewer file={id} host={registered as any} renderers={[renderer]} state={{}} onStateChange={() => {}} recent={{ list: async () => rows }}
    explorerFolder="/home/me/last" onExplorerFolderChange={kept} />);
  await screen.findByText('shown');
  expect(fileName().tagName).toBe('BUTTON');
  await user.click(fileName());
  expect(screen.getByRole('tab', { name: 'Models' }).getAttribute('aria-selected')).toBe('true');
  await user.click(screen.getByRole('tab', { name: 'Files' }));
  await waitFor(() => expect(list).toHaveBeenCalledWith('/home/me/last', expect.anything()));
  expect(kept).toHaveBeenCalledWith('/home/me/last');
  expect(labels()).not.toContain('File actions');
});

it('puts Open in › Browser and the host\'s own items (Export) in the file menu; a model\'s Copy path and file manager act on its script, disabled with the reason where it is gone', async () => {
  // No hover: jsdom lays nothing out, so a pointer leaving a submenu's trigger for its items closes it.
  const user = userEvent.setup({ skipHover: true });
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const exported = vi.fn();
  const perform = { 'copy-path': vi.fn(), 'copy-link': vi.fn(), reveal: vi.fn(), browser: vi.fn() };
  // The host's items as the viewer's Export hands them: a submenu of formats.
  const exportMenu = <DropdownMenuSub><DropdownMenuSubTrigger>Export</DropdownMenuSubTrigger><DropdownMenuSubContent aria-label="Export">
    <DropdownMenuItem data-export-format="step" onSelect={() => exported('step')}>STEP</DropdownMenuItem>
  </DropdownMenuSubContent></DropdownMenuSub>;
  const modelHost = (script?: string, { missing = false, actions = perform as Record<string, unknown> } = {}) => ({ ...host, fileActions: { platform: 'darwin', perform: actions }, files: { id: 'one',
    stat: async (path: string) => ({ path, name: 'bracket', navigationPath: null, ...(script ? { sourceFile: script } : {}),
      ...(missing ? { sourceMissing: true } : {}), kind: 'file' as const, extension: 'xbf', size: 0 }) } });
  const top = () => screen.getAllByRole('menuitem').map(item => item.textContent);
  const openIn = () => within(screen.getByRole('menu', { name: 'Open in' })).getAllByRole('menuitem').map(item => item.textContent);
  // A model whose script the engine names: the same menu a file has, on its script.
  render(<FileViewer file={id} host={modelHost('/m/parts.py') as any} renderers={[renderer]} state={{}} onStateChange={() => {}} fileMenuItems={exportMenu} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(top()).toEqual(['Copy path', 'Copy link', 'Open in', 'Export']);
  await user.click(screen.getByRole('menuitem', { name: 'Copy path' }));
  expect(perform['copy-path']).toHaveBeenCalledWith({ path: '/m/parts.py', kind: 'file' });
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(openIn()).toEqual(['Browser', 'Finder']);
  await user.click(screen.getByRole('menuitem', { name: 'Finder' }));
  expect(perform.reveal).toHaveBeenCalledWith({ path: '/m/parts.py', kind: 'file' });
  // Browser opens the document's own page, by its id, never the script's.
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  await user.click(screen.getByRole('menuitem', { name: 'Browser' }));
  expect(perform.browser).toHaveBeenCalledWith({ path: id, kind: 'file' });
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Export' }));
  await user.click(document.querySelector<HTMLElement>('[data-export-format="step"]')!);
  expect(exported).toHaveBeenCalledWith('step');
  // The menu and its submenus are shadcn's own width, sized to their items: none sets one.
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  for (const menu of screen.getAllByRole('menu')) expect(menu.className.split(/\s+/).filter(name => /^w-/.test(name))).toEqual([]);
  cleanup();
  // A model whose script was moved or deleted, where nothing in Open in can open (the web viewer's: no
  // Browser): Copy path stays (where it was), and Open in is drawn disabled, its hint saying why.
  const web = { 'copy-path': perform['copy-path'], 'copy-link': perform['copy-link'], reveal: perform.reveal };
  render(<FileViewer file={id} host={modelHost('/m/parts.py', { missing: true, actions: web }) as any} renderers={[renderer]} state={{}} onStateChange={() => {}} fileMenuItems={exportMenu} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(top()).toEqual(['Copy path', 'Copy link', 'Open in', 'Export']);
  const openInRow = screen.getByRole('menuitem', { name: 'Open in' });
  expect([openInRow.getAttribute('aria-disabled'), openInRow.closest('[data-disabled-reason]')]).toEqual(['true', expect.anything()]);
  await user.hover(openInRow.closest('[data-disabled-reason]')!);
  expect((await screen.findByRole('tooltip')).textContent).toBe('The source was moved or deleted.');
  expect(screen.queryByRole('menu', { name: 'Open in' })).toBeNull();
  await user.click(screen.getByRole('menuitem', { name: 'Copy path' }));
  expect(perform['copy-path']).toHaveBeenLastCalledWith({ path: '/m/parts.py', kind: 'file' });
  // Copy link needs no source: enabled, and it names the document itself, never its script.
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(screen.getByRole('menuitem', { name: 'Copy link' }).getAttribute('aria-disabled')).toBeNull();
  await user.click(screen.getByRole('menuitem', { name: 'Copy link' }));
  expect(perform['copy-link']).toHaveBeenLastCalledWith({ path: id, kind: 'file' });
  cleanup();
  // The card's: Browser needs no source, so Open in and Browser stay enabled and Finder is disabled, saying why.
  render(<FileViewer file={id} host={modelHost('/m/parts.py', { missing: true }) as any} renderers={[renderer]} state={{}} onStateChange={() => {}} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(screen.getByRole('menuitem', { name: 'Open in' }).getAttribute('aria-disabled')).toBeNull();
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(openIn()).toEqual(['Browser', 'Finder']);
  const finder = screen.getByRole('menuitem', { name: 'Finder' });
  expect([screen.getByRole('menuitem', { name: 'Browser' }).getAttribute('aria-disabled'), finder.getAttribute('aria-disabled')]).toEqual([null, 'true']);
  // The pointer straight onto its row's wrapper: jsdom lays nothing out, so a pointer crossing from
  // Open in to its submenu would close it (a browser's pointer grace keeps it open).
  fireEvent.pointerMove(finder.closest('[data-disabled-reason]')!, { pointerType: 'mouse' });
  expect((await screen.findByRole('tooltip')).textContent).toBe('The source was moved or deleted.');
  const reveals = perform.reveal.mock.calls.length;
  await user.click(screen.getByRole('menuitem', { name: 'Browser' }));
  expect(perform.browser).toHaveBeenLastCalledWith({ path: id, kind: 'file' });
  expect(perform.reveal).toHaveBeenCalledTimes(reveals);
  cleanup();
  // A model whose script is not named: Open in › Browser and Export alone.
  render(<FileViewer file={id} host={modelHost() as any} renderers={[renderer]} state={{}} onStateChange={() => {}} fileMenuItems={exportMenu} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(top()).toEqual(['Copy link', 'Open in', 'Export']);
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(openIn()).toEqual(['Browser']);
  cleanup();
  // A file on disk: Copy path, Open in (Browser, then Finder on a Mac), then Export.
  open({ host: { ...host, fileActions: { platform: 'darwin', perform } }, fileMenuItems: exportMenu } as any);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(top()).toEqual(['Copy path', 'Copy link', 'Open in', 'Export']);
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(openIn()).toEqual(['Browser', 'Finder']);
  await user.click(screen.getByRole('menuitem', { name: 'Browser' }));
  expect(perform.browser).toHaveBeenLastCalledWith({ path: FILE, kind: 'file' });
});

// The contract's example (`GET /api/v1/local/open-in`): a model with its script and a STEP its last build wrote.
const OPEN_IN = { fileManager: 'finder', targets: [
  { target: 'source', kind: 'script', name: 'bracket.py', present: true, apps: [{ id: 'vscode', name: 'Visual Studio Code' }, { id: 'cursor', name: 'Cursor' }] },
  { target: 'export:step', kind: 'step', name: 'bracket.step', present: true, apps: [{ id: 'freecad', name: 'FreeCAD' }, { id: 'bambu', name: 'Bambu Studio' }] },
] };

it('Open in adds the apps the host has for the document\'s files as the menu opens: the source\'s, each export\'s, then Default app, a separator between groups', async () => {
  const user = userEvent.setup({ skipHover: true });
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  // The submenu as drawn: its rows' names, a separator as a rule.
  const drawn = () => [...screen.getByRole('menu', { name: 'Open in' }).querySelectorAll('[role="menuitem"], [role="separator"]')]
    .map(node => node.getAttribute('role') === 'separator' ? '—' : `${node.textContent}${node.getAttribute('aria-disabled') === 'true' ? ' (disabled)' : ''}`);
  let answer!: (files: unknown) => void;
  const apps = vi.fn(() => new Promise(resolve => { answer = resolve; }));
  const openApp = vi.fn();
  const perform = { 'copy-path': vi.fn(), reveal: vi.fn() };
  const view = (actions: object, file = id, stat: object = { navigationPath: null, sourceFile: '/m/bracket.py' }) => render(<FileViewer file={file} renderers={[renderer]} state={{}} onStateChange={() => {}}
    host={{ ...host, fileActions: { platform: 'darwin', perform, apps, openApp, ...actions }, files: { id: 'one',
      stat: async (path: string) => ({ path, name: 'bracket', kind: 'file' as const, extension: 'xbf', size: 0, ...stat }) } } as any} />);
  const openMenu = async () => {
    await user.click(screen.getByRole('button', { name: 'File actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  };

  // The web viewer's: nothing is asked until the menu opens; what needs no answer is there at once,
  // and the apps join it when the answer comes.
  view({});
  await screen.findByText('shown');
  expect(apps).not.toHaveBeenCalled();
  await openMenu();
  expect(apps).toHaveBeenCalledWith({ path: id, kind: 'file' }, { signal: expect.any(AbortSignal) });
  expect(drawn()).toEqual(['Finder']);
  await act(async () => answer(OPEN_IN));
  expect(drawn()).toEqual(['Finder', '—', 'Visual Studio Code', 'Cursor', '—', 'FreeCAD (bracket.step)', 'Bambu Studio (bracket.step)', '—', 'Default app']);
  await user.click(screen.getByRole('menuitem', { name: 'Cursor' }));
  expect(openApp).toHaveBeenLastCalledWith({ path: id, kind: 'file' }, 'source', 'cursor');
  // Asked again at each opening: the answer may have changed.
  await openMenu();
  expect(apps).toHaveBeenCalledTimes(2);
  await act(async () => answer(OPEN_IN));
  await user.click(screen.getByRole('menuitem', { name: 'FreeCAD (bracket.step)' }));
  expect(openApp).toHaveBeenLastCalledWith({ path: id, kind: 'file' }, 'export:step', 'freecad');
  await openMenu();
  await act(async () => answer(OPEN_IN));
  await user.click(screen.getByRole('menuitem', { name: 'Default app' }));
  expect(openApp).toHaveBeenLastCalledWith({ path: id, kind: 'file' }, 'source', 'default');
  cleanup();

  // The card's: Browser first. A source moved or deleted: Finder, its apps and Default app disabled,
  // saying why; the export on disk still opens, and one whose file is gone is left out.
  view({ perform: { ...perform, browser: vi.fn() } }, id, { navigationPath: null, sourceFile: '/m/bracket.py', sourceMissing: true });
  await screen.findByText('shown');
  await openMenu();
  await act(async () => answer({ ...OPEN_IN, targets: [{ ...OPEN_IN.targets[0], present: false }, OPEN_IN.targets[1],
    { target: 'export:stl', kind: 'stl', name: 'bracket.stl', present: false, apps: [{ id: 'bambu', name: 'Bambu Studio' }] }] }));
  expect(drawn()).toEqual(['Browser', 'Finder (disabled)', '—', 'Visual Studio Code (disabled)', 'Cursor (disabled)', '—',
    'FreeCAD (bracket.step)', 'Bambu Studio (bracket.step)', '—', 'Default app (disabled)']);
  cleanup();

  // A STEP file: its own apps; with none detected, Finder and Default app alone.
  view({}, '/models/bracket.step', {});
  await screen.findByText('shown');
  await openMenu();
  await act(async () => answer({ fileManager: 'finder', targets: [{ target: 'source', kind: 'step', name: 'bracket.step', present: true, apps: [{ id: 'freecad', name: 'FreeCAD' }] }] }));
  expect(drawn()).toEqual(['Finder', '—', 'FreeCAD', '—', 'Default app']);
  await user.keyboard('{Escape}');
  await openMenu();
  await act(async () => answer({ fileManager: 'finder', targets: [{ target: 'source', kind: 'dxf', name: 'bracket.step', present: true, apps: [] }] }));
  expect(drawn()).toEqual(['Finder', '—', 'Default app']);
  await user.keyboard('{Escape}');
  // A failed answer leaves the menu as it is without apps.
  apps.mockImplementationOnce(() => Promise.reject(new Error('offline')));
  await openMenu();
  await act(async () => {});
  expect(drawn()).toEqual(['Finder']);
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in', 'Finder']);
});

it('Open in draws a KiCad that refuses the board disabled, its hint saying why, and takes no click on it', async () => {
  const user = userEvent.setup({ skipHover: true });
  const openApp = vi.fn();
  const apps = vi.fn(async () => ({ fileManager: 'finder', targets: [{ target: 'source', kind: 'kicad_pcb', name: 'blinky.kicad_pcb', present: true, default: false,
    apps: [{ id: 'kicad', name: 'KiCad 9.0.6', refuses: 'newer' }, { id: 'kicad-nightly', name: 'KiCad 10.99 nightly' }] }] }));
  render(<FileViewer file="/boards/blinky.kicad_pcb" renderers={[renderer]} state={{}} onStateChange={() => {}}
    host={{ ...host, fileActions: { platform: 'darwin', perform: { 'copy-path': vi.fn(), reveal: vi.fn() }, apps, openApp } } as any} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  const stable = await screen.findByRole('menuitem', { name: 'KiCad 9.0.6' });
  expect(stable.getAttribute('aria-disabled')).toBe('true');
  // No Default app for a KiCad file; the nightly is an ordinary row.
  expect(within(screen.getByRole('menu', { name: 'Open in' })).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Finder', 'KiCad 9.0.6', 'KiCad 10.99 nightly']);
  expect(screen.getByRole('menuitem', { name: 'KiCad 10.99 nightly' }).getAttribute('aria-disabled')).toBeNull();
  // A pointer on the row's wrapper alone: a hover from outside would leave the submenu's trigger and close it in jsdom.
  fireEvent.pointerMove(stable.closest('[data-disabled-reason]')!, { pointerType: 'mouse' });
  expect((await screen.findByRole('tooltip')).textContent).toBe("KiCad 9.0.6 can't open this board: it was saved by a newer KiCad.");
  await user.click(screen.getByRole('menuitem', { name: 'KiCad 10.99 nightly' }));
  expect(openApp).toHaveBeenCalledTimes(1);
  expect(openApp).toHaveBeenCalledWith({ path: '/boards/blinky.kicad_pcb', kind: 'file' }, 'source', 'kicad-nightly');
});

it('Open in draws each row\'s mark in the text\'s colour: an app\'s own, else the plain app glyph, and each place\'s glyph', async () => {
  const user = userEvent.setup({ skipHover: true });
  const apps = vi.fn(async () => ({ fileManager: 'finder', targets: [{ target: 'source', kind: 'step', name: 'bracket.step', present: true,
    apps: [{ id: 'freecad', name: 'FreeCAD' }, { id: 'solidworks', name: 'SolidWorks' }] }] }));
  render(<FileViewer file="/models/bracket.step" renderers={[renderer]} state={{}} onStateChange={() => {}}
    host={{ ...host, fileActions: { platform: 'darwin', perform: { browser: vi.fn(), reveal: vi.fn() }, apps, openApp: vi.fn() } } as any} />);
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  await screen.findByRole('menuitem', { name: 'FreeCAD' });
  const rows = within(screen.getByRole('menu', { name: 'Open in' })).getAllByRole('menuitem');
  expect(rows.map(row => [row.textContent, row.querySelector('svg')?.getAttribute('data-open-in-mark')])).toEqual([
    ['Browser', 'browser'], ['Finder', 'reveal'], ['FreeCAD', 'freecad'], ['SolidWorks', 'glyph'], ['Default app', 'default']]);
  const freecad = rows[2].querySelector('svg')!;
  expect([freecad.getAttribute('fill'), freecad.getAttribute('aria-hidden'), freecad.querySelectorAll('path').length]).toEqual(['currentColor', 'true', 1]);
});

it('says why a file will not open, and that it does not exist when it is missing', async () => {
  const missing = Object.assign(new Error('File does not exist: /models/gone.step'), { code: 'cad-file-missing' });
  expect(isMissingFileError(missing)).toBe(true);
  const failing = (error: Error) => ({ ...host, files: { id: 'one', stat: async () => { throw error; } } });
  const failures: unknown[] = [];
  const presentation = { error: (failure: unknown) => { failures.push(failure); return <p>failed</p>; } };
  open({ host: failing(missing), presentation });
  await screen.findByText('failed');
  cleanup();
  open({ host: failing(new Error('The disk is gone')), presentation });
  await screen.findByText('failed');
  // What the source raised comes with it, for a host to read its own fields on.
  expect(failures.at(0)).toEqual({ message: 'File does not exist: /models/gone.step', missing: true, error: missing, reload: expect.any(Function) });
  expect(failures.at(-1)).toEqual({ message: 'The disk is gone', missing: false, error: expect.any(Error), reload: expect.any(Function) });
  cleanup();
  // A host with no page of its own for it gets the viewer's.
  open({ host: failing(new Error('The disk is gone')) });
  expect(await screen.findByText('Could not open that file')).toBeTruthy();
});

it('a missing-file presentation can reread the requested file through its injected reload', async () => {
  const missing = Object.assign(new Error('File does not exist'), { code: 'cad-file-missing' });
  const stat = vi.fn().mockRejectedValueOnce(missing).mockImplementation(host.files.stat);
  let retry = () => {};
  open({ host: { ...host, files: { ...host.files, stat } },
    presentation: { error: ({ reload }: { reload: () => void }) => { retry = reload; return <button onClick={reload}>Retry missing file</button>; } } });
  await userEvent.click(await screen.findByRole('button', { name: 'Retry missing file' }));
  expect(await screen.findByText('shown')).toBeTruthy();
  act(() => retry());
  expect(stat.mock.calls.map(([path]) => path)).toEqual([FILE, FILE]);
});

it('takes the keyboard as its file is shown, so a tool key works with no press first; never from a field that has it', async () => {
  const view = open({});
  await screen.findByText('shown');
  await waitFor(() => expect(document.activeElement?.classList.contains('text-to-cad-file-viewer')).toBe(true));
  view.unmount();
  const field = document.body.appendChild(document.createElement('input'));
  field.focus();
  open({});
  await screen.findByText('shown');
  expect(document.activeElement).toBe(field);
  field.remove();
});
