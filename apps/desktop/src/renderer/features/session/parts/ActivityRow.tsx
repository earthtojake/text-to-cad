import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Suspense, lazy, useContext, useId, useState } from "react";
import { Ban, Box, CircleAlert, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "cn";

import { Terminal } from "@renderer/components/ai-elements/terminal";
import { capToolBody, ToolInput, ToolOutput, TrimmedBody } from "@renderer/components/ai-elements/tool";
import { useAcp } from "@renderer/state/acp";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import { isCadFile } from "@shared/cad-refs";
import type { ToolCallPart } from "@shared/acp/types";

import { GlyphIcon } from "../glyphs";
import { TranscriptScopeContext } from "../links/PathLink";
import { activityRow, commandLine, type ActivityRow, type ViewItem } from "../view";
import { PartsList } from "./PartsList";

const DiffView = lazy(() => import("./DiffView"));

type ActivityItem = Extract<ViewItem, { kind: "activity" }>;

/**
 * One or more tool calls as Codex activity rows (plan §2): collapsed by
 * default, one line each. A run of consecutive calls folds into a single
 * summary line ("Edited 3 files, ran 2 commands") that opens to the rows;
 * a row opens to the call's detail — the diff, the command's output, or
 * its input and result.
 */
export function ActivityGroup({ item, sessionId }: { item: ActivityItem; sessionId: string }) {
  const [open, setOpen] = useState(false);
  // Which rows are open is the group's, not each row's: a lone call is drawn
  // bare and a second one folds both under the summary, and a row's own
  // state would not survive that move. Opening the lone row opens the group
  // too, so the fold that follows shows the row where the person left it.
  const [openRows, setOpenRows] = useState<ReadonlySet<string>>(() => new Set());
  const active = item.rows.some((row) => row.status === "pending" || row.status === "in_progress");
  const failureCount = item.rows.filter((row) => row.status === "failed").length;
  const toggleRow = (id: string) => {
    const opening = !openRows.has(id);
    setOpenRows((current) => {
      const next = new Set(current);
      if (opening) next.add(id);
      else next.delete(id);
      return next;
    });
    if (opening && item.summary === null) {
      setOpen(true);
    }
  };
  const groupId = useId();
  const rowView = (row: ActivityRow) => (
    <ActivityRowView key={row.id} onToggle={() => toggleRow(row.id)} open={openRows.has(row.id)} row={row} sessionId={sessionId} />
  );

  if (item.summary === null) {
    return rowView(item.rows[0]!);
  }

  return (
    <div className="not-prose min-w-0" data-activity-group data-open={open}>
      <RowButton
        active={active}
        controls={groupId}
        onClick={() => setOpen((value) => !value)}
        open={open}
      >
        <span className="flex size-4 shrink-0 items-center justify-center text-muted-foreground">
          {active ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          )}
        </span>
        <span className="min-w-0 truncate">{item.summary}</span>
        {failureCount > 0 ? <FailureIndicator count={failureCount} /> : null}
      </RowButton>
      {open ? (
        <div className="ui-reveal ml-2 border-l pl-2" id={groupId}>
          {item.rows.map(rowView)}
        </div>
      ) : null}
    </div>
  );
}

export function ActivityRowView({
  row,
  sessionId,
  open,
  onToggle,
}: {
  row: ActivityRow;
  sessionId: string;
  /** Held by the group (`ActivityGroup`), so it outlives the fold. */
  open: boolean;
  onToggle: () => void;
}) {
  const active = row.status === "pending" || row.status === "in_progress";
  const failed = row.status === "failed";
  const cancelled = row.status === "cancelled";
  const label = row.label;
  const command = row.command ? commandLine(row.command) : null;
  const detailId = useId();

  return (
    <div className="not-prose min-w-0" data-activity-row={row.id} data-status={row.status}>
      <RowButton
        active={active}
        controls={detailId}
        onClick={onToggle}
        open={open}
        title={row.path ?? row.command ?? row.part.title}
        trailing={row.path ? <OpenCadFile path={row.path} sessionId={sessionId} /> : null}
      >
        <span className="flex size-4 shrink-0 items-center justify-center text-muted-foreground">
          {active ? <Loader2 className="size-3.5 animate-spin" /> : <GlyphIcon glyph={row.glyph} />}
        </span>
        <span className="flex min-w-0 flex-1 items-baseline gap-2">
          {label ? (
            <span className="min-w-0 truncate">{label}</span>
          ) : null}
          {command ? (
            <span className="min-w-0 truncate font-mono text-[12px] text-foreground/80">{command}</span>
          ) : null}
        </span>
        {failed ? <FailureIndicator /> : null}
        {cancelled ? <CancelledIndicator /> : null}
        {row.insertions + row.deletions > 0 ? (
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
            +{row.insertions} −{row.deletions}
          </span>
        ) : null}
      </RowButton>
      {open ? <ToolDetail id={detailId} part={row.part} sessionId={sessionId} /> : null}
    </div>
  );
}

