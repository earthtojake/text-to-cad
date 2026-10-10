import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { CadViewerProps } from '@text-to-cad/ui/cad-viewer';
import App from './App';
import type { HostContext } from './host/bridge';
import type { Launch } from './host/server';

// The shared CAD viewer, reduced to what this page hands it: what it draws for each prompt
// destination and each page is its own suite's (packages/ui); what this page hands it is this one's.
const viewer = vi.hoisted(() => ({ props: null as CadViewerProps | null, mounts: 0 }));
vi.mock('@text-to-cad/ui/cad-viewer', async original => {
  const { useEffect } = await import('react');
  return {
    ...await original<object>(),
    // The host's notice, if it had one, drawn as the real viewer would once a model is on screen.
    CadViewer: (props: CadViewerProps) => { viewer.props = props; useEffect(() => { viewer.mounts += 1; }, []); return <>{props.update ?? null}{props.fullSize ?? null}{props.notice ?? null}</>; },
  };
});

beforeEach(() => vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; viewer.mounts = 0; });

const POLICY = 'https://www.texttocad.dev/privacy-policy';
type Answer = (body: any) => unknown;

/**
 * A host frame and CAD's server, as the page reaches them: its sync, and the viewer's routes over
 * `cad_http`, answered here as the viewer answers them (`answers`, by path; a route without one, as
 * what the viewer reads for itself, never answers). `asked(path)` is what the page sent each: its
 * JSON body, or null for a read.
 */
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
  let kept = { quickEdit: true };
  const answers: Record<string, Answer> = {
    '/__cad/analytics': body => ({ sharing: Boolean(body?.share), policy: POLICY }),
    // The person's features as the server keeps them.
    '/__cad/features': body => (kept = { ...kept, ...body }),
    '/__cad/version': () => ({ notice: null }),
    '/__cad/recents': () => ({ recents: [] }),
    '/__cad/reveal': () => null,
  };
  const requests: { path: string; body: any }[] = [];
  const server = {
    sync: () => new Promise(() => {}), reply: vi.fn(async () => ({})),
    http: vi.fn(async ({ url, body }: { url: string; body: string }) => {
      const path = new URL(url).pathname;
      const sent = body ? JSON.parse(atob(body)) : null;
      requests.push({ path, body: sent });
      if (!answers[path]) return new Promise(() => {});
      const value = await answers[path](sent);
      return value === null ? { status: 204, headers: {}, body: '' }
        : { status: 200, headers: { 'content-type': 'application/json' }, body: btoa(JSON.stringify(value)) };
    }),
    answers,
    asked: (path: string) => requests.filter(request => request.path === path).map(request => request.body),
  };
  return { bridge, server };
}
// The home, as the server launches it: the library, with Open on a computer that has a chooser.
const home: Launch = { protocol: 5, page: 'home', model: null, pick: true };
const sized = (notify: ReturnType<typeof vi.fn>) => notify.mock.calls.filter(([method]) => method === 'ui/notifications/size-changed');

it('a tab host gets the page it always had, down to its bottom: the home, with no card to size and no full-size button', () => {
  const { bridge, server } = host({ displayMode: 'fullscreen', safeAreaInsets: { top: 4, bottom: 72 } });
  const { container } = render(<App bridge={bridge as any} server={server as any} launch={{ ...home, surface: 'sidebar' }} />);
  // The home is the viewer with nothing open: its library, with this computer's Open.
  expect(viewer.props!.file).toBe('');
  expect(typeof viewer.props!.library!.pick).toBe('function');
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  expect(sized(bridge.notify)).toEqual([]);
  // The host's composer floats over the page's bottom: no strip is kept for it, preview's playbar
  // sits on the composer's line, and lists scroll clear of it.
  const frame = container.firstElementChild as HTMLElement;
  expect([frame.style.paddingTop, frame.style.paddingBottom]).toEqual(['4px', '0px']);
  expect(frame.style.getPropertyValue('--cad-viewport-bottom-center')).toBe('40px');
  expect(frame.style.getPropertyValue('--cad-host-bottom-inset')).toBe('72px');
});

