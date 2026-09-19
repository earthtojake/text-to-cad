import { Minus, Plus, RotateCcw } from "lucide-react";

// Camera math stays in the viewer; this compact control only reports the live
// value and asks the viewer to step or reset it.

const DISPLAY_TOOLBAR_BUTTON_CLASSES = "grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50";
const ZOOM_CONTROL_STEP_PERCENT = 10;

const ZOOM_CONTROL_MIN_PERCENT = 10;
const ZOOM_CONTROL_MAX_PERCENT = 800;

export function normalizeZoomPercent(value, fallback = 100) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.min(ZOOM_CONTROL_MAX_PERCENT, Math.max(ZOOM_CONTROL_MIN_PERCENT, numeric));
}

function formatZoomPercent(value) {
  return `${Math.round(Number(value) || 100)}%`;
}

export function ZoomControl({
  zoomPercent,
  onZoomPercentChange,
  onZoomReset
}) {
  const adjustZoom = (delta) => {
    onZoomPercentChange?.(normalizeZoomPercent(Math.round(zoomPercent) + delta));
  };

  return (
    <div
      role="group"
      className="flex h-6 items-center gap-0.5"
      aria-label="Zoom controls"
      onPointerDown={(event) => {
        event.stopPropagation();
      }}
    >
      <button
        type="button"
        aria-label="Zoom out"
        title="Zoom out"
        className={DISPLAY_TOOLBAR_BUTTON_CLASSES}
        onClick={(event) => {
          event.stopPropagation();
          adjustZoom(-ZOOM_CONTROL_STEP_PERCENT);
        }}
      >
        <Minus className="size-3" strokeWidth={2.25} aria-hidden="true" />
      </button>
      <span
        aria-label="Zoom level percent"
        className="inline-flex h-6 w-9 select-none items-center justify-center text-xs tabular-nums text-sidebar-foreground"
      >
        {formatZoomPercent(zoomPercent)}
      </span>
      <button
        type="button"
        aria-label="Zoom in"
        title="Zoom in"
        className={DISPLAY_TOOLBAR_BUTTON_CLASSES}
        onClick={(event) => {
          event.stopPropagation();
          adjustZoom(ZOOM_CONTROL_STEP_PERCENT);
        }}
      >
        <Plus className="size-3" strokeWidth={2.25} aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label="Reset view"
        title="Reset view"
        className={DISPLAY_TOOLBAR_BUTTON_CLASSES}
        onClick={(event) => {
          event.stopPropagation();
          onZoomReset?.();
        }}
      >
        <RotateCcw className="size-3" strokeWidth={2.1} aria-hidden="true" />
      </button>
    </div>
  );
}
