import { useContext } from "react";
import { Progress } from "@cad/ui/primitives/progress";
import { cn } from "@cad/ui/utils";
import { ViewerHostContext } from "../host/context.js";

/**
 * Every loading surface's one indicator (`docs/viewer-ux.md`, "Loading and status screens"): what is happening now, as one step line — the
 * step in the chrome's text, muted, its count at the right in tabular figures — over the thin progress bar (its share
 * where it has one, a sliding segment where it has none), and under it whatever the caller adds (the connection-lost
 * line, a long step's detail), in the same type. No mark, no spinner, no headline: the navbar names the file and the
 * panel's placeholder rows already say it is loading. 240px wide, never wider than the room it is centred in.
 *
 * Where less motion is asked for (the host's Reduce motion, `environment.reducedMotion`, or the system's) the bar
 * does not move: an indeterminate one stands still across the track. `paused`: the work is waiting (the connection
 * lost), its bar held where it is.
 * @param {{ label: string, counts?: string, percent?: number | null, paused?: boolean, className?: string,
 *   children?: import("react").ReactNode }} props  Other props (`data-*`) go on its box.
 */
export default function LoadingStep({ label, counts = "", percent = null, paused = false, className, children = null, ...props }) {
  const still = useContext(ViewerHostContext)?.environment?.reducedMotion === true;
  // The step line and the bar are what is centred; the lines a long or a lost step adds hang under the bar, so the
  // indicator never moves as they come and go.
  return <div className={cn("relative flex w-60 max-w-full flex-col gap-2 text-ui text-muted-foreground", className)} role="status" aria-live="polite" {...props}>
    <div className="flex min-w-0 items-baseline justify-between gap-4" data-loading-step="">
      <span className="min-w-0 truncate">{label}</span>
      {counts ? <span className="shrink-0 tabular-nums">{counts}</span> : null}
    </div>
    <Progress value={percent} aria-label={label} still={still} paused={paused} />
    {children ? <div className="absolute inset-x-0 top-full mt-2 flex flex-col gap-2" data-loading-more="">{children}</div> : null}
  </div>;
}
