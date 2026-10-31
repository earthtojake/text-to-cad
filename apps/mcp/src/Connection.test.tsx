import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { CadViewerProps } from '@text-to-cad/ui/cad-viewer';
import Connection from './Connection';
import { HostError } from './host/bridge';
import { createChannel, declaresServerTools } from './host/channel';
import { createServer, type Launch } from './host/server';

// The shared CAD viewer, reduced to whether this page mounted it, and with what client.
const viewer = vi.hoisted(() => ({ props: null as CadViewerProps | null }));
vi.mock('@text-to-cad/ui/cad-viewer', async original => ({
  ...await original<object>(),
  CadViewer: (props: CadViewerProps) => { viewer.props = props; return null; },
}));

beforeEach(() => vi.stubGlobal('IntersectionObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); viewer.props = null; });

const PAGE = 'http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=1893456000.mac';
const ENGINE = 'http://127.0.0.1:3245';
const launch: Launch = { protocol: 9, page: 'viewer', model: '/work/parts/a.step', surface: 'inline', view: 'cad-1-a', browser: PAGE, engine: ENGINE };
// What the Claude app's Code tab answers every tools/call of a card with.
const REFUSAL = 'IPC not available for MCP tool call';

/** A host frame whose every tools/call is answered by `callTool`, with the capabilities it declares. */
function host(hostCapabilities: Record<string, unknown>, callTool: (name: string, args: any) => Promise<any>) {
  const bridge = {
    hostContext: {}, hostCapabilities, notify: vi.fn(), request: vi.fn(async () => ({})), callTool: vi.fn(callTool),
    onToolResult: () => () => {}, onTeardown: () => () => {}, onHostContext: () => () => {},
  };
  const channel = createChannel(declaresServerTools(hostCapabilities));
  const server = createServer(bridge, 'app-capability', channel);
  return { bridge, channel, server };
}
const refuse = async () => { throw new HostError(REFUSAL, -32603); };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

it('a host that refuses every call before any comes back gets one plain notice, its link and nothing else; the engine unreachable directly too', async () => {
  const { bridge, server, channel } = host({ openLinks: {} }, refuse);
  const fetchImpl = vi.fn(async () => { throw new TypeError('Refused to connect because it violates the document\'s Content Security Policy.'); });
  const { container } = render(<Connection bridge={bridge as any} server={server} channel={channel} launch={launch} presentation="inline" fetchImpl={fetchImpl as any} />);
  const notice = await screen.findByRole('alert');
  expect(notice.textContent).toContain('This chat can\'t connect the CAD viewer to its engine. Open the model in the CAD Viewer instead.');
  const link = screen.getByRole('link', { name: 'Open in CAD Viewer' });
  expect([link.getAttribute('href'), link.getAttribute('target')]).toEqual([PAGE, '_blank']);
  // No home, no library, and never the host's own words or the sandbox's.
  expect(viewer.props).toBeNull();
  expect(container.textContent).not.toMatch(/IPC|Content Security|library/i);
  expect(channel.state).toBe('none');
  // The probe asked the engine once, directly, with the page's day link as a Bearer credential.
  expect(fetchImpl).toHaveBeenCalledTimes(1);
  // The host opens links: the link goes through it.
  act(() => link.click());
  expect(bridge.request).toHaveBeenCalledWith('ui/open-link', { url: PAGE });
  // The card is as tall as its notice, once its effects have run (the DOM commits before them).
  await waitFor(() => expect(bridge.notify).toHaveBeenLastCalledWith('ui/notifications/size-changed', { height: 180 }));
});

it('a host that declared it carries calls, and refused them anyway, ends on the same notice; a launch with no page says to ask the agent', async () => {
  const { bridge, server, channel } = host({ serverTools: {} }, refuse);
  const fetchImpl = vi.fn(async () => json({ error: 'engine token required' }, 403));
  const { container } = render(<Connection bridge={bridge as any} server={server} channel={channel} launch={{ ...launch, browser: undefined, engine: undefined }}
    presentation="inline" fetchImpl={fetchImpl as any} />);
  await waitFor(() => expect(container.querySelector('[data-cad-unreachable]')).not.toBeNull());
  expect(container.textContent).toBe('This chat can\'t connect the CAD viewer to its engine. Ask your agent to open the model in the CAD Viewer instead.');
  expect(screen.queryByRole('link')).toBeNull();
  expect(fetchImpl).not.toHaveBeenCalled();
});

it('an engine the probe reaches runs the whole card over direct HTTP: the day link as its credential, no host call and no sync', async () => {
  const { bridge, server, channel } = host({}, refuse);
  const asked: { url: string; headers: Headers; credentials?: string }[] = [];
  const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
    asked.push({ url, headers: new Headers(init.headers), credentials: init.credentials });
    const path = new URL(url).pathname;
    if (path === '/__cad/server') return json({ app: 'cad-viewer' });
    if (path === '/__cad/recents') return json({ recents: [] });
    if (path === '/__cad/analytics') return json({ sharing: false, policy: 'https://www.texttocad.dev/privacy-policy' });
    return json({ notice: null });
  });
  render(<Connection bridge={bridge as any} server={server} channel={channel} launch={launch} presentation="inline" fetchImpl={fetchImpl as any} />);
  await waitFor(() => expect(viewer.props).not.toBeNull());
  expect(viewer.props!.file).toBe('/work/parts/a.step');
  // The client's requests (its library here) go to the engine's origin, path and query unchanged.
  await act(async () => { await viewer.props!.client.recents(); });
  expect(asked.every(request => request.url.startsWith(`${ENGINE}/`))).toBe(true);
  expect(asked.map(request => new URL(request.url).pathname)).toEqual(expect.arrayContaining(['/__cad/server', '/__cad/recents']));
  for (const request of asked) {
    expect(request.headers.get('authorization')).toBe('Bearer 1893456000.mac');
    expect(request.headers.has('x-cadgen-app')).toBe(false);
    expect(request.credentials).toBe('omit');
  }
  // The host was asked once, the check that found it refuses; never again, and no view sync.
  expect(bridge.callTool.mock.calls.map(([name]) => name)).toEqual(['cad_http']);
});