it('a model opened from the home is shown in place, joins the library with its picture, and leads back home; the navbar\'s links and file menu go through the host', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={home} />);
  await act(async () => viewer.props!.library!.open({ path: '/work/parts/a.step', name: 'a.step', folder: 'work/parts', pinned: false, thumbnail: null, opened: 1 } as any));
  expect(viewer.props!.file).toBe('/work/parts/a.step');
  // On screen, it joins the library every CAD view shares, and its picture is kept there.
  await act(async () => viewer.props!.onShown!('/work/parts/a.step'));
  await act(async () => { await viewer.props!.onThumbnail!(new Blob([new Uint8Array([0x89, 0x50])], { type: 'image/png' }), '/work/parts/a.step'); });
  expect(server.asked('/__cad/recents')).toEqual([{ action: 'open', path: '/work/parts/a.step' },
    { action: 'thumbnail', path: '/work/parts/a.step', png: 'iVA=' }]);
  // Home again, from the navbar's logo.
  act(() => viewer.props!.onShow(''));
  expect(viewer.props!.file).toBe('');
  await act(async () => viewer.props!.host.links!.open!('https://github.com/earthtojake/text-to-cad'));
  expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: 'https://github.com/earthtojake/text-to-cad' });
  // Feedback and Report Issue open a new issue on the project's tracker, the same way.
  expect(viewer.props!.host.links!.issues).toBe('https://github.com/earthtojake/text-to-cad/issues/new');
  const { perform, platform } = viewer.props!.host.fileActions!;
  expect([platform, Object.keys(perform!).sort()]).toEqual(['darwin', ['copy-path', 'reveal']]);
  await act(async () => perform!.reveal!({ path: '/work/parts/a.step', kind: 'file' }));
  expect(server.asked('/__cad/reveal')).toEqual([{ path: '/work/parts/a.step' }]);
});

it('every view has the home and browses from its file\'s folder, but the host\'s file handler shows its file alone', () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'home', model: null, surface: 'tab', pick: false }} />);
  // A thread's empty tab is the home; a computer with no chooser has no Open.
  expect([viewer.props!.file, viewer.props!.library?.pick]).toEqual(['', undefined]);
  expect(viewer.props!.host.files.list).toBeDefined();
  cleanup();
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'viewer', model: '/work/a.step', surface: 'file' }} />);
  // No home, and a source that neither lists nor searches: no explorer either.
  expect([viewer.props!.file, viewer.props!.library]).toEqual(['/work/a.step', undefined]);
  expect([viewer.props!.host.files.list, viewer.props!.host.files.search]).toEqual([undefined, undefined]);
});

it("the host's file handler keeps the file it opened: a show sent to it changes nothing, and gives it no home", async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  const replies: ((reply: { events: unknown[] }) => void)[] = [];
  server.sync = vi.fn(() => new Promise(resolve => { replies.push(resolve); }));
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'viewer', model: '/work/a.step', surface: 'file' }} />);
  // A show's launch names no surface: it is not this view's to take.
  await act(async () => { replies.shift()!({ events: [{ seq: 1, type: 'show', launch: { protocol: 5, page: 'viewer', model: '/work/b.step' } }] }); });
  expect([viewer.props!.file, viewer.props!.library, viewer.props!.history, viewer.props!.host.files.list])
    .toEqual(['/work/a.step', undefined, undefined, undefined]);
});

it("a capture the agent asks with its show is of the model it showed, once that is loaded and drawn: never the one it left, never a refusal while it loads", async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  const replies: ((reply: { events: unknown[] }) => void)[] = [];
  server.sync = vi.fn(() => new Promise(resolve => { replies.push(resolve); }));
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'viewer', model: '/work/a.step' }} />);
  // A renderer's live controller for `path`, as the shared viewer binds it.
  const bound = (path: string, loading: boolean) => {
    const state = { loading, active: true, resource: { kind: 'workspace-file', path } };
    const unbind = viewer.props!.live!.binding.bind({ readState: () => state, capture: async () => new Blob([path]), thumbnail: async () => new Blob() } as any);
    return { loaded: () => { state.loading = false; }, unbind };
  };
  const a = bound('/work/a.step', false);
  await act(async () => { replies.shift()!({ events: [
    { seq: 1, type: 'show', launch: { protocol: 5, page: 'viewer', model: '/work/b.step' } },
    { seq: 2, type: 'capture', requestId: 'c1' },
  ] }); });
  expect(viewer.props!.file).toBe('/work/b.step');
  a.unbind();
  const b = bound('/work/b.step', true);
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 250)); });
  expect(server.reply).not.toHaveBeenCalled();
  b.loaded();
  await vi.waitFor(() => expect(server.reply).toHaveBeenCalledWith('c1', { png: btoa('/work/b.step') }));
});

