import { Button } from '@react/primitives/button';
import { cx } from '@styles/utilities/cx';
import { ArrowUp, ChevronRight, CircleAlert, Paperclip, Plug, ShieldCheck, X } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { Combobox } from '@/react/primitives/combobox/combobox';
import { DropdownMenu } from '@/react/primitives/dropdown-menu';
import { Popover } from '@/react/primitives/popover';
import { Select } from '@/react/primitives/select';
import { ComboboxPopover } from '../combobox-popover';
import { PromptEditor } from '../prompt-editor/prompt-editor';
import type {
  CommandItem,
  ContextMentionProvider,
  MentionItem,
  PromptEditorRef,
  RenderMentionIcon,
} from '../prompt-editor/types';
import { ContextUsageIndicator } from './context-usage-indicator';
import type { ContextUsage } from './context-usage-indicator';
import { PermissionBand } from './permission-band';
import type { ComposerPermissionRequest } from './permission-band';
import { QueuedPromptsBand } from './queued-prompts-band';
import type { ComposerQueuedPrompt } from './queued-prompts-band';
import * as styles from './chat-composer.css';
import { composerThemeScope } from './composer-contract.css';

export type { MentionItem, CommandItem };
export type {
  MentionKind,
  CommandBehavior,
  ContextMentionProvider,
  PromptEditorRef,
  RenderMentionIcon,
} from '../prompt-editor/types';
export type { ContextUsage } from './context-usage-indicator';
export type { ComposerQueuedPrompt } from './queued-prompts-band';

export type ComposerNoticeVariant = 'error' | 'warning' | 'info';

export interface ComposerNotice {
  variant: ComposerNoticeVariant;
  title?: string;
  message: string;
  /** When provided, renders a dismiss button. */
  onDismiss?: () => void;
}

/**
 * Map an ACP stop reason to a composer notice. Returns null for reasons that
 * are not user-facing errors (end_turn, cancelled, unknown). Accepts a plain
 * string so callers can forward the ACP StopReason without this package
 * importing the ACP SDK.
 */
export function stopReasonNotice(reason: string): ComposerNotice | null {
  switch (reason) {
    case 'max_turn_requests':
      return {
        variant: 'error',
        title: 'Turn limit reached',
        message:
          'The agent hit the maximum number of turn requests. Send a new message to continue.',
      };
    case 'max_tokens':
      return {
        variant: 'error',
        title: 'Response truncated',
        message: 'The response was cut off after reaching the maximum token limit.',
      };
    case 'refusal':
      return {
        variant: 'error',
        title: 'Request refused',
        message: 'The agent declined to continue with this request.',
      };
    default:
      return null;
  }
}

// ── Attachment types ──────────────────────────────────────────────────────────

const imageFileExtension = /\.(?:avif|bmp|gif|heic|heif|jpe?g|png|svg|tiff?|webp)$/i;

export interface ComposerAttachment {
  id: string;
  name: string;
  /** Absolute or relative path — populated by the host for file-kind attachments. */
  path?: string;
  kind: 'image' | 'file';
  /**
   * Image source for the preview `<img>`. A `data:` URL for dropped images
   * (so the bytes can be forwarded to the agent); needs no `revokeObjectURL`.
   */
  previewUrl?: string;
  /** MIME type of the image (e.g. `image/png`) — used when sending to the agent. */
  mimeType?: string;
}

/**
 * Read a dropped image file into a `ComposerAttachment` with a `data:` URL
 * preview. On read failure the attachment is still created (without
 * `previewUrl`) so the host shows a fallback tile rather than dropping it.
 */
function readImageAttachment(file: File): Promise<ComposerAttachment> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve({
        id: crypto.randomUUID(),
        name: file.name,
        kind: 'image',
        previewUrl: typeof reader.result === 'string' ? reader.result : undefined,
        mimeType: file.type,
      });
    reader.onerror = () =>
      resolve({ id: crypto.randomUUID(), name: file.name, kind: 'image', mimeType: file.type });
    reader.readAsDataURL(file);
  });
}

// ── Model option types ────────────────────────────────────────────────────────

