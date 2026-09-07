import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Camera, Image, Paperclip, Plus, X } from "lucide-react";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { NEW_SESSION_KEY, useComposer, useQueue } from "@renderer/state/composer";
import { useExplorer } from "@renderer/state/explorer";
import type { AvailableCommand, PromptBlock } from "@shared/acp/types";

import { isCadPath } from "../explorer/renderers/registry";
import { dataUrlOf, rememberFiles } from "./composer/attachments";
import { ComposerEditor, type ComposerEditorHandle } from "./composer/ComposerEditor";

/**
 * The composer (plan §2): "Do anything", the `+` menu, the chips the caller
 * supplies, and send — which becomes stop while a turn runs. Enter sends,
 * Shift+Enter is a newline, Escape stops a running turn, a pasted image
 * becomes an attachment. Typing `/` opens the agent's slash commands.
 *
 * One row, Codex's: `+` and the caller's `chips` on the left, the caller's
 * `trailing` chips (the model, the effort) then send on the right. Nothing
 * wraps — the chips truncate — so the box is the same height at 560px as at
 * 1200px.
 *
 * There is no microphone. There is no dictation backend behind one, and on
 * macOS the system's own dictation already types into this box; a button
 * that is permanently disabled is a promise the app does not keep.
 *
 * Shared by the new-session state and the live session: the chips differ,
 * the rest does not. Submission hands back the text and the ACP content
 * blocks; whether that creates a session or queues a prompt is the
 * caller's decision.
 *
 * The input is `composer/ComposerEditor`, not AI Elements' textarea: a CAD
 * reference typed, pasted or copied in from the viewer is drawn as a chip in
 * the sentence and sent as its plain token. `PromptInput` itself — the form,
 * the attachments, the footer — is untouched; the editor keeps the form's
 * `message` field for it.
 */
