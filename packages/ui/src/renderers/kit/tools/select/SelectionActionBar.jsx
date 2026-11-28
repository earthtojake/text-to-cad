import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Vector3 } from "three";
import { MoreHorizontal } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS, FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";

// How far the bar keeps from what it is about, and from the view's edges and its chrome, in px.
const GAP = 10;
const EDGE = 8;
// A move smaller than this, in px, leaves the bar where it is (a box re-read each frame jitters by less).
const STILL_PX = 0.5;

/** The eight corners of a box `{ min, max }`, each `[x, y, z]`, in world space. */
function corners({ min, max }) {
  const out = [];
  for (const x of [min[0], max[0]]) for (const y of [min[1], max[1]]) for (const z of [min[2], max[2]]) out.push(new Vector3(x, y, z));
  return out;
}

/**
 * Where a world box falls on the canvas, in its CSS px: the screen box round the corners in front of the camera,
 * or null where none is (behind the camera, or nothing to box).
 */
export function screenBox(bounds, camera, width, height) {
  if (!bounds || !camera || !width || !height) return null;
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const point of corners(bounds)) {
    const ndc = point.project(camera);
    if (ndc.z > 1) continue;
    const x = ((ndc.x + 1) / 2) * width, y = ((1 - ndc.y) / 2) * height;
    left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
  }
  return Number.isFinite(left) ? { left, top, right, bottom } : null;
}

/**
 * Where the bar stands, in the canvas's CSS px: centred over what it is about and just above it, else just below it,
 * else (what is picked fills the view) at the top of the room; always inside the room the view's chrome leaves
 * (`room`: under the strip's column, above Quick Edit, `EDGE` in from either side), and never over a box that is wholly
 * off the view (null then).
 * @param {{ left: number, top: number, right: number, bottom: number }} box
 * @param {{ width: number, height: number }} size The bar's own.
 * @param {{ width: number, height: number, top: number, bottom: number }} room `top` and `bottom` from the canvas's top.
 */
export function placeBar(box, size, room) {
  if (!box) return null;
  if (box.right < 0 || box.left > room.width || box.bottom < room.top || box.top > room.bottom) return null;
  const centre = (box.left + box.right) / 2;
  const left = Math.max(EDGE, Math.min(room.width - EDGE - size.width, centre - size.width / 2));
  const lowest = room.bottom - size.height;
  const above = box.top - GAP - size.height;
  const below = box.bottom + GAP;
  const top = above >= room.top ? above : below <= lowest ? below : room.top;
  return { left, top: Math.max(room.top, Math.min(lowest, top)) };
}

const cssPx = (style, name) => {
  const value = Number.parseFloat(style.getPropertyValue(name));
  return Number.isFinite(value) ? value : 0;
};

/**
 * What Select has picked, its bar: a small floating toolbar just above the picked parts (below them where there is no
 * room above), following them as the camera moves, as the bar over picked ink does (`AnnotationSelectionBar.jsx`), on
 * the strip's surface a size smaller. It holds the few things a person does to a pick there and then (the renderer's
 * `actions`: Isolate, Hide, Zoom to selection), then More, the rest of the view's menu for the same pick (`menu`, the
 * view menu's entries, `viewMenu.js`), so nothing in it is only here. It keeps clear of the strip's column and of
 * Quick Edit, and steps aside while what it is about is off the view.
 *
 * @param {{ runtimeRef: { current: object | null }, viewerReadyTick?: number, bounds(): ({ min: number[], max: number[] } | null),
 *   boundsKey: string, label: string, moreLabel: string, disabled?: boolean,
 *   actions: { id: string, label: string, icon: import("react").ReactNode, onSelect(): void, disabled?: boolean, active?: boolean }[],
 *   menu?: (() => { id: string, label: import("react").ReactNode, disabled?: boolean, separatorBefore?: boolean, onSelect?: () => void }[]) | null,
 *   onMenuOpen?: (() => void) | null }} props
 *   `menu` is asked for its entries while More's menu is open; `onMenuOpen` hears each time it opens.
 */
