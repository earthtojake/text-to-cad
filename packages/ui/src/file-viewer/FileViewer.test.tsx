import { act, cleanup, render, screen, within } from '@testing-library/react';
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
  // The host's links, the same three in every app, followed the host's way.
  const followed: string[] = [];
  const linked = { ...host, links: viewerLinks({ version: 'v0.7.4', open: async (url: string) => { followed.push(url); } }) };
  open({ navigationPath: null, host: linked });
  await screen.findByText('shown');
  expect(screen.getByRole('button', { name: 'Version 0.7.4' })).toBeTruthy();
  act(() => screen.getByRole('link', { name: 'GitHub' }).click());
  act(() => screen.getByRole('link', { name: 'Discord' }).click());
  await act(async () => {});
  expect(followed).toEqual(['https://github.com/earthtojake/text-to-cad', 'https://discord.gg/5FGB9DwJYU']);
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
  const message = "Update CAD from Codex's plugin marketplace, then run $setup and restart Codex.";
  menu = await versionMenu({ message });
  expect(menu.querySelector('[data-install-message]')?.textContent).toBe(message);
  expect(within(menu).queryByText('In your terminal')).toBeNull();
  expect(within(menu).queryByText('Or ask your agent')).toBeNull();
});

it('leads home from a file where the host has a home, and is the brand on the home itself', async () => {
  const home = vi.fn();
  const homed = { ...host, links: viewerLinks({ version: '0.7.4' }), navigation: { openFile() {}, home } };
  open({ host: homed });
  await screen.findByText('shown');
  act(() => screen.getByRole('button', { name: 'Home' }).click());
  expect(home).toHaveBeenCalledOnce();
  cleanup();
  open({ host: homed, file: null, presentation: { home: <p>home</p> } });
  await screen.findByText('home');
  expect(screen.queryByRole('button', { name: 'Home' })).toBeNull();
  expect(screen.getByRole('img', { name: 'CAD' })).toBeTruthy();
});

it('opens a tab with no file on the host\'s home with the explorer shut, and on the explorer where there is no home', async () => {
  const browsing = { ...host, files: { ...host.files, list: async () => [] } };
  open({ host: browsing, file: null, presentation: { home: <p>home</p> } });
  expect(await screen.findByText('home')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Show files' })).toBeTruthy();
  expect(document.querySelector('[data-file-explorer]')).toBeNull();
  cleanup();
  // With nothing of its own there, the explorer is all there is to reach for.
  open({ host: browsing, file: null, presentation: { empty: <p>nothing open</p> } });
  expect(await screen.findByRole('button', { name: 'Hide files' })).toBeTruthy();
  expect(document.querySelector('[data-file-explorer]')).toBeTruthy();
});
