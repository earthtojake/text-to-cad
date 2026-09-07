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
 * Dependencies are injected so this file has no Electron import of its own:
 * main wires it to the sqlite repository, node-pty and the IPC broadcaster.
 */
import { existsSync } from "node:fs";
import nodePath from "node:path";

import type { McpServer } from "@agentclientprotocol/sdk";

import { autoModeId, autoModeValue, effortOption, modeOption, modelOption } from "../../shared/acp/options";
import type {
  ApprovalMode,
  ConfigOption,
  PromptBlock,
  SessionEvent,
  SessionState,
} from "../../shared/acp/types";
import type { IpcEventChannel, IpcEventPayload } from "../../shared/ipc";
import type { Launch } from "../../shared/agents";
import type { GitMode, Session, SessionStatus } from "../../shared/types";
import type { AgentDetector } from "../agents/detect";
import { agentProvider } from "../agents/registry";
import { SessionConnection } from "./connection";
import type { SpawnTerminal } from "./terminals";

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
   * P2: what the agents' sessions can be configured with, kept between
   * sessions (`./agent-options.ts`). Injected: this file applies the stored
   * defaults on create and writes back what it sees, and knows nothing about
   * where they are stored.
   */
  agentOptions?: {
    defaults(agentId: string): { model: string | null; effort: string | null };
    remember(agentId: string, options: ConfigOption[]): void;
    rememberChoice(
      agentId: string,
      configId: string,
      value: string | boolean,
      options: ConfigOption[],
    ): void;
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
  private readonly live = new Map<string, SessionConnection>();
  private readonly tallies = new Map<string, ChangeTally>();
  private readonly approval = new Map<string, ApprovalMode>();

  constructor(private readonly deps: SessionManagerDeps) {}

  /* ---------------------------------------------------------------------- */
  /* Index                                                                    */
  /* ---------------------------------------------------------------------- */

  list(projectId?: string): Session[] {
    return this.deps.repo.list(projectId);
  }

  get(id: string): Session | null {
    return this.deps.repo.get(id);
  }

  state(id: string): SessionState | null {
    return this.live.get(id)?.state ?? null;
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
      // Both scopes start here. `turnHead` is the session's head until the
      // first turn moves it, so a review taken before any prompt shows what
      // the person changed by hand rather than nothing at all.
      sessionHead: startHead,
      turnHead: startHead,
      turnStartedAt: null,
    };
    this.deps.repo.upsert(session);
    this.broadcastIndex();

    let connection: SessionConnection;
    try {
      connection = await this.connect(session);
      await connection.newSession();
    } catch (error) {
      // A row with no agent session id can never be loaded; the renderer
      // shows the failure (sign in, install) and the user creates again.
      this.live.get(session.id)?.close();
      this.live.delete(session.id);
      this.deps.repo.remove(session.id);
      this.broadcastIndex();
      throw error;
    }
    // What the person last chose for this agent, and the agent's own
    // auto-approval preset. Never a reason for the session to fail: a
    // refused `set_config_option` leaves the session at the agent's own
    // defaults, which is a working session.
    await this.applyPreferences(session, connection);
    const updated = this.update(session.id, { acpSessionId: connection.acpSessionId, status: "idle" });
    this.deps.broadcast("session.state", { sessionId: session.id, state: connection.state });
    return updated;
  }

  /**
   * The model, then the effort, then the agent's own auto mode — in that
   * order, and the order matters: switching model is what changes which
   * effort levels the agent offers, so an effort set first would be set
   * against the outgoing model's list.
   *
   * Every step is best-effort. An adapter that refuses one of them logs and
   * the session goes on.
   */
  private async applyPreferences(session: Session, connection: SessionConnection): Promise<void> {
    const defaults = this.deps.agentOptions?.defaults(session.agentId) ?? { model: null, effort: null };
    await this.applyConfigOption(connection, modelOption(connection.state.configOptions), defaults.model);
    await this.applyConfigOption(connection, effortOption(connection.state.configOptions), defaults.effort);
    await this.applyAutoMode(connection);
    this.deps.agentOptions?.remember(session.agentId, connection.state.configOptions);
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
   * Start in whatever the provider calls its own auto-approval preset —
   * Claude's `Auto`, Codex's `Approve for me` — rather than in the adapter's
   * most cautious default (`_meta.kind: auto_review`, `shared/acp/options`).
   * The app's own `approvalMode` is a separate decision and is untouched.
   */
  private async applyAutoMode(connection: SessionConnection): Promise<void> {
    try {
      const modeId = autoModeId(connection.state.modes);
      if (modeId) {
        if (connection.state.currentModeId !== modeId) {
          await connection.setMode(modeId);
        }
        return;
      }
      const option = modeOption(connection.state.configOptions);
      const value = autoModeValue(option);
      if (option && value && option.currentValue !== value) {
        await connection.setConfigOption(option.id, value);
      }
    } catch (error) {
      console.warn(`[acp] the agent's auto mode was refused: ${String(error)}`);
    }
  }

  /**
   * What one `session/new` with this agent would offer, without keeping the
   * session: the adapter is spawned exactly as a real session's is — the same
   * environment, the same MCP servers, the project's own directory — asked
   * for a session, read, and killed. Nothing is prompted and no row is
   * written.
   *
   * This is what the new-session screen's model and effort chips are drawn
   * from before anything has run. An agent that is not installed or not
   * signed in throws here, and the caller's answer to that is silence.
   */
  async probeOptions(input: {
    agentId: string;
    cwd: string;
    projectId: string | null;
  }): Promise<ConfigOption[]> {
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
    const env = await this.deps.detector.environment();
    const connection = new SessionConnection({
      sessionId: probeId,
      agentId: input.agentId,
      launch: launch ?? provider.launch,
      env,
      cwd: input.cwd,
      mcpServers:
        this.deps.mcpServers?.({ id: probeId, projectId: input.projectId ?? "", cwd: input.cwd }) ?? [],
      spawnTerminal: this.deps.spawnTerminal,
      clientVersion: this.deps.clientVersion,
      onStderr: () => undefined,
    });
    try {
      // An adapter that has to be fetched before it can answer (`npx -y …`)
      // is slow but finite; one that never answers must not leave a process
      // behind for the rest of the app's life.
      await Promise.race([connection.newSession(), rejectAfter(PROBE_TIMEOUT_MS, input.agentId)]);
      return connection.state.configOptions;
    } finally {
      connection.close();
      this.deps.forgetProbe?.(probeId);
    }
  }

  /** Resume: spawn and `session/load`. A live connection is returned as is. */
  async load(id: string): Promise<SessionState> {
    const existing = this.live.get(id);
    if (existing?.alive) {
      this.deps.broadcast("session.state", { sessionId: id, state: existing.state });
      return existing.state;
    }
    const session = this.require(id);
    if (!session.acpSessionId) {
      throw new Error("this session never connected; create it again");
    }
    const connection = await this.connect(session);
    try {
      await connection.loadSession(session.acpSessionId);
    } catch (error) {
      this.setStatus(id, "error");
      connection.close();
      this.live.delete(id);
      throw error;
    }
    this.update(id, { status: "idle" });
    this.deps.broadcast("session.state", { sessionId: id, state: connection.state });
    return connection.state;
  }

  async prompt(id: string, content: PromptBlock[]): Promise<{ stopReason: string }> {
    const session = this.require(id);
    const connection = await this.ensureLive(session);
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

  async setMode(id: string, modeId: string): Promise<void> {
    await this.requireLive(id).setMode(modeId);
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
    if (session) {
      this.deps.agentOptions?.rememberChoice(session.agentId, configId, value, before);
      this.deps.agentOptions?.remember(session.agentId, connection.state.configOptions);
    }
  }

  respondPermission(id: string, requestId: string, optionId: string | null): void {
    this.requireLive(id).respondPermission(requestId, optionId);
  }

  setApprovalMode(id: string, mode: ApprovalMode): void {
    this.approval.set(id, mode);
    this.live.get(id)?.setApprovalMode(mode);
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

  close(id: string): void {
    const connection = this.live.get(id);
    if (connection) {
      connection.close();
      this.live.delete(id);
    }
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
    this.live.get(id)?.close();
    this.live.delete(id);
    this.tallies.delete(id);
    this.approval.delete(id);
    this.deps.repo.remove(id);
    this.broadcastIndex();
    if (session) {
      await this.deps.releaseWorkspace?.(session).catch(() => undefined);
    }
  }

  /** On quit: kill every adapter. */
  closeAll(): void {
    for (const id of [...this.live.keys()]) {
      this.close(id);
    }
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

  /** A live connection, reconnecting (and loading) after a crash or a close. */
  private async ensureLive(session: Session): Promise<SessionConnection> {
    const existing = this.live.get(session.id);
    if (existing?.alive) {
      return existing;
    }
    await this.load(session.id);
    return this.requireLive(session.id);
  }

  private async connect(session: Session): Promise<SessionConnection> {
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
    this.live.get(session.id)?.close();
    this.setStatus(session.id, "connecting");

    const env = await this.deps.detector.environment();
    const connection = new SessionConnection({
      sessionId: session.id,
      agentId: session.agentId,
      launch: this.deps.launchOverride?.(provider.id) ?? provider.launch,
      env,
      cwd: session.cwd,
      mcpServers: this.deps.mcpServers?.(session) ?? [],
      spawnTerminal: this.deps.spawnTerminal,
      approvalMode: this.approval.get(session.id),
      clientVersion: this.deps.clientVersion,
      onEvent: (event) => this.onEvent(session.id, event),
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
    });
    this.live.set(session.id, connection);
    return connection;
  }

  private onEvent(id: string, event: SessionEvent) {
    this.deps.broadcast("session.update", { sessionId: id, event });
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
        this.deps.agentOptions?.remember(session.agentId, state.configOptions);
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
