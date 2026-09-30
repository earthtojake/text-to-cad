/**
 * The MCP Apps bridge: JSON-RPC 2.0 over postMessage with the frame that hosts this page.
 *
 * The page asks the host for things (`tools/call` to CAD's server, `ui/update-model-context`,
 * `ui/open-link`) and the host tells the page things: the result of the tool that opened it,
 * changes to its context (theme, insets, the composer's model context) and teardown.
 */

export interface HostContext {
  theme?: 'light' | 'dark';
  safeAreaInsets?: { top?: number; right?: number; bottom?: number; left?: number };
  locale?: string;
  platform?: string;
  [key: string]: unknown;
}

export interface ToolResult {
  content?: Array<{ type: string; text?: string; [key: string]: unknown }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

export interface CallOptions { signal?: AbortSignal; timeoutMs?: number }

export interface Bridge {
  readonly hostContext: HostContext;
  readonly hostCapabilities: Record<string, unknown>;
  request<T = unknown>(method: string, params?: Record<string, unknown>, options?: CallOptions): Promise<T>;
  notify(method: string, params?: Record<string, unknown>): void;
  callTool(name: string, args: Record<string, unknown>, options?: CallOptions): Promise<ToolResult>;
  /** The opening tool's result: delivered now if it already arrived, and again on each later one. */
  onToolResult(listener: (result: ToolResult) => void): () => void;
  onHostContext(listener: (context: HostContext) => void): () => void;
  onTeardown(listener: () => void): () => void;
}

export class HostError extends Error {
  constructor(message: string, readonly code?: number) { super(message); this.name = 'HostError'; }
}

interface Message { jsonrpc?: string; id?: string | number; method?: string; params?: any; result?: any; error?: { code?: number; message?: string } }
interface Pending { resolve(value: unknown): void; reject(error: Error): void; cleanup(): void }

const PROTOCOL_VERSION = '2026-01-26';

export function createBridge(host: Pick<Window, 'postMessage'>, self: Pick<Window, 'addEventListener' | 'removeEventListener'> = window): Bridge & { initialize(appInfo: { name: string; version: string }): Promise<void>; dispose(): void } {
  let nextId = 1;
  const pending = new Map<string | number, Pending>();
  const results = new Set<(result: ToolResult) => void>();
  const contexts = new Set<(context: HostContext) => void>();
  const teardowns = new Set<() => void>();
  let lastResult: ToolResult | undefined;
  let hostContext: HostContext = {};
  let hostCapabilities: Record<string, unknown> = {};

  const post = (message: Message) => host.postMessage({ jsonrpc: '2.0', ...message }, '*');
  const notify = (method: string, params?: Record<string, unknown>) => post({ method, ...(params ? { params } : {}) });

  function request<T>(method: string, params: Record<string, unknown> = {}, { signal, timeoutMs }: CallOptions = {}): Promise<T> {
    if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    const id = nextId++;
    return new Promise<T>((resolve, reject) => {
      const timer = timeoutMs ? setTimeout(() => fail(new HostError(`${method} timed out`)), timeoutMs) : undefined;
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
      for (const listener of [...teardowns]) listener();
      post({ id: message.id, result: {} });
    } else if (method === 'ping') post({ id: message.id, result: {} });
    else if (method === 'tools/list') post({ id: message.id, result: { tools: [] } });
    else post({ id: message.id, error: { code: -32601, message: `${method} is not supported` } });
  }

  function receive(event: MessageEvent) {
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
    async initialize(appInfo) {
      const result = await request<{ hostContext?: HostContext; hostCapabilities?: Record<string, unknown> }>('ui/initialize', {
        protocolVersion: PROTOCOL_VERSION, appInfo, appCapabilities: { availableDisplayModes: ['fullscreen'] },
      }, { timeoutMs: 15_000 });
      hostContext = { ...(result?.hostContext || {}) };
      hostCapabilities = result?.hostCapabilities || {};
      notify('ui/notifications/initialized');
      for (const listener of [...contexts]) listener(hostContext);
    },
    dispose() {
      self.removeEventListener('message', receive as EventListener);
      for (const waiting of [...pending.values()]) waiting.reject(new HostError('The page closed.'));
    },
  };
}
