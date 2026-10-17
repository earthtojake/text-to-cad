/**
 * One stored mesh's sections, viewed in place (`decodeComponentTessellation`): both tables are
 * u32 rows of four, faces (ord, indexStart, indexCount, colour: 0 for none, else a `faceColors`
 * row plus one) and edges (ord, pointStart, pointCount, class: a MESH_EDGE_CLASSES index).
 */
export interface TessellatedComponent {
  positions: Float32Array;
  normals: Float32Array;
  indices: Uint16Array | Uint32Array;
  faceTable: Uint32Array;
  edgeTable: Uint32Array;
  edgePoints: Float32Array;
  faceColors: number[][];
  bounds: { min: number[]; max: number[] };
  /** The faces no mesher could cover: their ranges are empty and the mesh does not draw them. */
  unmeshedFaces: readonly number[];
}
export interface TessellationCacheEntry {
  component: TessellatedComponent;
  /** The part the mesh is (`<digest>-v<version>`). */
  part: string;
}
/**
 * A part's record, by its key (cadgen/store/parts.py): its two objects -- the display mesh and the
 * selector table -- with what a reader sizes each by without opening it.
 */
export interface PartRow {
  part: string;
  glb: {
    object: string;
    byteLength: number;
    decodedBytes: number;
    vertexCount: number;
    indexCount: number;
    faceCount: number;
    edgeCount: number;
    edgePointCount: number;
    /** How many faces the mesh leaves undrawn, no mesher having covered them; absent when none. */
    unmeshedFaceCount?: number;
  };
  selectors: { object: string; byteLength: number; faceCount: number; edgeCount: number; vertexCount: number };
}
export interface TessellationReadOptions {
  signal?: AbortSignal;
  probe?: PartRow | null;
  strictProbe?: boolean;
}
export interface TessellationCacheProvider {
  probeMany(parts: string[], options?: { signal?: AbortSignal }): Promise<(PartRow | null)[] | null>;
  getProbed(row: PartRow, options?: { signal?: AbortSignal; maxBytes?: number }): Promise<Uint8Array | null>;
  getManyProbed?(rows: PartRow[], options?: { signal?: AbortSignal; maxBytes?: number }): Promise<(Uint8Array | null)[] | null>;
  /** The most framed bytes its transport carries in one batched read (`tessBatchMaxBytes`). */
  readonly maxBatchBytes?: number;
}
export interface TessellationCache {
  /**
   * The most framed bytes one `getCachedEntryBytesMany` may ask for: the server's bound, or the
   * lower ceiling its provider's transport declares (`tessBatchMaxBytes`).
   */
  readonly batchMaxBytes?: number;
  /** Borrow a cancellable view of this cache's reads. */
  createSession(options?: { signal?: AbortSignal }): TessellationCache;
  tessellationCacheProviderRegistered(): boolean;
  probeCachedTessellationEntries(parts: string[], request?: TessellationReadOptions): Promise<Map<string, PartRow>>;
  getCachedComponentEntry(part: string, request?: TessellationReadOptions): Promise<TessellationCacheEntry | null>;
  getCachedEntryBytes(part: string, request?: TessellationReadOptions): Promise<Uint8Array | null>;
  getCachedEntryBytesMany(rows: PartRow[], request?: { signal?: AbortSignal; maxBytes?: number }): Promise<(Uint8Array | null)[] | null>;
  dispose(): void;
}