it('an inline host gets the whole viewer in a card of a height it is told, with Full size in its navbar, which goes full size in place', () => {
  const { bridge, server } = host({ displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen'] });
  const { container } = render(<App bridge={bridge as any} server={server as any} presentation="inline"
    launch={{ ...home, surface: 'inline', view: 'cad-1-a', order: { createdAt: 1, seq: 1 } }} />);
  // Not a picture: the card has the navbar (and its update button), the tools, the cube and Quick Edit.
  expect(viewer.props!.host.environment.compact).toBeUndefined();
  expect(sized(bridge.notify)).toEqual([['ui/notifications/size-changed', { height: expect.any(Number) }]]);
  act(() => (container.querySelector('[aria-label="Full size"]') as HTMLButtonElement).click());
  expect(bridge.request).toHaveBeenCalledWith('ui/request-display-mode', { mode: 'fullscreen' });
  act(() => bridge.change({ displayMode: 'fullscreen', safeAreaInsets: { bottom: 72 } }));
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  // Full size, the host's composer lies across the bottom: the view keeps clear of it, and its
  // playbar keeps its own line.
  expect((container.firstElementChild as HTMLElement).style.paddingBottom).toBe('72px');
  expect((container.firstElementChild as HTMLElement).style.getPropertyValue('--cad-viewport-bottom-center')).toBe('');
  // Full size keeps what was on the card: the same view, not a new one.
  expect(viewer.mounts).toBe(1);
});

it("a view keeps its own history of files, as a browser's tab does: the agent's shows and the person's moves, Back and Forward over them, a move after a Back dropping what was ahead, the home no step", async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  // The agent's shows reach the view on its sync, one reply at a time.
  const replies: ((reply: { events: unknown[] }) => void)[] = [];
  server.sync = vi.fn(() => new Promise(resolve => { replies.push(resolve); }));
  const agentShows = (model: string, seq: number) => act(async () => {
    replies.shift()!({ events: [{ seq, type: 'show', launch: { protocol: 5, page: 'viewer', model } }] });
  });
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'viewer', model: '/work/a.step' }} />);
  const at = () => [viewer.props!.file, viewer.props!.history!.canGoBack, viewer.props!.history!.canGoForward];
  expect(at()).toEqual(['/work/a.step', false, false]);
  // The agent shows b, and the person opens c from the explorer: each a step.
  await agentShows('/work/b.step', 1);
  expect(at()).toEqual(['/work/b.step', true, false]);
  act(() => viewer.props!.onShow('/work/c.step'));
  expect(at()).toEqual(['/work/c.step', true, false]);
  act(() => viewer.props!.history!.back());
  expect(at()).toEqual(['/work/b.step', true, true]);
  act(() => viewer.props!.history!.back());
  expect(at()).toEqual(['/work/a.step', false, true]);
  act(() => viewer.props!.history!.forward());
  expect(at()).toEqual(['/work/b.step', true, true]);
  // The home is no step, a bigger way to pick a recent file: going there leaves the history where
  // it stands, and the file picked there follows the one the view left, dropping what was ahead (c).
  act(() => viewer.props!.onShow(''));
  expect(at()).toEqual(['', true, true]);
  act(() => viewer.props!.onShow('/work/d.step'));
  expect(at()).toEqual(['/work/d.step', true, false]);
  act(() => viewer.props!.history!.back());
  expect(at()).toEqual(['/work/b.step', true, true]);
  // Picking, on the home, the file the view left adds nothing; nor does a show of what is on screen.
  act(() => viewer.props!.onShow(''));
  act(() => viewer.props!.onShow('/work/b.step'));
  expect(at()).toEqual(['/work/b.step', true, true]);
  await agentShows('/work/b.step', 2);
  expect(at()).toEqual(['/work/b.step', true, true]);
  cleanup();
  // A view opened on the home: its first file is its first step, with nothing behind it.
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'home', model: null, surface: 'tab', pick: false }} />);
  act(() => viewer.props!.onShow('/work/a.step'));
  expect(at()).toEqual(['/work/a.step', false, false]);
  cleanup();
  // A file handler shows its file alone, with no home to go to: no Back or Forward.
  render(<App bridge={bridge as any} server={server as any} launch={{ protocol: 5, page: 'viewer', model: '/work/a.step', surface: 'file' }} />);
  expect(viewer.props!.history).toBeUndefined();
});

