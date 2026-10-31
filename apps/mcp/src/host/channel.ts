import { HostError } from './bridge';

/**
 * Whether a host says it carries an app's `tools/call` to the app's server: the `serverTools` its
 * `ui/initialize` answer's `hostCapabilities` names (MCP Apps). Every call this page makes to CAD's
 * server is one: its sync, its captures, and every viewer request (`cad_http`).
 */
export function declaresServerTools(capabilities: Record<string, unknown>): boolean {
  const tools = capabilities.serverTools;
  return typeof tools === 'object' && tools !== null;
}

/** Whether a host says it opens links (`hostCapabilities.openLinks`, `ui/open-link`). */
export function declaresOpenLinks(capabilities: Record<string, unknown>): boolean {
  const links = capabilities.openLinks;
  return typeof links === 'object' && links !== null;
}

/**
 * A host's own refusal of a request: an error it answered with -- not a timeout, and not an answer
 * of CAD's server, which comes back as a result. The Claude app's Code tab draws CAD cards but
 * answers each of their `tools/call` so ("IPC not available for MCP tool call").
 */
export function isHostRefusal(error: unknown): boolean {
  return error instanceof HostError && error.kind === 'refused';
}

/**
 * The way from this page to CAD's server, as far as its calls have shown it:
 *
 * - `unknown`: nothing said either way yet (a host that did not declare `serverTools`);
 * - `open`: the host carries the calls -- it said so, or one came back with the server's answer;
 * - `none`: the host refused a call before any came back. It never carried one, so it carries none:
 *   this chat has no channel to the server, and restarting the plugin changes nothing.
 *
 * Once a call has come back, a later refusal is the plugin stopping (its process gone), which the
 * view's sync tells (`host/sync.ts`): the channel stays `open`.
 */
export type ChannelState = 'unknown' | 'open' | 'none';

export interface Channel {
  readonly state: ChannelState;
  /** A call came back with the server's answer, whatever it said. */
  answered(): void;
  /** The host refused a call itself (`isHostRefusal`). */
  refused(): void;
  subscribe(listener: (state: ChannelState) => void): () => void;
}

export function createChannel(declared: boolean): Channel {
  let state: ChannelState = declared ? 'open' : 'unknown';
  let answered = false;
  const listeners = new Set<(state: ChannelState) => void>();
  const become = (next: ChannelState) => {
    if (next === state) return;
    state = next;
    for (const listener of [...listeners]) listener(state);
  };
  return {
    get state() { return state; },
    answered() { if (state === 'none') return; answered = true; become('open'); },
    refused() { if (!answered) become('none'); },
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
}
