import { describe, expect, it, vi } from 'vitest';
import { createArtifactBridge, createReplayMcp, openCad, replayKey, SERVER, unreachable, type ArtifactMcp } from './artifact';
import { HostError } from './bridge';

const LAUNCH = { protocol: 9, page: 'home', model: null };

/** An artifact's `mcp` capability: records each call and answers with `answer`. */
function fakeMcp(answer: (tool: string, input: unknown) => Promise<unknown> | unknown) {
  const calls: Array<{ server: string; tool: string; input: unknown; options: unknown }> = [];
  const mcp: ArtifactMcp = {
    async callTool(server, tool, input, options) {
      calls.push({ server, tool, input, options });
      return (await answer(tool, input)) as Awaited<ReturnType<ArtifactMcp['callTool']>>;
    },
  };
  return { mcp, calls };
}

const rejecting = (error: Record<string, unknown>) => () => Promise.reject(error);

describe('the artifact bridge', () => {
  it('calls CAD\'s server on this computer, uncached, and hands the app its answer', async () => {
    const { mcp, calls } = fakeMcp(() => ({ content: [{ type: 'text', text: 'ok' }], structuredContent: { status: 200 } }));
    const result = await createArtifactBridge(mcp).callTool('cad_http', { method: 'GET' });
    expect(result).toEqual({ content: [{ type: 'text', text: 'ok' }], structuredContent: { status: 200 } });
    expect(calls).toEqual([{ server: SERVER, tool: 'cad_http', input: { method: 'GET' }, options: { cache: false } }]);
  });

  it('reads a failure CAD\'s server answered as the result a host hands the app', async () => {
    const { mcp } = fakeMcp(rejecting({ code: 'tool_error', message: 'x', result: { content: [{ type: 'text', text: 'No file.' }], structuredContent: { refused: 'stale' } } }));
    expect(await createArtifactBridge(mcp).callTool('cad_sync', {})).toEqual({
      content: [{ type: 'text', text: 'No file.' }], structuredContent: { refused: 'stale' }, isError: true,
    });
  });

  it('says a call that cannot reach CAD from here is refused, and one that went unanswered timed out', async () => {
    for (const code of ['server_not_connected', 'not_in_manifest', 'cancelled']) {
      const failure = await createArtifactBridge(fakeMcp(rejecting({ code, message: code })).mcp).callTool('cad_home', {}).catch(error => error);
      expect(failure).toBeInstanceOf(HostError);
      expect([failure.kind, unreachable(failure)]).toEqual(['refused', true]);
    }
    const lapsed = await createArtifactBridge(fakeMcp(rejecting({ code: 'server_unavailable', retryable: true })).mcp).callTool('cad_sync', {}).catch(error => error);
    expect([lapsed.kind, unreachable(lapsed)]).toEqual(['timeout', false]);
  });

  it('keeps Queue\'s context for Send, which copies it with the message and starts again', async () => {
    const copied: string[] = [];
    const bridge = createArtifactBridge(fakeMcp(() => ({})).mcp, { copy: async text => { copied.push(text); } });
    await bridge.request('ui/update-model-context', { content: [{ type: 'text', text: 'face f:3' }] });
    await bridge.request('ui/message', { role: 'user', content: [{ type: 'text', text: 'make it 4 mm' }] });
    await bridge.request('ui/message', { role: 'user', content: [{ type: 'text', text: 'again' }] });
    expect(copied).toEqual(['face f:3\n\nmake it 4 mm', 'again']);
  });

  it('shows the message where the clipboard refuses it, and opens links outside the page', async () => {
    const show = vi.fn();
    const open = vi.fn();
    const bridge = createArtifactBridge(fakeMcp(() => ({})).mcp, { copy: () => Promise.reject(new Error('denied')), show, open });
    await bridge.request('ui/message', { content: [{ type: 'text', text: 'hi' }] });
    await bridge.request('ui/open-link', { url: 'http://127.0.0.1:3245/x' });
    expect([show.mock.calls, open.mock.calls]).toEqual([[['hi']], [['http://127.0.0.1:3245/x']]]);
    await expect(bridge.request('ui/download-file', {})).rejects.toBeInstanceOf(HostError);
  });

  it('follows the theme the artifact\'s viewer sets on the page', async () => {
    const bridge = createArtifactBridge(fakeMcp(() => ({})).mcp);
    const seen: string[] = [];
    bridge.onHostContext(context => seen.push(String(context.theme)));
    document.documentElement.dataset.theme = 'dark';
    await new Promise(resolve => setTimeout(resolve, 0));
    expect([seen, bridge.hostContext.theme]).toEqual([['dark'], 'dark']);
    delete document.documentElement.dataset.theme;
    bridge.dispose();
  });
});

describe('opening CAD from an artifact', () => {
  it('takes the page\'s capability from the launch\'s structured content where the result has no metadata', async () => {
    const { mcp } = fakeMcp(() => ({ content: [], structuredContent: { launch: LAUNCH, capability: 'cap' } }));
    const opened = await openCad(createArtifactBridge(mcp));
    expect([opened.launch, opened.result._meta]).toEqual([LAUNCH, { 'dev.texttocad/httpToken': 'cap' }]);
  });

  it('says what CAD answered where it gave no launch', async () => {
    const { mcp } = fakeMcp(rejecting({ code: 'tool_error', result: { content: [{ type: 'text', text: 'unknown tool' }] } }));
    await expect(openCad(createArtifactBridge(mcp))).rejects.toThrow('unknown tool');
  });
});

describe('the samples a page replays', () => {
  const reply = { status: 206, headers: { etag: '"a"' }, body: 'AAEC' };
  const recording = { home: { content: [], structuredContent: { launch: LAUNCH } },
    http: { [replayKey('GET', 'http://cad.invalid/api/v1/documents?path=', 'bytes=0-9')]: reply } };

  it('opens CAD on the recording, with a capability nothing checks', async () => {
    const opened = await openCad(createArtifactBridge(createReplayMcp(recording)));
    expect([opened.launch, opened.result._meta]).toEqual([LAUNCH, { 'dev.texttocad/httpToken': 'replay' }]);
  });

  it('answers a request it recorded, and what it never saw as missing or unchanged', async () => {
    const bridge = createArtifactBridge(createReplayMcp(recording));
    const ask = (method: string, url: string, range?: string) => bridge.callTool('cad_http', { method, url, headers: range ? { range, 'x-cad-app': 'x' } : {}, body: '' })
      .then(result => result.structuredContent);
    expect(await ask('GET', 'http://cad.invalid/api/v1/documents?path=', 'bytes=0-9')).toEqual(reply);
    expect(await ask('GET', 'http://cad.invalid/api/v1/settings')).toMatchObject({ status: 404 });
    expect(await ask('PATCH', 'http://cad.invalid/api/v1/documents')).toMatchObject({ status: 204 });
    expect((await bridge.callTool('cad_sync', {})).structuredContent).toEqual({ events: [] });
  });
});
