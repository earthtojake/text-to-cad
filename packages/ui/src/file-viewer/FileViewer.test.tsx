import { createPortal } from 'react-dom';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { isMissingFileError } from '@text-to-cad/core/client';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';

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

it('draws the navbar over every file, named by its name, and over the home with only its menu, update, Full size and the host\'s last control; never over a view shown small', async () => {
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
  // history, and the host's update, Full size and Open in browser, as over a file; no file, no box for view controls.
  const back = vi.fn();
  open({ host: { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home() {} } }, file: null,
    history: { canGoBack: true, canGoForward: false, back, forward() {} },
    update: <button type="button" aria-label="Update to 0.7.5" />, fullSize: <button type="button" aria-label="Full size" />,
    openInBrowser: <button type="button" aria-label="Open in browser" />,
    presentation: { home: <p>home</p> } } as any);
  await screen.findByText('home');
  expect([labels(), document.querySelector('[data-file-name]'), document.querySelector('[data-view-controls]')])
    .toEqual([['Menu', 'Back', 'Forward', 'Update to 0.7.5', 'Full size', 'Open in browser'], null, null]);
  expect((screen.getByRole('button', { name: 'Forward' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Back' }));
  expect(back).toHaveBeenCalledOnce();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Menu' }));
  expect(screen.queryByRole('menuitem', { name: 'Back to files' })).toBeNull();
});

it('keeps the right of the navbar for the host\'s update button and Full size, then hands the renderer a box for its own view controls, then the host\'s Open in browser, last; a view shown small has no navbar and no box', async () => {
  // A renderer that draws its view controls into the box it is handed (the CAD viewer's Display
  // and Preview), and over its view where it is handed none.
  const handed: (HTMLElement | null)[] = [];
  const slotted = defineFileRenderer({
    id: 'slotted', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: (props: any) => {
      handed.push(props.navbarSlot ?? null);
      expect('onFullscreenChange' in props).toBe(false);
      const control = <button type="button" aria-label="Preview" />;
      return props.navbarSlot ? createPortal(control, props.navbarSlot) : control;
    } }),
  });
  const view = (extra: object = {}) => render(<FileViewer file={FILE} host={{ ...host, ...extra } as any} renderers={[slotted]} state={{}} onStateChange={() => {}}
    update={<button type="button" aria-label="Update to 0.7.5" />} fullSize={<button type="button" aria-label="Full size" />}
    openInBrowser={<button type="button" aria-label="Open in browser" />} />);
  view();
  await screen.findByRole('button', { name: 'Preview' });
  expect([labels(), screen.getByRole('button', { name: 'Preview' }).parentElement!.hasAttribute('data-view-controls')]).toEqual([['Update to 0.7.5', 'Full size', 'Preview', 'Open in browser'], true]);
  cleanup();
  handed.length = 0;
  view({ environment: { colorScheme: 'light', compact: true } });
  await screen.findByRole('button', { name: 'Preview' });
  expect([navbar(), handed.at(-1)]).toEqual([null, null]);
});

it('draws Back and Forward between the logo and the file\'s name where the host keeps the view\'s own history, each disabled where it has nowhere to go', async () => {
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
});

it('opens the app menu from the logo: Back to files where the host has a home, the person\'s settings and the host\'s links; its ⋯ offers what the host can do with the file', async () => {
  const user = userEvent.setup();
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
  expect([...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent)).toEqual(['Back to files', 'Share anonymous usage data', 'Send feedback', 'GitHub', 'Discord']);
  expect(menu.querySelector('[data-menu-footer]')?.textContent).toContain('v0.7.4');
  // Send feedback: a new issue on the project's tracker, begun "Feedback: ", for the person to
  // finish, naming the version and the platform; no label: the project has none for feedback.
  const feedback = new URL(screen.getByRole('menuitem', { name: 'Send feedback' }).getAttribute('href')!);
  expect([`${feedback.origin}${feedback.pathname}`, feedback.searchParams.get('title'), feedback.searchParams.get('labels')])
    .toEqual(['https://github.com/earthtojake/text-to-cad/issues/new', 'Feedback: ', null]);
  expect(feedback.searchParams.get('body')).toMatch(/- CAD: 0\.7\.4\n- Platform: win32$/);
  // A setting turns without closing the menu; Back to files goes home.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Share anonymous usage data' }));
  expect([share.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[[false]], true]);
  await user.click(screen.getByRole('menuitem', { name: 'Back to files' }));
  expect(home).toHaveBeenCalledOnce();
  await user.click(screen.getByRole('button', { name: 'File actions' }));
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Copy path', 'Show in Explorer']);
  await user.click(screen.getByRole('menuitem', { name: 'Show in Explorer' }));
  expect(perform.reveal).toHaveBeenCalledWith({ path: FILE, kind: 'file' });
  cleanup();
  // A host with no home still has the menu, without Back to files; one that can only copy offers only that.
  open({ host: { ...host, links, fileActions: { perform: { 'copy-path': perform['copy-path'] } } } });
  await screen.findByText('shown');
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  expect(screen.queryByRole('menuitem', { name: 'Back to files' })).toBeNull();
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

it('has no Select File and no file menu on a document with no file of its own, which its name names', async () => {
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
  expect(failures.at(0)).toEqual({ message: 'File does not exist: /models/gone.step', missing: true, reload: expect.any(Function) });
  expect(failures.at(-1)).toEqual({ message: 'The disk is gone', missing: false, reload: expect.any(Function) });
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
