import type { Bridge, CallOptions, ToolResult } from './bridge';

/**
 * The launch/view protocol this page speaks with `cadgen mcp` (its `PROTOCOL`). 2: every launch
 * names a root, the home's included, and the page reveals files (`cad_reveal`). 3: only the
 * sidebar has a home, and a launch browses only the thread's project.
 */
export const PROTOCOL = 3;

/** Where a view is: its project's catalog (`workspace`, browsed), or a filesystem holding only the file on screen (`global`). */
export interface Root { kind: 'workspace' | 'global'; path: string; name: string }
/** What an opening tool tells the page to show. The server decides all of it. */
export interface Launch {
  protocol: number;
  page: 'home' | 'viewer';
  surface?: string;
  model: string | null;
  /** Where the view browses, whether or not a model is open: the server always says. */
  root: Root;
  explore: boolean;
  /** A view mounted inline: its token (the agent names it by that) and its place among the chat's views. */
  view?: string;
  order?: { createdAt: number; seq: number };
}
export interface Session { protocol: number; build: string; version: string; platform: string; workspace: Root[] }
export interface Recent { path: string; name: string; folder: string; opened: number; modified: number | null; pinned: boolean; missing: boolean; thumbnail: string | null; pictured: number | null }
export type ViewEvent =
  | { seq: number; type: 'show'; launch: Launch }
  | { seq: number; type: 'capture' | 'describe'; requestId: string };
export interface HttpReply { status: number; headers: Record<string, string>; body: string }

export class ServerError extends Error {
  constructor(message: string) { super(message); this.name = 'ServerError'; }
}

const message = (result: ToolResult) => result.content?.find(part => part.type === 'text')?.text || 'CAD could not do that.';

export function readLaunch(result: ToolResult | undefined): Launch | null {
  const launch = result?.structuredContent?.launch as Launch | undefined;
  return launch && typeof launch === 'object' && (launch.page === 'home' || launch.page === 'viewer') ? launch : null;
}

/** CAD's server, as this page calls it through the host. */
export function createServer(bridge: Pick<Bridge, 'callTool'>) {
  async function call<T>(name: string, args: Record<string, unknown> = {}, options?: CallOptions): Promise<T> {
    const result = await bridge.callTool(name, args, options);
    if (result.isError) throw new ServerError(message(result));
    return (result.structuredContent || {}) as T;
  }
  return {
    session: (options?: CallOptions) => call<Session>('cad_session', {}, options),
    /** The newest release, as GitHub says it (the server asks at most every few hours), or null. */
    release: () => call<{ latest: { version: string; url: string; newer: boolean } | null }>('cad_release').then(value => value.latest),
    launch: (model: string) => call<{ launch: Launch }>('cad_launch', { model }).then(value => value.launch),
    pickModel: () => call<{ launch?: Launch; cancelled?: boolean }>('cad_pick_model', {}, { timeoutMs: 16 * 60_000 }),
    recents: (args: { action?: 'list' | 'pin' | 'unpin' | 'remove' | 'thumbnail'; path?: string; png?: string } = {}) =>
      call<{ recents: Recent[] }>('cad_recents', args).then(value => value.recents),
    thumbnails: (names: string[]) => call<{ thumbnails: Record<string, string> }>('cad_recents', { action: 'thumbnails', names }).then(value => value.thumbnails),
    events: (view: string, surface: string, model: string | null, options?: CallOptions) =>
      call<{ events: ViewEvent[] }>('cad_events', { view, surface, model }, options).then(value => value.events),
    report: (view: string, surface: string, model: string | null, state: Record<string, unknown>, focused: boolean) =>
      call('cad_view_report', { view, surface, model, state, focused }),
    reply: (requestId: string, reply: { png?: string; error?: string; state?: Record<string, unknown> }) =>
      call('cad_capture_reply', { requestId, ...reply }),
    http: (args: { root: Pick<Root, 'kind' | 'path'>; method: string; url: string; headers: Record<string, string>; body: string }, options?: CallOptions) =>
      call<HttpReply>('cad_http', args, options),
    /** Show a file of `root` in the desktop's file manager (the server runs on the person's machine). */
    reveal: (root: Pick<Root, 'kind' | 'path'>, path: string) => call('cad_reveal', { root: { kind: root.kind, path: root.path }, path }).then(() => {}),
  };
}
export type Server = ReturnType<typeof createServer>;
