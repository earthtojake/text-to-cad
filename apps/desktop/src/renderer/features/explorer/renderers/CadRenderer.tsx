import { Box, RefreshCw, Settings2 } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import LoadingIcon from "cad-viewer/loading-icon";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { useExplorer } from "@renderer/state/explorer";
import { addToDraft } from "@renderer/state/cad-draft";
import { useUi } from "@renderer/state/ui";
import type { ViewerOrigin } from "@shared/ipc/cad";
import type { CadReference } from "@shared/cad-refs";
import type { ExplorerRoot } from "@shared/types";

import { EmptyState } from "../EmptyState";

/**
 * A CAD file, rendered by the CAD Viewer's own per-file surface.
 *
 * `CadFileView` is `apps/viewer`'s `./file-view` entry — the render pane, the
 * floating toolbar, the right-hand STEP/mesh/URDF/DXF sheets and the theme
 * panel — shipped as **source** and compiled by this app's bundler (see
 * `apps/viewer/docs/file-view.md`, and the aliases, JSX loader, `worker.format`
 * and `@source` line that `electron.vite.config.ts` and `globals.css` carry
 * for it). One implementation, two consumers: the standalone viewer's shell
 * and this tab.
 *
 * It is lazily imported. The closure is three.js and the whole viewer client;
 * a window that only ever opens a README should not pay for it at startup, and
 * `React.lazy` is what keeps it in its own chunk.
 *
 * The surface talks HTTP to a `cadgen viewer --api-only`, so it needs that
 * instance's origin; main spawns one per root — the project, or a worktree —
 * (`cad.viewerOrigin`).
 * The runtime that process runs in SHIPS INSIDE THE APP, so an answer with no
 * origin is a failure, never a first-run state: the card below shows the
 * runtime's or the launcher's own words, the log to read, and the two things
 * a person can do — try again, or go to About & Updates, where the runtime's
 * status and Repair live.
 *
 * Three things are the desktop's to decide, not the surface's, and are passed
 * in: WHERE its panels are drawn (`panelSlot` — the file tab's one panel
 * column, so the theme editor and the Inspector share the frame, the width
 * and the toggles of the tab's own panels), the layout (always the desktop
 * one, so nothing is ever a drawer over the model), and light/dark
 * (`colorScheme`, the app's theme — the CAD theme paints the scene and
 * nothing around it).
 *
 * `layout="desktop"` is a pin, not a measurement: the surface measures its
 * own root and drops into compact mode — the Inspector as a drawer over the
 * model — below 1024px, and every explorer pane is narrower than that. Its
 * panels are drawn in the tab's panel column, so their width is that
 * column's and this app has no other opinion about the layout.
 *
 * The scene's BACKDROP is not one of the three either. It belongs to the CAD
 * theme, and only the theme named "System" follows this window: the surface
 * reads the `--background` token off the document for that one and leaves
 * every other preset its own. This app used to hand the colour over for every
 * theme (a `sceneBackground` prop and a `cadSceneBackgroundFor` beside it),
 * which is why picking Cinematic here changed the lights and the floor but
 * never the background.
 */
type CadSurfaceProps = {
  origin: string;
  file: string;
  colorScheme: "light" | "dark";
  onOpenFile: (path: string) => void;
  /** A reference to select once the model is up; `key` distinguishes repeats. */
  selectReference: { selector: string; key: number } | null;
  onReference: (reference: { file: string; selector: string; text: string; label?: string }) => void;
  onCapture: (capture: { blob: Blob; file: string; references?: CadReference[] }) => void;
  /**
   * A capture requested by the host from outside the viewport.
   * `key` distinguishes repeats, exactly as `selectReference`'s does; the
   * picture goes to `onCapture` either way, so the toolbar's camera button
   * and this are one path.
   */
  captureRequest: { key: number } | null;
  /**
   * The surface's two panels, driven from here and drawn into `panelSlot`.
   *
   * `layout="desktop"` hides the surface's own top bar, which is where the
   * theme and Inspector toggles live standalone — so without these the
   * theme panel had no door at all in this app. They are controlled props
   * (`apps/viewer/docs/file-view.md`): the file tab has one open panel, so
   * at most one of these is ever true, and the surface reports the changes
   * it makes itself (a measurement opening the sheet) so the nav row's
   * highlight follows the screen.
   */
  themeEditing: boolean;
  onThemeEditingChange: (next: boolean) => void;
  fileSheetOpen: boolean;
  onFileSheetOpenChange: (next: boolean) => void;
  /**
   * The box in the tab's panel column the open panel is drawn into. Null —
   * the tab has another panel open, or none — and the surface draws no panel
   * at all, which is right: this app's column is showing something else.
   */
  panelSlot: HTMLElement | null;
};