export default function SelectionActionBar({ runtimeRef, viewerReadyTick = 0, bounds, boundsKey, label, moreLabel, actions, menu = null, onMenuOpen = null,
  disabled = false }) {
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const bar = useRef(/** @type {HTMLDivElement | null} */ (null));
  const sizeRef = useRef({ width: 0, height: 0 });
  const [size, setSize] = useState({ width: 0, height: 0 });
  sizeRef.current = size;
  const [place, setPlace] = useState(/** @type {{ left: number, top: number } | null} */ (null));
  const [menuOpen, setMenuOpen] = useState(false);
  // Each frame, where the pick falls on the screen: what is picked can move without the camera (the renderer moving it),
  // so the box is read every frame, and the bar moves only when where it stands has.
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      frame = globalThis.requestAnimationFrame(tick);
      const runtime = runtimeRef.current, canvas = runtime?.renderer?.domElement;
      if (!runtime?.camera || !canvas) return;
      runtime.camera.updateMatrixWorld();
      const width = canvas.clientWidth, height = canvas.clientHeight;
      const box = screenBox(boundsRef.current?.() || null, runtime.camera, width, height);
      const style = getComputedStyle(canvas);
      const room = { width, height, top: Math.max(EDGE, cssPx(style, "--cad-tools-bottom") + EDGE),
        bottom: height - Math.max(EDGE, cssPx(style, "--cad-quick-edit-reserve")) };
      const next = placeBar(box, sizeRef.current, room);
      setPlace(now => {
        if (!next || !now) return next === now ? now : next;
        return Math.abs(now.left - next.left) < STILL_PX && Math.abs(now.top - next.top) < STILL_PX ? now : next;
      });
    };
    tick();
    return () => globalThis.cancelAnimationFrame(frame);
  }, [boundsKey, runtimeRef, viewerReadyTick]);
  useLayoutEffect(() => {
    const element = bar.current;
    if (element && (element.offsetWidth !== size.width || element.offsetHeight !== size.height)) setSize({ width: element.offsetWidth, height: element.offsetHeight });
  });
  // A new pick is not the open menu's pick any more.
  useEffect(() => { setMenuOpen(false); }, [boundsKey]);
  // Off the view, the bar (and its menu) goes; it comes back with the pick.
  if (!place) return null;
  const entries = menuOpen && menu ? menu() : [];
  return <div ref={bar} role="toolbar" aria-label={label} data-selection-action-bar=""
    className={cn(FLOATING_CHROME_SURFACE_CLASS, "pointer-events-auto absolute z-20 flex items-center gap-0.5 rounded-md p-0.5", size.width ? null : "invisible")}
    style={place} onPointerDown={event => event.stopPropagation()} onContextMenu={event => event.stopPropagation()}>
    {actions.map(action => <ToolbarButton key={action.id} tooltip={action.label} tooltipSide="top" label={action.label} active={action.active === true}
      disabled={disabled || action.disabled === true} data-action={action.id} onClick={() => action.onSelect()}>
      {action.icon}
    </ToolbarButton>)}
    {menu ? <>
      <span role="separator" aria-orientation="vertical" className="mx-0.5 h-4 w-px bg-border" />
      <DropdownMenu open={menuOpen} onOpenChange={open => { setMenuOpen(open); if (open) onMenuOpen?.(); }}>
        <DropdownMenuTrigger asChild>
          <ToolbarButton tooltip={moreLabel} tooltipSide="top" label={moreLabel} disabled={disabled} data-action="more">
            <MoreHorizontal className="size-3" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="bottom" sideOffset={4} className={cn(FLOATING_SURFACE_CLASS, "w-44")}
          onContextMenu={event => { event.preventDefault(); event.stopPropagation(); }}>
          {entries.map(item => <div key={item.id} className="contents">
            {item.separatorBefore ? <DropdownMenuSeparator /> : null}
            <DropdownMenuItem disabled={item.disabled === true} onSelect={() => item.onSelect?.()}>{item.label}</DropdownMenuItem>
          </div>)}
        </DropdownMenuContent>
      </DropdownMenu>
    </> : null}
  </div>;
}
