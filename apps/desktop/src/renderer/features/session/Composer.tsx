import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Paperclip, X } from "lucide-react";
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
  PromptInputHeader,
  PromptInputSubmit,
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
import { NEW_SESSION_KEY, useComposer, useQueue } from "@renderer/state/composer";
import { useActiveProject } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { AvailableCommand, PromptBlock } from "@shared/acp/types";

import {
  AttachmentFiles,
  attachmentRefusal,
  dataUrlOf,
  MAX_ATTACHMENT_BYTES,
  MAX_INLINE_TEXT_BYTES,
  openAttachmentFiles,
  screenAttachments,
} from "./composer/attachments";
import { AttachmentImagePreview } from "./composer/AttachmentImagePreview";
import { ComposerEditor, type ComposerEditorHandle } from "./composer/ComposerEditor";
import { ReferenceScopeContext } from "./composer/ReferenceScope";
import { AnnotationsChip, annotationImageParts, withAnnotations } from "./composer/AnnotationsChip";
import type { DraftAnnotation, TakenDraft } from "@renderer/state/composer";

const NO_ANNOTATIONS: DraftAnnotation[] = [];

/**
 * The composer (plan §2): "Do anything", the `+` menu, the chips the caller
 * supplies, and send — which becomes stop while a turn runs. Enter sends,
 * Shift+Enter is a newline, Escape stops a running turn, a pasted image
 * becomes an attachment. Typing `/` opens the agent's slash commands.
 *
 * The box holds the sentence and send, and nothing else. Everything the
 * caller supplies — `+`, `chips` on the left, `trailing` on the right — is
 * one row **under** the box (Claude Code's), so the thing being typed into
 * is a box with writing in it rather than a box with a toolbar in it.
 * Nothing wraps — the chips truncate — so that row is the same height at
 * 560px as at 1200px.
 *
 * **The box is one row until there is more to show.** Empty, it is a single
 * line with send centred at its right end; it grows with the sentence to
 * eight lines and then scrolls inside (the min and the max are the editor's,
 * `composer/ComposerEditor`). A composer that starts three lines tall is
 * three lines of nothing, and the prompt most people send is short.
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
 * its attachments, its submit — is untouched; the editor keeps the form's
 * `message` field for it. Its footer is not used: send sits beside the
 * sentence, not under it.
 */
