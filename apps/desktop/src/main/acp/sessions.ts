/**
 * The session index and the live connections behind it (plan §5).
 *
 * The agent owns the transcript; sqlite keeps the row the sidebar lists
 * (`sessions` table). `SessionManager` maps a row to at most one
 * `SessionConnection`, creates rows, resumes them with `session/load`, and
 * forwards every event to the renderer through `broadcast`. A connection
 * that dies stays in the index with `status: error`; the next `load` spawns a
 * fresh adapter and loads the transcript back, and so does the next `prompt`
 * — except for an archived row with no live connection, which `prompt`
 * refuses ("This thread is archived; unarchive it first.") after awaiting an
 * in-flight create.
 *
 * Opening a session used to be that whole sequence with a spinner over it —
 * two and a half seconds for Claude Code, one for Codex, measured by the
 * timing line `load` logs (`./timing.ts`). Three things stand between a
 * click and a transcript now, and each is its own small module:
 *
 *   - `./snapshots.ts`  the last state, on disk, painted immediately
 *   - `./live.ts`       the adapters of the last few sessions, still running
 *   - `./warm.ts`       one idle adapter per agent, spawned in advance
 *
 * Dependencies are injected so this file has no Electron import of its own:
 * main wires it to the sqlite repository, node-pty and the IPC broadcaster.
 */
import { existsSync } from "node:fs";
import nodePath from "node:path";

import type { McpServer } from "@agentclientprotocol/sdk";

import { effortOption, modeChoice, modelOption, preferredMode } from "../../shared/acp/options";
import { diffCounts } from "../../shared/diff-counts";
import type {
  ConfigOption,
  PromptBlock,
  SessionEvent,
  SessionMode,
  SessionState,
} from "../../shared/acp/types";
import type { IpcEventChannel, IpcEventPayload } from "../../shared/ipc";
import { DELETED_WHILE_STARTING } from "../../shared/ipc/errors";
import type { Launch } from "../../shared/agents";
import type { GitMode, Session, SessionStatus } from "../../shared/types";
import type { Event as TelemetryEvent } from "../telemetry";
import { startTimer } from "../timer";
import { PROBE_WAIT_MS, type AgentDetector } from "../agents/detect";
import { agentProvider } from "../agents/registry";
import { adapterOptionsKey, SessionConnection, type SessionConnectionOptions } from "./connection";
import { LiveConnections } from "./live";
import { SessionSnapshotWriter, type SnapshotStore } from "./snapshots";
import type { SpawnTerminal } from "./terminals";
import { createTimer, loadTimer } from "./timing";
import { WarmAdapterPool } from "./warm";

export { diffCounts };

export interface SessionRepository {
  list(projectId?: string): Session[];
  get(id: string): Session | null;
  upsert(session: Session): Session;
  remove(id: string): void;
}

/** What a git mode resolves to (P7, `src/main/projects/workspace.ts`). */
export type SessionWorkspace = {
  cwd: string;
  branch?: string | undefined;
  worktreePath?: string | undefined;
};

export type SessionManagerDeps = {
  repo: SessionRepository;
  detector: AgentDetector;
  spawnTerminal: SpawnTerminal;
  broadcast: <C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) => void;
  /**
   * The MCP servers a session gets: text-to-cad's seven domain servers
   * (`text-to-cad-<integration>`), minted per session by `mcpServersFor` in
   * src/main/integrations/index.ts. A probe (`probeOptions`) is minted one too, and revokes
   * it when it is done: the adapter is spawned exactly as a real session's
   * would be, or the options it reports are not the options it would have.
   */
  mcpServers?: (session: Pick<Session, "id" | "projectId" | "cwd">) => McpServer[];
  /** Called when a probe's connection is closed, so its bridge token can be revoked. */
  forgetProbe?: (probeId: string) => void;

  /**
   * P5: the skills every session gets (src/main/integrations/skills.ts). `root` is
   * named in `session/new` and `session/load` as an additional directory;
   * `preamble` is the text an agent that ignores those gets in front of its
   * first prompt, and is asked for per agent (`skillRoots` in the registry).
   * Injected, so this file knows nothing about where the skills live.
   */
  skills?: {
    root: () => string | null;
    preamble: () => string | null;
  };

  /**
   * P5: the directories the bundled CAD runtime puts in front of a session's
   * `PATH` — where its `cadgen` and its `python` are. Every adapter, and so
   * every command a session runs, is spawned with them
   * (`CadRuntime.sessionPath`).
   */
  runtimePath?: () => string[];

  /**
   * P2: what the agents' sessions can be configured with, kept between
   * sessions (`./agent-options.ts`). Injected: this file applies the stored
   * defaults on create and writes back what it sees, and knows nothing about
   * where they are stored.
   */
  agentOptions?: {
    defaults(agentId: string): { model: string | null; mode: string | null };
    /**
     * The effort remembered for one of this agent's models — asked after the
     * model has landed, because the levels are the model's (`options.ts`).
     */
    effortFor(agentId: string, model: string | null): string | null;
    remember(agentId: string, options: ConfigOption[], modes: SessionMode[]): void;
    rememberChoice(
      agentId: string,
      configId: string,
      value: string | boolean,
      options: ConfigOption[],
    ): void;
    /** The mode a session was switched into, as the next session's default. */
    rememberMode(agentId: string, modeId: string): void;
  };
  clientVersion?: string;
  newId: () => string;
  /**
   * Replace a provider's launch line. The e2e suite points every agent at
   * `tests/fake-agent`; nothing else sets this.
   */
  launchOverride?: (agentId: string) => Launch | null;

  /**
   * P7: the git mode as a directory (plan §9). Injected rather than imported
   * so this file still knows nothing about settings, projects or git — it
   * takes a directory and runs an agent in it.
   *
   * It runs *before* the row is written. A `worktree` mode that cannot be
   * satisfied — a project that is not a repository — should leave no thread
   * behind for the person to wonder about, so its message is thrown out of
   * `create` instead of being stored as a failed session.
   */
  workspace?: (input: {
    projectId: string;
    gitMode: GitMode;
    /** The first prompt, when the caller has one: the worktree's slug. */
    name?: string | undefined;
    /** An explicit directory — Settings' `New session in this worktree`. */
    cwd?: string | undefined;
  }) => Promise<SessionWorkspace>;

  /**
   * P7: told once the workspace `workspace` answered is recorded on a session
   * row — or abandoned by a create that failed. Until then a new worktree
   * belongs to no session, and main keeps the keep-limit sweep off it.
   */
  workspaceSettled?: (workspace: SessionWorkspace) => void;

  /**
   * P7: the commit a directory is at. Recorded when the session is created and
   * again when each turn starts, which is what the review's `This session` and
   * `Last turn` scopes are measured from.
   */
  head?: (cwd: string) => Promise<string | null>;

  /**
   * P7: the working tree as a tree object, pinned under `mark`
   * (`<session id>/turn`). When present it is the turn mark — and the session
   * mark outside a worktree — because `head` is where the last commit was,
   * not where the work stood: until a commit lands, a range from HEAD is
   * everything. Null falls back to `head`.
   */
  snapshot?: (cwd: string, mark: string) => Promise<string | null>;

  /** P7: unpin a session's snapshot marks when it is deleted. */
  dropMarks?: (cwd: string, sessionId: string) => Promise<void>;

  /**
   * P7: the empty tree's id when `cwd` is a repository with no commits, else
   * null. Asked only after `head` answered null, and it must prove the
   * repository unborn — `head`'s null also means "git failed".
   */
  emptyTree?: (cwd: string) => Promise<string | null>;

  /**
   * P7: remove the session's worktree on delete, if the settings allow it.
   * Answers whether it did and, when it kept one, why — which is logged.
   *
   * `abandoned` is a create that failed after its worktree was made: nobody
   * has worked in it and no session will ever open it, so it goes whatever
   * the setting says — otherwise every failed sign-in leaves `slug`,
   * `slug-2`, … and their branches behind.
   */
  releaseWorkspace?: (
    session: Session,
    options?: { abandoned?: boolean },
  ) => Promise<{ removed: boolean; reason?: string } | void>;

  /**
   * Where the painted-on-select snapshot of each session's transcript is
   * kept (`./snapshots.ts`; sqlite's `session_state` in the app). Without
   * one — the unit tests — a session with no live connection is the spinner
   * it always was.
   */
  snapshots?: SnapshotStore;

  /**
   * How many adapters stay alive behind the sessions that are not on screen
   * (`KEEP_ALIVE_LIMIT` in `./live.ts`). A constant rather than a setting:
   * it is a number about this machine's memory, not a preference, and four
   * covers "the two or three threads I am switching between" with room to
   * spare.
   */
  keepAlive?: number;

  /**
   * P8: anonymous usage events (`../telemetry.ts`). Injected for the same
   * reason as everything else here; the only thing this file reports is
   * that a session was created, and with which agent.
   */
  track?: (event: TelemetryEvent) => void;

  /**
   * Start a timer that calls `fire` after `ms`; returns its cancel. The clock
   * for the archive's wait on a create, injected so a test fires it by hand.
   */
  startTimer?: (ms: number, fire: () => void) => () => void;
};

