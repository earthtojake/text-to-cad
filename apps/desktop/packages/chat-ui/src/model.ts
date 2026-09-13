import type {
  AcpPermissionRequest,
  PlanEntryPriority,
  PlanEntryStatus,
  PlanState,
  ToolNode,
  ToolStatus,
  TranscriptItem,
  TranscriptMessage,
  TranscriptThinking,
  TranscriptTurn,
  TranscriptTurnOutcome,
} from '@emdash/core/runtimes/acp/api/client';

export type {
  AcpPermissionRequest,
  PlanEntryPriority,
  PlanEntryStatus,
  PlanState,
  ToolNode,
  ToolStatus,
  TranscriptItem,
  TranscriptMessage,
  TranscriptThinking,
  TranscriptTurn,
  TranscriptTurnOutcome,
};

export type ChatRole = 'user' | 'assistant' | 'thought';

export type ThinkingStatus = 'thinking' | 'done';

/**
 * An image attachment shown as a thumbnail at the top of a user message bubble.
 *
 * `dataUrl` carries the inline image for display; when it is absent (the source
 * content could not be resolved, e.g. on reload when the agent did not replay
 * the bytes) the renderer shows a neutral fallback tile instead.
 */
export type ChatImageAttachment = {
  id: string;
  name: string;
  /** MIME type retained from the runtime attachment reference when available. */
  mimeType?: 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp';
  /** Data URL for inline display; absent when content can't be resolved -> fallback tile. */
  dataUrl?: string;
};

export type ChatMessage = {
  kind: 'message';
  id: string;
  seq?: number;
  role: ChatRole;
  /** Markdown source text. */
  text: string;
  /** True while the agent is still writing to this message. */
  streaming?: boolean;
  /** Image attachments rendered as a thumbnail strip above the text (user messages). */
  attachments?: ChatImageAttachment[];
};

export type ChatToolCall = {
  kind: 'tool';
  id: string;
  name: string;
  status: ToolStatus;
  /** Plain-language activity category used for status copy and accessibility. */
  activity?: 'search' | 'web-search' | 'web-fetch' | 'image-generation' | 'integration';
  awaitingPermission?: boolean;
  /** Optional failure message shown in the error icon's native tooltip. */
  error?: string;
  /** Short one-line synopsis shown alongside the tool name. */
  inputSummary?: string;
  /** First line of the tool's text result, shown under the row when the provider reported one. */
  outputPreview?: string;
  /** Latest provider progress line while the call runs. */
  progress?: string;
  /** Runtime-owned generated image references. Bytes are resolved lazily by the host. */
  outputAttachments?: ChatImageAttachment[];
  /** Id of the parent tool call (for hierarchical rendering). */
  parentId?: string;
};

/**
 * A generated-image result displayed beside its originating tool activity.
 *
 * Transcript/runtime state stores only immutable attachment references. The
 * desktop host resolves bytes on demand, so large image payloads never enter
 * the virtualized chat model or transcript JSON.
 */
export type ChatGeneratedImage = {
  kind: 'generated-image';
  id: string;
  attachments: ChatImageAttachment[];
  /** Item that owns the result (normally an image-generation tool call). */
  sourceItemId: string;
  source: 'generated-image' | 'assistant-message';
};

export type SubagentPhase = 'spawning' | 'running' | 'completed' | 'failed';

export type ChatSubagentToolCall = {
  kind: 'subagent';
  id: string;
  name: string;
  status: ToolStatus;
  phase: SubagentPhase;
  agentId?: string;
  background?: boolean;
  awaitingPermission?: boolean;
  /** Optional failure message shown in the failed state tooltip. */
  error?: string;
  /** First line of what the agent reported back, shown once it finished. */
  outputPreview?: string;
  /** Id of the parent tool call (for hierarchical rendering). */
  parentId?: string;
};

/**
 * A thinking / reasoning row produced by the agent before it replies.
 *
 * While `status === 'thinking'` the row shows a fixed-height streaming window
 * with the tail of the reasoning text truncated/faded at the top.
 * When `status === 'done'` the row collapses to a "Thought for {duration}s"
 * header that can be expanded to reveal the full reasoning text.
 */
