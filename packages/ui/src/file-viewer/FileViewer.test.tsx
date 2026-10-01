import { act, cleanup, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
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
  // The host's links, the same in every app: the version, whose menu holds GitHub and Discord,
  // each followed the host's way.
  const user = userEvent.setup();
  const followed: string[] = [];
  const linked = { ...host, links: viewerLinks({ version: 'v0.7.4', open: async (url: string) => { followed.push(url); } }) };
  open({ navigationPath: null, host: linked });
  await screen.findByText('shown');
  const version = screen.getByRole('button', { name: 'Version 0.7.4' });
  expect(version.textContent).toBe('v0.7.4');
  expect(screen.queryByRole('link', { name: 'GitHub' })).toBeNull();
  await user.click(version);
  const menu = await screen.findByRole('menu');
  expect(within(menu).getByRole('menuitem', { name: 'Discord' }).getAttribute('href')).toBe('https://discord.gg/5FGB9DwJYU');
  await user.click(within(menu).getByRole('menuitem', { name: 'GitHub' }));
  expect(followed).toEqual(['https://github.com/earthtojake/text-to-cad']);
  cleanup();
  open({ host: { ...linked, environment: { colorScheme: 'light', compact: true } } });
  await screen.findByText('shown');
  expect(navbar()).toBeNull();
});

it('says how its host updates: a command and a message for an agent, or a line where the update is not a command, each only when given', async () => {
  const user = userEvent.setup();
  const versionMenu = async (install?: object) => {
    open({ navigationPath: null, host: { ...host, links: viewerLinks({ version: '0.7.4', install }) } });
    await screen.findByText('shown');
    await user.click(screen.getByRole('button', { name: 'Version 0.7.4' }));
    return screen.findByRole('menu');
  };
  // The skills' update, by default: a command for a terminal, and the same for an agent.
  let menu = await versionMenu();
  expect(within(menu).getByText('npx skills add earthtojake/text-to-cad')).toBeTruthy();
  expect(within(menu).getByText('Or ask your agent')).toBeTruthy();
  expect(menu.querySelector('[data-install-message]')).toBeNull();
  cleanup();
  // A host whose update is not a command says how in a line, and nothing else.
  const message = 'Update CAD from the plugin marketplace, then restart the app.';
  menu = await versionMenu({ message });
  expect(menu.querySelector('[data-install-message]')?.textContent).toBe(message);
  expect(within(menu).queryByText('In your terminal')).toBeNull();
  expect(within(menu).queryByText('Or ask your agent')).toBeNull();
});

it('marks a newer release with a dot on the version, and says where the person stands: up to date, or the step to the new one', async () => {
  const user = userEvent.setup();
  const versionFor = async (latest: object | null) => {
    open({ navigationPath: null, host: { ...host, links: viewerLinks({ version: '0.7.4', latest }) } });
    await screen.findByText('shown');
    return screen.getByRole('button', { name: /^Version 0\.7\.4/ });
  };
  // A newer release: a dot on the version; open, the step to it, how to update, and what is new.
  const notes = 'https://github.com/earthtojake/text-to-cad/releases/tag/v0.7.5';
  let version = await versionFor({ version: '0.7.5', url: notes, newer: true });
  expect([version.getAttribute('aria-label'), version.hasAttribute('data-update')]).toEqual(['Version 0.7.4, update available', true]);
  await user.click(version);
  let menu = await screen.findByRole('menu');
  expect(menu.querySelector('[data-version-update]')?.textContent).toBe('Update availablev0.7.4 → v0.7.5');
  expect(within(menu).getByText('In your terminal')).toBeTruthy();
  expect(within(menu).getByRole('menuitem', { name: 'What’s new in v0.7.5' }).getAttribute('href')).toBe(notes);
  cleanup();
  // Up to date: no dot, and nothing to do.
  version = await versionFor({ version: '0.7.4', url: notes, newer: false });
  expect([version.getAttribute('aria-label'), version.hasAttribute('data-update')]).toEqual(['Version 0.7.4', false]);
  await user.click(version);
  menu = await screen.findByRole('menu');
  expect(within(menu).getByText('Up to date')).toBeTruthy();
  expect(within(menu).queryByText('In your terminal')).toBeNull();
  expect(within(menu).getByRole('menuitem', { name: 'Release notes' })).toBeTruthy();
});

it('steps the navbar aside while the renderer shows its file fullscreen', async () => {
  const fullscreen = defineFileRenderer({
    id: 'full', priority: 2, matches: () => true, prepare: async () => ({ data: null }),
    load: async () => ({ default: ({ onFullscreenChange }: any) => <>
      <button type="button" onClick={() => onFullscreenChange(true)}>Fullscreen</button>
      <button type="button" onClick={() => onFullscreenChange(false)}>Back</button>
    </> }),
  });
  render(<FileViewer file="parts/a.step" host={{ ...host, links: viewerLinks({ version: '0.7.4' }) } as any} renderers={[fullscreen]}
    state={{ panel: null, panelWidth: 220 }} onStateChange={() => {}} />);
  await screen.findByRole('button', { name: 'Fullscreen' });
  expect(navbar()).not.toBeNull();
  act(() => screen.getByRole('button', { name: 'Fullscreen' }).click());
  expect(navbar()).toBeNull();
  act(() => screen.getByRole('button', { name: 'Back' }).click());
  expect(navbar()).not.toBeNull();
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
