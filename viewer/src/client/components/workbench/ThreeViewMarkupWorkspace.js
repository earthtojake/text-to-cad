"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftRight,
  ArrowRight,
  Circle,
  ClipboardCopy,
  Download,
  Eraser,
  Images,
  Minus,
  PaintBucket,
  PenTool,
  RotateCcw,
  Square,
  Upload
} from "lucide-react";
import CadViewer from "../CadViewer";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "../ui/dialog";
import { Textarea } from "../ui/textarea";
import { triggerBlobDownload } from "@/ui/download";
import { copyTextToClipboard } from "@/ui/clipboard";
import { DRAWING_TOOL } from "@/workbench/constants";
import DrawingToolbar from "./DrawingToolbar";
import {
  buildThreeViewMarkupDocument,
  emptyThreeViewMarkupState,
  markupFilenameStem,
  parseThreeViewMarkupDocument,
  THREE_VIEW_MARKUP_INTENTS,
  THREE_VIEW_MARKUP_VIEWS,
  viewStateFromThreeViewMarkupDocument
} from "@/workbench/threeViewMarkup";
import { cn } from "@/ui/utils";

const DRAWING_TOOL_OPTIONS = [
  { id: DRAWING_TOOL.FREEHAND, label: "Freehand", Icon: PenTool },
  { id: DRAWING_TOOL.LINE, label: "Line", Icon: Minus },
  { id: DRAWING_TOOL.ARROW, label: "Arrow", Icon: ArrowRight },
  { id: DRAWING_TOOL.DOUBLE_ARROW, label: "Expand / rotate", Icon: ArrowLeftRight },
  { id: DRAWING_TOOL.RECTANGLE, label: "Rectangle", Icon: Square },
  { id: DRAWING_TOOL.CIRCLE, label: "Circle", Icon: Circle },
  { id: DRAWING_TOOL.FILL, label: "Fill", Icon: PaintBucket },
  { id: DRAWING_TOOL.ERASE, label: "Erase", Icon: Eraser }
];

function emptyHistory() {
  return Object.fromEntries(
    THREE_VIEW_MARKUP_VIEWS.map((view) => [
      view.id,
      {
        undo: [],
        redo: []
      }
    ])
  );
}

function cloneStrokes(strokes) {
  return Array.isArray(strokes)
    ? strokes.map((stroke) => ({
      ...stroke,
      points: Array.isArray(stroke?.points)
        ? stroke.points.map((point) => ({ ...point }))
        : [],
      ...(Array.isArray(stroke?.fillPoints)
        ? { fillPoints: stroke.fillPoints.map((point) => ({ ...point })) }
        : {})
    }))
    : [];
}

function ThreeViewPanel({
  definition,
  meshData,
  modelKey,
  renderFormat,
  themeSettings,
  displaySettings,
  drawingTool,
  drawingStyle,
  strokes,
  onStrokesChange,
  registerViewer
}) {
  const viewerRef = useRef(null);

  const setViewerRef = useCallback((instance) => {
    viewerRef.current = instance;
    registerViewer(definition.id, instance);
  }, [definition.id, registerViewer]);

  useEffect(() => {
    let cancelled = false;
    const timers = [];

    const orientAndFit = () => {
      if (cancelled) {
        return;
      }
      const focused = viewerRef.current?.focusViewPreset?.(definition.cameraPreset, {
        animate: false
      });
      if (!focused) {
        return;
      }
      viewerRef.current?.zoomToFit?.({ animate: false });
    };

    for (const delay of [0, 650, 1500]) {
      timers.push(globalThis.setTimeout(orientAndFit, delay));
    }
    return () => {
      cancelled = true;
      timers.forEach((timer) => globalThis.clearTimeout(timer));
    };
  }, [definition.cameraPreset, meshData, modelKey]);

  return (
    <section
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-primary bg-background/70 shadow-sm ring-2 ring-primary/20"
    >
      <div className="flex items-center justify-between border-b bg-muted/55 px-3 py-1.5">
        <div>
          <h3 className="text-sm font-semibold">{definition.label}</h3>
          <p className="text-[11px] text-muted-foreground">
            {definition.plane} plane · right {definition.screenAxes.right} · up {definition.screenAxes.up}
          </p>
        </div>
        <span className="rounded bg-background/80 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {strokes.length} mark{strokes.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="relative min-h-[180px] flex-1 bg-background">
        <CadViewer
          ref={setViewerRef}
          meshData={meshData}
          modelKey={`${modelKey || "cad-part"}:three-view-markup`}
          renderFormat={renderFormat}
          projection="orthographic"
          showViewPlane={false}
          previewMode={false}
          themeSettings={themeSettings}
          displaySettings={displaySettings ? {
            ...displaySettings,
            projection: "orthographic"
          } : null}
          drawingEnabled
          drawingTool={drawingTool}
          drawingStyle={drawingStyle}
          drawingStrokes={strokes}
          onDrawingStrokesChange={onStrokesChange}
        />
      </div>
    </section>
  );
}