export function Composer({
  sessionId,
  newDraftKey,
  chips,
  trailing,
  commands,
  status,
  disabled,
  placeholder = "Do anything",
  autoFocus,
  refuseSend,
  onSubmit,
  onStop,
}: {
  /** Drafts and the queue are kept per session; null in the new-session state. */
  sessionId: string | null;
  newDraftKey?: string;
  chips: React.ReactNode;
  /** The row's right-hand end: the model, the effort, the context ring. */
  trailing?: React.ReactNode;
  commands: AvailableCommand[];
  /** `streaming` shows stop; `submitted` shows a spinner (the session is being created). */
  status: "ready" | "submitted" | "streaming";
  disabled?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  /**
   * Why a send cannot go out now. The box still takes a draft; send is shown unavailable and
   * says this, the way a chip with a `disabledReason` does, and the draft stays where it is.
   */
  refuseSend?: string;
  /** `draft` is what the box held, kept apart, so a queued prompt can be put back as it was. */
  onSubmit: (text: string, content: PromptBlock[], draft: TakenDraft) => Promise<void> | void;
  onStop?: () => void;
}) {
  // The draft lives in the composer store, per session, so switching
  // sessions and back does not lose typed text and a suggestion card can
  // fill the box from outside.
  const draftKey = sessionId ?? newDraftKey ?? NEW_SESSION_KEY;
  const refuseId = useId();
  const project = useActiveProject();
  const session = useSessions((state) => state.sessions.find((item) => item.id === sessionId));
  const draftRoot = useComposer((state) => state.draftRoots[draftKey]);
  const referenceScope = useMemo(() => {
    if (!project || (sessionId && (!session || session.projectId !== project.id))) return null;
    const cwd = session?.cwd ?? draftRoot ?? project.path;
    return { projectId: project.id, root: cwd === project.path ? null : cwd, draftKey };
  }, [project, sessionId, session, draftRoot, draftKey]);
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
  const focusRequest = useComposer((state) => state.focusRequest?.key === draftKey ? state.focusRequest.nonce : null);
  useEffect(() => {
    if (focusRequest !== null) textRef.current?.focus();
  }, [focusRequest]);
  // A send asked for from outside (the new-session state's Try again) is Enter's send: the form
  // submits what the box holds now, through `handleSubmit` below. The request is consumed when it
  // is handled, and one already in the store when this composer mounted is not this composer's to
  // act on — either way a composer for the same key arriving later never sends its box unasked.
  const submitRequest = useComposer((state) => state.submitRequest?.key === draftKey ? state.submitRequest.nonce : null);
  const staleSubmitRequest = useRef(useComposer.getState().submitRequest?.nonce ?? null);
  useEffect(() => {
    if (submitRequest === null || submitRequest === staleSubmitRequest.current) return;
    useComposer.getState().consumeSubmit(submitRequest);
    const form = textRef.current?.form() ?? null;
    const submit = form?.querySelector('button[type="submit"]') as HTMLButtonElement | null;
    if (form && !submit?.disabled) form.requestSubmit();
  }, [submitRequest]);

  // The files behind this box's attachments (`composer/attachments.ts`), for as long as it is mounted.
  const [attachmentFiles] = useState(() => new AttachmentFiles());
  useEffect(() => openAttachmentFiles(attachmentFiles), [attachmentFiles]);
  // The form's attachments, for the `+` that now sits outside the form.
  const attachmentsRef = useRef<AttachmentsHandle | null>(null);
  // Every way a file reaches the box — the paperclip, a paste, a drop, the viewer — is sorted here
  // first (`screenAttachments`): refused files are refused now, with the reason, rather than shown
  // as attached and dropped at send; a CAD file the project holds goes in as its reference.
  const admit = useCallback<Admit>(async (files, add) => {
    const scope = referenceScope ? { projectId: referenceScope.projectId, root: referenceScope.root } : null;
    const screened = await screenAttachments(files, scope);
    for (const message of screened.refusals) {
      toast.error(message);
    }
    for (const reference of screened.references) {
      useComposer.getState().insertReference(draftKey, reference);
    }
    if (screened.attach.length > 0) {
      add(attachmentFiles.remember(screened.attach));
    }
  }, [referenceScope, draftKey, attachmentFiles]);
  const queue = useQueue(sessionId);
  const dequeue = useComposer((state) => state.dequeue);
  // A failed turn holds the queue until the next turn starts; said here, with a way to go on.
  const queuePaused = useComposer((state) => (sessionId ? sessionId in state.paused : false));

  useEffect(() => {
    if (autoFocus) {
      textRef.current?.focus();
    }
  }, [autoFocus, draftKey]);

  const slash = useSlashCommands(text, commands);
  const annotations = useComposer((state) => state.annotations[draftKey] ?? NO_ANNOTATIONS);
  const removeAnnotations = useComposer((state) => state.removeAnnotations);
  const editAnnotation = useComposer((state) => state.editAnnotation);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      if (refuseSend) {
        toast.info(refuseSend);
        // Rejected, so the form keeps its attachments; the draft was never taken.
        throw new Error(refuseSend);
      }
      // Annotations added from the viewer go out with the prompt, after what was typed.
      const pending = useComposer.getState().annotations[draftKey] ?? NO_ANNOTATIONS;
      const trimmed = withAnnotations(message.text.trim(), pending);
      if (!trimmed && message.files.length === 0) {
        return;
      }
      // A note's sketch goes out with it, after the form's own attachments.
      const content = await toPromptBlocks(trimmed, [...message.files, ...await annotationImageParts(pending)], attachmentFiles);
      if (content.length === 0) {
        return;
      }
      // The box empties now, but what it held is kept whole — the typed text and the annotations
      // apart, with their chips' labels — rather than as the flattened prompt: a start that fails
      // puts it back as it was (the catch below), and so does taking it out of the queue.
      const taken = useComposer.getState().takeDraft(draftKey);
      // With its files, for a refusal that comes back after the box has let them go.
      const files = message.files.flatMap((part) => attachmentFiles.fileFor(part) ?? []);
      const sent = files.length ? { ...taken, files } : taken;
      // The strip empties with the text, now: `onSubmit` settles when the turn ends, and waiting
      // for that kept the image chip on screen through the whole turn, sent it again with the
      // next message typed meanwhile, and let the form's late clear wipe a file attached since.
      attachmentsRef.current?.clear();
      // Not awaited for the same reason. A start that fails puts the draft back as it was, its
      // files in the strip again (`restoreDraft`), from wherever the rejection arrives.
      void (async () => {
        try {
          await onSubmit(trimmed, content, sent);
        } catch {
          useComposer.getState().restoreDraft(draftKey, sent);
        }
      })();
    },
    [onSubmit, refuseSend, draftKey, attachmentFiles],
  );

  return (
    <div
      className="relative flex flex-col gap-2"
      data-composer
      onDropCapture={(event) => {
        // Ahead of the vendored form's own drop handler, which would attach the file unchecked.
        const dropped = [...(event.dataTransfer?.files ?? [])];
        if (dropped.length === 0) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        const add = attachmentsRef.current?.add;
        if (add) {
          void admit(dropped, add);
        }
      }}
    >
      {queue.length > 0 && sessionId ? (
        <Queue className="rounded-xl px-2 pt-1 pb-1">
          <QueueSection defaultOpen>
            <QueueSectionTrigger className="px-2 py-1 text-[12px]">
              <QueueSectionLabel count={queue.length} label={queue.length === 1 ? "queued prompt" : "queued prompts"} />
            </QueueSectionTrigger>
            {/* Always mounted, so the text arriving in it is announced; the button stays outside. */}
            <div className="flex items-center justify-between gap-2 px-2 text-[12px] text-muted-foreground">
              <span aria-live="polite" role="status">{queuePaused ? "Paused after an error" : ""}</span>
              {queuePaused ? (
                <button
                  className="my-1 rounded-md px-2 py-0.5 font-medium text-foreground hover:bg-muted"
                  onClick={() => void useComposer.getState().resume(sessionId)}
                  type="button"
                >
                  Resume
                </button>
              ) : null}
            </div>
            <QueueSectionContent>
              <QueueList className="mt-1">
                {queue.map((item) => (
                  <QueueItem className="py-0.5 text-[12px]" key={item.id}>
                    <div className="flex items-center gap-2">
                      <QueueItemIndicator />
                      <QueueItemContent>{item.text || "(attachments)"}</QueueItemContent>
                      <QueueItemActions>
                        <QueueItemAction
                          aria-label={`Remove from queue: ${(item.text || "attachments").slice(0, 40)}`}
                          onClick={() => {
                            const removed = dequeue(sessionId, item.id);
                            if (removed?.draft) {
                              useComposer.getState().restoreDraft(draftKey, removed.draft);
                            } else if (removed) {
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

      <div className="flex flex-col gap-1">
        <PromptInput
          className={cn(
            "rounded-2xl shadow-xs",
            // shadcn's `input-group` is a fixed `h-9` unless one of its own
            // children is a textarea or a block-aligned addon. The editor is
            // neither, and send is now on its row rather than in a footer, so
            // without this the box is 36px tall whatever is in it — and
            // `overflow-hidden` on the group means the second line is simply
            // not drawn. The height comes from the editor's min/max instead.
            "[&>[data-slot=input-group]]:h-auto",
            disabled && "opacity-70",
          )}
          maxFileSize={MAX_ATTACHMENT_BYTES}
          multiple
          onError={(error) => toast.error(error.message)}
          onSubmit={handleSubmit}
        >
          <AttachmentStrip
            annotations={<AnnotationsChip annotations={annotations} onEdit={(id, text) => editAnnotation(draftKey, id, text)}
              onRemove={() => removeAnnotations(draftKey)} onRemoveOne={(id) => removeAnnotations(draftKey, [id])} scope={referenceScope} />}
            hasAnnotations={annotations.length > 0}
          />
          <AttachmentSink admit={admit} draftKey={draftKey} />
          <AttachmentBridge targetRef={attachmentsRef} />
          <AttachmentFilesSync files={attachmentFiles} />
          {/*
           * No <PromptInputBody>: it renders `display: contents`, which the
           * InputGroup's direct-child stacking selector does not see, and the
           * composer collapses to one row.
           */}
          {/*
           * The sentence and send share one row, so an empty composer is one
           * line tall with send centred on it (Codex's, Claude Code's). Send
           * in a footer under the box made the smallest possible composer two
           * rows: a line to type in and a line holding one button.
           */}
          <div className="flex w-full min-w-0 items-center gap-1 pr-1.5">
            <ReferenceScopeContext.Provider value={referenceScope}>
              <ComposerEditorField
                admit={admit}
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
            </ReferenceScopeContext.Provider>
            <PromptInputSubmit
              className={cn(
                "size-7 shrink-0 rounded-full",
                status === "streaming" && "bg-foreground text-background",
                refuseSend && status === "ready" && "cursor-not-allowed opacity-50",
              )}
              aria-describedby={refuseSend ? refuseId : undefined}
              aria-disabled={refuseSend ? "true" : undefined}
              disabled={disabled || status === "submitted"}
              onStop={onStop}
              size="icon-sm"
              status={status}
            />
          </div>
        </PromptInput>
        {refuseSend ? <span className="sr-only" id={refuseId}>{refuseSend}</span> : null}

        {/*
         * The row, under the box. `+` and the caller's chips on the left,
         * the caller's `trailing` on the right with a wider gap between its
         * items — the model, the effort and the ring are three separate
         * things, and reading them as one run of text is the thing the gap
         * prevents.
         */}
        <div className="flex h-7 items-center gap-1 px-0.5" data-composer-row>
          <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-hidden">
            <AttachButton admit={admit} attachmentsRef={attachmentsRef} disabled={disabled} />
            {chips}
          </div>
          <div className="flex min-w-0 shrink-0 items-center gap-2">{trailing}</div>
        </div>
      </div>
    </div>
  );
}

/**
 * The form's attachments, reachable from outside the form.
 *
 * `usePromptInputAttachments` only answers inside `<PromptInput>`, and the
 * `+` is no longer inside it. Rather than lift the vendored component's
 * state into a provider — which swaps its validated `add` (the size limit,
 * the accept list) for the provider's unchecked one — this renders nothing
 * inside the form and hands the context out through a ref. The `+` reads it
 * when it is clicked, which is always after this has mounted.
 */
function AttachmentBridge({ targetRef }: { targetRef: React.RefObject<AttachmentsHandle | null> }) {
  const attachments = usePromptInputAttachments();
  useEffect(() => {
    targetRef.current = attachments;
    return () => {
      if (targetRef.current === attachments) {
        targetRef.current = null;
      }
    };
  }, [attachments, targetRef]);
  return null;
}

/** The box's attachments, told to its files as they change: a new one is bound, a gone one let go. */
function AttachmentFilesSync({ files }: { files: AttachmentFiles }) {
  const attachments = usePromptInputAttachments();
  useEffect(() => files.sync(attachments.files), [files, attachments.files]);
  return null;
}

type AttachmentsHandle = ReturnType<typeof usePromptInputAttachments>;
/** Sort files, then hand what may be attached to the form's `add`. */
type Admit = (files: readonly File[], add: (files: File[]) => void) => Promise<void>;

/**
 * The editor, with the three things the textarea did for the form: Enter
 * submits unless the submit button says no, Backspace on an empty box
 * removes the last attachment, and files on the clipboard become
 * attachments. All three need `usePromptInputAttachments`, so this lives
 * inside `PromptInput`.
 */
function ComposerEditorField({
  admit,
  handle,
  onKeyDown,
  ...props
}: Omit<React.ComponentProps<typeof ComposerEditor>, "onSubmit" | "onPasteFiles" | "onKeyDown"> & {
  admit: Admit;
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
      onPasteFiles={(files) => void admit(files, attachments.add)}
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
function AttachmentSink({ admit, draftKey }: { admit: Admit; draftKey: string }) {
  const attachments = usePromptInputAttachments();
  const pending = useComposer((state) => state.pendingFiles[draftKey]);
  const takeFiles = useComposer((state) => state.takeFiles);
  useEffect(() => {
    if (pending && pending.length > 0) {
      void admit(takeFiles(draftKey), attachments.add);
    }
  }, [pending, attachments, takeFiles, draftKey, admit]);
  return null;
}

/**
 * The paperclip: files and photos from disk, in one picker. The input is this
 * component's own rather than the vendored form's: the files have to be
 * remembered (`composer/attachments.ts`) before they become blob URLs, and
 * only this side can do that. A capture of the CAD view comes from the
 * viewer's own camera button and lands in the same place.
 *
 * It sits in the row under the box, so the form's attachments reach it
 * through `AttachmentBridge`'s ref rather than through the form's context.
 */
function AttachButton({
  admit,
  attachmentsRef,
  disabled,
}: {
  admit: Admit;
  attachmentsRef: React.RefObject<AttachmentsHandle | null>;
  disabled?: boolean;
}) {
  const files = useRef<HTMLInputElement | null>(null);
  const take = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = [...(event.currentTarget.files ?? [])];
    event.currentTarget.value = "";
    const add = attachmentsRef.current?.add;
    if (picked.length > 0 && add) {
      void admit(picked, add);
    }
  };
  return (
    <>
      <input aria-hidden className="hidden" data-attach-input multiple onChange={take} ref={files} tabIndex={-1} type="file" />
      <TooltipHint content="Attach files or photos" side="bottom">
        <PromptInputButton
          aria-label="Attach files or photos"
          className="size-7 text-muted-foreground"
          disabled={disabled}
          onClick={() => files.current?.click()}
          size="icon-sm"
        >
          <Paperclip className="size-4" />
        </PromptInputButton>
      </TooltipHint>
    </>
  );
}

/**
 * What waits to go with the next prompt, above the textarea: the viewer's annotations, as one
 * chip, then the files.
 */
function AttachmentStrip({ annotations, hasAnnotations }: { annotations: React.ReactNode; hasAnnotations: boolean }) {
  const attachments = usePromptInputAttachments();
  if (attachments.files.length === 0 && !hasAnnotations) {
    return null;
  }
  return (
    <PromptInputHeader className="px-2 pt-2">
      <Attachments variant="inline">
        {annotations}
        {attachments.files.map((file) => {
          const isImage = file.mediaType?.startsWith("image/");
          return (
            <Attachment
              className={cn(
                "cursor-default text-[12px]",
                isImage ? "h-auto w-[280px] max-w-full gap-2 rounded-xl bg-muted/30 p-2" : "h-8 max-w-full",
              )}
              data={file}
              key={file.id}
              onRemove={() => attachments.remove(file.id)}
              title={file.filename}
            >
              {isImage ? <AttachmentImagePreview file={file} /> : <AttachmentPreview className="size-4" />}
              <AttachmentInfo className={isImage ? "min-w-0 text-[11px] leading-4" : "max-w-[160px]"} />
              <AttachmentRemove className="size-6 opacity-60 hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring" />
            </Attachment>
          );
        })}
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
 * content whether or not its sandbox can reach the path. What may be attached
 * is decided when a file is added (`screenAttachments`); the checks here are
 * the backstop for a file that reached the form another way, and refuse with
 * the same words rather than send bytes the agent cannot read.
 * The bytes come through `dataUrlOf`: the vendored form's own blob fetch
 * fails on a `file://` renderer (`composer/attachments.ts`).
 */
export async function toPromptBlocks(text: string, files: FileUIPart[], remembered: AttachmentFiles | null = null): Promise<PromptBlock[]> {
  const blocks: PromptBlock[] = [];
  if (text) {
    blocks.push({ type: "text", text });
  }
  for (const file of files) {
    const parsed = parseDataUrl((await dataUrlOf(file, remembered)) ?? "");
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
      toast.error(attachmentRefusal.notText(name));
      continue;
    }
    if (new TextEncoder().encode(decoded).length > MAX_INLINE_TEXT_BYTES) {
      toast.error(attachmentRefusal.tooLarge(name));
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
