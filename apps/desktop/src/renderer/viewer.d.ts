/**
 * `@viewer/file-view` — the CAD Viewer's per-file surface.
 *
 * `apps/viewer` exports that entry as **source**: JSX in `.js` files, with no
 * types and no build step (`apps/viewer/docs/file-view.md`). This app's
 * bundler compiles it; the compiler needs to be told what it is.
 *
 * Declared narrowly on purpose — the props this app passes, and nothing else.
 * A `declare module "@viewer/file-view";` with no body would type the whole
 * surface as `any` and lose the one thing a declaration is for: catching a
 * prop that was renamed on the viewer's side.
 */
declare module "@viewer/file-view" {
  import type { ComponentType, ReactNode } from "react";

  /**
   * `origin` is the `cadgen viewer --api-only` this surface talks to; `file`
   * is the served-root-relative path, the same value the standalone viewer
   * keeps in `?file=`. See the props table in the doc for the rest.
   */
  export const CadFileView: ComponentType<{
    origin?: string;
    file?: string;
    className?: string;
    manageDocumentTitle?: boolean;
    onOpenFile?: (path: string, meta: { history?: string }) => void;
    /**
     * `"desktop"` pins the desktop layout — the sheet beside the model, never
     * a drawer over it — however narrow the pane; `"auto"` measures.
     */
    layout?: "auto" | "desktop";
    /** The sheet's width in px, when the host sizes it; null for the surface's own. */
    fileSheetWidth?: number | null;
    /**
     * The host's resolved theme. Resolves the CAD "system" preset the same
     * way and stops the surface writing `.dark` to the document — the host
     * owns that.
     */
    colorScheme?: "light" | "dark" | null;
    /** Hex colour the scene is painted on, so the model sits on this app's ground. */
    sceneBackground?: string | null;
    /**
     * Select a reference — `o1.2`, `label.f45`, a comma-separated list — once
     * the model is up. A new `key` selects again; null selects nothing.
     */
    selectReference?: { selector: string; key: number } | null;
    /**
     * A reference the person copied from the surface — the render pane's
     * Copy Reference, the tree's, the sheet's, the file menu's Copy Link —
     * beside the clipboard. `file` is served-root-relative; `selector` is
     * the half after `#`, `""` for a whole file; `text` is what was copied.
     */
    onReference?: (reference: { file: string; selector: string; text: string; label?: string }) => void;
    /** The viewport rendered to a PNG, from the toolbar's camera button (shown only when this is given). */
    onCapture?: (capture: { blob: Blob; file: string }) => void;
    /**
     * The same capture, asked for from outside the viewport — this app's
     * composer has `Capture from viewer` in its `+` menu. A new `key` takes
     * another picture; the result goes to `onCapture` either way.
     */
    captureRequest?: { key: number } | null;
  }>;

  /** Publishes `origin` to the subtree; `useViewerOrigin` reads it back. */
  export const ViewerOriginProvider: ComponentType<{
    origin: string;
    children: ReactNode;
  }>;

  export function useViewerOrigin(): string;

  /** Absolute URL for a backend path, given the surface's origin. */
  export function viewerOriginUrl(origin: string, path: string): string;

  export function normalizeViewerOrigin(origin: string): string;
}