export type ChatThinking = {
  kind: 'thinking';
  id: string;
  seq?: number;
  segmentId?: string;
  status: ThinkingStatus;
  text: string;
  startedAt: number;
  durationMs?: number;
};

/** ACP tool-call categories that represent file operations. */
export type FileOpKind = 'read' | 'edit' | 'delete' | 'move';

/** A single file touched by a file-operation tool call. */
export type FileOp = {
  path: string;
};

/**
 * A file-operation tool call row (read / edit / delete / move).
 *
 * Single file (ops.length <= 1): renders as an inline one-liner, e.g. "Read foo.tsx".
 * Multiple files (ops.length > 1): renders as a collapsible header "Read 2 files ›"
 * that expands to a per-file list. While `status === 'running'` the collapsed
 * header shows a fixed-height streaming preview window (like ChatThinking).
 *
 * Collapse semantics are inverted: the stored "collapsed" bool means "expanded"
 * (same convention as ChatThinking).
 */
export type ChatFileOpToolCall = {
  kind: 'file-op';
  id: string;
  op: FileOpKind;
  status: ToolStatus;
  awaitingPermission?: boolean;
  /** Optional failure message shown in the error icon's native tooltip. */
  error?: string;
  /** Accumulating list of files touched. Replaced (not appended) on each update. */
  ops: FileOp[];
  /** Id of the parent tool call (for hierarchical rendering). */
  parentId?: string;
};

/**
 * An execute tool call row — ACP `kind: 'execute'` commands (e.g. Bash).
 *
 * Rendered as a single non-interactive line: "Execute `{command}` {elapsed}s".
 * While running: shimmer + live ticking timer. When done: frozen duration if
 * durationMs is present; duration omitted if data is unavailable (e.g. replay).
 */
export type ChatExecute = {
  kind: 'execute';
  id: string;
  /** The shell command, e.g. "ls -a". Empty string until the command-bearing update arrives. */
  command: string;
  /** Optional provider-supplied purpose shown as the execute card title. */
  inputSummary?: string;
  /**
   * Tool output as retained lines. For live terminal output this is the
   * client store's identity-stable array (mutated in place across flushes);
   * for static tool output it is a memoized split of the final text.
   */
  outputLines?: readonly string[];
  /** True when earlier output was dropped upstream (agent ring or client cap). */
  outputTruncated?: boolean;
  /** Bumped per live-output flush; lets consumers detect changes despite the stable array identity. */
  outputVersion?: number;
  status: ToolStatus;
  awaitingPermission?: boolean;
  /** Optional failure message shown in the error icon's native tooltip. */
  error?: string;
  /** Start time (epoch ms) — used to derive the live timer and frozen duration. */
  startedAt: number;
  /** Frozen duration once status flips to 'done'. Absent when data is unavailable. */
  durationMs?: number;
  /** ACP terminal id backing live output, when the command runs in a terminal. */
  terminalId?: string;
  /** Id of the parent tool call (for hierarchical rendering). */
  parentId?: string;
};

/**
 * Live terminal output as held by the client-side line log store.
 *
 * `lines` is identity-stable across flushes (the store mutates it in place);
 * `version` is bumped once per flush so consumers can detect changes without
 * comparing content. `truncated` collapses at presentation: it is true when
 * output was dropped anywhere upstream (agent-side ring buffer or the client
 * store's byte cap) — the UI never distinguishes the two.
 */
export type TerminalOutputSnapshot = {
  readonly lines: readonly string[];
  readonly truncated: boolean;
  readonly version: number;
};

/**
 * A diff preview row — produced by ACP `kind: 'edit'` tool calls.
 *
 * Renders a compact, non-scrollable preview of the first changed region
 * (capped at 12 lines with ±1 context), with syntax + diff highlighting.
 * One `ChatDiff` is created per changed file within a single tool call.
 *
 * `oldText` is the replaced region (old_string). `null` means a new file —
 * all `newText` lines are additions.
 */
