import { lazy, Suspense } from "react";
import { useViewerHost } from "../../../../host/context.js";
import { DEFAULT_OVERLAY_DRAWING_COLOR } from "../../../../drawing/toolbar.jsx";

// Someone who pressed Draw came to draw: the overlay opens on the pen. Shared with the session
// (`CadFileView.js`) so the toolbar shows the same tool before the editor has reported any.
export const CAD_DRAWING_DEFAULTS = Object.freeze({ tool: "freedraw", color: DEFAULT_OVERLAY_DRAWING_COLOR });

// Excalidraw is large and only Draw needs it: the chunk loads on the first use of the tool.
const DrawingEditor = lazy(() => import("../../../../drawing/index.js").then(module => ({ default: module.DrawingEditor })));

/**
 * Draw mode's ink: the shared drawing editor, transparent and without its own
 * controls, over a viewport whose camera follows it (`drawingViewLock.js`).
 * Mounted only while Draw is active, so leaving the tool discards the sketch.
 */
export default function DrawingOverlay({ drawing, onReady, onContentChange, onViewportChange }) {
  const { platform } = useViewerHost().environment;
  return <div className="absolute inset-0 z-10" data-cad-drawing-overlay="">
    <Suspense fallback={null}>
      {/* The host exposes drawing controls through Draw's corner dropdown. */}
      <DrawingEditor mode="overlay" toolbar={false} initialTool={CAD_DRAWING_DEFAULTS.tool} name="CAD drawing" platform={platform} onReady={onReady}
        onHistoryChange={drawing?.onHistoryChange} onToolChange={drawing?.onToolChange} onColorChange={drawing?.onColorChange}
        onContentChange={onContentChange} onViewportChange={onViewportChange} />
    </Suspense>
  </div>;
}
