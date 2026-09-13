import type { AttachmentMimeType, AttachmentRef } from '@emdash/core/runtimes/acp/api/client';
import { ChatComposer, ImageViewerDialog, MermaidViewerDialog } from '@emdash/ui/react/components';
import type {
  CommandItem,
  ComposerAgentOption,
  ComposerAttachment,
  ComposerPermissionRequest,
  ContextMentionProvider,
  MentionItem,
  PromptEditorRef,
} from '@emdash/ui/react/components';
import { Button, toast } from '@emdash/ui/react/primitives';
import { ArrowDown, Loader2 } from 'lucide-react';
import { observer, useObserver } from 'mobx-react-lite';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentMetadata } from '@core/features/agents/api/browser/use-agent-metadata';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { ChatTranscript } from '@core/features/conversations/api/browser/chat/chat-transcript';
import type {
  ChatCommands,
  ChatView,
} from '@core/features/conversations/api/browser/chat/chat-transcript';
import {
  appendWorkbenchChatReference,
  imageBytesFromDataUrl,
  subscribeWorkbenchChatInput,
} from '@core/features/conversations/api/browser/chat/workbench-chat-input-bridge';
import { prepareWorkbenchChatSubmission } from '@core/features/conversations/api/browser/chat/workbench-chat-submit-bridge';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import { usePromptLibrary } from '@core/features/library/api/browser/prompts/use-prompt-library';
import { getProjectSshConnectionId } from '@core/features/projects/api/browser/stores/project-selectors';
import { getSearchClient } from '@core/features/search/api/client';
// TODO(conversations-extraction): Pass task state into ACP chat instead of importing task stores.
import {
  asProvisioned,
  getTaskStore,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import {
  isHeicLikeFile,
  isUnstableDropPath,
} from '@core/features/terminals/api/browser/pty/terminal-image-paths';
import { openModal } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { log } from '@core/primitives/logging/browser/logger';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import { acpBootstrapStatusLabel } from './acp-bootstrap-status';
import type { AcpChatStore, AcpPromptAttachment } from './acp-chat-store';
import type { AcpChatTabResource } from './acp-chat-tab-resource';
import { chatViewCommandForShortcut, executeChatViewCommand } from './acp-chat-view-commands';
import { createTranscriptFileCommands } from './transcript-file-commands';

// ── Helpers ───────────────────────────────────────────────────────────────────

const attachmentDataUrlCache = new Map<string, Promise<string | null>>();
const SLASH_COMMANDS_SECTION = 'Commands';
const SLASH_PROMPTS_SECTION = 'Prompts';

function promptPreview(text: string): string {
  return text.split(/\r?\n/, 1)[0] ?? '';
}

function commandMatchesQuery(command: CommandItem, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return [command.name, command.label, command.description]
    .filter((value): value is string => !!value)
    .some((value) => value.toLowerCase().includes(normalized));
}

function useAnimatedInteger(target: number): number {
  const [displayed, setDisplayed] = useState(0);
  const current = useRef(0);

  useEffect(() => {
    const from = current.current;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (from === target || reduceMotion) {
      current.current = target;
      setDisplayed(target);
      return;
    }

    const startedAt = performance.now();
    const durationMs = 180;
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / durationMs);
      const eased = 1 - (1 - progress) ** 3;
      const next = Math.round(from + (target - from) * eased);
      current.current = next;
      setDisplayed(next);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  return displayed;
}

const ActiveAgentStatus = observer(function ActiveAgentStatus({
  store,
  providerName,
}: {
  store: AcpChatStore;
  providerName: string | null;
}) {
  const [startedAt] = useState(() => Date.now());
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const progress = store.agentProgress;
  const modelLabel = store.modelLabel ?? `${providerName ?? 'Agent'} default model`;
  const animatedThinkingTokens = useAnimatedInteger(progress.thinkingTokens);
  const tokenLabel =
    animatedThinkingTokens > 0
      ? ` · ~${animatedThinkingTokens.toLocaleString()} thinking tokens`
      : '';

  return (
    <div
      className="mx-3 mb-1 flex min-w-0 items-center gap-2 overflow-hidden rounded-md border bg-background/95 px-2.5 py-1.5 text-xs text-foreground-muted"
      title="Thinking-token counts are estimated from reasoning text streamed by the provider."
    >
      <span className="sr-only" role="status" aria-live="polite">
        {modelLabel}: {progress.phase}
      </span>
      <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-foreground" aria-hidden />
      <span className="min-w-0 truncate tabular-nums">
        <span className="font-medium text-foreground">{modelLabel}</span> · {progress.phase}
        {tokenLabel} · {elapsedSeconds}s
      </span>
    </div>
  );
});

const BACKGROUND_AGENT_STATUS: Record<'running' | 'completed' | 'failed', string> = {
  running: 'running',
  completed: 'done',
  failed: 'failed',
};

/**
 * Background subagents outlive the turn that launched them, so they get a
 * strip of their own: every agent the runtime tracks, its state, and what it
 * reported back, whether or not the foreground agent is still working.
 */
const BackgroundAgentsStatus = observer(function BackgroundAgentsStatus({
  store,
}: {
  store: AcpChatStore;
}) {
  const agents = store.backgroundAgents;
  if (agents.length === 0) return null;
  const running = agents.filter((agent) => agent.status === 'running').length;
  const heading =
    running > 0
      ? `${running} background agent${running === 1 ? '' : 's'} running`
      : `${agents.length} background agent${agents.length === 1 ? '' : 's'} finished`;
  return (
    <div
      className="mx-3 mb-1 flex min-w-0 flex-col gap-0.5 overflow-hidden rounded-md border bg-background/95 px-2.5 py-1.5 text-xs text-foreground-muted"
      role="status"
      aria-live="polite"
    >
      <span className="font-medium text-foreground">{heading}</span>
      {agents.slice(-4).map((agent) => (
        <span
          key={agent.agentId}
          className="min-w-0 truncate"
          title={[agent.summary, agent.outputFile].filter(Boolean).join('\n') || undefined}
        >
          {agent.name} · {BACKGROUND_AGENT_STATUS[agent.status]}
          {agent.summary ? ` · ${agent.summary}` : ''}
        </span>
      ))}
    </div>
  );
});

/** Map an AcpPermissionRequest to the ComposerPermissionRequest shape the UI expects. */
function toComposerPermission(
  req: AcpChatStore['permissionQueue'][number] | undefined
): ComposerPermissionRequest | null {
  if (!req) return null;
  return {
    requestId: req.requestId,
    kind: req.kind,
    title: req.title,
    ...(req.body !== undefined ? { body: req.body } : {}),
    options: req.options.map((o) => ({
      optionId: o.optionId,
      name: o.name,
      kind: o.kind,
      ...(o.description !== undefined ? { description: o.description } : {}),
    })),
  };
}

const SessionEndedStatus = observer(function SessionEndedStatus({
  store,
}: {
  store: AcpChatStore;
}) {
  if (!store.sessionEnded) return null;
  return (
    <div
      className="mx-3 mb-1 rounded-md border bg-background/95 px-2.5 py-1.5 text-xs text-foreground-muted"
      role="status"
      aria-live="polite"
    >
      The agent session ended. Your history is kept; sending a message reconnects it.
    </div>
  );
});

const RateLimitStatus = observer(function RateLimitStatus({ store }: { store: AcpChatStore }) {
  const notice = store.rateLimitNotice;
  if (!notice) return null;
  return (
    <div
      className="mx-3 mb-1 rounded-md border border-border-warning bg-background-warning px-2.5 py-1.5 text-xs text-foreground-warning"
      role="status"
      aria-live="polite"
    >
      {notice}
    </div>
  );
});

const supportedAttachmentMimeTypes = new Set<AttachmentMimeType>([
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
]);
const attachmentMimeTypeByExtension: Record<string, AttachmentMimeType> = {
  gif: 'image/gif',
  jpeg: 'image/jpeg',
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
};

function toAttachmentMimeTypeValue(value: string): AttachmentMimeType | null {
  const mimeType = value.toLowerCase();
  return supportedAttachmentMimeTypes.has(mimeType as AttachmentMimeType)
    ? (mimeType as AttachmentMimeType)
    : null;
}

function toAttachmentMimeType(file: File): AttachmentMimeType | null {
  const declaredMimeType = toAttachmentMimeTypeValue(file.type);
  if (declaredMimeType) return declaredMimeType;
  const extension = file.name.split('.').pop()?.toLowerCase();
  return extension ? (attachmentMimeTypeByExtension[extension] ?? null) : null;
}

function readFileAsDataUrl(file: File): Promise<string | undefined> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : undefined);
    reader.onerror = () => resolve(undefined);
    reader.readAsDataURL(file);
  });
}