export type ChatDiff = {
  kind: 'diff';
  /** `${toolCallId}:${path}` — unique per file within a tool call. */
  id: string;
  /** Full path; basename and extension derived in the component. */
  path: string;
  /** The replaced region, or null for new files. */
  oldText: string | null;
  newText: string;
  status: ToolStatus;
  awaitingPermission?: boolean;
  /** Optional failure message shown in the error icon's native tooltip. */
  error?: string;
  /** Id of the parent tool call (for hierarchical rendering). */
  parentId?: string;
};

/**
 * Resolved addressing target for a resource link.
 *
 * `workspace-file` — the URI resolves to a file inside the current workspace;
 *   `path` is the workspace-relative or absolute path, ready for the editor.
 * `external` — an http(s) URL or other browser-openable resource.
 * `opaque` — a custom MCP server scheme the client cannot resolve locally.
 */
export type ResourceTarget =
  | { kind: 'workspace-file'; path: string }
  | { kind: 'external'; url: string }
  | { kind: 'opaque' };

/**
 * A resource-link row — produced by ACP `resource_link` content blocks inside
 * agent messages, emitted as a standalone row (split from the surrounding message).
 *
 * The `target` is pre-resolved by the desktop enrichment transform before the
 * item enters chat-ui, so the renderer stays transport-agnostic.
 *
 * Renders as a compact card: mime icon, `title ?? name`, secondary line
 * derived from `target` (path / host / scheme), and optional size.
 * Clicking a `workspace-file` target opens it in the editor.
 */
export type ChatResourceLink = {
  kind: 'resource-link';
  id: string;
  /** Original ACP URI, preserved for display and copy. */
  uri: string;
  /** Required resource name. */
  name: string;
  /** Optional human-friendly label (preferred for display over `name`). */
  title?: string;
  /** Optional one-line description shown below the title. */
  description?: string;
  /** MIME type hint; drives the file-type icon. */
  mimeType?: string;
  /** File size in bytes; shown when present. */
  size?: number;
  /** Pre-resolved addressing target. */
  target: ResourceTarget;
  status?: ToolStatus;
  /** Optional failure message shown in the error icon's native tooltip. */
  error?: string;
};

/** Lifecycle status of a single plan entry. Mirrors ACP `PlanEntryStatus`. */
/**
 * A single task entry within an agent execution plan.
 *
 * `content` is a markdown-capable description of the task.
 * `status` and `priority` mirror the ACP `PlanEntry` schema.
 */
export type ChatPlanEntry = {
  content: string;
  status: PlanEntryStatus;
  priority: PlanEntryPriority;
};

/**
 * An agent execution plan row — produced by ACP `plan` / `plan_update` session updates.
 *
 * Renders as a collapsible checklist (collapsed by default to a capped preview
 * window; click the header to expand the full list). Each entry shows a status
 * glyph (○ / ◐ / ●) and its markdown content (wrapped text). The plan replaces
 * its entries wholesale on each ACP update.
 *
 * While `streaming` is true, entries are still being appended: the collapsed
 * preview auto-scrolls to the newest task and the header shimmers. Cleared on
 * turn completion.
 */
export type ChatPlan = {
  kind: 'plan';
  id: string;
  entries: ChatPlanEntry[];
  /** True while tasks are still being appended (drives preview auto-scroll + shimmer). */
  streaming?: boolean;
};

export type WorkingItem = {
  kind: 'working';
  id: string;
};

export type TurnOutcomeItem = {
  kind: 'turn-outcome';
  id: string;
  outcome: TranscriptTurnOutcome;
};

export type SyntheticItem = WorkingItem | TurnOutcomeItem;

export type ChatItem =
  | TranscriptItem
  | ChatMessage
  | ChatToolCall
  | ChatGeneratedImage
  | ChatSubagentToolCall
  | ChatThinking
  | ChatFileOpToolCall
  | ChatExecute
  | ChatDiff
  | ChatResourceLink
  | ChatPlan;
