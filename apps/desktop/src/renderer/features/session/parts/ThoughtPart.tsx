import { ChevronRight } from "lucide-react";
import { Spinner } from "@renderer/components/ui/spinner";
import { cn } from "cn";

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
  useReasoning,
} from "@renderer/components/ai-elements/reasoning";

import { TRANSCRIPT_COMPONENTS, TRANSCRIPT_REHYPE_PLUGINS } from "../links/components";

/**
 * A thought chunk as AI Elements' Reasoning: collapsed, one line —
 * "Thought for 12s" — that opens to the text. The duration is measured
 * here from when the chunk started streaming to when it stopped; a
 * replayed transcript has no timing, so it says "Thought".
 *
 * Its markdown draws links and images the way the transcript's prose does
 * (`TRANSCRIPT_COMPONENTS`): a thought is the agent's words too.
 *
 * The disclosure chevron leads, in the slot the activity group's summary
 * line uses for its own — one side for every fold in the transcript.
 */
export function ThoughtPart({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <Reasoning className="not-prose mb-0 min-w-0" defaultOpen={false} isStreaming={streaming}>
      <ReasoningTrigger className="rounded-md px-1.5 py-0.5 text-[13px] leading-5 hover:bg-accent/60 hover:text-foreground">
        <TriggerBody />
      </ReasoningTrigger>
      <ReasoningContent
        className="ui-disclosure mt-1 ml-6 min-w-0 [overflow-wrap:anywhere] text-[13px] leading-6"
        components={TRANSCRIPT_COMPONENTS}
        rehypePlugins={TRANSCRIPT_REHYPE_PLUGINS}
      >
        {text}
      </ReasoningContent>
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
      <span aria-hidden className="flex size-4 shrink-0 items-center justify-center text-muted-foreground" data-thought-chevron>
        {isStreaming ? (
          <Spinner aria-hidden className="size-3.5" />
        ) : (
          <ChevronRight className={cn("size-3.5 transition-transform", isOpen && "rotate-90")} />
        )}
      </span>
      <span className="min-w-0 flex-1 truncate text-left">{message}</span>
    </>
  );
}
