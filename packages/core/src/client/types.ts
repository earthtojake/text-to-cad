import type { TessellationCache } from '../lib/surf/cacheTypes.js';
export type { TessellationCache, TessellationCacheEntry, TessellationCacheProvider, TessellatedComponent, TessellationOptions } from '../lib/surf/cacheTypes.js';
export type CadJson = null | boolean | number | string | CadJson[] | { [key: string]: CadJson };
export interface CadEntry {
  /** The file's absolute path, `/`-separated. */
  file: string;
  kind?: string;
  format?: string;
  sourceFormat?: string;
  renderFormat?: string;
  url?: string;
  hash?: string;
  bytes?: number;
  [key: string]: unknown;
}
/** cadgen's display tessellation ladder (`cadgen.tessellation_policy`): what each LOD rung means. */
export interface CadTessellationLadder {
  levels: { chordTolerance: number; angleTolerance: number }[];
  defaultLevel: number;
}
export interface CadServerInfo {
  autoReload?: boolean;
  identityToken?: string;
  /** The display tessellation ladder the page draws STEP models by. */
  tessellation?: CadTessellationLadder;
  /** The folder the server was started in, where a developer's relative `?file=` resolves. */
  start?: string;
  /** Whether this computer has a file chooser for the home's Open. */
  pick?: boolean;
  /** `darwin`, `win32` or `linux`: which file manager Reveal opens. */
  platform?: string;
  [key: string]: unknown;
}
/** A model in the library every CAD view shares (`GET /__cad/recents`): times in seconds. */
export interface CadRecent {
  path: string; name: string; folder: string; opened: number;
  /** When the file last changed; null once it is gone. */
  modified: number | null;
  pinned: boolean; missing: boolean;
  /** The picture's name, for `thumbnail()`, and when it was taken. */
  thumbnail: string | null; pictured: number | null;
}
/** Whether the person's usage stats are sent (`/__cad/analytics`; nothing asks): `reason` says who decided. */
export interface CadConsent { sharing: boolean; reason: 'default' | 'untold' | 'choice' | 'environment' | 'unavailable'; policy: string }
/** A newer text-to-cad, as cadgen's version check says it (`/__cad/version`). */
export interface CadUpdateNotice { latest: string; version: string; text: string; prompt: string; instructions: string }
export interface CadCatalog { entries: CadEntry[]; [key: string]: unknown }
/** One folder's subfolders and CAD files (`GET /__cad/folder`). */
export interface CadFolder { path: string; entries: { name: string; kind: 'directory' | 'file' }[]; truncated: boolean }
/** The CAD files nested under a folder whose path below it holds the query (`GET /__cad/search`). */
export interface CadSearch { path: string; results: string[]; truncated: boolean }
export interface CadCatalogSnapshot {
  entries: CadEntry[];
  revision: number;
  hydrated: boolean;
  refreshing: boolean;
  error: string;
  /** The server's digest of the last catalog applied ('' before one is): what a change watcher compares. */
  catalogRevision: string;
}
export interface CadRequestOptions { signal?: AbortSignal }
export interface CadArtifactResult {
  ok?: boolean;
  state: 'compiled' | 'not-compiled' | 'compiling' | 'failed';
  error?: string;
  [key: string]: unknown;
}
/**
 * What `GET /__cad/drawing` answers: a drawing's modelspace, flattened to the
 * five primitive shapes ezdxf reduces every entity to, in DXF coordinates with
 * y UP. `color: null` is the default pen, painted with the theme's foreground;
 * `bounds: null` is a drawing with nothing in it. See `apps/web/docs/backend.md`.
 */
export interface CadDrawingPayload {
  schemaVersion: number;
  units: { insunits: number; name: string; toMillimetres: number };
  bounds: [number, number, number, number] | null;
  layers: { name: string; color: string | null; count: number }[];
  primitives: {
    type: 'point' | 'lines' | 'path' | 'filled-paths' | 'filled-polygon';
    layer: string;
    color: string | null;
    geometry: unknown;
  }[];
  [key: string]: unknown;
}
/** Byte tickets own their buffer exclusively: workers may detach it. URL tickets are approved by the provider. */
export type CadWorkerResourceTicket =
  | { kind: 'url'; url: string; headers?: Record<string, string>; cache?: RequestCache; maxBytes?: number }
  | { kind: 'bytes'; bytes: ArrayBuffer };
