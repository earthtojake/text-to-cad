import { useContext, useEffect, useState } from "react";
import { ScanSearch } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ViewerHostContext } from "../../../host/context.js";
import { ZOOM_FACTOR, zoomShortcuts } from "../tools/toolShortcuts.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";

export { ZOOM_FACTOR };

/**
 * The view's zoom, as every design tool shows it (Figma's, Spline's, Penpot's, tldraw's): the zoom as a
 * percentage, and, pressed, the zoom's menu — Zoom in, Zoom out, Zoom to 100%, then Zoom to fit and Zoom to
 * selection (off with nothing picked), each with its key (`zoomShortcuts`; the view's keys, `pressZoomKey`). It is the strip's view control, the same in every view, 2D and 3D.
 *
 * 100% is the model as authored, framed whole (a flat view's fit, a 3D view's rest box at the camera's
 * angle): a fixed ruler, which nothing shown moves — not a pose, a routine, a cut, parts spread apart, hiding or
 * isolating. Zoom to fit frames what is SHOWN, so it may read 72% with the parts spread apart.
 *
 * The number is the view's, read through `zoom.read()` and redrawn at most once a frame as the view tells
 * it moved (`zoom.subscribe(listener)`, which hands back its unsubscribe); nothing else re-renders. Its
 * digits are tabular and its width is fixed, so the strip never shifts as it changes.
 *
 * @param {{ zoom: ViewZoom, disabled?: boolean, tooltipSide?: "top" | "bottom" }} props
 * @typedef {{ read(): number, subscribe(listener: () => void): () => void, zoomBy(factor: number): void, fit(): void,
 *   zoomTo100?: (() => void) | null, zoomToSelection?: (() => void) | null, selectionAvailable?: boolean }} ViewZoom
 */
export default function ZoomControl({ zoom, disabled = false, tooltipSide = "top" }) {
  const { t } = useI18n();
  const tileClass = useStripButtonClass();
  const percent = useZoomPercent(zoom);
  const shown = `${Math.round(percent).toLocaleString()}%`;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton label={t("zoom.current", { percent: shown })} tooltip={t("zoom.label")} tooltipSide={tooltipSide} disabled={disabled}
        className={cn(tileClass, "w-[3.25rem] px-1 text-tiny font-medium tabular-nums")} data-zoom-control="">
        <span className="w-full text-center">{shown}</span>
      </ToolbarButton>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="center" sideOffset={6} collisionPadding={8} aria-label={t("zoom.label")}
      className={cn(FLOATING_SURFACE_CLASS, "w-48 data-[state=closed]:animate-none!")}>
      <ZoomMenuItems zoom={zoom} />
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** The zoom menu's items, for the tile's menu and a phone's More submenu alike. */
export function ZoomMenuItems({ zoom }) {
  const { t } = useI18n();
  const keys = zoomShortcuts(useContext(ViewerHostContext)?.environment?.platform);
  const item = (label, shortcut, onSelect, disabled = false) => <DropdownMenuItem className="text-xs" disabled={disabled} onSelect={onSelect}>
    {label}<DropdownMenuShortcut>{shortcut}</DropdownMenuShortcut>
  </DropdownMenuItem>;
  return <>
    {item(t("zoom.in"), keys.in, () => zoom.zoomBy(ZOOM_FACTOR))}
    {item(t("zoom.out"), keys.out, () => zoom.zoomBy(1 / ZOOM_FACTOR))}
    {item(t("zoom.to100"), keys.actual, () => (zoom.zoomTo100 ? zoom.zoomTo100() : zoom.fit()))}
    <DropdownMenuSeparator />
    {item(t("menu.zoomToFit"), keys.fit, () => zoom.fit())}
    {item(t("menu.zoomToSelection"), keys.selection, () => zoom.zoomToSelection?.(), !zoom.zoomToSelection || !zoom.selectionAvailable)}
  </>;
}

/** The zoom's view-control descriptor for the strip (`FloatingToolBar`): the tile, and a phone's More submenu. */
export function zoomViewControl(zoom, { t, disabled = false }) {
  return { id: "zoom", label: t("zoom.label"), icon: <ScanSearch aria-hidden="true" />, disabled,
    tile: <ZoomControl zoom={zoom} disabled={disabled} />, submenu: () => <ZoomMenuItems zoom={zoom} /> };
}

/** The view's zoom, live: read again at most once a frame after the view says it moved. */
function useZoomPercent(zoom) {
  const { read, subscribe } = zoom;
  const [percent, setPercent] = useState(() => read());
  useEffect(() => {
    let frame = 0;
    const update = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => { frame = 0; setPercent(read()); });
    };
    const unsubscribe = subscribe(update);
    update();
    return () => { unsubscribe?.(); if (frame) cancelAnimationFrame(frame); };
  }, [read, subscribe]);
  return percent;
}
