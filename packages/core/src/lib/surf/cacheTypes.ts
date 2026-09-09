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
export interface TessellationCacheProvider {
  get(key: string): Promise<Uint8Array | null>;
  put?(key: string, bytes: Uint8Array): Promise<void>;
  getMany?(keys: string[]): Promise<(Uint8Array | null)[] | null>;
}
export interface TessellationCache {
  tessellationCacheProviderRegistered(): boolean;
  getCachedComponentEntry(cid: string, options?: TessellationOptions): Promise<TessellationCacheEntry | null>;
  getCachedComponentEntries(cids: string[], options?: TessellationOptions): Promise<Map<string, TessellationCacheEntry>>;
  primeCachedEntryBytes(cids: string[], options?: TessellationOptions): Promise<number>;
  clearPrimedEntries(): void;
  getCachedEntryBytes(cid: string, options?: TessellationOptions): Promise<Uint8Array | null>;
  configureTessellationCacheWriteBack(options?: { deferMs?: number; concurrency?: number }): void;
  flushTessellationCacheWriteBacks(): Promise<void>;
  writeBackEntryBytes(cid: string, options: TessellationOptions, bytes: Uint8Array): Promise<void>;
  writeBackComponentEntry(cid: string, options: TessellationOptions, component: TessellatedComponent, index: unknown): Promise<void>;
  tessellateComponentCached(index: unknown, floats: ArrayLike<number>, request?: { cid?: string; options?: TessellationOptions }): Promise<TessellatedComponent>;
  dispose(): void;
}
