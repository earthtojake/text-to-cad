import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DocumentSearch, useDocumentSearch } from '../../dist/search/DocumentSearch.js';
import { ViewerHostContext } from '../../dist/host/context.js';
import { ViewerMobileContext } from '../../dist/file-viewer/responsive.js';
import { ControlUsageProvider } from '../../dist/usage/controls.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// A row, as a host lists it, opened at `opened` (seconds).
const doc = (path: string, extra: Record<string, unknown> = {}) => ({ path, id: `id:${path}`, name: path.split('/').pop()!, folder: '', opened: null,
  updated: null, created: null, pinned: false, missing: false, thumbnail: null, pictured: null, ...extra }) as any;
const ACTUATOR = doc('/w/drive/actuator.xbf', { id: 'm1', updated: 50, thumbnail: 'pic-1', project: 'p1' });
const GEAR = doc('/w/drive/gear.step', { opened: 100, project: 'p1' });
const SHAFT = doc('/w/drive/shaft.stl', { opened: 10, project: 'p1' });
const NUT = doc('/w/drive/STEP/nut.step', { project: 'p1' });
const BLANK = doc('/w/examples/gear_blank.step', { opened: 70, project: 'p2' });
const LOOSE = doc('/tmp/gearbox.step', { opened: 90, project: null });
const PROJECTS = [{ id: 'p1', name: 'drive', root: '/w/drive', opened: 1, missing: false }, { id: 'p2', name: 'examples', root: '/w/examples', opened: 1, missing: false }];
// The document on screen: the model, at the top of the drive project.
const ON_MODEL = { id: 'm1', path: ACTUATOR.path, project: { id: 'p1', name: 'drive', folder: '' } };
// The drive project's folder as its host answers it: the files directly in it; with words, every file below that holds them.
const folderOf = (files: any[]) => vi.fn(async (_id: string, { path = '', q = '' }: { path?: string; q?: string }) => {
  const base = path ? `/w/drive/${path}` : '/w/drive';
  const below = files.map(file => ({ file, rest: file.path.slice(base.length + 1) })).filter(({ file }) => file.path.startsWith(`${base}/`));
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  return { project: PROJECTS[0], path, folders: [], truncated: false, documents: (words.length
    ? below.filter(({ rest }) => words.every(word => rest.toLowerCase().includes(word))) : below.filter(({ rest }) => !rest.includes('/'))).map(({ file }) => file) };
});

function library(overrides: Record<string, unknown> = {}) {
  return { list: vi.fn(async () => [GEAR, LOOSE, BLANK]), projects: vi.fn(async () => PROJECTS), folder: folderOf([ACTUATOR, GEAR, SHAFT, NUT]),
    change: vi.fn(), open: vi.fn(async () => {}), thumbnail: vi.fn(async (model: any) => (model.thumbnail ? `blob:${model.thumbnail}` : null)), ...overrides };
}
// The search as `CadViewer` mounts it: under the viewer's host (its platform) and layout, a control opening it.
function Page({ source, navigation = {}, current = ON_MODEL as object | null, platform = 'darwin', mobile = false, report = (_: unknown) => {} }:
  { source: any; navigation?: object; current?: object | null; platform?: string; mobile?: boolean; report?: (counts: any) => void }) {
  const search = useDocumentSearch();
  return <ViewerHostContext.Provider value={{ environment: { colorScheme: 'light', platform } } as any}>
    <ViewerMobileContext.Provider value={mobile}><ControlUsageProvider report={report}>
      <button type="button" onClick={search.show}>Search</button>
      <DocumentSearch search={search} library={source} navigation={navigation as any} current={current as any} />
    </ControlUsageProvider></ViewerMobileContext.Provider>
  </ViewerHostContext.Provider>;
}
const input = () => screen.getByRole('combobox', { name: 'Search documents' }) as HTMLInputElement;
const options = () => screen.queryAllByRole('option');
const rowNames = () => options().map(option => option.querySelector('.truncate')!.textContent);
const active = () => document.getElementById(input().getAttribute('aria-activedescendant') ?? '')?.querySelector('.truncate')?.textContent ?? null;
const groups = () => [...document.querySelectorAll('[data-search-group]')].map(group => [group.querySelector('[data-search-heading]')?.textContent ?? null,
  [...group.querySelectorAll('[role=option]')].map(option => [option.querySelector('.truncate')!.textContent, option.querySelector('[data-search-detail]')!.textContent])]);
