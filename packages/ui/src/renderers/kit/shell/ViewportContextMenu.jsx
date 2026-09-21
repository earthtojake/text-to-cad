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
 * the tap slop opens nothing, and so does a secondary press made while the primary
 * button is held, which is a pan chord), and a press that opens nothing leaves the
 * camera exactly as it was. The browser's own menu is already kept off the canvas by the
 * camera controls, for every renderer, menu or no menu.
 *
 * What the menu SAYS is the renderer's alone: `items({ clientX, clientY, shiftKey })`
 * is asked at the moment of the press and answers with descriptors, or with an
 * empty list / null for "nothing to offer here", in which case no menu opens.
 * A renderer that passes no `items` at all gets no listeners and no menu —
 * which is what a viewport that only orbits, pans and zooms hands over.
 *
 * `onOpenChange(open)` says when a menu the renderer filled is on screen and when it
 * has gone (an item chosen, a dismissal, a replaced viewport), so the renderer can keep
 * what the menu is ABOUT marked in its scene for exactly as long as the menu is up.
 *
 * @param {{ viewport: { runtimeRef: object, hostRef: object, viewerReadyTick: number },
 *   items: ((press: { clientX: number, clientY: number, shiftKey: boolean }) =>
 *     ({ id: string, label: import("react").ReactNode, disabled?: boolean,
 *        separatorBefore?: boolean, onSelect?: () => void }[] | null)) | null,
 *   onOpenChange?: ((open: boolean) => void) | null }} props
 */
export default function ViewportContextMenu({ viewport, items, onOpenChange = null }) {
  const { runtimeRef, hostRef, viewerReadyTick } = viewport;
  const [open, setOpen] = useState(null);
  const openChangeRef = useRef(onOpenChange);
  openChangeRef.current = onOpenChange;
  const isOpen = Boolean(open);
  const reportedOpenRef = useRef(false);
  useEffect(() => {
    if (reportedOpenRef.current === isOpen) return;
    reportedOpenRef.current = isOpen;
    openChangeRef.current?.(isOpen);
  }, [isOpen]);
  // Unmounting with a menu up (fullscreen, a tool change that withdraws the items) is a close too.
  useEffect(() => () => {
    if (reportedOpenRef.current) { reportedOpenRef.current = false; openChangeRef.current?.(false); }
  }, []);
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

    // Primary and secondary held TOGETHER is a camera chord (a pan), whichever went down first.
    // A button that joins one already held arrives as a pointer MOVE with new `buttons`, never
    // as a second pointerdown, so a secondary press under a held primary starts nothing here,
    // and a primary that joins a secondary press is seen in `move`.
    const primaryHeld = event => (Number(event.buttons) & 1) === 1;
    const down = event => {
      if (event.button !== 2 || !onCanvas(event)) { press = null; return; }
      press = { x: event.clientX, y: event.clientY, pointerType: event.pointerType || "", moved: primaryHeld(event) };
    };
    const move = event => {
      if (!press) return;
      if (primaryHeld(event) || Math.hypot(event.clientX - press.x, event.clientY - press.y) > slop(press.pointerType)) press.moved = true;
    };
    const up = event => {
      const started = press;
      press = null;
      if (event.button !== 2 || !started || started.moved || primaryHeld(event) || !onCanvas(event)) return;
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
