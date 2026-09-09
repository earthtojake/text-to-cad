import { batch, createSignal } from 'solid-js';
import { createStore, reconcile, unwrap } from 'solid-js/store';
import type { ChatItem, TranscriptTurn } from '@/model';

/**
 * Global turn lifecycle status.
 *
 * - `'generating'` — the agent is actively streaming content.
 * - `'cancelled'`  — the host called commit('cancelled'); stays until next turn.
 * - `'done'`       — the turn completed normally, or no turn has run yet.
 */
export type TurnStatus = 'generating' | 'cancelled' | 'done';

export type TranscriptState = {
  readonly committedTurns: readonly TranscriptTurn[];
  readonly activeTurnSnapshot: TranscriptTurn | null;
  readonly turnStatus: TurnStatus;
};

// ── ChatHistory ────────────────────────────────────────────────────────────────

export type ChatHistory = {
  /** All committed turns. Reactive: reading inside a memo/effect tracks identity changes. */
  get(): readonly TranscriptTurn[];
  /**
   * Replace the entire committed history and reset activeTurn.
   * Rebuilds the id map. Prefer for initial load / session replay.
   */
  seed(turns: readonly TranscriptTurn[]): void;
  /**
   * Prepend older turns before the current committed history (pagination).
   * Stable object references required — identity-keyed caches key by ref.
   * Rebuilds the id map (O(total)).
   */
  prepend(turns: readonly TranscriptTurn[]): void;
  /**
   * Append turns after the current committed history (commit path / bulk add).
   * Patches the id map incrementally (O(new)).
   */
  append(turns: readonly TranscriptTurn[]): void;
};

// ── ActiveTurn ─────────────────────────────────────────────────────────────────

export type ActiveTurn = {
  /**
   * The current desired snapshot — the full intended turn state, including any
   * text that may still be buffered in an overlying smoother. Callers that want
   * to extend the turn should read from here.
   */
  get(): TranscriptTurn | null;
  /**
   * Replace the active turn with a full snapshot and set the status.
   *
   * Uses reconcile(key:'id') so in-place text growth only patches the changed
   * message node (O(activeTurn), not O(total)).
   *
   * - Pass `null` to clear the turn (e.g. after commit).
   * - Stable item `id` fields are required for reconcile to work correctly.
   * - The host is authoritative; chat-ui does not assume it is the sole writer.
   */
  set(turn: TranscriptTurn | null, _status?: TurnStatus): void;
  commit(status?: 'done' | 'cancelled'): void;
};

// ── TranscriptApi ──────────────────────────────────────────────────────────────