/**
 * The surface plus its origin context.
 *
 * `CadFileView` provides `ViewerOriginProvider` for its own subtree already;
 * the outer one here is for the tab's chrome, so anything this app puts beside
 * the surface — a breadcrumb action that fetches a thumbnail, P5's `open_file`
 * plumbing — builds backend URLs from the same `useViewerOrigin()` the surface
 * does instead of threading the string by hand.
 */
const CadSurface = lazy(async () => {
  // Typed by src/renderer/viewer.d.ts — the entry is JSX-in-`.js` source with
  // no declarations of its own.
  const { CadFileView, ViewerOriginProvider } = await import("cad-viewer/file-view");
  return {
    default: ({
      origin,
      file,
      colorScheme,
      onOpenFile,
      selectReference,
      onReference,
      onCapture,
      captureRequest,
      themeEditing,
      onThemeEditingChange,
      fileSheetOpen,
      onFileSheetOpenChange,
      panelSlot,
    }: CadSurfaceProps) => (
      <ViewerOriginProvider origin={origin}>
        {/*
          A containing block for any `position: fixed` part of the surface
          that is still drawn inside it. Its panels are not — they are
          portaled into the tab's panel column — but a compact-mode drawer
          would be, and a transform on an ancestor makes a fixed descendant
          position against this box rather than the window, so nothing can
          pin itself over the tab strip. Popovers portal to `body` and are
          unaffected.
        */}
        <div className="relative h-full min-h-0" style={{ transform: "translateZ(0)" }}>
          <CadFileView
            // `min-h-0` beats the surface's own `min-h-svh`: the tab is shorter
            // than the window, and a surface that insists on the window's
            // height puts its bottom panels below the tab's edge.
            captureRequest={captureRequest}
            className="h-full min-h-0"
            colorScheme={colorScheme}
            file={file}
            fileSheetOpen={fileSheetOpen}
            layout="desktop"
            // The desktop window owns its own title; the surface must not write it.
            manageDocumentTitle={false}
            onCapture={onCapture}
            onFileSheetOpenChange={onFileSheetOpenChange}
            onOpenFile={(next) => onOpenFile(next)}
            onReference={onReference}
            onThemeEditingChange={onThemeEditingChange}
            origin={origin}
            panelSlot={panelSlot}
            selectReference={selectReference}
            themeEditing={themeEditing}
          />
        </div>
      </ViewerOriginProvider>
    ),
  };
});

