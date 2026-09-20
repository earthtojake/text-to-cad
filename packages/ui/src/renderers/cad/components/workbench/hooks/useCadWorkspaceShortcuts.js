import { useViewerShortcuts } from "../../../../kit/shell/useViewerShortcuts.js";
import { TAB_TOOL_MODE } from "../../../workbench/constants.js";

// What Escape means in this renderer, innermost first: a measurement in progress,
// the Measure tool, the selection, then the open dialog and panels. Which viewer
// the key belongs to is the kit's (`useViewerShortcuts`).
export function useCadWorkspaceShortcuts({
  viewerElement,
  selectionActive = false,
  onClearSelection = null,
  copyStatus,
  screenshotStatus,
  setCopyStatus,
  setScreenshotStatus,
  previewMode,
  inspectionEnabled = true,
  viewerAlertOpen,
  tabToolsOpen,
  isDesktop,
  filesPanelOpen,
  tabToolMode,
  measureDraftActive = false,
  onCancelMeasureDraft = null,
  setViewerAlertOpen,
  setTabToolsOpen,
  setFilesPanelOpen,
  setTabToolMode
}) {
  useViewerShortcuts({
    viewerElement, previewMode, copyStatus, screenshotStatus, setCopyStatus, setScreenshotStatus,
    escapeActive: Boolean(selectionActive || viewerAlertOpen || tabToolsOpen || (!isDesktop && filesPanelOpen) || tabToolMode === TAB_TOOL_MODE.MEASURE),
    onEscape() {
      if (inspectionEnabled && tabToolMode === TAB_TOOL_MODE.MEASURE) {
        // Escape cancels the measurement in progress and leaves the tool
        // armed, the way it does in a CAD measure tool. Only once there is
        // nothing to cancel does it back out of the tool itself.
        if (measureDraftActive) {
          onCancelMeasureDraft?.();
          return;
        }
        setTabToolMode(TAB_TOOL_MODE.REFERENCES);
        return;
      }
      if (selectionActive && onClearSelection) {
        onClearSelection();
        return;
      }
      setViewerAlertOpen(false);
      setTabToolsOpen(false);
      if (!isDesktop) setFilesPanelOpen(false);
    }
  });
}
