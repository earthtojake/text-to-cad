import { expect, it, vi } from 'vitest';
import { HostError } from './bridge';
import { APP_ROUTE, Unconnected, loadApp, unconnected, viaEngine, viaTunnel } from './shell';

const encode = (text: string) => btoa(text);

it('the shell reads the engine\'s app through the call the host carries, a part at a time for a long one', async () => {
  const code = 'x'.repeat(10);
  // A body longer than one part is answered a part at a time (`cad_server/mcp/tunnel.py`), each naming the body it continues.
  const ranges: string[] = [];
  const callTool = vi.fn(async (_name: string, args: Record<string, any>) => {
    const range = args.headers.range as string;
    ranges.push(range);
    const [first] = /bytes=(\d+)-/.exec(range)!.slice(1).map(Number);
    const last = Math.min(first + 3, code.length - 1);
    return { structuredContent: { status: 206, body: encode(code.slice(first, last + 1)),
      headers: { 'content-range': `bytes ${first}-${last}/${code.length}`, etag: '"e1"' } } };
  });
  // The tunnel asks for 4 MiB a part: here a part is four bytes, as the server cuts them.
  const text = await viaTunnel({ callTool } as any, 'capability');
  expect(text).toBe(code);
  expect(callTool.mock.calls[0][0]).toBe('cad_http');
  expect(callTool.mock.calls[0][1]).toMatchObject({ method: 'GET', url: `http://cad.invalid${APP_ROUTE}`,
    headers: { 'x-cad-app': 'capability' } });
  expect(callTool.mock.calls.slice(1).every(([, args]) => args.headers['if-range'] === '"e1"')).toBe(true);
  expect(ranges[0]).toBe(`bytes=0-${4 * 1024 * 1024 - 1}`);
});

it('a whole body comes in one reply, and a refusal of the server\'s is said', async () => {
  const whole = { structuredContent: { status: 200, body: encode('app()'), headers: {} } };
  expect(await viaTunnel({ callTool: async () => whole } as any, 't')).toBe('app()');
  const refused = { isError: true, content: [{ type: 'text', text: 'That view is not open.' }] };
  await expect(viaTunnel({ callTool: async () => refused } as any, 't')).rejects.toThrow('That view is not open.');
});

it('where the host carries no call, the shell reads the app from the engine with the launch\'s link, never a cookie', async () => {
  const fetch = vi.fn(async () => new Response('app()', { status: 200 }));
  const launch = { browser: 'http://127.0.0.1:3245/abc?token=day-link', engine: 'http://127.0.0.1:3245' };
  expect(await viaEngine(launch, fetch as any)).toBe('app()');
  expect(fetch).toHaveBeenCalledWith(`http://127.0.0.1:3245${APP_ROUTE}`, expect.objectContaining({
    headers: { authorization: 'Bearer day-link' }, credentials: 'omit' }));
  await expect(viaEngine({ browser: 'http://elsewhere/?token=x', engine: 'http://127.0.0.1:3245' }, fetch as any))
    .rejects.toBeInstanceOf(Unconnected);
});

it('a card its host carries no call for, and that cannot read the engine either, says so and links the page (#797)', async () => {
  // The Claude app's Code tab on Windows refuses the card's cad_http and blocks its fetch of the loopback engine
  // (ERR_BLOCKED_BY_CLIENT): the card once showed the fetch's own "Failed to fetch" and nothing else.
  const launch = { protocol: 9, page: 'viewer' as const, model: 'd5e6', browser: 'http://127.0.0.1:3245/d5e6?token=day-link',
    engine: 'http://127.0.0.1:3245' };
  const refused = { callTool: async () => { throw new HostError('IPC not available for MCP tool call'); } };
  const blocked = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
  for (const fetch of [blocked, vi.fn(async () => new Response('', { status: 401 }))]) {
    await expect(viaEngine(launch, fetch as any)).rejects.toBeInstanceOf(Unconnected);
  }
  await expect(loadApp({ bridge: refused as any, launch, result: {} }, { engine: launch => viaEngine(launch, blocked as any) }))
    .rejects.toBeInstanceOf(Unconnected);
  // A call the host did not refuse (it timed out) is no proof of a chat without a channel: not this notice.
  const slow = { callTool: async () => { throw new HostError('tools/call timed out', undefined, 'timeout'); } };
  await expect(loadApp({ bridge: slow as any, launch, result: {} })).rejects.toThrow('tools/call timed out');

  const root = document.createElement('div');
  const request = vi.fn(async () => ({}));
  const notify = vi.fn();
  const bridge = { hostContext: { locale: 'ja-JP' }, hostCapabilities: { openLinks: {} }, request, notify };
  unconnected(bridge as any, launch, 'inline', root);
  expect(root.querySelector('[data-cad-unreachable] p')?.textContent).toBe(
    'このチャットでは CAD ビューアーをエンジンに接続できません。代わりに CAD ビューアーでモデルを開いてください。');
  const open = root.querySelector('a')!;
  expect(open.getAttribute('href')).toBe(launch.browser);
  open.click();
  expect(request).toHaveBeenCalledWith('ui/open-link', { url: launch.browser });
  expect(notify).toHaveBeenCalledWith('ui/notifications/size-changed', { height: 180 });
  // No page in the launch: the agent is asked to open one, and nothing is linked.
  unconnected({ ...bridge, hostContext: {}, hostCapabilities: {} } as any, { ...launch, browser: undefined }, 'tabs', root);
  expect(root.textContent).toBe("This chat can't connect the CAD viewer to its engine. Ask your agent to open the model in the CAD "
    + 'Viewer instead.');
  expect(root.querySelector('a')).toBeNull();
});
