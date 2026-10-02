import { cn } from "@text-to-cad/ui/utils";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";

const INSET = `${VIEWPORT_INSET_PX}px`;
// A host whose own control sits in the view's top-right corner (Claude's inline card: its Full size
// button) moves the column down by setting `--cad-viewport-top-right-inset`.
const HOST = "var(--cad-viewport-top-right-inset, 0px)";
// Under the tool strip's row: where a notice starts on a narrow view, so the strip stays in reach.
const BELOW_STRIP = `${VIEWPORT_INSET_PX * 2 + VIEWPORT_TOP_BAR_PX}px`;

/**
 * The viewport's top-right corner, one column: the host's notice first (`notice`, a question it
 * asks once, such as whether to share anonymous usage statistics), then what the view keeps there,
 * Quick Edit, which steps down below the notice while it is up rather than hiding under it. On a
 * narrow view the notice would cover the tool strip, so with a strip (`belowStrip`) it starts below
 * the strip's row.
 * @param {{ notice?: import("react").ReactNode, belowStrip?: boolean, children?: import("react").ReactNode }} props
 */
export function ViewportTopRight({ notice = null, belowStrip = false, children = null }) {
  if (!notice && !children) return null;
  return <div className={cn("pointer-events-none absolute z-30 flex flex-col items-end gap-2 top-[var(--cad-top-right-top)]",
    notice && belowStrip && "@max-md/cad-viewport:top-[var(--cad-top-right-narrow)]")}
    style={{ left: INSET, right: INSET, "--cad-top-right-top": `calc(${INSET} + ${HOST})`, "--cad-top-right-narrow": `calc(${BELOW_STRIP} + ${HOST})` }}
    data-viewport-top-right="">
    {notice ? <div className="pointer-events-auto w-full max-w-xs" data-viewport-notice="">{notice}</div> : null}
    {children}
  </div>;
}
