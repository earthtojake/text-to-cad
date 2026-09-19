import SelectionFilterMenu from "./SelectionFilterMenu.jsx";
import { SELECTION_FILTERS } from "../../workbench/selectionFilter.js";
import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Camera,
  Focus,
  Hand,
  MousePointer2,
  Orbit,
  Pause,
  Play,
  PenTool,
  Ruler,
  X
} from "lucide-react";
import {
  renderCapabilities,
  supportsTool
} from "@hardcore/core/lib/renderCapabilities.js";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import DrawingToolbar from "./DrawingToolbar.js";
import { ToolbarButton } from "./ToolbarButton.js";
import ToolbarShell from "./ToolbarShell.js";
import { FileSheetPortalContext } from "./FileSheet.js";

const FLOATING_TOOL_BAR_SURFACE_CLASS =
  "bg-background border border-border text-foreground shadow-sm";
const PREVIEW_TOOLBAR_HIDE_DELAY_MS = 2500;

// In orbit/preview mode the toolbar stays available but auto-hides: it appears
// on any cursor activity and fades out after a short idle delay (and never
// hides while the pointer is over it). Outside preview mode it is always shown.
function usePreviewToolbarVisibility(previewMode) {
  const [visible, setVisible] = useState(true);
  const hideTimerRef = useRef(0);
  const hoveredRef = useRef(false);
  const previewRef = useRef(previewMode);
  previewRef.current = previewMode;

  const scheduleHide = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.clearTimeout(hideTimerRef.current);
    if (!previewRef.current || hoveredRef.current) {
      return;
    }
    hideTimerRef.current = window.setTimeout(() => setVisible(false), PREVIEW_TOOLBAR_HIDE_DELAY_MS);
  }, []);

  const reveal = useCallback(() => {
    setVisible(true);
    scheduleHide();
  }, [scheduleHide]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }
    if (!previewMode) {
      window.clearTimeout(hideTimerRef.current);
      hoveredRef.current = false;
      setVisible(true);
      return undefined;
    }
    reveal();
    const onActivity = () => reveal();
    window.addEventListener("pointermove", onActivity, { passive: true });
    window.addEventListener("pointerdown", onActivity, { passive: true });
    return () => {
      window.clearTimeout(hideTimerRef.current);
      window.removeEventListener("pointermove", onActivity);
      window.removeEventListener("pointerdown", onActivity);
    };
  }, [previewMode, reveal]);

  const onToolbarEnter = useCallback(() => {
    hoveredRef.current = true;
    if (typeof window !== "undefined") {
      window.clearTimeout(hideTimerRef.current);
    }
    setVisible(true);
  }, []);
  const onToolbarLeave = useCallback(() => {
    hoveredRef.current = false;
    scheduleHide();
  }, [scheduleHide]);

  return {
    toolbarHidden: previewMode ? !visible : false,
    onToolbarEnter,
    onToolbarLeave
  };
}
const FLOATING_TOOL_BAR_BUTTON_CLASSES =
  "grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground";

function ToolbarMenu({ label, Icon, active = false, resetKey, onEnter, onLeave, children }) {
  const boundary = useContext(FileSheetPortalContext);
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [resetKey]);
  return <DropdownMenu open={open} onOpenChange={next => {
    setOpen(next);
    if (next) onEnter?.(); else onLeave?.();
  }}>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label={label} title={label}
        className={`${FLOATING_TOOL_BAR_BUTTON_CLASSES} ${active ? "bg-sidebar-accent" : ""}`}>
        <Icon className="size-3" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" sideOffset={8} collisionBoundary={boundary} collisionPadding={8}
      onEscapeKeyDown={event => event.stopPropagation()}
      className="pointer-events-auto w-60 max-w-[min(240px,var(--radix-dropdown-menu-content-available-width))]">
      <DropdownMenuLabel>{label}</DropdownMenuLabel>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

