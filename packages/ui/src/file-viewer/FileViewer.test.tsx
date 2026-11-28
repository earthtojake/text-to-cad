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
import { useProjectKey } from '../../dist/file-viewer/projectKeys.js';
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

it("ends the stand-in panel in the panel's foot from a document page's first frame where the host has a home; a host with no home has none, and keeps the logo's menu", async () => {
  const ID = '906f6bff-80e7-5331-b842-dd377b720a7b';
  const links = viewerLinks({ version: '0.7.4' });
  const pending = { ...host, links, files: { id: 'slow', stat: () => new Promise(() => {}) } };
  const foot = () => document.querySelector<HTMLElement>('[data-app-foot]');
  // A host with a home: the links and Settings at the stand-in's bottom, under its placeholder rows, where the view's
  // panel will have them.
  render(<FileViewer file={ID} host={{ ...pending, navigation: { openFile() {}, home() {} } } as any} renderers={[renderer]} state={{}} onStateChange={() => {}} />);
  const frame = document.querySelector<HTMLElement>('aside[data-panel-loading]')!;
  expect([foot()!.parentElement === frame, frame.lastElementChild === foot(), foot()!.previousElementSibling!.className.includes('flex-1'),
    [...foot()!.querySelectorAll('[data-app-foot-links] a')].map(link => link.getAttribute('aria-label')), within(foot()!).getByRole('button', { name: 'Settings' }) !== null,
    screen.queryByRole('button', { name: 'Menu' })]).toEqual([true, true, true, ['GitHub', 'Discord', 'Send feedback'], true, null]);
  cleanup();
  // No home: the same links are the logo's menu's, so the panel has no foot.
  render(<FileViewer file={ID} host={pending as any} renderers={[renderer]} state={{}} onStateChange={() => {}} />);
  expect([Boolean(document.querySelector('aside[data-panel-loading]')), foot(), screen.getByRole('button', { name: 'Menu' }) !== null]).toEqual([true, null, true]);
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

it('draws the navbar over every file, named by its name, and over the home with only the logo, Back and Forward, the host\'s actions; never over a view shown small', async () => {
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
  // The home has the same navbar: the logo (the way to Recents), Back and Forward where the host keeps the view's
  // history, and the host's actions, as over a file; no file, no box for view controls.
  const back = vi.fn(), home = vi.fn();
  open({ host: { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home } }, file: null,
    history: { canGoBack: true, canGoForward: false, back, forward() {} },
    navbarActions: <button type="button" aria-label="Full size" />,
    presentation: { home: <p>home</p> } } as any);
  await screen.findByText('home');
  expect([labels(), document.querySelector('[data-file-name]'), document.querySelector('[data-navbar-view]')])
    .toEqual([['Home', 'Back', 'Forward', 'Full size'], null, null]);
  expect((screen.getByRole('button', { name: 'Forward' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Back' }));
  expect(back).toHaveBeenCalledOnce();
  // Over the home the logo goes to Recents, and opens no menu: the app's menu is the home's (Settings, in its sidebar).
  await userEvent.setup().click(screen.getByRole('button', { name: 'Home' }));
  expect([home.mock.calls.length, screen.queryByRole('menu')]).toEqual([1, null]);
});

it('draws the view\'s panel toggle in the navbar right after the logo: the same neutral button open or shut, its state aria-expanded, its icon the sidebar\'s; none over a home that has no sidebar', async () => {
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
  // The logo, then the toggle, then the name and its ⋯; nothing of it at the row's right.
  const order = [...navbar()!.querySelectorAll('[data-navbar-logo], [data-file-name], [data-testid="file-actions"], [data-navbar-panel], [aria-label="Full size"]')]
    .map(node => node.getAttribute('data-navbar-panel') ?? (node.hasAttribute('data-navbar-logo') ? 'logo' : null) ?? node.getAttribute('aria-label') ?? (node.hasAttribute('data-file-name') ? 'name' : '?'));
  expect(order).toEqual(['logo', 'left', 'name', 'File actions', 'Full size']);
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
  // A home that says no panel of its own: no toggle.
  open({ host: { ...host, navigation: { openFile() {}, home() {} } }, file: null, presentation: { home: <p>home</p> } } as any);
  await screen.findByText('home');
  expect(navbar()!.querySelector('[data-navbar-panel]')).toBeNull();
  cleanup();
  // A home that says its sidebar's toggle, as a view's frame says its panel's, has it from its first frame, after the
  // logo; a document shown after it has its own, and the home's is gone with the home.
  function Sided() {
    const [shown, setShown] = React.useState(true);
    usePanelToggles(React.useMemo(() => ({ left: { open: shown, label: shown ? 'Hide panel' : 'Show panel', shortcut: '⌘\\', toggle: () => setShown(value => !value) } }), [shown]), { early: true });
    return <p>home</p>;
  }
  const homed = { ...host, navigation: { openFile() {}, home() {} } };
  const page = (file: string | null) => <FileViewer file={file} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}} presentation={{ home: <Sided /> } as any} />;
  const view = render(page(null));
  expect([look(), navbar()!.querySelector('nav')!.firstElementChild!.getAttribute('data-navbar-logo'), toggle().compareDocumentPosition(screen.getByRole('button', { name: 'Home' })) & Node.DOCUMENT_POSITION_PRECEDING])
    .toEqual([['Hide panel', 'true', null, 'ghost'], 'home', Node.DOCUMENT_POSITION_PRECEDING]);
  await user.click(toggle());
  expect(look()).toEqual(['Show panel', 'false', null, 'ghost']);
  view.rerender(page(FILE));
  await screen.findByText('shown');
  await waitFor(() => expect(navbar()!.querySelector('[data-navbar-panel]')).toBeNull());
});

it('draws the home\'s own controls at its navbar\'s right end: the search and Import, and no name of the home\'s after the logo; the layout in a row of the place\'s own', async () => {
  const user = userEvent.setup();
  const models = [{ path: '/work/a.step', name: 'a.step', folder: '/work', opened: 1, updated: 1, created: null, pinned: false, missing: false, thumbnail: null, pictured: null },
    { path: 'model-1', name: 'bracket', folder: null, opened: 1, updated: 1, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, kind: 'model' }];
  const library = { list: async () => models, change: async () => models, thumbnail: async () => null, open: async () => {}, pick: async () => {} };
  // A 1440px row.
  const boxes = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const width = this.hasAttribute('data-viewer-navbar') ? 1440 : this.matches('nav') ? 36 : 0;
    return { x: 0, y: 0, left: 0, top: 0, right: width, bottom: 40, width, height: 40, toJSON() {} } as DOMRect;
  });
  open({ host: { ...host, navigation: { openFile() {}, home() {} } }, file: null,
    presentation: { home: <ModelLibrary library={library as any} onLayoutChange={() => {}} /> } } as any);
  await screen.findByText('a.step');
  const home = navbar()!.querySelector<HTMLElement>('[data-navbar-home]')!;
  const right = home.querySelector('[data-navbar-home-right]')!;
  // Nothing names the home in the navbar: the place's title does, and the logo is the way home.
  expect([home.querySelector('[data-navbar-home-left]'), navbar()!.querySelector('h1'), right.querySelector('input')!.getAttribute('aria-label'),
    within(right as HTMLElement).getByRole('button', { name: 'Import' }) !== null]).toEqual([null, null, 'Search models', true]);
  // The row over the home is the row over a file: its own padding, the logo first, never padded onto a centred column
  // (the home under it is full width, its sidebar at the window's edge).
  expect([navbar()!.style.paddingLeft, navbar()!.style.paddingRight]).toEqual(['', '']);
  const lead = navbar()!.querySelector('nav')!;
  expect([lead.nextElementSibling === home, home.firstElementChild === right]).toEqual([true, true]);
  // The logo first, then the sidebar's toggle, and no ⋯ on the home; the app menu is the sidebar's Settings.
  expect([lead.lastElementChild!.querySelector('[data-navbar-panel="left"]')?.getAttribute('aria-expanded'), lead.firstElementChild!.getAttribute('data-navbar-logo'),
    navbar()!.querySelector('[data-testid="file-actions"]'), navbar()!.querySelector('[data-navbar-menu]')]).toEqual(['true', 'home', null, null]);
  // The page's own row: its title, the page's one h1, with Sort and the layout control at its right, no search, no tabs.
  const row = document.querySelector<HTMLElement>('[data-library-toolbar]')!;
  expect([row.parentElement?.querySelector('h1')?.textContent, row.querySelector('h1'), row.querySelector('input'), document.querySelector('[data-library-kinds]'),
    within(row).getByRole('group', { name: 'Layout' }) !== null]).toEqual(['Recents', null, null, null, true]);
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

it('heads the home and a document with the one C mark, in one control that never changes', async () => {
  const homed = { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home() {} } };
  const view = (file: string | null) => <FileViewer file={file} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}}
    presentation={{ home: <p>home</p> } as any} />;
  const { rerender } = render(view(null));
  await screen.findByText('home');
  const logo = screen.getByRole('button', { name: 'Home' });
  // One mark, the C: no wordmark beside or behind it, and nothing that moves between the two.
  const images = () => [...logo.querySelectorAll('img')].map(image => image.getAttribute('src'));
  expect([logo.getAttribute('data-logo'), images()]).toEqual(['mark', [expect.stringMatching(/C(%20| )logo/)]]);
  rerender(view(FILE));
  await screen.findByText('shown');
  expect(screen.getByRole('button', { name: 'Home' })).toBe(logo);
  expect([logo.getAttribute('data-logo'), images()]).toEqual(['mark', [expect.stringMatching(/C(%20| )logo/)]]);
  expect(document.querySelector('.cad-navbar-wordmark, .cad-navbar-logo-box')).toBeNull();
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
  expect([labels(), document.querySelector('[data-navbar-view-controls]')]).toEqual([['Full size'], null]);
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
  expect(left()).toEqual(['Home', 'Back', 'Forward', 'name:a.step']);
  const [backButton, forwardButton] = [screen.getByRole('button', { name: 'Back' }), screen.getByRole('button', { name: 'Forward' })];
  expect([backButton.hasAttribute('disabled'), forwardButton.hasAttribute('disabled')]).toEqual([false, true]);
  act(() => { backButton.click(); forwardButton.click(); });
  expect([back.mock.calls.length, forward.mock.calls.length]).toEqual([1, 0]);
  view.unmount();
  // A host that keeps none (a browser's page has its own) gets neither.
  open({ host: homed });
  await screen.findByText('shown');
  expect(left()).toEqual(['Home', 'name:a.step']);
  cleanup();
  // A phone's row has no room for them: a view under 600px wide draws neither, its history kept.
  const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 390, height: 700, top: 0, left: 0, right: 390, bottom: 700, x: 0, y: 0, toJSON() {} } as DOMRect);
  render(<FileViewer file={FILE} host={homed as any} renderers={[renderer]} state={{}} onStateChange={() => {}}
    history={{ canGoBack: true, canGoForward: true, back, forward }} />);
  await screen.findByText('shown');
  await waitFor(() => expect(document.querySelector('[data-viewer-layout]')?.getAttribute('data-viewer-layout')).toBe('mobile'));
  expect(left()).toEqual(['Home', 'name:a.step']);
  rect.mockRestore();
});

