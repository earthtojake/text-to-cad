/**
 * The CAD app as a Claude artifact: a page claude.ai hosts that reaches CAD's server on the person's own
 * computer through the Claude app, and shows the engine's own CAD app, as the shell a host keeps does
 * (`host/shell.ts`).
 *
 * A Claude artifact calls MCP servers through its `mcp` capability (`claude.use('mcp')`), and a server
 * named `host:<name>` is one the Claude app runs on the viewer's computer: CAD's, as `cad mcp`. So this
 * page is the shell with another bridge: no MCP Apps host greets it or hands it a launch, so it opens CAD
 * itself (`cad_home`, as the Codex sidebar does), then reads the app through `cad_http` (`viaTunnel`) and
 * starts it on `globalThis.__cadShell` with this bridge. The app is the engine's release, so the page a
 * person keeps never has to match the cad they run.
 *
 * What a host would carry that an artifact cannot: the agent's chat. There is none beside the page, so a
 * Quick Edit's Queue keeps its context here and Send copies the message, to paste into the person's agent.
 */
import { HostError, type Bridge, type CallOptions, type HostContext, type ToolResult } from './bridge';
import { readLaunch, toolText, type Launch } from './server';
import type { CadShell } from './shell';

/** The server's name in the Claude app's MCP settings, as an artifact names a local one (`host:` and its name). */
export const SERVER = 'host:text-to-cad';
/** The tools this page calls: what its declaration grants (`declaration`), and no others. */
export const TOOLS = Object.freeze(['cad_home', 'cad_sync', 'cad_capture_reply', 'cad_http']);

/** What an artifact's `mcp` capability answers (the artifacts runtime's `Claude.mcp`), as far as this page uses it. */
export interface ArtifactMcp {
  callTool(server: string, tool: string, input?: unknown, options?: { cache?: false; signal?: AbortSignal }): Promise<{
    content?: ToolResult['content']; structuredContent?: unknown; _meta?: Record<string, unknown>;
  }>;
}

/** A rejection of `callTool` (the runtime's `McpError`): its `code` says what happened. */
interface McpError { code?: string; message?: string; result?: unknown }

/** Codes that say the call never reached CAD's server and will not now: no Claude app, no server, no consent. */
const UNREACHABLE = new Set(['server_not_connected', 'server_not_found', 'not_in_manifest', 'blocked_by_policy',
  'approval_required', 'not_granted', 'capability_disabled', 'capability_removed', 'selection_required', 'needs_reauth']);

/** Whether a failure says this page cannot reach CAD's server from here at all (the page's no-host screen). */
export function unreachable(error: unknown): boolean {
  return error instanceof HostError && error.kind === 'refused';
}

