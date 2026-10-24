import { describe, expect, it, vi } from 'vitest';
import { encodeBase64 } from '@text-to-cad/core/client';
import { createPromptContext, referencePart } from '@text-to-cad/core/prompt';
import { createBridge, HostError, type ToolResult } from './bridge';
import { frameClipboard } from './clipboard';
import { chatReach, createChatPromptContext } from './prompt';
import { createServer, type SyncReply, type SyncRequest, type ViewEvent } from './server';
import { createViewSync, LOST_AFTER, SYNC_MS } from './sync';
import { createTunnelFetch, decodeBase64, TUNNEL_ORIGIN, TUNNEL_REPLY_MAX_BYTES } from './tunnel';

/** A host frame: records what the page posts and answers with `respond`. */
function fakeHost(respond: (message: any) => unknown) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const posted: any[] = [];
  const host: { postMessage(message: any): void } = {
    postMessage(message: any) {
      posted.push(message);
      if (message.id === undefined || message.method === undefined) return;
      const result = respond(message);
      if (result !== undefined) queueMicrotask(() => deliver({ jsonrpc: '2.0', id: message.id, result }));
    },
  };
  // What the host posts arrives from the host's window; `source` lets a test speak as another frame.
  const deliver = (data: unknown, source: unknown = host) => {
    for (const listener of [...listeners]) listener({ data, source } as MessageEvent);
  };
  const self = {
    addEventListener: (_type: string, listener: any) => listeners.add(listener),
    removeEventListener: (_type: string, listener: any) => listeners.delete(listener),
  };
  return { host, self, posted, deliver };
}

describe('the MCP Apps bridge', () => {
  it('initializes, replays the launching result and follows the host context', async () => {
    const frame = fakeHost(message => message.method === 'ui/initialize' ? { hostContext: { theme: 'dark' }, hostCapabilities: {} } : {});
    const bridge = createBridge(frame.host, frame.self as any);
    await bridge.initialize({ name: 'CAD', version: 'test' });
    expect(bridge.hostContext.theme).toBe('dark');
    expect(frame.posted.some(message => message.method === 'ui/notifications/initialized')).toBe(true);
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: { launch: { page: 'home' } }, _meta: { 'dev.texttocad/httpToken': 'session-capability' } } });
    const seen: ToolResult[] = [];
    bridge.onToolResult(result => seen.push(result));
    expect(seen[0].structuredContent).toEqual({ launch: { page: 'home' } });
    expect(seen[0]._meta?.['dev.texttocad/httpToken']).toBe('session-capability');
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme: 'light' } });
    expect(bridge.hostContext.theme).toBe('light');
  });

  it('hears only the host: another frame can neither answer a request nor speak as the host', async () => {
    const frame = fakeHost(() => undefined);
    const bridge = createBridge(frame.host, frame.self as any);
    const other = { postMessage() {} };
    const seen: ToolResult[] = [];
    bridge.onToolResult(result => seen.push(result));
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: { launch: { page: 'forged' } } } }, other);
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme: 'dark' } }, null);
    expect(seen).toEqual([]);
    expect(bridge.hostContext.theme).toBeUndefined();

    const pending = bridge.callTool('cad_sync', { view: 'v' });
    const call = frame.posted.find(message => message.method === 'tools/call');
    frame.deliver({ jsonrpc: '2.0', id: call.id, result: { structuredContent: { from: 'other' } } }, other);
    frame.deliver({ jsonrpc: '2.0', id: call.id, result: { structuredContent: { from: 'host' } } });
    await expect(pending).resolves.toEqual({ structuredContent: { from: 'host' } });
  });

  it('numbers its requests from a random start, one apart', async () => {
    const starts = new Set<number>();
    for (let at = 0; at < 4; at += 1) {
      const frame = fakeHost(() => ({}));
      const bridge = createBridge(frame.host, frame.self as any);
      await bridge.callTool('cad_sync', { view: 'v' });
      await bridge.callTool('cad_sync', { view: 'v' });
      const [first, second] = frame.posted.filter(message => message.method === 'tools/call').map(message => message.id);
      expect(Number.isSafeInteger(first)).toBe(true);
      expect(second).toBe(first + 1);
      starts.add(first);
    }
    expect(starts.size).toBeGreaterThan(1);
  });

  it('cancels an aborted request with the host and rejects it', async () => {
    const frame = fakeHost(() => undefined);
    const bridge = createBridge(frame.host, frame.self as any);
    const abort = new AbortController();
    const pending = bridge.callTool('cad_sync', { view: 'v' }, { signal: abort.signal });
    abort.abort();
    await expect(pending).rejects.toThrow();
    const call = frame.posted.find(message => message.method === 'tools/call');
    expect(frame.posted).toContainEqual({ jsonrpc: '2.0', method: 'notifications/cancelled', params: { requestId: call.id } });
  });

  it('acknowledges teardown before the page cleans up, even when a cleanup throws', () => {
    const frame = fakeHost(() => undefined);
    const bridge = createBridge(frame.host, frame.self as any);
    const acknowledged = () => frame.posted.some(message => message.id === 7 && message.result);
    const seen: boolean[] = [];
    bridge.onTeardown(() => { seen.push(acknowledged()); throw new Error('cleanup failed'); });
    bridge.onTeardown(() => seen.push(acknowledged()));
    frame.deliver({ jsonrpc: '2.0', id: 7, method: 'ui/resource-teardown', params: {} });
    expect(frame.posted).toContainEqual({ jsonrpc: '2.0', id: 7, result: {} });
    expect(seen).toEqual([true, true]);
  });
});