function DesktopFloatingToolBar({
  renderFormat,
  floatingCadToolbarPosition,
  drawingViewToggle = false,
  drawingViewMode = "3d",
  onDrawingViewModeChange,
  previewMode = false,
  toolbarHidden = false,
  onToolbarEnter,
  onToolbarLeave,
  handleEnterPreviewMode,
  handleExitPreviewMode,
  selectionFilter = null,
  onSelectionFilterChange,
  selectionFilterNotice = "",
  selectionToolActive,
  referenceSelectionPending = false,
  referenceSelectionUnavailable = false,
  referenceSelectionDeferred = false,
  animationAvailable = false,
  animationPlaying = false,
  animationDisabled = false,
  handleAnimationPlayToggle,
  drawToolActive,
  measureModeActive = false,
  measurementPanel = null,
  measureDisabled = false,
  measureSupported = null,
  panToolActive,
  handleSelectTabToolMode,
  viewerLoading,
  selectedMeshData,
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes,
  handleScreenshotCopy,
  handleCapture = null
}) {
  // What this format can do, from the one capability table — never re-derived from
  // its identity, so a new format inherits the toolbar by declaring a row.
  const capabilities = renderCapabilities(renderFormat);
  // "Is there anything on screen?" — asked once, for every format, rather than
  // re-derived per format at each button.
  const viewportContent = selectedMeshData;
  const showToolCluster = supportsTool(renderFormat, "select") ||
    supportsTool(renderFormat, "pan") ||
    supportsTool(renderFormat, "draw");
  const captureDisabled = viewerLoading || !viewportContent;
  const canMeasure = measureSupported ?? capabilities.measure;
  const selectDisabled = viewerLoading ||
    !viewportContent ||
    referenceSelectionPending ||
    referenceSelectionUnavailable ||
    referenceSelectionDeferred;
  const selectLabel = referenceSelectionPending ? "Preparing selection" : "Select";
  // Any format with animation clips gets transport controls, whichever store backs them.
  const showAnimationPlay = capabilities.animations && animationAvailable;
  const animationPlayDisabled = viewerLoading || !viewportContent || animationDisabled;
  const animationLabel = animationPlaying ? "Pause" : "Play";

  const toolbarRef = useRef(null);
  const [compact, setCompact] = useState(false);
  const hasCapture = typeof handleCapture === "function";
  // The wrapper's compact/full marker remains a useful host diagnostic. Both
  // groups wrap as whole horizontal pills when this width is unavailable.
  const viewWidth = (showToolCluster ? 26 : 0) + (selectionFilter !== null ? 26 : 0) +
    (drawingViewToggle ? 52 : 0) + 42;
  const toolsWidth = 8 + 26 * [supportsTool(renderFormat, "select"),
    supportsTool(renderFormat, "pan"), canMeasure, supportsTool(renderFormat, "draw")].filter(Boolean).length;
  useLayoutEffect(() => {
    const scene = toolbarRef.current?.parentElement;
    if (!scene) return undefined;
    const update = () => setCompact(scene.clientWidth < 28 + Math.max(viewWidth, toolsWidth));
    const observer = new ResizeObserver(update);
    observer.observe(scene);
    update();
    return () => observer.disconnect();
  }, [viewWidth, toolsWidth]);
  const menuProps = { resetKey: `${compact}:${previewMode}`, onEnter: onToolbarEnter, onLeave: onToolbarLeave };
  const viewMenu = <ToolbarMenu label="View controls" Icon={Orbit} active={animationPlaying} {...menuProps}>
    {!previewMode && <>
      <DropdownMenuItem disabled={captureDisabled} onSelect={handleEnterPreviewMode}>
        <Orbit className="size-3.5" aria-hidden="true" />Orbit
      </DropdownMenuItem>
    </>}
    {showAnimationPlay && <>
      {!previewMode && <DropdownMenuSeparator />}
      <DropdownMenuItem disabled={animationPlayDisabled} onSelect={handleAnimationPlayToggle}>
        {animationPlaying ? <Pause className="size-3.5" aria-hidden="true" /> : <Play className="size-3.5" aria-hidden="true" />}{animationLabel}
      </DropdownMenuItem>
    </>}
  </ToolbarMenu>;
  const captureMenu = <ToolbarMenu label="Capture" Icon={Camera} {...menuProps}>
    <DropdownMenuItem disabled={captureDisabled} onSelect={() => { void handleScreenshotCopy(); }}>
      <Focus className="size-3.5" aria-hidden="true" />Copy screenshot
    </DropdownMenuItem>
    {hasCapture && <DropdownMenuItem disabled={captureDisabled} onSelect={() => { void handleCapture(); }} data-testid="capture-to-chat">
      <Camera className="size-3.5" aria-hidden="true" />Ask about this view
    </DropdownMenuItem>}
  </ToolbarMenu>;
  // A group stays one horizontal pill whenever it fits. At extreme widths its
  // own buttons wrap inside the same semantic group instead of letting the
  // pill extend past the scene edge.
  const groupClasses = `${toolbarHidden ? "pointer-events-none" : "pointer-events-auto"} inline-flex min-h-8 w-fit min-w-0 max-w-full flex-wrap items-center justify-end gap-0.5 rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`;

  // Buttons shared between the full toolbar and the reduced orbit-mode toolbar.
  const animationButton = showAnimationPlay ? (
    <ToolbarButton
      label={animationLabel}
      active={animationPlaying}
      onClick={handleAnimationPlayToggle}
      disabled={animationPlayDisabled}
      aria-pressed={animationPlaying}
    >
      {animationPlaying ? (
        <Pause className="size-3" strokeWidth={2} aria-hidden="true" />
      ) : (
        <Play className="size-3" strokeWidth={2} aria-hidden="true" />
      )}
    </ToolbarButton>
  ) : null;

  const showSelectTool = !previewMode && supportsTool(renderFormat, "select");
  const showPanTool = !previewMode && supportsTool(renderFormat, "pan");
  const showMeasureTool = !previewMode && canMeasure;
  const showDrawTool = !previewMode && supportsTool(renderFormat, "draw");
  const showInteractionTools = showSelectTool || showPanTool || showMeasureTool || showDrawTool;
  const showSelectionSettings = !previewMode && selectionFilter !== null;
  const showViewSettings = !previewMode && showToolCluster;
  const showDrawingViewSettings = !previewMode && drawingViewToggle;
  const hasViewActions = showSelectionSettings || showViewSettings || showDrawingViewSettings;

  return (
    <div
      className={`absolute z-20 flex flex-col items-end gap-1 transition-opacity duration-300 ${toolbarHidden ? "opacity-0" : "opacity-100"}`}
      ref={toolbarRef}
      data-cad-toolbar={compact ? "compact" : "full"}
      style={{ ...floatingCadToolbarPosition, maxWidth: "calc(100% - 28px)" }}
    >
      <TooltipProvider delayDuration={250}>
        {/* Interaction and view/action pills stay horizontal internally and
            wrap as whole groups in a narrow host pane. */}
        <div className="flex w-full max-w-full flex-wrap items-center justify-end gap-1 self-end">
        {showInteractionTools && <div role="group" aria-label="Interaction tools" className={groupClasses} onPointerEnter={onToolbarEnter} onPointerLeave={onToolbarLeave}>
          {showSelectTool && <ToolbarButton label={selectLabel} active={referenceSelectionDeferred ? false : selectionToolActive}
            onClick={() => handleSelectTabToolMode("references")} disabled={selectDisabled}
            aria-pressed={referenceSelectionDeferred ? false : selectionToolActive}>
            <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>}
          {showPanTool && <ToolbarButton label="Pan" active={panToolActive} onClick={() => handleSelectTabToolMode("pan")}
            disabled={viewerLoading || !viewportContent} aria-pressed={panToolActive}>
            <Hand className="size-3" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>}
          {showMeasureTool && <ToolbarButton label="Measure" active={measureModeActive} onClick={() => handleSelectTabToolMode("measure")}
            disabled={measureDisabled} aria-pressed={measureModeActive}>
            <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>}
          {showDrawTool && <ToolbarButton label="Draw" active={drawToolActive} onClick={() => handleSelectTabToolMode("draw")}
            disabled={viewerLoading || !viewportContent} aria-pressed={drawToolActive}>
            <PenTool className="size-3" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>}
        </div>}
        <div role="group" aria-label="View and actions" className={groupClasses} onPointerEnter={onToolbarEnter} onPointerLeave={onToolbarLeave}>
          {showSelectionSettings && <SelectionFilterMenu value={selectionFilter} onChange={onSelectionFilterChange} disabled={viewerLoading || !viewportContent} />}
          {showViewSettings && viewMenu}
          {showDrawingViewSettings && <>
            {/* `active`, not `isActive`: ToolbarButton switches variant on `active`. */}
            <ToolbarButton label="Top-down 2D view" active={drawingViewMode === "2d"} onClick={() => onDrawingViewModeChange?.("2d")}>
              <span className="text-micro leading-none">2D</span>
            </ToolbarButton>
            <ToolbarButton label="3D view" active={drawingViewMode !== "2d"} onClick={() => onDrawingViewModeChange?.("3d")}>
              <span className="text-micro leading-none">3D</span>
            </ToolbarButton>
          </>}
          {hasViewActions && <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />}
          {previewMode && animationButton}
          {captureMenu}
          {previewMode && <ToolbarButton label="Exit orbit" onClick={handleExitPreviewMode}>
            <X className="size-3" aria-hidden="true" />
          </ToolbarButton>}
        </div>
        </div>
      </TooltipProvider>
      {!previewMode && selectionToolActive && selectionFilter !== null && selectionFilter !== "all" && (
        <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {SELECTION_FILTERS.find(item => item.id === selectionFilter)?.label}
        </div>
      )}
      {!previewMode && selectionToolActive && selectionFilterNotice && <p role="status" className="max-w-56 rounded-md border bg-background px-2 py-1 text-micro text-muted-foreground shadow-sm">{selectionFilterNotice}</p>}


      {!previewMode && measureModeActive && measurementPanel && <ToolbarShell
        title="Measure" label="Measurements" className="max-h-64"
        onClose={() => handleSelectTabToolMode("references")} closeLabel="Finish measuring"
        footer="Clears when you leave Measure.">
        {measurementPanel}
      </ToolbarShell>}
      {!previewMode && supportsTool(renderFormat, "draw") && drawToolActive ? (
        <DrawingToolbar
          onClose={() => handleSelectTabToolMode("references")}
          drawingToolOptions={drawingToolOptions}
          drawingTool={drawingTool}
          handleSelectDrawingTool={handleSelectDrawingTool}
          handleUndoDrawing={handleUndoDrawing}
          handleRedoDrawing={handleRedoDrawing}
          handleClearDrawings={handleClearDrawings}
          canUndoDrawing={canUndoDrawing}
          canRedoDrawing={canRedoDrawing}
          drawingStrokes={drawingStrokes}
        />
      ) : null}
    </div>
  );
}

export default function FloatingToolBar({
  previewMode,
  selectedEntry,
  ...toolbarProps
}) {
  const { toolbarHidden, onToolbarEnter, onToolbarLeave } = usePreviewToolbarVisibility(previewMode);
  if (!selectedEntry) {
    return null;
  }

  return (
    <DesktopFloatingToolBar
      previewMode={previewMode}
      toolbarHidden={toolbarHidden}
      onToolbarEnter={onToolbarEnter}
      onToolbarLeave={onToolbarLeave}
      {...toolbarProps}
    />
  );
}
