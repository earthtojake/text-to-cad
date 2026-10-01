import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useId, useState } from "react";
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
const ROW = "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] leading-5 text-muted-foreground transition-colors";

export function SubagentRow({ part, sessionId }: { part: SubagentPart; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const running = part.state === "running";
  const label = `${part.name} ${STATE_LABEL[part.state]}`;
  const expandable = part.parts.length > 0;
  const partsId = useId();
  const row = (
    <>
      <span className="flex size-4 items-center justify-center">
        <SubagentOrb name={part.name} state={part.state} />
      </span>
      <span className="min-w-0 flex-1 truncate">
        {label}
        {part.task ? <span className="text-muted-foreground"> · {part.task}</span> : null}
      </span>
    </>
  );

  return (
    <div className="not-prose" data-subagent={part.sessionId} data-state={part.state}>
      {/* A row with nothing to open is not a control: a disabled button would also switch its
          hint off, and the task it clips would be out of reach. */}
      <TooltipHint content={part.task ?? undefined} overflowOnly>
        {expandable ? (
          <button
            aria-controls={open ? partsId : undefined}
            aria-expanded={open}
            className={cn(ROW, "hover:bg-accent/60")}
            onClick={() => setOpen((value) => !value)}
            type="button"
          >
            {row}
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          </button>
        ) : (
          <div className={ROW}>{row}</div>
        )}
      </TooltipHint>
      {open && expandable ? (
        <div className="ml-6 border-l pl-2" id={partsId}>
          <PartsList open={running} parts={part.parts} prefix={part.sessionId} sessionId={sessionId} />
        </div>
      ) : null}
    </div>
  );
}
