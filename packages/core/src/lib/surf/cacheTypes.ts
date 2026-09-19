export interface TessellationOptions {
  chordTolerance?: number;
  angleTolerance?: number;
  collectBoundaryDebug?: boolean;
  noSharedBoundaries?: boolean;
  noConformPass?: boolean;
  [key: string]: unknown;
}
export interface TessellatedComponent {
  positions: Float32Array;
  normals: Float32Array;
  faceOrds: Float32Array;
  indices: Uint32Array;
  sideOrds: Uint32Array;
  faceRanges: { ord: number; color: number[] | null; indexStart: number; indexCount: number }[];
  edges: { ord: number; visibilityClass?: string | null; polyline: Float32Array }[];
  bounds: { min: number[]; max: number[] };
  scale: number;
  [key: string]: unknown;
}
export interface TessellationCacheEntry {
  component: TessellatedComponent;
  partColor: number[] | null;
  edgeClasses: [number, string][] | null;
}
export interface TessellationProbe {
  schemaVersion: number;
  object: string;
  byteLength: number;
  decodedBytes: number;
  surfaceInput: string;
  surfaceObject: string;
  tessellationInput: string;
  renderIdentity: string;
  quality: TessellationOptions;
  tessellatorVersion: number;
  payloadVersion: number;
  headerBytes: number;
  arrayBytes: number;
  faceRangeCount: number;
  edgeCount: number;
  edgeClassCount: number;
  edgeSegmentCount: number;
}
export interface TessellationReadOptions {
  signal?: AbortSignal;
  probe?: TessellationProbe | null;
  strictProbe?: boolean;
}
export interface TessellationCacheProvider {
  probeMany(keys: string[], options?: { signal?: AbortSignal }): Promise<(TessellationProbe | null)[] | null>;
  getProbed(probe: TessellationProbe, options?: { signal?: AbortSignal; maxBytes?: number }): Promise<Uint8Array | null>;
  getManyProbed?(probes: TessellationProbe[], options?: { signal?: AbortSignal; maxBytes?: number }): Promise<(Uint8Array | null)[] | null>;
  put?(key: string, bytes: Uint8Array, options?: { signal?: AbortSignal }): Promise<unknown>;
}
export interface TessellationCache {
  /** Borrow a cancellable view; admitted write-backs remain owned by the parent cache. */
  createSession(options?: { signal?: AbortSignal }): TessellationCache;
  tessellationCacheProviderRegistered(): boolean;
  probeCachedTessellationEntries(surfaceInputs: string[], options?: TessellationOptions, request?: TessellationReadOptions): Promise<Map<string, TessellationProbe>>;
  getCachedComponentEntry(surfaceInput: string, options?: TessellationOptions, request?: TessellationReadOptions): Promise<TessellationCacheEntry | null>;
  getCachedEntryBytes(surfaceInput: string, options?: TessellationOptions, request?: TessellationReadOptions): Promise<Uint8Array | null>;
  getCachedEntryBytesMany(probes: TessellationProbe[], request?: { signal?: AbortSignal; maxBytes?: number }): Promise<(Uint8Array | null)[] | null>;
  configureTessellationCacheWriteBack(options?: { deferMs?: number; concurrency?: number; maxPendingBytes?: number }): void;
  flushTessellationCacheWriteBacks(): Promise<void>;
  writeBackEntryBytes(surfaceInput: string, options: TessellationOptions, bytes: Uint8Array): Promise<unknown>;
  writeBackComponentEntry(surfaceInput: string, surfaceObject: string, options: TessellationOptions, component: TessellatedComponent, index: unknown): Promise<unknown>;
  memoryStats(): { pendingWriteBackBytes: number; activeWriteBackBytes: number; writeBackBytes: number };
  dispose(): void;
}
