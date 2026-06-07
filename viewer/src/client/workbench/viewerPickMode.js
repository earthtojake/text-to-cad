import { VIEWER_PICK_MODE } from "cadjs/lib/viewer/constants.js";

export function viewerPickModeForRenderPane({
  dxfMode = false,
  pathPreviewMode = false,
  topologySelectionPending = false,
  topologySelectionUnavailable = false,
  topologySelectionDeferred = false,
  viewerMode = "",
  focusedPartIds = ""
} = {}) {
  if (topologySelectionPending || topologySelectionUnavailable || topologySelectionDeferred) {
    return VIEWER_PICK_MODE.NONE;
  }
  if (dxfMode || pathPreviewMode) {
    return VIEWER_PICK_MODE.NONE;
  }
  if (viewerMode === "assembly" && !String(focusedPartIds || "").trim()) {
    return VIEWER_PICK_MODE.ASSEMBLY;
  }
  return VIEWER_PICK_MODE.AUTO;
}
