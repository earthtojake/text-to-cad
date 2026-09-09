/**
 * @emdash/chat-ui public API.
 *
 * Three primitives following the CodeMirror EditorState/EditorView split:
 *
 *   createChatContext(opts) — global services singleton (theme, highlighter,
 *                             shared caches, measureEpoch). Create once per app.
 *   createChatState(ctx)   — per-conversation state (transcript + parse caches).
 *   createChatView(opts)   — per-mount DOM owner (virtualizer, scroll, scheduler).
 *
 * Quick start:
 *   const ctx  = createChatContext({ highlighter });
 *   const st   = createChatState(ctx);
 *   const view = createChatView({ context: ctx, state: st, parent, composer: 'slot' });
 *   st.transcript.history.seed(items);
 *   // After mount:
 *   ReactDOM.createPortal(<ChatComposer />, view.composerSlot!);
 *   // Cleanup:
 *   view.dispose();
 *   st.dispose();
 *   ctx.dispose();
 */

import './styles/global.css';

// ── Core API ──────────────────────────────────────────────────────────────────

export { createChatContext } from './chat-context';
export type { ChatContext, ChatContextOptions } from './chat-context';

export { connectSession, createChatState, tailMode, pinTopMode } from './state/chat-state';
export type {
  ChatState,
  ChatStateOptions,
  ScrollMode,
  HeightmapStore,
  ChatSessionState,
  ChatSessionSnapshot,
  PendingPrompt,
  ConnectSessionSource,
  ConnectSessionOptions,
} from './state/chat-state';

export { createChatView } from './chat-view';
export type {
  ChatView,
  ChatViewOptions,
  ComposerPlacement,
  ComposerPlacementOptions,
} from './chat-view';

// ── Data types ────────────────────────────────────────────────────────────────

export type {
  ChatItem,
  ChatMessage,
  ChatImageAttachment,
  ChatGeneratedImage,
  ChatToolCall,
  ChatThinking,
  ChatFileOpToolCall,
  ChatExecute,
  ChatDiff,
  ChatResourceLink,
  ResourceTarget,
  ChatPlan,
  ChatPlanEntry,
  PlanEntryStatus,
  PlanEntryPriority,
  ChatRole,
  FileOpKind,
  FileOp,
  ToolStatus,
  TranscriptTurn,
  TranscriptItem,
  ToolNode,
  AcpPermissionRequest,
  PlanState,
  TerminalOutputSnapshot,
} from './model';

// ── Transcript API ────────────────────────────────────────────────────────────

export type { TurnStatus, TranscriptApi, ChatHistory } from './state/transcript';

// ── Theme ─────────────────────────────────────────────────────────────────────

export type {
  ChatConfig,
  ChipConfig,
  ChatTheme,
  FontConfig,
  FontFamilies,
  ResolvedTheme,
  RoleName,
  TypeRole,
} from './core/theme';
export { buildChatTheme, DEFAULT_CONFIG, DEFAULT_THEME } from './core/theme';

// ── Highlighter ───────────────────────────────────────────────────────────────

export type { ChatHighlighter, HighlightResult, CodeToken } from './core/highlight/highlighter';
export { createDefaultHighlighter } from './core/highlight/highlighter';

// ── Mention provider ─────────────────────────────────────────────────────────

export type {
  MentionProvider,
  ChatMentionMeta,
  ChatMentionKind,
} from './core/markdown/mention-provider';

// ── Command provider ──────────────────────────────────────────────────────────

export type { CommandProvider, ChatCommandMeta } from './core/markdown/command-provider';

// ── Commands + scroll helpers ─────────────────────────────────────────────────

export { CHAT_VIEW_COMMANDS } from './commands';
export type {
  ChatCommands,
  ChatViewCommand,
  ChatViewCommandId,
  ScrollToItemOptions,
} from './commands';

// ── Dev helpers ───────────────────────────────────────────────────────────────

export { generateMockTranscript, mockMentionProvider } from './mock-transcript';

// ── Cache types (for advanced use) ────────────────────────────────────────────

export type { ChatCaches, SharedCaches, ParseCaches } from './core/caches';
export { createChatCaches } from './core/caches';
