import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewerNavbar } from '../../../dist/file-viewer/navigation/ViewerNavbar.js';
import { ControlUsageProvider } from '../../../dist/usage/controls.js';
import { DropdownMenuItem } from '../../../dist/primitives/dropdown-menu.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const FILE = '/home/me/models/a.step';
const MODEL = '6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab';
const name = () => document.querySelector('[data-file-name]')!;
const fileMenu = (extra = {}) => ({ platform: 'darwin' as const, capabilities: new Set(['copy-path'] as const), onAction: vi.fn(), ...extra });

// The ⋯ menu, opened as a press opens it.
async function openMenu() {
  await act(async () => { fireEvent.pointerDown(screen.getByTestId('file-actions'), { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  return screen.findByRole('menu');
}

it('shows the name alone, with no glyph and no menu of its own: moving to another document is the search\'s', () => {
  const { rerender } = render(<ViewerNavbar file={FILE} />);
  expect([name().tagName, name().textContent, name().querySelector('svg')]).toEqual(['SPAN', 'a.step', null]);
  // A model's document is named by its name, never by its id; until the name is known, its place is empty.
  rerender(<ViewerNavbar file={MODEL} name="bracket" />);
  expect(name().textContent).toBe('bracket');
  rerender(<ViewerNavbar file={MODEL} />);
  expect(name().textContent).toBe('');
  expect(document.querySelector('[data-navbar-project]')).toBeNull();
});

it("puts the project's name and a slash before the document's, muted, a button where it has no address: a press goes to the home at it, counted", () => {
  const reports: { control: string; count: number }[][] = [];
  const onOpen = vi.fn();
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={FILE} project={{ name: 'heart-tag', onOpen }} /></ControlUsageProvider>);
  const crumb = document.querySelector('[data-navbar-project]')!;
  // Named by the project's name, as the text it shows.
  const button = within(crumb as HTMLElement).getByRole('button', { name: 'heart-tag' });
  expect([button.tagName, button.textContent, button.className.includes('text-muted-foreground'), within(crumb as HTMLElement).queryByRole('link')])
    .toEqual(['BUTTON', 'heart-tag', true, null]);
  // Before the name, in the row's order; the name keeps its width, the project's name shrinks.
  expect(crumb.compareDocumentPosition(name()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect([crumb.className.includes('min-w-0'), name().className.includes('shrink-0'), name().className.includes('max-w-[65%]')]).toEqual([true, true, true]);
  fireEvent.click(button);
  expect(onOpen).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'project_crumb', count: 1, seconds: 0 }]);
});

it("is a real link where the host gives the project's page an address: a plain click shows it here, a modified or middle click is the browser's", () => {
  const onOpen = vi.fn();
  render(<ViewerNavbar file={FILE} project={{ name: 'heart-tag', href: '/projects/p1', onOpen }} />);
  const link = screen.getByRole('link', { name: 'heart-tag' });
  expect(link.getAttribute('href')).toBe('/projects/p1');
  // A plain click: this view, the link's own navigation held back.
  expect(fireEvent.click(link)).toBe(false);
  expect(onOpen).toHaveBeenCalledTimes(1);
  // ⌘ or Ctrl and a click, Shift, a middle click: the browser's (a new tab or window), left alone.
  for (const modifier of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) expect(fireEvent.click(link, modifier)).toBe(true);
  expect(onOpen).toHaveBeenCalledTimes(1);
});

it("on a phone the project's name is a control-sized folder tile, named by the project, the slash after it and the document's name whole", async () => {
  const { ViewerMobileContext } = await import('../../../dist/file-viewer/responsive.js');
  const onOpen = vi.fn();
  render(<ViewerMobileContext.Provider value={true}><ViewerNavbar file={FILE} project={{ name: 'heart-tag', href: '/projects/p1', onOpen }} /></ViewerMobileContext.Provider>);
  const tile = screen.getByRole('link', { name: 'heart-tag' });
  expect([tile.hasAttribute('data-project-tile'), tile.textContent, Boolean(tile.querySelector('svg')), tile.className.includes('w-control')]).toEqual([true, '', true, true]);
  expect(document.querySelector('[data-navbar-project]')!.textContent).toBe('/');
  expect(name().textContent).toBe('a.step');
  fireEvent.click(tile);
  expect(onOpen).toHaveBeenCalledTimes(1);
});

it("ends a document's ⋯ in Import its folder as a project where the host can, after the rest, disabled while its source is gone, counted", async () => {
  const reports: { control: string; count: number }[][] = [];
  const onImportFolder = vi.fn();
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}>
    <ViewerNavbar file={FILE} fileMenu={fileMenu({ onImportFolder })} /></ControlUsageProvider>);
  const menu = await openMenu();
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Import its folder as a project…']);
  expect(within(menu).getAllByRole('separator')).toHaveLength(1);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: 'Import its folder as a project…' })); });
  expect(onImportFolder).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(reports.flat()).toEqual([{ control: 'file_import_folder', count: 1, seconds: 0 }]);
  // A ⋯ with it alone, and with no separator; a source gone draws it disabled.
  render(<ViewerNavbar file={FILE} fileMenu={fileMenu({ capabilities: new Set(), onImportFolder, sourceMissing: true })} />);
  const alone = await openMenu();
  expect(within(alone).queryByRole('separator')).toBeNull();
  expect(within(alone).getByRole('menuitem', { name: 'Import its folder as a project…' }).getAttribute('data-disabled')).toBe('');
});

