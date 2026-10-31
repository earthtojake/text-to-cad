import { expect, it, vi } from 'vitest';
import { APP_ROUTE, viaEngine, viaTunnel } from './shell';

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
    headers: { 'x-cadgen-app': 'capability' } });
  expect(callTool.mock.calls.slice(1).every(([, args]) => args.headers['if-range'] === '"e1"')).toBe(true);
  expect(ranges[0]).toBe(`bytes=0-${4 * 1024 * 1024 - 1}`);
});

it('a whole body comes in one reply, and a refusal of the server\'s is said', async () => {
  const whole = { structuredContent: { status: 200, body: encode('app()'), headers: {} } };
  expect(await viaTunnel({ callTool: async () => whole } as any, 't')).toBe('app()');
  const refused = { isError: true, content: [{ type: 'text', text: 'That view is not open.' }] };
  await expect(viaTunnel({ callTool: async () => refused } as any, 't')).rejects.toThrow('That view is not open.');
});

it('where the host carries no call, the shell reads the app from the engine with the launch\'s day link, never a cookie', async () => {
  const fetch = vi.fn(async () => new Response('app()', { status: 200 }));
  const launch = { browser: 'http://127.0.0.1:3245/abc?token=day-link', engine: 'http://127.0.0.1:3245' };
  expect(await viaEngine(launch, fetch as any)).toBe('app()');
  expect(fetch).toHaveBeenCalledWith(`http://127.0.0.1:3245${APP_ROUTE}`, expect.objectContaining({
    headers: { authorization: 'Bearer day-link' }, credentials: 'omit' }));
  await expect(viaEngine({ browser: 'http://elsewhere/?token=x', engine: 'http://127.0.0.1:3245' }, fetch as any))
    .rejects.toThrow('This chat cannot reach the CAD engine.');
});
