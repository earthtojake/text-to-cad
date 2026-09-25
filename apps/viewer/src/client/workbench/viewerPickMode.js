import { VIEWER_PICK_MODE } from "cadgen-js/lib/viewer/constants.js";

// Callers decide whether picking is enabled (parts, topology, or Measure).
// This helper stays format-agnostic.
export function viewerPickModeForRenderPane({
  panToolActive = false,
  topologySelectionPending = false,
  topologySelectionUnavailable = false,
  topologySelectionDeferred = false,
  topologyPickingActive = false,
  viewerMode = "",
  assemblyPickingActive = false,
  focusedPartIds = "",
  measureMode = false
} = {}) {
  // While panning, a drag is a camera move — picking on release would select
  // whatever the drag happened to finish over.
  if (panToolActive) {
    return VIEWER_PICK_MODE.NONE;
  }
  if (topologySelectionPending || topologySelectionUnavailable || topologySelectionDeferred) {
    return VIEWER_PICK_MODE.NONE;
  }
  // Measure outranks both part and topology selection, and needs neither. The
  // endpoint always comes from the ray hit on the visible mesh; loaded topology
  // only refines that hit into a snap. An assembly with nothing expanded still
  // measures surface to surface across its parts.
  if (measureMode) {
    return VIEWER_PICK_MODE.MEASURE;
  }
  if (
    viewerMode === "assembly" &&
    !topologyPickingActive &&
    (
      assemblyPickingActive ||
      !String(focusedPartIds || "").trim()
    )
  ) {
    return VIEWER_PICK_MODE.ASSEMBLY;
  }
  return VIEWER_PICK_MODE.AUTO;
}
