import { VIEWPORT_INSET_PX } from "./viewportLayout.js";

const INSET = `${VIEWPORT_INSET_PX}px`;
const POSITION = Object.freeze({ top: INSET, right: INSET, left: INSET });

/**
 * The viewport's top-right corner, one column: the host's notice first (`notice`, a question it
 * asks once, such as whether to share anonymous usage statistics), then what the view keeps there,
 * Quick Edit, which steps down below the notice while it is up rather than hiding under it.
 * @param {{ notice?: import("react").ReactNode, children?: import("react").ReactNode }} props
 */
export function ViewportTopRight({ notice = null, children = null }) {
  if (!notice && !children) return null;
  return <div className="pointer-events-none absolute z-30 flex flex-col items-end gap-2" style={POSITION} data-viewport-top-right="">
    {notice ? <div className="pointer-events-auto w-full max-w-xs" data-viewport-notice="">{notice}</div> : null}
    {children}
  </div>;
}
