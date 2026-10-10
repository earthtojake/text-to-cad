import { useMemo } from "react";
import PlaneShell from "../kit/shell/PlaneShell.jsx";
import { usePlaneFileView, usePlaneShell } from "../kit/shell/usePlaneShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument } from "../workspace/useWorkspaceDocument.js";
import { drawingLoadAlert, useDrawingPayload } from "./useDrawingPayload.js";
import { useDrawingView } from "./useDrawingView.js";

/**
 * A `.dxf` is a straight render: the drawing, on a canvas, and nothing else. No 3D, no fold
 * preview, no thickness or material, no tools, no toolbar and no panel — not a file panel, not
 * Display settings, not a layer list. A DXF is a finished 2D document; the questions those
 * controls answered were about a sheet-metal part the viewer was inventing from it.
 *
 * The picture comes from the BACKEND (`GET /__cad/drawing`), which runs ezdxf over the file and
 * returns flat primitives. This renderer never parses DXF. Its frame, file view and host glue are
 * the flat views' shell (`kit/shell/usePlaneShell.js`).
 */

/** Host commands a 2D drawing cannot answer, each with the sentence its caller reads. */
const DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A DXF is a 2D drawing without CAD references: it has no parts, faces or edges to select. "
    + "Selection needs a model with topology, such as a STEP file.",
  clearSelection: "A DXF is a 2D drawing without CAD references, so it never has a selection to clear."
});
const LIVE = Object.freeze({ declined: DECLINED_LIVE_COMMANDS });
const WORDS = Object.freeze({
  noun: "drawing",
  captureFailed: "Couldn’t capture the drawing",
  copyFailed: "Couldn’t copy from the drawing",
  noCamera: "A DXF is a flat drawing shown head on: it has no camera to pose. "
    + "Zoom and pan it in the view, or call resetCamera to fit the whole drawing again.",
  noDisplay: "A DXF has no Display settings: a drawing is painted in the pens it declares, on the "
    + "theme's background, with no surfaces, lighting or render mode to configure."
});
const DRAWING_UPDATE_STATUS = Object.freeze({ pending: true, label: "Updating drawing…" });

function DxfSurface({ view, data }) {
  const workspace = useWorkspaceDocument({ view, data });
  const file = workspace.entry?.file || view.file.path;
  const payload = useDrawingPayload({ client: workspace.client, file, revision: workspace.resource.revision });
  // The file's view with the drawing's transform as its camera and nothing else: a drawing has no
  // Display settings and no slices of its own.
  const fileView = usePlaneFileView({ view });
  const drawingView = useDrawingView({
    drawing: payload.drawing, restored: fileView.restored, colorScheme: view.appearance?.colorScheme === "dark" ? "dark" : "light",
    onViewMoved: fileView.rememberView
  });

  // With a drawing on screen, a failure to read the file again leaves that drawing to use.
  const shown = Boolean(payload.drawing);
  const alert = useMemo(() => {
    if (workspace.catalogError && !shown) {
      return {
        severity: "error", kind: "status", title: "Couldn’t open the drawing",
        message: "The viewer couldn’t retrieve this file’s information.",
        recovery: "Try again. If this continues, check that the viewer is running.",
        details: String(workspace.catalogError), reload: true
      };
    }
    const failed = drawingLoadAlert(workspace.modelKey || file, payload.error);
    return failed && shown ? { ...failed, blocking: false, message: `${failed.message} The existing drawing remains visible.` } : failed;
  }, [workspace.catalogError, workspace.modelKey, file, payload.error, shown]);
  // A host asking to select a reference is answered rather than dropped.
  useDeclinedSelectReference(workspace);

  const shell = usePlaneShell({
    view, services: workspace.services, resource: workspace.resource, modelKey: file, plane: drawingView, words: WORDS, live: LIVE,
    load: { shown, busy: payload.loading, updating: payload.updating, alert, reading: "Reading drawing", updateStatus: DRAWING_UPDATE_STATUS }
  });
  return <PlaneShell shell={shell} surface="drawing-surface" label={`Drawing: ${view.file.name}`}
    overlay={shown && !payload.drawing.bounds ? <p className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground"
      data-drawing-empty>
      This drawing has no geometry in its modelspace, so there is nothing to show.
    </p> : null} />;
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