describe('a view\'s one call each second', () => {
  function syncing(replies: Partial<SyncReply>[]) {
    const requests: SyncRequest[] = [];
    const replies_ = [...replies];
    const replied: unknown[] = [];
    const server = {
      sync: vi.fn(async (request: SyncRequest) => { requests.push(structuredClone(request)); return { events: [], ...(replies_.shift() || {}) } as SyncReply; }),
      reply: async (requestId: string, reply: object) => { replied.push({ requestId, ...reply }); },
    };
    return { server, requests, replied };
  }

  it('answers the agent, asks again at once after news, and otherwise once a second; nothing is held', async () => {
    vi.useFakeTimers();
    try {
      const launch = { protocol: 5, page: 'viewer' as const, model: '/p/b.step' };
      const { server, requests, replied } = syncing([
        { events: [{ seq: 1, type: 'show', launch }, { seq: 2, type: 'capture', requestId: 'c1' }] as ViewEvent[] },
        { events: [{ seq: 3, type: 'capture', requestId: 'c2' }] as ViewEvent[] },
      ]);
      const shown: unknown[] = [];
      const captures = [new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })];
      const stop = new AbortController();
      const sync = createViewSync(server, { id: 'v1', surface: 'tab', model: () => '/p/a.step' }, {
        show: next => shown.push(next.model),
        capture: async () => { const png = captures.shift(); if (!png) throw new Error('nothing to capture'); return png; },
        state: () => ({ model: '/p/a.step', selection: ['/p/a.step#o:3f2a9c1d7e5b/f:bracket.extrude1.3'] }),
      });
      sync.run(stop.signal);
      await vi.advanceTimersByTimeAsync(0);
      expect(requests).toHaveLength(3);
      await vi.advanceTimersByTimeAsync(SYNC_MS - 1);
      expect(requests).toHaveLength(3);
      await vi.advanceTimersByTimeAsync(1);
      expect(requests).toHaveLength(4);
      // What the view shows goes up once, and again only when it changes.
      expect(requests.map(request => Boolean(request.state))).toEqual([true, false, false, false]);
      expect(requests[0]).toMatchObject({ view: 'v1', surface: 'tab', model: '/p/a.step', state: { selection: ['/p/a.step#o:3f2a9c1d7e5b/f:bracket.extrude1.3'] } });
      expect(shown).toEqual(['/p/b.step']);
      expect(replied).toEqual(expect.arrayContaining([
        { requestId: 'c1', png: encodeBase64(new Uint8Array([1, 2, 3])) },
        { requestId: 'c2', error: 'nothing to capture' },
      ]));
      // A touch is said at once; a newer view's taking over is the last sync.
      sync.focus();
      await vi.advanceTimersByTimeAsync(0);
      expect(requests.at(-1)).toMatchObject({ focused: true });
      await sync.close();
      expect(requests.at(-1)).toMatchObject({ closed: true });
      const count = requests.length;
      await vi.advanceTimersByTimeAsync(SYNC_MS * 3);
      expect(requests).toHaveLength(count);
      stop.abort();
    } finally { vi.useRealTimers(); }
  });

  // The host starts a thread's server once: if its process goes, every sync fails, and the view
  // says so rather than freeze on its last model; it says so again once a sync succeeds.
  it('says its server is gone once syncs keep failing, and back when one answers', async () => {
    vi.useFakeTimers();
    try {
      let down = true;
      const server = {
        sync: vi.fn(async () => { if (down) throw new Error('server gone'); return { events: [] } as unknown as SyncReply; }),
        reply: async () => {},
      };
      const said: boolean[] = [];
      const stop = new AbortController();
      const sync = createViewSync(server, { id: 'v1', surface: 'tab', model: () => null }, {
        show: () => {}, capture: async () => new Blob(), state: () => ({}),
        connection: connected => said.push(connected),
      });
      sync.run(stop.signal);
      // The backoff between failures doubles from a second: 1, 2, 4, 8 s.
      await vi.advanceTimersByTimeAsync(0);
      await vi.advanceTimersByTimeAsync(1_000);
      await vi.advanceTimersByTimeAsync(2_000);
      expect(server.sync).toHaveBeenCalledTimes(LOST_AFTER - 1);
      expect(said).toEqual([]);
      await vi.advanceTimersByTimeAsync(4_000);
      expect(said).toEqual([false]);
      down = false;
      await vi.advanceTimersByTimeAsync(8_000);
      expect(said).toEqual([false, true]);
      stop.abort();
    } finally { vi.useRealTimers(); }
  });

  it('reads the catalog again only when its revision moves past the one applied', async () => {
    vi.useFakeTimers();
    try {
      const { server, requests } = syncing([
        { catalog: { revision: 'r1' } },
        { catalog: { revision: 'r2' } },
        { catalog: { revision: 'r2' } },
        { catalog: { revision: 'r2' } },
      ]);
      let applied = 'r1';
      const refreshes: (string | null)[] = [];
      const stop = new AbortController();
      const sync = createViewSync(server, { id: 'v1', surface: 'tab', model: () => '/p/a.step' },
        { show() {}, capture: async () => new Blob(), state: () => ({}) });
      sync.watch({ file: () => '/p/a.step', revision: () => applied,
        refresh: async file => { refreshes.push(file); applied = 'r2'; } });
      sync.run(stop.signal);
      await vi.advanceTimersByTimeAsync(0);
      expect(requests[0].watch).toEqual({ file: '/p/a.step' });
      expect(refreshes).toEqual([]);
      await vi.advanceTimersByTimeAsync(SYNC_MS);
      expect(refreshes).toEqual(['/p/a.step']);
      await vi.advanceTimersByTimeAsync(2 * SYNC_MS);
      expect(requests).toHaveLength(4);
      expect(refreshes).toEqual(['/p/a.step']);
      stop.abort();
    } finally { vi.useRealTimers(); }
  });
});