it("makes the logo the way home wherever the host has a home: a real link where the home has an address, a button otherwise, with a hint; no menu there, and its ⋯ offers what the host can do with the file", async () => {
  const user = userEvent.setup({ skipHover: true });
  const home = vi.fn();
  const perform = { 'copy-path': vi.fn(), reveal: vi.fn() };
  const links = viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' });
  const homed = (navigation: object = {}) => ({ ...host, links, environment: { colorScheme: 'light', platform: 'win32' },
    navigation: { openFile() {}, home, ...navigation }, fileActions: { platform: 'win32', perform } });
  const settings = { appSettings: [{ id: 'analytics', label: 'Share anonymous usage data', checked: true, onCheckedChange() {} }] };
  // A host whose pages have no address (an app's frame): a button, named Home.
  open({ host: homed(), ...settings } as any);
  await screen.findByText('shown');
  expect(labels()).toEqual(['Home', 'File actions']);
  const button = screen.getByRole('button', { name: 'Home' });
  expect([button.tagName, button.getAttribute('data-navbar-logo'), button.getAttribute('aria-haspopup'), navbar()!.querySelector('[data-navbar-menu]')]).toEqual(['BUTTON', 'home', null, null]);
  // Its hint says where it goes.
  await userEvent.setup().hover(button);
  expect((await screen.findByRole('tooltip')).textContent).toBe('Home');
  await user.click(button);
  // It goes home, and opens no menu: the person's settings and the host's links are the home's (Settings).
  expect([home.mock.calls.length, document.querySelector('[data-app-menu]'), screen.queryByRole('menu')]).toEqual([1, null, null]);
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  // Copy path, then Open in: the file manager by its name (Windows': File Explorer), no Browser where the host has none.
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in']);
  await user.click(screen.getByRole('menuitem', { name: 'Open in' }));
  expect(within(screen.getByRole('menu', { name: 'Open in' })).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['File Explorer']);
  await user.click(screen.getByRole('menuitem', { name: 'File Explorer' }));
  expect(perform.reveal).toHaveBeenCalledWith({ path: FILE, kind: 'file' });
  cleanup();
  // A host that gives the home an address (the web page): a real link to Recents. A plain click goes home in this
  // view, the link's own navigation held back; ⌘ or Ctrl and a click, Shift, a middle click are the browser's.
  const hrefOf = vi.fn((target: any) => ('home' in target ? `/?view=${target.home.view}` : null));
  home.mockClear();
  open({ host: homed({ hrefOf }), ...settings } as any);
  await screen.findByText('shown');
  const link = screen.getByRole('link', { name: 'Home' });
  expect([link.getAttribute('href'), link.getAttribute('data-navbar-logo'), hrefOf.mock.calls.some(([target]) => JSON.stringify(target) === '{"home":{"view":"recents"}}')])
    .toEqual(['/?view=recents', 'home', true]);
  expect(fireEvent.click(link)).toBe(false);
  expect(home).toHaveBeenCalledTimes(1);
  for (const modifier of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) expect(fireEvent.click(link, modifier)).toBe(true);
  expect(home).toHaveBeenCalledTimes(1);
  cleanup();
  // A page still loading, and one that failed, have the logo as the way home; counted as the way home always was.
  const { ControlUsageProvider } = await import('../../dist/usage/controls.js');
  const reports: { control: string; count: number }[][] = [];
  home.mockClear();
  const pending = { ...homed({ hrefOf }), files: { id: 'slow', stat: () => new Promise(() => {}) } };
  const loading = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <FileViewer file={FILE} host={pending as any} renderers={[renderer]} state={{}} onStateChange={() => {}} /></ControlUsageProvider>);
  fireEvent.click(screen.getByRole('link', { name: 'Home' }));
  loading.unmount();
  const failing = { ...homed(), files: { id: 'gone', stat: async () => { throw new Error('No such file'); } } };
  open({ host: failing });
  await screen.findByText('No such file');
  fireEvent.click(screen.getByRole('button', { name: 'Home' }));
  expect([home.mock.calls.length, reports.flat()]).toEqual([2, [{ control: 'home', count: 1, seconds: 0 }]]);
});

