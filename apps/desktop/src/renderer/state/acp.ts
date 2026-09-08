import { create } from "zustand";

import { reduce } from "@shared/acp/reduce";
import { errorMessage } from "@shared/ipc/errors";
import type {
  PendingPermission,
  PromptBlock,
  SessionEvent,
  SessionState,
} from "@shared/acp/types";

/**
 * Live session state, one `SessionState` per connected session, mirrored
 * from main (plan §5).
 *
 * Main sends a full snapshot on `session.state` (connect, load) and then one
 * reducer event per `session.update`; this store runs the same pure reducer
 * on them, so both processes hold the same state without a second protocol.
 * Every mutation is an IPC call and never touches the state directly — the
 * event that follows is what updates it, exactly as a change made from
 * anywhere else would.
 *
 * `loading` and `loadErrors` are the renderer's own: they cover the gap
 * between selecting a session from the index and its snapshot arriving,
 * which is where the connecting and the reconnect-failed states live.
 *
 * That gap is a second or two of spawn, `initialize` and replay (README,
 * "Opening a session"), and `reconnecting` is what makes it invisible: a
 * session with no live connection is painted from the snapshot main filed
 * on disk and then reconnected behind the transcript, with `Reconnecting…`
 * in the composer's row instead of a spinner over the pane. While that flag
 * is up the reducer events are dropped — they are the agent replaying a
 * history the snapshot already shows, and folding them onto it would double
 * every turn — and the authoritative state that ends every `load` replaces
 * the picture.
 */
type AcpState = {
  sessions: Record<string, SessionState>;
  /** The most recent chunk per agent-created terminal, keyed `sessionId/terminalId`. */
  terminalOutput: Record<string, string>;
  /** Sessions whose `load` is in flight. */
  loading: Record<string, true>;
  /**
   * Sessions being loaded *behind a painted state* — a snapshot, or the
   * state of a connection that has since been closed. Their reducer events
   * are dropped until the load answers.
   */
  reconnecting: Record<string, true>;
  /** The last `load` failure per session, cleared by the next attempt. */
  loadErrors: Record<string, string>;

  receiveState: (sessionId: string, state: SessionState) => void;
  receiveEvent: (sessionId: string, event: SessionEvent) => void;
  receiveTerminalOutput: (sessionId: string, terminalId: string, data: string) => void;
  forget: (sessionId: string) => void;

  create: (input: {
    projectId: string;
    agentId: string;
    cwd?: string;
    gitMode: "none" | "checkout" | "worktree";
    branch?: string;
  }) => Promise<string>;
  load: (sessionId: string) => Promise<void>;
  /**
   * What a click on a session row costs: nothing when its adapter is still
   * alive, a paint from the stored snapshot plus a background `load` when it
   * is not, and the spinner only for a session that has neither.
   */
  ensureLoaded: (sessionId: string) => Promise<void>;
  prompt: (sessionId: string, content: PromptBlock[] | string) => Promise<string>;
  cancel: (sessionId: string) => Promise<void>;
  setMode: (sessionId: string, modeId: string) => Promise<void>;
  setConfigOption: (sessionId: string, configId: string, value: string | boolean) => Promise<void>;
  respondPermission: (sessionId: string, requestId: string, optionId: string | null) => Promise<void>;
  close: (sessionId: string) => Promise<void>;
};

const TERMINAL_TAIL = 64 * 1024;