/** Minimal model descriptor the composer needs to render the model selector. */
export interface ComposerModelOption {
  name: string;
  description?: string;
  /** Optional capability metadata shown in the hover card detail. */
  modelFeatures?: {
    contextWindowSize?: number;
    speed?: number;
    intelligence?: number;
  };
}

// ── Effort option types ───────────────────────────────────────────────────────

/** Minimal effort/thought-level descriptor the composer needs to render the effort submenu. */
export interface ComposerEffortOption {
  name: string;
  description?: string;
}

// ── Permission mode option types ──────────────────────────────────────────────

/** Minimal mode descriptor the composer needs to render the permission-mode selector. */
export interface ComposerPermissionModeOption {
  name: string;
  description?: string;
}

export interface ComposerMcpServer {
  name: string;
  transport: string;
}

// ── Agent option types ────────────────────────────────────────────────────────

/** Minimal agent descriptor the composer needs to render the agent selector. */
export interface ComposerAgentOption {
  id: string;
  name: string;
  /**
   * Host-rendered icon — the app's AgentIcon is theme/registry aware, which
   * this package can't reach. Shown in the trigger and each list row.
   */
  icon?: React.ReactNode;
  description?: string;
  /** e.g. not installed — shown but not selectable. */
  disabled?: boolean;
  /** Optional grouping header, e.g. "Installed" / "Not installed". */
  groupLabel?: string;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ChatComposerProps {
  disabled?: boolean;
  isWorking?: boolean;
  /** False while the session is still starting up. Blocks Send/Enter but keeps the editor typeable. */
  canSubmit?: boolean;
  /** Hide the submit/stop control for draft-only composer surfaces. */
  showSubmitButton?: boolean;
  /** Override the idle editor placeholder. Disabled/working placeholders still take precedence. */
  placeholder?: string;

  agentOptions?: ComposerAgentOption[] | null;
  selectedAgent?: string;
  onAgentChange?: (agentId: string) => void;
  /**
   * True once the session has history (any prompt sent). ACP cannot switch
   * agents mid-conversation, so the trigger becomes a disabled icon button.
   */
  agentLocked?: boolean;

  modelOptions?: Record<string, ComposerModelOption> | null;
  selectedModel?: string;
  onModelChange?: (modelId: string) => void;

  effortOptions?: Record<string, ComposerEffortOption> | null;
  selectedEffort?: string;
  onEffortChange?: (effortId: string) => void;

  permissionModeOptions?: Record<string, ComposerPermissionModeOption> | null;
  selectedPermissionMode?: string;
  onPermissionModeChange?: (modeId: string) => void;
  mcpServers?: ComposerMcpServer[];

  onSubmit: (text: string) => void;
  /** Called whenever the editor serialized plain text changes. */
  onInputChange?: (text: string) => void;
  /** Called after a mention node is inserted. Raw insertText entries do not trigger this. */
  onMentionInsert?: (item: MentionItem) => void;
  /**
   * Called instead of onSubmit when the user attempts to send while the
   * session is actively working (isWorking === true). Lets the host queue,
   * confirm interruption, or otherwise resolve the conflict.
   * When absent, submit attempts while working are silently ignored.
   */
  onSubmitWhileWorking?: (text: string) => void;
  onStop?: () => void;
  onAttach?: () => void;
  /** Context-window usage data for the toolbar donut indicator. Hidden when null/undefined. */
  contextUsage?: ContextUsage | null;

  /**
   * Host-controlled attachment list. By default the composer creates image
   * attachments itself from drag-drop and forwards them via `onAttachmentsChange`.
   * Hosts can override image handling with `onImageFilesDropped`.
   */
  attachments?: ComposerAttachment[];
  onAttachmentsChange?: (next: ComposerAttachment[]) => void;
  /**
   * Called with pasted or dropped image files before the default data-url attachment path.
   * When supplied, the host owns uploading and adding preview attachments.
   */
  onImageFilesDropped?: (files: File[]) => void;
  /**
   * Called whenever files are dropped onto the composer.
   * The host should resolve real filesystem paths and insert non-image files
   * as path mentions via the `editorApiRef` (using `insertMention`).
   */
  onFilesDropped?: (files: File[]) => void;

  /**
   * Optional ref forwarded to the inner PromptEditor imperative API, giving
   * the host access to `insertMention` (and focus/clear/getText).
   */
  editorApiRef?: React.Ref<PromptEditorRef>;

  /**
   * Called when the user clicks an image attachment thumbnail in the preview
   * strip above the editor. Host can use this to open an image viewer dialog.
   */
  onViewImage?: (att: ComposerAttachment) => void;

  /**
   * Preferred: typed provider for @ mention suggestions.
   * When both `mentionProvider` and `queryMentions` are provided,
   * `mentionProvider` takes precedence.
   */
  mentionProvider?: ContextMentionProvider;
  /** Optional host renderer for inline mention pill icons. */
  renderMentionIcon?: RenderMentionIcon;
  /** Legacy: async callback returning @ mention suggestions for the given query. */
  queryMentions?: (query: string) => Promise<MentionItem[]>;
  /** Async callback returning / command suggestions for the given query. */
  queryCommands?: (query: string) => Promise<CommandItem[]>;
  /** Called when a / command with behavior='execute' is selected. */
  onCommand?: (item: CommandItem) => void;
  /** Session-state notice shown flush above the input (e.g. ACP stop reasons). */
  notice?: ComposerNotice | null;
  /**
   * Pending ACP permission request to show in the band above the input.
   * When present, the notice band is replaced by the permission band.
   * Pass null/undefined when no request is pending.
   */
  permissionRequest?: ComposerPermissionRequest | null;
  /** Total number of queued permission requests. Drives the "1 of N" counter. */
  permissionQueueCount?: number;
  /** Called with the chosen optionId when the user resolves a permission request. */
  onResolvePermission?: (optionId: string) => void;

  /** Prompts accepted while the agent is busy and waiting to be sent. */
  queuedPrompts?: ComposerQueuedPrompt[];
  onEditQueuedPrompt?: (id: string, text: string) => void;
  onDeleteQueuedPrompt?: (id: string) => void;
  onReorderQueuedPrompts?: (ids: string[]) => void;
  onSendQueuedPromptNow?: (id: string) => void;
  className?: string;
}

// ── Internal model item type ──────────────────────────────────────────────────

interface ModelItem {
  id: string;
  name: string;
  description?: string;
  modelFeatures?: ComposerModelOption['modelFeatures'];
}

// ── Model detail hover card ───────────────────────────────────────────────────

function ModelDetailCard({ item }: { item: ModelItem }) {
  const { name, description, modelFeatures } = item;
  const hasFeatures =
    modelFeatures &&
    (modelFeatures.contextWindowSize !== undefined ||
      modelFeatures.speed !== undefined ||
      modelFeatures.intelligence !== undefined);

  return (
    <div className={styles.modelDetailCard}>
      <p className={styles.modelDetailName}>{name}</p>
      {description && <p className={styles.modelDetailDesc}>{description}</p>}
      {hasFeatures && (
        <div className={styles.modelDetailFeatures}>
          {modelFeatures?.contextWindowSize !== undefined && (
            <ModelFeatureRow
              label="Context"
              value={formatContextWindow(modelFeatures.contextWindowSize)}
            />
          )}
          {modelFeatures?.speed !== undefined && (
            <ModelFeatureRow label="Speed" value={<BarMeter value={modelFeatures.speed} />} />
          )}
          {modelFeatures?.intelligence !== undefined && (
            <ModelFeatureRow
              label="Intelligence"
              value={<BarMeter value={modelFeatures.intelligence} />}
            />
          )}
        </div>
      )}
    </div>
  );
}

function ModelFeatureRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className={styles.modelDetailRow}>
      <span className={styles.modelDetailLabel}>{label}</span>
      <span className={styles.modelDetailValue}>{value}</span>
    </div>
  );
}