it('an inline host that cannot show a view full size gets no Full size, and still the whole viewer', () => {
  const { bridge, server } = host({ displayMode: 'inline', availableDisplayModes: ['inline'] });
  const { container } = render(<App bridge={bridge as any} server={server as any} presentation="inline"
    launch={{ protocol: 5, page: 'viewer', model: '/work/part.stl', surface: 'inline', view: 'cad-1-b', order: { createdAt: 1, seq: 1 } }} />);
  expect(container.querySelector('[aria-label="Full size"]')).toBeNull();
  expect(viewer.props!.fullSize).toBeNull();
  expect(viewer.props!.host.environment.compact).toBeUndefined();
});

it('a Quick Edit queues into a tab host\'s composer always, into an inline host\'s when it takes model context, and sends where the host takes messages', () => {
  const model: Launch = { protocol: 5, page: 'viewer', model: '/work/part.stl' };
  const reach = (presentation: 'tabs' | 'inline', capabilities: Record<string, unknown>) => {
    const { bridge, server } = host({ displayMode: presentation === 'tabs' ? 'fullscreen' : 'inline' }, capabilities);
    render(<App bridge={bridge as any} server={server as any} presentation={presentation} launch={model} />);
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

it('a Quick Edit that reached its destination is counted by the CAD app\'s server, told nothing of the edit', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' }, { message: { text: {} } });
  server.answers['/__cad/analytics/activity'] = () => null;
  render(<App bridge={bridge as any} server={server as any} presentation="tabs" launch={{ protocol: 5, page: 'viewer', model: '/work/part.stl' }} />);
  viewer.props!.host.usage.used('quickEdit');
  await vi.waitFor(() => expect(server.asked('/__cad/analytics/activity')).toEqual([{ quickEdit: true }]));
});

it('nothing asks about usage stats: the app menu shows the answer, and its toggle changes it', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  const { queryByRole } = render(<App bridge={bridge as any} server={server as any} launch={home} />);
  await act(async () => {});
  // cadgen's telemetry is on by default once a `cadgen` command has said so: the page never asks.
  expect(queryByRole('dialog')).toBeNull();
  expect(viewer.props!.notice).toBeFalsy();
  expect(server.asked('/__cad/analytics')).toEqual([null]);
  expect(viewer.props!.appSettings).toEqual([expect.objectContaining({ id: 'analytics', checked: false }),
    expect.objectContaining({ id: 'quickEdit', checked: true })]);
  await act(async () => viewer.props!.appSettings![0].onCheckedChange(true));
  expect(server.asked('/__cad/analytics').at(-1)).toEqual({ share: true });
  expect(viewer.props!.appSettings![0].checked).toBe(true);
  await act(async () => viewer.props!.appSettings![0].onCheckedChange(false));
  expect(server.asked('/__cad/analytics').at(-1)).toEqual({ share: false });
  expect(viewer.props!.appSettings![0].checked).toBe(false);
});

it('an answer is never undone by a read sent just before it, and a choice the environment made is shown fixed', async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  let releaseStaleRead: (value: unknown) => void = () => {};
  render(<App bridge={bridge as any} server={server as any} launch={home} />);
  await act(async () => {});
  // The click's own focus sends a read that answers late, with the answer from before it.
  const answer = server.answers['/__cad/analytics'];
  server.answers['/__cad/analytics'] = () => {
    server.answers['/__cad/analytics'] = answer;
    return new Promise(resolve => { releaseStaleRead = resolve; });
  };
  act(() => { window.dispatchEvent(new Event('focus')); });
  await act(async () => viewer.props!.appSettings![0].onCheckedChange(true));
  await act(async () => releaseStaleRead({ sharing: false, policy: POLICY }));
  expect(viewer.props!.appSettings![0].checked).toBe(true);
  cleanup();
  // DO_NOT_TRACK: the setting says so, and cannot be changed here.
  const fixed = host({ displayMode: 'fullscreen' });
  fixed.server.answers['/__cad/analytics'] = () => ({ sharing: false, reason: 'environment', policy: POLICY });
  render(<App bridge={fixed.bridge as any} server={fixed.server as any} launch={home} />);
  await act(async () => {});
  expect(viewer.props!.appSettings![0]).toEqual(expect.objectContaining({ disabled: true, label: 'Share usage stats (set by your environment)' }));
});