export interface CadResourceReadOptions extends CadRequestOptions { maxBytes?: number }
export interface CadResourceProvider {
  /** Main-thread lifetime of the current resource generation; issued worker requests observe it too. */
  readonly signal?: AbortSignal;
  /** Stable within one immutable authorization/generation scope; change it when that scope changes. */
  cacheKey?(url: string): string;
  readJson(url: string, options?: CadRequestOptions): Promise<unknown>;
  readText(url: string, options?: CadRequestOptions): Promise<string>;
  readBytes(url: string, options?: CadResourceReadOptions): Promise<ArrayBuffer>;
  byteLength(url: string, options?: CadRequestOptions): Promise<number | null>;
  resolveDependency(source: string, reference: string, options?: { kind?: 'relative' | 'package' | 'robot' }): string;
  workerTicket(url: string, options?: CadResourceReadOptions): Promise<CadWorkerResourceTicket>;
}
export interface CadSurfaceProducer { scheme?: number; surfFormat?: number; producerKey?: string; [key: string]: unknown }
export interface CadRuntimeView {
  tree: string;
  viewId: string;
  surfaceProducer: CadSurfaceProducer;
  components?: Record<string, {surfaceInput: string; surfaceObject?: string; [key: string]: unknown}>;
  [key: string]: unknown;
}
export interface CadSurfaceComponentRequest { cid: string; surfaceInput: string; surfaceObject?: string }
/** One component's exact surface and, beside it, cadgen's selector table (the refs and facts the page joins to the mesh). */
export interface CadSurfaceTicket {
  readonly surfaceInput: string; readonly surfaceObject: string; readonly surfUrl: string; readonly byteLength: number;
  readonly selectorsObject: string; readonly selectorsUrl: string; readonly selectorsByteLength: number;
}
export interface CadSurfaceRequest {
  tree: string; viewId: string; producer: CadSurfaceProducer;
  components: {cid: string; surfaceInput: string; expectedSurfaceObject?: string}[];
  job?: string;
}
export interface CadSurfaceResponse {
  viewId: string; job?: string; replacementView?: CadRuntimeView;
  components: Record<string, {state: 'pending' | 'ready' | 'failed'; surfaceInput: string; surfaceObject?: string; url?: string; byteLength?: number; job?: string; error?: string; code?: string}>;
}
/** What a build of a STEP file is doing: status only. The viewer always shows the saved file. */
export interface CadEditingPreview {
  feedCursor?: string;
  feedLimited?: boolean;
  epoch?: string;
  revision?: number;
  state?: string;
  phase?: string;
  detail?: string;
  updatedAt?: number;
  error?: string;
  output?: string;
  file?: string;
  /** The file changed after this build finished: its failure is no longer the news. */
  superseded?: boolean;
}
export interface CadPreviewObserverOptions {
  schedule?: typeof globalThis.setTimeout;
  cancel?: typeof globalThis.clearTimeout;
}
export interface CadRenderSession {
  resources: CadResourceProvider;
  tessellationCache: TessellationCache;
  signal: AbortSignal;
  dispose(): void;
}
/** Domain service consumed by renderers; HTTP metadata stays on its adapter. */
export interface CadWorkspaceService {
  getSnapshot(): CadCatalogSnapshot;
  subscribe(listener: () => void): () => void;
  refresh(options?: CadRequestOptions & {file?: string;markRefreshing?: boolean}): Promise<CadCatalog>;
  resolveEntry(path: string, options?: CadRequestOptions): Promise<CadEntry>;
  serverInfo(options?: CadRequestOptions & { fresh?: boolean }): Promise<CadServerInfo>;
  folder(path: string, options?: CadRequestOptions): Promise<CadFolder>;
  search(path: string, query: string, options?: CadRequestOptions): Promise<CadSearch>;
  /** The home's library, newest first. */
  recents(options?: CadRequestOptions): Promise<CadRecent[]>;
  /** A change to the library (`open`, `pin`, `unpin`, `remove`, `thumbnail`): the library as it now is. */
  changeRecents(change: { action: 'open' | 'pin' | 'unpin' | 'remove' | 'thumbnail'; path: string; png?: string }): Promise<CadRecent[]>;
  /** Keep a model's picture in the library. */
  keepThumbnail(png: Blob, path: string): Promise<CadRecent[]>;
  /** A library picture, by the name the library gives it, as a data URL; null when there is none. */
  thumbnail(name: string, options?: CadRequestOptions): Promise<string | null>;
  /** Open: the model the person picks with the desktop's chooser, by its absolute path, or null. */
  pick(): Promise<string | null>;
  /** Show a file, by its absolute path, in the desktop's file manager. */
  reveal(path: string): Promise<void>;
  /** Whether the person's usage stats are sent; with `share`, their answer (the app menu's toggle). */
  consent(share?: boolean): Promise<CadConsent>;
  /** The features the person can turn off, as they left them; with `change`, their change of some. */
  features(change?: Record<string, boolean>): Promise<Record<string, boolean>>;
  /** Whether a newer text-to-cad is out: the update button's notice, or null. */
  version(): Promise<{ notice: CadUpdateNotice | null }>;
  /**
   * What the page did -- a person touched it, sent a Quick Edit, or the page crashed (`crashOf`) --
   * noted by the server and sent only with consent. Never fails.
   */
  reportActivity(activity: CadActivity): void;
  requestArtifactStatus(file: string, options?: CadRequestOptions): Promise<CadArtifactResult>;
  requestArtifact(file: string, options?: CadRequestOptions & {force?: boolean}): Promise<CadArtifactResult>;
  /** A `.dxf` flattened to 2D render primitives on the server; the client never parses DXF. */
  drawing(file: string, options?: CadRequestOptions): Promise<CadDrawingPayload>;
  readonly resources: CadResourceProvider;
  /**
   * `onReady` hears each component as soon as its row is ready, while the rest are still awaited.
   * `onFailed` hears each component cadgen could not derive or mesh, with its own error, and the
   * request resolves with the rest; without it, a failed component fails the request.
   * `tessellation` also has cadgen mesh each component at those tolerances.
   */
  resolveSurfaceComponents(view: CadRuntimeView, requested: CadSurfaceComponentRequest[],
    options?: CadRequestOptions & {
      onReady?: (cid: string, ticket: CadSurfaceTicket) => void;
      onFailed?: (cid: string, error: Error) => void;
      tessellation?: { chordTolerance?: number; angleTolerance?: number };
    }): Promise<Map<string, CadSurfaceTicket>>;
  observeEditingPreview(file: string, onUpdate: (preview: CadEditingPreview) => void, onError: (error: unknown) => void, options?: CadPreviewObserverOptions): () => void;
  createRenderSession(options?: { file?: string }): CadRenderSession;
  dispose(): void;
}
/** Reusable HTTP implementation, also used by existing catalog adapters. */
export interface CadClient extends CadWorkspaceService {
  readonly origin: string;
  requestSurfaces(body: CadSurfaceRequest, options?: CadRequestOptions): Promise<CadSurfaceResponse>;
  cancelSurfaceRequest(body: { job: string }, options?: CadRequestOptions): Promise<{ok?: boolean}>;
  editingPreview(file: string, options?: CadRequestOptions & { after?: string }): Promise<CadEditingPreview>;
}
export interface CadClientOptions {
  resources?: CadResourceProvider;
  origin?: string;
  fetch?: typeof globalThis.fetch;
  pollIntervalMs?: number;
  /** Host visibility policy, evaluated at each polling interval. */
  shouldPoll?: () => boolean;
  /**
   * A file's build feed, from a host that already hears it on a call it makes anyway: the
   * client then asks the preview route nothing. Returns the unsubscribe.
   */
  editingPreviewFeed?: (file: string, onUpdate: (preview: CadEditingPreview) => void, onError: (error: unknown) => void) => () => void;
  /**
   * The most bytes one batched read asks for over this client's `fetch`: a host whose channel
   * carries large replies slowly declares a ceiling, and reads that batch (a package's warm
   * tessellation bodies) stay within the lesser of it and the server's own bound
   * (`TESS_BATCH_MAX_BYTES`). Unset, the server's bound alone applies.
   */
  maxBatchBytes?: number;
}

/** A page's crash, as telemetry takes one (`crashOf`): never its message, a value or a URL. */
export interface CadPageCrash {
  where: 'page';
  /** The error's name, such as `TypeError`; `<?>` for one that is no plain name. */
  type: string;
  /** Whether the page went on: an error a view's boundary caught, not one that stopped it. */
  handled: boolean;
  /** Its innermost frames, oldest first: a script file's own name (or `<?>`), a function, a place, and for
   * one of the page's own chunks its debug id, by which PostHog finds the chunk's source map. */
  frames: { file: string; function: string; line: number; column: number; chunk_id?: string }[];
}

/** What `reportActivity` tells the page's server. */
export interface CadActivity {
  touched?: boolean;
  quickEdit?: boolean;
  crash?: CadPageCrash;
}
