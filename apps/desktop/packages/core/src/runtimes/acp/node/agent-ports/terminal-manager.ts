import { PassThrough } from 'node:stream';
import type { TerminalState } from '#runtimes/acp/api';
import type {
  AcpProcessHost,
  AcpTerminalExit,
  AcpTerminalProcess,
} from '#runtimes/acp/api/transport';
import { ManagedAgentTerminal } from './managed-terminal';

type TerminalHost = Pick<AcpProcessHost, 'spawnTerminal'>;

export interface AgentTerminalHooks {
  onTerminalCreated(e: {
    conversationId: string;
    terminalId: string;
    command: string;
    args: string[];
    cwd: string;
  }): void;
  onTerminalOutput(e: {
    conversationId: string;
    terminalId: string;
    chunk: string;
    truncated: boolean;
  }): void;
  onTerminalExit(e: {
    conversationId: string;
    terminalId: string;
    exitStatus: { exitCode: number | null; signal: string | null };
  }): void;
  onTerminalReleased(e: { conversationId: string; terminalId: string }): void;
}

/**
 * A terminal the agent runs on its own side and only narrates to the client.
 * Codex executes commands itself and streams their output through
 * `_meta.terminal_output_delta` instead of asking for a client terminal, so
 * there is no process here: the runtime feeds output and the exit status in,
 * and the managed terminal buffers and publishes them exactly like a
 * client-spawned command.
 */
class NarratedTerminalProcess implements AcpTerminalProcess {
  readonly stdout = new PassThrough();
  exitCode: number | null = null;
  /** Characters appended so far, to skip the part of an exit aggregate already streamed. */
  written = 0;
  private exitStatus: AcpTerminalExit | null = null;
  private readonly exitCallbacks: Array<(status: AcpTerminalExit) => void> = [];

  onExit(cb: (status: AcpTerminalExit) => void): void {
    if (this.exitStatus) cb(this.exitStatus);
    else this.exitCallbacks.push(cb);
  }

  onError(): void {
    // A narrated terminal has no process that could fail on this side.
  }

  kill(): void {
    // Nothing runs here; the agent owns the process.
  }

  append(chunk: string): void {
    if (this.exitStatus || chunk.length === 0) return;
    this.written += chunk.length;
    this.stdout.write(chunk);
  }

  exit(status: AcpTerminalExit): void {
    if (this.exitStatus) return;
    this.exitStatus = status;
    this.exitCode = status.exitCode;
    this.stdout.end();
    for (const cb of this.exitCallbacks.splice(0)) cb(status);
  }
}

/**
 * Host-scoped registry of all ACP agent terminals: the ones the client spawns
 * for the agent and the ones the agent runs itself and narrates.
 */
export class AgentTerminalManager {
  private readonly byId = new Map<
    string,
    { conversationId: string; terminal: ManagedAgentTerminal }
  >();
  private readonly byConversation = new Map<string, Set<string>>();
  private readonly narrated = new Map<string, NarratedTerminalProcess>();

  constructor(
    private readonly host: TerminalHost,
    private readonly hooks: AgentTerminalHooks
  ) {}

  /** True when the host supports spawning agent terminals. */
  supportsTerminals(): boolean {
    return typeof this.host.spawnTerminal === 'function';
  }

  /**
   * Spawn a terminal command and register it under the given conversation.
   * Emits `onTerminalCreated` synchronously after registration.
   * Throws if the host does not support terminal spawning.
   */
  async create(
    conversationId: string,
    spec: {
      command: string;
      args: string[];
      env: Record<string, string>;
      cwd: string;
      outputByteLimit?: number | null;
    }
  ): Promise<string> {
    if (!this.host.spawnTerminal) {
      throw new Error(
        'AgentTerminalManager: host does not support terminal spawning (spawnTerminal is undefined)'
      );
    }

    const terminalId = crypto.randomUUID();
    const proc = await this.host.spawnTerminal(spec);
    this.register(conversationId, terminalId, spec, proc, spec.outputByteLimit);
    return terminalId;
  }

  /**
   * Register a terminal the agent runs itself, keyed by the agent's own
   * terminal id. No-op when that id is already known.
   */
  adoptNarrated(
    conversationId: string,
    spec: { terminalId: string; command: string; cwd: string }
  ): void {
    if (this.byId.has(spec.terminalId)) return;
    const proc = new NarratedTerminalProcess();
    this.narrated.set(spec.terminalId, proc);
    this.register(
      conversationId,
      spec.terminalId,
      { command: spec.command, args: [], cwd: spec.cwd },
      proc
    );
  }

