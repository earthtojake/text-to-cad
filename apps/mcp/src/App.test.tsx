import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { CadViewerProps } from '@text-to-cad/ui/cad-viewer';
import type { UpdateNotice } from '@text-to-cad/ui/update';
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
    // The host's notice (the analytics card) drawn as the real viewer would once a model is on screen.
    CadViewer: (props: CadViewerProps) => { viewer.props = props; useEffect(() => { viewer.mounts += 1; }, []); return props.notice ?? null; },
  };
});

beforeEach(() => vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; viewer.mounts = 0; });

/** A host frame and CAD's server, as the page reaches them. */
function host(initial: HostContext, hostCapabilities: Record<string, unknown> = {}, ask = false, notice: UpdateNotice | null = null) {
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
    consent: vi.fn(async (share?: boolean) => ({ ask: share === undefined && ask, sharing: Boolean(share), policy: 'https://www.texttocad.dev/privacy-policy' })),
    // The person's features as the server keeps them (`cad_features`).
    features: vi.fn(async (change?: object) => { kept = { ...kept, ...change }; return kept; }),
    version: vi.fn(async (dismiss?: string) => ({ notice: dismiss === undefined ? notice : null })),
  };
  let kept = { quickEdit: true };
  return { bridge, server };
}
const session: Session = { protocol: 3, build: 'b', version: 'test', platform: 'darwin', workspace: [] };
// The sidebar's home, as the server launches it: the library, over a filesystem it does not browse.
const home: Launch = { protocol: 3, page: 'home', model: null, root: { kind: 'global', path: '/', name: '/' }, explore: false };
const sized = (notify: ReturnType<typeof vi.fn>) => notify.mock.calls.filter(([method]) => method === 'ui/notifications/size-changed');

it('a tab host gets the page it always had, down to its bottom: the home, with no explorer, no card to size and no full-size button', () => {
  const { bridge, server } = host({ displayMode: 'fullscreen', safeAreaInsets: { top: 4, bottom: 72 } });
  const { container } = render(<App bridge={bridge as any} server={server as any} launch={{ ...home, surface: 'sidebar' }} session={session} />);
  // The home is the viewer with nothing open: its library, with this host's Open, and no files to browse.
  expect(viewer.props!.file).toBe('');
  expect(typeof viewer.props!.library!.pick).toBe('function');
  expect(viewer.props!.host.files.list).toBeUndefined();
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  expect(sized(bridge.notify)).toEqual([]);
  // The host's composer floats over the page's bottom: no strip is kept for it, preview's playbar
  // sits on the composer's line, and lists scroll clear of it.
  const frame = container.firstElementChild as HTMLElement;
  expect([frame.style.paddingTop, frame.style.paddingBottom]).toEqual(['4px', '0px']);
  expect(frame.style.getPropertyValue('--cad-viewport-bottom-center')).toBe('40px');
  expect(frame.style.getPropertyValue('--cad-host-bottom-inset')).toBe('72px');
});

it('a model opened from the home is launched by the server and leads back to it; the navbar\'s links and file menu go through the host', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  await act(async () => viewer.props!.library!.open({ path: '/work/parts/a.step', name: 'a.step', folder: 'work/parts', pinned: false, thumbnail: null, openedAt: 1 } as any));
  expect(server.launch).toHaveBeenCalledWith('/work/parts/a.step');
  expect(viewer.props!.file).toBe('work/parts/a.step');
  // Back: the home the view opened on.
  act(() => viewer.props!.onShow(''));
  expect(viewer.props!.file).toBe('');
  await act(async () => viewer.props!.host.links!.open!('https://github.com/earthtojake/text-to-cad'));
  expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: 'https://github.com/earthtojake/text-to-cad' });
  // Feedback and Report Issue open a new issue on the project's tracker, the same way.
  expect(viewer.props!.host.links!.issues).toBe('https://github.com/earthtojake/text-to-cad/issues/new');
  const { perform, platform } = viewer.props!.host.fileActions!;
  // A file on its own, in no project: its path is its only one.
  expect([platform, Object.keys(perform!).sort()]).toEqual(['darwin', ['copy-path', 'reveal']]);
  await act(async () => perform!.reveal!({ path: 'work/parts/a.step', kind: 'file' }));
  expect(server.reveal).toHaveBeenCalledWith(expect.objectContaining({ kind: 'global', path: '/' }), 'work/parts/a.step');
});

