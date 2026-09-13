/**
 * ChatState — per-conversation, width-independent state.
 *
 * Holds the transcript (history + active turn), parse caches, and all
 * per-conversation view state that must survive view dispose/recreate
 * (e.g. tab switches):
 *
 *   viewState       — collapse map (inverted semantics: true = expanded)
 *   expandedUserId  — the single expanded user message card id
 *   scroll          — declarative scroll intent (ScrollMode: tail|anchor(edge))
 *   heightmap       — Map<unitId, measuredHeight> keyed by RenderUnit.id
 *                     (stable "${itemId}#self"). lastWidth is the container
 *                     width at snapshot time; used by ChatRoot to decide
 *                     whether seeded heights are pixel-accurate or estimates.
 *
 * Lives under a `createRoot` so it persists across ChatView mounts:
 * disposing a view does NOT dispose the state, so re-attaching a view
 * reuses Block object identities and warm WeakMap measurement caches.
 *
 * Lifetime: per conversation. Dispose when the conversation is closed.
 *
 * Usage:
 *   const state = createChatState(ctx);
 *   state.transcript.history.seed(items);
 *   const view = createChatView({ context: ctx, state, parent });
 *   // ... later, on conversation close:
 *   state.dispose();
 *
 * Note: scroll is per-viewport in semantics. If two views ever attached to
 * the same ChatState simultaneously they would contend for scroll. Today
 * there is exactly one view per conversation (ChatRoot is keyed by
 * conversationId in AcpChatPanel) — this assumption is intentional.
 */

import { createMemo, createRoot, createSignal } from 'solid-js';
import type { ChatContext } from '../chat-context';
import { createParseCaches } from '../core/caches';
import type { ParseCaches } from '../core/caches';
import type {
  AcpPermissionRequest,
  ChatImageAttachment,
  PlanState,
  TerminalOutputSnapshot,
  TranscriptTurn,
} from '../model';
import { createTranscript } from './transcript';
import type { TranscriptApi } from './transcript';
import { createViewState } from './view-state';
import type { ViewState } from './view-state';
export type { ScrollMode } from './scroll-mode';
export { tailMode, pinTopMode } from './scroll-mode';

// ScrollMode type and helpers live in scroll-mode.ts (re-exported above)
// so unit tests can import them without pulling in DOM-dependent parse caches.
import type { ScrollMode } from './scroll-mode';

/**
 * Per-conversation heightmap snapshot.
 *
 * Keys are stable `RenderUnit.id` values ("${itemId}#${key}", today always
 * "${itemId}#self" since every ChatItem maps to exactly one RenderUnit).
 * Values are measured row heights in pixels from the most recent view mount.
 *
 * `lastWidth` is the container width (px) when the snapshot was written.
 * ChatRoot uses it to decide whether to seed heights as pixel-accurate (same
 * width → no scrollbar drift) or as best-effort estimates (width changed →
 * anchor-based restore corrects position without drift).
 */
export type HeightmapStore = {
  /** Return the last-measured height for a unit id, or undefined on cache miss. */
  get(unitId: string): number | undefined;
  /** Bulk-write a set of unitId → height entries from a ChatRoot dispose snapshot. */
  setAll(entries: Iterable<[unitId: string, height: number]>): void;
  /** The container width when the most recent snapshot was taken. 0 = not set. */
  lastWidth: number;
};

export type ChatSessionState = {
  readonly state: ChatSessionSnapshot;
  setPermissions(permissions: readonly AcpPermissionRequest[]): void;
  setPlan(plan: PlanState | null): void;
  setPendingPrompt(prompt: PendingPrompt | null): void;
  setTerminalOutput(terminalId: string, snapshot: TerminalOutputSnapshot | null): void;
};

export type ChatSessionSnapshot = {
  readonly permissions: readonly AcpPermissionRequest[];
  readonly plan: PlanState | null;
  readonly pendingToolCallIds: Set<string>;
  readonly pendingPrompt: PendingPrompt | null;
  terminalOutput(terminalId: string): TerminalOutputSnapshot | null;
};