describe('the page\'s own calls', () => {
  it('carry the app capability: cad_sync and cad_capture_reply as `app`', async () => {
    const calls: any[] = [];
    const server = createServer({ callTool: async (name, args) => { calls.push({ name, args }); return { structuredContent: { events: [] } }; } }, 'app-capability');
    await server.sync({ view: 'v', surface: 'tab', model: null });
    await server.reply('r1', { png: 'iVBORw0KGgo=' });
    expect(calls).toEqual([
      { name: 'cad_sync', args: { view: 'v', surface: 'tab', model: null, app: 'app-capability' } },
      { name: 'cad_capture_reply', args: { requestId: 'r1', png: 'iVBORw0KGgo=', app: 'app-capability' } },
    ]);
  });
});

describe('the fetch tunnel', () => {
  it('sends the request as cad_http and returns the reply as a Response', async () => {
    const calls: any[] = [];
    const server = createServer({
      callTool: async (name, args) => {
        calls.push({ name, args });
        return { structuredContent: { status: args.method === 'HEAD' ? 200 : 201, headers: { 'content-type': 'application/json', 'content-length': '11' }, body: encodeBase64(new TextEncoder().encode('{"ok":true}')) } };
      },
    }, 'app-capability');
    const tunnel = createTunnelFetch(server);
    const posted = await tunnel(`${TUNNEL_ORIGIN}/__cad/parts?x=1`, { method: 'POST', headers: { 'x-cadgen-viewer': '1' }, body: '{"a":1}' });
    expect(calls[0]).toMatchObject({ name: 'cad_http', args: { method: 'POST', url: `${TUNNEL_ORIGIN}/__cad/parts?x=1` } });
    expect(calls[0].args.headers['x-cadgen-viewer']).toBe('1');
    expect(calls[0].args.headers['x-cadgen-app']).toBe('app-capability');
    expect(new TextDecoder().decode(decodeBase64(calls[0].args.body))).toBe('{"a":1}');
    expect(posted.status).toBe(201);
    expect(await posted.json()).toEqual({ ok: true });
    const head = await tunnel(`${TUNNEL_ORIGIN}/__cad/asset?file=a`, { method: 'HEAD' });
    expect([head.status, head.headers.get('content-length'), await head.text()]).toEqual([200, '11', '']);
  });

  it('keeps version reads from occupying a host call slot', async () => {
    const calls: any[] = [];
    const server = createServer({ callTool: async (_name, args) => {
      calls.push(args);
      return { structuredContent: { status: 200, headers: {}, body: '' } };
    } }, 'app-capability');
    await createTunnelFetch(server)(`${TUNNEL_ORIGIN}/__cad/api/doc/part/version?after=v&wait=60`);
    expect(new URL(calls[0].url).searchParams.get('wait')).toBe('0');
  });

  it('inflates a body the server gzipped for the trip, and refuses an encoding it cannot read', async () => {
    const json = JSON.stringify({ entries: Array.from({ length: 200 }, (_, index) => ({ file: `parts/part-${index}.step` })) });
    const gzipped = new Uint8Array(await new Response(new Response(json).body!.pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
    let encoding = 'gzip';
    const server = createServer({
      callTool: async () => ({ structuredContent: { status: 200, encoding, body: encodeBase64(gzipped),
        headers: { 'content-type': 'application/json', 'content-length': String(json.length) } } }),
    }, 'app-capability');
    const tunnel = createTunnelFetch(server);
    const reply = await tunnel(`${TUNNEL_ORIGIN}/__cad/catalog`);
    expect([reply.headers.get('content-length'), await reply.text()]).toEqual([String(json.length), json]);
    encoding = 'br';
    await expect(tunnel(`${TUNNEL_ORIGIN}/__cad/catalog`)).rejects.toThrow(TypeError);
  });

  it('turns a failed call into the TypeError fetch throws', async () => {
    const tunnel = createTunnelFetch(createServer({ callTool: async () => ({ isError: true, content: [{ type: 'text', text: 'not this thread' }] }) }, 'app-capability'));
    await expect(tunnel(`${TUNNEL_ORIGIN}/__cad/catalog`)).rejects.toThrow(TypeError);
  });

  it('reads a body longer than one reply a part at a time, each within the bound and naming the body it continues, and hands over the whole', async () => {
    const bytes = pattern(3 * TUNNEL_REPLY_MAX_BYTES + 1000);
    const parted = servingInParts(bytes);
    const reply = await createTunnelFetch(parted.server)(`${TUNNEL_ORIGIN}/__cad/asset?file=big.stl`);
    expect([reply.status, reply.headers.get('content-length'), reply.headers.get('content-range')]).toEqual([200, String(bytes.length), null]);
    expect(same(new Uint8Array(await reply.arrayBuffer()), bytes)).toBe(true);
    expect(parted.ranges).toEqual([0, 1, 2, 3].map(part => `bytes=${part * TUNNEL_REPLY_MAX_BYTES}-${Math.min(bytes.length, (part + 1) * TUNNEL_REPLY_MAX_BYTES) - 1}`));
    expect(Math.max(...parted.sizes)).toBe(TUNNEL_REPLY_MAX_BYTES);
    // Every part after the first names the body, which the server kept and cuts the part from.
    expect(parted.continues).toEqual([null, '"v1"', '"v1"', '"v1"']);
  });

  it('fails the read of a body that changed between its parts, or whose parts are out of place', async () => {
    const bytes = pattern(TUNNEL_REPLY_MAX_BYTES + 10);
    for (const parted of [
      servingInParts(bytes, { etag: first => (first ? '"rewritten"' : '"v1"') }),
      servingInParts(bytes, { offset: first => (first ? first + 1 : 0) }),
    ]) {
      const reply = await createTunnelFetch(parted.server)(`${TUNNEL_ORIGIN}/__cad/asset?file=big.stl`);
      await expect(reply.arrayBuffer()).rejects.toThrow(TypeError);
    }
  });
});

/** `length` bytes that differ from part to part. */
function pattern(length: number) {
  return new Uint8Array(length).map((_, index) => (index * 7 + (index >> 12)) & 255);
}

function same(a: Uint8Array, b: Uint8Array) {
  if (a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) if (a[index] !== b[index]) return false;
  return true;
}

/**
 * A server that answers a ranged GET as `cadgen mcp` does (`cadgen/mcp/tunnel.py`) for a body
 * longer than the range: its part (206). `etag` names the body a part is of, `offset` moves where
 * a part starts, and `alter` changes a part's bytes.
 */
function servingInParts(bytes: Uint8Array, {
  etag = (_first: number) => '"v1"', offset = (first: number) => first, alter = (part: Uint8Array, _first: number) => part,
} = {}) {
  const ranges: string[] = [];
  const continues: (string | null)[] = [];
  const sizes: number[] = [];
  const server = createServer({
    callTool: async (_name, args: any) => {
      ranges.push(args.headers.range);
      continues.push(args.headers['if-range'] ?? null);
      const asked = /^bytes=(\d+)-(\d+)$/.exec(args.headers.range)!;
      const first = offset(Number(asked[1]));
      const last = Math.min(bytes.length - 1, Number(asked[2]));
      const part = alter(bytes.slice(first, last + 1), first);
      sizes.push(part.length);
      return { structuredContent: { status: 206, body: encodeBase64(part), headers: {
        'content-type': 'application/octet-stream', 'content-length': String(part.length),
        'content-range': `bytes ${first}-${last}/${bytes.length}`, etag: etag(first),
      } } };
    },
  }, 'app-capability');
  return { server, ranges, continues, sizes };
}

describe('a Quick Edit in the chat', () => {
  const file = referencePart({ resource: { kind: 'workspace-file', path: '/project/parts/a.step' }, target: { kind: 'whole-resource' } }, 'file');
  const face = referencePart({ resource: { kind: 'workspace-file', path: '/project/parts/a.step' }, target: { kind: 'cad-selector', selectors: ['o:1a2b3c4d5e6f/f:base.extrude1.2'] } }, 'face');
  const annotation = () => ({ id: 'annotation', kind: 'attachment' as const, name: 'a.annotation.json', label: 'Annotation', mimeType: 'application/json', about: ['file'],
    content: { then: () => { throw new Error('JSON bytes must not be read for handoff'); } }, path: Promise.resolve('/tmp/p/a-1.annotation.json') });
  // The snapshot packet: a file, never an image, always named by where it was made.
  const snapshot = () => ({ id: 'snapshot', kind: 'attachment' as const, name: 'a.snapshot.json', label: 'Snapshot', mimeType: 'application/json', about: ['file'],
    content: new Blob(['{}'], { type: 'application/json' }), path: Promise.resolve('/tmp/p/a-1.snapshot.json') });
  const edit = (...parts: any[]) => createPromptContext([{ id: 'text', kind: 'text', text: 'Round it.' }, file, ...parts]);

  it('reaches what the host declared: a tab host queues whatever it declares, and messages only need text', () => {
    expect(chatReach({}, 'tabs')).toEqual({ queue: true, send: false });
    expect(chatReach({ message: { text: {} } }, 'inline')).toEqual({ queue: false, send: true });
    expect(chatReach({ updateModelContext: {}, message: { text: {}, image: {} } }, 'inline')).toEqual({ queue: true, send: true });
  });

  it('queues into the composer as one titled message and its annotation, keeping what it queued until the host clears it', async () => {
    const updates: any[] = [];
    let context: (value: any) => void = () => {};
    const port = createChatPromptContext({
      hostContext: {},
      onHostContext: listener => { context = listener; return () => {}; },
      request: async (method: string, params: any) => { updates.push({ method, params }); return {}; },
    } as any, { reach: { queue: true, send: false } });
    expect([port.getSnapshot().kind, port.send]).toEqual(['composer', undefined]);
    expect((await port.deliver(edit(face, annotation()))).status).toBe('added');
    const [text] = updates[0].params.content;
    expect(updates[0].params.content).toHaveLength(1);
    expect(updates[0].method).toBe('ui/update-model-context');
    expect(text).toEqual({ type: 'text', text: 'Round it.\n\nFile: /project/parts/a.step\nReferences:\n/project/parts/a.step#o:1a2b3c4d5e6f/f:base.extrude1.2\nAnnotation: /tmp/p/a-1.annotation.json', _meta: { 'openai/title': 'Quick edit · a.step' } });
    await port.deliver(edit());
    expect(updates[1].params.content).toHaveLength(2);
    // The host cleared the context (the message went out): the next one starts afresh.
    context({ 'openai/modelContext': null });
    await port.deliver(edit());
    expect(updates[2].params.content).toHaveLength(1);
  });

  it('says to copy the prompt where a tab host does not take context, instead of the bare JSON-RPC error', async () => {
    const port = createChatPromptContext({
      hostContext: {}, onHostContext: () => () => {},
      request: async () => { throw new HostError('Method not found', -32601); },
    } as any, { reach: { queue: true, send: false } });
    const result = await port.deliver(edit());
    expect(result.status).toBe('failed');
    expect((result as { message: string }).message).toMatch(/Copy Prompt/);
  });

  it.each(['queue', 'send'])('delivers inline snapshot JSON through the real %s host port', async action => {
    const sent: any[] = [];
    const port = createChatPromptContext({ hostContext: {}, onHostContext: () => () => {},
      request: async (method: string, params: any) => { sent.push({ method, params }); return {}; },
    } as any, { reach: { queue: true, send: true } });
    const context = edit({ ...snapshot(), path: Promise.resolve(''),
      inlineText: Promise.resolve('Snapshot JSON:\n{"jobs":[]}') });
    await (action === 'queue' ? port.deliver(context) : port.send!(context));
    expect(sent[0].method).toBe(action === 'queue' ? 'ui/update-model-context' : 'ui/message');
    expect(sent[0].params.content[0].text).toBe('Round it.\n\nFile: /project/parts/a.step\nSnapshot JSON:\n{"jobs":[]}');
    port.dispose();
  });

  it('sends a message into the chat, its single snapshot named by path even when the host supports images', async () => {
    const sent: any[] = [];
    let refuse = false;
    const bridge = {
      hostContext: {}, onHostContext: () => () => {},
      request: async (method: string, params: any) => {
        sent.push({ method, params });
        if (refuse && params.content.some((block: any) => block.type === 'image')) throw new HostError('Invalid MCP message params', -32602);
        return {};
      },
    } as any;
    const port = createChatPromptContext(bridge, { reach: { queue: false, send: true } });
    expect(port.getSnapshot().kind).toBe('unavailable');
    expect((await port.send!(edit(snapshot()))).status).toBe('sent');
    expect(sent[0].method).toBe('ui/message');
    expect(sent[0].params.role).toBe('user');
    expect(sent[0].params.content.map((block: any) => block.type)).toEqual(['text']);
    expect(sent[0].params.content[0].text).toBe('Round it.\n\nFile: /project/parts/a.step\nSnapshot: /tmp/p/a-1.snapshot.json');
    refuse = true;
    expect((await port.send!(edit(snapshot()))).status).toBe('sent');
    expect(sent.at(-1).params.content).toEqual([{ type: 'text',
      text: 'Round it.\n\nFile: /project/parts/a.step\nSnapshot: /tmp/p/a-1.snapshot.json' }]);
  });
});

describe('the frame\'s clipboard', () => {
  it('starts a write of text still on its way inside the gesture, and takes the text when it arrives', async () => {
    const events: string[] = [];
    vi.stubGlobal('ClipboardItem', class { constructor(readonly items: Record<string, Promise<Blob>>) { events.push('item'); } });
    vi.stubGlobal('navigator', { clipboard: { write: async (items: any[]) => { events.push('write'); events.push(await (await items[0].items['text/plain']).text()); } } });
    try {
      let arrive!: (text: string) => void;
      const copied = frameClipboard.writeText(new Promise<string>(resolve => { arrive = resolve; }));
      expect(events).toEqual(['item', 'write']);
      arrive('File: /work/a.step');
      await copied;
      expect(events).toEqual(['item', 'write', 'File: /work/a.step']);
    } finally { vi.unstubAllGlobals(); }
  });

  it('copies by the page\'s copy command where the host grants the frame no clipboard, and fails only when that fails too', async () => {
    const details = ['File: /work/gear.step', 'Operation: loading geometry', 'Traceback (most recent call last):',
      ...Array.from({ length: 40 }, (_, line) => `  File "/work/gear.py", line ${line + 1}, in build`), 'ValueError: no teeth'].join('\n');
    // What the copy command would put on the clipboard: the selection in the focused field.
    const copied: string[] = [];
    const execCommand = vi.fn((command: string) => {
      const field = document.activeElement as HTMLTextAreaElement;
      copied.push(`${command}:${field.value.slice(field.selectionStart, field.selectionEnd)}`);
      return true;
    });
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand });
    const button = document.body.appendChild(document.createElement('button'));
    const refusing = { clipboard: { writeText: async () => { throw new DOMException('Write permission denied.', 'NotAllowedError'); } } };
    try {
      // Granted: the clipboard API, and nothing else.
      const written: string[] = [];
      vi.stubGlobal('navigator', { clipboard: { writeText: async (text: string) => { written.push(text); } } });
      await frameClipboard.writeText(details);
      expect([written, execCommand.mock.calls.length]).toEqual([[details], 0]);
      // Refused, or no clipboard API at all: the copy command takes the whole text, and leaves the
      // page as it was, its field gone and the focus back on the button pressed.
      vi.stubGlobal('navigator', refusing);
      button.focus();
      await frameClipboard.writeText(details);
      expect([copied, document.querySelector('textarea'), document.activeElement]).toEqual([[`copy:${details}`], null, button]);
      vi.stubGlobal('navigator', {});
      await frameClipboard.writeText('File: /work/a.step');
      await frameClipboard.writeText(Promise.resolve('File: /work/b.step'));
      expect(copied.slice(1)).toEqual(['copy:File: /work/a.step', 'copy:File: /work/b.step']);
      // Both refused: the copy fails, with the clipboard's refusal where there was one.
      execCommand.mockReturnValue(false);
      await expect(frameClipboard.writeText('File: /work/c.step')).rejects.toThrow('Copying is not available here.');
      vi.stubGlobal('navigator', refusing);
      await expect(frameClipboard.writeText('File: /work/c.step')).rejects.toThrow('Write permission denied.');
    } finally {
      vi.unstubAllGlobals();
      delete (document as { execCommand?: unknown }).execCommand;
      button.remove();
    }
  });
});
