import { useEffect, useRef, useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";

// A secondary press that MOVED is a pan, not a menu. Coarse pointers wander more.
const FINE_TAP_SLOP_PX = 4;
const COARSE_TAP_SLOP_PX = 12;
const MARGIN_PX = 8;

/** Keep the menu's anchor inside the window, so a press at the edge still opens a whole menu. */
export function viewportMenuAnchorStyle({ clientX, clientY }, viewportWidth, viewportHeight) {
  const maxX = viewportWidth > 0 ? Math.max(MARGIN_PX, viewportWidth - MARGIN_PX) : clientX;
  const maxY = viewportHeight > 0 ? Math.max(MARGIN_PX, viewportHeight - MARGIN_PX) : clientY;
  return {
    position: "fixed",
    left: `${Math.min(Math.max(Number(clientX) || MARGIN_PX, MARGIN_PX), maxX)}px`,
    top: `${Math.min(Math.max(Number(clientY) || MARGIN_PX, MARGIN_PX), maxY)}px`,
    width: "1px",
    height: "1px"
  };
}

/**
 * The viewport's own menu on a secondary press, whose ITEMS are the renderer's.
 *
 * The gesture, the anchor, the clamping and the dismissal are the shell's and are
 * the same everywhere: a secondary DRAG still pans (a press that moved more than
 * the tap slop opens nothing), and a press that opens nothing leaves the camera
 * exactly as it was. The browser's own menu is already kept off the canvas by the
 * camera controls, for every renderer, menu or no menu.
 *
 * What the menu SAYS is the renderer's alone: `items({ clientX, clientY, shiftKey })`
 * is asked at the moment of the press and answers with descriptors, or with an
 * empty list / null for "nothing to offer here", in which case no menu opens.
 * A renderer that passes no `items` at all gets no listeners and no menu —
 * which is what a viewport that only orbits, pans and zooms hands over.
 *
 * @param {{ viewport: { runtimeRef: object, hostRef: object, viewerReadyTick: number },
 *   items: ((press: { clientX: number, clientY: number, shiftKey: boolean }) =>
 *     ({ id: string, label: import("react").ReactNode, disabled?: boolean,
 *        separatorBefore?: boolean, onSelect?: () => void }[] | null)) | null }} props
 */
export default function ViewportContextMenu({ viewport, items }) {
  const { runtimeRef, hostRef, viewerReadyTick } = viewport;
  const [open, setOpen] = useState(null);
  // Held in a ref so a renderer that builds the list inline does not rebind the
  // gesture on every render; it is asked at the moment of the press either way.
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const offering = typeof items === "function";

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !offering) return undefined;
    const coarseDefault = window.matchMedia?.("(pointer: coarse)")?.matches ?? false;
    const slop = pointerType => (pointerType === "touch" || pointerType === "pen" || coarseDefault
      ? COARSE_TAP_SLOP_PX : FINE_TAP_SLOP_PX);
    // The scene's own canvas only: a control drawn over it keeps its presses.
    const onCanvas = event => event.target === runtimeRef.current?.renderer?.domElement;
    let press = null;

    const down = event => {
      if (event.button !== 2 || !onCanvas(event)) { press = null; return; }
      press = { x: event.clientX, y: event.clientY, pointerType: event.pointerType || "", moved: false };
    };
    const move = event => {
      if (!press) return;
      if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > slop(press.pointerType)) press.moved = true;
    };
    const up = event => {
      const started = press;
      press = null;
      if (event.button !== 2 || !started || started.moved || !onCanvas(event)) return;
      if (Math.hypot(event.clientX - started.x, event.clientY - started.y) > slop(started.pointerType)) return;
      const list = itemsRef.current?.({ clientX: event.clientX, clientY: event.clientY, shiftKey: Boolean(event.shiftKey) });
      if (!list?.length) return;
      setOpen({ items: list, clientX: event.clientX, clientY: event.clientY });
    };
    host.addEventListener("pointerdown", down, true);
    host.addEventListener("pointermove", move, true);
    host.addEventListener("pointerup", up, true);
    host.addEventListener("pointercancel", () => { press = null; }, true);
    return () => {
      host.removeEventListener("pointerdown", down, true);
      host.removeEventListener("pointermove", move, true);
      host.removeEventListener("pointerup", up, true);
      press = null;
    };
  }, [hostRef, runtimeRef, viewerReadyTick, offering]);

  // A new model, or a viewport that was rebuilt, is not the press's model any more.
  useEffect(() => { setOpen(null); }, [viewerReadyTick]);
  if (!open) return null;
  const style = viewportMenuAnchorStyle(open, window.innerWidth, window.innerHeight);
  return (
    <DropdownMenu open onOpenChange={next => { if (!next) setOpen(null); }}>
      <DropdownMenuTrigger asChild>
        <button type="button" tabIndex={-1} aria-hidden="true" className="pointer-events-none fixed size-px opacity-0" style={style} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="bottom" sideOffset={4} className="w-44"
        onContextMenu={event => { event.preventDefault(); event.stopPropagation(); }}>
        {open.items.map(item => (
          <div key={item.id} className="contents">
            {item.separatorBefore ? <DropdownMenuSeparator /> : null}
            <DropdownMenuItem className="text-xs" disabled={item.disabled === true}
              onSelect={() => { setOpen(null); item.onSelect?.(); }}>{item.label}</DropdownMenuItem>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