async function openSearch(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Search' }));
  await waitFor(() => expect(document.querySelector('[data-search-status="reading"]')).toBeNull());
}

it("opens as a dialog with the keyboard in its input, reads the library as it opens, and lists the project on screen, its own row marked and never opened", async () => {
  const user = userEvent.setup();
  const source = library();
  let answer = (_: unknown) => {};
  source.list.mockImplementationOnce(() => new Promise(resolve => { answer = resolve; }) as any);
  render(<Page source={source} />);
  await user.click(screen.getByRole('button', { name: 'Search' }));
  const dialog = screen.getByRole('dialog', { name: 'Search documents' });
  expect(document.activeElement).toBe(input());
  // While it reads: placeholders where the rows will be, and a line saying so.
  expect([document.querySelectorAll('[data-search-placeholder]').length, within(dialog).getByRole('status').textContent, input().getAttribute('aria-expanded')])
    .toEqual([3, 'Reading the documents…', 'false']);
  await act(async () => answer([GEAR, LOOSE, BLANK]));
  expect(source.projects).toHaveBeenCalledTimes(1);
  // Nothing typed: the folder of the project the document on screen is in, as its host lists it.
  expect(source.folder).toHaveBeenCalledWith('p1', { path: '' });
  expect(groups()).toEqual([['In drive', [['actuator.xbf', 'On screen'], ['gear.step', 'STEP'], ['shaft.stl', 'STL']]]]);
  const own = options()[0];
  expect([own.getAttribute('aria-current'), own.getAttribute('aria-disabled'), own.hasAttribute('href')]).toEqual(['page', 'true', false]);
  // The keys start on the first row that opens; a press on its own row opens nothing and keeps it open.
  expect([input().getAttribute('aria-expanded'), active()]).toEqual(['true', 'gear.step']);
  await user.click(own);
  expect([source.open, screen.queryByRole('dialog') !== null]).toEqual([source.open, true]);
  expect(source.open).not.toHaveBeenCalled();
  // Every picture is the library's, read for the rows drawn; the kind's glyph where there is none.
  await waitFor(() => expect(own.querySelector('img')?.getAttribute('src')).toBe('blob:pic-1'));
  expect([source.thumbnail.mock.calls.length, options()[1].querySelector('[data-search-picture] img')]).toEqual([1, null]);
});

it("says an .xbf is an XBF where its parts are not known, and a file its format, in the project on screen", async () => {
  const user = userEvent.setup();
  render(<Page source={library()} current={{ id: GEAR.id, path: GEAR.path, project: { id: 'p1', name: 'drive', folder: '' } }} />);
  await openSearch(user);
  expect(groups()).toEqual([['In drive', [['actuator.xbf', 'XBF'], ['gear.step', 'On screen'], ['shaft.stl', 'STL']]]]);
});

it("says a model is a Part when its document holds one part and an Assembly when it holds more, an xbf too; a file of another format keeps its format", async () => {
  const user = userEvent.setup();
  const documents = [doc('/w/drive/hinge.xbf', { parts: 2 }), doc('/w/drive/pin.xbf', { parts: 1 }), doc('/w/drive/unread.xbf'), doc('/w/drive/pair.step', { parts: 2 }), GEAR];
  render(<Page source={library({ folder: folderOf(documents) })} current={{ id: GEAR.id, path: GEAR.path, project: { id: 'p1', name: 'drive', folder: '' } }} />);
  await openSearch(user);
  expect(groups()).toEqual([['In drive', [['hinge.xbf', 'Assembly'], ['pin.xbf', 'Part'], ['unread.xbf', 'XBF'], ['pair.step', 'STEP'], ['gear.step', 'On screen']]]]);
});

