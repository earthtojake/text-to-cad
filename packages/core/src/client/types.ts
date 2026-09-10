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
export interface CadRenderSession {
  tessellationCache: TessellationCache;
  signal: AbortSignal;
  dispose(): void;
}
export interface CadClient {
  readonly origin: string;
  readonly workspaceId: string;
  getSnapshot(): CadCatalogSnapshot;
  subscribe(listener: () => void): () => void;
  refresh(options?: CadRequestOptions & {file?: string;markRefreshing?: boolean}): Promise<CadCatalog>;
  resolveEntry(path: string, options?: CadRequestOptions): Promise<CadEntry>;
  serverInfo(options?: CadRequestOptions): Promise<CadServerInfo>;
  requestArtifactStatus(file: string, options?: CadRequestOptions): Promise<CadArtifactResult>;
  requestArtifact(file: string, options?: CadRequestOptions & {force?: boolean}): Promise<CadArtifactResult>;
  createRenderSession(): CadRenderSession;
  dispose(): void;
}
export interface CadClientOptions {
  origin?: string;
  workspaceId?: string;
  fetch?: typeof globalThis.fetch;
  pollIntervalMs?: number;
  /** Host visibility policy, evaluated at each polling interval. */
  shouldPoll?: () => boolean;
}
