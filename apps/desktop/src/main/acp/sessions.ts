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
import type { McpServer } from "@agentclientprotocol/sdk";

import type {
  ApprovalMode,
  PromptBlock,
  SessionEvent,
  SessionState,
} from "../../shared/acp/types";
import type { IpcEventChannel, IpcEventPayload } from "../../shared/ipc";
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

export type SessionManagerDeps = {
  repo: SessionRepository;
  detector: AgentDetector;
  spawnTerminal: SpawnTerminal;
  broadcast: <C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) => void;
  /** The MCP servers a session gets: Hardcore's own, minted per session (src/main/cad). */
  mcpServers?: (session: Session) => McpServer[];
  clientVersion?: string;
  newId: () => string;
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

  async create(input: {
    projectId: string;
    agentId: string;
    cwd: string;
    gitMode: GitMode;
    branch?: string;
  }): Promise<Session> {
    if (!agentProvider(input.agentId)) {
      throw new Error(`unknown agent: ${input.agentId}`);
    }
    const now = Date.now();
    const session: Session = {
      id: this.deps.newId(),
      projectId: input.projectId,
      agentId: input.agentId,
      cwd: input.cwd,
      gitMode: input.gitMode,
      branch: input.branch,
      title: "New session",
      createdAt: now,
      updatedAt: now,
      status: "connecting",
      acpSessionId: null,
      changedFiles: 0,
      insertions: 0,
      deletions: 0,
    };
    this.deps.repo.upsert(session);
    this.broadcastIndex();

    const connection = await this.connect(session);
    try {
      await connection.newSession();
    } catch (error) {
      this.setStatus(session.id, "error");
      connection.close();
      this.live.delete(session.id);
      throw error;
    }
    const updated = this.update(session.id, { acpSessionId: connection.acpSessionId, status: "idle" });
    this.deps.broadcast("session.state", { sessionId: session.id, state: connection.state });
    return updated;
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
    await this.requireLive(id).setConfigOption(configId, value);
  }

  respondPermission(id: string, requestId: string, optionId: string | null): void {
    this.requireLive(id).respondPermission(requestId, optionId);
  }

  setApprovalMode(id: string, mode: ApprovalMode): void {
    this.approval.set(id, mode);
    this.live.get(id)?.setApprovalMode(mode);
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

  delete(id: string): void {
    this.live.get(id)?.close();
    this.live.delete(id);
    this.tallies.delete(id);
    this.approval.delete(id);
    this.deps.repo.remove(id);
    this.broadcastIndex();
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
    this.live.get(session.id)?.close();
    this.setStatus(session.id, "connecting");

    const env = await this.deps.detector.environment();
    const connection = new SessionConnection({
      sessionId: session.id,
      agentId: session.agentId,
      launch: provider.launch,
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
        // project the paths belong to and one change record per path.
        this.deps.broadcast("files.changed", {
          projectId: session.projectId,
          changes: paths.map((path) => ({ path, kind: "changed" as const, directory: false })),
        });
      },
      onStderr: (line) => console.info(`[${session.agentId}:${session.id.slice(0, 8)}] ${line}`),
    });
    this.live.set(session.id, connection);
    return connection;
  }

  private onEvent(id: string, event: SessionEvent) {
    this.deps.broadcast("session.update", { sessionId: id, event });
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
