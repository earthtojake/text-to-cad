/**
 * The session index and the live connections behind it (plan §5).
 *
 * The agent owns the transcript; sqlite keeps the row the sidebar lists
 * (`sessions` table). `SessionManager` maps a row to at most one
 * `SessionConnection`, creates rows, resumes them with `session/load`, and
 * forwards every event to the renderer through `broadcast`. A connection
 * that dies stays in the index with `status: error`; the next `prompt` or
 * `load` spawns a fresh adapter and loads the transcript back.
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
import type {
  ConfigOption,
  PromptBlock,
  SessionEvent,
  SessionMode,
  SessionState,
} from "../../shared/acp/types";
import type { IpcEventChannel, IpcEventPayload } from "../../shared/ipc";
import type { Launch } from "../../shared/agents";
import type { GitMode, Session, SessionStatus } from "../../shared/types";
import type { AgentDetector } from "../agents/detect";
import { agentProvider } from "../agents/registry";
import { SessionConnection, type SessionConnectionOptions } from "./connection";
import { LiveConnections } from "./live";
import { SessionSnapshotWriter, type SnapshotStore } from "./snapshots";
import type { SpawnTerminal } from "./terminals";
import { createTimer, loadTimer } from "./timing";
import { WarmAdapterPool } from "./warm";

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
   * The MCP servers a session gets: Hardcore's own, minted per session
   * (src/main/cad). A probe (`probeOptions`) is minted one too, and revokes
   * it when it is done: the adapter is spawned exactly as a real session's
   * would be, or the options it reports are not the options it would have.
   */
  mcpServers?: (session: Pick<Session, "id" | "projectId" | "cwd">) => McpServer[];
  /** Called when a probe's connection is closed, so its bridge token can be revoked. */
  forgetProbe?: (probeId: string) => void;

  /**
   * P5: the skills every session gets (src/main/cad/skills.ts). `root` is
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
    /** An explicit directory — Settings' `New chat in this worktree`. */
    cwd?: string | undefined;
  }) => Promise<SessionWorkspace>;

  /**
   * P7: the commit a directory is at. Recorded when the session is created and
   * again when each turn starts, which is what the review's `This session` and
   * `Last turn` scopes are measured from.
   */
  head?: (cwd: string) => Promise<string | null>;

  /** P7: remove the session's worktree on delete, if the settings allow it. */
  releaseWorkspace?: (session: Session) => Promise<void>;

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
};

/** Codex's convention: the first line of the first prompt, trimmed to fit a sidebar row. */
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

