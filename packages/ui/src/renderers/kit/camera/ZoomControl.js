import { useContext } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { FileSheetPortalContext } from "../inspector/FileSheet.js";

const MIN_PERCENT = 10;
const MAX_PERCENT = 800;
export function normalizeZoomPercent(value, fallback = 100) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, numeric)) : fallback;
}

// The header is a readout, not an input. All camera operations stay with the
// owning viewport; this menu never owns or persists another zoom value.
//
// "Zoom to 100%" and "Reset Zoom" are not the same act and both are offered:
// 100% sets the zoom number and leaves the pan alone, while Reset Zoom re-frames
// the model — zoom AND pan back to the opening framing — without turning the
// camera. Neither changes which way the model is being looked at.
export function ZoomControl({ zoomPercent = 100, onZoomPercentChange, onResetZoom,
  onZoomFit, onZoomSelection, selectionAvailable = false, disabled = false }) {
  const boundary = useContext(FileSheetPortalContext);
  const adjust = delta => onZoomPercentChange?.(normalizeZoomPercent(Math.round(zoomPercent) + delta));
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label="Zoom controls" title="Zoom and reset" disabled={disabled}
        className="h-7 shrink-0 rounded-sm px-1.5 text-micro font-normal tabular-nums text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
        <span aria-label="Zoom level percent">{`${Math.round(Number(zoomPercent) || 100)}%`}</span>
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" sideOffset={4} collisionBoundary={boundary} className="w-48">
      <DropdownMenuItem onSelect={() => adjust(10)}>Zoom in</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => adjust(-10)}>Zoom out</DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onZoomPercentChange?.(100)}>Zoom to 100%</DropdownMenuItem>
      <DropdownMenuItem onSelect={onZoomFit}>Zoom to fit</DropdownMenuItem>
      <DropdownMenuItem disabled={!selectionAvailable} onSelect={onZoomSelection}>Zoom to selection</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={onResetZoom} title="Frame the model again; keep the direction it is looked at from">Reset Zoom</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}
