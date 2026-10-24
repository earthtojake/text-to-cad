export type CadJson = null | boolean | number | string | CadJson[] | { [key: string]: CadJson };
export interface CadEntry {
  /** The document's id (`cadgen.engine.ids`): rows join by it, so one file is one row however its path is spelled. */
  id?: string;
  /** The file's absolute path, `/`-separated; a document known by its id alone (a model's): its id. */
  file: string;
  /** The document's name where its file does not give it (a model's function). */
  name?: string;
  /** The file to browse from; null for a document with no file of its own (a model's). */
  sourcePath?: string | null;
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
  /** The folder of the most recent launch (`cadgen viewer`), which the home shows. */
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
export interface CadConsent { sharing: boolean; reason: 'default' | 'untold' | 'choice' | 'environment' | 'unavailable'; policy: string; saved?: boolean }
/** A newer text-to-cad, as cadgen's version check says it (`/__cad/version`). */
export interface CadUpdateNotice { latest: string; version: string; text: string; prompt: string; instructions: string }
export interface CadCatalog {
  entries: CadEntry[];
  /** Why an id asked for has no row: the engine holds no such document (its words name the command that builds it again). */
  missing?: string;
  [key: string]: unknown;
}
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
  /** The last read failed because the engine is gone (`isEngineGone`); cleared by the next that answers. */
  engineGone: boolean;
  /** The server's digest of the last catalog applied ('' before one is): what a change watcher compares. */
  catalogRevision: string;
}
export interface CadRequestOptions { signal?: AbortSignal }
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
  layers: { name: string; color: string | null; entities: number }[];
  entities: { handle: string; type: string; layer: string; block?: string; center?: number[]; radius?: number }[];
  /** The faces `text` primitives are set in, which a `text` names by index. */
  fonts: { family: string; weight: number; italic: boolean }[];
  primitives: ({
    type: 'point' | 'lines' | 'path' | 'filled-paths' | 'filled-polygon';
    entity: string;
    layer: string;
    color: string | null;
    geometry: unknown;
  } | {
    type: 'text';
    entity: string;
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
 * What `GET /__cad/xbf` answers: the engine serving a cadgen engine document (`engine`, its origin),
 * the document's id there (`doc`) and its API URL (`url`, `<engine>/api/doc/<doc>`).
 */
/**
 * Where a page reads a document the cadgen engine serves (an `.xbf`, a STEP): its id, its API URL
 * through the viewer (`/__cad/api/doc/<id>`, on the client's origin), and the fetch every read
 * of it is made with (the client's own: the CAD app's travels over its tunnel).
 */
export interface CadEngineDocument {
  doc: string;
  url: string;
  fetch: typeof fetch;
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
  resolveDependency(source: string, reference: string): string;
  workerTicket(url: string, options?: CadResourceReadOptions): Promise<CadWorkerResourceTicket>;
}
export interface CadRenderSession {
  resources: CadResourceProvider;
  signal: AbortSignal;
  dispose(): void;
}
/** Domain service consumed by renderers; HTTP metadata stays on its adapter. */
export interface CadWorkspaceService {
  exports?: ExportService;
  getSnapshot(): CadCatalogSnapshot;
  subscribe(listener: () => void): () => void;
  refresh(options?: CadRequestOptions & {file?: string;markRefreshing?: boolean}): Promise<CadCatalog>;
  /** The row of a document, by its absolute path or its id, read when the catalog has none yet. */
  resolveEntry(path: string, options?: CadRequestOptions): Promise<CadEntry>;
  /** The row the catalog has of a document (its path, or its id), joined by the document's id; null when it has none. */
  entryOf?(path: string): CadEntry | null;
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
  /** The language the person chose for every CAD view, or null (Automatic); with `locale`, their choice (null clears it). */
  language(locale?: string | null): Promise<{ locale: string | null }>;
  /** Whether a newer text-to-cad is out: the update button's notice, or null. */
  version(): Promise<{ notice: CadUpdateNotice | null }>;
  /**
   * What the page did -- a person touched it, sent a Quick Edit, or the page crashed (`crashOf`) --
   * noted by the server and sent only with consent. Never fails.
   */
  reportActivity(activity: CadActivity): void;
  /** A `.dxf` flattened to 2D render primitives on the server; the client never parses DXF. */
  drawing(file: string, options?: CadRequestOptions): Promise<CadDrawingPayload>;
  /** `GET /__cad/robot`: a robot description resolved for the page (`cadgen.robot_payload`). */
  robot(file: string, options?: CadRequestOptions): Promise<CadRobotPayload>;
  /**
   * `GET /__cad/xbf`: where the page reads a document the cadgen engine serves (an `.xbf`, a STEP),
   * through this server (`lib/xbf/xbfDocument.js`), once the engine holds it. A host without an
   * engine leaves it out, and the xbf renderer says it cannot open the file.
   */
  engineDocument?(file: string, options?: CadRequestOptions): Promise<CadEngineDocument>;
  /** Whether the engine holds a read of the document now (`GET /__cad/xbf?held=1`), asked without starting one. */
  engineHolds?(file: string, options?: CadRequestOptions): Promise<boolean>;
  readonly resources: CadResourceProvider;
  createRenderSession(options?: { file?: string }): CadRenderSession;
  dispose(): void;
}
/** Reusable HTTP implementation, also used by existing catalog adapters. */
export interface CadClient extends CadWorkspaceService {
  readonly origin: string;
}
export interface CadClientOptions {
  resources?: CadResourceProvider;
  origin?: string;
  fetch?: typeof globalThis.fetch;
  pollIntervalMs?: number;
  /** Host visibility policy, evaluated at each polling interval. */
  shouldPoll?: () => boolean;
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

export type ExportFormat = 'step' | 'glb' | 'stl' | 'threemf' | 'dxf' | 'xbf' | 'original';
export interface ExportSource { doc: string; revision: string }
export interface ExportOption { format: ExportFormat; label: string; extension: string; reason: string | null }
export interface ExportRequest { requestId: string; epoch: string; source: ExportSource; format: ExportFormat }
export interface ExportJob {
  id: string; requestId: string; epoch: string; filename: string;
  state: 'queued' | 'running' | 'cancelling' | 'cancelled' | 'failed' | 'ready' | 'expired';
  stage: string; sequence: number; createdAt: number; finishedAt: number; expiresAt: number;
  bytes?: number; error?: string;
  /** Expired because the browser fetched the whole file (it is deleted then), not by its window. */
  fetched?: boolean;
}
export interface ExportService {
  options(source: ExportSource, signal: AbortSignal): Promise<{ epoch: string; formats: ExportOption[] }>;
  create(request: ExportRequest, signal?: AbortSignal): Promise<ExportJob>;
  status(id: string, sequence?: number, signal?: AbortSignal): Promise<ExportJob>;
  cancel(id: string): Promise<ExportJob>;
  release(id: string): Promise<ExportJob>;
  /** Where the browser downloads a ready job's file: the session's own origin, never a token. */
  fileUrl(id: string): string;
}
