import { Box, Settings2 } from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import { Spinner } from "@renderer/components/ui/spinner";
import { useUi } from "@renderer/state/ui";
import type { ViewerOrigin } from "@shared/ipc/cad";

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
 * instance's origin. P5 spawns one per project root; until then
 * `cad.viewerOrigin` answers `{ origin: null, reason: "runtime-not-ready" }`
 * and this component shows the card below — which is not a placeholder for a
 * missing feature but the real first-run state of an app whose 1 GB Python
 * runtime installs on demand (plan §8).
 */
type CadSurfaceProps = {
  origin: string;
  file: string;
  onOpenFile: (path: string) => void;
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
    default: ({ origin, file, onOpenFile }: CadSurfaceProps) => (
      <ViewerOriginProvider origin={origin}>
        <CadFileView
          className="h-full"
          file={file}
          // The desktop window owns its own title; the surface must not write it.
          manageDocumentTitle={false}
          onOpenFile={(next) => onOpenFile(next)}
          origin={origin}
        />
      </ViewerOriginProvider>
    ),
  };
});

export function CadRenderer({
  projectId,
  path,
  onOpenFile,
}: {
  projectId: string;
  /** Project-root-relative: the same path the viewer's `?file=` carries. */
  path: string;
  onOpenFile: (path: string) => void;
}) {
  const [answer, setAnswer] = useState<ViewerOrigin | null>(null);
  const openSettings = useUi((state) => state.openSettings);

  // Asked once per mount. A tab's project cannot change under it — a project
  // change rebuilds the strip — so there is nothing to reset here.
  useEffect(() => {
    let cancelled = false;
    void window.hardcore.cad
      .viewerOrigin({ projectId })
      .then((result) => {
        if (!cancelled) {
          setAnswer(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAnswer({ origin: null, reason: "viewer-failed" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (!answer) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
        <Spinner className="size-3.5" />
        Starting the CAD runtime…
      </div>
    );
  }

  if (!answer.origin) {
    return (
      <EmptyState
        action={
          <Button
            className="h-7 gap-1.5 text-xs"
            onClick={() => openSettings("cad-runtime")}
            size="sm"
            variant="secondary"
          >
            <Settings2 className="size-3.5" />
            Open CAD Runtime settings
          </Button>
        }
        description={REASONS[answer.reason ?? "runtime-not-ready"]}
        icon={Box}
        title="CAD runtime is not set up yet"
        tone="warn"
      />
    );
  }

  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center gap-2 text-xs text-muted-foreground">
          <Spinner className="size-3.5" />
          Loading the CAD viewer…
        </div>
      }
    >
      <CadSurface file={path} onOpenFile={onOpenFile} origin={answer.origin} />
    </Suspense>
  );
}

/** One sentence per reason: they are different problems with different fixes. */
const REASONS: Record<NonNullable<ViewerOrigin["reason"]>, string> = {
  "runtime-not-ready":
    "STEP, GLB, STL, 3MF, DXF and robot descriptions render here once the bundled Python runtime and cadgen are installed. It is a one-time download.",
  "viewer-failed":
    "The CAD runtime is installed but its viewer process did not start. Settings has a Repair button and the last error.",
  "no-project": "This file's project is no longer open.",
};
