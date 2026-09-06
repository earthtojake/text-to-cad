import { Suspense, lazy, useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { cn } from "cn";

import { Terminal } from "@renderer/components/ai-elements/terminal";
import { ToolInput, ToolOutput } from "@renderer/components/ai-elements/tool";
import { useAcp } from "@renderer/state/acp";
import type { ToolCallPart } from "@shared/acp/types";

import { GlyphIcon } from "../glyphs";
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
  const active = item.rows.some((row) => row.status === "pending" || row.status === "in_progress");
  const failed = item.rows.some((row) => row.status === "failed");

  if (item.summary === null) {
    return <ActivityRowView row={item.rows[0]!} sessionId={sessionId} />;
  }

  return (
    <div className="not-prose" data-activity-group data-open={open}>
      <RowButton
        active={active}
        failed={failed}
        onClick={() => setOpen((value) => !value)}
        open={open}
      >
        <span className="flex size-4 items-center justify-center text-muted-foreground">
          {active ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          )}
        </span>
        <span className="min-w-0 flex-1 truncate">{item.summary}</span>
      </RowButton>
      {open ? (
        <div className="ml-2 border-l pl-2">
          {item.rows.map((row) => (
            <ActivityRowView key={row.id} row={row} sessionId={sessionId} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ActivityRowView({ row, sessionId }: { row: ActivityRow; sessionId: string }) {
  const [open, setOpen] = useState(false);
  const active = row.status === "pending" || row.status === "in_progress";
  const failed = row.status === "failed";
  const label = row.label;
  const command = row.command ? commandLine(row.command) : null;

  return (
    <div className="not-prose" data-activity-row={row.id} data-status={row.status}>
      <RowButton
        active={active}
        failed={failed}
        onClick={() => setOpen((value) => !value)}
        open={open}
        title={row.path ?? row.command ?? row.part.title}
      >
        <span className="flex size-4 items-center justify-center text-muted-foreground">
          {active ? <Loader2 className="size-3.5 animate-spin" /> : <GlyphIcon glyph={row.glyph} />}
        </span>
        <span className="flex min-w-0 flex-1 items-baseline gap-2">
          {label ? (
            <span className="shrink-0 truncate">{label}</span>
          ) : null}
          {command ? (
            <span className="min-w-0 truncate font-mono text-[12px] text-foreground/80">{command}</span>
          ) : null}
        </span>
        {row.insertions + row.deletions > 0 ? (
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
            +{row.insertions} −{row.deletions}
          </span>
        ) : null}
      </RowButton>
      {open ? <ToolDetail part={row.part} sessionId={sessionId} /> : null}
    </div>
  );
}

function RowButton({
  children,
  open,
  active,
  failed,
  onClick,
  title,
}: {
  children: React.ReactNode;
  open: boolean;
  active: boolean;
  failed: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      aria-expanded={open}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] leading-5 transition-colors hover:bg-accent/60",
        failed ? "text-destructive" : "text-muted-foreground",
        active && "text-foreground/80",
      )}
      onClick={onClick}
      title={title}
      type="button"
    >
      {children}
    </button>
  );
}

/**
 * What a row expands to. Diffs get Monaco; a command gets the terminal
 * (the live stream from the client's own terminal, or what the adapter
 * streamed, or its final output); everything else shows input and result.
 */
export function ToolDetail({ part, sessionId }: { part: ToolCallPart; sessionId: string }) {
  const diffs = part.content.filter((content) => content.type === "diff");
  const terminalRef = part.content.find((content) => content.type === "terminal");
  const terminalKey = terminalRef?.type === "terminal" ? `${sessionId}/${terminalRef.terminalId}` : null;
  const liveOutput = useAcp((state) => (terminalKey ? (state.terminalOutput[terminalKey] ?? null) : null));
  const texts = part.content.filter((content) => content.type === "text");
  const images = part.content.filter((content) => content.type === "image");
  const links = part.content.filter((content) => content.type === "resource_link");
  const running = part.status === "pending" || part.status === "in_progress";
  const command = part.kind === "execute" ? activityRow(part).command : null;

  const terminalText =
    part.kind === "execute" || terminalRef
      ? (liveOutput ?? (part.stream || outputText(part.output)))
      : null;

  return (
    <div className="mt-1 mb-2 ml-6 flex flex-col gap-2 text-[13px]" data-tool-detail>
      {command !== null && command.includes("\n") ? (
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
          className="border bg-muted/40 text-foreground dark:bg-black/30"
          isStreaming={running}
          output={terminalText || (running ? "" : "(no output)")}
        >
          <div className="max-h-72 overflow-auto px-3 py-2 font-mono text-[12px] leading-5">
            <TerminalBody isStreaming={running} output={terminalText} />
          </div>
        </Terminal>
      ) : null}
      {texts.map((text, index) =>
        text.type === "text" ? (
          <pre
            className="max-h-72 overflow-auto rounded-md bg-muted/40 px-3 py-2 font-mono text-[12px] leading-5 whitespace-pre-wrap"
            key={index}
          >
            {text.text}
          </pre>
        ) : null,
      )}
      {images.map((image, index) =>
        image.type === "image" ? (
          <img
            alt=""
            className="max-h-72 w-fit rounded-md border"
            key={index}
            src={`data:${image.mimeType};base64,${image.data}`}
          />
        ) : null,
      )}
      {links.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {links.map((link, index) =>
            link.type === "resource_link" ? (
              <span className="rounded-md border px-2 py-0.5 font-mono text-[11px]" key={index}>
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
  // body keeps its context (copy button, streaming cursor) but sizes to the
  // transcript.
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
