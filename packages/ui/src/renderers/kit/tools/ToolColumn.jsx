import { useContext, useId, useSyncExternalStore } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { ViewerHostContext } from "../../../host/context.js";
import { CHROME_INSET_PX } from "../../../lib/chromeInset.js";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import FloatingToolBar from "./FloatingToolBar.js";
import { TOOL_STRIP_HEIGHT } from "./toolStackLayout.js";

// The column slides out to the left and fades as it goes, and back in: transforms and opacity
// alone, so nothing is laid out again while it moves. Going, it eases in and is the quicker;
// coming back, it eases out. Under reduced motion it does neither: it is simply gone, or back.
const HIDE_MOTION = "duration-150 ease-in";
const SHOW_MOTION = "duration-200 ease-out";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const reducedMotionQuery = () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(REDUCED_MOTION) : null);
function subscribeReducedMotion(notify) {
  const query = reducedMotionQuery();
  query?.addEventListener?.("change", notify);
  return () => query?.removeEventListener?.("change", notify);
}
const systemReducedMotion = () => reducedMotionQuery()?.matches === true;
/** The system's `prefers-reduced-motion`, or the app's own (`environment.reducedMotion`): either keeps the column still. */
function useReducedMotion() {
  const app = useContext(ViewerHostContext)?.environment?.reducedMotion === true;
  const system = useSyncExternalStore(subscribeReducedMotion, systemReducedMotion, () => false);
  return app || system;
}

/**
 * The column's own toggle, at the strip's right end: a strip of one, the strip's button on the
 * strip's surface, "Hide tools". Hidden, the row it ends has slid left by the strip's width, so the
 * toggle comes to rest where the strip began, on the strip's line: its box gone, the bare icon
 * ("Show tools"), faint until a pointer or the keyboard comes to it.
 */
function ToolColumnToggle({ away, motion, controls, onToggle }) {
  const Icon = away ? PanelLeftOpen : PanelLeftClose;
  return <div className={cn("relative flex shrink-0 items-center justify-center", away ? "pointer-events-none" : "pointer-events-auto")}
    style={{ width: TOOL_STRIP_HEIGHT, height: TOOL_STRIP_HEIGHT }} data-cad-tools-toggle="">
    <span aria-hidden="true" className={cn("absolute inset-0 rounded-md", FLOATING_CHROME_SURFACE_CLASS, motion && `transition-opacity ${motion}`)}
      style={away ? { opacity: 0 } : undefined} />
    <ToolbarButton label={away ? "Show tools" : "Hide tools"} tooltipSide="top" disclosure aria-expanded={!away} aria-controls={controls}
      className={cn("pointer-events-auto relative", away && "opacity-60 hover:opacity-100 focus-visible:opacity-100")} onClick={onToggle}>
      <Icon className="size-3" strokeWidth={2} aria-hidden="true" />
    </ToolbarButton>
  </div>;
}

/**
 * The strip and the tool stack under it, one column at the viewer's top-left (`style` places it),
 * and the person's way to put the whole of it away and bring it back. The strip's row ends in the
 * column's toggle; a column with no strip (a file whose one tool's panel is always up) has the
 * toggle alone on that row. The toggle is drawn only where the column has something to put away
 * (`toggle`), and a column that has nothing has no row at all.
 *
 * Hidden (`hidden`), the strip and every panel slide out to the left and fade, and are inert —
 * out of reach and out of the accessibility tree — and invisible once out, but mounted: a tree
 * keeps its expansion, filter and scroll, as panels already do from one tool to the next. Nothing
 * here shows or hides the column but its toggle, which reports the person's choice
 * (`onHiddenChange`, once per press); where it starts is the caller's (`toolStackHidden`).
 *
 * @param {{ tools: import("./FloatingToolBar.js").ViewportTool[], hidden?: boolean,
 *   onHiddenChange?: ((hidden: boolean) => void) | null, toggle?: boolean, mobile?: boolean,
 *   style?: import("react").CSSProperties, children?: import("react").ReactNode }} props
 *   `children`: the tool stack (`ToolStack.jsx`), which takes the column's height under the row.
 */
export default function ToolColumn({ tools, hidden = false, onHiddenChange = null, toggle = true, mobile = false, style, children }) {
  const still = useReducedMotion();
  const id = useId();
  const stripId = `${id}strip`, stackId = `${id}stack`;
  const strip = tools.length > 0;
  const togglable = toggle && Boolean(onHiddenChange);
  const away = togglable && hidden;
  const motion = still ? null : away ? HIDE_MOTION : SHOW_MOTION;
  // Gone: transparent, and invisible once the slide has ended. Visibility is transitioned only on
  // the way out, where it steps at the end; coming back it is visible at once, and while the column
  // is shown nothing in it transitions visibility, so whatever hides the column hides it at once.
  const gone = away ? { opacity: 0, visibility: "hidden" } : null;
  const fade = away ? "transition-[opacity,visibility]" : "transition-opacity";
  const slideAndFade = away ? "transition-[transform,opacity,visibility]" : "transition-[transform,opacity]";
  return <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-start gap-2" style={style}
    data-mobile={mobile ? "" : undefined} data-cad-tool-groups="" data-tools-hidden={away ? "" : undefined}>
    {strip || togglable ? <div className={cn("flex max-w-full shrink-0 items-start gap-2", motion && `transition-transform ${motion}`)}
      style={away ? { transform: `translateX(calc(-100% + ${TOOL_STRIP_HEIGHT}px))` } : undefined} data-cad-tool-row="">
      {strip ? <div id={stripId} className={cn("min-w-0", motion && `${fade} ${motion}`)} inert={away} style={gone ?? undefined}>
        <FloatingToolBar tools={tools} />
      </div> : null}
      {togglable ? <ToolColumnToggle away={away} motion={motion} controls={strip ? `${stripId} ${stackId}` : stackId}
        onToggle={() => onHiddenChange(!away)} /> : null}
    </div> : null}
    {/* The panels slide out past their own width and the inset they hang at, so nothing of them is left at the edge. */}
    <div id={stackId} className={cn("flex min-h-0 max-w-full flex-1 flex-col items-start", motion && `${slideAndFade} ${motion}`)}
      inert={away} style={away ? { transform: `translateX(calc(-100% - ${CHROME_INSET_PX}px))`, ...gone } : undefined}>
      {children}
    </div>
  </div>;
}
