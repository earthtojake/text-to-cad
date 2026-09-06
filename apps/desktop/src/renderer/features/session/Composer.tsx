import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Mic, Plus, X } from "lucide-react";
import { cn } from "cn";
import { toast } from "sonner";

import {
  Attachment,
  AttachmentInfo,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
} from "@renderer/components/ai-elements/attachments";
import {
  PromptInput,
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
  type PromptInputMessage,
} from "@renderer/components/ai-elements/prompt-input";
import {
  Queue,
  QueueItem,
  QueueItemAction,
  QueueItemActions,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
  QueueSection,
  QueueSectionContent,
  QueueSectionLabel,
  QueueSectionTrigger,
} from "@renderer/components/ai-elements/queue";
import type { FileUIPart } from "@renderer/components/ai-elements/types";
import { useComposer, useQueue } from "@renderer/state/composer";
import type { AvailableCommand, PromptBlock } from "@shared/acp/types";

/**
 * The composer (plan §2): "Do anything", `+` for attachments, the chips
 * the caller supplies, a mic placeholder, and send — which becomes stop
 * while a turn runs. Enter sends, Shift+Enter is a newline, a pasted image
 * becomes an attachment. Typing `/` opens the agent's slash commands.
 *
 * Shared by the new-session state and the live session: the chips differ,
 * the rest does not. Submission hands back the text and the ACP content
 * blocks; whether that creates a session or queues a prompt is the
 * caller's decision.
 */
