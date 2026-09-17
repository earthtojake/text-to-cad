import type { TessellationCache } from '../lib/surf/cacheTypes.js';
export type { TessellationCache, TessellationCacheEntry, TessellationCacheProvider, TessellatedComponent, TessellationOptions } from '../lib/surf/cacheTypes.js';
export type CadJson = null | boolean | number | string | CadJson[] | { [key: string]: CadJson };
export interface CadEntry {
  file: string;
  rootRelativeFile?: string;
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
  rootId: string;
  autoReload?: boolean;
  identityToken?: string;
  rootPath?: string;
  rootDir?: string;
  backend?: string;
  [key: string]: unknown;
}
export interface CadCatalog { entries: CadEntry[]; rootId?: string; [key: string]: unknown }
export interface CadCatalogSnapshot {
  entries: CadEntry[];
  revision: number;
  hydrated: boolean;
  refreshing: boolean;
  error: string;
  rootId: string;
}
export interface CadRequestOptions { signal?: AbortSignal }
export interface CadArtifactResult {
  ok?: boolean;
  state: 'rendered' | 'not-compiled' | 'compiling' | 'failed';
  catalog?: CadCatalog;
  error?: string;
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
export interface CadSurfaceTicket { readonly surfaceInput: string; readonly surfaceObject: string; readonly surfUrl: string; readonly byteLength: number }
export interface CadSurfaceRequest {
  tree: string; viewId: string; producer: CadSurfaceProducer;
  components: {cid: string; surfaceInput: string; expectedSurfaceObject?: string}[];
  job?: string;
}
export interface CadSurfaceResponse {
  viewId: string; job?: string; replacementView?: CadRuntimeView;
  components: Record<string, {state: 'pending' | 'ready' | 'failed'; surfaceInput: string; surfaceObject?: string; url?: string; byteLength?: number; job?: string; error?: string; code?: string}>;
}
export interface CadPreviewGeometry {
  tree: string;
  url: string;
  kind?: string;
  revision?: number;
  sequence: number;
  kinematics?: CadJson;
  appearance?: CadJson;
  appearanceHash?: string;
  animation?: CadJson;
  animationHash?: string;
}
export interface CadSavedArtifact { tree: string; documentHash: string; revision?: number }
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
  previewUnavailable?: boolean;
  preview?: CadPreviewGeometry | null;
  saved?: CadSavedArtifact | null;
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
  readonly workspaceId: string;
  getSnapshot(): CadCatalogSnapshot;
  subscribe(listener: () => void): () => void;
  refresh(options?: CadRequestOptions & {file?: string;markRefreshing?: boolean}): Promise<CadCatalog>;
  resolveEntry(path: string, options?: CadRequestOptions): Promise<CadEntry>;
  serverInfo(options?: CadRequestOptions & { fresh?: boolean }): Promise<CadServerInfo>;
  requestArtifactStatus(file: string, options?: CadRequestOptions): Promise<CadArtifactResult>;
  requestArtifact(file: string, options?: CadRequestOptions & {force?: boolean}): Promise<CadArtifactResult>;
  readonly resources: CadResourceProvider;
  resolveSurfaceComponents(view: CadRuntimeView, requested: CadSurfaceComponentRequest[], options?: CadRequestOptions): Promise<Map<string, CadSurfaceTicket>>;
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
  workspaceId?: string;
  fetch?: typeof globalThis.fetch;
  pollIntervalMs?: number;
  /** Host visibility policy, evaluated at each polling interval. */
  shouldPoll?: () => boolean;
}