/** A provisional title until the agent supplies one, trimmed to fit a sidebar row. */
export function titleFromPrompt(content: PromptBlock[], max = 60): string {
  const text = content.find((block) => block.type === "text");
  const line = (text?.type === "text" ? text.text : "")
    .split("\n")
    .map((candidate) => candidate.trim())
    .find(Boolean);
  if (!line) {
    return content[0]?.type === "image" ? "Image" : "New session";
  }
  const collapsed = line.replace(/\s+/g, " ");
  return collapsed.length > max ? `${collapsed.slice(0, max - 1).trimEnd()}…` : collapsed;
}

/**
 * `baseFiles`: files counted before this app run, when a reload replayed no
 * diffs — their paths are not known, so a later edit to one of them counts
 * it again. The row's `changedFiles` is `baseFiles + files.size`.
 */
type ChangeTally = { files: Set<string>; baseFiles: number; insertions: number; deletions: number };

/** How long a turn (or a create) waits for the working tree to be snapshotted. */
const MARK_WAIT_MS = 5_000;
const EXPIRED = Symbol("mark wait expired");

/** A turn in flight, or a connection on its way up: neither evicted nor left standing at startup. */
const ACTIVE: ReadonlySet<SessionStatus> = new Set(["running", "waiting", "connecting"]);

/** How long an archive waits for a create still running before it abandons that create. */
const ARCHIVE_WAIT_MS = 10_000;

/** How long a config-option probe may take before it is abandoned. */
const PROBE_TIMEOUT_MS = 60_000;

function rejectAfter(ms: number, agentId: string): Promise<never> {
  return new Promise((_resolve, reject) => {
    setTimeout(() => reject(new Error(`${agentId} did not answer session/new in ${ms}ms`)), ms).unref?.();
  });
}

export class SessionManager {
  /**
   * The adapters still running, most recently used last. Selecting another
   * session does not close the one before it (`./live.ts`); the oldest
   * beyond the limit is closed, and its row goes to `closed` so the next
   * click reconnects it.
   */
  private readonly live: LiveConnections<SessionConnection>;
  private readonly tallies = new Map<string, ChangeTally>();
  /** The `load` in flight per session, so two callers wait on one spawn. */
  private readonly loads = new Map<string, Promise<SessionState>>();
  /**
   * The connections a `prompt` is between `ensureLive` and the end of its
   * turn. The turn mark waits on git, and until `session/prompt` is sent the
   * connection is `idle`, which `busy` alone would let a second session's
   * `create` or `load` evict from under the prompt.
   */
  private readonly held = new Set<SessionConnection>();
  /**
   * The `create` still spawning per session, settled when it succeeds or fails.
   * The row is in the index (and in the sidebar) from before `session/new`, so
   * a click on it — or a prompt — arrives while the row has no agent session
   * id yet, and `load` waits here rather than say it never connected.
   */
  private readonly creating = new Map<string, Promise<void>>();
  /** An agent may announce its title before session/new tells us its session id. */
  private readonly pendingTitles = new Map<string, Map<string, string>>();
  private readonly snapshots: SessionSnapshotWriter | null;
  private readonly warm: WarmAdapterPool<SessionConnection>;