export function Composer({
  sessionId,
  chips,
  commands,
  status,
  disabled,
  placeholder = "Do anything",
  autoFocus,
  onSubmit,
  onStop,
}: {
  /** Drafts and the queue are kept per session; null in the new-session state. */
  sessionId: string | null;
  chips: React.ReactNode;
  commands: AvailableCommand[];
  /** `streaming` shows stop; `submitted` shows a spinner (the session is being created). */
  status: "ready" | "submitted" | "streaming";
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  onSubmit: (text: string, content: PromptBlock[]) => Promise<void> | void;
  onStop?: () => void;
}) {
  // The draft lives in the composer store, per session, so switching
  // sessions and back does not lose typed text and a suggestion card can
  // fill the box from outside.
  const draftKey = sessionId ?? "__new__";
  const text = useComposer((state) => state.drafts[draftKey] ?? "");
  const setDraft = useComposer((state) => state.setDraft);
  const setText = useCallback(
    (value: string | ((current: string) => string)) => {
      const current = useComposer.getState().drafts[draftKey] ?? "";
      setDraft(draftKey, typeof value === "function" ? value(current) : value);
    },
    [draftKey, setDraft],
  );
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const queue = useQueue(sessionId);
  const dequeue = useComposer((state) => state.dequeue);

  useEffect(() => {
    if (autoFocus) {
      textRef.current?.focus();
    }
  }, [autoFocus, draftKey]);

  const slash = useSlashCommands(text, commands);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      const trimmed = message.text.trim();
      if (!trimmed && message.files.length === 0) {
        return;
      }
      const content = await toPromptBlocks(trimmed, message.files);
      if (content.length === 0) {
        return;
      }
      setText("");
      await onSubmit(trimmed, content);
    },
    [onSubmit, setText],
  );

  return (
    <div className="relative flex flex-col gap-2" data-composer>
      {queue.length > 0 && sessionId ? (
        <Queue className="rounded-xl px-2 pt-1 pb-1">
          <QueueSection defaultOpen>
            <QueueSectionTrigger className="px-2 py-1 text-[12px]">
              <QueueSectionLabel count={queue.length} label={queue.length === 1 ? "queued prompt" : "queued prompts"} />
            </QueueSectionTrigger>
            <QueueSectionContent>
              <QueueList className="mt-1">
                {queue.map((item) => (
                  <QueueItem className="py-0.5 text-[12px]" key={item.id}>
                    <div className="flex items-center gap-2">
                      <QueueItemIndicator />
                      <QueueItemContent>{item.text || "(attachments)"}</QueueItemContent>
                      <QueueItemActions>
                        <QueueItemAction
                          aria-label="Remove from queue"
                          onClick={() => {
                            const removed = dequeue(sessionId, item.id);
                            if (removed) {
                              setText((current) => (current ? current : removed.text));
                            }
                          }}
                        >
                          <X className="size-3" />
                        </QueueItemAction>
                      </QueueItemActions>
                    </div>
                  </QueueItem>
                ))}
              </QueueList>
            </QueueSectionContent>
          </QueueSection>
        </Queue>
      ) : null}

      {slash.open ? (
        <SlashPalette
          commands={slash.matches}
          onPick={(command) => {
            setText(`/${command.name} `);
            textRef.current?.focus();
          }}
          selected={slash.selected}
        />
      ) : null}

      <PromptInput
        className={cn("rounded-2xl shadow-xs", disabled && "opacity-70")}
        maxFileSize={20 * 1024 * 1024}
        multiple
        onError={(error) => toast.error(error.message)}
        onSubmit={handleSubmit}
      >
        <AttachmentStrip />
        {/*
         * No <PromptInputBody>: it renders `display: contents`, which the
         * InputGroup's direct-child stacking selector does not see, and the
         * composer collapses to one row.
         */}
        <PromptInputTextarea
          autoFocus={autoFocus}
          className="min-h-12 px-3 py-2.5 text-[13px] leading-5"
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (!slash.open) {
              return;
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              slash.move(event.key === "ArrowDown" ? 1 : -1);
            } else if ((event.key === "Enter" || event.key === "Tab") && slash.matches.length > 0) {
              event.preventDefault();
              const command = slash.matches[slash.selected];
              if (command) {
                setText(`/${command.name} `);
              }
            } else if (event.key === "Escape") {
              event.preventDefault();
              slash.dismiss();
            }
          }}
          placeholder={placeholder}
          ref={textRef}
          value={text}
        />
        <PromptInputFooter className="px-2 pb-1.5">
          <PromptInputTools className="min-w-0 flex-1 flex-wrap gap-0.5">
            <AttachButton disabled={disabled} />
            {chips}
          </PromptInputTools>
          <div className="flex shrink-0 items-center gap-0.5">
            <PromptInputButton
              aria-label="Voice input (coming later)"
              className="size-7 text-muted-foreground"
              disabled
              size="icon-sm"
              tooltip="Voice input is not available yet"
            >
              <Mic className="size-3.5" />
            </PromptInputButton>
            <PromptInputSubmit
              className={cn("size-7 rounded-full", status === "streaming" && "bg-foreground text-background")}
              disabled={disabled || status === "submitted"}
              onStop={onStop}
              size="icon-sm"
              status={status}
            />
          </div>
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
}

function AttachButton({ disabled }: { disabled?: boolean }) {
  const attachments = usePromptInputAttachments();
  return (
    <PromptInputButton
      aria-label="Attach files"
      className="size-7 text-muted-foreground"
      disabled={disabled}
      onClick={() => attachments.openFileDialog()}
      size="icon-sm"
      tooltip="Attach files or images"
    >
      <Plus className="size-4" />
    </PromptInputButton>
  );
}

/** The files waiting to go with the next prompt, above the textarea. */
function AttachmentStrip() {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0) {
    return null;
  }
  return (
    <PromptInputHeader className="px-2 pt-2">
      <Attachments variant="inline">
        {attachments.files.map((file) => (
          <Attachment className="h-7 text-[12px]" data={file} key={file.id} onRemove={() => attachments.remove(file.id)}>
            <AttachmentPreview className="size-4" />
            <AttachmentInfo className="max-w-[160px]" />
            <AttachmentRemove className="size-4" />
          </Attachment>
        ))}
      </Attachments>
    </PromptInputHeader>
  );
}

