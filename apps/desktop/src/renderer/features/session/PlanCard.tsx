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
  running,
}: {
  entries: PlanEntry[];
  /** When the turn that produced the plan started, for the elapsed clock. */
  startedAt: number | null;
  running: boolean;
}) {
  const done = entries.filter((entry) => entry.status === "completed").length;
  const current = entries.find((entry) => entry.status === "in_progress") ?? entries.find((entry) => entry.status === "pending");
  const elapsed = useElapsed(startedAt, running);
  const title = current?.content ?? (done === entries.length ? "Plan complete" : "Plan");

  return (
    <Plan
      className="mx-auto w-full max-w-[720px] gap-0 rounded-xl border bg-card py-0 text-[13px] shadow-xs"
      data-plan-card
      defaultOpen={false}
      isStreaming={false}
    >
      <PlanHeader className="grid-cols-[auto_1fr_auto] items-center gap-x-2 px-3 py-2">
        <span className="row-span-2 flex size-6 items-center justify-center rounded-md bg-muted text-muted-foreground">
          <Target className="size-3.5" />
        </span>
        <PlanTitle className="truncate text-[13px] leading-5 font-medium">{title}</PlanTitle>
        <PlanDescription className="text-[12px] leading-4">
          {`${done} of ${entries.length} done${elapsed !== null ? ` · ${elapsed}` : ""}`}
        </PlanDescription>
        <PlanAction className="row-span-2 self-center">
          <PlanTrigger className="size-7" />
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

function useElapsed(startedAt: number | null, running: boolean): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running || startedAt === null) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, startedAt]);
  if (startedAt === null) {
    return null;
  }
  return formatDuration((running ? now : Math.max(now, startedAt)) - startedAt);
}