  constructor(private readonly deps: SessionManagerDeps) {
    this.live = new LiveConnections({
      ...(deps.keepAlive === undefined ? {} : { limit: deps.keepAlive }),
      // A turn in flight is never evicted: the work and the reason for it
      // would both be lost, and the limit comes back down when it ends. Nor
      // is one still connecting — in `session/new` or `session/load`: closing
      // it rejects the load, and a prompt waiting on that load in
      // `ensureLive` with it. Nor one whose prompt is on its way out — idle
      // until the turn mark is taken and `session/prompt` is sent (`held`).
      busy: (connection) =>
        this.held.has(connection) || ACTIVE.has(connection.state.status),
      onEvict: (sessionId) => {
        console.info(`[acp] ${sessionId.slice(0, 8)} was closed to keep the adapter count at the limit`);
        // The snapshot, now: the adapter is gone and a click on that row has
        // only the picture to paint (`./snapshots.ts`).
        this.snapshots?.flush(sessionId);
        this.announceClosed(sessionId);
        if (this.deps.repo.get(sessionId)) {
          this.setStatus(sessionId, "closed");
        }
      },
    });
    this.snapshots = deps.snapshots ? new SessionSnapshotWriter({ store: deps.snapshots }) : null;
    this.warm = new WarmAdapterPool({
      spawn: (agentId, cwd) => this.spawnWarm(agentId, cwd),
      log: (line) => console.info(line),
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Index                                                                    */
  /* ---------------------------------------------------------------------- */

  list(projectId?: string): Session[] {
    this.boot();
    return this.deps.repo.list(projectId);
  }

  get(id: string): Session | null {
    this.boot();
    return this.deps.repo.get(id);
  }

  /**
   * Once, before the index is first read: a row left `running`, `waiting` or
   * `connecting` names an adapter that died with the last app run (a crash or
   * a force-quit skips `closeAll`). Nothing can be live before this manager
   * has spawned something, so those rows become `closed` — otherwise a
   * "needs you" glyph outlives the agent that needed you. Lazy rather than in
   * the constructor, which runs before the database is open; `updatedAt` is
   * kept so the sidebar's order does not change.
   *
   * A row with no agent session id is a `create` that never reached
   * `session/new`'s answer — the app quit mid-spawn, and `create`'s cleanup
   * cannot run once the database is closed. It can never be loaded, so it is
   * removed rather than left in the sidebar as a "New session" nobody made,
   * and the worktree it cut (`worktreeOwned`) is released with it.
   */
  private booted = false;
  private boot(): void {
    if (this.booted) {
      return;
    }
    this.booted = true;
    for (const session of this.deps.repo.list()) {
      if (!session.acpSessionId && !this.creating.has(session.id)) {
        this.deps.repo.remove(session.id);
        void this.unpinMarks(session);
        // The worktree the dead create cut goes with it; one it was handed was
        // there before and stays.
        if (session.worktreeOwned && session.worktreePath) {
          void Promise.resolve(this.deps.releaseWorkspace?.(session, { abandoned: true })).catch(() => undefined);
        }
        continue;
      }
      if (ACTIVE.has(session.status) && !this.live.get(session.id)?.alive) {
        this.deps.repo.upsert({ ...session, status: "closed" });
      }
    }
  }

  /**
   * What to draw for this session right now, and whether it is the truth.
   *
   * `live: true` is the state of a connected adapter and needs nothing else.
   * `live: false` is the stored snapshot (`./snapshots.ts`) — the renderer
   * paints it at once, says "Reconnecting…" in the composer's row, and
   * replaces it with what `load` answers. Null is a session with neither: it
   * gets the spinner, the way every session did before migration 10.
   */
  state(id: string): { state: SessionState; live: boolean } | null {
    this.boot();
    const connection = this.live.get(id);
    // `acpSessionId`, not merely `alive`: a connection that is spawned but
    // has not answered `session/new` holds an empty state, and the snapshot is
    // a better picture than that. A `loadSession` dispatches `session/connected`
    // first, so a replaying connection is `live: true` here — `connecting`, with
    // the transcript replayed so far. The renderer that started the load drops
    // that connection's events until the load's own state lands (`reconnecting`
    // in `state/acp.ts`); one that reloaded mid-load paints this state from
    // `ensureLoaded` and reduces the replay's events as they come, which the
    // load's final `session.state` then replaces.
    if (connection?.alive && connection.acpSessionId) {
      // A create still in its preferences and marks: the reducer says idle from
      // `session/new`, but the row says `connecting` until `create` returns,
      // and the composer follows the row (the model chip would be overwritten
      // by `applyPreferences`). The end of `create` broadcasts the real state.
      if (this.creating.has(id) && connection.state.status === "idle") {
        return { state: { ...connection.state, status: "connecting" }, live: true };
      }
      return { state: connection.state, live: true };
    }
    const stored = this.snapshots?.read(id) ?? null;
    return stored ? { state: stored, live: false } : null;
  }

  /* ---------------------------------------------------------------------- */
  /* Lifecycle                                                                */
  /* ---------------------------------------------------------------------- */

  /**
   * A new thread.
   *
   * The working directory is resolved from `gitMode` first (plan §9) and only
   * then is anything written: a worktree that cannot be created is an error
   * with a sentence in it, not a session row pointing at a directory that does
   * not exist.
   */
  async create(input: {
    projectId: string;
    agentId: string;
    gitMode: GitMode;
    /** Used when there is no workspace resolver — the tests, and `none` mode. */
    cwd?: string;
    /** The first prompt, when the caller has one: the worktree's slug. */
    name?: string | undefined;
    branch?: string;
  }): Promise<Session> {
    this.boot();
    if (!agentProvider(input.agentId)) {
      throw new Error(`unknown agent: ${input.agentId}`);
    }

    const workspace = await this.workspaceFor(input);
    const id = this.deps.newId();
    // A worktree this create cut is clean, so its start is a commit, and that
    // commit is also the base its branch is deleted against
    // (`releaseWorkspace`). A checkout can hold anything already, and so can a
    // worktree the caller named (`New session in this worktree`, which sends
    // `cwd`), so the start of those is the tree as it is.
    const fresh = input.gitMode === "worktree" && !input.cwd;
    // Started now and settled after `session/new`: the marks are of the tree
    // before the first prompt, which cannot go out until this create has
    // returned, so they overlap the spawn rather than delay it.
    const owner = { id, projectId: input.projectId, cwd: workspace.cwd };
    const marks: Promise<[string | null, string | null]> = fresh
      ? Promise.all([this.headOf(workspace.cwd), this.markWithin(owner, "turn")])
      : this.markWithin(owner, "session").then((head) => [head, head]);
    const now = Date.now();
    const session: Session = {
      id,
      projectId: input.projectId,
      agentId: input.agentId,
      cwd: workspace.cwd,
      gitMode: input.gitMode,
      branch: workspace.branch ?? input.branch,
      ...(workspace.worktreePath ? { worktreePath: workspace.worktreePath } : {}),
      // Recorded for `boot`, which cannot tell a worktree this create cut from
      // one it was handed.
      ...(workspace.worktreePath && fresh ? { worktreeOwned: true } : {}),
      title: "New session",
      titleSource: "prompt",
      createdAt: now,
      updatedAt: now,
      status: "connecting",
      acpSessionId: null,
      changedFiles: 0,
      insertions: 0,
      deletions: 0,
      archived: false,
      pinned: false,
      // Both scopes start at `marks`, filled in below once they have landed.
      // `turnHead` is the session's mark until the first turn moves it, so a
      // review taken before any prompt shows what the person changed by hand
      // rather than nothing at all.
      sessionHead: null,
      turnHead: null,
    };
    try {
      this.deps.repo.upsert(session);
    } finally {
      this.deps.workspaceSettled?.(workspace);
    }
    let created!: () => void;
    this.creating.set(id, new Promise<void>((resolve) => (created = resolve)));
    // The connection this create is still setting up, in `held` from `connect`
    // until it returns: idle through the preferences and the marks (up to five
    // seconds), it is not `busy` to the keep-alive limit, and another create or
    // load past the limit would close it under this one.
    let setup: SessionConnection | undefined;
    try {
      this.broadcastIndex();

      const timer = createTimer();
      let warmed = false;
      let connection: SessionConnection;
      try {
        connection = await this.connect(session, {
          onWarm: () => {
            warmed = true;
          },
        });
        timer.mark("spawn");
        this.held.add(connection);
        setup = connection;
        await connection.initialize();
        timer.mark("initialize");
        await connection.newSession();
        timer.mark("session/new");
        // On its own, before the preferences and the marks: the row is what
        // `boot` purges when it has no agent session id, and a crash while
        // the marks are pending must not take a connected session with it.
        this.update(session.id, { acpSessionId: connection.acpSessionId });
        console.info(
          `[acp] create ${session.id.slice(0, 8)} ${session.agentId} warm=${warmed ? "yes" : "no"} ${timer.format()}`,
        );
      } catch (error) {
        // A row with no agent session id can never be loaded; the renderer
        // shows the failure (sign in, install) and the user creates again.
        // Unless the person deleted it: that is not a failure to show.
        const deleted = !this.deps.repo.get(session.id);
        await this.abandonCreate(session, input, workspace, marks);
        throw deleted ? new Error(DELETED_WHILE_STARTING) : error;
      }
      // What the person last chose for this agent — the model, the effort and
      // the mode. Never a reason for the session to fail: a refused
      // `set_config_option` leaves the session at the agent's own defaults,
      // which is a working session.
      try {
        await this.applyPreferences(session, connection);
        const [sessionHead, turnHead] = await marks;
        // Only a row still `connecting` goes idle. A `close` during the
        // preferences or the marks has set `closed` over a retired connection,
        // and writing `idle` back would draw a live composer on a dead one.
        const stillConnecting = this.deps.repo.get(session.id)?.status === "connecting";
        const updated = this.update(
          session.id,
          stillConnecting ? { status: "idle", sessionHead, turnHead } : { sessionHead, turnHead },
        );
        if (stillConnecting) {
          this.deps.broadcast("session.state", { sessionId: session.id, state: connection.state });
        }
        // The registry id and nothing else — no directory, project or prompt.
        this.deps.track?.({ name: "session_created", agent: session.agentId });
        return updated;
      } catch (error) {
        // A throw between `session/new` and the row going idle (the store
        // refusing `remember`, say). One contract: a `create` that reached
        // `session/new` and still has its connection RESOLVES with the session,
        // so the renderer adopts the row and offers no second create; the
        // failure is logged and told to the index as a note. One whose
        // connection is gone rejects and leaves no row, as a failure before
        // `session/new` does — its agent session was never used, so a Retry that
        // loaded it would have nothing to resume ("this session never
        // connected; create it again").
        const row = this.deps.repo.get(session.id);
        if (row && row.status !== "connecting") return row; // closed under this create: that state stands
        if (!row || !connection.alive) {
          await this.abandonCreate(session, input, workspace, marks);
          // A row gone under the create is a delete, not a failure to show.
          throw row ? error : new Error(DELETED_WHILE_STARTING);
        }
        console.warn(`[acp] create ${session.id.slice(0, 8)} finished with a warning: ${String(error)}`);
        try {
          return await this.settleAfterFailedCreate(session, connection, marks, error);
        } catch (settleError) {
          // The store refused the settle too (the same SQLITE_BUSY, persistent). Nothing may stay
          // `connecting` with a live connection and no owner: retire it and take the row.
          console.warn(`[acp] create ${session.id.slice(0, 8)} could not settle: ${String(settleError)}`);
          await this.abandonCreate(session, input, workspace, marks);
          throw error;
        }
      }
    } finally {
      if (setup) this.held.delete(setup);
      this.creating.delete(id);
      created();
    }
  }

  /**
   * A `create` that will not produce a session: the connection, the row, and
   * the worktree this create cut all go. Not a worktree it was given
   * (`New session in this worktree` sends `cwd`): that directory was there before.
   */
  private async abandonCreate(
    session: Session,
    input: { cwd?: string },
    workspace: { worktreePath?: string | undefined },
    marks: Promise<[string | null, string | null]>,
  ): Promise<void> {
    this.retire(session.id);
    this.pendingTitles.delete(session.id);
    this.deps.repo.remove(session.id);
    this.broadcastIndex();
    // The marks may still be landing: unpin them once they have, and take
    // the branch's base from the session mark (`releaseWorkspace`).
    const [startHead] = await marks.catch(() => [null, null] as const);
    await this.unpinMarks(session);
    if (workspace.worktreePath && !input.cwd) {
      await this.deps.releaseWorkspace?.({ ...session, sessionHead: startHead }, { abandoned: true }).catch(() => undefined);
    }
  }

  /**
   * The row a `create` that failed after `session/new` leaves, its connection
   * alive: idle, so the composer opens, with what went wrong as a note on the
   * index (`session.status` carries `error` beside a live status).
   */
  private async settleAfterFailedCreate(
    session: Session,
    connection: SessionConnection,
    marks: Promise<[string | null, string | null]>,
    cause: unknown,
  ): Promise<Session> {
    const [sessionHead, turnHead] = await marks.catch(() => [null, null] as const);
    const row = this.update(session.id, { status: "idle", sessionHead, turnHead });
    this.deps.broadcast("session.state", { sessionId: session.id, state: connection.state });
    this.deps.broadcast("session.status", {
      sessionId: session.id,
      status: "idle",
      error: `The session started, but setting it up failed: ${cause instanceof Error ? cause.message : String(cause)}`,
    });
    return row;
  }

  /**
   * Run the setup again on a live, idle session that `settleAfterFailedCreate` left with a note:
   * the same `applyPreferences` a create runs. Resolves with the new note, or null when it went
   * through (the renderer drops its held note on null); a failure is also re-broadcast as the
   * note. It is the only way to retry: `load` on a live connection re-broadcasts its state and
   * returns, so it would retry nothing.
   */
  async retrySetup(id: string): Promise<{ error: string | null }> {
    const connection = this.requireLive(id);
    const session = this.require(id);
    if (session.status !== "idle") {
      throw new Error("The session is busy; set it up again when it is idle.");
    }
    try {
      await this.applyPreferences(session, connection);
    } catch (error) {
      const note = `Setting it up again failed: ${error instanceof Error ? error.message : String(error)}`;
      this.setStatus(id, "idle", note);
      return { error: note };
    }
    this.deps.broadcast("session.state", { sessionId: id, state: connection.state });
    return { error: null };
  }

  /**
   * The model, then the effort, then the mode — in that order, and the order
   * matters twice over: switching model is what changes which effort levels
   * the agent offers, *and* which effort was remembered. An effort read or
   * set first would be the outgoing model's.
   *
   * Every step is best-effort. An adapter that refuses one of them logs and
   * the session goes on — including a refused model, after which the effort
   * is read against the model the session is actually on rather than the one
   * that was wanted.
   */
  private async applyPreferences(session: Session, connection: SessionConnection): Promise<void> {
    const defaults = this.deps.agentOptions?.defaults(session.agentId) ?? { model: null, mode: null };
    await this.applyConfigOption(connection, modelOption(connection.state.configOptions), defaults.model);
    const model = modelOption(connection.state.configOptions)?.currentValue ?? null;
    const effort = this.deps.agentOptions?.effortFor(session.agentId, model) ?? null;
    await this.applyConfigOption(connection, effortOption(connection.state.configOptions), effort);
    await this.applyMode(connection, defaults.mode, session.agentId);
    this.deps.agentOptions?.remember(
      session.agentId,
      connection.state.configOptions,
      connection.state.modes,
    );
  }

  private async applyConfigOption(
    connection: SessionConnection,
    option: ReturnType<typeof modelOption>,
    value: string | null,
  ): Promise<void> {
    if (!option || !value || option.currentValue === value) {
      return;
    }
    // A model the agent no longer offers — an upgrade dropped it, or the
    // default was stored against a different account. Leave the agent's own.
    if (!option.options.some((candidate) => candidate.value === value)) {
      return;
    }
    try {
      await connection.setConfigOption(option.id, value);
    } catch (error) {
      console.warn(`[acp] ${option.id}=${value} was refused: ${String(error)}`);
    }
  }

  /**
   * The mode the person left this agent in — the composer's one permission
   * control, on both screens — and, until they have chosen one, whatever the
   * provider calls its own auto-approval preset (`_meta.kind: auto_review`)
   * rather than the adapter's most cautious default.
   *
   * Whichever of the two shapes the agent sends its modes in is where the
   * answer goes: `session/set_mode`, or the `mode` config option
   * (`shared/acp/options`).
   */
  private async applyMode(connection: SessionConnection, preferred: string | null, agentId: string): Promise<void> {
    try {
      const choice = modeChoice(connection.state);
      if (!choice) {
        return;
      }
      const wanted = preferredMode(agentId, choice.modes, preferred);
      if (!wanted || wanted === choice.currentModeId) {
        return;
      }
      if (choice.source === "modes") {
        await connection.setMode(wanted);
      } else if (choice.configId) {
        await connection.setConfigOption(choice.configId, wanted);
      }
    } catch (error) {
      console.warn(`[acp] the session's mode was refused: ${String(error)}`);
    }
  }

  /**
   * Whether `probeOptions` would run for this agent at all: its CLI is on
   * this machine, or a launch override makes every provider the same test
   * process. `launchWithoutBinary` is not enough — it says the adapter can
   * run without the CLI, which a session the person asked for may use, not
   * that a speculative probe should fetch it (see `probeOptions`).
   *
   * "Not installed" is a verdict only from this launch's probe: a warm launch's first table is
   * the last launch's, and a CLI installed since is on this machine now. A row that says absent
   * waits for the fresh table, with the bound `connect` uses, before it refuses.
   */
  async canProbe(agentId: string): Promise<boolean> {
    const provider = agentProvider(agentId);
    if (!provider) {
      return false;
    }
    if (this.deps.launchOverride?.(provider.id)) {
      return true;
    }
    const held = this.deps.detector.list().find((candidate) => candidate.id === provider.id);
    if (held?.installed === true) {
      return true;
    }
    const fresh = await this.deps.detector.freshWithin(PROBE_WAIT_MS);
    return (fresh ?? this.deps.detector.list()).find((candidate) => candidate.id === provider.id)?.installed === true;
  }

  /**
   * What one `session/new` with this agent would offer, without keeping the
   * session: the adapter is spawned exactly as a real session's is — the same
   * environment, the same MCP servers, the project's own directory — asked
   * for a session, read, and killed. Nothing is prompted and no row is
   * written.
   *
   * This is what the new-session screen's model, effort and mode chips are
   * drawn from before anything has run — the modes as well as the config
   * options, because Claude's modes arrive in the same `session/new` reply
   * and nothing else says which they are. An agent that is not installed or
   * not signed in throws here, and the caller's answer to that is silence.
   */
  async probeOptions(input: {
    agentId: string;
    cwd: string;
    projectId: string | null;
  }): Promise<{ configOptions: ConfigOption[]; modes: SessionMode[] }> {
    const provider = agentProvider(input.agentId);
    if (!provider) {
      throw new Error(`unknown agent: ${input.agentId}`);
    }
    const launch = this.deps.launchOverride?.(provider.id) ?? null;
    // Stricter than `connect`, on purpose. A session is something a person
    // asked for and is worth an `npx -y` download; a probe is speculative,
    // and eight `launchWithoutBinary` providers fetching their adapters on a
    // first run — each to be told it is signed out — is a download storm
    // nobody asked for. So: the CLI is on this machine, or nothing. (With a
    // launch override in force every provider is the same test process, and
    // the machine's PATH says nothing about it.)
    if (!(await this.canProbe(provider.id))) {
      throw new Error(`${provider.name} is not installed`);
    }
    if (!existsSync(input.cwd)) {
      throw new Error(`${input.cwd} does not exist`);
    }
    const probeId = `probe:${input.agentId}:${this.deps.newId()}`;
    const connection = new SessionConnection({
      sessionId: probeId,
      agentId: input.agentId,
      launch: launch ?? provider.launch,
      env: await this.environment(),
      cwd: input.cwd,
      mcpServers:
        this.deps.mcpServers?.({ id: probeId, projectId: input.projectId ?? "", cwd: input.cwd }) ?? [],
      skillsRoot: this.deps.skills?.root() ?? null,
      spawnTerminal: this.deps.spawnTerminal,
      clientVersion: this.deps.clientVersion,
      onStderr: () => undefined,
    });
    try {
      // An adapter that has to be fetched before it can answer (`npx -y …`)
      // is slow but finite; one that never answers must not leave a process
      // behind for the rest of the app's life.
      await Promise.race([connection.newSession(), rejectAfter(PROBE_TIMEOUT_MS, input.agentId)]);
      return { configOptions: connection.state.configOptions, modes: connection.state.modes };
    } finally {
      connection.close();
      this.deps.forgetProbe?.(probeId);
    }
  }

  /**
   * Resume: spawn and `session/load`. A live connection is returned as is —
   * which, with the keep-alive set (`./live.ts`), is what switching back to
   * a session you were just in costs: nothing.
   *
   * The phases are timed and logged once per load, because they are the
   * whole reason this file has three caches in it and because they are not
   * the same shape for the two adapters (README, "Opening a session").
   */
  async load(id: string): Promise<SessionState> {
    this.boot();
    const creation = this.creating.get(id);
    if (creation) {
      return creation.then(() => this.load(id));
    }
    // One load per session at a time. The renderer starts one behind the
    // painted snapshot, and a prompt typed into that snapshot's composer
    // arrives while it is still running — two spawns for one session, and a
    // `session/prompt` sent into the middle of a `session/load`.
    const inflight = this.loads.get(id);
    if (inflight) {
      return inflight;
    }
    const existing = this.live.get(id);
    if (existing?.alive && existing.acpSessionId) {
      this.live.touch(id);
      this.deps.broadcast("session.state", { sessionId: id, state: existing.state });
      return existing.state;
    }
    const work: Promise<SessionState> = this.loadNow(id).finally(() => {
      // Its own entry only: a close drops an abandoned load's, and the load a Reconnect then
      // started is not this one's to delete.
      if (this.loads.get(id) === work) this.loads.delete(id);
    });
    this.loads.set(id, work);
    return work;
  }

  /**
   * How many times each session was closed by a person. A load that began before one is for
   * nobody: a close that lands while `connect` is still reading the shell environment finds no
   * connection to retire, and the load would go on to make the row `idle` again — or `error`, if
   * the close is what made it fail.
   */
  private readonly disconnects = new Map<string, number>();

  /**
   * A load that failed: the row goes to `error`. A failure the connection
   * already put on `session.update` (an agent that answered session/load with
   * an error, an adapter that died) has been heard; one that never reached it
   * — a `connect` that threw, no loadSession capability, an `initialize` that
   * threw — is said here, where the renderer listens, so the state it holds
   * does not keep the old status.
   */
  private failLoad(id: string, message: string, alreadyReported = false) {
    this.setStatus(id, "error", message);
    if (!alreadyReported && !this.shuttingDown) {
      this.deps.broadcast("session.update", {
        sessionId: id,
        event: { type: "status", status: "error", error: message, at: Date.now() },
      });
    }
  }

  private async loadNow(id: string): Promise<SessionState> {
    const session = this.require(id);
    const disconnectsAtStart = this.disconnects.get(id) ?? 0;
    const overtaken = () => (this.disconnects.get(id) ?? 0) !== disconnectsAtStart;
    // What the connection this replaces last said, written now: a reload that
    // fails `discard`s the pending write below, and the dead connection's
    // final state (a crashed turn's, queued 750 ms out) is the only copy of it.
    this.snapshots?.flush(id);
    if (!session.acpSessionId) {
      throw new Error("this session never connected; create it again");
    }
    const timer = loadTimer();
    let warmed = false;
    // Held by reference and cleared below: after the load, every update of
    // this session's life would otherwise go through a mark nobody reads.
    const replay: { onReplayUpdate?: () => void } = {
      onReplayUpdate: () => timer.mark("firstUpdate"),
    };
    // A `connect` that throws after it quietly retired the old connection (the shell env probe,
    // the spawn) has left the renderer with its last status and the row `connecting`: said here,
    // the same way a failed `initialize` is.
    let connection: SessionConnection;
    try {
      connection = await this.connect(session, {
        overtaken,
        onWarm: () => {
          warmed = true;
        },
        replay,
      });
    } catch (error) {
      if (overtaken()) throw error;
      this.failLoad(id, error instanceof Error ? error.message : String(error));
      throw error;
    }
    if (overtaken()) return this.abandon(id, connection);
    timer.mark("spawn");
    // session/load replays the whole history, edits included, through
    // `tallyUpdate`: start the count again rather than add a second copy of
    // it to what an earlier load (or turn) in this app run counted.
    this.tallies.delete(id);
    try {
      await connection.initialize();
      timer.mark("initialize");
      // The agent's title, which the replay does not send again: the last
      // state's, or the row's when the agent is who named it.
      const stored = this.snapshots?.read(id) ?? null;
      const title = stored?.title ?? (session.titleSource === "agent" ? session.title : null);
      // The preamble went out with the first prompt: an agent turn with more
      // in it than an error says that prompt was read, whatever the replay
      // brings back (`loadSession`).
      const answered =
        stored?.turns.some((turn) => turn.role === "agent" && turn.parts.some((part) => part.type !== "error")) ?? false;
      await connection.loadSession(session.acpSessionId, title, answered);
      // An adapter that replays no diffs leaves nothing counted, and the
      // next persistTally would overwrite the row with one turn's edits:
      // the persisted counts are then the history to add to.
      // Unless a delete (or another retire) took the session meanwhile: a
      // tally made now would be one nothing ever forgets.
      const persisted = this.deps.repo.get(id);
      if (!this.tallies.has(id) && persisted && this.live.get(id) === connection) {
        this.tallies.set(id, {
          files: new Set(),
          baseFiles: persisted.changedFiles ?? 0,
          insertions: persisted.insertions ?? 0,
          deletions: persisted.deletions ?? 0,
        });
      }
    } catch (error) {
      // Out of the live set before it is closed: its `closed` is then a
      // detached connection's and dropped (`onEvent`), and the row keeps
      // the error.
      const reported = connection.state.status === "error";
      // Closed by the person mid-load: the failure is the close's, and the row keeps `closed`.
      const closed = overtaken();
      if (this.live.get(id) === connection) this.live.delete(id);
      connection.close();
      // The error state has no transcript (the reload never replayed one), and
      // its pending write would put that over the stored one 750 ms later —
      // the previous snapshot is the only copy of the session's history.
      this.snapshots?.discard(id);
      if (closed) throw error;
      this.failLoad(id, error instanceof Error ? error.message : String(error), reported);
      throw error;
    } finally {
      replay.onReplayUpdate = undefined;
    }
    if (overtaken()) return this.abandon(id, connection);
    timer.mark("replay");
    console.info(
      `[acp] load ${id.slice(0, 8)} ${session.agentId} warm=${warmed ? "yes" : "no"} ${timer.format()}`,
    );
    this.update(id, { status: "idle" });
    this.deps.broadcast("session.state", { sessionId: id, state: connection.state });
    return connection.state;
  }

  /** A load a person's close overtook: its connection goes, and nothing is written over the `closed` row or broadcast over the pane. */
  private abandon(id: string, connection: SessionConnection): never {
    if (this.live.get(id) === connection) this.live.delete(id);
    connection.close();
    throw new Error("the session was disconnected while it loaded");
  }

  /**
   * Have an adapter ready for the agents the index says are in use, before
   * anyone clicks anything (`./warm.ts`).
   *
   * One per agent, in the directory of that agent's most recent session —
   * which is the project for every mode but `worktree`, and a worktree
   * thread spawns its own (an adapter cannot be moved between directories).
   * An agent that is not installed or not signed in is skipped: there is
   * nothing to spawn and a download storm is not a pre-warm.
   */
  async warmAgents(): Promise<void> {
    const statuses = this.deps.detector.list();
    const wanted = new Map<string, string>();
    for (const session of this.deps.repo.list()) {
      if (session.archived || wanted.has(session.agentId) || !existsSync(session.cwd)) {
        continue;
      }
      const provider = agentProvider(session.agentId);
      if (!provider) {
        continue;
      }
      const status = statuses.find((candidate) => candidate.id === session.agentId);
      // The same rule `connect` applies, and no stricter: an adapter fetched
      // by `npx -y` is usable with nothing on the PATH, and this agent has a
      // session in the index, so it has already run here once. A provider
      // `connect` would refuse, or one the person is signed out of, is
      // skipped — warming it would buy an error message in advance.
      if (!provider.launchWithoutBinary && status && !status.installed) {
        continue;
      }
      if (status?.auth === "unauthenticated") {
        continue;
      }
      wanted.set(session.agentId, session.cwd);
    }
    await Promise.all([...wanted].map(([agentId, cwd]) => this.warm.warm(agentId, cwd)));
  }

  /** Whether an idle adapter is waiting for this agent (the tests, and the timing log). */
  warmed(agentId: string): boolean {
    return this.warm.has(agentId);
  }

  async prompt(id: string, content: PromptBlock[]): Promise<{ stopReason: string; refused?: string }> {
    this.require(id);
    // An archive that landed during a create closed the connection once the
    // create settled, and the first prompt (`NewSession` sends it as the
    // create returns) would reconnect the archived row and run a turn in a
    // thread the person put away. Wait the create out, then look.
    await this.creating.get(id)?.catch(() => undefined);
    const session = this.require(id);
    // Only a row with nothing live is refused: an archived transcript the
    // person opened and Reconnected is theirs to continue, and it has a
    // connection. What `prompt` must not do is be the reconnect.
    if (session.archived && !this.live.get(id)?.alive) {
      throw new Error("This thread is archived; unarchive it first.");
    }
    const connection = await this.ensureLive(session);
    // A block the agent did not say it takes (`promptCapabilities`) is
    // refused before anything moves — the turn mark, the title, the
    // transcript. An answer rather than a rejection: nothing failed, and the
    // renderer keeps the draft and says why beside it.
    const refused = connection.refusal(content);
    if (refused) {
      return { stopReason: "refused", refused };
    }
    this.held.add(connection);
    try {
      // The session being prompted is the one in use: it goes to the front of
      // the keep-alive queue and is never what an eviction closes.
      this.live.touch(id);
      // Re-read after reconnect: session/load may have supplied the agent's
      // title while ensureLive was in flight.
      const current = this.require(id);
      if (current.titleSource === "prompt" && current.title === "New session") {
        this.update(id, { title: titleFromPrompt(content), titleSource: "prompt" });
      }
      // The turn's starting point, read before the agent can move it. This is
      // what the review's `Last turn` scope diffs against; taking it afterwards
      // would measure the turn against its own result. A snapshot that takes
      // too long keeps the previous mark: a wider `Last turn` is still a
      // review, where a null would unmark it altogether.
      const turnHead = await this.markWithin(session, "turn", current.turnHead);
      // Deleted while the snapshot ran: `delete` unpinned before this mark
      // was pinned, and nothing else would ever drop the ref it just made.
      if (!this.deps.repo.get(id)) {
        await this.unpinMarks(session);
        throw new Error(`no such session: ${id}`);
      }
      this.update(id, turnHead === null ? {} : { turnHead });
      try {
        const response = await connection.prompt(content, `${id}:${Date.now()}`);
        this.persistTally(id);
        return { stopReason: response.stopReason };
      } catch (error) {
        // A turn cut short by `close` (or an eviction, or a reconnect) is not
        // activity in the session: its counts are kept, its row does not move.
        this.persistTally(id, { touch: this.live.get(id) === connection });
        throw error;
      }
    } finally {
      this.held.delete(connection);
    }
  }

  async cancel(id: string): Promise<void> {
    await this.live.get(id)?.cancel();
  }

  /**
   * Switch the session's mode, and make it this agent's default: the next
   * thread starts where the last one was left, the way the model and the
   * effort do.
   */
  async setMode(id: string, modeId: string): Promise<void> {
    await this.requireLive(id).setMode(modeId);
    const session = this.deps.repo.get(id);
    if (session) {
      this.deps.agentOptions?.rememberMode(session.agentId, modeId);
    }
  }

  async setConfigOption(id: string, configId: string, value: string | boolean): Promise<void> {
    const connection = this.requireLive(id);
    const before = connection.state.configOptions;
    await connection.setConfigOption(configId, value);
    // The model or the effort changed here is what the next session with this
    // agent starts as — a thread ends the way the last one was left, rather
    // than back at the adapter's default. Matched against the options as they
    // were *before* the call, because a model switch rewrites the effort list.
    const session = this.deps.repo.get(id);
    if (!session) {
      return;
    }
    this.deps.agentOptions?.rememberChoice(session.agentId, configId, value, before);
    // A model switched mid-thread brings its own remembered effort with it,
    // the way a new session would: the adapter resets the level to the new
    // model's default, and the person's last choice for that model is the
    // higher authority. Only when there is one, and only when it differs.
    if (modelOption(before)?.id === configId && typeof value === "string") {
      const wanted = this.deps.agentOptions?.effortFor(session.agentId, value) ?? null;
      const effort = effortOption(connection.state.configOptions);
      if (wanted && effort && effort.currentValue !== wanted && effort.options.some((option) => option.value === wanted)) {
        try {
          await connection.setConfigOption(effort.id, wanted);
        } catch (error) {
          console.warn(`[acp] the model's remembered effort was refused: ${String(error)}`);
        }
      }
    }
    this.deps.agentOptions?.remember(
      session.agentId,
      connection.state.configOptions,
      connection.state.modes,
    );
  }

  /**
   * Throws when nothing is waiting on `requestId` — answered already, or
   * asked by an adapter that has since gone — so the card can say so rather
   * than swallow the click.
   */
  respondPermission(id: string, requestId: string, optionId: string | null): void {
    if (!this.requireLive(id).respondPermission(requestId, optionId)) {
      throw new Error("This request has expired — reconnect and ask again.");
    }
  }

  rename(id: string, title: string): Session {
    this.require(id);
    return this.update(id, { title: title.trim(), titleSource: "user" });
  }

  /**
   * Hide the row from the sidebar. The adapter is closed; `load` still resumes it later.
   *
   * A row still being created is archived once its create has settled: `close`
   * under it would reject `session/new`, and `create` would then remove the row
   * and its worktree — an "archived" thread destroyed, and a create error shown
   * for it. The create runs to its end (the row goes idle), then this closes it.
   */
  async archive(id: string, archived: boolean): Promise<Session> {
    const session = this.require(id);
    if (archived) {
      const creation = this.creating.get(id);
      if (creation && !(await this.settlesWithin(creation, ARCHIVE_WAIT_MS))) {
        // A create that never answers (`initialize` and `session/new` have no
        // timeout of their own) would leave the sidebar's archive click dead.
        // Past the limit, the old way: close under it. `session/new` rejects,
        // `create` removes the row and its worktree and rejects to its caller,
        // so the thread is gone, not archived; this answers with the row as it
        // stood.
        console.warn(`[acp] archive ${id.slice(0, 8)}: create still running after ${ARCHIVE_WAIT_MS / 1000} s, abandoning it`);
        this.close(id);
        return this.deps.repo.get(id) ? this.update(id, { archived }) : { ...session, archived, status: "closed" };
      }
      // A create that failed took the row with it: there is nothing left to archive.
      this.require(id);
      this.close(id);
    }
    return this.update(id, { archived });
  }

  /** Whether `work` settled (either way) before `ms` passed. */
  private async settlesWithin(work: Promise<unknown>, ms: number): Promise<boolean> {
    let cancel = () => {};
    const expired = new Promise<false>((resolve) => {
      cancel = (this.deps.startTimer ?? startTimer)(ms, () => resolve(false));
    });
    try {
      return await Promise.race([work.then(() => true, () => true), expired]);
    } finally {
      cancel();
    }
  }

  /**
   * Pin or unpin. Written straight through `repo.upsert` rather than through
   * `update`, which stamps `updatedAt`: pinning a thread is not activity in
   * it, and a sidebar sorted by last activity must not jump when someone
   * pins the oldest row in the list.
   */
  setPinned(id: string, pinned: boolean): Session {
    const session = this.require(id);
    const next = this.deps.repo.upsert({ ...session, pinned });
    this.broadcastIndex();
    return next;
  }

  close(id: string): void {
    this.disconnects.set(id, (this.disconnects.get(id) ?? 0) + 1);
    // An abandoned load is for nobody: a Reconnect that joined it would inherit its refusal.
    this.loads.delete(id);
    this.retire(id);
    this.pendingTitles.delete(id);
    // The transcript as it stood, written now rather than in a second: the
    // adapter is gone and the next click has only the snapshot to paint.
    this.snapshots?.flush(id);
    if (this.deps.repo.get(id)) {
      this.setStatus(id, "closed");
    }
  }

  /**
   * Close and forget, and — when the settings say so and the worktree is
   * clean — take the worktree with it (plan §9).
   *
   * The row goes either way. A worktree that cannot be removed because there
   * is uncommitted work in it stays on disk and in Settings › Git &
   * Worktrees, which is where someone can look at it and decide; refusing to
   * delete the thread over it would leave a thread nobody wants and a
   * directory they cannot see.
   */
  async delete(
    id: string,
    options: {
      /**
       * Runs after the row is gone and before the worktree is released: the
       * terminals, browser targets and CAD viewer holding the session's
       * directory open (`src/main/ipc/acp.ts`). After the row, so a delete
       * that fails leaves the session whole; before the release, so nothing
       * outlives its directory. A throw here keeps the worktree on disk.
       */
      beforeRelease?: (session: Session | null) => void | Promise<void>;
    } = {},
  ): Promise<void> {
    const session = this.deps.repo.get(id);
    this.retire(id);
    this.pendingTitles.delete(id);
    this.tallies.delete(id);
    // The snapshot row goes with the session's own (ON DELETE CASCADE); this
    // cancels the pending write that would otherwise put it back.
    this.snapshots?.forget(id);
    this.deps.repo.remove(id);
    this.broadcastIndex();
    await options.beforeRelease?.(session);
    if (session) {
      // Before the worktree goes: the refs live in the repository it shares.
      await this.unpinMarks(session);
      const released = await this.deps.releaseWorkspace?.(session).catch((error: unknown) => ({
        removed: false,
        reason: error instanceof Error ? error.message : String(error),
      }));
      if (released && !released.removed && released.reason) {
        console.warn(`[acp] kept the worktree ${session.worktreePath ?? session.cwd} of deleted session ${id.slice(0, 8)}: ${released.reason}`);
      }
    }
  }

  /**
   * On quit: kill every adapter, the idle ones included, and file the
   * snapshots still waiting on their debounce — a session that was streaming
   * when the app was quit paints where it left off rather than where it was
   * a minute earlier.
   */
  closeAll(): void {
    // From here the database is about to close: an adapter's late event — the
    // in-flight prompt's rejection arriving as `prompt/error` after its
    // process was killed — must not write a status through it.
    this.shuttingDown = true;
    this.warm.closeAll();
    for (const id of this.live.keys()) {
      this.close(id);
    }
    this.snapshots?.flushAll();
  }

  /* ---------------------------------------------------------------------- */
  /* Internals                                                                */
  /* ---------------------------------------------------------------------- */

  /**
   * The directory a new session runs in.
   *
   * Without a resolver — the unit tests, and any caller that already knows
   * where it wants to run — the given `cwd` is taken as it is. Main always
   * installs one (`src/main/ipc/git.ts`), so in the app the mode decides.
   */
  private async workspaceFor(input: {
    projectId: string;
    gitMode: GitMode;
    cwd?: string;
    name?: string | undefined;
  }): Promise<SessionWorkspace> {
    if (this.deps.workspace) {
      return this.deps.workspace({
        projectId: input.projectId,
        gitMode: input.gitMode,
        name: input.name,
        cwd: input.cwd,
      });
    }
    if (!input.cwd) {
      throw new Error("a session needs a working directory");
    }
    return { cwd: input.cwd };
  }

  /** Unpin the snapshot marks a session took, in the project and in its own directory. */
  private async unpinMarks(session: Pick<Session, "id" | "projectId" | "cwd">): Promise<void> {
    for (const repository of new Set([session.projectId, session.cwd])) {
      await this.deps.dropMarks?.(repository, session.id).catch(() => undefined);
    }
  }

  /** The snapshots running, per mark: a second `git add -A` of the same tree waits for the first. */
  private readonly snapshotting = new Map<string, Promise<string | null>>();

  /**
   * The working tree as it stands, pinned under `<id>/<kind>`; null where no
   * snapshot can be taken (no `snapshot` dep, or git failed).
   *
   * One at a time per mark: a snapshot past `MARK_WAIT_MS` is still running
   * when the next turn asks for its own, and a second one would stack another
   * `add -A` on a tree that is already slow, and could land after the first
   * and re-point the ref away from the tree the newer mark stored. The second
   * asker takes the first's result.
   */
  private snapshotOf(cwd: string, mark: string): Promise<string | null> {
    if (!this.deps.snapshot) {
      return Promise.resolve(null);
    }
    const key = `${cwd}\0${mark}`;
    const running = this.snapshotting.get(key);
    if (running) {
      return running;
    }
    const flight: Promise<string | null> = this.deps.snapshot(cwd, mark)
      .catch(() => null)
      .finally(() => {
        if (this.snapshotting.get(key) === flight) this.snapshotting.delete(key);
      });
    this.snapshotting.set(key, flight);
    return flight;
  }

  /**
   * The working tree, as `snapshotOf` takes it, but only up to `MARK_WAIT_MS`:
   * a `git add` in a huge or locked tree can take a minute, and a turn — or a
   * new session — waits for its mark on the way out. Past the wait, or where no
   * snapshot can be taken, `fallback` stands in for the tree — the previous
   * mark where the caller has one (a wider `Last turn` than the turn, never a
   * different one), the commit where it has not.
   *
   * The late snapshot goes on running and pins its ref when it lands. A
   * session deleted (or a create that failed) in the meantime has already
   * unpinned its marks, so a result that finds no row unpins them again.
   */
  private async markWithin(
    owner: Pick<Session, "id" | "projectId" | "cwd">,
    kind: "turn" | "session",
    fallback?: string | null,
  ): Promise<string | null> {
    const flight = this.snapshotOf(owner.cwd, `${owner.id}/${kind}`);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const expired = new Promise<typeof EXPIRED>((resolve) => {
      timer = setTimeout(() => resolve(EXPIRED), MARK_WAIT_MS);
    });
    try {
      const tree = await Promise.race([flight, expired]);
      if (tree === EXPIRED) {
        console.warn(`[acp] mark fell back after ${MARK_WAIT_MS / 1000} s`);
        void flight.then(async (late) => {
          if (late !== null && !this.deps.repo.get(owner.id)) {
            await this.unpinMarks(owner);
          }
        });
        return fallback ?? (await this.headOf(owner.cwd));
      }
      // No snapshot to take (or git failed): the commit is what the tree is at.
      return tree ?? (await this.headOf(owner.cwd));
    } finally {
      clearTimeout(timer);
    }
  }

  /** The commit a directory is at, or null — never a reason to fail a turn. */
  private async headOf(cwd: string): Promise<string | null> {
    if (!this.deps.head) {
      return null;
    }
    const head = await this.deps.head(cwd).catch(() => null);
    // A repository with no commits yet has no HEAD, but it does have a
    // beginning: the empty tree. Marking that — rather than nothing — keeps
    // `This session` and `Last turn` a range once the first commit lands
    // mid-session (a null mark would read as "no mark recorded" by then).
    if (head !== null || !this.deps.emptyTree) {
      return head;
    }
    return this.deps.emptyTree(cwd).catch(() => null);
  }

  private require(id: string): Session {
    this.boot();
    const session = this.deps.repo.get(id);
    if (!session) {
      throw new Error(`no such session: ${id}`);
    }
    return session;
  }

  private requireLive(id: string): SessionConnection {
    const connection = this.live.get(id);
    if (!connection?.alive) {
      throw new Error("the session is not connected; load it first");
    }
    return connection;
  }

  /**
   * A live connection, reconnecting (and loading) after a crash or a close.
   *
   * A load already running is waited for rather than joined: the connection
   * exists from the moment it is spawned, and prompting one that is still
   * replaying its transcript would put a turn in the middle of a
   * `session/load`.
   */
  private async ensureLive(session: Session): Promise<SessionConnection> {
    // The connection of a create is live from `session/new`, but the create
    // has not written the row's marks yet: a turn run in that window has its
    // mark written over by the create's (and a crash in it leaves the row
    // unmarked). It goes out after the create has returned.
    await this.creating.get(session.id);
    const inflight = this.loads.get(session.id);
    if (inflight) {
      await inflight;
      return this.requireLive(session.id);
    }
    const existing = this.live.get(session.id);
    if (existing?.alive && existing.acpSessionId) {
      return existing;
    }
    await this.load(session.id);
    return this.requireLive(session.id);
  }

  /**
   * The environment an adapter is spawned with: the login shell's, with the
   * app's launcher directory (`cadgen`, `python3`, `python` — not the bundled
   * runtime's own bin, whose pip is off the PATH) in front of `PATH`. A
   * session's `cadgen` and `python` are then the app's own, whatever the
   * person's shell would have found — and nothing about it is installed on
   * the machine.
   */
  private async environment(): Promise<Record<string, string>> {
    const env = await this.deps.detector.environment();
    const dirs = this.deps.runtimePath?.() ?? [];
    if (dirs.length === 0) {
      return env;
    }
    // The PATH key's case varies on Windows; whichever one the shell gave us
    // is the one prepended to, so the value is never split in two.
    const key = Object.keys(env).find((name) => name.toUpperCase() === "PATH") ?? "PATH";
    const existing = env[key];
    const prefix = dirs.join(nodePath.delimiter);
    return { ...env, [key]: existing ? `${prefix}${nodePath.delimiter}${existing}` : prefix };
  }

  /**
   * The half of an adapter's options that is the same for every session of
   * one agent in one directory — which is exactly what makes a warm adapter
   * interchangeable (`./warm.ts`). Everything a session brings with it is in
   * `sessionOptions` below.
   */
  private async adapterOptions(
    agentId: string,
    cwd: string,
  ): Promise<
    Pick<
      SessionConnectionOptions,
      "agentId" | "launch" | "env" | "cwd" | "skillsRoot" | "spawnTerminal" | "clientVersion"
    >
  > {
    const provider = agentProvider(agentId);
    if (!provider) {
      throw new Error(`unknown agent: ${agentId}`);
    }
    return {
      agentId,
      launch: this.deps.launchOverride?.(provider.id) ?? provider.launch,
      env: await this.environment(),
      cwd,
      // The skills root, to every agent (plan §8, as revised).
      skillsRoot: this.deps.skills?.root() ?? null,
      spawnTerminal: this.deps.spawnTerminal,
      ...(this.deps.clientVersion === undefined ? {} : { clientVersion: this.deps.clientVersion }),
    };
  }

  /**
   * The half that is this session's: its id, the MCP server minted for it,
   * the preamble, and the four listeners its events have to arrive on. An
   * adopted warm adapter is given exactly this set
   * (`SessionConnection.adopt`).
   */
  private sessionOptions(
    session: Session,
    /** Held by reference: `loadNow` clears its hook when the replay is over. */
    replay: { onReplayUpdate?: () => void } = {},
    /** The connection these options end up on, set by `connect` once it exists. */
    owner: { connection?: SessionConnection } = {},
  ): Pick<
    SessionConnectionOptions,
    | "sessionId"
    | "mcpServers"
    | "preamble"
    | "onEvent"
    | "onTerminalOutput"
    | "onFilesChanged"
    | "onStderr"
  > {
    const provider = agentProvider(session.agentId);
    // Only the session's current connection speaks for it. One that was
    // closed, evicted or replaced still has things to say — the SDK rejects
    // its pending turn as `prompt/error`, `close` dispatches `closed`, late
    // writes would count into a tally and ask the explorer to re-read — and
    // none of it is about the row any more: whoever detached it has already
    // set the status it should have, and the row may already be deleted.
    const current = () => owner.connection !== undefined && this.live.get(session.id) === owner.connection;
    return {
      sessionId: session.id,
      mcpServers: this.deps.mcpServers?.(session) ?? [],
      // The preamble only to the agents that do not load the skills root
      // themselves (plan §8, as revised).
      preamble: provider?.skillRoots === "preamble" ? (this.deps.skills?.preamble() ?? null) : null,
      onEvent: (event) => {
        if (!current()) {
          return;
        }
        if (event.type === "session/update") {
          replay.onReplayUpdate?.();
        }
        this.onEvent(session.id, event);
      },
      onTerminalOutput: (terminalId, data, exit, silent) =>
        this.deps.broadcast("terminal.output", { sessionId: session.id, terminalId, data, exit, ...(silent ? { silent } : {}) }),
      onFilesChanged: (paths) => {
        if (!current()) {
          return;
        }
        const tally = this.tally(session.id);
        for (const file of paths) {
          tally.files.add(file);
        }
        // The explorer owns this event's shape (src/shared/ipc/explorer.ts): the
        // project and root the paths belong to — the session's worktree when
        // it has one, else the project directory, which is also its cwd —
        // and one root-relative change record per path.
        this.deps.broadcast("files.changed", {
          projectId: session.projectId,
          root: session.worktreePath ?? null,
          changes: paths.map((file) => ({
            path: nodePath.relative(session.cwd, file).split(nodePath.sep).join("/"),
            kind: "changed" as const,
            directory: false,
          })),
        });
      },
      onStderr: (line) => console.info(`[${session.agentId}:${session.id.slice(0, 8)}] ${line}`),
    };
  }

  /**
   * An adapter for this session: the warm one if the pool has it in the
   * right directory, else a fresh spawn. The caller calls `initialize`
   * itself (it is a no-op on an adopted adapter, which is the point) and
   * then `session/new` or `session/load`.
   */
  private async connect(
    session: Session,
    hooks: {
      onWarm?: () => void;
      replay?: { onReplayUpdate?: () => void };
      /** A person's close landed since the load began: nothing this call does may touch the session. */
      overtaken?: () => boolean;
    } = {},
  ): Promise<SessionConnection> {
    const stop = () => {
      if (hooks.overtaken?.()) throw new Error("the session was disconnected while it loaded");
    };
    const provider = agentProvider(session.agentId);
    if (!provider) {
      throw new Error(`unknown agent: ${session.agentId}`);
    }
    let status = this.deps.detector.list().find((candidate) => candidate.id === provider.id);
    // With a launch override in force every provider is the same test process
    // and the machine's PATH says nothing about it — the same reasoning the
    // options probe states above. Without this an agent whose adapter is a
    // binary rather than an `npx` package (gemini-cli, say) is unreachable on
    // any machine that has not installed it, fake agent or not.
    const overridden = Boolean(this.deps.launchOverride?.(provider.id));
    if (!overridden && !provider.launchWithoutBinary && status && !status.installed) {
      // "Not installed" is only a verdict from this launch's probe: the last launch's row may
      // predate an install, and a restored session auto-loads before the probe lands. Wait for
      // it; past the bound the spawn's own failure says what is missing.
      const fresh = await this.deps.detector.freshWithin(PROBE_WAIT_MS);
      status = fresh?.find((candidate) => candidate.id === provider.id);
      if (status && !status.installed) {
        throw new Error(`${provider.name} is not installed`);
      }
    }
    // A worktree removed from Settings, or from a terminal, while its thread
    // was closed. The adapter would fail to spawn with an ENOENT naming an
    // absolute path; this says what actually happened.
    if (!existsSync(session.cwd)) {
      const message =
        session.gitMode === "worktree"
          ? "This session's worktree has been deleted"
          : "This session's directory no longer exists";
      this.setStatus(session.id, "error", message);
      throw new Error(message);
    }
    // Before the old connection is retired and the row says `connecting`: an overtaken load's
    // connect is for nobody, and would write over the `closed` row or over the connection of the
    // load a Reconnect started since.
    stop();
    // Quietly: this is a reconnect, not a close. The renderer may not have
    // asked for it (a prompt into a crashed session reconnects on its own),
    // and a `closed` would show it Disconnected until `session/connected`.
    this.retire(session.id, { announce: false });
    this.setStatus(session.id, "connecting");

    const owner: { connection?: SessionConnection } = {};
    const sessionOptions = this.sessionOptions(session, hooks.replay ?? {}, owner);
    // Read before the pool is asked: a warm adapter is only this session's if
    // it was spawned with the options a fresh spawn would get now.
    const adapterOptions = await this.adapterOptions(session.agentId, session.cwd);
    // Deleted while the options were read: an adapter made live now would
    // belong to a row that is gone, and nothing would ever retire it.
    if (!this.deps.repo.get(session.id)) {
      throw new Error("this session was deleted");
    }
    stop();
    const warm = this.warm.take(session.agentId, session.cwd, adapterOptionsKey(adapterOptions));
    if (warm) {
      warm.adopt(sessionOptions);
      owner.connection = warm;
      hooks.onWarm?.();
      this.live.set(session.id, warm);
      return warm;
    }
    const connection = new SessionConnection({ ...adapterOptions, ...sessionOptions });
    owner.connection = connection;
    this.live.set(session.id, connection);
    return connection;
  }

  /**
   * One idle adapter, spawned and initialized, belonging to no session. The
   * pool's `spawn` (`./warm.ts`); the events it produces before it is
   * adopted go to the log and nowhere else, because there is no session for
   * them to belong to.
   */
  private async spawnWarm(agentId: string, cwd: string): Promise<SessionConnection> {
    const connection = new SessionConnection({
      ...(await this.adapterOptions(agentId, cwd)),
      sessionId: `warm:${agentId}`,
      onStderr: (line) => console.info(`[${agentId}:warm] ${line}`),
    });
    try {
      await connection.initialize();
    } catch (error) {
      connection.close();
      throw error;
    }
    return connection;
  }

  /**
   * Take a session's connection out of the live set and close it. Out first,
   * so `onEvent` drops what the closing connection says; the one thing of it
   * the renderer needs — that it is closed — is then said here, unless
   * `announce: false` (a reconnect replacing it, `connect`).
   */
  private retire(id: string, { announce = true }: { announce?: boolean } = {}): void {
    const connection = this.live.delete(id);
    if (!connection) {
      return;
    }
    // A connection still connecting has only the beginning of its own reload (the rule in
    // `onEvent`); one that was not is filed as `close` leaves it.
    const connecting = connection.state.status === "connecting";
    connection.close();
    if (announce) {
      // Its own `closed` event was dropped by the owner check above (it is out of `live`), so
      // `onEvent` never saw the state that ended the turn: without this the stored snapshot is
      // the last one before the close, an open turn with its calls running and its card
      // pending, and a repaint from it shows the session still streaming.
      if (!connecting && this.deps.repo.get(id)) {
        this.snapshots?.save(id, connection.state);
      }
      this.announceClosed(id);
    }
  }

  /**
   * `closed` on `session.update`, which is where the renderer hears it
   * (`session.status` feeds only the index): its next click on the row then
   * reconnects, and it lets go of what it held for the adapter.
   */
  private announceClosed(id: string): void {
    if (this.shuttingDown) {
      return;
    }
    this.deps.broadcast("session.update", {
      sessionId: id,
      event: { type: "status", status: "closed", error: null, at: Date.now() },
    });
  }

  /** Set by `closeAll` on quit; `onEvent` drops everything after it. */
  private shuttingDown = false;

  private onEvent(id: string, event: SessionEvent) {
    if (this.shuttingDown) {
      return;
    }
    this.deps.broadcast("session.update", { sessionId: id, event });
    // Every state main sees is a state the next click could paint from
    // (`./snapshots.ts`). Debounced there, so a streaming turn is one write
    // when it stops rather than one per token. Not while the connection is
    // still connecting — in `session/new`, or replaying `session/load`: its
    // transcript is the beginning of its own reload, and filed now (a quit, a
    // Disconnect) it would replace the whole one stored. `session/loaded`
    // ends the replay, and its state is the one worth keeping.
    const current = this.live.get(id)?.state;
    if (current && current.status !== "connecting" && this.deps.repo.get(id)) {
      this.snapshots?.save(id, current);
    }
    // Every time the agent tells us what a session can be configured with —
    // `session/new`, `session/load`, a `config_option_update` it sent on its
    // own — that becomes this agent's snapshot for the new-session screen.
    if (
      event.type === "session/connected" ||
      event.type === "config/updated" ||
      (event.type === "session/update" && event.update.sessionUpdate === "config_option_update")
    ) {
      const session = this.deps.repo.get(id);
      const state = this.live.get(id)?.state;
      if (session && state) {
        this.deps.agentOptions?.remember(session.agentId, state.configOptions, state.modes);
      }
    }
    switch (event.type) {
      case "session/connected": {
        const pending = this.pendingTitles.get(id)?.get(event.acpSessionId);
        this.pendingTitles.delete(id);
        if (pending) {
          this.setAgentTitle(id, pending);
        }
        break;
      }
      case "session/update":
        if (event.update.sessionUpdate === "session_info_update") {
          const title = typeof event.update.title === "string" ? event.update.title.trim() : "";
          if (title) {
            if (current?.acpSessionId === event.acpSessionId) {
              this.setAgentTitle(id, title);
            } else if (current && !current.acpSessionId && this.deps.repo.get(id)) {
              const pending = this.pendingTitles.get(id) ?? new Map<string, string>();
              pending.set(event.acpSessionId, title);
              this.pendingTitles.set(id, pending);
            }
          }
        }
        this.tallyUpdate(id, event.update as Record<string, unknown>);
        break;
      case "permission/request":
        this.setStatus(id, "waiting");
        this.deps.broadcast("session.permission", { sessionId: id, request: event.request });
        break;
      case "permission/resolve": {
        // Running when a turn is open; idle when the request came after the turn had closed and
        // there is no `prompt/end` still to come to say so.
        const status = this.live.get(id)?.state.status;
        if (status === "running" || status === "idle") {
          this.setStatus(id, status);
        }
        break;
      }
      case "prompt/start":
        this.setStatus(id, "running");
        break;
      case "prompt/end":
        this.setStatus(id, "idle");
        break;
      case "prompt/error":
        this.setStatus(id, "error", event.message);
        break;
      case "status":
        if (this.deps.repo.get(id)) {
          this.setStatus(id, event.status, event.error);
        }
        break;
      default:
        break;
    }
  }

  private setAgentTitle(id: string, title: string): void {
    const session = this.deps.repo.get(id);
    if (!session || session.titleSource === "user" || (session.title === title && session.titleSource === "agent")) {
      return;
    }
    // Updating the persisted index also broadcasts sessions.changed, so the
    // sidebar and session header follow the same title across restarts.
    this.update(id, { title, titleSource: "agent" });
  }

  private tally(id: string): ChangeTally {
    let tally = this.tallies.get(id);
    if (!tally) {
      tally = { files: new Set(), baseFiles: 0, insertions: 0, deletions: 0 };
      this.tallies.set(id, tally);
    }
    return tally;
  }

  /** Count the diffs an edit tool call reports. */
  private tallyUpdate(id: string, update: Record<string, unknown>) {
    if (update.sessionUpdate !== "tool_call" && update.sessionUpdate !== "tool_call_update") {
      return;
    }
    const content = Array.isArray(update.content) ? update.content : [];
    for (const item of content) {
      const entry = item as Record<string, unknown> | null;
      if (entry?.type !== "diff" || typeof entry.path !== "string") {
        continue;
      }
      const tally = this.tally(id);
      tally.files.add(entry.path);
      const { insertions, deletions } = diffCounts(
        typeof entry.oldText === "string" ? entry.oldText : "",
        typeof entry.newText === "string" ? entry.newText : "",
      );
      tally.insertions += insertions;
      tally.deletions += deletions;
    }
  }

  /** `touch: false` writes the counts without stamping `updatedAt` (see `setPinned`). */
  private persistTally(id: string, { touch = true }: { touch?: boolean } = {}) {
    // After `closeAll` the database is closing: a turn the quit killed
    // rejects into here, and must not read or write the row.
    const tally = this.shuttingDown ? undefined : this.tallies.get(id);
    const session = tally ? this.deps.repo.get(id) : null;
    if (!tally || !session) {
      return;
    }
    const counts = {
      changedFiles: tally.baseFiles + tally.files.size,
      insertions: tally.insertions,
      deletions: tally.deletions,
    };
    if (touch) {
      this.update(id, counts);
      return;
    }
    this.deps.repo.upsert({ ...session, ...counts });
    this.broadcastIndex();
  }

  private setStatus(id: string, status: SessionStatus, error: string | null = null) {
    const session = this.deps.repo.get(id);
    if (!session || session.status === status) {
      // Unchanged and with nothing to say: the index already says so, and a renderer that took the
      // repeat could not tell it from a note.
      if (session && error) {
        this.deps.broadcast("session.status", { sessionId: id, status, error });
      }
      return;
    }
    this.update(id, { status });
    this.deps.broadcast("session.status", { sessionId: id, status, error });
  }

  private update(id: string, patch: Partial<Session>): Session {
    const session = this.require(id);
    const next = this.deps.repo.upsert({ ...session, ...patch, updatedAt: Date.now() });
    this.broadcastIndex();
    return next;
  }

  private broadcastIndex() {
    this.deps.broadcast("sessions.changed", this.deps.repo.list());
  }
}
