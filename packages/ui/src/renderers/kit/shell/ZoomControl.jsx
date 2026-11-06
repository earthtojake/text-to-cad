import { useContext, useEffect, useState } from "react";
import { Minus, Plus, ScanSearch } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ViewerHostContext } from "../../../host/context.js";
import { ZOOM_FACTOR, zoomShortcuts } from "../tools/toolShortcuts.js";
import { VIEW_CORNER_SURFACE_CLASS } from "./ViewCorner.jsx";

export { ZOOM_FACTOR };

/**
 * A flat view's zoom, in the view's corner (`ViewCorner.jsx`), as a canvas tool keeps it (tldraw's,
 * Excalidraw's, Miro's): − and + either side of the zoom as a percentage, on one see-through pill, and the
 * percentage pressed opens the zoom's menu — Zoom in, Zoom out, Zoom to 100%, then Zoom to fit and Zoom to
 * selection (off with nothing picked), each with its key (`zoomShortcuts`; the view's keys, `pressZoomKey`).
 * A 3D view shows no percentage: its corner is the cube's, with Zoom to fit over it.
 *
 * 100% is the picture as authored, framed whole (a flat view's fit): a fixed ruler, which nothing shown
 * moves. The number is the view's, read through `zoom.read()` and redrawn at most once a frame as the view
 * tells it moved (`zoom.subscribe(listener)`, which hands back its unsubscribe); nothing else re-renders. Its
 * digits are tabular and its width is fixed, so the pill never shifts as it changes.
 *
 * @param {{ zoom: ViewZoom, style?: object }} props
 * @typedef {{ read(): number, subscribe(listener: () => void): () => void, zoomBy(factor: number): void, fit(): void,
 *   zoomTo100?: (() => void) | null, zoomToSelection?: (() => void) | null, selectionAvailable?: boolean }} ViewZoom
 */
const PILL_BUTTON_CLASS = "size-7 rounded-full border-0 bg-transparent text-muted-foreground shadow-none hover:bg-foreground/[0.1] hover:text-foreground [&>svg]:size-3.5!";
export default function ZoomPill({ zoom, style = null }) {
  const { t } = useI18n();
  const keys = zoomShortcuts(useContext(ViewerHostContext)?.environment?.platform);
  const percent = useZoomPercent(zoom);
  const shown = `${Math.round(percent).toLocaleString()}%`;
  return <div className={cn("pointer-events-auto absolute z-20 inline-flex h-7 items-center rounded-full", VIEW_CORNER_SURFACE_CLASS)} style={style ?? undefined} data-zoom-pill="">
    <ToolbarButton label={t("zoom.out")} shortcut={keys.out} tooltipSide="top" className={PILL_BUTTON_CLASS} onClick={() => zoom.zoomBy(1 / ZOOM_FACTOR)}>
      <Minus aria-hidden="true" />
    </ToolbarButton>
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <ToolbarButton label={t("zoom.current", { percent: shown })} tooltip={t("zoom.label")} tooltipSide="top"
          className={cn(PILL_BUTTON_CLASS, "w-12 px-0 text-tiny font-medium tabular-nums text-foreground aria-expanded:bg-foreground/[0.1]")} data-zoom-control="">
          <span className="w-full text-center">{shown}</span>
        </ToolbarButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="end" sideOffset={6} collisionPadding={8} aria-label={t("zoom.label")}
        className={cn(FLOATING_SURFACE_CLASS, "w-48 data-[state=closed]:animate-none!")}>
        <ZoomMenuItems zoom={zoom} />
      </DropdownMenuContent>
    </DropdownMenu>
    <ToolbarButton label={t("zoom.in")} shortcut={keys.in} tooltipSide="top" className={PILL_BUTTON_CLASS} onClick={() => zoom.zoomBy(ZOOM_FACTOR)}>
      <Plus aria-hidden="true" />
    </ToolbarButton>
  </div>;
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

/** The zoom as a phone's More submenu (`FloatingToolBar`): a phone has no corner, its view's controls are More's rows. */
export function zoomViewControl(zoom, { t, disabled = false }) {
  return { id: "zoom", label: t("zoom.label"), icon: <ScanSearch aria-hidden="true" />, disabled,
    tile: null, submenu: () => <ZoomMenuItems zoom={zoom} /> };
}

/**
 * A 3D view's zoom (`ViewZoom`), read live through its viewport (`ShellViewport.jsx`'s handle in
 * `viewerRef`): the zoom against the authored box, its steps about the camera's target, and word of the
 * camera moving. What the zoom's keys and a phone's More reach in every 3D view, a renderer's own frame
 * or a flat view's frame showing one alike.
 * @returns {ViewZoom}
 */
export function viewportZoom(viewerRef) {
  return {
    read: () => viewerRef.current?.zoomPercent?.() ?? 100,
    subscribe: listener => viewerRef.current?.subscribeCamera?.(listener) || (() => {}),
    zoomBy: factor => viewerRef.current?.zoomBy?.(factor),
    zoomTo100: () => viewerRef.current?.zoomTo100?.(),
    fit: () => viewerRef.current?.resetZoom?.()
  };
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