it("keeps the app menu on the logo where the host has no home (a view that shows one file alone): the person's settings and the host's links, no way home", async () => {
  const user = userEvent.setup({ skipHover: true });
  const share = vi.fn();
  const perform = { 'copy-path': vi.fn() };
  const links = viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' });
  open({ host: { ...host, links, environment: { colorScheme: 'light', platform: 'win32' }, fileActions: { perform } },
    appSettings: [{ id: 'analytics', label: 'Share anonymous usage data', checked: true, onCheckedChange: share }] } as any);
  await screen.findByText('shown');
  expect(labels()).toEqual(['Menu', 'File actions']);
  const logo = screen.getByRole('button', { name: 'Menu' });
  expect([logo.getAttribute('data-navbar-logo'), logo.hasAttribute('data-navbar-menu'), screen.queryByRole('link', { name: 'Home' })]).toEqual(['menu', true, null]);
  await user.click(logo);
  const menu = document.querySelector('[data-app-menu]')!;
  expect([menu.getAttribute('aria-label'), [...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent)])
    .toEqual(['Menu', ['Share anonymous usage data', 'Send feedback', 'GitHub', 'Discord']]);
  expect(menu.querySelector('[data-menu-footer]')?.textContent).toContain('v0.7.4');
  // Send feedback: a new issue on the project's tracker, begun "Feedback: ", for the person to
  // finish, naming the version and the platform; no label: the project has none for feedback.
  const feedback = new URL(screen.getByRole('menuitem', { name: 'Send feedback' }).getAttribute('href')!);
  expect([`${feedback.origin}${feedback.pathname}`, feedback.searchParams.get('title'), feedback.searchParams.get('labels')])
    .toEqual(['https://github.com/earthtojake/text-to-cad/issues/new', 'Feedback: ', null]);
  expect(feedback.searchParams.get('body')).toMatch(/- CAD: 0\.7\.4\n- Platform: win32$/);
  // A setting turns without closing the menu.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Share anonymous usage data' }));
  expect([share.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[[false]], true]);
  await user.keyboard('{Escape}');
  // One that can only copy offers only that.
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
  expect(await footer(viewerLinks({ version: '0.7.15' }))).toEqual(['v0.7.15', notes]);
  expect(await footer(viewerLinks({ version: '0.7.15', build: 'b80844940-dirty' }))).toEqual(['v0.7.15-dev.b80844940-dirty', notes]);
  // Its one link is muted, 11/16, the foreground and underlined under the pointer or the keyboard: never the brand's blue.
  open({ host: { ...host, links: viewerLinks({ version: '0.7.15' }) } });
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const links = [...document.querySelectorAll<HTMLElement>('[data-app-menu] [data-menu-footer] a')];
  expect(links.length).toBe(1);
  for (const link of links) {
    expect(link.className).not.toMatch(/brand/);
    expect(['text-muted-foreground', 'hover:text-foreground', 'hover:underline', 'focus-visible:underline'].every(name => link.className.split(' ').includes(name))).toBe(true);
  }
  expect(document.querySelector('[data-app-menu] [data-menu-footer]')!.className).toContain('text-tiny');
});

