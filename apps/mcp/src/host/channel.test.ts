import { describe, expect, it } from 'vitest';
import { createBridge, HostError } from './bridge';
import { createChannel, declaresOpenLinks, declaresServerTools, isHostRefusal } from './channel';
import { createDirectFetch, engineReach, probeEngine } from './direct';
import { createServer, ServerError } from './server';
import { createTunnelFetch, TUNNEL_ORIGIN } from './tunnel';

/** A host frame answering the page's requests with `respond`: a result, or `{ error }`. */
function frame(respond: (message: any) => { result?: unknown; error?: { code: number; message: string } } | undefined) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    postMessage(message: any) {
      if (message.id === undefined || message.method === undefined) return;
      const answer = respond(message);
      if (answer) queueMicrotask(() => { for (const listener of [...listeners]) listener({ data: { jsonrpc: '2.0', id: message.id, ...answer }, source: host } as MessageEvent); });
    },
  };
  const self = { addEventListener: (_: string, listener: any) => listeners.add(listener), removeEventListener: (_: string, listener: any) => listeners.delete(listener) };
  return createBridge(host, self as any);
}

const REFUSAL = 'IPC not available for MCP tool call';

describe('the channel to CAD\'s server', () => {
  it('reads at ui/initialize whether the host carries an app\'s tools/call, and whether it opens links', async () => {
    const declaring = frame(message => message.method === 'ui/initialize' ? { result: { hostCapabilities: { serverTools: { listChanged: true }, openLinks: {} } } } : { result: {} });
    await declaring.initialize({ name: 'CAD', version: 'test' });
    expect([declaresServerTools(declaring.hostCapabilities), declaresOpenLinks(declaring.hostCapabilities)]).toEqual([true, true]);
    const silent = frame(message => message.method === 'ui/initialize' ? { result: { hostCapabilities: {} } } : { result: {} });
    await silent.initialize({ name: 'CAD', version: 'test' });
    expect([declaresServerTools(silent.hostCapabilities), declaresOpenLinks(silent.hostCapabilities)]).toEqual([false, false]);
    expect(createChannel(true).state).toBe('open');
    expect(createChannel(false).state).toBe('unknown');
  });

  it('tells the host\'s refusal of a call from a timeout and from the engine\'s own answer', async () => {
    const refusing = frame(() => ({ error: { code: -32603, message: REFUSAL } }));
    const refused = await refusing.callTool('cad_http', {}).catch(error => error);
    expect([refused instanceof HostError, refused.kind, isHostRefusal(refused)]).toEqual([true, 'refused', true]);
    const silent = frame(() => undefined);
    const late = await silent.request('tools/call', {}, { timeoutMs: 5 }).catch(error => error);
    expect([late.kind, isHostRefusal(late)]).toEqual(['timeout', false]);
    expect(isHostRefusal(new ServerError('This CAD view was opened before CAD restarted: close it and open CAD again.'))).toBe(false);
  });

  it('is none once the host refuses a call before any came back, and never from a refusal after one did', async () => {
    let refuse = true;
    const bridge = frame(() => refuse ? { error: { code: -32603, message: REFUSAL } } : { result: { structuredContent: { status: 200, headers: {}, body: '' } } });
    const never = createChannel(true);
    const tunnel = createTunnelFetch(createServer(bridge, 'app-capability', never));
    // The fetch fails as fetch does, in words of ours: never the host's.
    const failed = await tunnel(`${TUNNEL_ORIGIN}/__cad/recents`).catch(error => error);
    expect([failed instanceof TypeError, failed.message]).toEqual([true, 'This chat cannot connect the CAD viewer to its engine.']);
    expect(never.state).toBe('none');
    // A chat whose calls came back: a later refusal is the plugin stopping, which the sync says.
    refuse = false;
    const carried = createChannel(false);
    const server = createServer(bridge, 'app-capability', carried);
    await server.http({ method: 'GET', url: `${TUNNEL_ORIGIN}/__cad/server`, headers: {}, body: '' });
    refuse = true;
    await expect(server.http({ method: 'GET', url: `${TUNNEL_ORIGIN}/__cad/server`, headers: {}, body: '' })).rejects.toThrow(REFUSAL);
    expect(carried.state).toBe('open');
    // The engine's own refusal is an answer: the channel is open, and its words are the reason shown.
    const stale = createChannel(false);
    const engine = createTunnelFetch(createServer({ callTool: async () => ({ isError: true, content: [{ type: 'text', text: 'This CAD view was opened before CAD restarted: close it and open CAD again.' }] }) }, 'app-capability', stale));
    await expect(engine(`${TUNNEL_ORIGIN}/__cad/server`)).rejects.toThrow('This CAD view was opened before CAD restarted');
    expect(stale.state).toBe('open');
  });
});

