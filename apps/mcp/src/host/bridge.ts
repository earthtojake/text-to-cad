/**
 * The MCP Apps bridge: JSON-RPC 2.0 over postMessage with the frame that hosts this page.
 *
 * The page asks the host for things (`tools/call` to CAD's server, `ui/update-model-context`,
 * `ui/open-link`) and the host tells the page things: the result of the tool that opened it,
 * changes to its context (theme, insets, the composer's model context) and teardown.
 *
 * Only the host is heard: a message whose `source` is not the host's window is dropped, as the
 * MCP Apps SDK's own transport drops it (the host, or the sandbox frame it relays through, is the
 * page's parent). And the page's request ids start at a random number, so no other frame can
 * answer a request it did not see.
 */

export interface HostContext {
  theme?: 'light' | 'dark';
  displayMode?: 'inline' | 'fullscreen' | 'pip';
  availableDisplayModes?: string[];
  containerDimensions?: { width?: number; maxWidth?: number; height?: number; maxHeight?: number };
  safeAreaInsets?: { top?: number; right?: number; bottom?: number; left?: number };
  locale?: string;
  platform?: string;
  [key: string]: unknown;
}

/** The host, as it names itself at `ui/initialize` (`hostInfo`, MCP Apps): Codex, Claude, Cursor... */
export interface HostInfo { name?: string; version?: string }

