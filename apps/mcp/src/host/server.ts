import type { CadEditingPreview } from '@text-to-cad/core/client';
import type { LibraryModel } from '@text-to-cad/ui/library';
import type { AnalyticsConsent, AnswerFrom } from '@text-to-cad/ui/consent';
import type { ViewerFeatures } from '@text-to-cad/ui/features';
import type { UpdateNotice } from '@text-to-cad/ui/update';
import type { Bridge, CallOptions, ToolResult } from './bridge';

/**
 * The launch/view protocol this page speaks with `cadgen mcp` (its `PROTOCOL`): a launch names a
 * model by its absolute path (`page: viewer`) or the home (`page: home`), and carries what the page
 * needs to start on it alone; a view makes one call a second (`cad_sync`).
 */
export const PROTOCOL = 5;

/** What an opening tool tells the page to show. The server decides all of it. */
export interface Launch {
  protocol: number;
  page: 'home' | 'viewer';
  surface?: string;
  /** The model, by its absolute path; null on the home. */
  model: string | null;
  /** The server's version and platform: the page starts on the launch alone. */
  version?: string;
  platform?: string;
  /** The home's library as it stood, so the home draws its cards without asking first. */
  recents?: Recent[];
  /** Whether this computer has a file chooser for the home's Open. */
  pick?: boolean;
  /** A view mounted inline: its token (the agent names it by that) and its place among the chat's views. */
  view?: string;
  order?: { createdAt: number; seq: number };
}
/** A model in the library every CAD view shares (`cad_recents`), as the home lists it. */
export type Recent = LibraryModel;
export type ViewEvent =
  | { seq: number; type: 'show'; launch: Launch }
  | { seq: number; type: 'capture'; requestId: string };
export interface HttpReply { status: number; headers: Record<string, string>; body: string }
/** A view's sync (`cad_sync`): what it says, and what comes back. */
export interface SyncRequest {
  view: string; surface: string; model: string | null;
  focused?: boolean; closed?: boolean; state?: Record<string, unknown>;
  watch?: { file: string; previews?: string[] };
}
export interface SyncReply {
  events: ViewEvent[];
  /** The watched file's catalog revision, or why it could not be read (the agent's requests come regardless). */
  catalog?: { revision?: string; error?: string };
  previews?: ({ file: string; error?: string } & CadEditingPreview)[];
}

/** Anonymous usage analytics (`cad_consent`): the shared card's and Settings toggle's state. */
export type { AnalyticsConsent as Consent } from '@text-to-cad/ui/consent';

export class ServerError extends Error {
  constructor(message: string) { super(message); this.name = 'ServerError'; }
}

/** What a tool result says, in its first text block, or `fallback`. */
export const toolText = (result: ToolResult, fallback = 'CAD could not do that.') =>
  result.content?.find(part => part.type === 'text')?.text || fallback;

export function readLaunch(result: ToolResult | undefined): Launch | null {
  const launch = result?.structuredContent?.launch as Launch | undefined;
  return launch && typeof launch === 'object' && (launch.page === 'home' || launch.page === 'viewer') ? launch : null;
}

/** CAD's server, as this page calls it through the host. */
export function createServer(bridge: Pick<Bridge, 'callTool'>) {
  async function call<T>(name: string, args: Record<string, unknown> = {}, options?: CallOptions): Promise<T> {
    const result = await bridge.callTool(name, args, options);
    if (result.isError) throw new ServerError(toolText(result));
    return (result.structuredContent || {}) as T;
  }
  return {
    /** Whether to ask the person about anonymous analytics; with `share`, their answer (`cadgen/analytics.py`). */
    consent: (share?: boolean, from?: AnswerFrom) => call<AnalyticsConsent>('cad_consent', share === undefined ? {} : { share, ...(from === 'card' ? { card: true } : {}) }),
    /** The app menu's features as the person left them; with `change`, their change of some (`cadgen/features.py`). */
    features: (change?: Partial<ViewerFeatures>) => call<ViewerFeatures>('cad_features', change ?? {}),
    /** Whether a newer text-to-cad is out (`cadgen/updates.py`): the update button's notice, or null. */
    version: () => call<{ notice: UpdateNotice | null }>('cad_version', {}),
    launch: (model: string) => call<{ launch: Launch }>('cad_launch', { model }).then(value => value.launch),
    pickModel: () => call<{ launch?: Launch; cancelled?: boolean }>('cad_pick_model', {}, { timeoutMs: 16 * 60_000 }),
    recents: (args: { action?: 'list' | 'pin' | 'unpin' | 'remove' | 'thumbnail'; path?: string; png?: string } = {}) =>
      call<{ recents: Recent[] }>('cad_recents', args).then(value => value.recents),
    thumbnails: (names: string[]) => call<{ thumbnails: Record<string, string> }>('cad_recents', { action: 'thumbnails', names }).then(value => value.thumbnails),
    /** This view's one call each second (`host/sync.ts`). */
    sync: (request: SyncRequest, options?: CallOptions) =>
      call<SyncReply>('cad_sync', request as unknown as Record<string, unknown>, options).then(value => ({ ...value, events: value.events || [] })),
    reply: (requestId: string, reply: { png?: string; error?: string }) =>
      call('cad_capture_reply', { requestId, ...reply }),
    http: (args: { method: string; url: string; headers: Record<string, string>; body: string }, options?: CallOptions) =>
      call<HttpReply>('cad_http', args, options),
    /** Show a file, by its absolute path, in the desktop's file manager (the server runs on the person's machine). */
    reveal: (path: string) => call('cad_reveal', { path }).then(() => {}),
  };
}
export type Server = ReturnType<typeof createServer>;
