import { useEffect, useRef, useState } from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";

// Extracted from CadViewer so the zoom pill can live in the shared top-right toolbar row
// (FloatingToolBar) while the camera math stays in the viewer. One control, two hosts.

const DISPLAY_TOOLBAR_BUTTON_CLASSES = "grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50";
const ZOOM_CONTROL_CONTENT_WIDTH = "6.875rem";
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
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState(formatZoomPercent(zoomPercent));
  const selectOnFocusRef = useRef(false);
  useEffect(() => {
    if (!editing) {
      setInputValue(formatZoomPercent(zoomPercent));
    }
  }, [editing, zoomPercent]);

  const commitInputValue = () => {
    const numericValue = Number(String(inputValue || "").replace(/%/g, "").trim());
    setEditing(false);
    if (!Number.isFinite(numericValue) || numericValue <= 0) {
      const resetValue = 100;
      setInputValue(formatZoomPercent(resetValue));
      onZoomPercentChange?.(resetValue);
      return;
    }
    onZoomPercentChange?.(normalizeZoomPercent(numericValue));
  };
  const adjustZoom = (delta) => {
    onZoomPercentChange?.(normalizeZoomPercent(Math.round(zoomPercent) + delta));
  };

  return (
    <div
      className="flex h-6 items-center gap-0.5"
      style={{ width: ZOOM_CONTROL_CONTENT_WIDTH }}
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
      <input
        type="text"
        inputMode="numeric"
        aria-label="Zoom level percent"
        className="h-6 w-8 min-w-0 rounded-sm border border-transparent bg-transparent px-0 text-center text-xs font-medium tabular-nums text-sidebar-foreground outline-none transition focus-visible:border-ring focus-visible:bg-sidebar-accent/40 focus-visible:ring-2 focus-visible:ring-ring/35"
        value={inputValue}
        onFocus={(event) => {
          const input = event.currentTarget;
          selectOnFocusRef.current = true;
          setEditing(true);
          setInputValue(String(Math.round(zoomPercent)));
          window.requestAnimationFrame(() => {
            if (!selectOnFocusRef.current) {
              return;
            }
            input.select();
            selectOnFocusRef.current = false;
          });
        }}
        onMouseUp={(event) => {
          if (!selectOnFocusRef.current) {
            return;
          }
          event.preventDefault();
          event.currentTarget.select();
          selectOnFocusRef.current = false;
        }}
        onClick={(event) => {
          if (String(event.currentTarget.value || "").includes("%")) {
            event.currentTarget.select();
          }
        }}
        onChange={(event) => {
          // Typing cancels the deferred focus-select, or the first digit gets re-selected
          // and the second overwrites it.
          selectOnFocusRef.current = false;
          setInputValue(event.target.value);
        }}
        onBlur={commitInputValue}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commitInputValue();
          } else if (event.key === "Escape") {
            event.preventDefault();
            setEditing(false);
            setInputValue(formatZoomPercent(zoomPercent));
            event.currentTarget.blur();
          }
        }}
      />
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