// A document in a project: three of them, the one on screen the middle one, a model first (by its id).
const MODEL_ID = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
const PROJECT = { id: 'p1', name: 'parts', root: '/models/parts', documents: [
  { path: MODEL_ID, name: 'bracket', kind: 'model', folder: '/models/parts/src' },
  { path: FILE, name: 'a.step', kind: 'file', folder: '/models/parts' },
  { path: '/models/parts/STEP/b.step', name: 'b.step', kind: 'file', folder: '/models/parts/STEP' },
] };
// A view that keys as a CAD view's shell does (`useViewerShortcuts`, whose single keys reach `useProjectKey`).
const keyed = defineFileRenderer({
  id: 'keyed', priority: 1, matches: () => true, prepare: async () => ({ data: null }),
  load: async () => ({ default: () => { const key = useProjectKey(); return <p tabIndex={-1} onKeyDown={event => { if (key(event.nativeEvent)) event.preventDefault(); }}>shown</p>; } }),
});

it("names the project before the document, which goes to the home at it; no panel of its own: [ and ] and the ⋯ move to the project's previous and next, the name kept on the way, counted", async () => {
  const user = userEvent.setup();
  const reports: { control: string; count: number }[][] = [];
  const opened: string[] = [];
  const onShow = vi.fn();
  const { ControlUsageProvider } = await import('../../dist/usage/controls.js');
  // A host that shows another document as asked, and names nothing until the document is read.
  let answer = () => {};
  const browsing = { ...host, fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } },
    files: { id: 'one', stat: (path: string) => new Promise(resolve => {
      const read = () => resolve({ path, name: path === MODEL_ID ? 'bracket' : path.split('/').pop()!, kind: 'file' as const, extension: 'step', size: 1 });
      if (path === FILE) read(); else answer = read;
    }) },
    navigation: { openFile: (path: string) => { opened.push(path); }, home() {} } };
  const view = (file: string, project: object | null = { ...PROJECT, onShow }) => <ControlUsageProvider report={counts => reports.push(counts)}>
    <FileViewer file={file} host={browsing as any} renderers={[keyed]} state={{}} onStateChange={() => {}} project={project as any} /></ControlUsageProvider>;
  const shown = render(view(FILE));
  const page = await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'parts' }));
  expect(onShow).toHaveBeenCalledTimes(1);
  // The ⋯: Previous in project and Next in project, last.
  await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  const menu = await screen.findByRole('menu');
  expect(within(menu).getAllByRole('menuitem').map(item => item.firstChild?.textContent)).toEqual(['Copy path', 'Previous in project', 'Next in project']);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: /Next in project/ })); });
  // ] and [: the next and the previous, in the project's order.
  fireEvent.keyDown(page, { key: ']' });
  fireEvent.keyDown(page, { key: '[' });
  expect(opened).toEqual(['/models/parts/STEP/b.step', '/models/parts/STEP/b.step', MODEL_ID]);
  // Shown as the host shows it: a model, by its id, is named by the name it was moved to until it is read.
  shown.rerender(view(MODEL_ID));
  expect(fileName().textContent).toBe('bracket');
  await act(async () => answer());
  // At the project's start, [ does nothing and the key is left alone; ] goes on.
  const first = await screen.findByText('shown');
  expect(fireEvent.keyDown(first, { key: '[' })).toBe(true);
  expect(fireEvent.keyDown(first, { key: ']' })).toBe(false);
  expect(opened.at(-1)).toBe(FILE);
  shown.unmount();
  expect(reports.flat().filter(entry => entry.control.startsWith('project_'))).toEqual([{ control: 'project_crumb', count: 1, seconds: 0 },
    { control: 'project_next', count: 3, seconds: 0 }, { control: 'project_previous', count: 1, seconds: 0 }]);
});