export function Composer({
  sessionId,
  chips,
  trailing,
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
  /** Chips on the right, before the mic and send. */
  trailing?: React.ReactNode;
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
  const draftKey = sessionId ?? NEW_SESSION_KEY;
  const text = useComposer((state) => state.drafts[draftKey] ?? "");
  const setDraft = useComposer((state) => state.setDraft);
  const setText = useCallback(
    (value: string | ((current: string) => string)) => {
      const current = useComposer.getState().drafts[draftKey] ?? "";
      setDraft(draftKey, typeof value === "function" ? value(current) : value);
    },
    [draftKey, setDraft],
  );
  const textRef = useRef<ComposerEditorHandle | null>(null);
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
        <AttachmentSink draftKey={draftKey} />
        {/*
         * No <PromptInputBody>: it renders `display: contents`, which the
         * InputGroup's direct-child stacking selector does not see, and the
         * composer collapses to one row.
         */}
        <ComposerEditorField
          autoFocus={autoFocus}
          disabled={disabled}
          handle={textRef}
          onChange={setText}
          onKeyDown={(event) => {
            if (!slash.open) {
              if (event.key === "Escape" && status === "streaming" && onStop) {
                event.preventDefault();
                onStop();
              }
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
          value={text}
        />
        <PromptInputFooter className="flex-nowrap px-2 pb-1.5">
          <PromptInputTools className="min-w-0 flex-1 flex-nowrap gap-0.5 overflow-hidden">
            <AttachButton disabled={disabled} />
            {chips}
          </PromptInputTools>
          <div className="flex min-w-0 shrink-0 items-center gap-0.5">
            {trailing}
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

/**
 * The editor, with the three things the textarea did for the form: Enter
 * submits unless the submit button says no, Backspace on an empty box
 * removes the last attachment, and files on the clipboard become
 * attachments. All three need `usePromptInputAttachments`, so this lives
 * inside `PromptInput`.
 */
function ComposerEditorField({
  handle,
  onKeyDown,
  ...props
}: Omit<React.ComponentProps<typeof ComposerEditor>, "onSubmit" | "onPasteFiles" | "onKeyDown"> & {
  handle: React.RefObject<ComposerEditorHandle | null>;
  onKeyDown: (event: React.KeyboardEvent) => void;
}) {
  const attachments = usePromptInputAttachments();
  return (
    <ComposerEditor
      {...props}
      handle={handle}
      onKeyDown={(event) => {
        onKeyDown(event);
        if (event.defaultPrevented) {
          return;
        }
        if (event.key === "Backspace" && handle.current?.isEmpty() && attachments.files.length > 0) {
          event.preventDefault();
          const last = attachments.files.at(-1);
          if (last) {
            attachments.remove(last.id);
          }
        }
      }}
      onPasteFiles={(files) => attachments.add(rememberFiles(files))}
      onSubmit={() => {
        const form = handle.current?.form() ?? null;
        const submit = form?.querySelector('button[type="submit"]') as HTMLButtonElement | null;
        if (form && !submit?.disabled) {
          form.requestSubmit();
        }
      }}
    />
  );
}

/**
 * Files the explorer attached — a capture of the viewer — reach the form's
 * attachments here, the one place inside `PromptInput` that can add them.
 */
function AttachmentSink({ draftKey }: { draftKey: string }) {
  const attachments = usePromptInputAttachments();
  const pending = useComposer((state) => state.pendingFiles[draftKey]);
  const takeFiles = useComposer((state) => state.takeFiles);
  useEffect(() => {
    if (pending && pending.length > 0) {
      attachments.add(rememberFiles(takeFiles(draftKey)));
    }
  }, [pending, attachments, takeFiles, draftKey]);
  return null;
}

/**
 * The `+`: a menu of the three ways something gets into a prompt — a file
 * from disk, an image from disk, and the view in the CAD tab.
 *
 * The file inputs are this component's own rather than the vendored form's:
 * the files have to be remembered (`composer/attachments.ts`) before they
 * become blob URLs, and only this side can do that. `Capture from viewer` is
 * the same capture as the viewer's own camera button and lands in the same
 * place — it is disabled, not hidden, when no CAD file is open, because the
 * answer to "why can I not do that" should be visible.
 */
function AttachButton({ disabled }: { disabled?: boolean }) {
  const attachments = usePromptInputAttachments();
  const files = useRef<HTMLInputElement | null>(null);
  const images = useRef<HTMLInputElement | null>(null);
  const cadTabId = useExplorer((state) => state.tabs.find((tab) => tab.id === state.activeId && isCadTab(tab))?.id
    ?? state.tabs.find(isCadTab)?.id
    ?? null);
  const captureCad = useExplorer((state) => state.captureCad);
  const take = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = [...(event.currentTarget.files ?? [])];
    event.currentTarget.value = "";
    if (picked.length > 0) {
      attachments.add(rememberFiles(picked));
    }
  };
  return (
    <>
      <input aria-hidden className="hidden" multiple onChange={take} ref={files} tabIndex={-1} type="file" />
      <input
        accept="image/*"
        aria-hidden
        className="hidden"
        multiple
        onChange={take}
        ref={images}
        tabIndex={-1}
        type="file"
      />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <PromptInputButton
            aria-label="Add to this prompt"
            className="size-7 text-muted-foreground"
            disabled={disabled}
            size="icon-sm"
          >
            <Plus className="size-4" />
          </PromptInputButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56" side="top">
          <DropdownMenuItem onSelect={() => files.current?.click()}>
            <Paperclip className="size-3.5" />
            Attach files…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => images.current?.click()}>
            <Image className="size-3.5" />
            Attach image…
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!cadTabId}
            onSelect={() => {
              if (cadTabId) {
                captureCad(cadTabId);
              }
            }}
          >
            <Camera className="size-3.5" />
            Capture from viewer
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

/** A file tab the CAD viewer is rendering — the one a capture can come from. */
function isCadTab(tab: { kind: string; path?: string | null }): boolean {
  return tab.kind === "file" && !!tab.path && isCadPath(tab.path);
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
 * The bytes come through `dataUrlOf`: the vendored form's own blob fetch
 * fails on a `file://` renderer (`composer/attachments.ts`).
 */
export async function toPromptBlocks(text: string, files: FileUIPart[]): Promise<PromptBlock[]> {
  const blocks: PromptBlock[] = [];
  if (text) {
    blocks.push({ type: "text", text });
  }
  for (const file of files) {
    const parsed = parseDataUrl((await dataUrlOf(file)) ?? "");
    if (!parsed) {
      toast.error(`${file.filename ?? "An attachment"} could not be read, so it was not attached.`);
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
