import { create } from "zustand";

import { useSessions } from "./sessions";

import { allToolCalls, reduce } from "@shared/acp/reduce";
import { errorMessage } from "@shared/ipc/errors";
import { withoutKey } from "@renderer/lib/record";
import type {
  PendingPermission,
  PromptBlock,
  SessionEvent,
  SessionState,
} from "@shared/acp/types";

/**
 * A prompt main refused before any turn began — it holds a block the agent did not say it takes
 * (`refused` on the `sessions.prompt` reply). Nothing was written and nothing failed: the message
 * is the reason, for the composer to say beside the draft it keeps.
 */
export class PromptRefused extends Error {
  override readonly name = "PromptRefused";
}

type AcpState = {
  sessions: Record<string, SessionState>;
  /** The most recent chunk per agent-created terminal, keyed `sessionId/terminalId`. */
  terminalOutput: Record<string, string>;
  /**
   * Terminals already in a state when this store took it (a snapshot, a reload, a background
   * session's reconnect) whose chunks it never saw, keyed like `terminalOutput`. A command with
   * no output held is silent when it ran here and unknown when it is in this set.
   */
  coldTerminals: Record<string, true>;
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
  /**
   * What main said went wrong after `session/new` answered (`session.status.error` beside a live
   * status, `settleAfterFailedCreate`): the session started and is promptable, so this is a note
   * above the composer, not a screen in place of the transcript. Cleared by the next `load` and
   * when the session is forgotten.
   */
  setupNotes: Record<string, string>;

  receiveSetupNote: (sessionId: string, note: string) => void;
  receiveState: (sessionId: string, state: SessionState) => void;
  receiveEvent: (sessionId: string, event: SessionEvent) => void;
  receiveTerminalOutput: (sessionId: string, terminalId: string, data: string, silent?: boolean) => void;
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
  /**
   * The setup note's retry: main runs the setup again on the live session and answers with the
   * new note or null. Not a `load` — that would only re-broadcast a live connection's state.
   */
  retrySetup: (sessionId: string) => Promise<void>;
};