function BarMeter({ value }: { value: number }) {
  const filled = Math.round(Math.max(0, Math.min(1, value)) * 5);
  return (
    <span className={styles.barMeter}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < filled ? styles.barDotFilled : styles.barDotEmpty} />
      ))}
    </span>
  );
}

function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(0)}M tokens`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(0)}K tokens`;
  return `${tokens} tokens`;
}

// ── Notice band ───────────────────────────────────────────────────────────────

function NoticeBand({ notice }: { notice: ComposerNotice }) {
  return (
    <div className={styles.noticeBand({ variant: notice.variant })}>
      <div className={styles.noticeBandBody}>
        <div className={styles.noticeBandHeader}>
          <CircleAlert style={{ width: '0.875rem', height: '0.875rem', flexShrink: 0 }} />
          {notice.title && <p className={styles.noticeBandTitle}>{notice.title}</p>}
        </div>
        <p
          className={cx(styles.noticeBandMessage, notice.title && styles.noticeBandMessageIndented)}
        >
          {notice.message}
        </p>
      </div>
      {notice.onDismiss && (
        <button
          type="button"
          aria-label="Dismiss notice"
          onClick={notice.onDismiss}
          className={styles.noticeDismiss}
        >
          <X style={{ width: '0.875rem', height: '0.875rem' }} />
        </button>
      )}
    </div>
  );
}

