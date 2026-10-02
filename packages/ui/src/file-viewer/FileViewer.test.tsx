import { act, cleanup, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { createPortal } from 'react-dom';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { unavailablePromptContext } from '@text-to-cad/core/prompt';
import { FileViewer, defineFileRenderer } from '../../dist/file-viewer/index.js';
import { viewerLinks } from '../../dist/file-viewer/navigation/links.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const renderer = defineFileRenderer({
  id: 'plain', priority: 1, matches: () => true,
  load: async () => ({ default: () => <p>shown</p> }),
  prepare: async () => ({ data: null }),
});
// A host that shows one file and browses nothing: a source with no listing, as an agent host's file view has.
const host = {
  files: { id: 'one', rootName: 'one', stat: async (path: string) => ({ path, name: path, kind: 'file' as const, extension: 'step', size: 1 }) },
  clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
  promptContext: unavailablePromptContext, environment: { colorScheme: 'light' as const }, navigation: { openFile() {} },
};
const open = (props: { navigationPath?: string | null; host?: object; file?: string | null; presentation?: object }) =>
  render(<FileViewer file="parts/a.step" host={host as any} renderers={[renderer]} state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}} {...props as any} />);
const navbar = () => document.querySelector('[data-viewer-navbar]');
const labels = (selector = '[data-viewer-navbar]') => [...document.querySelectorAll(`${selector} a, ${selector} button`)].map(node => node.getAttribute('aria-label'));

it('draws the navbar only when it has something to hold, and never for a view shown small', async () => {
  open({ navigationPath: null });
  await screen.findByText('shown');
  expect(navbar()).toBeNull();
  cleanup();
  // The open file's name, with no ⋯ where the host can do nothing with it.
  open({});
  await screen.findByText('shown');
  expect(document.querySelector('[data-file-name]')?.textContent).toBe('a.step');
  expect(screen.queryByRole('button', { name: 'File actions' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Show files' })).toBeNull();
  cleanup();
  // The host's links: without an update, GitHub (the project is open source), then Feedback — a new
  // issue titled "Feedback: ", for the person to finish, naming the version and the platform (X,
  // Discord and the version are in Settings' footer). It carries no label: the project has none for feedback.
  const linked = { ...host, links: viewerLinks({ version: 'v0.7.4' }), environment: { colorScheme: 'light', platform: 'darwin' } };
  open({ navigationPath: null, host: linked });
  await screen.findByText('shown');
  expect(labels()).toEqual(['GitHub', 'Feedback']);
  const feedback = new URL(screen.getByRole('link', { name: 'Feedback' }).getAttribute('href')!);
  expect(`${feedback.origin}${feedback.pathname}`).toBe('https://github.com/earthtojake/text-to-cad/issues/new');
  expect(feedback.searchParams.get('title')).toBe('Feedback: ');
  expect(feedback.searchParams.has('labels')).toBe(false);
  expect(feedback.searchParams.get('body')).toMatch(/^\*\*What happened, or what would you like\?\*\*\n[\s\S]*- CAD: 0\.7\.4\n- Platform: darwin$/);
  cleanup();
  // A host with no tracker: no Feedback; GitHub stays.
  open({ navigationPath: null, host: { ...linked, links: viewerLinks({ version: '0.7.4', issues: '' }) } });
  await screen.findByText('shown');
  expect(navbar()).not.toBeNull();
  expect(labels()).toEqual(['GitHub']);
  cleanup();
  open({ host: { ...linked, environment: { colorScheme: 'light', compact: true } } });
  await screen.findByText('shown');
  expect(navbar()).toBeNull();
});

it('an update is a blue download button whose menu says the step to it, how this host updates and what is new; nothing without one', async () => {
  const user = userEvent.setup();
  const notes = 'https://github.com/earthtojake/text-to-cad/releases/tag/v0.7.5';
  const followed: string[] = [];
  const updateMenu = async (latest: object | null, install?: object) => {
    open({ navigationPath: null, host: { ...host, links: viewerLinks({ version: '0.7.4', latest, install, open: async (url: string) => { followed.push(url); } }) } });
    await screen.findByText('shown');
    const button = screen.queryByRole('button', { name: 'Update to 0.7.5' });
    if (!button) return null;
    await user.click(button);
    return screen.findByRole('menu');
  };
  // Up to date, or never checked: nothing.
  expect(await updateMenu({ version: '0.7.4', url: notes, newer: false })).toBeNull();
  cleanup();
  expect(await updateMenu(null)).toBeNull();
  cleanup();
  // A newer release: the step to it, the skills' update by default, and what is new, followed the host's way.
  let menu = (await updateMenu({ version: '0.7.5', url: notes, newer: true }))!;
  expect(menu.querySelector('[data-version-update]')?.textContent).toBe('Update availablev0.7.4 → v0.7.5');
  expect(within(menu).getByText('npx skills add earthtojake/text-to-cad')).toBeTruthy();
  expect(within(menu).getByText('Or ask your agent')).toBeTruthy();
  await user.click(within(menu).getByRole('menuitem', { name: 'What’s new in v0.7.5' }));
  expect(followed).toEqual([notes]);
  cleanup();
  // A host whose update is not a command says how in a line, and nothing else.
  const message = 'Update CAD from the plugin marketplace, then restart the app.';
  menu = (await updateMenu({ version: '0.7.5', url: notes, newer: true }, { message }))!;
  expect(menu.querySelector('[data-install-message]')?.textContent).toBe(message);
  expect(within(menu).queryByText('In your terminal')).toBeNull();
});

it('puts Feedback just before the view\'s controls, outside them, and steps the navbar aside while the renderer shows its file fullscreen', async () => {
  // A renderer with the CAD viewer's controls in the navbar, whose Preview is fullscreen.
  const fullscreen = defineFileRenderer({
    id: 'full', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: ({ onFullscreenChange, navbarSlot }: any) => <>
      {navbarSlot ? createPortal(<><button type="button" aria-label="Settings" />
        <button type="button" aria-label="Preview" onClick={() => onFullscreenChange(true)} /></>, navbarSlot) : null}
      <button type="button" onClick={() => onFullscreenChange(false)}>Back</button>
    </> }),
  });
  render(<FileViewer file="parts/a.step" host={{ ...host, links: viewerLinks({ version: '0.7.4' }) } as any} renderers={[fullscreen]}
    state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}} />);
  await screen.findByRole('button', { name: 'Preview' });
  expect(labels()).toEqual(['GitHub', 'Feedback', 'Settings', 'Preview']);
  expect(labels('[data-navbar-controls]')).toEqual(['Settings', 'Preview']);
  act(() => screen.getByRole('button', { name: 'Preview' }).click());
  expect(navbar()).toBeNull();
  expect(screen.queryByRole('link', { name: 'Feedback' })).toBeNull();
  act(() => screen.getByRole('button', { name: 'Back' }).click());
  expect(labels()).toEqual(['GitHub', 'Feedback', 'Settings', 'Preview']);
});

