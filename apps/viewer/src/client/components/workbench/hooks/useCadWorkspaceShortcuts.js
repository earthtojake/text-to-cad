import { useEffect } from "react";
import { isEditableTarget } from "../../../ui/dom";
import { TAB_TOOL_MODE } from "../../../workbench/constants";

export function useCadWorkspaceShortcuts({
  copyStatus,
  screenshotStatus,
  setCopyStatus,
  setScreenshotStatus,
  previewMode,
  inspectionEnabled = true,
  viewerAlertOpen,
  tabToolsOpen,
  isDesktop,
  sidebarOpen,
  previewUiStateRef,
  tabToolMode,
  measureDraftActive = false,
  onCancelMeasureDraft = null,
  drawingUndoStackRef,
  drawingRedoStackRef,
  handleUndoDrawing,
  handleRedoDrawing,
  setPreviewMode,
  setViewerAlertOpen,
  setTabToolsOpen,
  setSidebarOpen,
  setTabToolMode
}) {
  useEffect(() => {
    if (!(copyStatus || screenshotStatus)) {
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      setCopyStatus("");
      setScreenshotStatus("");
    }, 2200);
    return () => window.clearTimeout(timeoutId);
  }, [copyStatus, screenshotStatus, setCopyStatus, setScreenshotStatus]);

  useEffect(() => {
    if (!(previewMode || viewerAlertOpen || tabToolsOpen || (!isDesktop && sidebarOpen) || tabToolMode === TAB_TOOL_MODE.MEASURE)) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (
        !event.defaultPrevented &&
        !isEditableTarget(event.target) &&
        !event.altKey &&
        (event.metaKey || event.ctrlKey)
      ) {
        const lowerKey = String(event.key || "").toLowerCase();
        const redoShortcut =
          lowerKey === "y" ||
          (lowerKey === "z" && event.shiftKey);
        const undoShortcut = lowerKey === "z" && !event.shiftKey;
        if (inspectionEnabled && undoShortcut && drawingUndoStackRef.current.length) {
          event.preventDefault();
          handleUndoDrawing();
          return;
        }

        if (inspectionEnabled && redoShortcut && drawingRedoStackRef.current.length) {
          event.preventDefault();
          handleRedoDrawing();
          return;
        }
      }

      if (event.key === "Escape" && !event.defaultPrevented) {
        if (previewMode) {
          const previousUiState = previewUiStateRef.current;
          previewUiStateRef.current = null;
          setPreviewMode(false);
          if (previousUiState) {
            setViewerAlertOpen(previousUiState.viewerAlertOpen);
            setSidebarOpen(previousUiState.sidebarOpen);
            setTabToolsOpen(previousUiState.tabToolsOpen);
            setTabToolMode(previousUiState.tabToolMode);
          }
          return;
        }
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
        setViewerAlertOpen(false);
        setTabToolsOpen(false);
        if (!isDesktop) {
          setSidebarOpen(false);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [
    drawingRedoStackRef,
    drawingUndoStackRef,
    handleRedoDrawing,
    handleUndoDrawing,
    isDesktop,
    inspectionEnabled,
    previewMode,
    previewUiStateRef,
    setPreviewMode,
    setSidebarOpen,
    setTabToolMode,
    setTabToolsOpen,
    setViewerAlertOpen,
    sidebarOpen,
    measureDraftActive,
    onCancelMeasureDraft,
    tabToolMode,
    tabToolsOpen,
    viewerAlertOpen
  ]);
}