export type PendingPrompt = {
  id: string;
  text: string;
  attachments?: ChatImageAttachment[];
};

type LiveReadable<T> = {
  getSnapshot(): T | null | undefined;
  subscribe(listener: () => void): () => void;
};

export type ConnectSessionSource = {
  activeTurn: LiveReadable<TranscriptTurn | null>;
  plan: LiveReadable<PlanState | null>;
  sessionState: LiveReadable<{ pendingPermissions: readonly AcpPermissionRequest[] }>;
};

export type ConnectSessionOptions = {
  onTurnCommitted?: () => void;
};

export type ChatState = {
  /** Reactive transcript (history + active turn + turn status). */
  readonly transcript: TranscriptApi;
  /** Per-messageId parse caches. Stable Block identities enable WeakMap hits. */
  readonly parseCaches: ParseCaches;
  /**
   * Conversation URI passed to `createChatState`. Forwarded to
   * `MentionProvider.resolve` so a global provider can scope resolution to the
   * correct project or worktree.
   */
  readonly uri: string | undefined;

  // ── Per-conversation view state (persists across view remounts) ──────────

  /**
   * Collapse/expand state for collapsible rows.
   * Lives here (not in ChatRoot) so it survives tab switches.
   */
  readonly viewState: ViewState;

  /** Reactive session-level slices resolved by row renderers. */
  readonly session: ChatSessionState;

  /**
   * The id of the single currently-expanded user message card, or null.
   * Persisted here so re-mounting a view restores the expansion.
   */
  readonly expandedUserId: {
    get(): string | null;
    set(id: string | null): void;
  };

  /**
   * Declarative scroll intent. Written by ChatRoot's readPhase (user scroll)
   * and by the host via view.setScrollMode(); read by ChatRoot on mount/swap
   * to restore position without DOM geometry reads.
   */
  readonly scroll: {
    get(): ScrollMode;
    set(mode: ScrollMode): void;
  };

  /**
   * Measured row heights keyed by RenderUnit.id. Written by ChatRoot on
   * dispose; used to seed the Virtualizer on the next mount to avoid
   * scrollbar drift.
   */
  readonly heightmap: HeightmapStore;

  /**
   * Dispose the state's reactive root and all parse caches.
   * Call when the conversation is permanently closed (not just hidden).
   */
  dispose(): void;
};

export type ChatStateOptions = {
  /**
   * Conversation URI — passed as the second argument to
   * `MentionProvider.resolve(token, uri)` so the global provider can scope
   * resolution to the correct project or worktree.
   */
  uri?: string;
};

// ── createChatState ───────────────────────────────────────────────────────────

/**
 * Create a ChatState for a conversation.
 *
 * The state owns a `createRoot` so transcript signals, parse caches, and
 * per-conversation view state survive across view mounts/unmounts. Multiple
 * views can attach to the same state simultaneously (though only one view per
 * conversation is expected today — see scroll note above).
 *
 * @param ctx  - Shared ChatContext (provides highlighter, caches, theme).
 * @param opts - Optional per-conversation options (e.g. `uri`).
 */