it("the app menu's features: Quick edit is read from the server, turned off there for every view, and handed to the viewer", async () => {
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  render(<App bridge={bridge as any} server={server as any} launch={home} />);
  await act(async () => {});
  expect(server.asked('/__cad/features')).toEqual([null]);
  expect(viewer.props!.features).toEqual({ quickEdit: true });
  // Settings: Analytics, then Features.
  expect(viewer.props!.appSettings!.map(setting => [setting.label, setting.checked]))
    .toEqual([['Share usage stats', false], ['Quick edit', true]]);
  await act(async () => viewer.props!.appSettings!.find(setting => setting.id === 'quickEdit')!.onCheckedChange(false));
  expect(server.asked('/__cad/features').at(-1)).toEqual({ quickEdit: false });
  expect(viewer.props!.features).toEqual({ quickEdit: false });
  cleanup();
  // Another view of the person's opens with it off: the server kept it.
  const again = host({ displayMode: 'fullscreen' });
  again.server.answers['/__cad/features'] = () => ({ quickEdit: false });
  render(<App bridge={again.bridge as any} server={again.server as any} launch={home} />);
  await act(async () => {});
  expect(viewer.props!.features).toEqual({ quickEdit: false });
});

it('a newer release is the blue update button: its card sends the prompt to the chat where the host takes messages, copies it elsewhere, the full instructions a link away', async () => {
  const notice = { latest: '0.9.0', version: '0.8.1', text: 'A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)',
    prompt: 'Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad', instructions: 'https://www.texttocad.dev/install' };
  {
    // The launch carries the notice as the server last read it: the button draws with the page.
    const { bridge, server } = host({ displayMode: 'fullscreen' }, { message: {} });
    const { findByRole, getByRole, queryByRole } = render(<App bridge={bridge as any} server={server as any} launch={{ ...home, notice }} />);
    const update = await findByRole('button', { name: 'Update to 0.9.0' });
    await act(async () => update.click());
    await findByRole('dialog', { name: 'Update available' });
    await act(async () => getByRole('link', { name: 'Manual installation' }).click());
    expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: notice.instructions });
    await act(async () => getByRole('button', { name: 'Send to agent' }).click());
    expect(bridge.request).toHaveBeenCalledWith('ui/message', { role: 'user', content: [{ type: 'text', text: notice.prompt }] }, { timeoutMs: 30_000 });
    expect(queryByRole('dialog', { name: 'Update available' })).toBeNull();
    expect(getByRole('button', { name: 'Update to 0.9.0' })).toBeTruthy();
    expect(server.asked('/__cad/version')).toEqual([]); // nothing to read, and nothing kept
    cleanup();
  }
  const writeText = vi.fn(async () => {});
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  const { bridge, server } = host({ displayMode: 'fullscreen' });
  const { findByRole } = render(<App bridge={bridge as any} server={server as any} launch={{ ...home, notice }} />);
  // Looked up outside act: act holds React's updates until it returns, and the lookup waits on them.
  const update = await findByRole('button', { name: 'Update to 0.9.0' });
  await act(async () => update.click());
  const copy = await findByRole('button', { name: 'Copy prompt' });
  await act(async () => copy.click());
  expect(writeText).toHaveBeenCalledWith(notice.prompt);
  expect(bridge.request).not.toHaveBeenCalledWith('ui/message', expect.anything(), expect.anything());
});
