import { describe, expect, it, vi } from 'vitest';
import { createPromptContext, referencePart } from '@text-to-cad/core/prompt';
import { createBridge, type ToolResult } from './bridge';
import { watchViewEvents } from './events';
import { createCatalogSource, createFilesystemSource } from './files';
import { createComposerPromptContext } from './prompt';
import { createServer, type ViewEvent } from './server';
import { createTunnelFetch, decodeBase64, encodeBase64, TUNNEL_ORIGIN } from './tunnel';

/** A host frame: records what the page posts and answers with `respond`. */
function fakeHost(respond: (message: any) => unknown) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const posted: any[] = [];
  const deliver = (data: unknown) => { for (const listener of [...listeners]) listener({ data } as MessageEvent); };
  const host = {
    postMessage(message: any) {
      posted.push(message);
      if (message.id === undefined || message.method === undefined) return;
      const result = respond(message);
      if (result !== undefined) queueMicrotask(() => deliver({ jsonrpc: '2.0', id: message.id, result }));
    },
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
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: { launch: { page: 'home' } } } });
    const seen: ToolResult[] = [];
    bridge.onToolResult(result => seen.push(result));
    expect(seen[0].structuredContent).toEqual({ launch: { page: 'home' } });
    frame.deliver({ jsonrpc: '2.0', method: 'ui/notifications/host-context-changed', params: { theme: 'light' } });
    expect(bridge.hostContext.theme).toBe('light');
  });

  it('cancels an aborted request with the host and rejects it', async () => {
    const frame = fakeHost(() => undefined);
    const bridge = createBridge(frame.host, frame.self as any);
    const abort = new AbortController();
    const pending = bridge.callTool('cad_events', { view: 'v' }, { signal: abort.signal });
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

describe('the agent driving a view', () => {
  it('shows what the agent sends and answers its questions over the long-poll', async () => {
    const launch = { protocol: 1, page: 'viewer' as const, model: '/p/b.step', root: null, explore: true };
    const batches: ViewEvent[][] = [
      [{ seq: 1, type: 'show', launch }, { seq: 2, type: 'capture', requestId: 'c1' }, { seq: 3, type: 'describe', requestId: 'd1' }],
      [{ seq: 4, type: 'capture', requestId: 'c2' }],
    ];
    const polls: unknown[][] = [];
    const replies: unknown[] = [];
    const server = {
      events: (...args: any[]) => {
        polls.push(args.slice(0, 3));
        const batch = batches.shift();
        // Past the scripted events, the poll waits, as the server's does, until the view goes.
        return batch ? Promise.resolve(batch) : new Promise<ViewEvent[]>((_, reject) => args[3].signal.addEventListener('abort', () => reject(new Error('aborted'))));
      },
      reply: async (requestId: string, reply: object) => { replies.push({ requestId, ...reply }); },
    };
    const shown: unknown[] = [];
    const captures = [new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })];
    const stop = new AbortController();
    watchViewEvents(server as any, { id: 'v1', surface: 'tab', model: () => '/p/a.step' }, {
      show: next => shown.push(next.model),
      capture: async () => { const png = captures.shift(); if (!png) throw new Error('nothing to capture'); return png; },
      describe: () => ({ model: '/p/a.step', selection: ['/p/a.step#o1.f2'] }),
    }, stop.signal);
    await vi.waitFor(() => expect(replies).toHaveLength(3));
    stop.abort();
    expect(shown).toEqual(['/p/b.step']);
    expect(polls[0]).toEqual(['v1', 'tab', '/p/a.step']);
    expect(replies).toEqual(expect.arrayContaining([
      { requestId: 'c1', png: encodeBase64(new Uint8Array([1, 2, 3])) },
      { requestId: 'd1', state: { model: '/p/a.step', selection: ['/p/a.step#o1.f2'] } },
      { requestId: 'c2', error: 'nothing to capture' },
    ]));
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
    });
    const tunnel = createTunnelFetch(server, { kind: 'workspace', path: '/project' });
    const posted = await tunnel(`${TUNNEL_ORIGIN}/__cad/surfaces?x=1`, { method: 'POST', headers: { 'x-cadgen-viewer': '1' }, body: '{"a":1}' });
    expect(calls[0]).toMatchObject({ name: 'cad_http', args: { root: { kind: 'workspace', path: '/project' }, method: 'POST', url: `${TUNNEL_ORIGIN}/__cad/surfaces?x=1` } });
    expect(calls[0].args.headers['x-cadgen-viewer']).toBe('1');
    expect(new TextDecoder().decode(decodeBase64(calls[0].args.body))).toBe('{"a":1}');
    expect(posted.status).toBe(201);
    expect(await posted.json()).toEqual({ ok: true });
    const head = await tunnel(`${TUNNEL_ORIGIN}/__cad/asset?file=a`, { method: 'HEAD' });
    expect([head.status, head.headers.get('content-length'), await head.text()]).toEqual([200, '11', '']);
  });

  it('turns a failed call into the TypeError fetch throws', async () => {
    const tunnel = createTunnelFetch(createServer({ callTool: async () => ({ isError: true, content: [{ type: 'text', text: 'not this thread' }] }) }), { kind: 'workspace', path: '/p' });
    await expect(tunnel(`${TUNNEL_ORIGIN}/__cad/catalog`)).rejects.toThrow(TypeError);
  });
});

