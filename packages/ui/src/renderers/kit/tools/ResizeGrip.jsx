import { cn } from "@cad/ui/utils";

// The grip's two strokes, drawn into the corner they sit in.
const STROKES = Object.freeze({ "bottom-left": "M1 2L6 7M1 5L3 7", "bottom-right": "M7 2L2 7M7 5L5 7" });

/**
 * The one way a floating box over the viewport is resized: a grip in one of its bottom corners,
 * two short strokes that are muted until the pointer is over them, inside a 14px hit area at the
 * corner and drawn inside the box's own border. Quick Edit's sits at its bottom-left, since the box
 * hangs from the viewport's top-right; every resizable panel of the tool stack's at its
 * bottom-right, since the stack hangs from the top-left. The caller gives it what a press and a key
 * do and what it is called; the grip only draws.
 *
 * @param {{ corner?: "bottom-left" | "bottom-right", className?: string } & import("react").HTMLAttributes<HTMLDivElement>} props
 */
export default function ResizeGrip({ corner = "bottom-right", className, ...props }) {
  const left = corner === "bottom-left";
  return <div data-resize-grip={corner} {...props}
    className={cn("group/resize absolute bottom-0 z-10 flex size-3.5 touch-none items-end rounded-sm p-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
      left ? "left-0 cursor-nesw-resize justify-start" : "right-0 cursor-nwse-resize justify-end", className)}>
    <svg viewBox="0 0 8 8" aria-hidden="true" className="size-2 text-muted-foreground/50 group-hover/resize:text-muted-foreground group-focus-visible/resize:text-foreground group-data-[dragging]/resize:text-foreground">
      <path d={STROKES[left ? "bottom-left" : "bottom-right"]} stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" fill="none" />
    </svg>
  </div>;
}