export function createChatState(ctx: ChatContext, opts?: ChatStateOptions): ChatState {
  let transcript!: TranscriptApi;
  let parseCaches!: ParseCaches;
  let viewState!: ViewState;
  let session!: ChatSessionState;
  let getExpandedUserId!: () => string | null;
  let setExpandedUserId!: (id: string | null) => void;
  let disposeRoot!: () => void;

  createRoot((dispose) => {
    disposeRoot = dispose;
    transcript = createTranscript();
    parseCaches = createParseCaches(ctx.mentionProvider, ctx.commandProvider, opts?.uri);
    viewState = createViewState();
    [getExpandedUserId, setExpandedUserId] = createSignal<string | null>(null);
    session = createSessionState();
  });

  // Scroll mode — plain mutable value; not reactive (ChatRoot reads it once on
  // mount/swap, writes it via setAnchor in readPhase and host calls). No signal.
  let scrollMode: ScrollMode = { kind: 'tail' };

  // Heightmap — plain Map keyed by RenderUnit.id.
  const heightmapData = new Map<string, number>();
  let heightmapLastWidth = 0;

  const heightmap: HeightmapStore = {
    get(unitId) {
      return heightmapData.get(unitId);
    },
    setAll(entries) {
      for (const [id, h] of entries) {
        heightmapData.set(id, h);
      }
    },
    get lastWidth() {
      return heightmapLastWidth;
    },
    set lastWidth(w: number) {
      heightmapLastWidth = w;
    },
  };

  return {
    transcript,
    parseCaches,
    uri: opts?.uri,
    viewState,
    session,
    expandedUserId: {
      get: getExpandedUserId,
      set: setExpandedUserId,
    },
    scroll: {
      get: () => scrollMode,
      set: (mode) => {
        scrollMode = mode;
      },
    },
    heightmap,
    dispose() {
      parseCaches.clearAll();
      disposeRoot();
    },
  };
}

function createSessionState(): ChatSessionState {
  const [permissions, setPermissions] = createSignal<readonly AcpPermissionRequest[]>([]);
  const [plan, setPlan] = createSignal<PlanState | null>(null);
  const [pendingPrompt, setPendingPrompt] = createSignal<PendingPrompt | null>(null);
  const [terminalOutputs, setTerminalOutputs] = createSignal<
    ReadonlyMap<string, TerminalOutputSnapshot>
  >(new Map());
  const pendingToolCallIds = createMemo(() => {
    const ids = new Set<string>();
    for (const request of permissions()) {
      ids.add(request.toolCall.toolCallId);
    }
    return ids;
  });

  const state: ChatSessionSnapshot = {
    get permissions() {
      return permissions();
    },
    get plan() {
      return plan();
    },
    get pendingToolCallIds() {
      return pendingToolCallIds();
    },
    get pendingPrompt() {
      return pendingPrompt();
    },
    terminalOutput(terminalId) {
      return terminalOutputs().get(terminalId) ?? null;
    },
  };

  return {
    state,
    setPermissions: (next) => setPermissions([...next]),
    setPlan,
    setPendingPrompt,
    setTerminalOutput(terminalId, snapshot) {
      setTerminalOutputs((previous) => {
        const next = new Map(previous);
        if (snapshot === null) {
          next.delete(terminalId);
        } else {
          next.set(terminalId, snapshot);
        }
        return next;
      });
    },
  };
}

export function connectSession(
  state: ChatState,
  source: ConnectSessionSource,
  options: ConnectSessionOptions = {}
): () => void {
  let hadActiveTurn = source.activeTurn.getSnapshot() !== null;

  const syncSessionState = (): void => {
    const snapshot = source.sessionState.getSnapshot();
    state.session.setPermissions(snapshot?.pendingPermissions ?? []);
  };

  const syncPlan = (): void => {
    state.session.setPlan(source.plan.getSnapshot() ?? null);
  };

  const syncActiveTurn = (): void => {
    const turn = source.activeTurn.getSnapshot() ?? null;
    if (turn) state.session.setPendingPrompt(null);
    state.transcript.activeTurn.set(turn);
    if (!turn && hadActiveTurn) options.onTurnCommitted?.();
    hadActiveTurn = turn !== null;
  };
  syncSessionState();
  syncPlan();
  syncActiveTurn();

  const unsubs = [
    source.sessionState.subscribe(syncSessionState),
    source.plan.subscribe(syncPlan),
    source.activeTurn.subscribe(syncActiveTurn),
  ];
  return () => {
    for (const unsub of unsubs) unsub();
  };
}