/* -------------------------------------------------------------------------- */
/* Slash commands                                                              */
/* -------------------------------------------------------------------------- */

function useSlashCommands(text: string, commands: AvailableCommand[]) {
  // The selection is remembered with the query it was made for, so a new
  // query starts at the top without an effect to reset it.
  const [selection, setSelection] = useState<{ query: string | null; index: number }>({ query: null, index: 0 });
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const match = /^\/(\S*)$/.exec(text);
  const query = match?.[1]?.toLowerCase() ?? null;
  const matches = useMemo(
    () =>
      query === null
        ? []
        : commands.filter((command) => command.name.toLowerCase().includes(query)).slice(0, 12),
    [commands, query],
  );
  const open = query !== null && matches.length > 0 && dismissedFor !== text;
  const selected = selection.query === query ? Math.min(selection.index, Math.max(0, matches.length - 1)) : 0;

  return {
    open,
    matches,
    selected,
    move: (delta: number) =>
      setSelection({
        query,
        index: matches.length === 0 ? 0 : (selected + delta + matches.length) % matches.length,
      }),
    dismiss: () => setDismissedFor(text),
  };
}

function SlashPalette({
  commands,
  selected,
  onPick,
}: {
  commands: AvailableCommand[];
  selected: number;
  onPick: (command: AvailableCommand) => void;
}) {
  return (
    <div
      className="absolute right-0 bottom-full left-0 z-20 mb-2 max-h-64 overflow-y-auto rounded-xl border bg-popover p-1 text-popover-foreground shadow-md"
      data-slash-palette
      role="listbox"
    >
      {commands.map((command, index) => (
        <button
          aria-selected={index === selected}
          className={cn(
            "flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-[13px]",
            index === selected ? "bg-accent text-accent-foreground" : "hover:bg-accent/60",
          )}
          key={command.name}
          onMouseDown={(event) => {
            // Before the textarea loses focus.
            event.preventDefault();
            onPick(command);
          }}
          role="option"
          type="button"
        >
          <span className="shrink-0 font-mono">/{command.name}</span>
          {command.hint ? <span className="shrink-0 text-muted-foreground">{command.hint}</span> : null}
          <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">{command.description}</span>
        </button>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Attachments → ACP content                                                   */
/* -------------------------------------------------------------------------- */

/**
 * The composer's files become ACP content blocks: images as `image`
 * (base64), text files embedded as `resource` so the agent has the
 * content whether or not its sandbox can reach the path. Anything else is
 * refused with a toast rather than sent as bytes the agent cannot read.
 */
export async function toPromptBlocks(text: string, files: FileUIPart[]): Promise<PromptBlock[]> {
  const blocks: PromptBlock[] = [];
  if (text) {
    blocks.push({ type: "text", text });
  }
  for (const file of files) {
    const parsed = parseDataUrl(file.url ?? "");
    if (!parsed) {
      continue;
    }
    const mimeType = file.mediaType || parsed.mimeType || "application/octet-stream";
    const name = file.filename || "attachment";
    if (mimeType.startsWith("image/")) {
      blocks.push({ type: "image", data: parsed.base64, mimeType, uri: null });
      continue;
    }
    const decoded = decodeText(parsed.base64);
    if (decoded === null) {
      toast.error(`${name} is not text or an image, so it was not attached.`);
      continue;
    }
    blocks.push({ type: "resource", uri: `attachment:///${encodeURIComponent(name)}`, text: decoded, mimeType });
  }
  return blocks;
}

function parseDataUrl(url: string): { mimeType: string; base64: string } | null {
  const match = /^data:([^;,]*)(?:;[^,]*)?;base64,(.*)$/s.exec(url);
  if (!match) {
    return null;
  }
  return { mimeType: match[1] ?? "", base64: match[2] ?? "" };
}

function decodeText(base64: string): string | null {
  try {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    const probe = bytes.subarray(0, 8192);
    if (probe.includes(0)) {
      return null;
    }
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}