it("puts Open in new tab with the places it opens in, and Previous and Next in project last, their keys at the right, each disabled at its end, counted by the host's own", async () => {
  const beside = { label: 'Open in new tab', onSelect: vi.fn() };
  const previous = vi.fn();
  const { rerender } = render(<ViewerNavbar file={FILE} fileMenu={fileMenu({ capabilities: new Set(['copy-path', 'copy-link']), beside,
    neighbours: { previous, next: null }, items: <DropdownMenuItem>Export</DropdownMenuItem> })} />);
  let menu = await openMenu();
  // From the document itself outwards: copying it, where it opens, what is made of it, then its project.
  expect(within(menu).getAllByRole('menuitem').map(item => item.firstChild?.textContent)).toEqual(['Copy path', 'Copy link', 'Open in new tab', 'Export', 'Previous in project', 'Next in project']);
  expect(within(menu).getAllByRole('separator')).toHaveLength(1);
  const item = (label: string) => within(menu).getByRole('menuitem', { name: new RegExp(label) });
  expect([item('Previous').querySelector('[data-slot="dropdown-menu-shortcut"]')?.textContent, item('Next').querySelector('[data-slot="dropdown-menu-shortcut"]')?.textContent])
    .toEqual(['[', ']']);
  // At the project's end, Next is there and off.
  expect([item('Previous').hasAttribute('data-disabled'), item('Next').hasAttribute('data-disabled')]).toEqual([false, true]);
  await act(async () => { fireEvent.click(item('Previous')); });
  expect(previous).toHaveBeenCalledTimes(1);
  // Open in new tab: the host's.
  rerender(<ViewerNavbar file={FILE} fileMenu={fileMenu({ capabilities: new Set(), beside })} />);
  menu = await openMenu();
  expect(within(menu).getAllByRole('menuitem').map(entry => entry.textContent)).toEqual(['Open in new tab']);
  await act(async () => { fireEvent.click(within(menu).getByRole('menuitem', { name: 'Open in new tab' })); });
  expect(beside.onSelect).toHaveBeenCalledTimes(1);
});