/**
 * "Open" beside a row whose path is a CAD file under this session's folder:
 * the file opens in this session's explorer, in the root the transcript's
 * links use (the worktree for a worktree thread). A path outside the folder,
 * or a transcript not bound to the explorer showing, gets no button.
 */
function OpenCadFile({ path, sessionId }: { path: string; sessionId: string }) {
  const scope = useContext(TranscriptScopeContext);
  const cwd = useSessions((state) => state.sessions.find((session) => session.id === sessionId)?.cwd ?? null);
  const owned = useExplorer((state) => state.sessionId === sessionId);
  const relative = relativeTo(path, cwd);
  if (!scope || !owned || !relative || !isCadFile(relative)) {
    return null;
  }
  const open = () => {
    const explorer = useExplorer.getState();
    // The strip may have moved to another session since this rendered.
    if (explorer.sessionId !== sessionId) return;
    explorer.openFile(relative, scope.root);
  };
  return (
    <TooltipHint content={`Open ${relative}`}>
      <button
        className="inline-flex h-5 shrink-0 items-center gap-1 rounded-sm px-1.5 text-[11px] font-medium text-primary hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        data-activity-open={relative}
        onClick={open}
        type="button"
      >
        <Box aria-hidden className="size-3" />
        Open
      </button>
    </TooltipHint>
  );
}

/** A path the agent reported, relative to the session's folder; null when it is outside it. */
function relativeTo(path: string, cwd: string | null): string | null {
  const posix = path.replace(/\\/g, "/");
  if (!posix.startsWith("/") && !/^[a-z]:\//i.test(posix)) {
    const relative = posix.replace(/^(\.\/)+/, "");
    return relative && !relative.split("/").includes("..") ? relative : null;
  }
  if (!cwd) return null;
  const base = cwd.replace(/\\/g, "/").replace(/\/+$/, "");
  return posix.startsWith(`${base}/`) ? posix.slice(base.length + 1) : null;
}

/** A failure belongs to the affected call, not to every word in the group. */
function FailureIndicator({ count }: { count?: number }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-destructive" data-activity-failures>
      <CircleAlert aria-hidden className="size-3" />
      {count === undefined ? "Failed" : `${count} failed`}
    </span>
  );
}

/** A call whose turn was cancelled while it was still pending or running. */
function CancelledIndicator() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-muted-foreground" data-activity-cancelled>
      <Ban aria-hidden className="size-3" />
      Cancelled
    </span>
  );
}

function RowButton({
  children,
  open,
  active,
  controls,
  onClick,
  title,
  trailing,
}: {
  children: React.ReactNode;
  open: boolean;
  /** The id of what the row opens, named while it is open (`aria-controls`). */
  controls: string;
  active: boolean;
  onClick: () => void;
  title?: string;
  /** A second control beside the row — a sibling, never nested in the toggle. */
  trailing?: React.ReactNode;
}) {
  if (trailing) {
    return (
      <div className="flex min-w-0 items-center gap-1">
        <RowButton active={active} controls={controls} onClick={onClick} open={open} title={title}>
          {children}
        </RowButton>
        {trailing}
      </div>
    );
  }
  return (
    <TooltipHint content={title} overflowOnly>
      <button
        aria-controls={open ? controls : undefined}
        aria-expanded={open}
        className={cn(
          "flex min-w-0 w-full items-center gap-2 rounded-md px-1.5 py-0.5 text-left text-[13px] leading-5 transition-colors hover:bg-accent/60",
          "text-muted-foreground",
          active && "text-foreground/80",
        )}
        onClick={onClick}
        type="button"
      >
        {children}
      </button>
    </TooltipHint>
  );
}

/**
 * What a row expands to. Diffs get Monaco; a command gets the terminal
 * (the live stream from the client's own terminal, or what the adapter
 * streamed, or its final output); everything else shows input and result.
 */