export type TranscriptApi = {
  /** Imperative history write surface (seed / prepend / append). */
  history: ChatHistory;
  /** Controlled active-turn write surface (set / commit). */
  activeTurn: ActiveTurn;
  /** Reactive read facade — consumed by ChatRoot and helpers. */
  readonly state: TranscriptState;
  /** Returns the transcript item with the given id, or undefined if not found. */
  findItemById(id: string): ChatItem | undefined;
  /** Clear all state (e.g. at the start of a replay). */
  reset(): void;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function finalizeCompatItem(item: ChatItem): ChatItem {
  if (item.kind === 'message' && 'streaming' in item) {
    return { ...item, streaming: false } as ChatItem;
  }
  if ('status' in item && item.status === 'running') return { ...item, status: 'done' } as ChatItem;
  if (item.kind === 'plan') return { ...item, streaming: false } as ChatItem;
  return item;
}

function assertOrderedTurns(turns: readonly TranscriptTurn[], source: string): void {
  if (!import.meta.env.DEV) return;
  for (let i = 1; i < turns.length; i++) {
    if (turns[i - 1].seq > turns[i].seq) {
      console.error(
        `[chat-ui] ${source} received out-of-order TranscriptTurn seq values: ` +
          `${turns[i - 1].id} (${turns[i - 1].seq}) before ${turns[i].id} (${turns[i].seq}).`
      );
      return;
    }
  }
}

function assertOrderedItems(turn: TranscriptTurn): void {
  if (!import.meta.env.DEV) return;
  for (let i = 1; i < turn.items.length; i++) {
    const prevSeq = (turn.items[i - 1] as { seq?: number }).seq ?? 0;
    const nextSeq = (turn.items[i] as { seq?: number }).seq ?? 0;
    if (prevSeq > nextSeq) {
      console.error(
        `[chat-ui] turn "${turn.id}" received out-of-order item seq values: ` +
          `${turn.items[i - 1].id} (${prevSeq}) before ${turn.items[i].id} (${nextSeq}).`
      );
      return;
    }
  }
}

// ── Factory ───────────────────────────────────────────────────────────────────

export function createTranscript(): TranscriptApi {
  // Committed items are immutable after placement — only ever swapped as a whole
  // array identity (seed/prepend/append). A plain signal gives coarse tracking
  // with zero store-proxy overhead on the hot measure/render path.
  const [committed, setCommitted] = createSignal<readonly TranscriptTurn[]>([]);

  // activeTurn + turnStatus mutate in place during streaming; fine-grained
  // store tracking is warranted here.
  const [live, setLive] = createStore<{
    activeTurn: TranscriptTurn | null;
    turnStatus: TurnStatus;
  }>({
    activeTurn: null,
    turnStatus: 'done',
  });

  // Expose the TranscriptState shape via getters. committed() is read in the
  // getter so createMemo/createEffect readers re-run on identity changes.
  // live.activeTurn/live.turnStatus retain fine-grained reactivity.
  const state: TranscriptState = {
    get committedTurns() {
      return committed();
    },
    get activeTurnSnapshot() {
      return live.activeTurn;
    },
    get turnStatus() {
      return live.turnStatus;
    },
  };

  // item id → committed item map; rebuilt on history mutations.
  const itemMap = new Map<string, ChatItem>();

  const rebuildItemMap = (turns: readonly TranscriptTurn[]): void => {
    itemMap.clear();
    for (const turn of turns) {
      assertOrderedItems(turn);
      for (const item of turn.items) {
        if (import.meta.env.DEV && itemMap.has(item.id)) {
          console.error(
            `[chat-ui] duplicate ChatItem id "${item.id}" in turn "${turn.id}" — ` +
              'item ids must be unique across the entire transcript. ' +
              'This will corrupt id-keyed lookups (heightmap, scroll anchor, reconcile).'
          );
        }
        itemMap.set(item.id, item as ChatItem);
      }
    }
  };

  // ── history ─────────────────────────────────────────────────────────────────

  const history: ChatHistory = {
    get() {
      return committed();
    },

    seed(turns) {
      assertOrderedTurns(turns, 'history.seed');
      batch(() => {
        setCommitted(turns);
        setLive({ activeTurn: null, turnStatus: 'done' });
      });
      rebuildItemMap(turns);
    },

    prepend(turns) {
      if (turns.length === 0) return;
      setCommitted((prev) => {
        const next = [...turns, ...prev];
        assertOrderedTurns(next, 'history.prepend');
        return next;
      });
      rebuildItemMap(committed());
    },

    append(turns) {
      if (turns.length === 0) return;
      setCommitted((prev) => {
        const next = [...prev, ...turns];
        assertOrderedTurns(next, 'history.append');
        return next;
      });
      rebuildItemMap(committed());
    },
  };

  // ── activeTurn ──────────────────────────────────────────────────────────────

  const activeTurnApi: ActiveTurn = {
    get() {
      return live.activeTurn;
    },

    set(turn, status) {
      batch(() => {
        if (turn === null) {
          setLive({ activeTurn: null, turnStatus: 'done' });
        } else {
          assertOrderedItems(turn);
          setLive('turnStatus', status ?? 'generating');
          setLive('activeTurn', reconcile(turn, { key: 'id' }));
        }
      });
    },

    commit(status = 'done') {
      const raw = live.activeTurn;
      if (!raw) return;
      const turn = {
        ...(unwrap(raw) as TranscriptTurn),
        items: (unwrap(raw).items as ChatItem[]).map((item) =>
          finalizeCompatItem(item)
        ) as TranscriptTurn['items'],
        outcome: { kind: status },
      } satisfies TranscriptTurn;
      batch(() => {
        history.append([turn]);
        setLive({ activeTurn: null, turnStatus: status });
      });
    },
  };

  return {
    history,
    activeTurn: activeTurnApi,
    state,

    findItemById(id) {
      const committedItem = itemMap.get(id);
      if (committedItem) return committedItem;
      const at = live.activeTurn;
      if (at) {
        for (const item of at.items) {
          if (item.id === id) return item as ChatItem;
        }
      }
      return undefined;
    },

    reset() {
      batch(() => {
        setCommitted([]);
        setLive({ activeTurn: null, turnStatus: 'done' });
      });
      itemMap.clear();
    },
  };
}