it("draws the logo as the way home where it is handed one (a link with an address, a button without), and as the app menu's button where it is handed only a menu; over the home too, first, the panel's toggle after it", async () => {
  const onHome = vi.fn();
  const menu = { colorScheme: { preference: 'system' as const, onPreferenceChange() {} } };
  const logo = () => document.querySelector<HTMLElement>('[data-navbar-logo]');
  // With a home: the way home, whatever menu it is also handed, over a file and over the home (no file) alike.
  const { rerender } = render(<ViewerNavbar file={FILE} onHome={onHome} homeHref="/" menu={menu} />);
  expect([logo()!.tagName, logo()!.getAttribute('href'), logo()!.getAttribute('aria-label'), logo()!.getAttribute('data-navbar-logo'), logo()!.querySelectorAll('img').length])
    .toEqual(['A', '/', 'Home', 'home', 1]);
  expect(fireEvent.click(logo()!)).toBe(false);
  expect(fireEvent.click(logo()!, { ctrlKey: true })).toBe(true);
  expect(onHome).toHaveBeenCalledTimes(1);
  const toggle = { open: true, label: 'Hide panel', shortcut: '⌘\\', toggle: vi.fn() };
  rerender(<ViewerNavbar onHome={onHome} menu={menu} panels={{ left: toggle }} homeSlots={{ left() {}, right() {} }} />);
  expect([logo()!.tagName, logo()!.getAttribute('type'), logo()!.getAttribute('aria-haspopup')]).toEqual(['BUTTON', 'button', null]);
  fireEvent.click(logo()!);
  expect([onHome.mock.calls.length, screen.queryByRole('menu')]).toEqual([2, null]);
  // The logo is the row's first control over the home as over a file, the panel's toggle after it.
  const lead = document.querySelector('nav')!;
  const second = lead.children[1]!.querySelector<HTMLElement>('[data-navbar-panel="left"]')!;
  expect([lead.firstElementChild === logo(), second.getAttribute('aria-expanded'), second.getAttribute('aria-label')]).toEqual([true, 'true', 'Hide panel']);
  fireEvent.click(second);
  expect(toggle.toggle).toHaveBeenCalledTimes(1);
  // With no home: the app menu's button, as it was.
  rerender(<ViewerNavbar file={FILE} menu={menu} />);
  expect([logo()!.getAttribute('aria-label'), logo()!.getAttribute('data-navbar-logo'), logo()!.hasAttribute('data-navbar-menu')]).toEqual(['Menu', 'menu', true]);
  await act(async () => { fireEvent.pointerDown(logo()!, { button: 0, ctrlKey: false, pointerType: 'mouse' }); });
  expect((await screen.findByRole('menu', { name: 'Menu' })).querySelector('[data-menu-theme]')).not.toBeNull();
  // With neither: no logo.
  rerender(<ViewerNavbar file={FILE} />);
  expect(logo()).toBeNull();
});

it("leads the ⋯'s last group with Search documents and its key, before Previous and Next in project, and alone where there is nothing else", async () => {
  const onSelect = vi.fn();
  const { rerender } = render(<ViewerNavbar file={FILE} fileMenu={fileMenu({ search: { onSelect, shortcut: '⌘K' }, neighbours: { previous: null, next: vi.fn() } })} />);
  let menu = await openMenu();
  expect(within(menu).getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Search documents⌘K', 'Previous in project[', 'Next in project]']);
  expect(within(menu).getAllByRole('separator')).toHaveLength(1);
  const search = within(menu).getByRole('menuitem', { name: /Search documents/ });
  expect([search.hasAttribute('data-menu-search'), search.querySelector('svg') !== null, search.previousElementSibling?.getAttribute('role')]).toEqual([true, true, 'separator']);
  await act(async () => { fireEvent.click(search); });
  expect(onSelect).toHaveBeenCalledTimes(1);
  rerender(<ViewerNavbar file={FILE} fileMenu={fileMenu({ capabilities: new Set(), search: { onSelect } })} />);
  menu = await openMenu();
  expect([within(menu).getAllByRole('menuitem').map(item => item.textContent), within(menu).queryByRole('separator')]).toEqual([['Search documents'], null]);
});
