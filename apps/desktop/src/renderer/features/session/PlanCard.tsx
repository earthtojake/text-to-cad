import { useEffect, useState } from "react";
import { Check, Circle, CircleDot, Target } from "lucide-react";
import { cn } from "cn";

import {
  Plan,
  PlanAction,
  PlanContent,
  PlanDescription,
  PlanHeader,
  PlanTitle,
  PlanTrigger,
} from "@renderer/components/ai-elements/plan";
import type { PlanEntry } from "@shared/acp/types";

import { formatDuration } from "./view";

/**
 * Codex's pinned goal card above the composer (plan §2, §6): the current
 * step as the title, progress and elapsed time under it, and the whole
 * plan on expand. AI Elements' Plan with `defaultOpen=false`.
 */
export function PlanCard({
  entries,
  startedAt,
  endedAt,
  running,
}: {
  entries: PlanEntry[];
  /** When the turn that produced the plan started, for the elapsed clock. */
  startedAt: number | null;
  /** When that turn ended; the clock then says how long it took. */
  endedAt: number | null;
  /** Whether that turn — not the session — is the one running (`planClock`). */
  running: boolean;
}) {
  const done = entries.filter((entry) => entry.status === "completed").length;
  const current = entries.find((entry) => entry.status === "in_progress") ?? entries.find((entry) => entry.status === "pending");
  const elapsed = useElapsed(startedAt, endedAt, running);
  const complete = entries.length > 0 && done === entries.length;
  const title = current?.content ?? (complete ? "Plan complete" : "Plan");
  const progress = `${done} of ${entries.length} done${elapsed !== null ? ` · ${elapsed}` : ""}`;

  // One row, read left to right: the icon, the words beside it, the toggle at
  // the end. A finished plan has nothing left to watch, so it shrinks to a
  // single line — still a trigger, so the steps are one click away.
  return (
    <Plan
      className="mx-auto w-full max-w-[720px] gap-0 rounded-xl border bg-card py-0 text-[13px] shadow-xs"
      data-plan-card
      data-plan-complete={complete ? "" : undefined}
      defaultOpen={false}
      isStreaming={false}
    >
      <PlanHeader
        className={cn("flex items-center gap-2.5 text-left", complete ? "px-2.5 py-1" : "px-3 py-2")}
        data-plan-header
      >
        <span
          className={cn(
            "flex shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground",
            complete ? "size-5" : "size-6",
          )}
        >
          {complete ? <Check className="size-3" /> : <Target className="size-3.5" />}
        </span>
        <div className={cn("min-w-0 flex-1", complete ? "flex items-baseline gap-2" : "flex flex-col")}>
          <PlanTitle className={cn("truncate text-[13px] font-medium", complete ? "leading-6" : "leading-5")}>
            {title}
          </PlanTitle>
          <PlanDescription className="shrink-0 truncate text-[12px] leading-4">{progress}</PlanDescription>
        </div>
        <PlanAction className="shrink-0 self-center">
          <PlanTrigger className={complete ? "size-6" : "size-7"} />
        </PlanAction>
      </PlanHeader>
      <PlanContent className="border-t px-3 py-2">
        <ol className="flex flex-col gap-1">
          {entries.map((entry, index) => (
            <li
              className={cn(
                "flex items-start gap-2 leading-5",
                entry.status === "completed" && "text-muted-foreground line-through decoration-muted-foreground/50",
              )}
              key={`${index}:${entry.content}`}
            >
              <span className="mt-1 flex size-3 shrink-0 items-center justify-center text-muted-foreground">
                {entry.status === "completed" ? (
                  <Check className="size-3" />
                ) : entry.status === "in_progress" ? (
                  <CircleDot className="size-3 text-foreground" />
                ) : (
                  <Circle className="size-3" />
                )}
              </span>
              <span className="min-w-0 flex-1">{entry.content}</span>
              {entry.priority === "high" ? (
                <span className="rounded border px-1 text-[10px] text-muted-foreground uppercase">high</span>
              ) : null}
            </li>
          ))}
        </ol>
      </PlanContent>
    </Plan>
  );
}

/**
 * The turn's length once it ended; while it runs, the time since it started,
 * ticking. A turn that neither ended nor runs (the agent went away mid-turn)
 * has no length to say.
 */
function useElapsed(startedAt: number | null, endedAt: number | null, running: boolean): string | null {
  const ticking = running && endedAt === null && startedAt !== null;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!ticking) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);
  if (startedAt === null) {
    return null;
  }
  if (endedAt !== null) {
    return formatDuration(endedAt - startedAt);
  }
  return ticking ? formatDuration(Math.max(now, startedAt) - startedAt) : null;
}
