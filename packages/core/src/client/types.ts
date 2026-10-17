import type { PartRow, TessellationCache } from '../lib/parts/cacheTypes.js';
export type { PartRow, TessellationCache, TessellationCacheEntry, TessellationCacheProvider, TessellatedComponent } from '../lib/parts/cacheTypes.js';
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
export interface CadServerInfo {
  autoReload?: boolean;
  identityToken?: string;
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
 * five primitive shapes ezdxf reduces every entity to and its text, placed, in
 * DXF coordinates with y UP. `color: null` is the default pen, painted with the
 * theme's foreground; `bounds: null` is a drawing with nothing in it. See
 * `apps/web/docs/backend.md`.
 */
export interface CadDrawingPayload {
  schemaVersion: number;
  units: { insunits: number; name: string; toMillimetres: number };
  bounds: [number, number, number, number] | null;
  layers: { name: string; color: string | null; count: number }[];
  /** The faces `text` primitives are set in, which a `text` names by index. */
  fonts: { family: string; weight: number; italic: boolean }[];
  primitives: ({
    type: 'point' | 'lines' | 'path' | 'filled-paths' | 'filled-polygon';
    layer: string;
    color: string | null;
    geometry: unknown;
  } | {
    type: 'text';
    layer: string;
    color: string | null;
    text: string;
    font: number;
    /** Cap height, and the advance width the server measured, in the string's own units. */
    height: number;
    width: number;
    /** `[a, b, c, d, e, f]`: the string's space (baseline-left at the origin, y up) to the drawing's. */
    transform: [number, number, number, number, number, number];
  })[];
  [key: string]: unknown;
}
/**
 * What `GET /__cad/robot` answers: a URDF, SDF or SRDF resolved by cadgen into the articulation
 * the page plays (`common/articulation.js`), the visuals it draws (each at its rest placement,
 * with its colour and the URL of the mesh it draws), and what the description says about its
 * links and joints, as written. See `packages/cadgen/src/cadgen/robot_payload.py`.
 */
export interface CadRobotPayload {
  schemaVersion: number;
  kind: 'urdf' | 'sdf' | 'srdf';
  name: string;
  root: string;
  articulation: Record<string, unknown>;
  links: { name: string; placement: number[]; visuals: unknown[]; collisions: unknown[]; inertial: unknown }[];
  joints: Record<string, unknown>[];
  visuals: { id: string; link: string; label: string; placement: number[]; color: string; mesh: { format: string; url: string } }[];
  srdf: Record<string, unknown> | null;
  sdf: Record<string, unknown> | null;
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
  readBytes(url: string, options?: CadResourceReadOptions): Promise<ArrayBuffer>;
  byteLength(url: string, options?: CadRequestOptions): Promise<number | null>;
  resolveDependency(source: string, reference: string, options?: { kind?: 'relative' | 'package' }): string;
  workerTicket(url: string, options?: CadResourceReadOptions): Promise<CadWorkerResourceTicket>;
}
/** The kernel a view's parts are derived under: opaque to the page, which only forwards it. */
export interface CadProducer { producerKey?: string; [key: string]: unknown }
export interface CadRuntimeView {
  tree: string;
  viewId: string;
  producer: CadProducer;
  /** Each component names its part (`<digest>-v<version>`): the key its display data is read by. */
  components?: Record<string, {part: string; [key: string]: unknown}>;
  [key: string]: unknown;
}
export interface CadPartComponentRequest { cid: string; part: string }
export interface CadPartRequest {
  tree: string; viewId: string; producer: CadProducer;
  components: CadPartComponentRequest[];
  job?: string;
}
export interface CadMeasureRequest { tree: string; viewId: string; producer: CadProducer; cid: string; part: string; face: number }
export interface CadFaceMeasure { face: number; area: number; center: [number, number, number] }
export interface CadPartResponse {
  viewId: string; job?: string; replacementView?: CadRuntimeView;
  components: Record<string, {state: 'pending' | 'ready' | 'failed'; part: string; record?: Omit<PartRow, 'part'>; job?: string; error?: string; code?: string}>;
}
/**
 * A build's preview revision, as its feed names it the moment the result tree exists (cadgen's
 * `STORE.md` §9b): names of artifact-side objects a client reads as it reads any, never geometry.
 */
export interface CadEditingPreviewRevision {
  /** The result tree, read as any tree is: its view at `storeTreeUrl`. */
  tree: string;
  /** The producer its parts are keyed under; null when the build could not name them, and the view keys them as for a saved file. */
  producer: CadProducer | null;
  /** The components whose part the store holds, by cid: the stored parts first, then one more each time the build derives one. */
  parts: Record<string, string>;
  /** Whether every component's part is named; until then the missing ones are coming. */
  complete: boolean;
  /** The one object the build resolved its declarations into against `tree` (`previewAnnotations`), or null until it has. */
  annotations: string | null;
}
/**
 * What a build of a STEP file is doing, and the preview revision it announced: the viewer shows the
 * saved file, or that preview labelled as one until the file replaces it in place.
 */
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
  /** The file changed after this build finished: its failure and its preview are no longer the news. */
  superseded?: boolean;
  /** The preview revision: null before the build's result exists and for a superseded build. */
  preview?: CadEditingPreviewRevision | null;
  /**
   * The file the build saved, the moment it lands: the tree its bytes were written from and their
   * digest; null while it has written nothing. A build records its result and writes the file after.
   */
  saved?: { tree: string; documentHash: string } | null;
}
/**
 * A preview revision's annotations object (`GET /__cad/store?annotations=`): exactly the fields a
 * catalog row carries for a saved file, resolved against the preview's tree and keyed by its tokens.
 */
