import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { VIEWPORT_INSET_PX } from "./viewportLayout.js";

const INSET = `${VIEWPORT_INSET_PX}px`;

/**
 * The viewport's top-right column, under the corner (the cube or the zoom pill and the stack under it, which stand in the
 * top-right corner itself: it starts an inset under them, `--cad-corner-below`, the shell's measure; at the top where the
 * host anchors the corner at the left): the host's notice first (`notice`, a question it asks once, such as whether to
 * share anonymous usage statistics), then anything else a view keeps there, under the notice rather than hiding under it
 * (Quick Edit is a bar at the view's bottom). It never reaches under the tool strip: its column starts an inset past the
 * strip's right side (`--cad-top-right-left`, the shell's measure), and what it holds is never wider than that.
 * @param {{ notice?: import("react").ReactNode, children?: import("react").ReactNode }} props
 */
export function ViewportTopRight({ notice = null, children = null }) {
  if (!notice && !children) return null;
  return <div className="pointer-events-none absolute z-30 flex flex-col items-end gap-2"
    style={{ top: `var(--cad-corner-below, ${INSET})`, left: `max(${INSET}, var(--cad-top-right-left, ${INSET}))`, right: INSET }}
    data-viewport-top-right="">
    <ScrollArea className="w-full [&_[data-slot=scroll-area-scrollbar]]:pointer-events-auto">
    <div className="flex flex-col items-end gap-2" data-viewport-top-right-content="">
    {notice ? <div className="pointer-events-auto w-full max-w-xs" data-viewport-notice="">{notice}</div> : null}
    {children}
    </div>
    </ScrollArea>
  </div>;
}