/** The artifact's theme: the `data-theme` the viewer sets on the page's root, else the system's. */
function themeOf(doc: Document, view: Pick<Window, 'matchMedia'> | undefined): 'light' | 'dark' {
  const set = doc.documentElement.dataset.theme;
  if (set === 'dark' || set === 'light') return set;
  return view?.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** The text a `ui/message` or `ui/update-model-context` carries (`host/prompt.ts`). */
const textOf = (content: unknown) => (Array.isArray(content) ? content : [])
  .flatMap(block => (block && typeof block === 'object' && typeof (block as { text?: unknown }).text === 'string' ? [(block as { text: string }).text] : []));

export interface ArtifactBridgeOptions {
  doc?: Document;
  view?: Window;
  /** Where Send puts the message for the person to paste: the clipboard, else `show` (the page's own dialog). */
  copy?: (text: string) => Promise<void>;
  /** The message, shown for the person to copy where the clipboard refused it. */
  show?: (text: string) => void;
  /** Open a link outside the page: an artifact opens an ordinary link's target in the person's browser. */
  open?: (url: string) => void;
}

/**
 * A bridge (`host/bridge.ts`) over an artifact's `mcp` capability: the calls go to CAD's server on this
 * computer, the context is the artifact's (its theme, the browser's locale), and the chat is the clipboard.
 */
export function createArtifactBridge(mcp: ArtifactMcp, options: ArtifactBridgeOptions = {}): CadShell['bridge'] {
  const doc = options.doc ?? document;
  const view = options.view ?? (typeof window === 'undefined' ? undefined : window);
  const contexts = new Set<(context: HostContext) => void>();
  const results = new Set<(result: ToolResult) => void>();
  const teardowns = new Set<() => void>();
  let lastResult: ToolResult | undefined;
  let queued: string[] = [];
  const context = (): HostContext => ({
    theme: themeOf(doc, view), displayMode: 'fullscreen', availableDisplayModes: ['fullscreen'],
    locale: view?.navigator?.language, platform: 'desktop',
  });
  let hostContext = context();
  const changed = () => {
    hostContext = context();
    for (const listener of [...contexts]) listener(hostContext);
  };
  const observer = typeof MutationObserver === 'function' ? new MutationObserver(changed) : null;
  observer?.observe(doc.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  view?.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', changed);
  const ended = () => { for (const listener of [...teardowns]) { try { listener(); } catch { /* the page is going */ } } };
  view?.addEventListener?.('pagehide', ended);

  const copy = options.copy ?? (async (text: string) => { await view!.navigator.clipboard.writeText(text); });
  const open = options.open ?? ((url: string) => {
    const link = doc.createElement('a');
    Object.assign(link, { href: url, target: '_blank', rel: 'noopener noreferrer' });
    link.click();
  });

  async function callTool(name: string, args: Record<string, unknown>, { signal, timeoutMs }: CallOptions = {}): Promise<ToolResult> {
    const deadline = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined;
    const signals = [signal, deadline].filter((each): each is AbortSignal => Boolean(each));
    const combined = signals.length > 1 ? AbortSignal.any(signals) : signals[0];
    try {
      const result = await mcp.callTool(SERVER, name, args, { cache: false, ...(combined ? { signal: combined } : {}) });
      return { content: result.content, structuredContent: result.structuredContent as ToolResult['structuredContent'],
        ...(result._meta ? { _meta: result._meta } : {}) };
    } catch (thrown) {
      const error = (thrown && typeof thrown === 'object' ? thrown : {}) as McpError;
      // CAD's server answered, and said it failed: a result the app reads, as a host hands it one.
      if (error.code === 'tool_error') return { ...((error.result as ToolResult) || {}), isError: true };
      if (signal?.aborted) throw signal.reason ?? new DOMException('Aborted', 'AbortError');
      if (deadline?.aborted) throw new HostError(`${name} timed out`, undefined, 'timeout');
      if (error.code && UNREACHABLE.has(error.code)) throw new HostError(error.message || error.code, undefined, 'refused');
      // The person declined the Claude app's confirmation of this call: it never ran, as a refusal.
      if (error.code === 'cancelled') throw new HostError(error.message || 'cancelled', undefined, 'refused');
      // Anything else (`server_unavailable`, `upstream_error`): no answer this time, as a host's timeout.
      throw new HostError(error.message || error.code || `${name} failed`, undefined, 'timeout');
    }
  }

  async function request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (method === 'ui/open-link' && typeof params.url === 'string') { open(params.url); return {} as T; }
    if (method === 'ui/request-display-mode') return { mode: 'fullscreen' } as T;
    // Queue: kept here for the next Send, as a host's composer keeps it for the next message.
    if (method === 'ui/update-model-context') { queued = textOf(params.content); return {} as T; }
    if (method === 'ui/message') {
      const text = [...queued, ...textOf(params.content)].join('\n\n');
      queued = [];
      try { await copy(text); } catch { options.show?.(text); }
      return {} as T;
    }
    throw new HostError(`${method} is not supported`, -32601);
  }

  const bridge: CadShell['bridge'] = {
    get hostContext() { return hostContext; },
    // `message`: Send is offered, and copies (`request`); `serverTools`: every call reaches CAD's server; `openLinks`.
    hostCapabilities: { serverTools: {}, message: {}, openLinks: {} },
    hostInfo: { name: 'Claude' },
    request,
    notify() {},
    callTool,
    onToolResult(listener) {
      results.add(listener);
      if (lastResult) listener(lastResult);
      return () => results.delete(listener);
    },
    onHostContext(listener) { contexts.add(listener); return () => contexts.delete(listener); },
    onTeardown(listener) { teardowns.add(listener); return () => teardowns.delete(listener); },
    async initialize() {},
    dispose() { observer?.disconnect(); view?.removeEventListener?.('pagehide', ended); },
  };
  return Object.assign(bridge, {
    /** Hand the app a tool's result, as a host hands it the one that opened the view. */
    deliver(result: ToolResult) {
      lastResult = result;
      for (const listener of [...results]) listener(result);
    },
  });
}

/**
 * Where the launch puts the page's capability for a page that cannot read a result's `_meta`: an artifact's
 * `callTool` answers a tool's content and structured content (`cad_server/mcp/server.py`'s artifact presentation).
 */
const CAPABILITY = 'capability';

/** CAD opened, as `cad_home` answers: its launch, and the result whose `_meta` carries the page's capability. */
export async function openCad(bridge: Pick<Bridge, 'callTool'>): Promise<{ launch: Launch; result: ToolResult }> {
  const result = await bridge.callTool('cad_home', {}, { timeoutMs: 60_000 });
  const launch = readLaunch(result);
  if (!launch) throw new Error(toolText(result, 'CAD could not open.'));
  const token = result.structuredContent?.[CAPABILITY];
  if (typeof token === 'string' && token && !result._meta?.['dev.texttocad/httpToken']) {
    return { launch, result: { ...result, _meta: { ...result._meta, 'dev.texttocad/httpToken': token } } };
  }
  return { launch, result };
}


/** One answer of the engine's routes, as `cad_http` answers it (`host/server.ts`'s `HttpReply`). */
interface Reply { status: number; headers: Record<string, string>; body: string; encoding?: string }

/**
 * CAD's answers to a page that opened some models, kept to be shown again where the page reaches no CAD (a
 * browser, or a Claude app with no CAD server): `cad_home`'s result, and each `cad_http` reply by its request
 * (`replayKey`). Its `/app` is the app of the engine that answered, so the replay is that release whole.
 */
export interface Recording { home: { content?: ToolResult['content']; structuredContent?: Record<string, unknown> }; http: Record<string, Reply> }

/**
 * A request as a recording knows it: its method, path and query, the range it asked, and a write's body where
 * the body is short (opening a document); a longer write (a thumbnail) is answered the same whatever it says.
 */
export function replayKey(method: string, url: string, range?: string, body?: string): string {
  const target = new URL(url);
  const write = method !== 'GET' && method !== 'HEAD' && body && body.length <= 256 ? ` ${body}` : '';
  return `${method} ${target.pathname}${target.search}${range ? ` ${range}` : ''}${write}`;
}

/**
 * An `mcp` capability that answers from a recording, never from a computer: the models it holds, as they were.
 * What it never recorded is not there (404); a write it never recorded changes nothing (204).
 */
export function createReplayMcp(recording: Recording): ArtifactMcp {
  return {
    async callTool(_server, tool, input) {
      // The page's capability: a recording keeps none, and nothing it answers asks for one.
      if (tool === 'cad_home') return { ...recording.home, structuredContent: { ...recording.home.structuredContent, capability: 'replay' } };
      if (tool === 'cad_sync') return { content: [], structuredContent: { events: [] } };
      if (tool !== 'cad_http') return { content: [], structuredContent: {} };
      const request = (input || {}) as { method?: string; url?: string; headers?: Record<string, string>; body?: string };
      const method = (request.method || 'GET').toUpperCase();
      const reply = recording.http[replayKey(method, request.url || 'http://cad.invalid/', request.headers?.range, request.body)];
      const none = { status: method === 'GET' || method === 'HEAD' ? 404 : 204, headers: {}, body: '' };
      return { content: [], structuredContent: reply ?? none };
    },
  };
}