async function uploadImageFile(
  store: AcpChatStore,
  file: File
): Promise<ComposerAttachment | null> {
  const mimeType = toAttachmentMimeType(file);
  if (!mimeType) {
    log.warn('Dropped image type is not supported for ACP attachments', {
      name: file.name,
      type: file.type,
    });
    return null;
  }

  const originalPath = window.electronAPI.getPathForFile(file).trim();
  const canReference =
    originalPath.length > 0 && !isUnstableDropPath(originalPath) && !isHeicLikeFile(file);
  const previewUrl = await readFileAsDataUrl(file);
  let ref: AttachmentRef | null;
  try {
    ref = canReference
      ? await store.uploadAttachment({ originalPath, mimeType, name: file.name })
      : await store.uploadAttachment({
          source: file.stream(),
          size: file.size,
          mimeType,
          name: file.name,
        });
  } catch (error) {
    log.warn('Failed to prepare ACP attachment upload', { name: file.name, error });
    return null;
  }

  if (!ref) return null;
  return {
    id: ref.id,
    name: ref.name,
    kind: 'image',
    previewUrl,
    mimeType: ref.mimeType,
  };
}

function resolveAttachmentDataUrl(store: AcpChatStore, id: string): Promise<string | null> {
  if (!store.session) return Promise.resolve(null);
  const cached = attachmentDataUrlCache.get(id);
  if (cached) return cached;
  const promise = store.session
    .downloadAttachment(id)
    .then((result) => {
      if (!result.success) return null;
      return `data:${result.data.ref.mimeType};base64,${bytesToBase64(result.data.data)}`;
    })
    .catch((error: unknown) => {
      log.warn('Failed to resolve ACP attachment', { id, error });
      return null;
    });
  attachmentDataUrlCache.set(id, promise);
  return promise;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

// ── Composer for a single store ────────────────────────────────────────────────
//
// Keyed by conversationId in the parent so that drafts, focus, and editor state
// reset when switching conversations — the same isolation the old remount gave.

const ComposerForStore = observer(function ComposerForStore({
  store,
  composerSlot,
  onViewerOpen,
}: {
  store: AcpChatStore;
  composerSlot: HTMLElement;
  onViewerOpen: (src?: string, alt?: string) => void;
}) {
  const editorApiRef = useRef<PromptEditorRef | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const preparingSubmissionRef = useRef(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [preparingSubmission, setPreparingSubmission] = useState(false);
  const { value: promptLibrary } = usePromptLibrary();
  const disabledReason = projectAvailabilityUi.getLiveActionDisabledReason(store.projectId);

  // Autofocus when the slot becomes available.
  useEffect(() => {
    editorApiRef.current?.focus();
  }, []);

  useEffect(() => {
    const editor = editorApiRef.current;
    if (!editor || editor.getText() === store.draftText) return;
    editor.setText(store.draftText);
  }, [store, store.draftText]);

  const buildPromptAttachments = useCallback(
    (): AcpPromptAttachment[] =>
      attachments
        .filter((att) => att.kind === 'image' && toAttachmentMimeTypeValue(att.mimeType ?? ''))
        .map((att) => {
          const mimeType = toAttachmentMimeTypeValue(att.mimeType ?? '') ?? 'image/png';
          return {
            ref: {
              type: 'attachment' as const,
              id: att.id,
              mimeType,
              name: att.name,
            },
            previewUrl: att.previewUrl,
          };
        }),
    [attachments]
  );

  const handleSubmit = useCallback(
    (value: string) => {
      const promptAttachments = buildPromptAttachments();
      if ((!value.trim() && promptAttachments.length === 0) || preparingSubmissionRef.current) {
        return;
      }
      preparingSubmissionRef.current = true;
      setPreparingSubmission(true);
      void (async () => {
        const preparation = await prepareWorkbenchChatSubmission(
          { projectId: store.projectId, taskId: store.taskId },
          {
            conversationId: store.conversationId,
            text: value,
            messageCountBeforeSubmit: store.messageCount,
            agentIsWorking: store.affordances.isWorking,
          }
        );
        if (!preparation.success) {
          // The editor clears itself on submit; hand the text back so nothing is lost.
          editorApiRef.current?.setText(value);
          toast.error('Could not start this change', { description: preparation.error });
          return;
        }

        const dispatch = await store.dispatchPrompt(
          value,
          promptAttachments,
          preparation.hiddenContext
        );
        if (!dispatch.success) {
          let rollbackError: string | undefined;
          if (preparation.onDispatchFailure) {
            try {
              const rollback = await preparation.onDispatchFailure(dispatch.error);
              if (!rollback.success) rollbackError = rollback.error;
            } catch (error) {
              rollbackError = error instanceof Error ? error.message : String(error);
            }
          }
          editorApiRef.current?.setText(value);
          toast.error('Could not send this request', {
            description: rollbackError ? `${dispatch.error} ${rollbackError}` : dispatch.error,
          });
          return;
        }

        setAttachments([]);
        editorApiRef.current?.clear();
      })()
        .catch((error: unknown) => {
          editorApiRef.current?.setText(value);
          toast.error('Could not prepare this request', {
            description: error instanceof Error ? error.message : String(error),
          });
        })
        .finally(() => {
          preparingSubmissionRef.current = false;
          setPreparingSubmission(false);
        });
    },
    [store, buildPromptAttachments]
  );

  const handleStop = useCallback(() => {
    store.stop();
  }, [store]);

  const handleResolvePermission = useCallback(
    (optionId: string | null) => {
      if (!optionId) return;
      store.resolvePermission(optionId);
    },
    [store]
  );

  const handleSendQueuedPromptNow = useCallback(
    (id: string) => {
      if (!store.affordances.isWorking) {
        store.sendQueuedPromptNow(id);
        return;
      }
      void openModal('confirmActionModal', {
        title: 'Turn in progress',
        description: 'Send this queued prompt now and cancel the active turn?',
        confirmLabel: 'Cancel & Send',
        variant: 'destructive',
      }).then((outcome) => {
        if (outcome.success) {
          store.sendQueuedPromptNow(id);
        }
      });
    },
    [store]
  );

  const handleModelChange = useCallback(
    (modelId: string) => {
      store.setModel(modelId);
    },
    [store]
  );

  const handleModeChange = useCallback(
    (modeId: string) => {
      store.setMode(modeId);
    },
    [store]
  );

  const handleEffortChange = useCallback(
    (effortId: string) => {
      store.setEffort(effortId);
    },
    [store]
  );

  const handleAttach = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const insertFileMentions = useCallback((files: File[]) => {
    for (const file of files) {
      if (file.type.startsWith('image/')) continue;
      const abs = window.electronAPI.getPathForFile(file).trim().replace(/\\/g, '/');
      if (!abs) continue;
      const name = abs.split('/').pop() ?? abs;
      editorApiRef.current?.insertMention({ id: abs, label: abs, name, kind: 'file' });
    }
  }, []);

  const addImageFiles = useCallback(
    async (files: File[]) => {
      const supportedFiles = files.filter((file) => toAttachmentMimeType(file) !== null);
      if (supportedFiles.length < files.length) {
        const unsupportedNames = files
          .filter((file) => toAttachmentMimeType(file) === null)
          .map((file) => file.name || 'unnamed image')
          .join(', ');
        toast.error('Unsupported image format', {
          description: `${unsupportedNames} could not be attached. Use PNG, JPEG, GIF, or WebP.`,
        });
      }

      const next = await Promise.all(supportedFiles.map((file) => uploadImageFile(store, file)));
      const uploaded = next.filter((att): att is ComposerAttachment => att !== null);
      if (uploaded.length > 0) {
        setAttachments((prev) => [...prev, ...uploaded]);
      }
    },
    [store]
  );

  useEffect(
    () =>
      subscribeWorkbenchChatInput(
        { projectId: store.projectId, taskId: store.taskId },
        async (input) => {
          if (input.kind === 'reference') {
            const nextDraft = appendWorkbenchChatReference(
              editorApiRef.current?.getText() ?? store.draftText,
              input.reference
            );
            if (nextDraft !== (editorApiRef.current?.getText() ?? store.draftText)) {
              store.setDraftText(nextDraft);
              editorApiRef.current?.setText(nextDraft);
            }
            editorApiRef.current?.focus();
            return true;
          }

          const data = imageBytesFromDataUrl(input.dataUrl, input.mimeType);
          if (!data) {
            toast.error('Could not add screenshot to chat', {
              description: 'The CAD screenshot data was invalid.',
            });
            return false;
          }
          const ref = await store.uploadAttachment({
            data,
            mimeType: input.mimeType,
            name: input.name,
          });
          if (!ref) return false;
          setAttachments((current) => [
            ...current,
            {
              id: ref.id,
              name: ref.name,
              kind: 'image',
              previewUrl: input.dataUrl,
              mimeType: ref.mimeType,
            },
          ]);
          editorApiRef.current?.focus();
          return true;
        }
      ),
    [store]
  );

  const handleAttachmentsChange = useCallback(
    (next: ComposerAttachment[]) => {
      const nextIds = new Set(next.map((attachment) => attachment.id));
      for (const attachment of attachments) {
        if (attachment.kind === 'image' && !nextIds.has(attachment.id)) {
          void store.deleteAttachment(attachment.id);
        }
      }
      setAttachments(next);
    },
    [attachments, store]
  );

  const handleFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      e.target.value = '';
      if (files.length === 0) return;

      const images = files.filter((f) => f.type.startsWith('image/'));
      if (images.length > 0) {
        await addImageFiles(images);
      }

      insertFileMentions(files);
    },
    [addImageFiles, insertFileMentions]
  );

  const workspaceId = useObserver(
    () => asProvisioned(getTaskStore(store.projectId, store.taskId))?.workspaceId
  );
  const mentionProvider = useMemo<ContextMentionProvider | undefined>(() => {
    if (!workspaceId) return undefined;
    return {
      async search(query: string): Promise<MentionItem[]> {
        const files = await (await getSearchClient()).searchWorkspaceFiles({ workspaceId, query });
        return files.map((file) => ({
          id: file.path,
          label: file.path,
          name: file.filename,
          kind: 'file',
          description: file.path,
        }));
      },
    };
  }, [workspaceId]);

  // Display-only (the selector is locked): static registry metadata, no host needed.
  const { data: agents } = useAgentMetadata();
  const agentOptions = useMemo<ComposerAgentOption[]>(
    () =>
      (agents ?? []).map((a) => ({
        id: a.id,
        name: a.name,
        icon: <AgentIcon id={a.id} size={14} className="rounded-sm" />,
      })),
    [agents]
  );

  const providerId =
    conversationRegistry.get(store.taskId)?.conversations.get(store.conversationId)?.data
      .providerId ?? null;
  const providerName = agentOptions.find((option) => option.id === providerId)?.name ?? null;
  const querySlashItems = useCallback(
    async (query: string): Promise<CommandItem[]> => {
      const normalized = query.trim().toLowerCase();
      const commands = store.commands
        .filter((command) => commandMatchesQuery(command, normalized))
        .map((command) => ({
          ...command,
          section: SLASH_COMMANDS_SECTION,
        }));
      const prompts = promptLibrary
        .filter((prompt) => {
          if (!normalized) return true;
          return [prompt.title, prompt.prompt].some((value) =>
            value.toLowerCase().includes(normalized)
          );
        })
        .map((prompt) => ({
          id: `prompt:${prompt.id}`,
          name: prompt.title,
          label: prompt.title,
          description: promptPreview(prompt.prompt),
          behavior: 'insert-text' as const,
          insertText: prompt.prompt,
          section: SLASH_PROMPTS_SECTION,
        }));
      return [...commands, ...prompts];
    },
    [store, promptLibrary]
  );

  const a = store.affordances;
  const permissionRequest = toComposerPermission(store.permissionQueue[0]);

  return createPortal(
    <>
      <input ref={fileInputRef} type="file" multiple hidden onChange={handleFileInputChange} />
      <RateLimitStatus store={store} />
      <SessionEndedStatus store={store} />
      <BackgroundAgentsStatus store={store} />
      {a.isWorking && <ActiveAgentStatus store={store} providerName={providerName} />}
      {disabledReason && (
        <div
          className="mx-3 mb-1 rounded-md border bg-background/95 px-2 py-1 text-center text-xs text-foreground-muted"
          tabIndex={0}
          role="note"
        >
          {disabledReason}
        </div>
      )}
      <div inert={disabledReason ? true : undefined}>
        <ChatComposer
          isWorking={a.isWorking}
          canSubmit={a.canSubmit && !preparingSubmission}
          onSubmit={handleSubmit}
          onInputChange={(text) => store.setDraftText(text)}
          onSubmitWhileWorking={handleSubmit}
          onStop={a.isWorking ? handleStop : undefined}
          permissionRequest={permissionRequest}
          permissionQueueCount={store.permissionQueue.length}
          onResolvePermission={handleResolvePermission}
          queuedPrompts={store.queuedPrompts}
          onEditQueuedPrompt={(id, text) => store.editQueuedPrompt(id, text)}
          onDeleteQueuedPrompt={(id) => store.deleteQueuedPrompt(id)}
          onReorderQueuedPrompts={(ids) => store.reorderQueuedPrompts(ids)}
          onSendQueuedPromptNow={handleSendQueuedPromptNow}
          editorApiRef={editorApiRef}
          modelOptions={store.modelOptions}
          selectedModel={store.model ?? undefined}
          onModelChange={handleModelChange}
          effortOptions={store.effortOptions}
          selectedEffort={store.effort ?? undefined}
          onEffortChange={handleEffortChange}
          permissionModeOptions={store.permissionModeOptions}
          selectedPermissionMode={store.permissionMode ?? undefined}
          onPermissionModeChange={handleModeChange}
          mcpServers={store.mcpServers}
          agentOptions={agentOptions}
          selectedAgent={providerId ?? undefined}
          agentLocked
          onAgentChange={() => {}}
          contextUsage={
            store.usage
              ? {
                  used: store.usage.contextUsed,
                  size: store.usage.contextSize,
                  cost: store.usage.cost,
                }
              : null
          }
          mentionProvider={mentionProvider}
          queryCommands={querySlashItems}
          attachments={attachments}
          onAttachmentsChange={handleAttachmentsChange}
          onAttach={handleAttach}
          onImageFilesDropped={(files) => void addImageFiles(files)}
          onFilesDropped={insertFileMentions}
          onViewImage={(att) => onViewerOpen(att.previewUrl, att.name)}
        />
      </div>
    </>,
    composerSlot
  );
});