export function ToolDetail({ part, sessionId, id }: { part: ToolCallPart; sessionId: string; id?: string }) {
  const diffs = part.content.filter((content) => content.type === "diff");
  const terminalRef = part.content.find((content) => content.type === "terminal");
  const terminalKey = terminalRef?.type === "terminal" ? `${sessionId}/${terminalRef.terminalId}` : null;
  const liveOutput = useAcp((state) => (terminalKey ? (state.terminalOutput[terminalKey] ?? null) : null));
  // A finished command with nothing to draw: silent, or its output was never held here (a
  // reload, a background session, a session let go of) — the two are not the same sentence.
  const notKept = useAcp((state) => (terminalKey ? state.coldTerminals[terminalKey] === true : false));
  const texts = part.content.filter((content) => content.type === "text");
  const images = part.content.filter((content) => content.type === "image");
  const links = part.content.filter((content) => content.type === "resource_link");
  const running = part.status === "pending" || part.status === "in_progress";
  const command = part.kind === "execute" ? activityRow(part).command : null;

  // The terminal keeps its last 64 KB (the newest output is what matters);
  // `capToolBody` is also what the text, input and result below are held to.
  const terminalBody =
    part.kind === "execute" || terminalRef
      ? capToolBody(liveOutput ?? (part.stream || outputText(part.output)), { keep: "tail" })
      : null;
  const terminalText = terminalBody?.text ?? null;
  const silence = notKept ? "Output not kept after reload" : "(no output)";

  return (
    <div className="ui-reveal mt-1 mb-2 ml-6 flex min-w-0 flex-col gap-2 text-[13px]" data-tool-detail id={id}>
      {command !== null ? (
        <pre className="overflow-x-auto rounded-md bg-muted/60 px-3 py-2 font-mono text-[12px] leading-5 whitespace-pre-wrap">
          {command}
        </pre>
      ) : null}
      {diffs.map((diff, index) =>
        diff.type === "diff" ? (
          <div key={`${diff.path}:${index}`}>
            <p className="mb-1 truncate font-mono text-[11px] text-muted-foreground">{diff.path}</p>
            <Suspense
              fallback={
                <div className="h-16 animate-pulse rounded-md border bg-muted/40" data-testid="diff-loading" />
              }
            >
              <DiffView newText={diff.newText} oldText={diff.oldText ?? ""} path={diff.path} />
            </Suspense>
          </div>
        ) : null,
      )}
      {terminalText !== null ? (
        <Terminal
          className="min-w-0 border bg-muted/40 text-foreground dark:bg-black/30"
          isStreaming={running}
          output={terminalText || (running ? "" : silence)}
        >
          <div className="max-h-72 overflow-auto px-3 py-2 font-mono text-[12px] leading-5">
            {(part.streamTruncated && liveOutput === null && part.stream) || (terminalBody?.hidden ?? 0) > 0 ? (
              // Only the stream's last 64 KB was kept (the reducer's cap), or
              // only its last 64 KB is drawn.
              <p className="mb-1 font-sans text-[11px] text-muted-foreground italic" data-stream-truncated>
                Earlier output trimmed
              </p>
            ) : null}
            <TerminalBody isStreaming={running} output={terminalText || (running ? "" : silence)} />
          </div>
        </Terminal>
      ) : null}
      {texts.map((text, index) => {
        if (text.type !== "text") return null;
        const body = capToolBody(text.text);
        return (
          <div className="rounded-md bg-muted/40" key={index}>
            <pre className="max-h-72 overflow-auto px-3 py-2 font-mono text-[12px] leading-5 whitespace-pre-wrap">
              {body.text}
            </pre>
            <TrimmedBody hidden={body.hidden} />
          </div>
        );
      })}
      {images.map((image, index) =>
        image.type === "image" ? (
          <img
            alt=""
            className="max-h-72 w-fit max-w-full rounded-md border"
            key={index}
            src={`data:${image.mimeType};base64,${image.data}`}
          />
        ) : null,
      )}
      {links.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {links.map((link, index) =>
            link.type === "resource_link" ? (
              <span className="min-w-0 rounded-md border px-2 py-0.5 break-words [overflow-wrap:anywhere] font-mono text-[11px]" key={index}>
                {link.name}
              </span>
            ) : null,
          )}
        </div>
      ) : null}
      {terminalText === null && diffs.length === 0 && part.input !== undefined ? (
        <ToolInput className="text-[12px]" input={part.input} />
      ) : null}
      {terminalText === null && part.output !== undefined ? (
        <ToolOutput
          className="text-[12px]"
          errorText={part.status === "failed" ? "The call failed" : undefined}
          output={part.output as never}
        />
      ) : null}
      {part.children.length > 0 ? (
        <div className="border-l pl-2">
          <PartsList open={running} parts={part.children} prefix={part.id} sessionId={sessionId} />
        </div>
      ) : null}
    </div>
  );
}

function TerminalBody({ output, isStreaming }: { output: string; isStreaming: boolean }) {
  // The AI Elements Terminal renders ANSI through its own content; this
  // body keeps its context (the streaming cursor; the transcript's Terminal
  // draws no copy button) but sizes to the transcript.
  return (
    <pre className="break-words whitespace-pre-wrap">
      {output}
      {isStreaming ? (
        <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-foreground/70 align-text-bottom" />
      ) : null}
    </pre>
  );
}

/** The adapters put a command's output in `rawOutput` under a handful of names. */
function outputText(output: unknown): string {
  if (typeof output === "string") {
    return output;
  }
  if (typeof output === "object" && output !== null) {
    const record = output as Record<string, unknown>;
    for (const key of ["formatted_output", "output", "stdout", "content", "text"]) {
      const value = record[key];
      if (typeof value === "string") {
        return value;
      }
    }
  }
  return "";
}