it("asks the host for the project on screen's files that hold the words, then finds the library's others; a row says its project, or a dash, and the words found are lit", async () => {
  const user = userEvent.setup();
  const source = library();
  render(<Page source={source} />);
  await openSearch(user);
  await user.type(input(), 'gear');
  // Once typing rests, one search of the whole project, from its root.
  await waitFor(() => expect(source.folder).toHaveBeenLastCalledWith('p1', { q: 'gear' }));
  await waitFor(() => expect(groups()).toEqual([['In drive', [['gear.step', 'STEP']]], ['Other projects', [['gearbox.step', '—'], ['gear_blank.step', 'examples']]]]));
  expect([...options()[0].querySelectorAll('[data-tree-filter-hit]')].map(hit => hit.textContent).join('')).toBe('gear');
  // Every level of the project is searched: a file's folder below the root is in what the words are found in.
  await user.clear(input());
  await user.type(input(), 'step nut');
  await waitFor(() => expect(rowNames()).toEqual(['nut.step']));
  await user.type(input(), ' nothing');
  expect([options(), screen.getByRole('status').textContent, input().getAttribute('aria-expanded')]).toEqual([[], 'Nothing matches “step nut nothing”', 'false']);
});

it("with nothing typed and no project on screen (the home) lists the latest documents under Recent, each saying its project", async () => {
  const user = userEvent.setup();
  render(<Page source={library()} current={null} />);
  await openSearch(user);
  expect(groups()).toEqual([['Recent', [['gear.step', 'drive'], ['gearbox.step', '—'], ['gear_blank.step', 'examples']]]]);
});

it("moves with the arrows, Home and End, past the row on screen; Enter opens the row here through the library and closes, the focus back where it was; counted, never what was typed", async () => {
  const user = userEvent.setup();
  const reports: { control: string; count: number }[][] = [];
  const source = library();
  const view = render(<Page source={source} report={counts => reports.push(counts)} />);
  await openSearch(user);
  await user.keyboard('{ArrowDown}');
  expect(active()).toBe('shaft.stl');
  await user.keyboard('{ArrowDown}');
  expect(active()).toBe('shaft.stl');
  await user.keyboard('{ArrowUp}{ArrowUp}');
  expect(active()).toBe('gear.step');
  await user.keyboard('{End}');
  expect(active()).toBe('shaft.stl');
  await user.keyboard('{Home}');
  expect(active()).toBe('gear.step');
  // Typing always lands in the input.
  await user.keyboard('ge');
  expect(input().value).toBe('ge');
  await user.keyboard('{Enter}');
  expect(source.open).toHaveBeenCalledWith(GEAR);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Search' }));
  view.unmount();
  expect(reports.flat().map(entry => entry.control).sort()).toEqual(['search_open', 'search_pick']);
});

it("closes on Escape, on a press outside and on ⌘K again, the focus back where it was", async () => {
  const user = userEvent.setup();
  render(<Page source={library()} />);
  const opener = screen.getByRole('button', { name: 'Search' });
  for (const close of [() => user.keyboard('{Escape}'), () => user.keyboard('{Meta>}k{/Meta}'),
    async () => { fireEvent.pointerDown(document.body); fireEvent.pointerUp(document.body); fireEvent.click(document.body); }]) {
    await openSearch(user);
    await close();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(opener);
  }
});

it("where the host gives a document an address, a row is a real link: a click opens it here, a modified or middle click is the browser's", async () => {
  const user = userEvent.setup();
  const reports: { control: string; count: number }[][] = [];
  const source = library();
  const view = render(<Page source={source} navigation={{ hrefOf: (target: { document: string }) => `/${target.document}` }} report={counts => reports.push(counts)} />);
  await openSearch(user);
  const [own, gear] = options();
  expect([own.tagName, own.hasAttribute('href'), gear.tagName, gear.getAttribute('href')]).toEqual(['DIV', false, 'A', '/id:/w/drive/gear.step']);
  // ⌘ and a click, a middle click: left to the browser, counted as a new tab, the search open.
  expect(fireEvent.click(gear, { metaKey: true })).toBe(true);
  fireEvent(gear, new MouseEvent('auxclick', { bubbles: true, cancelable: true, button: 1 }));
  expect(source.open).not.toHaveBeenCalled();
  // A plain click: here.
  expect(fireEvent.click(gear)).toBe(false);
  expect(source.open).toHaveBeenCalledWith(GEAR);
  view.unmount();
  expect(reports.flat().filter(entry => entry.control === 'search_new_tab')).toEqual([{ control: 'search_new_tab', count: 2, seconds: 0 }]);
});