// ── AcpChatPanel ──────────────────────────────────────────────────────────────
//
// One persistent ChatTranscript is mounted for the lifetime of this panel.
// When the active conversation changes, props.state identity changes, which
// triggers ChatTranscript's setModel effect — the Solid view swaps ChatState
// in-place without dispose/recreate, preserving per-conversation scroll.
//
// The composer subtree is keyed by conversationId so draft text, focus, and
// editor state reset on each switch (equivalent to the old remount behavior).

export const AcpChatPanel = observer(function AcpChatPanel() {
  const { pane } = usePaneContext();

  const activeTab = pane.resolvedTabs.find((t) => t.isActive && t.kind === 'acp-chat');
  const store = activeTab ? (activeTab.resource as AcpChatTabResource).store : null;

  const rootRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<ChatView | null>(null);
  const [composerSlot, setComposerSlot] = useState<HTMLElement | null>(null);
  const [heroSlot, setHeroSlot] = useState<HTMLElement | null>(null);
  const [overlaySlot, setOverlaySlot] = useState<HTMLElement | null>(null);
  const [viewer, setViewer] = useState<{ src?: string; alt?: string } | null>(null);
  const [mermaidViewer, setMermaidViewer] = useState<{ svg: string | null } | null>(null);
  const placementConversationRef = useRef<string | null>(null);
  const placementWasEmptyRef = useRef<boolean | null>(null);
  // True while the scroll viewport is at the tail. Defaults to true so the
  // button does not flash on mount before the first frame fires.
  const [atBottom, setAtBottom] = useState(true);

  const handleReady = useCallback((view: ChatView) => {
    viewRef.current = view;
    setComposerSlot(view.composerSlot);
    setHeroSlot(view.heroSlot);
    setOverlaySlot(view.contentOverlay);
  }, []);

  const isConversationEmpty = useObserver(() => store?.isEmpty ?? false);
  const activeConversationId = store?.conversationId ?? null;

  useEffect(() => {
    if (!store || !viewRef.current) return;
    const sameConversation = placementConversationRef.current === store.conversationId;
    const wasEmpty = placementWasEmptyRef.current === true;
    const placement = isConversationEmpty ? 'center' : 'bottom';
    viewRef.current.setComposerPlacement(placement, {
      animate: sameConversation && wasEmpty && !isConversationEmpty,
    });
    placementConversationRef.current = store.conversationId;
    placementWasEmptyRef.current = isConversationEmpty;
  }, [store, activeConversationId, isConversationEmpty, composerSlot]);

  // Bind/unbind the view handle to the active store so the store can call
  // scrollToItem on submit. Only the active store holds the handle.
  useEffect(() => {
    if (!store) return;
    store.bindView(viewRef.current);
    return () => {
      store.bindView(null);
    };
  }, [store]);

  // State-driven notification clearing: mark the active conversation as seen
  // immediately when the panel is showing it. This covers the split-pane case
  // where the same tab stays active and onActivate() does not re-fire.
  const conversationStore = useObserver(() =>
    store
      ? conversationRegistry.get(store.taskId)?.conversations.get(store.conversationId)
      : undefined
  );
  const conversationSeen = conversationStore?.seen;
  const connectionId = useObserver(() =>
    store ? getProjectSshConnectionId(store.projectId) : undefined
  );
  const host = useMemo(() => hostRefFromConnectionId(connectionId), [connectionId]);
  const { data: agents } = useAgents(host);
  const providerId = conversationStore?.data.providerId ?? null;
  const agent = agents?.find((candidate) => candidate.id === providerId) ?? null;
  const cliAuthMethod =
    agent?.capabilities.auth.kind === 'supported'
      ? agent.capabilities.auth.methods.find((method) => method.kind === 'cli-login')
      : undefined;

  const openSignInModal = useCallback(() => {
    if (!providerId || !cliAuthMethod || !store) return;
    void openModal('agentSignInModal', {
      providerId,
      methodId: cliAuthMethod.id,
      providerName: agent?.name ?? providerId,
      host,
    }).then((outcome) => {
      if (outcome.success) {
        if (store.loadError?.kind === 'auth_required') store.retry();
      }
    });
  }, [agent?.name, cliAuthMethod, host, providerId, store]);

  useEffect(() => {
    if (conversationStore && !conversationStore.seen) {
      conversationStore.markSeen();
    }
  }, [conversationStore, conversationSeen]);

  useEffect(() => {
    if (!store) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const root = rootRef.current;
      if (!root || !eventComposedPathContains(event, root)) return;

      const commandId = chatViewCommandForShortcut(event);
      if (!commandId) return;
      if (!executeChatViewCommand(viewRef.current, commandId)) return;

      event.preventDefault();
      event.stopPropagation();
    };

    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => {
      window.removeEventListener('keydown', handleKeyDown, { capture: true });
    };
  }, [store]);

  const handleViewerOpen = useCallback((src?: string, alt?: string) => {
    setViewer({ src, alt });
  }, []);

  const transcriptCommands = useMemo<ChatCommands>(() => {
    const fileCommands = store
      ? createTranscriptFileCommands({ projectId: store.projectId, taskId: store.taskId })
      : null;
    return {
      onViewImage: (arg) => {
        if (arg.attachment.dataUrl || !store) {
          handleViewerOpen(arg.attachment.dataUrl, arg.attachment.name);
          return;
        }
        void resolveAttachmentDataUrl(store, arg.attachment.id).then((src) =>
          handleViewerOpen(src ?? undefined, arg.attachment.name)
        );
      },
      resolveAttachment: (attachment) =>
        store ? resolveAttachmentDataUrl(store, attachment.id) : Promise.resolve(null),
      onViewMermaid: (arg) => {
        setMermaidViewer({
          svg: store?.chatContext.sharedCaches.renderMermaid(arg.chart) ?? null,
        });
      },
      classifyLink: fileCommands?.classifyLink,
      onOpenFile: fileCommands?.onOpenFile,
      onClickMention: (arg: Parameters<NonNullable<ChatCommands['onClickMention']>>[0]) => {
        if (!store) return;
        if (arg.kind === 'file') {
          fileCommands?.openMentionFile(arg.id);
          return;
        }
      },
    };
  }, [store, handleViewerOpen]);

  if (!store) return null;

  const unavailableWithoutTranscript =
    store.loadError?.kind === 'unavailable' && store.messageCount === 0;
  const showBlockingOverlay =
    store.historyLoading ||
    (store.loadError !== null && store.loadError.kind !== 'unavailable') ||
    unavailableWithoutTranscript;
  const showComposer =
    !store.historyLoading && (store.loadError === null || store.loadError.kind === 'unavailable');
  const showHero = showComposer && store.isEmpty && store.loadError === null;

  return (
    <div ref={rootRef} className="surface-paper relative h-full overflow-hidden bg-(--em-surface)">
      <ChatTranscript
        context={store.chatContext}
        state={store.chatState}
        composer="slot"
        composerPlacement={store.isEmpty ? 'center' : 'bottom'}
        contentOverlay
        stickToBottom
        pinUserMessages
        onReady={handleReady}
        commands={transcriptCommands}
        onAtBottomChange={setAtBottom}
        style={{ position: 'absolute', inset: 0 }}
      />

      {/* Loading / error overlay portaled into the library-owned slot.
          The slot sits at z-index 15 (above pinned, below composer at 20).
          Hide the composer in error state so the overlay owns the whole content area.
          Precedence: error > loading. */}
      {overlaySlot &&
        showBlockingOverlay &&
        createPortal(
          <div
            // The library-owned overlay slot is pointer-events: none by design;
            // opt back in so the Sign in / Retry buttons are clickable.
            className={`pointer-events-auto absolute inset-0 flex items-center justify-center text-sm text-foreground-muted ${
              showBlockingOverlay ? 'bg-(--em-surface)' : ''
            }`}
            aria-live="polite"
          >
            {store.loadError?.kind === 'unavailable' ? (
              <div className="flex max-w-md flex-col items-center gap-2 px-6 text-center">
                <span className="text-foreground">Chat unavailable</span>
                <span className="text-xs text-foreground-muted">{store.loadError.message}</span>
              </div>
            ) : store.loadError !== null ? (
              store.loadError.kind === 'auth_required' ? (
                <div className="flex max-w-md flex-col items-center gap-2 px-6 text-center">
                  <span className="text-foreground">
                    {agent?.name ?? 'This agent'} needs you to sign in.
                  </span>
                  <span className="text-xs text-foreground-muted">
                    {cliAuthMethod?.description ?? store.loadError.message}
                  </span>
                  <div className="mt-1 flex gap-2">
                    {cliAuthMethod && (
                      <Button variant="primary" size="sm" onClick={openSignInModal}>
                        Sign in
                      </Button>
                    )}
                    <Button variant="secondary" size="sm" onClick={() => store.retry()}>
                      Retry
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex max-w-md flex-col items-center gap-2 px-6 text-center">
                  <span className="text-foreground">Failed to load chat.</span>
                  <span className="text-xs text-foreground-muted">{store.loadError.message}</span>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-1"
                    onClick={() => store.retry()}
                  >
                    Retry
                  </Button>
                </div>
              )
            ) : (
              <div className="flex items-center gap-2" role="status">
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
                <span>{acpBootstrapStatusLabel(store.bootstrapPhase)}</span>
              </div>
            )}
          </div>,
          overlaySlot
        )}

      {showHero &&
        heroSlot &&
        createPortal(
          <div className="px-4 text-center">
            <h1 className="text-2xl tracking-tight text-foreground">What are we building today?</h1>
          </div>,
          heroSlot
        )}

      {showComposer && composerSlot && (
        <ComposerForStore
          key={store.conversationId}
          store={store}
          composerSlot={composerSlot}
          onViewerOpen={handleViewerOpen}
        />
      )}

      {showComposer &&
        composerSlot &&
        !atBottom &&
        createPortal(
          <div className="pointer-events-none absolute inset-x-0 bottom-full mb-2 flex justify-center">
            <Button
              variant="secondary"
              icon
              aria-label="Scroll to bottom"
              onClick={() => viewRef.current?.scrollToBottom({ behavior: 'smooth' })}
              className="pointer-events-auto shadow-md"
            >
              <ArrowDown />
            </Button>
          </div>,
          composerSlot
        )}

      <ImageViewerDialog
        open={!!viewer}
        onOpenChange={(open) => {
          if (!open) setViewer(null);
        }}
        src={viewer?.src}
        alt={viewer?.alt}
      />
      <MermaidViewerDialog
        open={!!mermaidViewer}
        onOpenChange={(open) => {
          if (!open) setMermaidViewer(null);
        }}
        svg={mermaidViewer?.svg ?? null}
      />
    </div>
  );
});

function eventComposedPathContains(event: Event, element: HTMLElement): boolean {
  if (event.composedPath().includes(element)) return true;
  return event.target instanceof Node && element.contains(event.target);
}
