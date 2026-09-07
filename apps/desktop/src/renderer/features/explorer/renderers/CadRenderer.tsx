import { Box, RefreshCw, Settings2 } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import { Spinner } from "@renderer/components/ui/spinner";
import { useElementWidth } from "@renderer/hooks/use-element-width";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { NEW_SESSION_KEY, useComposer } from "@renderer/state/composer";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";
import type { ViewerOrigin } from "@shared/ipc/cad";
import type { ExplorerRoot } from "@shared/types";

import { cadSceneBackgroundFor, cadSheetWidthFor } from "../cad-layout";
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
 * in (`cad-layout.ts`): the layout is always the desktop one — the sheet is a
 * column beside the model at any pane width, never a drawer over it — the
 * sheet's width follows the pane, and light/dark is the app's theme. Without
 * the last, opening a STEP file flipped the whole window to the CAD theme's
 * scheme.
 */
type CadSurfaceProps = {
  origin: string;
  file: string;
  width: number;
  colorScheme: "light" | "dark";
  onOpenFile: (path: string) => void;
  /** A reference to select once the model is up; `key` distinguishes repeats. */
  selectReference: { selector: string; key: number } | null;
  onReference: (reference: { file: string; selector: string; text: string }) => void;
  onCapture: (capture: { blob: Blob; file: string }) => void;
  /**
   * A capture asked for from outside the viewport — the composer's `+` menu.
   * `key` distinguishes repeats, exactly as `selectReference`'s does; the
   * picture goes to `onCapture` either way, so the toolbar's camera button
   * and this are one path.
   */
  captureRequest: { key: number } | null;
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
  const { CadFileView, ViewerOriginProvider } = await import("@viewer/file-view");
  return {
    default: ({
      origin,
      file,
      width,
      colorScheme,
      onOpenFile,
      selectReference,
      onReference,
      onCapture,
      captureRequest,
    }: CadSurfaceProps) => (
      <ViewerOriginProvider origin={origin}>
        {/*
          A containing block for the surface's `position: fixed` parts. The
          viewer's right-hand sheet is a shadcn Sidebar — `fixed inset-y-0
          right-0` — which in the standalone app coincides with the window and
          in this tab would pin itself to the window's edge, over the tab
          strip and the file tree. A transform on an ancestor makes fixed
          descendants position against it instead; popovers portal to `body`
          and are unaffected.
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
            fileSheetWidth={cadSheetWidthFor(width)}
            layout="desktop"
            // The desktop window owns its own title; the surface must not write it.
            manageDocumentTitle={false}
            onCapture={onCapture}
            onOpenFile={(next) => onOpenFile(next)}
            onReference={onReference}
            origin={origin}
            sceneBackground={cadSceneBackgroundFor(colorScheme)}
            selectReference={selectReference}
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
}: {
  tabId: string;
  projectId: string;
  /** The directory the viewer serves: the project, or the tab's worktree (plan §9). */
  root: ExplorerRoot;
  /** Root-relative: the same path the viewer's `?file=` carries. */
  path: string;
  onOpenFile: (path: string) => void;
}) {
  const [answer, setAnswer] = useState<ViewerOrigin | null>(null);
  // A transcript link's `#selector` for this tab (`explorer.selectCadReference`).
  const selection = useExplorer((state) => (state.cadSelection?.tabId === tabId ? state.cadSelection : null));
  const selectReference = useMemo(
    () => (selection ? { selector: selection.selector, key: selection.nonce } : null),
    [selection],
  );
  // The composer's `+ Capture from viewer`, for this tab.
  const capture = useExplorer((state) => (state.cadCapture?.tabId === tabId ? state.cadCapture : null));
  const captureRequest = useMemo(() => (capture ? { key: capture.nonce } : null), [capture]);

  /**
   * The viewer's copies and captures go to the composer of the thread the
   * person is in — or the new-session box when there is none — as a chip
   * and as an image attachment (`state/composer.ts`). `file` is the tab's
   * root-relative path, which is what the agent can open.
   */
  const onReference = useCallback((reference: { file: string; selector: string }) => {
    useComposer.getState().insertReference(composerKey(), { file: reference.file, selector: reference.selector });
  }, []);
  const onCapture = useCallback(({ blob, file }: { blob: Blob; file: string }) => {
    const stem = (file.split("/").pop() ?? "view").replace(/\.[^.]+$/, "");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    useComposer.getState().attachFile(composerKey(), new File([blob], `${stem}-${stamp}.png`, { type: "image/png" }));
  }, []);
  const openSettings = useUi((state) => state.openSettings);
  const colorScheme = useResolvedTheme();
  const [hostRef, width] = useElementWidth();

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

  if (!answer) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Spinner className="size-3.5" />
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
    <div className="h-full min-h-0" data-cad-surface ref={hostRef}>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
            <Spinner className="size-3.5" />
            Loading the CAD viewer…
          </div>
        }
      >
        <CadSurface
          captureRequest={captureRequest}
          colorScheme={colorScheme}
          file={path}
          onCapture={onCapture}
          onOpenFile={onOpenFile}
          onReference={onReference}
          origin={answer.origin}
          selectReference={selectReference}
          width={width}
        />
      </Suspense>
    </div>
  );
}

/** The composer a reference or a capture goes to: the active thread's, else the new-session box. */
function composerKey(): string {
  return useSessions.getState().activeId ?? NEW_SESSION_KEY;
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
