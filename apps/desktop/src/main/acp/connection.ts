/**
 * One adapter process, one ACP connection, one session (plan §4, §5).
 *
 * `SessionConnection` spawns the provider's launch command with the
 * login-shell environment, runs `@agentclientprotocol/sdk`'s
 * `ClientSideConnection` over its stdio, and drives `initialize`,
 * `authenticate`, `session/new` or `session/load`, `session/prompt`,
 * `session/cancel`, `session/set_mode` and `session/set_config_option`. It
 * also owns the session's `SessionState`: every event — the agent's updates
 * and the client's own narration — goes through `dispatch`, which reduces
 * and then tells whoever is listening (the IPC layer, the harness).
 *
 * Two things happen at the stream level rather than through the SDK:
 *
 *   - Every frame in both directions can be recorded (the harness writes
 *     the fixtures under `tests/fixtures/acp/` this way).
 *   - `session/update` notifications are read raw, before the SDK's schema
 *     sees them. Known kinds go on to the SDK as well (whose handler is a
 *     no-op); draft kinds the SDK 1.4.0 schema would reject —
 *     `subagent_spawned`, `subagent_state_update` — are diverted, so
 *     advertising the draft subagent capability cannot break the connection.
 *
 * No Electron here. The CLI harness and the connection tests run this file
 * in plain Node with the `child_process` terminal backend.
 */
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { Readable, Writable } from "node:stream";

import {
  ClientSideConnection,
  PROTOCOL_VERSION,
  RequestError,
  ndJsonStream,
  type AnyMessage,
  type InitializeResponse,
  type LoadSessionResponse,
  type McpServer,
  type NewSessionResponse,
  type PromptResponse,
} from "@agentclientprotocol/sdk";

import { configOptions, reduce, sessionModes } from "../../shared/acp/reduce";
import {
  initialSessionState,
  type ApprovalMode,
  type PromptBlock,
  type RawSessionUpdate,
  type SessionEvent,
  type SessionState,
} from "../../shared/acp/types";
import type { Launch } from "../../shared/agents";
import { AcpClient } from "./client";
import { TerminalManager, type SpawnTerminal, type TerminalOutputListener } from "./terminals";

/** The update kinds the SDK 1.4.0 schema accepts. Anything else is diverted around it. */
const SDK_UPDATE_KINDS = new Set([
  "user_message_chunk",
  "agent_message_chunk",
  "agent_thought_chunk",
  "tool_call",
  "tool_call_update",
  "plan",
  "plan_update",
  "plan_removed",
  "available_commands_update",
  "current_mode_update",
  "config_option_update",
  "session_info_update",
  "usage_update",
  "compaction_update",
  "compaction_summary_chunk",
]);

export type RecordedFrame = { dir: "in" | "out"; at: number; msg: unknown };

export type SessionConnectionOptions = {
  /** The app's session id (the sqlite row). */
  sessionId: string;
  agentId: string;
  launch: Launch;
  env: Record<string, string>;
  cwd: string;
  /** Passed to `session/new` and `session/load`; P5 adds the Hardcore server. */
  mcpServers?: McpServer[];
  spawnTerminal: SpawnTerminal;
  approvalMode?: ApprovalMode;
  clientVersion?: string;
  onEvent?: (event: SessionEvent, state: SessionState) => void;
  onTerminalOutput?: TerminalOutputListener;
  onFilesChanged?: (paths: string[]) => void;
  onStderr?: (line: string) => void;
  /** Every wire frame, both directions. */
  record?: (frame: RecordedFrame) => void;
};

export type ProcessExit = { code: number | null; signal: NodeJS.Signals | null };

export class SessionConnection {
  readonly client: AcpClient;
  readonly agent: ClientSideConnection;
  readonly process: ChildProcessWithoutNullStreams;
  readonly exited: Promise<ProcessExit>;
  readonly terminals: TerminalManager;

  private stateValue: SessionState;
  private initializeResponse: InitializeResponse | null = null;
  private closing = false;
  private exit: ProcessExit | null = null;
  private readonly stderrTail: string[] = [];