export default function ThreeViewMarkupWorkspace({
  open,
  onOpenChange,
  meshData,
  modelKey = "",
  sourceFile = "",
  renderFormat = "step",
  themeSettings = null,
  displaySettings = null
}) {
  const [drawingTool, setDrawingTool] = useState(DRAWING_TOOL.FREEHAND);
  const [activeIntentId, setActiveIntentId] = useState("remove");
  const [activeViewId, setActiveViewId] = useState("front");
  const [viewState, setViewState] = useState(emptyThreeViewMarkupState);
  const [history, setHistory] = useState(emptyHistory);
  const [overallNote, setOverallNote] = useState("");
  const [status, setStatus] = useState("");
  const importInputRef = useRef(null);
  const activeViewerRef = useRef(null);

  const activeIntent = useMemo(
    () => THREE_VIEW_MARKUP_INTENTS.find((intent) => intent.id === activeIntentId) ||
      THREE_VIEW_MARKUP_INTENTS[0],
    [activeIntentId]
  );
  const drawingStyle = useMemo(() => ({
    intent: activeIntent.id,
    color: activeIntent.color,
    fillColor: activeIntent.fillColor,
    haloColor: "rgba(255, 255, 255, 0.94)"
  }), [activeIntent]);
  const activeStrokes = viewState[activeViewId]?.strokes || [];
  const activeHistory = history[activeViewId] || { undo: [], redo: [] };
  const activeViewDefinition = THREE_VIEW_MARKUP_VIEWS.find((view) => view.id === activeViewId) ||
    THREE_VIEW_MARKUP_VIEWS[0];
  const filenameStem = markupFilenameStem(sourceFile);

  const registerViewer = useCallback((_viewId, instance) => {
    activeViewerRef.current = instance;
  }, []);

  const updateViewStrokes = useCallback((viewId, nextStrokes) => {
    const previous = cloneStrokes(viewState[viewId]?.strokes);
    setHistory((currentHistory) => ({
      ...currentHistory,
      [viewId]: {
        undo: [...(currentHistory[viewId]?.undo || []), previous],
        redo: []
      }
    }));
    setViewState((current) => {
      return {
        ...current,
        [viewId]: {
          ...current[viewId],
          strokes: cloneStrokes(nextStrokes)
        }
      };
    });
    setStatus("");
  }, [viewState]);

  const updateViewNote = useCallback((viewId, note) => {
    setViewState((current) => ({
      ...current,
      [viewId]: {
        ...current[viewId],
        note
      }
    }));
  }, []);

  const handleUndo = useCallback(() => {
    const viewId = activeViewId;
    const undo = history[viewId]?.undo || [];
    if (!undo.length) {
      return;
    }
    const previous = undo[undo.length - 1];
    setViewState((currentState) => ({
      ...currentState,
      [viewId]: {
        ...currentState[viewId],
        strokes: cloneStrokes(previous)
      }
    }));
    setHistory((currentHistory) => ({
      ...currentHistory,
      [viewId]: {
        undo: undo.slice(0, -1),
        redo: [
          ...(currentHistory[viewId]?.redo || []),
          cloneStrokes(viewState[viewId]?.strokes)
        ]
      }
    }));
  }, [activeViewId, history, viewState]);

  const handleRedo = useCallback(() => {
    const viewId = activeViewId;
    const redo = history[viewId]?.redo || [];
    if (!redo.length) {
      return;
    }
    const next = redo[redo.length - 1];
    setViewState((currentState) => ({
      ...currentState,
      [viewId]: {
        ...currentState[viewId],
        strokes: cloneStrokes(next)
      }
    }));
    setHistory((currentHistory) => ({
      ...currentHistory,
      [viewId]: {
        undo: [
          ...(currentHistory[viewId]?.undo || []),
          cloneStrokes(viewState[viewId]?.strokes)
        ],
        redo: redo.slice(0, -1)
      }
    }));
  }, [activeViewId, history, viewState]);

  const handleClear = useCallback(() => {
    if (!activeStrokes.length) {
      return;
    }
    updateViewStrokes(activeViewId, []);
  }, [activeStrokes.length, activeViewId, updateViewStrokes]);

  const handleResetView = useCallback(() => {
    const viewer = activeViewerRef.current;
    viewer?.focusViewPreset?.(activeViewDefinition.cameraPreset, { animate: false });
    viewer?.zoomToFit?.({ animate: false });
    setStatus(`Reset the ${activeViewDefinition.label.toLowerCase()} view.`);
  }, [activeViewDefinition]);

  const handleExportMarkup = useCallback(() => {
    const document = buildThreeViewMarkupDocument({
      sourceFile,
      modelKey,
      renderFormat,
      overallNote,
      viewState
    });
    const blob = new Blob([`${JSON.stringify(document, null, 2)}\n`], {
      type: "application/json"
    });
    triggerBlobDownload(blob, {
      filename: `${filenameStem}-three-view-markup.json`
    });
    setStatus("Markup JSON downloaded.");
  }, [filenameStem, modelKey, overallNote, renderFormat, sourceFile, viewState]);

  const handleCopyForCodex = useCallback(async () => {
    const document = buildThreeViewMarkupDocument({
      sourceFile,
      modelKey,
      renderFormat,
      overallNote,
      viewState,
      includeEmptyViews: false
    });
    try {
      await copyTextToClipboard(JSON.stringify(document, null, 2));
      const viewCount = document.views.length;
      setStatus(
        `Copied for Codex with ${viewCount} changed view${viewCount === 1 ? "" : "s"}. Paste it into your Codex task to submit.`
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not copy the markup.");
    }
  }, [modelKey, overallNote, renderFormat, sourceFile, viewState]);

  const handleExportCurrentImage = useCallback(async () => {
    setStatus(`Preparing the ${activeViewDefinition.label.toLowerCase()} PNG…`);
    try {
      const viewer = activeViewerRef.current;
      if (!viewer?.captureScreenshot) {
        throw new Error(`${activeViewDefinition.label} view is not ready yet.`);
      }
      await viewer.captureScreenshot({
        filename: `${filenameStem}-${activeViewDefinition.id}-markup.png`,
        mode: "download"
      });
      setStatus(`${activeViewDefinition.label} PNG downloaded.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not export the image.");
    }
  }, [activeViewDefinition, filenameStem]);

  const handleImportMarkup = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    try {
      const document = parseThreeViewMarkupDocument(await file.text());
      setViewState(viewStateFromThreeViewMarkupDocument(document));
      setOverallNote(document.overallNote);
      setHistory(emptyHistory());
      setStatus(`Loaded ${file.name}.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not import markup.");
    }
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="h-[calc(100svh-1rem)] max-h-[calc(100svh-1rem)] w-[calc(100vw-1rem)] max-w-[calc(100vw-1rem)] grid-rows-[auto_auto_minmax(0,1fr)_auto] gap-3 overflow-hidden p-3 sm:!max-w-[calc(100vw-1rem)]"
      >
        <DialogHeader className="pr-10">
          <DialogTitle>Orthographic Markup</DialogTitle>
          <DialogDescription>
            Switch between all six fixed orthographic views. Each view keeps its own marks and typed note; the JSON preserves all six.
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-w-0 flex-col gap-2 rounded-md border bg-muted/35 p-2 xl:flex-row xl:items-center">
          <DrawingToolbar
            className="min-w-0 flex-1"
            layout="scroll"
            drawingToolOptions={DRAWING_TOOL_OPTIONS}
            drawingTool={drawingTool}
            handleSelectDrawingTool={setDrawingTool}
            handleUndoDrawing={handleUndo}
            handleRedoDrawing={handleRedo}
            handleClearDrawings={handleClear}
            canUndoDrawing={activeHistory.undo.length > 0}
            canRedoDrawing={activeHistory.redo.length > 0}
            drawingStrokes={activeStrokes}
          />

          <div className="flex flex-wrap items-center gap-1.5" aria-label="Markup intent">
            {THREE_VIEW_MARKUP_INTENTS.map((intent) => {
              const active = intent.id === activeIntent.id;
              return (
                <button
                  key={intent.id}
                  type="button"
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition",
                    active
                      ? "border-foreground/30 bg-background text-foreground shadow-sm"
                      : "border-transparent text-muted-foreground hover:bg-background/70 hover:text-foreground"
                  )}
                  aria-pressed={active}
                  onClick={() => setActiveIntentId(intent.id)}
                >
                  <span
                    className="size-2.5 rounded-full border border-black/10"
                    style={{ backgroundColor: intent.color }}
                    aria-hidden="true"
                  />
                  {intent.label}
                </button>
              );
            })}
          </div>

          <Button variant="outline" size="sm" onClick={handleResetView}>
            <RotateCcw aria-hidden="true" />
            Reset view
          </Button>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <div className="grid grid-cols-3 gap-1 rounded-md border bg-muted/35 p-1 sm:grid-cols-6">
            {THREE_VIEW_MARKUP_VIEWS.map((definition) => {
              const active = definition.id === activeViewId;
              const markCount = viewState[definition.id]?.strokes?.length || 0;
              return (
                <button
                  key={definition.id}
                  type="button"
                  className={cn(
                    "rounded-md px-3 py-2 text-sm font-medium transition",
                    active
                      ? "bg-background text-foreground shadow-sm ring-1 ring-border"
                      : "text-muted-foreground hover:bg-background/65 hover:text-foreground"
                  )}
                  aria-pressed={active}
                  onClick={() => {
                    setActiveViewId(definition.id);
                    setStatus("");
                  }}
                >
                  {definition.label}
                  <span className="ml-2 text-[11px] font-normal text-muted-foreground">
                    {markCount} mark{markCount === 1 ? "" : "s"}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(0,3fr)_minmax(260px,1fr)]">
            <ThreeViewPanel
              definition={activeViewDefinition}
              meshData={meshData}
              modelKey={modelKey}
              renderFormat={renderFormat}
              themeSettings={themeSettings}
              displaySettings={displaySettings}
              drawingTool={drawingTool}
              drawingStyle={drawingStyle}
              strokes={activeStrokes}
              onStrokesChange={(strokes) => updateViewStrokes(activeViewId, strokes)}
              registerViewer={registerViewer}
            />

            <section className="flex min-h-0 flex-col gap-3 overflow-auto rounded-md border bg-muted/25 p-3">
              <div>
                <label
                  className="text-sm font-semibold"
                  htmlFor={`three-view-note-${activeViewId}`}
                >
                  {activeViewDefinition.label} view note
                </label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Type the exact change, dimension, angle, pivot, or clearance for this view.
                </p>
                <Textarea
                  id={`three-view-note-${activeViewId}`}
                  value={viewState[activeViewId]?.note || ""}
                  onChange={(event) => updateViewNote(activeViewId, event.target.value)}
                  placeholder={`What should change in the ${activeViewDefinition.label.toLowerCase()} view?`}
                  className="mt-2 min-h-32 resize-y bg-background/75"
                />
              </div>

              <div className="border-t pt-3">
                <label className="text-sm font-semibold" htmlFor="three-view-overall-note">
                  Overall instructions
                </label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Include details that apply across all six views.
                </p>
                <Textarea
                  id="three-view-overall-note"
                  value={overallNote}
                  onChange={(event) => setOverallNote(event.target.value)}
                  placeholder="Example: cut the red region, rotate the blue end 35° clockwise, and preserve the STS3215 mounting holes."
                  className="mt-2 min-h-40 resize-y bg-background/75"
                />
              </div>

              <div className="mt-auto rounded-md border bg-background/60 p-2 text-xs text-muted-foreground">
                Active view: <span className="font-medium text-foreground">{activeViewDefinition.label}</span>. Marks use normalized image coordinates and CAD Z-up axes.
                <span className="mt-1 block">Copy for Codex includes only views with marks or typed notes.</span>
              </div>
            </section>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <p className="min-h-5 text-xs text-muted-foreground" role="status">
            {status || "Tip: use arrows for movement, rectangles/circles for regions, and notes for exact dimensions."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={handleImportMarkup}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => importInputRef.current?.click()}
            >
              <Upload aria-hidden="true" />
              Import JSON
            </Button>
            <Button variant="outline" size="sm" onClick={handleExportCurrentImage}>
              <Images aria-hidden="true" />
              Download current PNG
            </Button>
            <Button variant="outline" size="sm" onClick={handleExportMarkup}>
              <Download aria-hidden="true" />
              Export markup JSON
            </Button>
            <Button size="sm" onClick={handleCopyForCodex}>
              <ClipboardCopy aria-hidden="true" />
              Copy for Codex
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