type ChangeTally = { files: Set<string>; insertions: number; deletions: number };

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
  private readonly snapshots: SessionSnapshotWriter | null;
  private readonly warm: WarmAdapterPool<SessionConnection>;

  constructor(private readonly deps: SessionManagerDeps) {
    this.live = new LiveConnections({
      ...(deps.keepAlive === undefined ? {} : { limit: deps.keepAlive }),
      // A turn in flight is never evicted: the work and the reason for it
      // would both be lost, and the limit comes back down when it ends.
      busy: (connection) =>
        connection.state.status === "running" || connection.state.status === "waiting",
      onEvict: (sessionId) => {
        console.info(`[acp] ${sessionId.slice(0, 8)} was closed to keep the adapter count at the limit`);
        // The snapshot, now: the adapter is gone and a click on that row has
        // only the picture to paint (`./snapshots.ts`).
        this.snapshots?.flush(sessionId);
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
    return this.deps.repo.list(projectId);
  }

  get(id: string): Session | null {
    return this.deps.repo.get(id);
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
    const connection = this.live.get(id);
    // `acpSessionId`, not merely `alive`: a connection that is spawned but
    // still replaying holds an empty state, and the snapshot is a better
    // picture of the session than the beginning of its own reload.
    if (connection?.alive && connection.acpSessionId) {
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
    if (!agentProvider(input.agentId)) {
      throw new Error(`unknown agent: ${input.agentId}`);
    }

    const workspace = await this.workspaceFor(input);
    const startHead = await this.headOf(workspace.cwd);
    const now = Date.now();
    const session: Session = {
      id: this.deps.newId(),
      projectId: input.projectId,
      agentId: input.agentId,
      cwd: workspace.cwd,
      gitMode: input.gitMode,
      branch: workspace.branch ?? input.branch,
      ...(workspace.worktreePath ? { worktreePath: workspace.worktreePath } : {}),
      title: "New session",
      createdAt: now,
      updatedAt: now,
      status: "connecting",
      acpSessionId: null,
      changedFiles: 0,
      insertions: 0,
      deletions: 0,
      archived: false,
      pinned: false,
      // Both scopes start here. `turnHead` is the session's head until the
      // first turn moves it, so a review taken before any prompt shows what
      // the person changed by hand rather than nothing at all.
      sessionHead: startHead,
      turnHead: startHead,
      turnStartedAt: null,
    };
    this.deps.repo.upsert(session);
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
      await connection.initialize();
      timer.mark("initialize");
      await connection.newSession();
      timer.mark("session/new");
      console.info(
        `[acp] create ${session.id.slice(0, 8)} ${session.agentId} warm=${warmed ? "yes" : "no"} ${timer.format()}`,
      );
    } catch (error) {
      // A row with no agent session id can never be loaded; the renderer
      // shows the failure (sign in, install) and the user creates again.
      this.live.delete(session.id)?.close();
      this.deps.repo.remove(session.id);
      this.broadcastIndex();
      throw error;
    }
    // What the person last chose for this agent — the model, the effort and
    // the mode. Never a reason for the session to fail: a refused
    // `set_config_option` leaves the session at the agent's own defaults,
    // which is a working session.
    await this.applyPreferences(session, connection);
    const updated = this.update(session.id, { acpSessionId: connection.acpSessionId, status: "idle" });
    this.deps.broadcast("session.state", { sessionId: session.id, state: connection.state });
    return updated;
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
    const status = this.deps.detector.list().find((candidate) => candidate.id === provider.id);
    // Stricter than `connect`, on purpose. A session is something a person
    // asked for and is worth an `npx -y` download; a probe is speculative,
    // and eight `launchWithoutBinary` providers fetching their adapters on a
    // first run — each to be told it is signed out — is a download storm
    // nobody asked for. So: the CLI is on this machine, or nothing. (With a
    // launch override in force every provider is the same test process, and
    // the machine's PATH says nothing about it.)
    if (!launch && !status?.installed) {
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
    const work = this.loadNow(id).finally(() => {
      this.loads.delete(id);
    });
    this.loads.set(id, work);
    return work;
  }

  private async loadNow(id: string): Promise<SessionState> {
    const session = this.require(id);
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
    const connection = await this.connect(session, {
      onWarm: () => {
        warmed = true;
      },
      replay,
    });
    timer.mark("spawn");
    try {
      await connection.initialize();
      timer.mark("initialize");
      await connection.loadSession(session.acpSessionId);
    } catch (error) {
      this.setStatus(id, "error");
      connection.close();
      this.live.delete(id);
      throw error;
    } finally {
      replay.onReplayUpdate = undefined;
    }
    timer.mark("replay");
    console.info(
      `[acp] load ${id.slice(0, 8)} ${session.agentId} warm=${warmed ? "yes" : "no"} ${timer.format()}`,
    );
    this.update(id, { status: "idle" });
    this.deps.broadcast("session.state", { sessionId: id, state: connection.state });
    return connection.state;
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

  async prompt(id: string, content: PromptBlock[]): Promise<{ stopReason: string }> {
    const session = this.require(id);
    const connection = await this.ensureLive(session);
    // The session being prompted is the one in use: it goes to the front of
    // the keep-alive queue and is never what an eviction closes.
    this.live.touch(id);
    if (session.title === "New session") {
      this.update(id, { title: titleFromPrompt(content) });
    }
    // The turn's starting point, read before the agent can move it. This is
    // what the review's `Last turn` scope diffs against; taking it afterwards
    // would measure the turn against its own result.
    this.update(id, {
      turnHead: await this.headOf(session.cwd),
      turnStartedAt: Date.now(),
    });
    try {
      const response = await connection.prompt(content, `${id}:${Date.now()}`);
      this.persistTally(id);
      return { stopReason: response.stopReason };
    } catch (error) {
      this.persistTally(id);
      throw error;
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

  respondPermission(id: string, requestId: string, optionId: string | null): void {
    this.requireLive(id).respondPermission(requestId, optionId);
  }

  rename(id: string, title: string): Session {
    this.require(id);
    return this.update(id, { title: title.trim() });
  }

  /** Hide the row from the sidebar. The adapter is closed; `load` still resumes it later. */
  archive(id: string, archived: boolean): Session {
    this.require(id);
    if (archived) {
      this.close(id);
    }
    return this.update(id, { archived });
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
    this.live.delete(id)?.close();
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
  async delete(id: string): Promise<void> {
    const session = this.deps.repo.get(id);
    this.live.delete(id)?.close();
    this.tallies.delete(id);
    // The snapshot row goes with the session's own (ON DELETE CASCADE); this
    // cancels the pending write that would otherwise put it back.
    this.snapshots?.forget(id);
    this.deps.repo.remove(id);
    this.broadcastIndex();
    if (session) {
      await this.deps.releaseWorkspace?.(session).catch(() => undefined);
    }
  }

  /**
   * On quit: kill every adapter, the idle ones included, and file the
   * snapshots still waiting on their debounce — a session that was streaming
   * when the app was quit paints where it left off rather than where it was
   * a minute earlier.
   */
  closeAll(): void {
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

  /** The commit a directory is at, or null — never a reason to fail a turn. */
  private async headOf(cwd: string): Promise<string | null> {
    if (!this.deps.head) {
      return null;
    }
    return this.deps.head(cwd).catch(() => null);
  }

  private require(id: string): Session {
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
   * bundled CAD runtime's bin directory in front of `PATH`. A session's
   * `cadgen` and `python` are then the app's own, whatever the person's shell
   * would have found — and nothing about it is installed on the machine.
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
    return {
      sessionId: session.id,
      mcpServers: this.deps.mcpServers?.(session) ?? [],
      // The preamble only to the agents that do not load the skills root
      // themselves (plan §8, as revised).
      preamble: provider?.skillRoots === "preamble" ? (this.deps.skills?.preamble() ?? null) : null,
      onEvent: (event) => {
        if (event.type === "session/update") {
          replay.onReplayUpdate?.();
        }
        this.onEvent(session.id, event);
      },
      onTerminalOutput: (terminalId, data, exit) =>
        this.deps.broadcast("terminal.output", { sessionId: session.id, terminalId, data, exit }),
      onFilesChanged: (paths) => {
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
    hooks: { onWarm?: () => void; replay?: { onReplayUpdate?: () => void } } = {},
  ): Promise<SessionConnection> {
    const provider = agentProvider(session.agentId);
    if (!provider) {
      throw new Error(`unknown agent: ${session.agentId}`);
    }
    const status = this.deps.detector.list().find((candidate) => candidate.id === provider.id);
    if (!provider.launchWithoutBinary && status && !status.installed) {
      throw new Error(`${provider.name} is not installed`);
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
    this.live.delete(session.id)?.close();
    this.setStatus(session.id, "connecting");

    const sessionOptions = this.sessionOptions(session, hooks.replay ?? {});
    const warm = this.warm.take(session.agentId, session.cwd);
    if (warm) {
      warm.adopt(sessionOptions);
      hooks.onWarm?.();
      this.live.set(session.id, warm);
      return warm;
    }
    const connection = new SessionConnection({
      ...(await this.adapterOptions(session.agentId, session.cwd)),
      ...sessionOptions,
    });
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

  private onEvent(id: string, event: SessionEvent) {
    this.deps.broadcast("session.update", { sessionId: id, event });
    // Every state main sees is a state the next click could paint from
    // (`./snapshots.ts`). Debounced there, so a streaming turn is one write
    // when it stops rather than one per token.
    const current = this.live.get(id)?.state;
    if (current && this.deps.repo.get(id)) {
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
      case "session/update":
        this.tallyUpdate(id, event.update as Record<string, unknown>);
        break;
      case "permission/request":
        this.setStatus(id, "waiting");
        this.deps.broadcast("session.permission", { sessionId: id, request: event.request });
        break;
      case "permission/resolve":
        if (this.live.get(id)?.state.status === "running") {
          this.setStatus(id, "running");
        }
        break;
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

  private tally(id: string): ChangeTally {
    let tally = this.tallies.get(id);
    if (!tally) {
      tally = { files: new Set(), insertions: 0, deletions: 0 };
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

  private persistTally(id: string) {
    const tally = this.tallies.get(id);
    if (tally && this.deps.repo.get(id)) {
      this.update(id, {
        changedFiles: tally.files.size,
        insertions: tally.insertions,
        deletions: tally.deletions,
      });
    }
  }

  private setStatus(id: string, status: SessionStatus, error: string | null = null) {
    const session = this.deps.repo.get(id);
    if (!session || session.status === status) {
      if (session) {
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

/** Lines added and removed between two texts, as a multiset difference — a pill, not a diff viewer. */
export function diffCounts(oldText: string, newText: string): { insertions: number; deletions: number } {
  const count = (text: string) => {
    const map = new Map<string, number>();
    if (text === "") {
      return map;
    }
    // A trailing newline ends the last line; it does not start an empty one.
    for (const line of text.replace(/\n$/, "").split("\n")) {
      map.set(line, (map.get(line) ?? 0) + 1);
    }
    return map;
  };
  const before = count(oldText);
  const after = count(newText);
  let insertions = 0;
  let deletions = 0;
  for (const [line, n] of after) {
    insertions += Math.max(0, n - (before.get(line) ?? 0));
  }
  for (const [line, n] of before) {
    deletions += Math.max(0, n - (after.get(line) ?? 0));
  }
  return { insertions, deletions };
}
