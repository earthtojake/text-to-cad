import { describe, expect, it, vi } from 'vitest';
import { createPromptContext, referencePart } from '@text-to-cad/core/prompt';
import { createBridge, HostError, type ToolResult } from './bridge';
import { watchViewEvents } from './events';
import { createCatalogFileSource } from '@text-to-cad/ui/catalog';
import { frameClipboard } from './clipboard';
import { createFilesystemSource } from './files';
import { chatReach, createChatPromptContext } from './prompt';
import { relaunch } from './relaunch';
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

describe('a tab restored from an older build', () => {
  it('is launched again as it was: the home, a thread\'s tab, a file\'s tab or an agent\'s model', async () => {
    const root = { kind: 'workspace' as const, path: '/work', name: 'work' };
    const calls: [string, Record<string, unknown>][] = [];
    const bridge = { callTool: vi.fn(async (name: string, args: Record<string, unknown>) => {
      calls.push([name, args]);
      return { structuredContent: { launch: { protocol: 3, page: name === 'cad_home' ? 'home' : 'viewer', model: (args.model as string) || null, root, explore: true } } } as ToolResult;
    }) };
    const stale = (patch: object) => ({ protocol: 2, page: 'viewer' as const, model: null, root, explore: true, ...patch });
    expect((await relaunch(bridge, stale({ page: 'home', surface: 'sidebar' }))).page).toBe('home');
    await relaunch(bridge, stale({ surface: 'tab' }));
    await relaunch(bridge, stale({ surface: 'file', model: '/work/parts/a b.step' }));
    const agent = await relaunch(bridge, stale({ surface: 'agent', model: '/work/parts/a.step' }));
    expect(calls).toEqual([
      ['cad_home', {}], ['cad_tab', {}],
      ['cad_file', { file: { name: 'a b.step', resourceUri: 'file:///work/parts/a%20b.step' } }],
      ['cad_launch', { model: '/work/parts/a.step' }],
    ]);
    expect([agent.protocol, agent.surface]).toEqual([3, 'agent']);
  });
});

describe('a filesystem, the file on screen alone', () => {
  it('lists nothing, and hears only the file that stayed change, not another file shown', async () => {
    let entries: any[] = [{ file: '/Users/me/.work/a.step', rootRelativeFile: 'Users/me/.work/a.step', hash: '1' }];
    const listeners = new Set<() => void>();
    const changed = () => { for (const listener of [...listeners]) listener(); };
    const client = { getSnapshot: () => ({ entries, hydrated: true }), subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); } } as any;
    const source = createFilesystemSource(client, { kind: 'global', path: '/', name: '/' }, { id: 'fs' });
    expect([source.list, source.paths]).toEqual([undefined, undefined]);
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
    const filesystem = (path: string) => createFilesystemSource(client, { kind: 'global', path, name: path }, { id: path });
    expect(filesystem('/').referencePath?.('Users/me/a.step')).toBe('/Users/me/a.step');
    expect(filesystem('C:\\').referencePath?.('work/a.step')).toBe('C:\\work\\a.step');
    // A project's catalog keeps the default: the path under its root.
    expect(createCatalogFileSource(client, { id: 'w', rootName: 'project' }).referencePath).toBeUndefined();
  });
});

describe('a Quick Edit in the chat', () => {
  const resolvePath = (resource: any) => `/project/${resource.kind === 'workspace-file' ? resource.path : ''}`;
  const file = referencePart({ resource: { kind: 'workspace-file', workspaceId: 'w', path: 'parts/a.step' }, target: { kind: 'whole-resource' } }, 'file');
  const face = referencePart({ resource: { kind: 'workspace-file', workspaceId: 'w', path: 'parts/a.step' }, target: { kind: 'cad-selector', selectors: ['o1.f2'] } }, 'face');
  const sketch = () => ({ id: 'sketch', kind: 'attachment' as const, name: 'a-sketch.png', label: 'Sketch', mimeType: 'image/png', about: ['file'],
    content: new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: 'image/png' }) });
  const edit = (...parts: any[]) => createPromptContext([{ id: 'text', kind: 'text', text: 'Round it.' }, file, ...parts]);

  it('reaches what the host declared: a tab host queues whatever it declares, and a picture rides in a message only where it takes images', () => {
    expect(chatReach({}, 'tabs')).toEqual({ queue: true, send: false, sendImages: false });
    expect(chatReach({ message: { text: {} } }, 'inline')).toEqual({ queue: false, send: true, sendImages: false });
    expect(chatReach({ updateModelContext: {}, message: { text: {}, image: {} } }, 'inline')).toEqual({ queue: true, send: true, sendImages: true });
  });

  it('queues into the composer as one titled message and its sketch, keeping what it queued until the host clears it', async () => {
    const updates: any[] = [];
    let context: (value: any) => void = () => {};
    const port = createChatPromptContext({
      hostContext: {},
      onHostContext: listener => { context = listener; return () => {}; },
      request: async (method: string, params: any) => { updates.push({ method, params }); return {}; },
    } as any, { resolvePath, reach: { queue: true, send: false, sendImages: false } });
    expect([port.getSnapshot().kind, port.send]).toEqual(['composer', undefined]);
    expect((await port.deliver(edit(face, sketch()))).status).toBe('added');
    const [text, image] = updates[0].params.content;
    expect(updates[0].method).toBe('ui/update-model-context');
    expect(text).toEqual({ type: 'text', text: 'Round it.\n\nFile: /project/parts/a.step\nReferences:\n/project/parts/a.step#o1.f2', _meta: { 'openai/title': 'Quick edit · a.step' } });
    expect([image.type, image.mimeType, image._meta['openai/title']]).toEqual(['image', 'image/png', 'Sketch · a.step']);
    await port.deliver(edit());
    expect(updates[1].params.content).toHaveLength(3);
    // The host cleared the context (the message went out): the next one starts afresh.
    context({ 'openai/modelContext': null });
    await port.deliver(edit());
    expect(updates[2].params.content).toHaveLength(1);
  });

  it('sends a message into the chat, its sketch as an image, or saved and named where the host refuses the image', async () => {
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
    const saved: string[] = [];
    const attachments = { save: async (_png: Blob, name: string) => { saved.push(name); return `/tmp/cadgen-sketches/${name}`; } };
    const port = createChatPromptContext(bridge, { resolvePath, reach: { queue: false, send: true, sendImages: true }, attachments });
    expect(port.getSnapshot().kind).toBe('unavailable');
    expect((await port.send!(edit(sketch()))).status).toBe('sent');
    expect(sent[0].method).toBe('ui/message');
    expect(sent[0].params.role).toBe('user');
    expect(sent[0].params.content.map((block: any) => block.type)).toEqual(['text', 'image']);
    expect(sent[0].params.content[0].text).toBe('Round it.\n\nFile: /project/parts/a.step');
    refuse = true;
    expect((await port.send!(edit(sketch()))).status).toBe('sent');
    expect(sent.at(-1).params.content).toEqual([{ type: 'text', text: 'Round it.\n\nFile: /project/parts/a.step\nSketch: /tmp/cadgen-sketches/a-sketch.png' }]);
    expect(saved).toEqual(['a-sketch.png']);
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
});
