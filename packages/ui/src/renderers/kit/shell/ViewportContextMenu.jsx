import { useEffect, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";

// A secondary press that travelled further than this was a pan, not a request for the menu.
const TAP_SLOP_PX = 4;
const MARGIN_PX = 8;

function anchorStyle(point) {
  const clamp = (value, max) => Math.min(Math.max(value, MARGIN_PX), Math.max(MARGIN_PX, max - MARGIN_PX));
  return { position: "fixed", left: `${clamp(point.x, window.innerWidth)}px`, top: `${clamp(point.y, window.innerHeight)}px`, width: "1px", height: "1px" };
}

/**
 * The viewport's own context menu: the camera actions every model has. It opens
 * on a secondary press over the canvas that did not drag (a drag pans), and
 * nowhere else, so overlays above the canvas keep their own menus.
 *
 * @param {{ surface: HTMLElement | null, disabled?: boolean, onResetZoom(): void, onZoomToFit(): void }} props
 *   `surface`: the element whose canvas the menu belongs to.
 */
export default function ViewportContextMenu({ surface, disabled = false, onResetZoom, onZoomToFit }) {
  const [point, setPoint] = useState(null);
  useEffect(() => {
    if (!surface || disabled) { setPoint(null); return undefined; }
    let pressed = null;
    const overCanvas = event => event.target instanceof Element && event.target.tagName === "CANVAS" && surface.contains(event.target);
    const onPointerDown = (event) => { pressed = event.button === 2 && overCanvas(event) ? { x: event.clientX, y: event.clientY } : null; };
    const onContextMenu = (event) => {
      if (!overCanvas(event)) return;
      event.preventDefault();
      const travelled = pressed ? Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y) : 0;
      pressed = null;
      if (travelled <= TAP_SLOP_PX) setPoint({ x: event.clientX, y: event.clientY });
    };
    surface.addEventListener("pointerdown", onPointerDown, true);
    surface.addEventListener("contextmenu", onContextMenu, true);
    return () => {
      surface.removeEventListener("pointerdown", onPointerDown, true);
      surface.removeEventListener("contextmenu", onContextMenu, true);
    };
  }, [surface, disabled]);
  if (!point) return null;
  const run = action => { action?.(); setPoint(null); };
  return (
    <DropdownMenu open onOpenChange={(open) => { if (!open) setPoint(null); }}>
      <DropdownMenuTrigger asChild>
        <button type="button" tabIndex={-1} aria-hidden="true" className="pointer-events-none fixed size-px opacity-0" style={anchorStyle(point)} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" sideOffset={4} className="w-44"
        onContextMenu={(event) => { event.preventDefault(); event.stopPropagation(); }}>
        <DropdownMenuItem className="text-xs" onSelect={() => run(onResetZoom)}>Reset Zoom</DropdownMenuItem>
        <DropdownMenuItem className="text-xs" onSelect={() => run(onZoomToFit)}>Zoom To Fit</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