it('a host that carries calls without declaring it is checked once, then the card runs through it; a tab host is never checked', async () => {
  const answered = async (name: string, args: any) => name === 'cad_sync' ? new Promise(() => {})
    : { structuredContent: { status: 200, headers: { 'content-type': 'application/json' }, body: btoa(JSON.stringify(new URL(args.url).pathname === '/__cad/server' ? { app: 'cad-viewer' } : {})) } };
  const quiet = host({}, answered);
  const fetchImpl = vi.fn();
  const { container } = render(<Connection bridge={quiet.bridge as any} server={quiet.server} channel={quiet.channel} launch={launch} presentation="inline" fetchImpl={fetchImpl as any} />);
  expect(container.querySelector('[data-cad-connecting]')).not.toBeNull();
  expect(viewer.props).toBeNull();
  await waitFor(() => expect(viewer.props).not.toBeNull());
  expect(quiet.channel.state).toBe('open');
  expect(quiet.bridge.callTool.mock.calls[0].slice(0, 2)).toMatchObject(['cad_http', { method: 'GET', url: 'http://cad.invalid/__cad/server' }]);
  cleanup();
  viewer.props = null;
  const tab = host({}, answered);
  render(<Connection bridge={tab.bridge as any} server={tab.server} channel={tab.channel} launch={{ ...launch, surface: 'tab' }} presentation="tabs" fetchImpl={fetchImpl as any} />);
  expect(viewer.props).not.toBeNull();
  expect(tab.bridge.callTool.mock.calls.some(([, args]) => String(args.url).endsWith('/__cad/server'))).toBe(false);
  expect(fetchImpl).not.toHaveBeenCalled();
});
