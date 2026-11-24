import { useContext, useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ViewerHostContext } from "../../../host/context.js";
import { prefersCoarsePointer } from "../viewport/dom.js";
import { ZOOM_FACTOR, zoomShortcuts } from "../tools/toolShortcuts.js";
import { useViewCornerSide } from "./ViewCorner.jsx";
import { viewCornerLayout } from "./viewportLayout.js";

export { ZOOM_FACTOR };

// The zoom: ONE control in the corner, its percentage and a small chevron on a faint resting surface (the foreground at
// 6%, a step more under the pointer and while its menu is open), so it reads as a control over the drawing; 28px tall,
// the digits tabular and as wide as their widest reading, so it never shifts as the zoom changes, haloed in the
// theme's background as the cube's glyphs are.
const PILL_CLASS = "pointer-events-auto absolute z-20 inline-flex shrink-0 items-center";
const ZOOM_BUTTON_CLASS = cn("h-control w-auto gap-0.5 rounded-md bg-foreground/6 px-2 text-tiny font-medium tabular-nums text-foreground/72 shadow-none",
  "hover:bg-foreground/10 hover:text-foreground dark:hover:bg-foreground/10 aria-expanded:bg-foreground/14 aria-expanded:text-foreground",
  "[text-shadow:0_0_1px_var(--background),0_0_2px_var(--background)] [&>svg]:size-3!");

/**
 * A flat view's zoom, the one thing in the view's corner (`ViewCorner.jsx`), as Figma keeps its: the zoom as a
 * percentage with a small chevron, no − or + of its own, pressed opening the zoom's menu — Zoom in, Zoom out, Zoom to
 * 100%, then Zoom to fit and Zoom to selection (off with nothing picked), each with its key (`zoomShortcuts`; the view's
 * keys, `pressZoomKey`; no key hints on a touch screen). The wheel, a pinch, a double-click and the keys zoom as before.
 * A 3D view shows no percentage: its corner is the cube's alone. A flat view that draws its picture in 3D (a board)
 * keeps it, and it zooms the 3D camera (`viewportZoom`); its way back is its own Zoom to fit.
 *
 * 100% is the picture as authored, framed whole (a flat view's fit; in 3D the 3D views' own ruler, the
 * authored box at the camera's angle): a fixed ruler, which nothing shown
 * moves. The number is the view's, read through `zoom.read()` and redrawn at most once a frame as the view
 * tells it moved (`zoom.subscribe(listener)`, which hands back its unsubscribe); nothing else re-renders.
 *
 * It stands in the corner wherever the host anchors it, its outer edge the corner's inset (12px) in and its middle on the tool
 * strip's (`viewCornerLayout`'s `pill`), unless `style` places it.
 *
 * @param {{ zoom: ViewZoom, style?: object }} props
 * @typedef {{ read(): number, subscribe(listener: () => void): () => void, zoomBy(factor: number): void, fit(): void,
 *   zoomTo100?: (() => void) | null, zoomToSelection?: (() => void) | null, selectionAvailable?: boolean }} ViewZoom
 */
export default function ZoomPill({ zoom, style = null }) {
  const { t } = useI18n();
  const percent = useZoomPercent(zoom);
  const shown = `${Math.round(percent).toLocaleString()}%`;
  const side = useViewCornerSide();
  return <div className={PILL_CLASS} style={style ?? viewCornerLayout(side).pill} data-zoom-pill="">
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <ToolbarButton label={t("zoom.current", { percent: shown })} tooltip={t("zoom.label")} tooltipSide="bottom" className={ZOOM_BUTTON_CLASS} data-zoom-control="">
          <span className="inline-block w-10 text-right">{shown}</span>
          <ChevronDown className="opacity-60" aria-hidden="true" />
        </ToolbarButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="bottom" align={side === "left" ? "start" : "end"} sideOffset={6} collisionPadding={8} aria-label={t("zoom.label")}
        className={cn(FLOATING_SURFACE_CLASS, "w-48 data-[state=closed]:animate-none!")}>
        <ZoomMenuItems zoom={zoom} />
      </DropdownMenuContent>
    </DropdownMenu>
  </div>;
}

/** The zoom menu's items. */
function ZoomMenuItems({ zoom }) {
  const { t } = useI18n();
  const keys = zoomShortcuts(useContext(ViewerHostContext)?.environment?.platform);
  // A touch screen has no keys to hint at.
  const touch = prefersCoarsePointer();
  const item = (label, shortcut, onSelect, disabled = false) => <DropdownMenuItem disabled={disabled} onSelect={onSelect}>
    {label}{touch ? null : <DropdownMenuShortcut>{shortcut}</DropdownMenuShortcut>}
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

/**
 * A 3D view's zoom (`ViewZoom`), read live through its viewport (`ShellViewport.jsx`'s handle in
 * `viewerRef`): the zoom against the authored box, its steps about the camera's target, and word of the
 * camera moving. What the zoom's keys reach in every 3D view, a renderer's own frame
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