describe('the engine reached directly', () => {
  const reach = { origin: 'http://127.0.0.1:3245', link: '1893456000.mac' };

  it('takes the engine and its day link from a launch that carries a page of that engine, else none', () => {
    expect(engineReach({ browser: 'http://127.0.0.1:3245/abc?token=1893456000.mac', engine: 'http://127.0.0.1:3245' }))
      .toEqual({ ...reach, page: 'http://127.0.0.1:3245/abc?token=1893456000.mac' });
    expect(engineReach({ browser: 'http://127.0.0.1:3245/abc', engine: 'http://127.0.0.1:3245' })).toBeNull();
    expect(engineReach({ browser: 'http://127.0.0.1:9999/abc?token=t', engine: 'http://127.0.0.1:3245' })).toBeNull();
    expect(engineReach({})).toBeNull();
  });

  it('probes one authenticated read, and says no for a refusal, a stranger, or a fetch the sandbox blocks', async () => {
    const answering = (body: unknown, status = 200) => async () => new Response(JSON.stringify(body), { status });
    expect(await probeEngine(reach, answering({ app: 'cad-viewer' }) as any)).toBe(true);
    expect(await probeEngine(reach, answering({ error: 'engine token required' }, 403) as any)).toBe(false);
    expect(await probeEngine(reach, answering({ app: 'something-else' }) as any)).toBe(false);
    expect(await probeEngine(reach, (async () => { throw new TypeError('Failed to fetch'); }) as any)).toBe(false);
    // An engine that never answers: the card stops waiting.
    expect(await probeEngine(reach, ((_url: string, init: RequestInit) => new Promise((_, reject) => init.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))) as any, 5)).toBe(false);
  });

  it('sends a POST to the engine with its body, the guard header and the Bearer link, and fails in words of ours', async () => {
    const sent: any[] = [];
    const direct = createDirectFetch(reach, (async (url: string, init: RequestInit) => {
      sent.push({ url, method: init.method, headers: Object.fromEntries(new Headers(init.headers)), body: new TextDecoder().decode(init.body as ArrayBuffer) });
      return new Response('{}');
    }) as any);
    await direct(`${TUNNEL_ORIGIN}/__cad/recents?x=1`, { method: 'POST', headers: { 'x-cadgen-viewer': '1', 'x-cadgen-app': 'session', 'content-type': 'application/json' }, body: '{"a":1}' });
    expect(sent).toEqual([{ url: 'http://127.0.0.1:3245/__cad/recents?x=1', method: 'POST', body: '{"a":1}',
      headers: { authorization: 'Bearer 1893456000.mac', 'content-type': 'application/json', 'x-cadgen-viewer': '1' } }]);
    const blocked = createDirectFetch(reach, (async () => { throw new TypeError('net::ERR_BLOCKED_BY_CSP'); }) as any);
    await expect(blocked(`${TUNNEL_ORIGIN}/__cad/server`)).rejects.toThrow('The CAD engine could not be reached.');
  });
});