export interface ToolResult {
  _meta?: Record<string, unknown>;
  content?: Array<{ type: string; text?: string; [key: string]: unknown }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

export interface CallOptions { signal?: AbortSignal; timeoutMs?: number }

export interface Bridge {
  readonly hostContext: HostContext;
  readonly hostCapabilities: Record<string, unknown>;
  /** What the host called itself at `ui/initialize`; empty before, and for a host that said nothing. */
  readonly hostInfo: HostInfo;
  request<T = unknown>(method: string, params?: Record<string, unknown>, options?: CallOptions): Promise<T>;
  notify(method: string, params?: Record<string, unknown>): void;
  callTool(name: string, args: Record<string, unknown>, options?: CallOptions): Promise<ToolResult>;
  /** The opening tool's result: delivered now if it already arrived, and again on each later one. */
  onToolResult(listener: (result: ToolResult) => void): () => void;
  onHostContext(listener: (context: HostContext) => void): () => void;
  onTeardown(listener: () => void): () => void;
}

/**
 * How a request to the host failed: `refused`, the host answered it with an error of its own (it
 * would not or could not carry it: the Claude app's Code tab answers every `tools/call` so); a
 * `timeout`, no answer in time; `closed`, the page went first.
 */
export type HostFailure = 'refused' | 'timeout' | 'closed';

export class HostError extends Error {
  constructor(message: string, readonly code?: number, readonly kind: HostFailure = 'refused') { super(message); this.name = 'HostError'; }
}

interface Message { jsonrpc?: string; id?: string | number; method?: string; params?: any; result?: any; error?: { code?: number; message?: string } }
interface Pending { resolve(value: unknown): void; reject(error: Error): void; cleanup(): void }

const PROTOCOL_VERSION = '2026-01-26';

/** A random first request id: 52 bits, so every id stays a safe integer for hosts that want numbers. */
function firstId(): number {
  const [high, low] = crypto.getRandomValues(new Uint32Array(2));
  return (high & 0xfffff) * 2 ** 32 + low + 1;
}

export function createBridge(host: Pick<Window, 'postMessage'>, self: Pick<Window, 'addEventListener' | 'removeEventListener'> = window): Bridge & {
  /** Greet the host. `displayModes` are the ones this page offers: a host that shows tabs is offered only fullscreen. */
  initialize(appInfo: { name: string; version: string }, options?: { displayModes?: string[] }): Promise<void>;
  dispose(): void;
} {
  let nextId = firstId();
  const pending = new Map<string | number, Pending>();
  const results = new Set<(result: ToolResult) => void>();
  const contexts = new Set<(context: HostContext) => void>();
  const teardowns = new Set<() => void>();
  let lastResult: ToolResult | undefined;
  let hostContext: HostContext = {};
  let hostInfo: HostInfo = {};
  let hostCapabilities: Record<string, unknown> = {};

  const post = (message: Message) => host.postMessage({ jsonrpc: '2.0', ...message }, '*');
  const notify = (method: string, params?: Record<string, unknown>) => post({ method, ...(params ? { params } : {}) });

  function request<T>(method: string, params: Record<string, unknown> = {}, { signal, timeoutMs }: CallOptions = {}): Promise<T> {
    if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    const id = nextId++;
    return new Promise<T>((resolve, reject) => {
      const timer = timeoutMs ? setTimeout(() => fail(new HostError(`${method} timed out`, undefined, 'timeout')), timeoutMs) : undefined;
      const abort = () => { notify('notifications/cancelled', { requestId: id }); fail(signal?.reason ?? new DOMException('Aborted', 'AbortError')); };
      const cleanup = () => { pending.delete(id); if (timer) clearTimeout(timer); signal?.removeEventListener('abort', abort); };
      const fail = (error: Error) => { cleanup(); reject(error); };
      pending.set(id, { resolve: value => { cleanup(); resolve(value as T); }, reject: fail, cleanup });
      signal?.addEventListener('abort', abort, { once: true });
      post({ id, method, params });
    });
  }

  function answer(message: Message) {
    const method = message.method!;
    if (method === 'ui/resource-teardown') {
      // Acknowledge first: the host is waiting to dispose the frame, and our cleanup
      // (ending the view's sync) is no reason to keep it waiting.
      post({ id: message.id, result: {} });
      for (const listener of [...teardowns]) {
        try { listener(); } catch { /* a listener's failure must not reach the host */ }
      }
    } else if (method === 'ping') post({ id: message.id, result: {} });
    else if (method === 'tools/list') post({ id: message.id, result: { tools: [] } });
    else post({ id: message.id, error: { code: -32601, message: `${method} is not supported` } });
  }

  function receive(event: MessageEvent) {
    if ((event.source as unknown) !== host) return; // another frame, or the page itself: not the host
    const message = event.data as Message;
    if (!message || typeof message !== 'object' || message.jsonrpc !== '2.0') return;
    if (message.method === undefined) {
      const waiting = message.id === undefined ? undefined : pending.get(message.id);
      if (!waiting) return;
      if (message.error) waiting.reject(new HostError(message.error.message || 'The host refused the request.', message.error.code));
      else waiting.resolve(message.result);
      return;
    }
    if (message.id !== undefined) { answer(message); return; }
    if (message.method === 'ui/notifications/tool-result') {
      lastResult = (message.params || {}) as ToolResult;
      for (const listener of [...results]) listener(lastResult);
    } else if (message.method === 'ui/notifications/host-context-changed') {
      hostContext = { ...hostContext, ...(message.params || {}) };
      for (const listener of [...contexts]) listener(hostContext);
    }
  }
  self.addEventListener('message', receive as EventListener);

  return {
    get hostContext() { return hostContext; },
    get hostInfo() { return hostInfo; },
    get hostCapabilities() { return hostCapabilities; },
    request,
    notify,
    callTool: (name, args, options) => request<ToolResult>('tools/call', { name, arguments: args }, options),
    onToolResult(listener) {
      results.add(listener);
      if (lastResult) listener(lastResult);
      return () => results.delete(listener);
    },
    onHostContext(listener) { contexts.add(listener); return () => contexts.delete(listener); },
    onTeardown(listener) { teardowns.add(listener); return () => teardowns.delete(listener); },
    async initialize(appInfo, { displayModes = ['fullscreen'] } = {}) {
      const result = await request<{ hostContext?: HostContext; hostCapabilities?: Record<string, unknown>; hostInfo?: HostInfo }>('ui/initialize', {
        protocolVersion: PROTOCOL_VERSION, appInfo, appCapabilities: { availableDisplayModes: displayModes },
      }, { timeoutMs: 15_000 });
      hostContext = { ...(result?.hostContext || {}) };
      hostCapabilities = result?.hostCapabilities || {};
      hostInfo = result?.hostInfo && typeof result.hostInfo === 'object' ? { ...result.hostInfo } : {};
      notify('ui/notifications/initialized');
      for (const listener of [...contexts]) listener(hostContext);
    },
    dispose() {
      self.removeEventListener('message', receive as EventListener);
      for (const waiting of [...pending.values()]) waiting.reject(new HostError('The page closed.', undefined, 'closed'));
    },
  };
}