it('leads back to the host\'s home from a file, and draws no navbar over the home itself', async () => {
  const home = vi.fn();
  const homed = { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home } };
  open({ host: homed });
  await screen.findByText('shown');
  act(() => screen.getByRole('button', { name: 'Back' }).click());
  expect(home).toHaveBeenCalledOnce();
  cleanup();
  open({ host: homed, file: null, presentation: { home: <p>home</p> } });
  await screen.findByText('home');
  expect(navbar()).toBeNull();
  cleanup();
  // No home, no way back to one.
  open({ host: { ...host, links: viewerLinks({ version: '0.7.4' }) } });
  await screen.findByText('shown');
  expect(screen.queryByRole('button', { name: 'Back' })).toBeNull();
});

it('with no file open and no home, the navbar asks for one, and the explorer opens only when asked', async () => {
  const browsing = { ...host, links: viewerLinks({ version: '0.7.4' }), files: { ...host.files, list: async () => [] } };
  // The tab's state is the host's: here, kept as a host keeps it.
  function Tab() {
    const [state, setState] = useState<{ panel: string | null; panelWidth: number }>({ panel: null, panelWidth: 220 });
    return <FileViewer file={null} host={browsing as any} renderers={[renderer]} state={state as any} onStateChange={setState as any}
      presentation={{ empty: <p>nothing open</p> }} />;
  }
  render(<Tab />);
  expect(await screen.findByText('nothing open')).toBeTruthy();
  expect(document.querySelector('[data-file-explorer]')).toBeNull();
  // Words in the name's place, not a control: the toggle beside them opens the explorer.
  expect(screen.getByText('Select file').closest('button')).toBeNull();
  act(() => screen.getByRole('button', { name: 'Show files' }).click());
  expect(document.querySelector('[data-file-explorer]')).toBeTruthy();
  cleanup();
  // With no files to browse there is nothing to select: the navbar holds only the links.
  open({ host: { ...host, links: viewerLinks({ version: '0.7.4' }) }, file: null, presentation: { empty: <p>nothing open</p> } });
  expect(await screen.findByText('nothing open')).toBeTruthy();
  expect(navbar()).not.toBeNull();
  expect(screen.queryByText('Select file')).toBeNull();
});