it('a thread\'s tab has no home: no library, and nothing to go back to, but its project to browse', () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} session={session}
    launch={{ protocol: 3, page: 'viewer', model: null, root: { kind: 'workspace', path: '/work', name: 'work' }, explore: true, surface: 'tab' }} />);
  expect(viewer.props!.library).toBeUndefined();
  expect(viewer.props!.host.files.list).toBeDefined();
});

it('an inline host gets a card of a height it is told, which goes full size in place', () => {
  const { bridge, server } = host({ displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'] });
  const { container } = render(<App bridge={bridge as any} server={server as any} presentation="inline" session={session}
    launch={{ ...home, surface: 'inline', explore: false, view: 'cad-1-a', order: { createdAt: 1, seq: 1 } }} />);
  expect(viewer.props!.host.environment.compact).toBe(true);
  expect(sized(bridge.notify)).toEqual([['ui/notifications/size-changed', { height: expect.any(Number) }]]);
  // Its Full size button holds the top-right corner: the viewer's column there (the analytics card) starts below it.
  expect((container.firstElementChild as HTMLElement).style.getPropertyValue('--cad-viewport-top-right-inset')).toBe('40px');
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
  const model: Launch = { protocol: 3, page: 'viewer', model: '/work/part.stl', root: { kind: 'global', path: '/', name: '/' }, explore: false };
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

it('a hand-made install is asked once about analytics: nothing is shared before a yes, and either answer ends the question', async () => {
  for (const choice of ['Allow', 'No thanks', 'Close']) {
    const { bridge, server } = host({ displayMode: 'fullscreen' }, {}, true);
    const { findByRole, queryByRole, getByText, getByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
    // The card is the viewer's notice: asked once a model is on screen, top-right, Quick Edit under it.
    await findByRole('dialog', { name: 'Allow Analytics' });
    expect(viewer.props!.notice).toBeTruthy();
    const policy = getByText('Privacy Policy') as HTMLAnchorElement;
    expect([policy.href, policy.target]).toEqual(['https://www.texttocad.dev/privacy-policy', '_blank']);
    await act(async () => policy.click());
    expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: 'https://www.texttocad.dev/privacy-policy' });
    expect(server.consent).toHaveBeenCalledTimes(1);
    await act(async () => (choice === 'Close' ? getByRole('button', { name: "Close and don't share" }) : getByText(choice)).click());
    expect(server.consent).toHaveBeenLastCalledWith(choice === 'Allow', 'card');
    expect(queryByRole('dialog', { name: 'Allow Analytics' })).toBeNull();
    cleanup();
  }
  // The answer is Settings' Analytics toggle from then on, and the toggle changes it.
  {
    const { bridge, server } = host({ displayMode: 'fullscreen' }, {}, true);
    const { findByRole, getByText } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
    await findByRole('dialog', { name: 'Allow Analytics' });
    expect(viewer.props!.appSettings).toEqual([expect.objectContaining({ id: 'analytics', checked: false }),
      expect.objectContaining({ id: 'quickEdit', section: 'Features', checked: true })]);
    await act(async () => getByText('Allow').click());
    expect(viewer.props!.appSettings![0].checked).toBe(true);
    await act(async () => viewer.props!.appSettings![0].onCheckedChange(false));
    expect(server.consent).toHaveBeenLastCalledWith(false, 'settings');
    expect(viewer.props!.appSettings![0].checked).toBe(false);
    cleanup();
  }
  // A person who already answered (or whose environment did) is never asked.
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  const { queryByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  await act(async () => {});
  expect(server.consent).toHaveBeenCalledTimes(1);
  expect(queryByRole('dialog', { name: 'Allow Analytics' })).toBeNull();
});

it('an answer is never undone by a read sent just before it, and a choice the environment made is shown fixed', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' }, {}, true);
  const policy = 'https://www.texttocad.dev/privacy-policy';
  let releaseStaleRead: (value: unknown) => void = () => {};
  const { findByRole, getByText, queryByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  await findByRole('dialog', { name: 'Allow Analytics' });
  // The click's own focus sends a read that answers late, with the question still open.
  server.consent.mockImplementationOnce(() => new Promise(resolve => { releaseStaleRead = resolve; }));
  act(() => { window.dispatchEvent(new Event('focus')); });
  await act(async () => getByText('Allow').click());
  await act(async () => releaseStaleRead({ ask: true, sharing: false, policy }));
  expect(queryByRole('dialog', { name: 'Allow Analytics' })).toBeNull();
  expect(viewer.props!.appSettings![0].checked).toBe(true);
  cleanup();
  // DO_NOT_TRACK: the setting says so, and cannot be changed here.
  const fixed = host({ displayMode: 'fullscreen' });
  fixed.server.consent.mockImplementation(async () => ({ ask: false, sharing: false, reason: 'environment', policy }));
  render(<App bridge={fixed.bridge as any} server={fixed.server as any} launch={home} session={session} />);
  await act(async () => {});
  expect(viewer.props!.appSettings![0]).toEqual(expect.objectContaining({ disabled: true, label: 'Share anonymous usage data (set by your environment)' }));
});

it("Settings' Features: Quick edit is read from the server, turned off there for every view, and handed to the viewer", async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  await act(async () => {});
  expect(server.features.mock.calls).toEqual([[undefined]]);
  expect(viewer.props!.features).toEqual({ quickEdit: true });
  // Settings: Analytics, then Features.
  expect(viewer.props!.appSettings!.map(setting => [setting.section, setting.label, setting.checked]))
    .toEqual([['Analytics', 'Share anonymous usage data', false], ['Features', 'Quick edit', true]]);
  await act(async () => viewer.props!.appSettings!.find(setting => setting.id === 'quickEdit')!.onCheckedChange(false));
  expect(server.features).toHaveBeenLastCalledWith({ quickEdit: false });
  expect(viewer.props!.features).toEqual({ quickEdit: false });
  cleanup();
  // Another view of the person's opens with it off: the server kept it.
  const again = host({ displayMode: 'fullscreen' });
  again.server.features.mockImplementation(async () => ({ quickEdit: false }));
  render(<App bridge={again.bridge as any} server={again.server as any} launch={home} session={session} />);
  await act(async () => {});
  expect(viewer.props!.features).toEqual({ quickEdit: false });
});

it('a newer release is offered once the analytics question is answered: sent to the chat where the host takes messages, copied elsewhere', async () => {
  const notice = { latest: '0.9.0', version: '0.8.1', text: 'text-to-cad 0.9.0 is available (you have 0.8.1)',
    prompt: 'Update text-to-cad to 0.9.0 (installed from GitHub).' };
  {
    const { bridge, server } = host({ displayMode: 'fullscreen' }, { message: {} }, true, notice);
    const { findByRole, getByText, getByRole, queryByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
    await findByRole('dialog', { name: 'Allow Analytics' });
    expect(queryByRole('dialog', { name: 'Update available' })).toBeNull();
    await act(async () => getByText('No thanks').click());
    await act(async () => getByRole('button', { name: 'Send to agent' }).click());
    expect(bridge.request).toHaveBeenCalledWith('ui/message', { role: 'user', content: [{ type: 'text', text: notice.prompt }] }, { timeoutMs: 30_000 });
    expect(server.version).toHaveBeenLastCalledWith('0.9.0');
    expect(queryByRole('dialog', { name: 'Update available' })).toBeNull();
    cleanup();
  }
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  const { bridge, server } = host({ displayMode: 'fullscreen' }, {}, false, notice);
  const { findByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} session={session} />);
  const copy = await findByRole('button', { name: 'Copy prompt' });
  await act(async () => copy.click());
  expect(writeText).toHaveBeenCalledWith(notice.prompt);
  expect(server.version).toHaveBeenLastCalledWith('0.9.0');
  expect(bridge.request).not.toHaveBeenCalledWith('ui/message', expect.anything(), expect.anything());
});