describe('a filesystem, a folder at a time', () => {
  it('reads a folder through the tunnel, keeps the way to the open file, and ignores the file on screen changing', async () => {
    const asked: string[] = [];
    const fetchFolder = (async (input: RequestInfo | URL) => {
      asked.push(String(input));
      return new Response(JSON.stringify({ entries: [{ name: 'b.stl', kind: 'file', path: 'Users/me/b.stl' }, { name: 'parts', kind: 'directory', path: 'Users/me/parts' }] }), { headers: { 'content-type': 'application/json' } });
    }) as typeof fetch;
    let entries: any[] = [{ file: '/Users/me/.work/a.step', rootRelativeFile: 'Users/me/.work/a.step', hash: '1' }];
    const listeners = new Set<() => void>();
    const changed = () => { for (const listener of [...listeners]) listener(); };
    const client = { getSnapshot: () => ({ entries, hydrated: true }), subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); } } as any;
    const source = createFilesystemSource(client, { kind: 'global', path: '/', name: '/' }, fetchFolder, { id: 'fs', explore: true, showing: () => 'Users/me/.work/a.step' });
    const signal = new AbortController().signal;
    const listed = await source.list!('Users/me', { signal });
    expect(asked).toEqual([`${TUNNEL_ORIGIN}/__cad/list?dir=Users%2Fme`]);
    // The hidden folder the open file is in, which no listing shows, is on the way to it.
    expect(listed.map(entry => [entry.path, entry.kind])).toEqual([['Users/me/.work', 'directory'], ['Users/me/parts', 'directory'], ['Users/me/b.stl', 'file']]);
    expect(await source.paths!({ signal })).toEqual(['Users/me/b.stl']);
    const seen: unknown[] = [];
    source.subscribe!(change => seen.push(change.changes));
    entries = [{ ...entries[0], hash: '2' }];
    changed();
    entries = [{ file: '/Users/me/b.stl', rootRelativeFile: 'Users/me/b.stl', hash: '1' }];
    changed();
    expect(seen).toEqual([[{ kind: 'content', path: 'Users/me/.work/a.step', revision: expect.any(String) }]]);
  });

  it('names its files absolutely in copied references, where a project names them by its own paths', () => {
    const client = { getSnapshot: () => ({ entries: [], hydrated: true }), subscribe: () => () => {} } as any;
    const fetchFolder = (async () => new Response('{}')) as typeof fetch;
    const filesystem = (path: string) => createFilesystemSource(client, { kind: 'global', path, name: path }, fetchFolder, { id: path, explore: true, showing: () => null });
    expect(filesystem('/').referencePath?.('Users/me/a.step')).toBe('/Users/me/a.step');
    expect(filesystem('C:\\').referencePath?.('work/a.step')).toBe('C:\\work\\a.step');
    // A project's catalog keeps the default: the path under its root.
    expect(createCatalogSource(client, { kind: 'workspace', path: '/project', name: 'project' }, { id: 'w', explore: true }).referencePath).toBeUndefined();
  });
});

describe('Add to prompt', () => {
  it('fills the composer with titled absolute references and the view, keeping earlier additions', async () => {
    const updates: any[] = [];
    let context: (value: any) => void = () => {};
    const port = createComposerPromptContext({
      hostContext: {},
      onHostContext: listener => { context = listener; return () => {}; },
      request: async (method: string, params: any) => { updates.push({ method, params }); return {}; },
    } as any, { resolvePath: resource => `/project/${resource.kind === 'workspace-file' ? resource.path : ''}` });
    expect(port.getSnapshot().kind).toBe('composer');
    const face = referencePart({ resource: { kind: 'workspace-file', workspaceId: 'w', path: 'parts/a.step' }, target: { kind: 'cad-selector', selectors: ['o1.f2'] } }, 'face');
    const png = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: 'image/png' });
    const first = await port.deliver(createPromptContext([face, { id: 'shot', kind: 'attachment', name: 'a-view.png', mimeType: 'image/png', content: png, about: ['face'] }]));
    expect(first.status).toBe('added');
    const [text, image] = updates[0].params.content;
    expect(updates[0].method).toBe('ui/update-model-context');
    expect(text).toEqual({ type: 'text', text: '/project/parts/a.step#o1.f2', _meta: { 'openai/title': 'o1.f2 · a.step' } });
    expect([image.type, image.mimeType, image._meta['openai/title']]).toEqual(['image', 'image/png', 'CAD view · a.step']);
    await port.deliver(createPromptContext([referencePart({ resource: { kind: 'workspace-file', workspaceId: 'w', path: 'b.stl' }, target: { kind: 'whole-resource' } })]));
    expect(updates[1].params.content.map((block: any) => block._meta['openai/title'])).toEqual(['o1.f2 · a.step', 'CAD view · a.step', 'b.stl']);
    // The host cleared the context (the message went out): the next addition starts afresh.
    context({ 'openai/modelContext': null });
    await port.deliver(createPromptContext([referencePart({ resource: { kind: 'workspace-file', workspaceId: 'w', path: 'c.stl' }, target: { kind: 'whole-resource' } })]));
    expect(updates[2].params.content).toHaveLength(1);
  });
});
