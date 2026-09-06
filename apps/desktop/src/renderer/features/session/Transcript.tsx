import { ArrowDown, Paperclip } from "lucide-react";
import { useStickToBottomContext } from "use-stick-to-bottom";

import { Conversation, ConversationContent } from "@renderer/components/ai-elements/conversation";
import type { SessionState, Turn } from "@shared/acp/types";

import { PartsList } from "./parts/PartsList";
import { StatusLine } from "./StatusLine";
import { statusLine } from "./view";

/**
 * The transcript (plan §2, §6): a vertical list of turns in one centred
 * column, user turns as compact bubbles on the right, agent turns as prose
 * and activity rows at full width, the live status line under the turn
 * that is running. Sticks to the bottom while streaming; a "Jump to
 * latest" pill appears once the user scrolls up.
 */
export function Transcript({
  state,
  onRetry,
  onReconnect,
}: {
  state: SessionState;
  onRetry: () => void;
  onReconnect: () => void;
}) {
  const status = statusLine(state);
  const lastTurn = state.turns.at(-1);

  return (
    <Conversation className="min-h-0 flex-1" data-transcript>
      <ConversationContent className="mx-auto w-full max-w-[720px] gap-4 px-6 pt-6 pb-4">
        {state.turns.map((turn, index) => (
          <TurnView
            key={turn.id}
            last={index === state.turns.length - 1}
            onReconnect={state.status === "error" ? onReconnect : undefined}
            onRetry={onRetry}
            sessionId={state.sessionId}
            turn={turn}
          />
        ))}
        {status && lastTurn?.role === "agent" ? <StatusLine text={status} /> : null}
        {status && lastTurn?.role !== "agent" ? <StatusLine text={status} /> : null}
      </ConversationContent>
      <JumpToLatest />
    </Conversation>
  );
}

function TurnView({
  turn,
  sessionId,
  last,
  onRetry,
  onReconnect,
}: {
  turn: Turn;
  sessionId: string;
  last: boolean;
  onRetry: () => void;
  onReconnect?: () => void;
}) {
  if (turn.role === "user") {
    return <UserTurn turn={turn} />;
  }
  const open = turn.endedAt === null;
  return (
    <div className="flex w-full flex-col" data-turn={turn.id} data-role="agent" data-stop-reason={turn.stopReason ?? undefined}>
      <PartsList
        onReconnect={last ? onReconnect : undefined}
        onRetry={last ? onRetry : undefined}
        open={open}
        parts={turn.parts}
        prefix={turn.id}
        sessionId={sessionId}
      />
      {turn.stopReason === "cancelled" ? (
        <p className="not-prose mt-1 px-1.5 text-[13px] leading-5 text-muted-foreground italic" data-stopped>
          Stopped
        </p>
      ) : turn.stopReason === "refusal" ? (
        <p className="not-prose mt-1 px-1.5 text-[13px] leading-5 text-muted-foreground italic">The agent declined.</p>
      ) : turn.stopReason === "max_tokens" || turn.stopReason === "max_turn_requests" ? (
        <p className="not-prose mt-1 px-1.5 text-[13px] leading-5 text-muted-foreground italic">
          Stopped at the agent&apos;s limit — send &quot;continue&quot; to go on.
        </p>
      ) : null}
    </div>
  );
}

/** A compact bubble on the right, with the prompt's images and attachments under it. */
function UserTurn({ turn }: { turn: Turn }) {
  const text = turn.parts
    .filter((part): part is Extract<Turn["parts"][number], { type: "text" }> => part.type === "text")
    .map((part) => part.text)
    .join("\n");
  const images = turn.parts.filter((part): part is Extract<Turn["parts"][number], { type: "image" }> => part.type === "image");
  const links = turn.parts.filter(
    (part): part is Extract<Turn["parts"][number], { type: "resource_link" }> => part.type === "resource_link",
  );
  return (
    <div className="flex w-full flex-col items-end gap-1.5" data-turn={turn.id} data-role="user">
      {text ? (
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-3.5 py-2 text-[14px] leading-6 break-words whitespace-pre-wrap text-foreground select-text [overflow-wrap:anywhere]">
          {text}
        </div>
      ) : null}
      {images.length > 0 ? (
        <div className="flex max-w-[85%] flex-wrap justify-end gap-1.5">
          {images.map((image, index) => (
            <img
              alt=""
              className="max-h-48 rounded-lg border"
              key={index}
              src={`data:${image.mimeType};base64,${image.data}`}
            />
          ))}
        </div>
      ) : null}
      {links.length > 0 ? (
        <div className="flex max-w-[85%] flex-wrap justify-end gap-1.5">
          {links.map((link, index) => (
            <span
              className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px]"
              key={index}
              title={link.uri}
            >
              <Paperclip className="size-3 text-muted-foreground" />
              {link.name}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function JumpToLatest() {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();
  if (isAtBottom) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-0 bottom-3 left-0 flex justify-center">
      <button
        className="pointer-events-auto inline-flex h-7 items-center gap-1.5 rounded-full border bg-background px-3 text-[12px] shadow-md transition-colors hover:bg-accent"
        data-jump-to-latest
        onClick={() => void scrollToBottom()}
        type="button"
      >
        <ArrowDown className="size-3.5" />
        Jump to latest
      </button>
    </div>
  );
}
