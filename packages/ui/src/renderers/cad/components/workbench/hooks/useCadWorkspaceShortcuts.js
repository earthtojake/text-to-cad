import { useEffect } from "react";
import { isEditableTarget } from "../../../ui/dom.js";
import { TAB_TOOL_MODE } from "../../../workbench/constants.js";

export function useCadWorkspaceShortcuts({
  selectionActive = false,
  onClearSelection = null,
  copyStatus,
  screenshotStatus,
  setCopyStatus,
  setScreenshotStatus,
  previewMode,
  viewerAlertOpen,
  themeSheetOpen,
  tabToolsOpen,
  isDesktop,
  filesPanelOpen,
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
  setThemeEditing,
  setTabToolsOpen,
  setFilesPanelOpen,
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
    if (!(selectionActive || previewMode || viewerAlertOpen || themeSheetOpen || tabToolsOpen || (!isDesktop && filesPanelOpen) || tabToolMode === TAB_TOOL_MODE.MEASURE)) {
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
        if (undoShortcut && drawingUndoStackRef.current.length) {
          event.preventDefault();
          handleUndoDrawing();
          return;
        }

        if (redoShortcut && drawingRedoStackRef.current.length) {
          event.preventDefault();
          handleRedoDrawing();
          return;
        }
      }

      if (event.key === "Escape" && !event.defaultPrevented && !isEditableTarget(event.target)) {
        if (previewMode) {
          const previousUiState = previewUiStateRef.current;
          previewUiStateRef.current = null;
          setPreviewMode(false);
          if (previousUiState) {
            setViewerAlertOpen(previousUiState.viewerAlertOpen);
            setThemeEditing(previousUiState.themeEditing);
            setFilesPanelOpen(previousUiState.filesPanelOpen);
            setTabToolsOpen(previousUiState.tabToolsOpen);
            setTabToolMode(previousUiState.tabToolMode);
          }
          return;
        }
        if (tabToolMode === TAB_TOOL_MODE.MEASURE) {
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
        setThemeEditing(false);
        setTabToolsOpen(false);
        if (!isDesktop) {
          setFilesPanelOpen(false);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [
    selectionActive,
    onClearSelection,
    drawingRedoStackRef,
    drawingUndoStackRef,
    handleRedoDrawing,
    handleUndoDrawing,
    isDesktop,
    themeSheetOpen,
    previewMode,
    previewUiStateRef,
    setThemeEditing,
    setPreviewMode,
    setFilesPanelOpen,
    setTabToolMode,
    setTabToolsOpen,
    setViewerAlertOpen,
    filesPanelOpen,
    measureDraftActive,
    onCancelMeasureDraft,
    tabToolMode,
    tabToolsOpen,
    viewerAlertOpen
  ]);
}