it("moves through nothing where the document is in no project, the project has no other, or the view shows its file alone", async () => {
  const opened: string[] = [];
  const browsing = { ...host, navigation: { openFile: (path: string) => { opened.push(path); } } };
  const view = render(<FileViewer file={FILE} host={browsing as any} renderers={[keyed]} state={{}} onStateChange={() => {}} project={null} />);
  fireEvent.keyDown(await screen.findByText('shown'), { key: ']' });
  view.rerender(<FileViewer file={FILE} host={browsing as any} renderers={[keyed]} state={{}} onStateChange={() => {}}
    project={{ ...PROJECT, documents: [PROJECT.documents[1]], onShow() {} } as any} />);
  fireEvent.keyDown(screen.getByText('shown'), { key: ']' });
  view.rerender(<FileViewer file={FILE} host={{ ...host, navigation: {} } as any} renderers={[keyed]} state={{}} onStateChange={() => {}}
    project={{ ...PROJECT, onShow() {} } as any} />);
  fireEvent.keyDown(screen.getByText('shown'), { key: ']' });
  expect(opened).toEqual([]);
});

it("offers Open in new tab (or Open in browser) for the document on screen where the host can open it beside, never twice beside Open in's Browser", async () => {
  const beside = vi.fn();
  const menuOf = async (navigation: object, perform: object = { 'copy-path': async () => {} }) => {
    cleanup();
    render(<FileViewer file={FILE} host={{ ...host, fileActions: { platform: 'darwin', perform }, navigation: { openFile() {}, ...navigation } } as any}
      renderers={[renderer]} state={{}} onStateChange={() => {}} />);
    await screen.findByText('shown');
    await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    return screen.findByRole('menu');
  };
  // A web page's: Open in new tab, after Copy path.
  let menu = await menuOf({ openBeside: { kind: 'tab', open: beside } });
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in new tab']);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: 'Open in new tab' })); });
  expect(beside).toHaveBeenCalledWith({ document: FILE });
  // An app's frame: Open in browser, where Open in has no Browser of its own; none where it has.
  menu = await menuOf({ openBeside: { kind: 'browser', open: beside } });
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in browser']);
  menu = await menuOf({ openBeside: { kind: 'browser', open: beside } }, { 'copy-path': async () => {}, browser: async () => {} });
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Open in']);
  // A host with neither: nothing.
  menu = await menuOf({});
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path']);
});

