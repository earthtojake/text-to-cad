import { useEffect, useRef } from "react";
import { isEditableTarget } from "../../../ui/dom.js";
import { TAB_TOOL_MODE } from "../../../workbench/constants.js";

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
  const pointerInside = useRef(false);
  useEffect(() => {
    const onPointerDown = event => { pointerInside.current = Boolean(viewerElement?.current?.contains(event.target)); };
    window.addEventListener('pointerdown', onPointerDown, true);
    return () => window.removeEventListener('pointerdown', onPointerDown, true);
  }, [viewerElement]);
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
    if (!(selectionActive || previewMode || viewerAlertOpen || tabToolsOpen || (!isDesktop && filesPanelOpen) || tabToolMode === TAB_TOOL_MODE.MEASURE)) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (previewMode) return; // The host owns fullscreen Escape; tools are inactive.
      const element = viewerElement?.current;
      if (!element) return;
      const target = event.target;
      const inViewer = target instanceof Node && element.contains(target);
      const background = target === document.body || target === document || target === window;
      const focus = document.activeElement;
      if (!inViewer && !(background && pointerInside.current && (focus === document.body || (focus && element.contains(focus))))) return;
      if (event.key === "Escape" && !event.defaultPrevented && !isEditableTarget(event.target)) {
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
    viewerElement,
    selectionActive,
    onClearSelection,
    isDesktop,
    inspectionEnabled,
    previewMode,
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
