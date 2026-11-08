import { useContext, useEffect, useState } from "react";
import { Minus, Plus, ScanSearch } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ViewerHostContext } from "../../../host/context.js";
import { STRIP_BUTTON_CLASS, STRIP_SHAPE_CLASS } from "../tools/stripTouch.js";
import { ZOOM_FACTOR, zoomShortcuts } from "../tools/toolShortcuts.js";
import { useViewCornerSide, viewCornerAway } from "./ViewCorner.jsx";
import { viewCornerLayout } from "./viewportLayout.js";

export { ZOOM_FACTOR };

// The pill is a floating toolbar of its own: the strip's shape on the strip's surface (`FloatingToolBar.js`), its
// tiles inside the strip's padding, so it is as tall as the strip (34px with its border) and reads as the same object.
const PILL_CLASS = cn("pointer-events-auto absolute z-20 inline-flex shrink-0", STRIP_SHAPE_CLASS, FLOATING_CHROME_SURFACE_CLASS);
// Its percentage: a tile 48px wide, its digits tabular, lit while the menu it opens is up.
const PERCENT_CLASS = cn(STRIP_BUTTON_CLASS, "w-12 px-0 text-tiny font-medium tabular-nums aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

/**
 * A flat view's zoom, the one thing in the view's corner (`ViewCorner.jsx`), as a canvas tool keeps it (tldraw's,
 * Excalidraw's, Miro's): − and + either side of the zoom as a percentage, the strip's tiles in a floating toolbar
 * of its own (the strip's shape and surface, 34px tall), and the percentage pressed opens the zoom's menu — Zoom in,
 * Zoom out, Zoom to 100%, then Zoom to fit and Zoom to selection (off with nothing picked), each with its key
 * (`zoomShortcuts`; the view's keys, `pressZoomKey`).
 * A 3D view shows no percentage: its corner is the cube's alone. A flat view that draws its
 * picture in 3D keeps its pill, which zooms the 3D camera (`viewportZoom`).
 *
 * 100% is the picture as authored, framed whole (a flat view's fit; in 3D the 3D views' own ruler, the
 * authored box at the camera's angle): a fixed ruler, which nothing shown
 * moves. The number is the view's, read through `zoom.read()` and redrawn at most once a frame as the view
 * tells it moved (`zoom.subscribe(listener)`, which hands back its unsubscribe); nothing else re-renders. Its
 * digits are tabular and its width is fixed, so the pill never shifts as it changes.
 *
 * It stands in the corner wherever the host anchors it, the corner's inset from the edges (`viewCornerLayout`'s
 * `pill`), unless `style` places it.
 *
 * @param {{ zoom: ViewZoom, style?: object }} props
 * @typedef {{ read(): number, subscribe(listener: () => void): () => void, zoomBy(factor: number): void, fit(): void,
 *   zoomTo100?: (() => void) | null, zoomToSelection?: (() => void) | null, selectionAvailable?: boolean }} ViewZoom
 */
export default function ZoomPill({ zoom, style = null }) {
  const { t } = useI18n();
  const keys = zoomShortcuts(useContext(ViewerHostContext)?.environment?.platform);
  const percent = useZoomPercent(zoom);
  const shown = `${Math.round(percent).toLocaleString()}%`;
  const side = useViewCornerSide();
  return <div className={PILL_CLASS} style={style ?? viewCornerLayout(side).pill} data-zoom-pill="">
    <ToolbarButton label={t("zoom.out")} shortcut={keys.out} tooltipSide="top" className={STRIP_BUTTON_CLASS} onClick={() => zoom.zoomBy(1 / ZOOM_FACTOR)}>
      <Minus aria-hidden="true" />
    </ToolbarButton>
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <ToolbarButton label={t("zoom.current", { percent: shown })} tooltip={t("zoom.label")} tooltipSide="top" className={PERCENT_CLASS} data-zoom-control="">
          <span className="w-full text-center">{shown}</span>
        </ToolbarButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align={viewCornerAway(side).align} sideOffset={6} collisionPadding={8} aria-label={t("zoom.label")}
        className={cn(FLOATING_SURFACE_CLASS, "w-48 data-[state=closed]:animate-none!")}>
        <ZoomMenuItems zoom={zoom} />
      </DropdownMenuContent>
    </DropdownMenu>
    <ToolbarButton label={t("zoom.in")} shortcut={keys.in} tooltipSide="top" className={STRIP_BUTTON_CLASS} onClick={() => zoom.zoomBy(ZOOM_FACTOR)}>
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
 * or a flat view's frame showing one alike, and a flat view's pill while its picture is in 3D. It hears the
 * camera of the viewport up when it is subscribed: an owner whose viewport comes up later makes it again
 * once it is (a new `subscribe`, which the pill subscribes again).
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