export function CadRenderer({
  tabId,
  projectId,
  root,
  path,
  onOpenFile,
  themeEditing,
  onThemeEditingChange,
  fileSheetOpen,
  onFileSheetOpenChange,
  panelSlot,
  onSurfaceReady,
}: {
  tabId: string;
  projectId: string;
  /** The directory the viewer serves: the project, or the tab's worktree (plan §9). */
  root: ExplorerRoot;
  /** Root-relative: the same path the viewer's `?file=` carries. */
  path: string;
  onOpenFile: (path: string) => void;
  /**
   * The tab's two CAD panel toggles (`renderers/panels.ts`), driven into the
   * surface, which draws the open one into `panelSlot`.
   */
  themeEditing: boolean;
  onThemeEditingChange: (next: boolean) => void;
  fileSheetOpen: boolean;
  onFileSheetOpenChange: (next: boolean) => void;
  /** The tab's panel column, when the open panel is one of these two. */
  panelSlot: HTMLElement | null;
  /**
   * Whether the surface — the thing that draws those panels — is up at all.
   * False while the origin is being asked for and false for good if it never
   * came: the tab draws no panel toggles then, because there is nothing
   * behind them but a failure card.
   */
  onSurfaceReady: (ready: boolean) => void;
}) {
  const [answer, setAnswer] = useState<ViewerOrigin | null>(null);
  // A transcript link's `#selector` for this tab (`explorer.selectCadReference`).
  const selection = useExplorer((state) => (state.cadSelection?.tabId === tabId ? state.cadSelection : null));
  const selectReference = useMemo(
    () => (selection ? { selector: selection.selector, key: selection.nonce } : null),
    [selection],
  );
  // A host-requested capture for this tab.
  const capture = useExplorer((state) => (state.cadCapture?.tabId === tabId ? state.cadCapture : null));
  const captureRequest = useMemo(() => (capture ? { key: capture.nonce } : null), [capture]);

  /**
   * The viewer's prompt references and captures go to the composer of the thread the
   * person is in — or the new-session box when there is none — as a chip
   * and as an image attachment (`state/composer.ts`). `file` is the tab's
   * root-relative path, which is what the agent can open.
   */
  const onReference = useCallback((reference: { file: string; selector: string; label?: string }) => {
    addToDraft(projectId, root, { references: [reference] });
  }, [projectId, root]);
  const onCapture = useCallback(({ blob, file, references }: { blob: Blob; file: string; references?: CadReference[] }) => {
    const stem = (file.split("/").pop() ?? "view").replace(/\.[^.]+$/, "");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    addToDraft(projectId, root, { references, files: [new File([blob], `${stem}-${stamp}.png`, { type: "image/png" })] });
  }, [projectId, root]);
  const openSettings = useUi((state) => state.openSettings);
  const colorScheme = useResolvedTheme();

  // Asked once per mount, and again on Retry. A tab's project cannot change
  // under it — a project change rebuilds the strip — so there is nothing
  // else to reset here.
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setAnswer(null);
    setAttempt((count) => count + 1);
  }, []);
  useEffect(() => {
    let cancelled = false;
    void window.hardcore.cad
      .viewerOrigin({ projectId, ...(root ? { root } : {}) })
      .then((result) => {
        if (!cancelled) {
          setAnswer(result);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setAnswer({ origin: null, reason: "viewer-failed", message: error instanceof Error ? error.message : String(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, root, attempt]);

  // The panels exist exactly while the surface does. Reported rather than
  // derived by the tab, because "did the viewer come up" is this component's
  // answer and nobody else's.
  const surfaceUp = !!answer?.origin;
  useEffect(() => {
    onSurfaceReady(surfaceUp);
    return () => onSurfaceReady(false);
  }, [onSurfaceReady, surfaceUp]);

  if (!answer) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-xs text-muted-foreground">
        <LoadingIcon />
        Starting the CAD runtime…
      </div>
    );
  }

  if (!answer.origin) {
    const reason = answer.reason ?? "runtime-not-ready";
    return (
      <EmptyState
        action={
          reason === "no-project" ? undefined : (
            <div className="flex flex-col items-center gap-2" data-cad-failure={reason}>
              {answer.message ? (
                <pre className="max-h-40 max-w-[420px] overflow-auto rounded-lg border bg-muted/40 px-3 py-2 text-left font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
                  <code data-selectable>{answer.message}</code>
                </pre>
              ) : null}
              {answer.log ? (
                <p className="max-w-[420px] truncate text-[11px] text-muted-foreground" title={answer.log}>
                  Log: <span data-selectable>{answer.log}</span>
                </p>
              ) : null}
              <div className="flex items-center gap-2">
                <Button className="h-7 gap-1.5 text-xs" onClick={retry} size="sm" variant="secondary">
                  <RefreshCw className="size-3.5" />
                  Try again
                </Button>
                <Button
                  className="h-7 gap-1.5 text-xs"
                  onClick={() => openSettings("about")}
                  size="sm"
                  variant="ghost"
                >
                  <Settings2 className="size-3.5" />
                  Runtime status
                </Button>
              </div>
            </div>
          )
        }
        description={REASONS[reason]}
        icon={Box}
        title={TITLES[reason]}
        tone="warn"
      />
    );
  }

  return (
    <div className="h-full min-h-0" data-cad-surface>
      <Suspense
        fallback={
          <div className="flex h-full flex-col items-center justify-center gap-3 text-xs text-muted-foreground">
            <LoadingIcon />
            Loading the CAD viewer…
          </div>
        }
      >
        <CadSurface
          captureRequest={captureRequest}
          colorScheme={colorScheme}
          file={path}
          fileSheetOpen={fileSheetOpen}
          onCapture={onCapture}
          onFileSheetOpenChange={onFileSheetOpenChange}
          onOpenFile={onOpenFile}
          onReference={onReference}
          onThemeEditingChange={onThemeEditingChange}
          origin={answer.origin}
          panelSlot={panelSlot}
          selectReference={selectReference}
          themeEditing={themeEditing}
        />
      </Suspense>
    </div>
  );
}

/** One title and one sentence per reason: they are different problems with different fixes. */
const TITLES: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready": "The CAD runtime did not start",
  "viewer-failed": "The CAD viewer did not start",
  "no-project": "This file's project is no longer open",
};

const REASONS: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready":
    "The Python runtime that ships with Hardcore could not run cadgen, so nothing can render this file. The runtime's own words are below.",
  "viewer-failed": "The runtime is fine, but its viewer process for this project did not come up. The launcher's last words are below.",
  "no-project": "Open the project again to render its files.",
};
