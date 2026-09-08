/**
 * `cad-viewer/file-view` — the CAD Viewer's per-file surface.
 *
 * `apps/viewer` exports that entry as **source**: JSX in `.js` files, with no
 * types and no build step (`apps/viewer/docs/file-view.md`). This app's
 * bundler compiles it; the compiler needs to be told what it is.
 *
 * Declared narrowly on purpose — the props this app passes, and nothing else.
 * A `declare module "cad-viewer/file-view";` with no body would type the whole
 * surface as `any` and lose the one thing a declaration is for: catching a
 * prop that was renamed on the viewer's side.
 */
declare module "cad-viewer/file-view" {
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
     * `"desktop"` pins the desktop layout — the Inspector beside the model,
     * never a drawer over it — however narrow the pane; `"auto"` measures.
     */
    layout?: "auto" | "desktop";
    /** The Inspector's width in px, when the host sizes it; null for the surface's own. */
    fileSheetWidth?: number | null;
    /**
     * The element the open panel's content is drawn into. Given one, the
     * surface portals its theme editor / Inspector there and draws no
     * column of its own — this app's file tab has ONE panel column, shared
     * with its file tree, so the width, the border, the resize handle and
     * the toggle are the tab's (`features/explorer/FilePanel.tsx`).
     */
    panelSlot?: HTMLElement | null;
    /**
     * The host's resolved theme. Resolves the CAD "system" theme the same
     * way — its light/dark half, and the `--background` it paints the scene
     * on — and stops the surface writing `.dark` to the document, because
     * the host owns that. There is no backdrop prop: the surface reads this
     * app's token itself, and only for that one theme.
     */
    colorScheme?: "light" | "dark" | null;
    /**
     * Select a reference — `o1.2`, `label.f45`, a comma-separated list — once
     * the model is up. A new `key` selects again; null selects nothing.
     */
    selectReference?: { selector: string; key: number } | null;
    /**
     * A reference explicitly added to the prompt. Copy actions stay on the clipboard.
     * `file` is served-root-relative; `selector` is the half after `#`.
     */
    onReference?: (reference: { file: string; selector: string; text: string; label?: string }) => void;
    /** The viewport rendered to a PNG, from the toolbar's camera button (shown only when this is given). */
    onCapture?: (capture: { blob: Blob; file: string; references?: { file: string; selector: string; label?: string }[] }) => void;
    /**
     * The same capture, asked for from outside the viewport — this app's
     * composer has `Ask about this view` in its `+` menu. A new `key` takes
     * another picture; the result goes to `onCapture` either way.
     */
    captureRequest?: { key: number } | null;
    /**
     * The surface's two panels, driven from here and drawn into `panelSlot`.
     *
     * A boolean makes that panel controlled: the surface stops keeping its
     * own flag and reports every change through the matching callback,
     * including the one it makes itself — a measurement landing opens the
     * Inspector. `layout="desktop"` hides the surface's own top bar, so the
     * nav row's toggles are the only door this app has to them.
     */
    themeEditing?: boolean | null;
    onThemeEditingChange?: (next: boolean) => void;
    fileSheetOpen?: boolean | null;
    onFileSheetOpenChange?: (next: boolean) => void;
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

/**
 * `cad-viewer/shell` — the chrome AROUND a file surface.
 *
 * The nav row above a file, its breadcrumb, the menus that breadcrumb drops
 * down, the file icons and the panel toggles. This app and the standalone CAD
 * Viewer draw the same one, so it lives in the package they both depend on
 * rather than here — the dependency runs one way, and `apps/viewer` must
 * never import from this app.
 *
 * Source again, not a build — JSX in `.jsx`, plain modules in `.js` — so the
 * same narrow declaration applies: what this app imports and nothing else, so
 * a rename on the viewer's side is a type error here rather than a blank row.
 */
declare module "cad-viewer/shell" {
  import type { ComponentType, ElementType, ReactNode } from "react";

  export type CrumbKind = "directory" | "file" | "ellipsis";

  /** One crumb: a path segment BELOW the root, and the directory its menu lists. */
  export type Crumb = {
    kind: CrumbKind;
    label: string;
    title: string;
    path: string;
    /** The crumb's PARENT — the menu is its neighbours. Null only for the ellipsis. */
    menu: string | null;
    current: string | null;
    hidden: { label: string; path: string }[];
  };

  /** One row of a crumb's menu, in the crumb path space. */
  export type ListingEntry = {
    path: string;
    name: string;
    kind: "file" | "directory";
    /** The host's own payload, handed back on open. */
    value?: unknown;
  };

  /**
   * Where the breadcrumb's listings and entry menus come from — the one thing
   * the two hosts do not share. This app's is
   * `features/explorer/crumb-source.tsx`.
   */
  export type CrumbSource = {
    /**
     * One directory's entries, or null while they are on their way. Called as
     * a React hook, unconditionally, once per open menu.
     */
    useListing: (directory: string) => readonly ListingEntry[] | null;
    /** Wraps a crumb's trigger — the right-click entry menu. Never the ellipsis. */
    wrapCrumb?: (args: { crumb: Crumb; children: ReactNode }) => ReactNode;
    /** Drawn after the FILE crumb: the `⋯` that opens the same menu by click. */
    renderCrumbActions?: (args: { crumb: Crumb }) => ReactNode;
    /** Drawn INSTEAD of the file crumb while the host is renaming it; null draws the crumb. */
    renderRename?: (args: { crumb: Crumb }) => ReactNode;
  };

  export function buildCrumbs(input: { path: string | null; narrow: boolean }): Crumb[];

  /** The worktree a file is in, as a label rather than a crumb; null in the project. */
  export function worktreeMark(root: string | null): { label: string; title: string } | null;

  /** The directory an entry lives in: `""` at the root. */
  export function parentOf(path: string): string;

  export const Breadcrumbs: ComponentType<{
    crumbs: Crumb[];
    source: CrumbSource;
    activePath: string | null;
    onOpen: (path: string, entry: ListingEntry) => void;
  }>;

  /**
   * The row above a file: the breadcrumb, then whatever the host hangs off the
   * ends. `leading` sits inside the breadcrumb's overflow box and truncates
   * with it; `status` follows the last crumb; `trailing` is the right end and
   * never shrinks.
   */
  export const FileNavRow: ComponentType<{
    crumbs: Crumb[];
    source: CrumbSource;
    activePath: string | null;
    onOpen: (path: string, entry: ListingEntry) => void;
    leading?: ReactNode;
    status?: ReactNode;
    trailing?: ReactNode;
    className?: string;
  }>;

  /** One panel's toggle at the end of the nav row; `active` is its panel being open. */
  export const PanelToggle: ComponentType<{
    icon: ElementType;
    label: string;
    active: boolean;
    onClick: () => void;
    id?: string;
    testId?: string;
  }>;

  /**
   * A file's icon. The nine formats the CAD Viewer renders get its own
   * per-format glyphs; everything else is one lucide table.
   */
  export const FileIcon: ComponentType<{ path: string; className?: string }>;
  export const FolderIcon: ComponentType<{ open: boolean; className?: string }>;

  /** An element's width through a `ResizeObserver`; `0` until first measured. */
  export function useElementWidth(): [(element: HTMLElement | null) => void, number];
}

/** Small standalone entry; importing a loader must not eagerly load the CAD surface. */
declare module "cad-viewer/loading-icon" {
  import type { ReactElement } from "react";

  export default function LoadingIcon(props: {
    active?: boolean;
    size?: number;
    className?: string;
  }): ReactElement;
}