const TERMINAL_TAIL = 64 * 1024;

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
export const useAcp = create<AcpState>((set, get) => ({
  sessions: {},
  terminalOutput: {},
  coldTerminals: {},
  loading: {},
  reconnecting: {},
  loadErrors: {},
  setupNotes: {},

  receiveSetupNote: (sessionId, note) =>
    set((current) => ({ setupNotes: { ...current.setupNotes, [sessionId]: note } })),

  receiveState: (sessionId, state) =>
    set((current) => {
      // Main broadcasts `session.state` at the end of a load, ahead of the load's reply — and a
      // Disconnect (or a forget) that landed since the load began has already made that reply
      // for nobody. Taking the broadcast would paint the pane connected again.
      const load = loadsInFlight.get(sessionId);
      if (load && load.asked !== generationOf(sessionId)) return current;
      let coldTerminals = current.coldTerminals;
      for (const call of allToolCalls(state)) {
        for (const content of call.content) {
          const key = content.type === "terminal" ? `${sessionId}/${content.terminalId}` : null;
          if (key && !(key in current.terminalOutput) && !(key in coldTerminals)) {
            coldTerminals = { ...coldTerminals, [key]: true };
          }
        }
      }
      // A state that says the agent is up is a reconnect that worked, by hand or on its own
      // (`ensureLive` in main): the "Reconnect failed" line above the box is over. Left, it
      // outlived the recovery and sat above a working session until a prompt was refused.
      const up = state.status === "idle" || state.status === "running" || state.status === "waiting";
      const loadErrors = up ? withoutKey(current.loadErrors, sessionId) : current.loadErrors;
      return { sessions: { ...current.sessions, [sessionId]: state }, coldTerminals, loadErrors };
    }),

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
      const next = reduce(state, event);
      // An adapter that closed behind another session's pane — the keep-alive evicting it — is
      // let go: its transcript is the snapshot main flushed, and a click repaints it from there.
      if (next.status === "closed" && !stillWanted(sessionId, current)) {
        return without(current, sessionId);
      }
      return { sessions: { ...current.sessions, [sessionId]: next } };
    }),

  receiveTerminalOutput: (sessionId, terminalId, data, silent) =>
    set((current) => {
      // A session the store let go of (Disconnect, delete, archive) or never
      // held: its terminals' chunks are not kept, or `without` would have
      // nothing to sweep them with.
      if (!current.sessions[sessionId]) {
        return current;
      }
      const key = `${sessionId}/${terminalId}`;
      const next = ((current.terminalOutput[key] ?? "") + data).slice(-TERMINAL_TAIL);
      // A command that exited having written nothing, seen to exit here: silent, not unknown, even
      // when a state landed while it ran and marked it cold.
      if (silent && key in current.coldTerminals) {
        return { terminalOutput: { ...current.terminalOutput, [key]: next }, coldTerminals: withoutKey(current.coldTerminals, key) };
      }
      return { terminalOutput: { ...current.terminalOutput, [key]: next } };
    }),

  forget: (sessionId) => set((current) => without(current, sessionId)),

  create: async (input) => {
    const session = await window.textToCad.sessions.create(input);
    useSessions.getState().adopt(session);
    return session.id;
  },

  load: async (sessionId) => {
    set((current) => {
      const loadErrors = { ...current.loadErrors };
      delete loadErrors[sessionId];
      const setupNotes = withoutKey(current.setupNotes, sessionId);
      return {
        setupNotes,
        loading: { ...current.loading, [sessionId]: true },
        // A load with something already on screen is a reconnect: the events
        // it produces are a replay of that, and are dropped.
        ...(current.sessions[sessionId] ? { reconnecting: { ...current.reconnecting, [sessionId]: true as const } } : {}),
        loadErrors,
      };
    });
    const asked = generationOf(sessionId);
    const flight = { asked };
    loadsInFlight.set(sessionId, flight);
    try {
      const state = await window.textToCad.sessions.load({ id: sessionId });
      // Forgotten while it loaded — archived, deleted, disconnected: the answer is for nobody.
      if (generationOf(sessionId) === asked) get().receiveState(sessionId, state);
    } catch (error) {
      if (generationOf(sessionId) === asked) {
        set((current) => ({ loadErrors: { ...current.loadErrors, [sessionId]: errorMessage(error) } }));
      }
    } finally {
      if (loadsInFlight.get(sessionId) === flight) loadsInFlight.delete(sessionId);
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
      const asked = generationOf(sessionId);
      try {
        const painted = await window.textToCad.sessions.state({ id: sessionId });
        if (generationOf(sessionId) !== asked) {
          return;
        }
        // A load that started while this was in flight owns the session now.
        if (get().loading[sessionId]) {
          return;
        }
        const current = get().sessions[sessionId];
        if (painted && !current) {
          get().receiveState(sessionId, painted.state);
        }
        // Main's connection is live: what is held — painted here, or by the `session.state`
        // main broadcast while this was in flight (a session just created) — is current, and
        // there is nothing to reconnect. A `load` here would mark the session `reconnecting`,
        // which drops every turn event until its reply, then repaint from a snapshot older
        // than the turn sent in the meantime: that prompt would never appear.
        if (painted?.live && current?.status !== "closed") {
          return;
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
    const { stopReason, refused } = await window.textToCad.sessions.prompt({ id: sessionId, content: blocks });
    if (refused !== undefined) {
      throw new PromptRefused(refused);
    }
    return stopReason;
  },

  cancel: (sessionId) => window.textToCad.sessions.cancel({ id: sessionId }),

  setMode: (sessionId, modeId) => window.textToCad.sessions.setMode({ id: sessionId, modeId }),

  setConfigOption: (sessionId, configId, value) =>
    window.textToCad.sessions.setConfigOption({ id: sessionId, configId, value }),

  respondPermission: (sessionId, requestId, optionId) =>
    window.textToCad.sessions.respondPermission({ id: sessionId, requestId, optionId }),

  close: async (sessionId) => {
    // Counted as a forget without the forgetting: a Reconnect still loading is for nobody now, and
    // its answer — a ready state, or the failure the close causes — would paint over "closed".
    forgotten.set(sessionId, generationOf(sessionId) + 1);
    await window.textToCad.sessions.close({ id: sessionId });
    // Kept, marked closed: the turns and the plan stay on screen under the Reconnect bar, the way
    // `ensureLoaded` expects a hand-disconnected session to be held. Leaving it lets it go.
    // And the setup note goes: the setup is moot once the adapter is gone, and the note's own
    // Reconnect would sit beside the bar's.
    set((current) => {
      const setupNotes = withoutKey(current.setupNotes, sessionId);
      const held = current.sessions[sessionId];
      if (!held || held.status === "closed") return setupNotes === current.setupNotes ? current : { setupNotes };
      const closed = reduce(held, { type: "status", status: "closed", error: null, at: Date.now() });
      return { sessions: { ...current.sessions, [sessionId]: closed }, setupNotes };
    });
  },

  retrySetup: async (sessionId) => {
    const asked = generationOf(sessionId);
    let note: string | null;
    try {
      note = (await window.textToCad.sessions.retrySetup({ id: sessionId })).error;
    } catch (error) {
      note = errorMessage(error);
    }
    // Forgotten or disconnected meanwhile: the setup is moot, and so is its answer.
    if (generationOf(sessionId) !== asked) return;
    set((current) => ({
      setupNotes: note === null ? withoutKey(current.setupNotes, sessionId) : { ...current.setupNotes, [sessionId]: note },
    }));
  },
}));

/**
 * How many times each session has been forgotten, or disconnected. An IPC answer that arrives
 * after a forget — the row archived or deleted while its snapshot or its load was on the way — is
 * dropped rather than bringing back state nothing will forget again; one that arrives after a
 * Disconnect is dropped rather than undoing it.
 */
const forgotten = new Map<string, number>();
const generationOf = (sessionId: string) => forgotten.get(sessionId) ?? 0;

/** The generation each in-flight `load` began under, so a state main broadcasts for it can be judged the same way its reply is. */
const loadsInFlight = new Map<string, { asked: number }>();

/** Everything held for one session, taken out: its state, its load's leftovers, its terminals' tails. */
function without(current: AcpState, sessionId: string): Partial<AcpState> {
  forgotten.set(sessionId, generationOf(sessionId) + 1);
  const sessions = { ...current.sessions };
  delete sessions[sessionId];
  const loadErrors = { ...current.loadErrors };
  delete loadErrors[sessionId];
  const reconnecting = { ...current.reconnecting };
  delete reconnecting[sessionId];
  const setupNotes = withoutKey(current.setupNotes, sessionId);
  const prefix = `${sessionId}/`;
  const terminalOutput = Object.fromEntries(Object.entries(current.terminalOutput).filter(([key]) => !key.startsWith(prefix)));
  const coldTerminals = Object.fromEntries(Object.entries(current.coldTerminals).filter(([key]) => !key.startsWith(prefix)));
  return { sessions, loadErrors, setupNotes, reconnecting, terminalOutput, coldTerminals };
}

/** Whether a closed session's state is still wanted: it is on screen, or a load is bringing it back. */
function stillWanted(sessionId: string, current: AcpState): boolean {
  return useSessions.getState().activeId === sessionId || Boolean(current.loading[sessionId]);
}

/**
 * The index decides what is kept here. A row deleted, or newly archived, takes its state and its
 * terminals' output with it — nothing else ever would, and each holds images, diffs and 64 KB per
 * terminal. A closed session the person has just left goes too: `ensureLoaded` repaints it from
 * the snapshot main keeps (flushed when the adapter closed) the next time it is picked, which is
 * one read of a row rather than a transcript held for every session ever opened.
 */
useSessions.subscribe((index, previous) => {
  const acp = useAcp.getState();
  const rows = new Map(index.sessions.map((row) => [row.id, row]));
  for (const row of previous.sessions) {
    const now = rows.get(row.id);
    if (!now || (now.archived && !row.archived)) acp.forget(row.id);
  }
  const left = previous.activeId;
  if (left && left !== index.activeId) {
    const held = useAcp.getState();
    if (held.sessions[left]?.status === "closed" && !stillWanted(left, held)) acp.forget(left);
  }
});

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