  /** Feed output the agent narrated. Returns false when the terminal is not a narrated one. */
  appendNarratedOutput(terminalId: string, chunk: string): boolean {
    const proc = this.narrated.get(terminalId);
    if (!proc) return false;
    proc.append(chunk);
    return true;
  }

  /**
   * Finish a narrated terminal. Providers re-send the whole output at exit;
   * only the part that was not streamed yet is appended so nothing shows twice.
   */
  exitNarrated(terminalId: string, status: AcpTerminalExit, aggregate?: string): boolean {
    const proc = this.narrated.get(terminalId);
    if (!proc) return false;
    if (aggregate !== undefined && aggregate.length > proc.written) {
      proc.append(aggregate.slice(proc.written));
    }
    proc.exit(status);
    return true;
  }

  private register(
    conversationId: string,
    terminalId: string,
    spec: { command: string; args: string[]; cwd: string },
    proc: AcpTerminalProcess,
    outputByteLimit?: number | null
  ): void {
    const terminal = new ManagedAgentTerminal(
      terminalId,
      spec.command,
      spec.args,
      spec.cwd,
      proc,
      (chunk, truncated) => {
        this.hooks.onTerminalOutput({ conversationId, terminalId, chunk, truncated });
      },
      (exitStatus) => {
        this.hooks.onTerminalExit({ conversationId, terminalId, exitStatus });
      },
      outputByteLimit
    );

    this.byId.set(terminalId, { conversationId, terminal });
    let ids = this.byConversation.get(conversationId);
    if (!ids) {
      ids = new Set();
      this.byConversation.set(conversationId, ids);
    }
    ids.add(terminalId);

    this.hooks.onTerminalCreated({
      conversationId,
      terminalId,
      command: spec.command,
      args: spec.args,
      cwd: spec.cwd,
    });
  }

  /** Retrieve a live terminal by id. Returns undefined if not found. */
  get(terminalId: string): ManagedAgentTerminal | undefined {
    return this.byId.get(terminalId)?.terminal;
  }

  /** Snapshots of all live terminals for a conversation. */
  listByConversation(conversationId: string): TerminalState[] {
    const ids = this.byConversation.get(conversationId);
    if (!ids) return [];
    const out: TerminalState[] = [];
    for (const id of ids) {
      const entry = this.byId.get(id);
      if (entry) out.push(entry.terminal.snapshot());
    }
    return out;
  }

  /** Snapshots of all live terminals across all conversations on this host. */
  listAll(): TerminalState[] {
    const out: TerminalState[] = [];
    for (const { terminal } of this.byId.values()) {
      out.push(terminal.snapshot());
    }
    return out;
  }

  /**
   * Dispose a single terminal and remove it from the registry.
   * Emits `onTerminalReleased`. No-op if the id is unknown.
   */
  release(terminalId: string): void {
    const entry = this.byId.get(terminalId);
    if (!entry) return;
    const { conversationId, terminal } = entry;
    terminal.dispose();
    this.byId.delete(terminalId);
    this.narrated.delete(terminalId);
    this.byConversation.get(conversationId)?.delete(terminalId);
    if (this.byConversation.get(conversationId)?.size === 0) {
      this.byConversation.delete(conversationId);
    }
    this.hooks.onTerminalReleased({ conversationId, terminalId });
  }

  /**
   * Dispose all terminals belonging to a conversation (called on session close).
   * Emits `onTerminalReleased` for each terminal.
   */
  disposeConversation(conversationId: string): void {
    const ids = this.byConversation.get(conversationId);
    if (!ids) return;
    for (const terminalId of [...ids]) {
      const entry = this.byId.get(terminalId);
      if (!entry) continue;
      entry.terminal.dispose();
      this.byId.delete(terminalId);
      this.narrated.delete(terminalId);
      this.hooks.onTerminalReleased({ conversationId, terminalId });
    }
    this.byConversation.delete(conversationId);
  }

  /**
   * Dispose every terminal on this host (called on host teardown).
   * Emits `onTerminalReleased` for each terminal.
   */
  killAll(): void {
    for (const [terminalId, { conversationId, terminal }] of this.byId) {
      terminal.dispose();
      this.hooks.onTerminalReleased({ conversationId, terminalId });
    }
    this.byId.clear();
    this.byConversation.clear();
    this.narrated.clear();
  }
}
