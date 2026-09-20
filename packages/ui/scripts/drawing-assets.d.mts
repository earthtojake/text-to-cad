/**
 * Types for the offline drawing-assets Vite plugin. Structural on purpose: the
 * consuming apps pin different Vite majors, so this names no `vite` type.
 */
export interface DrawingAssetFile {
  fileName: string;
  source: Buffer;
}

export interface DrawingAssetOptions {
  /** Tested against each emitted `fileName`; a match is neither served nor emitted. */
  exclude?: RegExp[];
}

interface DrawingFontOptimizerPlugin {
  name: string;
  setup(build: any): void;
}

interface DrawingFontRolldownPlugin {
  name: string;
  transform: {
    filter: { id: RegExp };
    handler(code: string): { code: string; map: null } | null;
  };
}

export interface DrawingAssetsPlugin {
  name: "hardcore-offline-drawing-assets";
  enforce: "pre";
  config(config?: unknown, env?: unknown): {
    optimizeDeps: {
      exclude?: string[];
      esbuildOptions?: { plugins: DrawingFontOptimizerPlugin[] };
      rolldownOptions?: { plugins: DrawingFontRolldownPlugin[] };
    };
  };
  buildStart(): void;
  transform(code: string, id: string): { code: string; map: null } | null;
  transformIndexHtml: {
    order: "post";
    handler(): { tag: string; attrs: Record<string, string>; injectTo: "head-prepend" }[];
  };
  configureServer(server: any): void;
  generateBundle(this: any): void;
}

export declare const DRAWING_ASSET_DIRECTORY: "excalidraw";
export declare const DRAWING_ASSET_BOOTSTRAP: "drawing-assets.js";
export declare const drawingAssetBootstrap: string;
export declare function drawingAssetFiles(options?: DrawingAssetOptions): DrawingAssetFile[];
/** `null` when the code is not the SDK's font chunk; throws when that chunk changed shape. */
export declare function localizeDrawingFontFallback(code: string): string | null;
export declare function drawingAssetsPlugin(options?: DrawingAssetOptions): DrawingAssetsPlugin;
