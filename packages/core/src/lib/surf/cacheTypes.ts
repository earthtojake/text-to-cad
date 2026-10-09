/** The tolerances a stored mesh is keyed by: chord relative to the component's diagonal, angle in radians. */
export interface TessellationOptions {
  chordTolerance?: number;
  angleTolerance?: number;
}
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
  scale: number;
  /** The faces no mesher could cover: their ranges are empty and the mesh does not draw them. */
  unmeshedFaces: readonly number[];
}
export interface TessellationCacheEntry {
  component: TessellatedComponent;
  partColor: number[] | null;
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
  vertexCount: number;
  indexCount: number;
  faceCount: number;
  edgeCount: number;
  edgePointCount: number;
  /** How many faces the mesh leaves undrawn, no mesher having covered them; absent when none. */
  unmeshedFaceCount?: number;
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
  /** Mesh what the keys name and answer as a probe would; only a host that meshes on request offers it. */
  produceMany?(keys: string[], options?: { signal?: AbortSignal }): Promise<(TessellationProbe | null)[] | null>;
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
  probeCachedTessellationEntries(surfaceInputs: string[], options?: TessellationOptions, request?: TessellationReadOptions): Promise<Map<string, TessellationProbe>>;
  /** Ask the host to mesh the inputs a probe found missing; empty where the host cannot. */
  produceTessellationEntries(surfaceInputs: string[], options?: TessellationOptions, request?: TessellationReadOptions): Promise<Map<string, TessellationProbe>>;
  getCachedComponentEntry(surfaceInput: string, options?: TessellationOptions, request?: TessellationReadOptions): Promise<TessellationCacheEntry | null>;
  getCachedEntryBytes(surfaceInput: string, options?: TessellationOptions, request?: TessellationReadOptions): Promise<Uint8Array | null>;
  getCachedEntryBytesMany(probes: TessellationProbe[], request?: { signal?: AbortSignal; maxBytes?: number }): Promise<(Uint8Array | null)[] | null>;
  dispose(): void;
}
