import { act, cleanup, render, screen } from '@testing-library/react';
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
  clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, navigation: { openFile(_path: string) {} },
};
const open = (props: { host?: object; file?: string | null; presentation?: object }) =>
  render(<FileViewer file={FILE} host={host as any} renderers={[renderer]} state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}} {...props as any} />);
const navbar = () => document.querySelector('[data-viewer-navbar]');
const fileName = () => document.querySelector<HTMLElement>('[data-file-name]')!;
const labels = (selector = '[data-viewer-navbar]') => [...document.querySelectorAll(`${selector} a, ${selector} button`)].map(node => node.getAttribute('aria-label'));

it('draws the navbar over every file, named by its name, and never over the home or a view shown small', async () => {
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
  // The home is the host's own page, which holds its links itself.
  open({ host: { ...host, navigation: { openFile() {}, home() {} } }, file: null, presentation: { home: <p>home</p> } });
  await screen.findByText('home');
  expect(navbar()).toBeNull();
});

it('keeps the right of the navbar for the host\'s update button and Full size alone, and steps the navbar aside while the renderer shows its file fullscreen', async () => {
  // A renderer that shows its file fullscreen (the CAD viewer's Preview, a control of its own view).
  const fullscreen = defineFileRenderer({
    id: 'full', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: ({ onFullscreenChange }: any) => <>
      <button type="button" onClick={() => onFullscreenChange(true)}>Preview</button>
      <button type="button" onClick={() => onFullscreenChange(false)}>Back</button>
    </> }),
  });
  render(<FileViewer file={FILE} host={host as any} renderers={[fullscreen]} state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}}
    update={<button type="button" aria-label="Update to 0.7.5" />} fullSize={<button type="button" aria-label="Full size" />} />);
  await screen.findByRole('button', { name: 'Preview' });
  expect(labels()).toEqual(['Update to 0.7.5', 'Full size']);
  act(() => screen.getByRole('button', { name: 'Preview' }).click());
  expect(navbar()).toBeNull();
  act(() => screen.getByRole('button', { name: 'Back' }).click());
  expect(labels()).toEqual(['Update to 0.7.5', 'Full size']);
});

it('opens the app menu from the logo: Back to files where the host has a home, the person\'s settings and the host\'s links; its ⋯ offers what the host can do with the file', async () => {
  const user = userEvent.setup();
  const home = vi.fn();
  const quickEdit = vi.fn();
  const perform = { 'copy-path': vi.fn(), reveal: vi.fn() };
  const links = viewerLinks({ version: '0.7.4', github: 'https://github.com/earthtojake/text-to-cad', discord: 'https://discord.gg/x' });
  open({ host: { ...host, links, environment: { colorScheme: 'light', platform: 'win32' }, navigation: { openFile() {}, home }, fileActions: { platform: 'win32', perform } },
    appSettings: [{ id: 'quick-edit', label: 'Quick edit', checked: true, onCheckedChange: quickEdit }] } as any);
  await screen.findByText('shown');
  expect(labels()).toEqual(['Menu', 'File actions']);
  await user.click(screen.getByRole('button', { name: 'Menu' }));
  const menu = document.querySelector('[data-app-menu]')!;
  expect([...menu.querySelectorAll('[role^="menuitem"]')].map(item => item.textContent)).toEqual(['Back to files', 'Quick edit', 'Send feedback', 'GitHub', 'Discord']);
  expect(menu.querySelector('[data-menu-footer]')?.textContent).toContain('v0.7.4');
  // Send feedback: a new issue on the project's tracker, begun "Feedback: ", for the person to
  // finish, naming the version and the platform; no label: the project has none for feedback.
  const feedback = new URL(screen.getByRole('menuitem', { name: 'Send feedback' }).getAttribute('href')!);
  expect([`${feedback.origin}${feedback.pathname}`, feedback.searchParams.get('title'), feedback.searchParams.get('labels')])
    .toEqual(['https://github.com/earthtojake/text-to-cad/issues/new', 'Feedback: ', null]);
  expect(feedback.searchParams.get('body')).toMatch(/- CAD: 0\.7\.4\n- Platform: win32$/);
  // A setting turns without closing the menu; Back to files goes home.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Quick edit' }));
  expect([quickEdit.mock.calls, Boolean(document.querySelector('[data-app-menu]'))]).toEqual([[[false]], true]);
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
  expect(failures.at(0)).toEqual({ message: 'File does not exist: /models/gone.step', missing: true });
  expect(failures.at(-1)).toEqual({ message: 'The disk is gone', missing: false });
  cleanup();
  // A host with no page of its own for it gets the viewer's.
  open({ host: failing(new Error('The disk is gone')) });
  expect(await screen.findByText('Could not open that file')).toBeTruthy();
});
