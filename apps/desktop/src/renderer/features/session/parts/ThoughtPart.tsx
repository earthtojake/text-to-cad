import { Sparkles, ChevronDown } from "lucide-react";
import { cn } from "cn";

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
  useReasoning,
} from "@renderer/components/ai-elements/reasoning";

/**
 * A thought chunk as AI Elements' Reasoning: collapsed, one line —
 * "Thought for 12s" — that opens to the text. The duration is measured
 * here from when the chunk started streaming to when it stopped; a
 * replayed transcript has no timing, so it says "Thought".
 */
export function ThoughtPart({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <Reasoning className="not-prose mb-0" defaultOpen={false} isStreaming={streaming}>
      <ReasoningTrigger className="rounded-md px-1.5 py-1 text-[13px] leading-5 hover:bg-accent/60 hover:text-foreground">
        <TriggerBody />
      </ReasoningTrigger>
      <ReasoningContent className="mt-1 ml-6 text-[13px] leading-6">{text}</ReasoningContent>
    </Reasoning>
  );
}

function TriggerBody() {
  const { isStreaming, isOpen, duration } = useReasoning();
  const message = isStreaming
    ? "Thinking…"
    : duration === undefined || duration === 0
      ? "Thought"
      : `Thought for ${duration}s`;
  return (
    <>
      <span className="flex size-4 items-center justify-center text-muted-foreground">
        <Sparkles className="size-3.5" />
      </span>
      <span className="min-w-0 flex-1 truncate text-left">{message}</span>
      <ChevronDown className={cn("size-3.5 transition-transform", isOpen ? "rotate-180" : "rotate-0")} />
    </>
  );
}