export const useAcp = create<AcpState>((set, get) => ({
  sessions: {},
  terminalOutput: {},
  loading: {},
  reconnecting: {},
  loadErrors: {},

  receiveState: (sessionId, state) =>
    set((current) => ({ sessions: { ...current.sessions, [sessionId]: state } })),

  receiveEvent: (sessionId, event) =>
    set((current) => {
      const state = current.sessions[sessionId];
      // Events for a session we have no snapshot of are dropped: the
      // snapshot that follows a connect carries everything up to that point.
      if (!state) {
        return current;
      }
      // A session painted from disk while its agent reconnects: what arrives
      // now is that agent replaying the history already on screen, and the
      // state at the end of the load is what replaces it.
      if (current.reconnecting[sessionId]) {
        return current;
      }
      return { sessions: { ...current.sessions, [sessionId]: reduce(state, event) } };
    }),

  receiveTerminalOutput: (sessionId, terminalId, data) =>
    set((current) => {
      const key = `${sessionId}/${terminalId}`;
      const next = ((current.terminalOutput[key] ?? "") + data).slice(-TERMINAL_TAIL);
      return { terminalOutput: { ...current.terminalOutput, [key]: next } };
    }),

  forget: (sessionId) =>
    set((current) => {
      const sessions = { ...current.sessions };
      delete sessions[sessionId];
      const loadErrors = { ...current.loadErrors };
      delete loadErrors[sessionId];
      const reconnecting = { ...current.reconnecting };
      delete reconnecting[sessionId];
      return { sessions, loadErrors, reconnecting };
    }),

  create: async (input) => {
    const session = await window.hardcore.sessions.create(input);
    return session.id;
  },

  load: async (sessionId) => {
    set((current) => {
      const loadErrors = { ...current.loadErrors };
      delete loadErrors[sessionId];
      return {
        loading: { ...current.loading, [sessionId]: true },
        // A load with something already on screen is a reconnect: the events
        // it produces are a replay of that, and are dropped.
        ...(current.sessions[sessionId] ? { reconnecting: { ...current.reconnecting, [sessionId]: true as const } } : {}),
        loadErrors,
      };
    });
    try {
      const state = await window.hardcore.sessions.load({ id: sessionId });
      get().receiveState(sessionId, state);
    } catch (error) {
      set((current) => ({ loadErrors: { ...current.loadErrors, [sessionId]: errorMessage(error) } }));
    } finally {
      set((current) => {
        const loading = { ...current.loading };
        delete loading[sessionId];
        const reconnecting = { ...current.reconnecting };
        delete reconnecting[sessionId];
        return { loading, reconnecting };
      });
    }
  },

  ensureLoaded: async (sessionId) => {
    const { sessions, loading } = get();
    if (loading[sessionId]) {
      return;
    }
    const held = sessions[sessionId];
    // A connection that is still up: this is a paint and nothing else.
    // `closed` is the adapter the keep-alive evicted (src/main/acp/live.ts)
    // or one that was disconnected by hand — the transcript is still right,
    // and the agent behind it has to come back.
    if (held && held.status !== "closed") {
      return;
    }
    if (!held) {
      // The snapshot main filed for this session, if it has one: painted
      // before the load starts, so the transcript is on screen in a frame
      // rather than in two seconds. `live: true` means main's connection
      // outlived the renderer's copy of it and there is nothing to reconnect.
      try {
        const painted = await window.hardcore.sessions.state({ id: sessionId });
        // A load that started while this was in flight owns the session now.
        if (painted && !get().sessions[sessionId] && !get().loading[sessionId]) {
          get().receiveState(sessionId, painted.state);
          if (painted.live) {
            return;
          }
        }
      } catch {
        /* no snapshot: the spinner, as before */
      }
    }
    await get().load(sessionId);
  },

  prompt: async (sessionId, content) => {
    const blocks: PromptBlock[] =
      typeof content === "string" ? [{ type: "text", text: content }] : content;
    const { stopReason } = await window.hardcore.sessions.prompt({ id: sessionId, content: blocks });
    return stopReason;
  },

  cancel: (sessionId) => window.hardcore.sessions.cancel({ id: sessionId }),

  setMode: (sessionId, modeId) => window.hardcore.sessions.setMode({ id: sessionId, modeId }),

  setConfigOption: (sessionId, configId, value) =>
    window.hardcore.sessions.setConfigOption({ id: sessionId, configId, value }),

  respondPermission: (sessionId, requestId, optionId) =>
    window.hardcore.sessions.respondPermission({ id: sessionId, requestId, optionId }),

  close: async (sessionId) => {
    await window.hardcore.sessions.close({ id: sessionId });
    get().forget(sessionId);
  },
}));

/** One session's live state, or null before it connects. */
export function useSessionState(sessionId: string | null): SessionState | null {
  return useAcp((state) => (sessionId ? (state.sessions[sessionId] ?? null) : null));
}

/** The permission request the user has to answer next, if any. */
export function usePendingPermission(sessionId: string | null): PendingPermission | null {
  return useAcp((state) =>
    sessionId ? (state.sessions[sessionId]?.pendingPermissions[0] ?? null) : null,
  );
}