it("opens beside where the host can: ⌘Enter (Ctrl+Enter off a Mac), and the row's own button; neither, nor its key's hint, where it cannot", async () => {
  const user = userEvent.setup();
  const beside = vi.fn();
  const source = library();
  const view = render(<Page source={source} navigation={{ openBeside: { kind: 'tab', open: beside } }} />);
  await openSearch(user);
  expect(screen.getByText('Open in new tab', { selector: '[data-search-keys] *' })).not.toBeNull();
  // The active row shows its button; the row on screen has none.
  const buttons = () => [...document.querySelectorAll('[data-search-beside]')];
  expect(buttons()).toHaveLength(2);
  await user.keyboard('{Meta>}{Enter}{/Meta}');
  expect([beside.mock.calls, source.open.mock.calls]).toEqual([[[{ document: 'id:/w/drive/gear.step' }]], []]);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await openSearch(user);
  fireEvent.click(buttons()[1]);
  expect(beside).toHaveBeenLastCalledWith({ document: 'id:/w/drive/shaft.stl' });
  view.unmount();
  // Off a Mac, Ctrl+Enter; an app's frame says Open in browser.
  render(<Page source={source} platform="win32" navigation={{ openBeside: { kind: 'browser', open: beside } }} />);
  await openSearch(user);
  expect(document.querySelector('[data-search-keys]')!.textContent).toContain('Ctrl+↵Open in browser');
  await user.keyboard('{Control>}{Enter}{/Control}');
  expect(beside).toHaveBeenCalledTimes(3);
  cleanup();
  // A host that cannot: no button, no hint, and ⌘Enter opens nothing.
  render(<Page source={source} />);
  await openSearch(user);
  expect([buttons(), document.querySelector('[data-search-keys]')!.textContent]).toEqual([[], '↑↓Move↵OpenEscClose']);
  await user.keyboard('{Meta>}{Enter}{/Meta}');
  expect([source.open.mock.calls.length, screen.queryByRole('dialog') !== null]).toEqual([0, true]);
});

it("says when the read failed and offers nothing; a read of the projects that fails leaves the documents unnamed by project", async () => {
  const user = userEvent.setup();
  render(<Page source={library({ list: vi.fn(async () => { throw new Error('offline'); }) })} />);
  await openSearch(user);
  expect([options(), screen.getByRole('status').textContent, input().getAttribute('aria-expanded')]).toEqual([[], "Couldn't read the documents.", 'false']);
  await user.keyboard('{Enter}');
  cleanup();
  render(<Page source={library({ projects: vi.fn(async () => { throw new Error('offline'); }) })} current={null} />);
  await openSearch(user);
  expect(groups()).toEqual([['Recent', [['gear.step', '—'], ['gearbox.step', '—'], ['gear_blank.step', '—']]]]);
});

it('draws at most 50 rows and says how many there are', async () => {
  const user = userEvent.setup();
  const many = Array.from({ length: 64 }, (_, index) => doc(`/w/drive/part-${index}.step`, { opened: index }));
  render(<Page source={library({ list: vi.fn(async () => many), projects: vi.fn(async () => []) })} current={null} />);
  await openSearch(user);
  expect([options().length, document.querySelector('[data-search-more]')!.textContent]).toEqual([50, '50 of 64 shown: type to narrow them down']);
});

it("on a phone is a sheet the width of the view under the navbar, with no key hints", async () => {
  const user = userEvent.setup();
  render(<Page source={library()} mobile />);
  await openSearch(user);
  const dialog = screen.getByRole('dialog');
  expect([dialog.getAttribute('data-search-layout'), document.querySelector('[data-search-keys]'), dialog.className.includes('inset-x-0')]).toEqual(['sheet', null, true]);
});