  constructor(private readonly options: SessionConnectionOptions) {
    this.stateValue = initialSessionState(options.sessionId, options.agentId);
    if (options.approvalMode) {
      this.stateValue = reduce(this.stateValue, {
        type: "approval",
        mode: options.approvalMode,
        at: Date.now(),
      });
    }

    this.process = spawn(options.launch.command, options.launch.args, {
      cwd: options.cwd,
      env: { ...options.env, ...options.launch.env },
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.process.stderr.setEncoding("utf8");
    this.process.stderr.on("data", (chunk: string) => {
      for (const line of chunk.split("\n")) {
        if (line.trim()) {
          this.stderrTail.push(line);
          if (this.stderrTail.length > 40) {
            this.stderrTail.shift();
          }
          options.onStderr?.(line);
        }
      }
    });

    this.exited = new Promise((resolve) => {
      this.process.on("exit", (code, signal) => {
        this.exit = { code, signal };
        resolve(this.exit);
      });
      this.process.on("error", (error) => {
        this.stderrTail.push(error.message);
        if (!this.exit) {
          this.exit = { code: null, signal: null };
          resolve(this.exit);
        }
      });
    });
    void this.exited.then((exit) => this.onProcessExit(exit));

    this.terminals = new TerminalManager(options.spawnTerminal, options.onTerminalOutput);
    this.client = new AcpClient({
      cwd: options.cwd,
      env: { ...options.env, ...options.launch.env },
      terminals: this.terminals,
      dispatch: (event) => this.dispatch(event),
      onFilesChanged: options.onFilesChanged,
      approvalMode: options.approvalMode,
    });

    this.agent = new ClientSideConnection(() => this.client, this.tappedStream());
  }

  /* ---------------------------------------------------------------------- */
  /* State                                                                   */
  /* ---------------------------------------------------------------------- */

  get state(): SessionState {
    return this.stateValue;
  }

  /**
   * Usable for requests. The SDK notices the end of the adapter's stdout
   * before Node reports the process exit, so both are checked: a connection
   * whose stream has closed rejects every request with "ACP connection
   * closed" even while the pid is technically still there.
   */
  get alive(): boolean {
    return this.exit === null && !this.agent.signal.aborted;
  }

  get initialized(): InitializeResponse | null {
    return this.initializeResponse;
  }

  /** The agent's session id, once `session/new` or `session/load` has answered. */
  get acpSessionId(): string | null {
    return this.stateValue.acpSessionId;
  }

  dispatch(event: SessionEvent): void {
    this.stateValue = reduce(this.stateValue, event);
    this.options.onEvent?.(event, this.stateValue);
  }

  /* ---------------------------------------------------------------------- */
  /* Agent methods                                                            */
  /* ---------------------------------------------------------------------- */

  async initialize(): Promise<InitializeResponse> {
    if (this.initializeResponse) {
      return this.initializeResponse;
    }
    const response = await this.agent.initialize({
      protocolVersion: PROTOCOL_VERSION,
      clientInfo: { name: "hardcore", version: this.options.clientVersion ?? "0.0.0" },
      clientCapabilities: {
        fs: { readTextFile: true, writeTextFile: true },
        terminal: true,
        auth: { terminal: false },
        // Subagent transcripts. The canonical draft field (`subagents`) is
        // not in SDK 1.4.0's ClientCapabilities type, so it rides in as a
        // plain property; the AIR meta key is what the Claude and Codex
        // adapters read while released SDKs strip the draft field.
        ...({ subagents: {} } as Record<string, unknown>),
        _meta: {
          "subagent-transcript": true,
          jetbrains: { air: { capabilities: { nativeSubagentSessions: true } } },
        },
      },
    });
    this.initializeResponse = response;
    return response;
  }

  async authenticate(methodId: string): Promise<void> {
    await this.agent.authenticate({ methodId });
  }

  async newSession(): Promise<NewSessionResponse> {
    await this.initialize();
    let response: NewSessionResponse;
    try {
      response = await this.agent.newSession({
        cwd: this.options.cwd,
        mcpServers: this.options.mcpServers ?? [],
      });
    } catch (error) {
      throw this.describe(error, "session/new");
    }
    this.dispatch({
      type: "session/connected",
      acpSessionId: response.sessionId,
      modes: response.modes
        ? {
            currentModeId: response.modes.currentModeId,
            availableModes: sessionModes(response.modes.availableModes),
          }
        : null,
      configOptions: response.configOptions ? configOptions(response.configOptions) : null,
      loading: false,
      at: Date.now(),
    });
    return response;
  }

  async loadSession(acpSessionId: string): Promise<LoadSessionResponse> {
    const init = await this.initialize();
    if (!init.agentCapabilities?.loadSession) {
      throw new Error(`${this.options.agentId} cannot resume sessions (no loadSession capability)`);
    }
    this.dispatch({
      type: "session/connected",
      acpSessionId,
      modes: null,
      configOptions: null,
      loading: true,
      at: Date.now(),
    });
    let response: LoadSessionResponse;
    try {
      response = await this.agent.loadSession({
        sessionId: acpSessionId,
        cwd: this.options.cwd,
        mcpServers: this.options.mcpServers ?? [],
      });
    } catch (error) {
      const described = this.describe(error, "session/load");
      this.dispatch({ type: "status", status: "error", error: described.message, at: Date.now() });
      throw described;
    }
    if (response.modes || response.configOptions) {
      this.dispatch({
        type: "session/connected",
        acpSessionId,
        modes: response.modes
          ? {
              currentModeId: response.modes.currentModeId,
              availableModes: sessionModes(response.modes.availableModes),
            }
          : null,
        configOptions: response.configOptions ? configOptions(response.configOptions) : null,
        loading: true,
        at: Date.now(),
      });
    }
    this.dispatch({ type: "session/loaded", at: Date.now() });
    return response;
  }

  /** Send a turn. Resolves with the stop reason; rejects (after dispatching `prompt/error`) on failure. */
  async prompt(content: PromptBlock[], turnId = `turn-${Date.now()}`): Promise<PromptResponse> {
    const acpSessionId = this.requireSession();
    this.dispatch({ type: "prompt/start", turnId, content, at: Date.now() });
    try {
      const response = await this.agent.prompt({
        sessionId: acpSessionId,
        prompt: content.map(toContentBlock),
      });
      this.dispatch({
        type: "prompt/end",
        stopReason: response.stopReason,
        usage: response.usage
          ? {
              totalTokens: response.usage.totalTokens,
              inputTokens: response.usage.inputTokens,
              outputTokens: response.usage.outputTokens,
              thoughtTokens: response.usage.thoughtTokens ?? null,
              cachedReadTokens: response.usage.cachedReadTokens ?? null,
              cachedWriteTokens: response.usage.cachedWriteTokens ?? null,
            }
          : null,
        at: Date.now(),
      });
      return response;
    } catch (error) {
      const described = this.describe(error, "session/prompt");
      this.dispatch({ type: "prompt/error", message: described.message, at: Date.now() });
      throw described;
    }
  }

  async cancel(): Promise<void> {
    const acpSessionId = this.requireSession();
    this.client.cancelPendingPermissions();
    await this.agent.cancel({ sessionId: acpSessionId });
  }

  async setMode(modeId: string): Promise<void> {
    await this.agent.setSessionMode({ sessionId: this.requireSession(), modeId });
    // Adapters also send `current_mode_update`; dispatching here means the UI
    // does not wait on it.
    this.dispatch({
      type: "session/update",
      acpSessionId: this.requireSession(),
      update: { sessionUpdate: "current_mode_update", currentModeId: modeId },
      at: Date.now(),
    });
  }

  async setConfigOption(configId: string, value: string | boolean): Promise<void> {
    const sessionId = this.requireSession();
    const response = await this.agent.setSessionConfigOption(
      typeof value === "boolean"
        ? { sessionId, configId, type: "boolean", value }
        : { sessionId, configId, value },
    );
    this.dispatch({
      type: "config/updated",
      configOptions: configOptions(response.configOptions),
      at: Date.now(),
    });
  }

  respondPermission(requestId: string, optionId: string | null): boolean {
    return this.client.respondPermission(requestId, optionId);
  }

  setApprovalMode(mode: ApprovalMode): void {
    this.client.approvalMode = mode;
    this.dispatch({ type: "approval", mode, at: Date.now() });
  }

  /** Kill the adapter. Idempotent. */
  close(): void {
    if (this.closing) {
      return;
    }
    this.closing = true;
    this.client.dispose();
    if (this.exit === null) {
      this.process.kill("SIGTERM");
      setTimeout(() => {
        if (this.exit === null) {
          this.process.kill("SIGKILL");
        }
      }, 2_000).unref();
    }
    this.dispatch({ type: "status", status: "closed", error: null, at: Date.now() });
  }

  /* ---------------------------------------------------------------------- */
  /* Internals                                                                */
  /* ---------------------------------------------------------------------- */

  private requireSession(): string {
    const id = this.stateValue.acpSessionId;
    if (!id) {
      throw new Error("no ACP session yet: call newSession or loadSession first");
    }
    return id;
  }

  private onProcessExit(exit: ProcessExit) {
    this.client.dispose();
    if (this.closing) {
      return;
    }
    const detail = this.stderrTail.slice(-5).join("\n");
    const message =
      `${this.options.agentId} exited unexpectedly` +
      (exit.code !== null ? ` (code ${exit.code})` : exit.signal ? ` (${exit.signal})` : "") +
      (detail ? `:\n${detail}` : "");
    this.dispatch({ type: "status", status: "error", error: message, at: Date.now() });
  }

  /** Turn an SDK/RPC failure into an error whose message the UI can show. */
  private describe(error: unknown, method: string): Error {
    if (error instanceof RequestError) {
      const auth = error.code === -32000;
      const methods = this.initializeResponse?.authMethods ?? [];
      const hint =
        auth && methods.length > 0
          ? ` — sign in first (${methods.map((m) => m.name).join(", ")})`
          : "";
      const data = error.data === undefined ? "" : ` ${JSON.stringify(error.data)}`;
      return new Error(`${method}: ${error.message}${data}${hint}`, { cause: error });
    }
    if (error instanceof Error) {
      if (this.exit !== null || this.agent.signal.aborted) {
        const tail = this.stderrTail.slice(-5).join("\n");
        const code = this.exit?.code;
        return new Error(
          `${method}: ${this.options.agentId} exited${code != null ? ` (code ${code})` : ""}${tail ? `:\n${tail}` : ""}`,
          { cause: error },
        );
      }
      return error;
    }
    return new Error(`${method}: ${String(error)}`);
  }

  /** The SDK's stream, with recording taps and the raw update reader in front of it. */
  private tappedStream() {
    const stdout = Readable.toWeb(this.process.stdout) as ReadableStream<Uint8Array>;
    const stdin = Writable.toWeb(this.process.stdin) as WritableStream<Uint8Array>;
    const raw = ndJsonStream(stdin, stdout);

    const readable = raw.readable.pipeThrough(
      new TransformStream<AnyMessage, AnyMessage>({
        transform: (msg, controller) => {
          this.options.record?.({ dir: "in", at: Date.now(), msg });
          const update = sessionUpdateOf(msg);
          if (update) {
            this.dispatch({
              type: "session/update",
              acpSessionId: update.sessionId,
              update: update.update,
              at: Date.now(),
            });
            if (!SDK_UPDATE_KINDS.has(update.update.sessionUpdate)) {
              return;
            }
          }
          controller.enqueue(msg);
        },
      }),
    );

    const outbound = new TransformStream<AnyMessage, AnyMessage>({
      transform: (msg, controller) => {
        this.options.record?.({ dir: "out", at: Date.now(), msg });
        controller.enqueue(msg);
      },
    });
    outbound.readable.pipeTo(raw.writable).catch(() => {
      // The process is gone; the exit handler reports it.
    });

    return { readable, writable: outbound.writable };
  }
}

function sessionUpdateOf(msg: unknown): { sessionId: string; update: RawSessionUpdate } | null {
  if (typeof msg !== "object" || msg === null) {
    return null;
  }
  const record = msg as Record<string, unknown>;
  if (record.method !== "session/update" || "id" in record) {
    return null;
  }
  const params = record.params as Record<string, unknown> | undefined;
  const update = params?.update as Record<string, unknown> | undefined;
  if (typeof params?.sessionId !== "string" || typeof update?.sessionUpdate !== "string") {
    return null;
  }
  return { sessionId: params.sessionId, update: update as RawSessionUpdate };
}

function toContentBlock(block: PromptBlock) {
  switch (block.type) {
    case "text":
      return { type: "text" as const, text: block.text };
    case "image":
      return {
        type: "image" as const,
        data: block.data,
        mimeType: block.mimeType,
        uri: block.uri ?? undefined,
      };
    case "resource_link":
      return {
        type: "resource_link" as const,
        uri: block.uri,
        name: block.name,
        mimeType: block.mimeType ?? undefined,
        title: block.title ?? undefined,
      };
  }
}
