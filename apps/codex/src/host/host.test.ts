import { describe, expect, it } from 'vitest';
import { createPromptContext, referencePart } from '@text-to-cad/core/prompt';
import { createBridge, type ToolResult } from './bridge';
import { createComposerPromptContext } from './prompt';
import { createServer } from './server';
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