it("opens the search with ⌘K on a Mac and Ctrl+K elsewhere, from a field too, and from Search documents in the document's ⋯, its key at the right; never in Preview or over another dialog", async () => {
  const onSearch = vi.fn();
  let report: ((previewing: boolean) => void) | undefined;
  const previewed = defineFileRenderer({ id: 'previewed', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: (props: any) => { report = props.onPreviewChange; return <input aria-label="note" />; } }) });
  const homed = (platform: string) => ({ ...host, environment: { colorScheme: 'light', platform }, navigation: { openFile() {}, home() {} } });
  const view = render(<FileViewer file={FILE} host={homed('darwin') as any} renderers={[previewed]} state={{}} onStateChange={() => {}} onSearch={onSearch} />);
  const note = await screen.findByRole('textbox', { name: 'note' });
  fireEvent.keyDown(note, { key: 'k', ctrlKey: true });
  expect(onSearch).not.toHaveBeenCalled();
  expect(fireEvent.keyDown(note, { key: 'k', metaKey: true })).toBe(false);
  expect(onSearch).toHaveBeenCalledTimes(1);
  // Held, it does not repeat.
  fireEvent.keyDown(note, { key: 'k', metaKey: true, repeat: true });
  expect(onSearch).toHaveBeenCalledTimes(1);
  // In Preview, nothing.
  act(() => report!(true));
  fireEvent.keyDown(document.body, { key: 'k', metaKey: true });
  act(() => report!(false));
  // Over another dialog, nothing.
  const dialog = document.body.appendChild(Object.assign(document.createElement('div'), { role: 'dialog' }));
  dialog.setAttribute('role', 'dialog');
  fireEvent.keyDown(document.body, { key: 'k', metaKey: true });
  dialog.remove();
  expect(onSearch).toHaveBeenCalledTimes(1);
  // Off a Mac, Ctrl+K.
  view.rerender(<FileViewer file={FILE} host={homed('win32') as any} renderers={[previewed]} state={{}} onStateChange={() => {}} onSearch={onSearch} />);
  fireEvent.keyDown(document.body, { key: 'K', ctrlKey: true });
  expect(onSearch).toHaveBeenCalledTimes(2);
  // The document's ⋯: Search documents with its key, in a group of its own where the host can do nothing else with the file.
  const fileMenu = async () => {
    await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
    return screen.findByRole('menu');
  };
  let menu = await fileMenu();
  expect([within(menu).getAllByRole('menuitem').map(item => item.textContent), within(menu).queryByRole('separator')]).toEqual([['Search documentsCtrl+K'], null]);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: /Search documents/ })); });
  expect(onSearch).toHaveBeenCalledTimes(3);
  cleanup();
  // The first of the last group, before Previous and Next in project: every document where the host has the search,
  // in a project of several or not.
  const acting = { ...homed('darwin'), fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } } };
  const shown = render(<FileViewer file={FILE} host={acting as any} renderers={[renderer]} state={{}} onStateChange={() => {}} onSearch={onSearch}
    project={{ ...PROJECT, onShow() {} } as any} />);
  await screen.findByText('shown');
  menu = await fileMenu();
  expect([within(menu).getAllByRole('menuitem').map(item => item.firstChild?.nodeType === 1 ? item.textContent : item.firstChild?.textContent),
    within(menu).getAllByRole('separator').length, within(menu).getByRole('menuitem', { name: /Search documents/ }).querySelector('[data-slot="dropdown-menu-shortcut"]')?.textContent])
    .toEqual([['Copy path', 'Search documents⌘K', 'Previous in project', 'Next in project'], 1, '⌘K']);
  fireEvent.keyDown(menu, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  // A standalone document: Search documents, then Import its folder as a project, one group.
  shown.rerender(<FileViewer file={FILE} host={acting as any} renderers={[renderer]} state={{}} onStateChange={() => {}} onSearch={onSearch} onImportFolder={() => {}} />);
  menu = await fileMenu();
  expect([within(menu).getAllByRole('menuitem').map(item => item.textContent), within(menu).getAllByRole('separator').length])
    .toEqual([['Copy path', 'Search documents⌘K', 'Import its folder as a project…'], 1]);
  cleanup();
  // A host with no search has neither the key nor the item.
  render(<FileViewer file={FILE} host={acting as any} renderers={[previewed]} state={{}} onStateChange={() => {}} />);
  await screen.findByRole('textbox', { name: 'note' });
  fireEvent.keyDown(document.body, { key: 'k', metaKey: true });
  menu = await fileMenu();
  expect([onSearch.mock.calls.length, within(menu).getAllByRole('menuitem').map(item => item.textContent)]).toEqual([3, ['Copy path']]);
});