// ── Agent selector ────────────────────────────────────────────────────────────

interface AgentGroup {
  label: string;
  items: ComposerAgentOption[];
}

function buildAgentGroups(options: ComposerAgentOption[]): AgentGroup[] {
  const grouped = new Map<string, ComposerAgentOption[]>();
  for (const opt of options) {
    const label = opt.groupLabel ?? '';
    const existing = grouped.get(label);
    if (existing) {
      existing.push(opt);
    } else {
      grouped.set(label, [opt]);
    }
  }
  return Array.from(grouped.entries()).map(([label, items]) => ({ label, items }));
}

interface ComposerAgentSelectorProps {
  options: ComposerAgentOption[];
  selectedId?: string;
  onSelect: (agentId: string) => void;
  locked: boolean;
  disabled: boolean;
}

function ComposerAgentSelector({
  options,
  selectedId,
  onSelect,
  locked,
  disabled,
}: ComposerAgentSelectorProps) {
  const [open, setOpen] = useState(false);
  const selected = selectedId ? (options.find((o) => o.id === selectedId) ?? null) : null;
  const groups = buildAgentGroups(options);
  const isDisabled = disabled || locked;

  const triggerLabel = selected
    ? locked
      ? `${selected.name} — agents can't be switched after a conversation starts`
      : selected.name
    : 'Select agent';

  // When locked or session closed, show a static disabled icon button.
  if (isDisabled) {
    return (
      <Button
        variant="ghost"
        size="xs"
        icon
        disabled
        aria-label={triggerLabel}
        title={triggerLabel}
      >
        {selected?.icon ?? <span style={{ width: '0.875rem', height: '0.875rem' }} />}
      </Button>
    );
  }

  return (
    <Combobox.Root
      value={selected ?? null}
      onValueChange={(item: ComposerAgentOption | null) => {
        if (!item || item.disabled) return;
        onSelect(item.id);
        setOpen(false);
      }}
      open={open}
      onOpenChange={(next) => setOpen(next)}
      isItemEqualToValue={(a: ComposerAgentOption, b: ComposerAgentOption) => a.id === b.id}
      filter={(item: ComposerAgentOption, query: string) =>
        item.name.toLowerCase().includes(query.toLowerCase())
      }
      autoHighlight
    >
      <Combobox.Trigger
        aria-label={triggerLabel}
        title={triggerLabel}
        className={styles.agentTrigger}
      >
        {selected?.icon ?? <span className={styles.agentIconPlaceholder} />}
      </Combobox.Trigger>
      {/* Portaled out of the composer root — must carry the theme-bridge scope. */}
      <Combobox.Content className={composerThemeScope} style={{ minWidth: '11.25rem' }}>
        <Combobox.Input showTrigger={false} placeholder="Search agents…" />
        <Combobox.List>
          {groups.map((group) =>
            group.label ? (
              <Combobox.Group key={group.label}>
                <Combobox.Label>{group.label}</Combobox.Label>
                {group.items.map((item) => (
                  <Combobox.Item key={item.id} value={item} disabled={item.disabled}>
                    {item.icon && <span style={{ flexShrink: 0 }}>{item.icon}</span>}
                    <span
                      style={{
                        minWidth: 0,
                        flex: '1 1 0%',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {item.name}
                    </span>
                  </Combobox.Item>
                ))}
              </Combobox.Group>
            ) : (
              group.items.map((item) => (
                <Combobox.Item key={item.id} value={item} disabled={item.disabled}>
                  {item.icon && <span style={{ flexShrink: 0 }}>{item.icon}</span>}
                  <span
                    style={{
                      minWidth: 0,
                      flex: '1 1 0%',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {item.name}
                  </span>
                </Combobox.Item>
              ))
            )
          )}
        </Combobox.List>
      </Combobox.Content>
    </Combobox.Root>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ChatComposer({
  disabled = false,
  isWorking = false,
  canSubmit = true,
  showSubmitButton = true,
  placeholder,
  agentOptions,
  selectedAgent,
  onAgentChange,
  agentLocked = false,
  modelOptions,
  selectedModel,
  onModelChange,
  effortOptions,
  selectedEffort,
  onEffortChange,
  permissionModeOptions,
  selectedPermissionMode,
  onPermissionModeChange,
  mcpServers = [],
  onSubmit,
  onInputChange,
  onMentionInsert,
  onSubmitWhileWorking,
  onStop,
  onAttach,
  contextUsage,
  attachments = [],
  onAttachmentsChange,
  onImageFilesDropped,
  onFilesDropped,
  editorApiRef,
  mentionProvider,
  renderMentionIcon,
  queryMentions,
  queryCommands,
  onCommand,
  onViewImage,
  notice,
  permissionRequest,
  permissionQueueCount = 1,
  onResolvePermission,
  queuedPrompts = [],
  onEditQueuedPrompt,
  onDeleteQueuedPrompt,
  onReorderQueuedPrompts,
  onSendQueuedPromptNow,
  className,
}: ChatComposerProps) {
  const editorRef = useRef<PromptEditorRef | null>(null);
  const [dragActive, setDragActive] = useState(false);

  // Retain the last notice so its content stays rendered while the band
  // collapses out, letting the exit transition play before unmount.
  const [retainedNotice, setRetainedNotice] = useState<ComposerNotice | null>(notice ?? null);
  useEffect(() => {
    if (notice) setRetainedNotice(notice);
  }, [notice]);

  // Revoke object URLs for image attachments on unmount to avoid leaks.
  // Track the latest attachments in a ref so the unmount cleanup revokes the
  // current set rather than a stale, mount-time snapshot.
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;
  useEffect(() => {
    return () => {
      attachmentsRef.current.forEach((att) => {
        if (att.kind === 'image' && att.previewUrl) {
          URL.revokeObjectURL(att.previewUrl);
        }
      });
    };
  }, []);

  const handleSubmit = (text: string) => {
    // Allow image-only sends: a message with attachments but no text is valid.
    const hasImages = attachments.some((a) => a.kind === 'image');
    if (!text.trim() && !hasImages) return;
    // While the agent is actively working, route to the host's conflict handler
    // (e.g. queueing or a cancel-and-send confirmation) instead of submitting.
    if (isWorking) {
      onSubmitWhileWorking?.(text);
      return;
    }
    if (disabled || !canSubmit) return;
    onSubmit(text);
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const imageFiles = Array.from(e.clipboardData.items).flatMap((item) => {
      if (item.kind !== 'file') return [];
      const file = item.getAsFile();
      if (!file) return [];
      const mimeType = (item.type || file.type).toLowerCase();
      return mimeType.startsWith('image/') || imageFileExtension.test(file.name) ? [file] : [];
    });
    if (imageFiles.length === 0) return;

    if (!e.clipboardData.types.some((type) => type.startsWith('text/'))) e.preventDefault();
    if (onImageFilesDropped) {
      onImageFilesDropped(imageFiles);
    } else if (onAttachmentsChange) {
      const base = attachments;
      void Promise.all(imageFiles.map(readImageAttachment)).then((newAttachments) => {
        onAttachmentsChange([...base, ...newAttachments]);
      });
    }
  };

  // ── Drag-and-drop ───────────────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!dragActive) setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    // Only clear when leaving the root element itself (not a child).
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
    setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    const imageFiles = files.filter((f) => f.type.startsWith('image/'));
    if (imageFiles.length > 0 && onImageFilesDropped) {
      onImageFilesDropped(imageFiles);
    } else if (imageFiles.length > 0 && onAttachmentsChange) {
      const base = attachments;
      void Promise.all(imageFiles.map(readImageAttachment)).then((newAttachments) => {
        onAttachmentsChange([...base, ...newAttachments]);
      });
    }

    onFilesDropped?.(files);
  };

  // ── Attachment removal ──────────────────────────────────────────────────────

  const removeAttachment = (id: string) => {
    const att = attachments.find((a) => a.id === id);
    if (att?.kind === 'image' && att.previewUrl) {
      URL.revokeObjectURL(att.previewUrl);
    }
    onAttachmentsChange?.(attachments.filter((a) => a.id !== id));
  };

  const imageAttachments = attachments.filter((a) => a.kind === 'image');

  // ── Model items ─────────────────────────────────────────────────────────────

  const modelItems: ModelItem[] = modelOptions
    ? Object.entries(modelOptions).map(([id, opt]) => ({ id, ...opt }))
    : [];
  const selectedAgentItem =
    selectedAgent && agentOptions
      ? (agentOptions.find((a) => a.id === selectedAgent) ?? null)
      : null;
  const selectedAgentTitle = selectedAgentItem
    ? agentLocked
      ? `${selectedAgentItem.name} — agents can't be switched after a conversation starts`
      : selectedAgentItem.name
    : undefined;

  // ── Effort items ─────────────────────────────────────────────────────────────

  interface EffortItem {
    id: string;
    name: string;
    description?: string;
  }

  const effortItems: EffortItem[] = effortOptions
    ? Object.entries(effortOptions).map(([id, opt]) => ({ id, ...opt }))
    : [];

  const selectedEffortItem = selectedEffort
    ? (effortItems.find((e) => e.id === selectedEffort) ?? null)
    : null;

  // ── Permission mode items ────────────────────────────────────────────────────

  interface PermissionModeItem {
    id: string;
    name: string;
    description?: string;
  }

  const permissionModeItems: PermissionModeItem[] = permissionModeOptions
    ? Object.entries(permissionModeOptions).map(([id, opt]) => ({ id, ...opt }))
    : [];
  const selectedPermissionModeItem = selectedPermissionMode
    ? (permissionModeItems.find((item) => item.id === selectedPermissionMode) ?? null)
    : null;
  const permissionModeIsFirst = modelItems.length === 0 && !agentOptions?.length;

  const canShowQueuedPrompts =
    queuedPrompts.length > 0 &&
    !!onEditQueuedPrompt &&
    !!onDeleteQueuedPrompt &&
    !!onReorderQueuedPrompts &&
    !!onSendQueuedPromptNow;
  // The permission band takes priority over the notice band.
  const hasBand = canShowQueuedPrompts || !!(permissionRequest ?? notice);
  const shouldHandleSubmitAttempt = !disabled && (isWorking ? !!onSubmitWhileWorking : canSubmit);
  const resolvedPlaceholder = disabled
    ? 'Session closed'
    : isWorking
      ? 'Add a follow-up'
      : (placeholder ?? 'Send a message, tag @files or use /commands');

  return (
    <div className={cx(styles.composerRoot, composerThemeScope, className)}>
      {canShowQueuedPrompts && (
        <QueuedPromptsBand
          prompts={queuedPrompts}
          onEdit={onEditQueuedPrompt}
          onDelete={onDeleteQueuedPrompt}
          onReorder={onReorderQueuedPrompts}
          onSendNow={onSendQueuedPromptNow}
          connectToBandBelow={!!(permissionRequest && onResolvePermission)}
        />
      )}

      {/* Permission band — shown when the agent is awaiting user approval. */}
      {permissionRequest && onResolvePermission && (
        <PermissionBand
          request={permissionRequest}
          queueCount={permissionQueueCount}
          onResolve={onResolvePermission}
        />
      )}

      {/* Notice band — height + opacity animate on enter/exit via the
          grid-rows 0fr↔1fr technique so add/remove transitions are smooth.
          Hidden when the permission band is active. */}
      {!permissionRequest && (
        <div
          className={cx(
            styles.noticeAnimWrapper,
            notice ? styles.noticeAnimVisible : styles.noticeAnimHidden
          )}
          aria-hidden={!notice}
        >
          <div className={styles.noticeOverflowClip}>
            {retainedNotice && <NoticeBand notice={retainedNotice} />}
          </div>
        </div>
      )}

      <div
        className={styles.composerShell({ hasBand: !!hasBand, dragActive })}
        onPaste={handlePaste}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Image attachment previews */}
        {imageAttachments.length > 0 && (
          <div className={styles.attachmentStrip}>
            {imageAttachments.map((att) => (
              <div key={att.id} className={styles.attachmentThumb} data-attachment-thumb>
                <button
                  type="button"
                  aria-label={`View image: ${att.name}`}
                  onClick={() => onViewImage?.(att)}
                  className={styles.attachmentThumbBtn}
                >
                  <img src={att.previewUrl} alt={att.name} className={styles.attachmentThumbImg} />
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${att.name}`}
                  onClick={() => removeAttachment(att.id)}
                  className={styles.attachmentRemoveBtn}
                >
                  <X style={{ width: '0.625rem', height: '0.625rem' }} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Editor area */}
        <div className={styles.editorArea}>
          <PromptEditor
            ref={(handle) => {
              editorRef.current = handle;
              if (editorApiRef) {
                if (typeof editorApiRef === 'function') {
                  editorApiRef(handle);
                } else {
                  (editorApiRef as React.MutableRefObject<PromptEditorRef | null>).current = handle;
                }
              }
            }}
            placeholder={resolvedPlaceholder}
            disabled={disabled}
            onChange={onInputChange}
            onSubmit={shouldHandleSubmitAttempt ? handleSubmit : undefined}
            onMentionInsert={onMentionInsert}
            mentionProvider={mentionProvider}
            renderMentionIcon={renderMentionIcon}
            queryMentions={queryMentions}
            queryCommands={queryCommands}
            onCommand={onCommand}
            popupClassName={composerThemeScope}
          />
        </div>

        {/* Toolbar */}
        <div className={styles.toolbar}>
          {/* Left: agent + model selector */}
          <div className={styles.toolbarLeft}>
            {agentOptions && agentOptions.length > 0 && modelItems.length === 0 && (
              <ComposerAgentSelector
                options={agentOptions}
                selectedId={selectedAgent}
                onSelect={(id) => onAgentChange?.(id)}
                locked={agentLocked}
                disabled={disabled}
              />
            )}
            {modelItems.length > 0 && (
              <ComboboxPopover<ModelItem>
                items={modelItems}
                value={selectedModel ?? null}
                onValueChange={(id) => onModelChange?.(id)}
                itemToKey={(item) => item.id}
                itemToLabel={(item) => item.name}
                disabled={disabled}
                searchPlaceholder="Search models…"
                contentClassName={composerThemeScope}
                contentStyle={{ minWidth: '12.5rem' }}
                triggerTitle={() => selectedAgentTitle}
                renderTrigger={(selected) => (
                  <span
                    style={{
                      display: 'inline-flex',
                      minWidth: 0,
                      alignItems: 'center',
                      gap: '0.375rem',
                      color: selected ? 'var(--em-foreground)' : 'var(--em-foreground-muted)',
                      fontSize: 'var(--em-text-xs)',
                      lineHeight: 1,
                    }}
                  >
                    {selectedAgentItem?.icon && (
                      <span style={{ display: 'inline-flex', flexShrink: 0 }}>
                        {selectedAgentItem.icon}
                      </span>
                    )}
                    <span
                      style={{
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        lineHeight: 1.25,
                      }}
                    >
                      {selected?.name ?? 'Model…'}
                    </span>
                  </span>
                )}
                renderItem={(item) => (
                  <span
                    style={{
                      flex: '1 1 0%',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      fontSize: 'var(--em-text-sm)',
                    }}
                  >
                    {item.name}
                  </span>
                )}
                renderItemDetail={(item) => <ModelDetailCard item={item} />}
                detailSide="right"
                detailAlign="start"
                renderFooter={
                  effortItems.length > 0
                    ? () => (
                        <DropdownMenu.Root>
                          <DropdownMenu.Trigger className={styles.effortRow}>
                            <span className={styles.effortRowLabel}>Effort</span>
                            <span className={styles.effortRowValue}>
                              {selectedEffortItem?.name ?? 'Default'}
                              <ChevronRight
                                style={{ width: '0.75rem', height: '0.75rem', flexShrink: 0 }}
                              />
                            </span>
                          </DropdownMenu.Trigger>
                          <DropdownMenu.Content
                            className={composerThemeScope}
                            side="right"
                            align="start"
                            sideOffset={4}
                          >
                            <DropdownMenu.RadioGroup
                              value={selectedEffort}
                              onValueChange={(v) => onEffortChange?.(String(v))}
                            >
                              {effortItems.map((e) => (
                                <DropdownMenu.RadioItem key={e.id} value={e.id}>
                                  {e.name}
                                </DropdownMenu.RadioItem>
                              ))}
                            </DropdownMenu.RadioGroup>
                          </DropdownMenu.Content>
                        </DropdownMenu.Root>
                      )
                    : undefined
                }
              />
            )}
            {permissionModeItems.length > 0 && (
              <Select.Root
                value={selectedPermissionMode ?? undefined}
                onValueChange={(id) => {
                  if (id) onPermissionModeChange?.(id);
                }}
                disabled={disabled}
              >
                <Select.Trigger
                  className={permissionModeIsFirst ? styles.permissionModeTrigger : undefined}
                >
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      color: selectedPermissionModeItem
                        ? 'var(--em-foreground)'
                        : 'var(--em-foreground-muted)',
                      fontSize: 'var(--em-text-xs)',
                      lineHeight: 1.25,
                    }}
                  >
                    <ShieldCheck style={{ width: '0.75rem', height: '0.75rem', flexShrink: 0 }} />
                    {selectedPermissionModeItem?.name ?? 'Permissions…'}
                  </span>
                </Select.Trigger>
                <Select.Content
                  align="start"
                  width="trigger"
                  className={composerThemeScope}
                  style={{
                    width: 'min(18rem, var(--available-width, 18rem))',
                    minWidth: 0,
                    maxWidth: '18rem',
                  }}
                >
                  {permissionModeItems.map((item) => (
                    <Select.Item key={item.id} value={item.id}>
                      <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                        <span
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontSize: 'var(--em-text-sm)',
                          }}
                        >
                          {item.name}
                        </span>
                        {item.description && (
                          <span
                            style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              fontSize: 'var(--em-text-xs)',
                              color: 'var(--em-foreground-muted)',
                            }}
                          >
                            {item.description}
                          </span>
                        )}
                      </span>
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            )}
            {mcpServers.length > 0 && (
              <Popover.Root>
                <Popover.Trigger className={styles.mcpTrigger} disabled={disabled}>
                  <Plug style={{ width: '0.75rem', height: '0.75rem', flexShrink: 0 }} />
                  MCP {mcpServers.length}
                </Popover.Trigger>
                <Popover.Content
                  align="start"
                  className={cx(styles.mcpPopoverContent, composerThemeScope)}
                  aria-label="Session MCP servers"
                >
                  <div className={styles.mcpList}>
                    {mcpServers.map((server) => (
                      <div key={`${server.transport}:${server.name}`} className={styles.mcpRow}>
                        <span className={styles.mcpName}>{server.name}</span>
                        <span className={styles.mcpBadge}>{server.transport}</span>
                      </div>
                    ))}
                  </div>
                </Popover.Content>
              </Popover.Root>
            )}
          </div>

          {/* Right: usage donut + attach + send/stop */}
          <div className={styles.toolbarRight}>
            {contextUsage && contextUsage.size > 0 && (
              <ContextUsageIndicator usage={contextUsage} disabled={disabled} />
            )}
            {onAttach && (
              <Button
                variant="ghost"
                size="xs"
                icon
                onClick={onAttach}
                disabled={disabled}
                aria-label="Add attachment"
              >
                <Paperclip />
              </Button>
            )}

            {showSubmitButton ? (
              isWorking ? (
                <Button
                  variant="primary"
                  tone="destructive"
                  size="sm"
                  icon
                  className={styles.sendButtonRound}
                  onClick={onStop}
                  aria-label="Stop generation"
                >
                  <span className={styles.stopIcon} aria-hidden="true" />
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  icon
                  className={styles.sendButtonRound}
                  onClick={() => handleSubmit(editorRef.current?.getText() ?? '')}
                  disabled={disabled || !canSubmit}
                  aria-label="Send message"
                >
                  <ArrowUp />
                </Button>
              )
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