export interface CadPreviewAnnotations {
  kind: 'preview-annotations';
  schemaVersion: number;
  tree: string;
  articulation: Record<string, unknown> | null;
  appearance: CadJson;
  display: Record<string, Record<string, unknown>> | null;
  animation: Record<string, unknown> | null;
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
  /** `GET /__cad/robot`: a robot description resolved for the page (`cadgen.robot_payload`). */
  robot(file: string, options?: CadRequestOptions): Promise<CadRobotPayload>;
  readonly resources: CadResourceProvider;
  /**
   * Each component's part row: its record, which cadgen derives in one job for a part the store
   * lacks. `onReady` hears each component as soon as its row is ready, while the rest are still
   * awaited. `onFailed` hears each component cadgen could not derive or mesh, with its own error,
   * and the request resolves with the rest; without it, a failed component fails the request.
   */
  resolveParts(view: CadRuntimeView, requested: CadPartComponentRequest[],
    options?: CadRequestOptions & {
      onReady?: (cid: string, row: PartRow) => void;
      onFailed?: (cid: string, error: Error) => void;
    }): Promise<Map<string, PartRow>>;
  observeEditingPreview(file: string, onUpdate: (preview: CadEditingPreview) => void, onError: (error: unknown) => void, options?: CadPreviewObserverOptions): () => void;
  /**
   * Where a store tree's view is read, as a catalog row names a saved file's: `assembly.json` under
   * it, resolved as a package asset, with the producer its parts are keyed under (a build feed's
   * preview names both; with none, the view keys them as for a saved file).
   */
  storeTreeUrl(tree: string, options?: { producer?: CadProducer | null }): string;
  /** A preview revision's annotations object, or null for one the store does not hold. */
  previewAnnotations(object: string, options?: CadRequestOptions): Promise<CadPreviewAnnotations | null>;
  createRenderSession(options?: { file?: string }): CadRenderSession;
  dispose(): void;
}
/** Reusable HTTP implementation, also used by existing catalog adapters. */
export interface CadClient extends CadWorkspaceService {
  readonly origin: string;
  requestParts(body: CadPartRequest, options?: CadRequestOptions): Promise<CadPartResponse>;
  cancelPartRequest(body: { job: string }, options?: CadRequestOptions): Promise<{ok?: boolean}>;
  /** One face's exact area and centroid, measured by cadgen on its component's stored BREP. */
  measureFace(body: CadMeasureRequest, options?: CadRequestOptions): Promise<CadFaceMeasure>;
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
