import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "cn";

import type { SubagentPart } from "@shared/acp/types";

import { SubagentOrb } from "../glyphs";
import { PartsList } from "./PartsList";

const STATE_LABEL: Record<SubagentPart["state"], string> = {
  running: "working",
  completed: "finished",
  failed: "failed",
  cancelled: "cancelled",
  disconnected: "disconnected",
};

/**
 * A subagent event as Codex draws it: a coloured orb, the subagent's name
 * and what it did ("Phalanx builder finished"). When the adapter streams
 * the child's transcript, the row opens to it inline.
 */
export function SubagentRow({ part, sessionId }: { part: SubagentPart; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const running = part.state === "running";
  const label = `${part.name} ${STATE_LABEL[part.state]}`;
  const expandable = part.parts.length > 0;

  return (
    <div className="not-prose" data-subagent={part.sessionId} data-state={part.state}>
      <button
        aria-expanded={open}
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] leading-5 text-muted-foreground transition-colors",
          expandable ? "hover:bg-accent/60" : "cursor-default",
        )}
        disabled={!expandable}
        onClick={() => setOpen((value) => !value)}
        title={part.task ?? undefined}
        type="button"
      >
        <span className="flex size-4 items-center justify-center">
          <SubagentOrb name={part.name} state={part.state} />
        </span>
        <span className="min-w-0 flex-1 truncate">
          {label}
          {part.task ? <span className="text-muted-foreground/70"> · {part.task}</span> : null}
        </span>
        {expandable ? (
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
        ) : null}
      </button>
      {open && expandable ? (
        <div className="ml-6 border-l pl-2">
          <PartsList open={running} parts={part.parts} prefix={part.sessionId} sessionId={sessionId} />
        </div>
      ) : null}
    </div>
  );
}