it('has no file menu on a document with no file of its own, which its name names; a document in no project offers Import its folder as a project where the host can', async () => {
  const id = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
  const model = { ...host, fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } }, files: { id: 'one',
    stat: async (path: string) => ({ path, name: 'bracket', navigationPath: null, kind: 'file' as const, extension: 'xbf', size: 0 }) } };
  open({ host: model, file: id });
  await screen.findByText('shown');
  // Its name is the model's, a name and no button; no file menu.
  expect([fileName().tagName, fileName().textContent]).toEqual(['SPAN', 'bracket']);
  expect(labels()).not.toContain('File actions');
  cleanup();
  // A file in no project: its ⋯ ends in Import its folder as a project, which the host does; in a project, it has none.
  const onImportFolder = vi.fn();
  const withMenu = { ...host, fileActions: { platform: 'darwin', perform: { 'copy-path': async () => {} } } };
  const view = render(<FileViewer file={FILE} host={withMenu as any} renderers={[renderer]} state={{}} onStateChange={() => {}} onImportFolder={onImportFolder} />);
  await screen.findByText('shown');
  await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  await act(async () => { fireEvent.click(await screen.findByRole('menuitem', { name: 'Import its folder as a project…' })); });
  expect(onImportFolder).toHaveBeenCalledTimes(1);
  view.rerender(<FileViewer file={FILE} host={withMenu as any} renderers={[renderer]} state={{}} onStateChange={() => {}} onImportFolder={onImportFolder}
    project={{ id: 'p1', name: 'parts', root: '/models/parts', documents: [], onShow() {} }} />);
  await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect(within(await screen.findByRole('menu')).getAllByRole('menuitem').map(item => item.textContent)).not.toContain('Import its folder as a project…');
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
  expect((await screen.findByRole('tooltip')).textContent).toBe('The source was moved, or is gone.');
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
  expect((await screen.findByRole('tooltip')).textContent).toBe('The source was moved, or is gone.');
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

