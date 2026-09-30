import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { CadViewerProps } from '@text-to-cad/ui/cad-viewer';
import App from './App';
import type { HostContext } from './host/bridge';
import type { Launch, Session } from './host/server';

// The shared CAD viewer, reduced to what this page hands it: what it draws for each prompt
// destination and each page is its own suite's (packages/ui); what this page hands it is this one's.
const viewer = vi.hoisted(() => ({ props: null as CadViewerProps | null, mounts: 0 }));
vi.mock('@text-to-cad/ui/cad-viewer', async original => {
  const { useEffect } = await import('react');
  return {
    ...await original<object>(),
    CadViewer: (props: CadViewerProps) => { viewer.props = props; useEffect(() => { viewer.mounts += 1; }, []); return null; },
  };
});

beforeEach(() => vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; viewer.mounts = 0; });

/** A host frame and CAD's server, as the page reaches them. */
function host(initial: HostContext, hostCapabilities: Record<string, unknown> = {}) {
  const listeners = new Set<(context: HostContext) => void>();
  let context = initial;
  const bridge = {
    get hostContext() { return context; }, hostCapabilities,
    notify: vi.fn(), request: vi.fn(async () => ({})), callTool: vi.fn(),
    onToolResult: () => () => {}, onTeardown: () => () => {},
    onHostContext(listener: (next: HostContext) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    change(next: HostContext) { context = { ...context, ...next }; for (const listener of [...listeners]) listener(context); },
  };
  const server = {
    events: () => new Promise(() => {}), report: vi.fn(async () => ({})), reply: vi.fn(async () => ({})),
    recents: vi.fn(async () => []), thumbnails: vi.fn(async () => ({})), http: () => new Promise(() => {}),
    launch: vi.fn(async (model: string) => ({ ...home, page: 'viewer', model })), pickModel: vi.fn(async () => ({ cancelled: true })),
    reveal: vi.fn(async () => {}),
  };
  return { bridge, server };
}
const session: Session = { protocol: 2, build: 'b', version: 'test', platform: 'darwin', workspace: [] };
const home: Launch = { protocol: 2, page: 'home', model: null, root: { kind: 'workspace', path: '/work', name: 'work' }, explore: true };
const sized = (notify: ReturnType<typeof vi.fn>) => notify.mock.calls.filter(([method]) => method === 'ui/notifications/size-changed');

it('a tab host gets the page it always had, down to its bottom: the home, with its explorer, no card to size and no full-size button', () => {
  const { bridge, server } = host({ displayMode: 'fullscreen', safeAreaInsets: { top: 4, bottom: 72 } });
  const { container } = render(<App bridge={bridge as any} server={server as any} launch={{ ...home, surface: 'sidebar' }} session={session} />);
  // The home is the viewer with nothing open: its library, with this host's Open Model, and the root's files.
  expect(viewer.props!.file).toBe('');
  expect(typeof viewer.props!.library.pick).toBe('function');
  expect(viewer.props!.host.files.list).toBeDefined();
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  expect(sized(bridge.notify)).toEqual([]);
  // The host's composer floats over the page's bottom: no strip is kept for it, preview's playbar
  // sits on the composer's line, and lists scroll clear of it.
  const frame = container.firstElementChild as HTMLElement;
  expect([frame.style.paddingTop, frame.style.paddingBottom]).toEqual(['4px', '0px']);
  expect(frame.style.getPropertyValue('--cad-viewport-bottom-center')).toBe('40px');
  expect(frame.style.getPropertyValue('--cad-host-bottom-inset')).toBe('72px');
});

it('a file picked on the home is launched by the server; the navbar\'s links and file menu go through the host', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  await act(async () => viewer.props!.onShow('parts/a.step'));
  expect(server.launch).toHaveBeenCalledWith('/work/parts/a.step');
  expect(viewer.props!.file).toBe('parts/a.step');
  // Home again: the launch the view opened on.
  act(() => viewer.props!.onShow(''));
  expect(viewer.props!.file).toBe('');
  await act(async () => viewer.props!.host.links!.open!('https://github.com/earthtojake/text-to-cad'));
  expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: 'https://github.com/earthtojake/text-to-cad' });
  const { perform, platform } = viewer.props!.host.fileActions!;
  expect([platform, Object.keys(perform!).sort()]).toEqual(['darwin', ['copy-path', 'copy-relative-path', 'reveal']]);
  await act(async () => perform!.reveal!({ path: 'parts/a.step', kind: 'file' }));
  expect(server.reveal).toHaveBeenCalledWith(expect.objectContaining({ kind: 'workspace', path: '/work' }), 'parts/a.step');
});

it('an inline host gets a card of a height it is told, which goes full size in place', () => {
  const { bridge, server } = host({ displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'] });
  const { container } = render(<App bridge={bridge as any} server={server as any} presentation="inline" session={session}
    launch={{ ...home, surface: 'inline', explore: false, view: 'cad-1-a', order: { createdAt: 1, seq: 1 } }} />);
  expect(viewer.props!.host.environment.compact).toBe(true);
  expect(sized(bridge.notify)).toEqual([['ui/notifications/size-changed', { height: expect.any(Number) }]]);
  act(() => (container.querySelector('[aria-label="Full size"]') as HTMLButtonElement).click());
  expect(bridge.request).toHaveBeenCalledWith('ui/request-display-mode', { mode: 'fullscreen' });
  act(() => bridge.change({ displayMode: 'fullscreen', safeAreaInsets: { bottom: 72 } }));
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  expect(viewer.props!.host.environment.compact).toBeUndefined();
  // Full size, the host's composer lies across the bottom: the view keeps clear of it, and its
  // playbar keeps its own line.
  expect((container.firstElementChild as HTMLElement).style.paddingBottom).toBe('72px');
  expect((container.firstElementChild as HTMLElement).style.getPropertyValue('--cad-viewport-bottom-center')).toBe('');
  // Full size keeps what was on the card: the same view, not a new one.
  expect(viewer.mounts).toBe(1);
});

it('a Quick Edit queues into a tab host\'s composer always, into an inline host\'s when it takes model context, and sends where the host takes messages', () => {
  const model: Launch = { protocol: 2, page: 'viewer', model: '/work/part.stl', root: { kind: 'global', path: '/', name: '/' }, explore: false };
  const reach = (presentation: 'tabs' | 'inline', capabilities: Record<string, unknown>) => {
    const { bridge, server } = host({ displayMode: presentation === 'tabs' ? 'fullscreen' : 'inline' }, capabilities);
    render(<App bridge={bridge as any} server={server as any} presentation={presentation} session={session} launch={model} />);
    const { promptContext, attachments } = viewer.props!.host;
    const reached = [promptContext.getSnapshot().kind, typeof promptContext.send === 'function' ? 'send' : '', Boolean(attachments)];
    cleanup();
    return reached;
  };
  // An inline host that declared neither has nowhere to add to or post in: Copy Prompt alone.
  expect(reach('inline', {})).toEqual(['unavailable', '', true]);
  expect(reach('inline', { updateModelContext: { text: {} } })).toEqual(['composer', '', true]);
  expect(reach('inline', { message: { text: {} } })).toEqual(['unavailable', 'send', true]);
  // Codex declares model context only sometimes and always forwards it: a tab is never asked.
  expect(reach('tabs', { message: { text: {}, image: {} } })).toEqual(['composer', 'send', true]);
});
