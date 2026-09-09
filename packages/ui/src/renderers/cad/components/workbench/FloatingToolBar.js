import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Camera,
  Check,
  Ellipsis,
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
  DropdownMenuSeparator, DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import DrawingToolbar from "./DrawingToolbar.js";
import { ToolbarButton } from "./ToolbarButton.js";
import { ZoomControl } from "../viewer/ZoomControl.js";
import { CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS } from "./ToolbarShell.js";

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

function DesktopFloatingToolBar({
  renderFormat,
  floatingCadToolbarPosition,
  zoomControlsVisible = false,
  zoomPercent = 100,
  onZoomPercentChange,
  onZoomReset,
  drawingViewToggle = false,
  drawingViewMode = "3d",
  onDrawingViewModeChange,
  previewMode = false,
  toolbarHidden = false,
  onToolbarEnter,
  onToolbarLeave,
  handleExitPreviewMode,
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
  measureDisabled = false,
  panToolActive,
  handleSelectTabToolMode,
  viewerLoading,
  selectedMeshData,
  selectedDxfData,
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes,
  handleEnterPreviewMode,
  handleScreenshotCopy,
  handleCapture = null,
  selectedEntry
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
  const [moreOpen, setMoreOpen] = useState(false);
  const hasCapture = typeof handleCapture === "function";
  // Each existing button is 24px, with 2px gaps and 10px of pill border/padding.
  // Measure the scene, not the window: the Inspector can leave a very thin viewport.
  const fullButtonCount = previewMode
    ? 2 + Number(hasCapture) + Number(showAnimationPlay)
    : 2 + Number(hasCapture) + (showToolCluster ? 4 + Number(showAnimationPlay) : 0);
  useLayoutEffect(() => {
    const scene = toolbarRef.current?.parentElement;
    if (!scene) return undefined;
    const update = () => setCompact(scene.clientWidth < 28 + 8 + fullButtonCount * 26);
    const observer = new ResizeObserver(update);
    observer.observe(scene);
    update();
    return () => observer.disconnect();
  }, [fullButtonCount]);
  useEffect(() => { setMoreOpen(false); }, [compact, previewMode]);

  const moreMenu = compact ? (
    <DropdownMenu open={moreOpen} onOpenChange={(open) => {
      setMoreOpen(open);
      if (open) onToolbarEnter?.();
      else onToolbarLeave?.();
    }}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="More tools"
          title="More tools"
          className={`${FLOATING_TOOL_BAR_BUTTON_CLASSES} ${drawToolActive || animationPlaying ? "bg-sidebar-accent" : ""}`}
        >
          <Ellipsis className="size-3" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={6}
        collisionPadding={8}
        // Escape dismisses this menu, not the Inspector or tool underneath it.
        onEscapeKeyDown={(event) => event.stopPropagation()}
        className="pointer-events-auto w-52 max-w-[calc(100vw-16px)]"
        onCloseAutoFocus={(event) => {
          if (!compact) {
            event.preventDefault();
            toolbarRef.current?.querySelector("button:not(:disabled)")?.focus();
          }
        }}
      >
        {!previewMode && showToolCluster ? (
          <DropdownMenuItem
            disabled={viewerLoading || !viewportContent}
            onSelect={() => handleSelectTabToolMode("draw")}
          >
            <PenTool className="size-3.5" aria-hidden="true" />
            Draw
            {drawToolActive ? <Check className="ml-auto size-3.5" aria-label="Active" /> : null}
          </DropdownMenuItem>
        ) : null}
        {!previewMode && showToolCluster && showAnimationPlay ? (
          <DropdownMenuItem disabled={animationPlayDisabled} onSelect={handleAnimationPlayToggle}>
            {animationPlaying ? <Pause className="size-3.5" aria-hidden="true" /> : <Play className="size-3.5" aria-hidden="true" />}
            {animationLabel}
          </DropdownMenuItem>
        ) : null}
        {!previewMode ? (
          <>
            <DropdownMenuItem disabled={captureDisabled} onSelect={handleEnterPreviewMode}>
              <Orbit className="size-3.5" aria-hidden="true" />Orbit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        ) : null}
        <DropdownMenuItem disabled={captureDisabled} onSelect={() => { void handleScreenshotCopy(); }}>
          <Focus className="size-3.5" aria-hidden="true" />Copy screenshot
        </DropdownMenuItem>
        {hasCapture ? (
          <DropdownMenuItem disabled={captureDisabled} onSelect={() => { void handleCapture(); }} data-testid="capture-to-chat">
            <Camera className="size-3.5" aria-hidden="true" />Ask about this view
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null;


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

  const screenshotButton = (
    <ToolbarButton
      label="Copy screenshot"
      onClick={() => {
        void handleScreenshotCopy();
      }}
      disabled={captureDisabled}
    >
      <Focus className="size-3" strokeWidth={2} aria-hidden="true" />
    </ToolbarButton>
  );

  // Only a host that takes captures gets the button (docs/cad-renderer.md,
  // `onCapture`): standalone there is no chat for the picture to go to.
  const captureButton = typeof handleCapture === "function" ? (
    <ToolbarButton
      label="Ask about this view"
      onClick={() => {
        void handleCapture();
      }}
      disabled={captureDisabled}
      data-testid="capture-to-chat"
    >
      <Camera className="size-3" strokeWidth={2} aria-hidden="true" />
    </ToolbarButton>
  ) : null;

  // A drawing's own toolbar, in its own pill to the LEFT of the shared one: 2D and 3D are a
  // property of the drawing being viewed, not a tool that acts on it, so grouping them with
  // select/pan/draw would read as a fourth mode of the same kind.
  const drawingViewToolbar = drawingViewToggle ? (
    <div
      className={`${toolbarHidden ? "pointer-events-none" : "pointer-events-auto"} inline-flex h-8 w-fit items-center gap-0.5 rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}
      onPointerEnter={onToolbarEnter}
      onPointerLeave={onToolbarLeave}
    >
      {/* `active`, not `isActive`: ToolbarButton switches variant on `active`, and an unknown
          prop is silently dropped -- which is why neither button looked selected. */}
      <ToolbarButton
        label="Top-down 2D view"
        active={drawingViewMode === "2d"}
        onClick={() => onDrawingViewModeChange?.("2d")}
      >
        <span className="text-micro leading-none">2D</span>
      </ToolbarButton>
      <ToolbarButton
        label="3D view"
        active={drawingViewMode !== "2d"}
        onClick={() => onDrawingViewModeChange?.("3d")}
      >
        <span className="text-micro leading-none">3D</span>
      </ToolbarButton>
    </div>
  ) : null;

  const zoomToolbar = zoomControlsVisible ? (
    <div
      className={`${toolbarHidden ? "pointer-events-none" : "pointer-events-auto"} inline-flex h-8 w-fit items-center gap-0.5 rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}
      onPointerEnter={onToolbarEnter}
      onPointerLeave={onToolbarLeave}
    >
      <ZoomControl
        zoomPercent={zoomPercent}
        onZoomPercentChange={onZoomPercentChange}
        onZoomReset={onZoomReset}
      />
    </div>
  ) : null;

  return (
    <div
      className={`absolute z-20 flex flex-col items-end gap-1 transition-opacity duration-300 ${toolbarHidden ? "opacity-0" : "opacity-100"}`}
      ref={toolbarRef}
      data-cad-toolbar={compact ? "compact" : "full"}
      style={{ ...floatingCadToolbarPosition, maxWidth: "calc(100% - 28px)" }}
    >
      <TooltipProvider delayDuration={250}>
        {/* Wraps: in a host pane too narrow for the zoom pill beside the
            tools, the pill drops under them rather than off the left edge. */}
        <div className="flex w-fit max-w-full flex-wrap items-center justify-end gap-1 self-end">
        {zoomToolbar}
        {drawingViewToolbar}
        <div
          className={`${toolbarHidden ? "pointer-events-none" : "pointer-events-auto"} inline-flex h-8 w-fit items-center gap-0.5 self-end rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}
          onPointerEnter={onToolbarEnter}
          onPointerLeave={onToolbarLeave}
        >
          {previewMode ? (
            // Orbit mode: only tools that make sense while orbiting, plus an
            // explicit exit (X). No select/draw/pose/orbit/export here.
            <>
              {animationButton}
              {compact ? moreMenu : <>{screenshotButton}{captureButton}</>}
              <ToolbarButton label="Exit orbit" onClick={handleExitPreviewMode}>
                <X className="size-3" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>
            </>
          ) : (
            <>
              {/* Select/Pan/Draw. Pan and Draw are camera and 2D-overlay tools that
                  work against any viewport; Select is only meaningful where there is
                  something to pick. Each button asks the capability table, so enabling
                  one for a new format is a data change. */}
              {showToolCluster ? (
                <>
                  <ToolbarButton
                    label={selectLabel}
                    active={referenceSelectionDeferred ? false : selectionToolActive}
                    onClick={() => handleSelectTabToolMode("references")}
                    disabled={selectDisabled}
                    aria-pressed={referenceSelectionDeferred ? false : selectionToolActive}
                  >
                    <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  <ToolbarButton
                    label="Pan"
                    active={panToolActive}
                    onClick={() => handleSelectTabToolMode("pan")}
                    disabled={viewerLoading || !viewportContent}
                    aria-pressed={panToolActive}
                  >
                    <Hand className="size-3" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  <ToolbarButton
                    label="Measure"
                    active={measureModeActive}
                    onClick={() => handleSelectTabToolMode("measure")}
                    disabled={measureDisabled}
                    aria-pressed={measureModeActive}
                  >
                    <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  {!compact ? <>
                  <ToolbarButton
                    label="Draw"
                    active={drawToolActive}
                    onClick={() => handleSelectTabToolMode("draw")}
                    disabled={viewerLoading || !viewportContent}
                    aria-pressed={drawToolActive}
                  >
                    <PenTool className="size-3" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  {animationButton}
                  </> : null}
                </>
              ) : null}

              {compact ? moreMenu : <>
              <ToolbarButton
                label="Orbit"
                onClick={handleEnterPreviewMode}
                disabled={captureDisabled}
              >
                <Orbit className="size-3" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>

              {screenshotButton}
              {captureButton}
              </>}
            </>
          )}
        </div>
        </div>
      </TooltipProvider>


      {!previewMode && supportsTool(renderFormat, "draw") && drawToolActive ? (
        <DrawingToolbar
          className={`${CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS} max-w-full`}
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
      selectedEntry={selectedEntry}
      previewMode={previewMode}
      toolbarHidden={toolbarHidden}
      onToolbarEnter={onToolbarEnter}
      onToolbarLeave={onToolbarLeave}
      {...toolbarProps}
    />
  );
}
