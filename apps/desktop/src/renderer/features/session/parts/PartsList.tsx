import { AlertCircle, Paperclip, RotateCcw, Unplug } from "lucide-react";

import { MessageResponse } from "@renderer/components/ai-elements/message";
import { Button } from "@renderer/components/ui/button";
import type { Part } from "@shared/acp/types";

import { formatTokens, partsView, type ViewItem } from "../view";
import { ActivityGroup } from "./ActivityRow";
import { PermissionCard } from "./PermissionCard";
import { SubagentRow } from "./SubagentRow";
import { ThoughtPart } from "./ThoughtPart";

/**
 * The parts of an agent turn (or of a subagent, or of a Claude tool call's
 * children) as transcript rows: prose, thoughts, activity rows, permission
 * cards, subagent rows, errors, usage. The mapping itself is `view.ts`;
 * this is only the dispatch to components.
 */
export function PartsList({
  parts,
  open,
  prefix,
  sessionId,
  onRetry,
  onReconnect,
}: {
  parts: Part[];
  /** True while the turn is still streaming. */
  open: boolean;
  prefix: string;
  sessionId: string;
  /** Re-send the last prompt; shown on an error row when given. */
  onRetry?: () => void;
  /** Spawn the agent again and load the history; shown when the agent is gone. */
  onReconnect?: () => void;
}) {
  const items = partsView(parts, open, prefix);
  return (
    <>
      {items.map((item) => (
        <ViewItemView item={item} key={item.key} onReconnect={onReconnect} onRetry={onRetry} sessionId={sessionId} />
      ))}
    </>
  );
}

function ViewItemView({
  item,
  sessionId,
  onRetry,
  onReconnect,
}: {
  item: ViewItem;
  sessionId: string;
  onRetry?: () => void;
  onReconnect?: () => void;
}) {
  switch (item.kind) {
    case "text":
      return (
        <div className="prose-transcript my-1 text-[14px] leading-6" data-part="text">
          <MessageResponse isAnimating={item.streaming}>{item.text}</MessageResponse>
        </div>
      );
    case "thought":
      return <ThoughtPart streaming={item.streaming} text={item.text} />;
    case "activity":
      return <ActivityGroup item={item} sessionId={sessionId} />;
    case "permission":
      return <PermissionCard part={item.part} sessionId={sessionId} />;
    case "subagent":
      return <SubagentRow part={item.part} sessionId={sessionId} />;
    case "error":
      return (
        <div
          className="not-prose my-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5"
          data-part="error"
          role="alert"
        >
          <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
          <div className="min-w-0 flex-1 whitespace-pre-wrap break-words">{item.message}</div>
          {onReconnect ? (
            <Button className="h-6 shrink-0 gap-1 px-2 text-[12px]" onClick={onReconnect} size="sm" variant="ghost">
              <Unplug className="size-3" />
              Reconnect
            </Button>
          ) : null}
          {onRetry ? (
            <Button className="h-6 shrink-0 gap-1 px-2 text-[12px]" onClick={onRetry} size="sm" variant="outline">
              <RotateCcw className="size-3" />
              Retry
            </Button>
          ) : null}
        </div>
      );
    case "usage":
      return (
        <div className="not-prose mt-1 flex justify-end" data-part="usage">
          <span
            className="rounded-full border px-2 py-px font-mono text-[10px] text-muted-foreground tabular-nums"
            title={`${item.usage.inputTokens} in · ${item.usage.outputTokens} out${
              item.usage.cachedReadTokens ? ` · ${item.usage.cachedReadTokens} cached` : ""
            }`}
          >
            {formatTokens(item.usage.totalTokens)} tokens
          </span>
        </div>
      );
    case "image":
      return (
        <img
          alt=""
          className="my-1 max-h-80 w-fit rounded-lg border"
          data-part="image"
          src={`data:${item.mimeType};base64,${item.data}`}
        />
      );
    case "attachment":
      return (
        <span
          className="not-prose my-1 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px]"
          data-part="attachment"
          title={item.uri}
        >
          <Paperclip className="size-3 text-muted-foreground" />
          {item.name}
        </span>
      );
    case "mode":
      return (
        <p className="not-prose my-1 px-1.5 text-[12px] text-muted-foreground" data-part="mode">
          Switched to {item.modeId} mode
        </p>
      );
  }
}
