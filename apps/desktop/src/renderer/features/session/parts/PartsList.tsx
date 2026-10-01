import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { AlertCircle, Paperclip, RotateCcw, Unplug } from "lucide-react";
import { useContext, useMemo, useState, type ComponentProps } from "react";

import { defaultRemarkPlugins } from "streamdown";

import { MessageResponse } from "@renderer/components/ai-elements/message";
import { Button } from "@renderer/components/ui/button";
import type { Part } from "@shared/acp/types";

import { TRANSCRIPT_COMPONENTS, TRANSCRIPT_REHYPE_PLUGINS } from "../links/components";
import { TranscriptScopeContext } from "../links/PathLink";
import { remarkPathLinks } from "../links/remarkPathLinks";
import { partsView, type ViewItem } from "../view";

/**
 * The transcript's markdown: Streamdown's own plugins, then the one that
 * turns a path in prose into a link (`../links`), drawn with the
 * transcript's own link and image (`TRANSCRIPT_COMPONENTS`). Module
 * constants, because `MessageResponse` is memoised on its children and a
 * fresh array per render would rebuild every block on every keystroke of the
 * composer.
 *
 * `remarkPlugins` *replaces* Streamdown's defaults rather than extending
 * them, so GFM is spread back in first. The path plugin is given the thread's
 * root (a root with a space in it is read where an absolute path begins with
 * it), so the list is one per root, kept by `useRemarkPlugins`.
 */
const DEFAULT_REMARK_PLUGINS = Object.values(defaultRemarkPlugins);
type RemarkPlugins = ComponentProps<typeof MessageResponse>["remarkPlugins"];
const remarkPluginsFor = new Map<string, NonNullable<RemarkPlugins>>();

function useRemarkPlugins(): RemarkPlugins {
  const rootPath = useContext(TranscriptScopeContext)?.rootPath ?? "";
  return useMemo(() => {
    let plugins = remarkPluginsFor.get(rootPath);
    if (!plugins) {
      plugins = [...DEFAULT_REMARK_PLUGINS, [remarkPathLinks, { rootPath: rootPath || null }]];
      remarkPluginsFor.set(rootPath, plugins);
    }
    return plugins;
  }, [rootPath]);
}
import { ActivityGroup } from "./ActivityRow";
import { PermissionCard } from "./PermissionCard";
import { SubagentRow } from "./SubagentRow";
import { ThoughtPart } from "./ThoughtPart";

/**
 * The parts of an agent turn (or of a subagent, or of a Claude tool call's
 * children) as transcript rows: prose, thoughts, activity rows, permission
 * cards, subagent rows, errors. The mapping itself is `view.ts`;
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
  onRetry?: () => void | Promise<void>;
  /** Spawn the agent again and load the history; shown when the agent is gone. */
  onReconnect?: () => void;
}) {
  const items = useMemo(() => partsView(parts, open, prefix), [parts, open, prefix]);
  return (
    <>
      {items.map((item) => (
        <ViewItemView item={item} key={item.key} onReconnect={onReconnect} onRetry={onRetry} sessionId={sessionId} />
      ))}
    </>
  );
}

/**
 * A failed turn's row. Retry is pending from the first click until the resend has settled (the
 * turn began, or the resend was refused), so a second click cannot queue the same prompt twice.
 */
function ErrorRow({ message, onRetry, onReconnect }: { message: string; onRetry?: () => void | Promise<void>; onReconnect?: () => void }) {
  const [retrying, setRetrying] = useState(false);
  const retry = () => {
    if (retrying) return;
    setRetrying(true);
    void Promise.resolve(onRetry?.()).finally(() => setRetrying(false));
  };
  return (
    <div
      className="not-prose my-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-[13px] leading-5"
      data-part="error"
      role="alert"
    >
      <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
      <div className="min-w-0 flex-1 whitespace-pre-wrap break-words">{message}</div>
      {onReconnect ? (
        <Button className="h-6 shrink-0 gap-1 px-2 text-[12px]" onClick={onReconnect} size="sm" variant="ghost">
          <Unplug className="size-3" />
          Reconnect
        </Button>
      ) : null}
      {onRetry ? (
        <Button aria-disabled={retrying} className="h-6 shrink-0 gap-1 px-2 text-[12px]" disabled={retrying} onClick={retry} size="sm" variant="outline">
          <RotateCcw className="size-3" />
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      ) : null}
    </div>
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
  onRetry?: () => void | Promise<void>;
  onReconnect?: () => void;
}) {
  const remarkPlugins = useRemarkPlugins();
  switch (item.kind) {
    case "text":
      return (
        <div className="prose-transcript my-2 min-w-0 [overflow-wrap:anywhere] text-[14px] leading-6" data-part="text">
          <MessageResponse components={TRANSCRIPT_COMPONENTS} isAnimating={item.streaming} rehypePlugins={TRANSCRIPT_REHYPE_PLUGINS} remarkPlugins={remarkPlugins}>
            {item.text}
          </MessageResponse>
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
      return <ErrorRow message={item.message} onReconnect={onReconnect} onRetry={onRetry} />;
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
        <TooltipHint content={item.uri} side="top">
          <span
            className="not-prose my-1 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[12px]"
            data-part="attachment"
          >
            <Paperclip className="size-3 text-muted-foreground" />
            {item.name}
          </span>
        </TooltipHint>
      );
    case "mode":
      return (
        <p className="not-prose my-1 px-1.5 text-[12px] text-muted-foreground" data-part="mode">
          Switched to {item.modeId} mode
        </p>
      );
  }
}
