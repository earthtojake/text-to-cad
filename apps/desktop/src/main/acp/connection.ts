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
 * Every session is also handed what this app gives an agent (plan §8): the
 * text-to-cad MCP server in `mcpServers`, and the skills root as an additional
 * directory — `additionalDirectories` and `_meta.additionalRoots` both, on
 * `session/new` and `session/load` alike. For an agent that does not read
 * either, `preamble` rides in front of the first prompt instead.
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
import fs from "node:fs";
import path from "node:path";

import { trackChild } from "../children";
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

import { configOptions, reduce, sessionModes, turnFactsFrom } from "../../shared/acp/reduce";
import {
  initialSessionState,
  type PromptBlock,
  type RawSessionUpdate,
  type SessionEvent,
  type SessionState,
  type Turn,
} from "../../shared/acp/types";
import type { Launch } from "../../shared/agents";
import { agentProvider } from "../agents/registry";
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
  /** Passed to `session/new` and `session/load`; P5 adds the text-to-cad server. */
  mcpServers?: McpServer[];
  /**
   * The skills root (`src/main/integrations/skills.ts`), named in `session/new` and
   * `session/load` as an additional directory — under both spellings, always
   * (see `sessionRoots` below).
   */
  skillsRoot?: string | null;
  /**
   * Text put in front of the FIRST prompt of a session created here, for an
   * agent that does not load the skills root by itself. Sent once: a resumed
   * session already has it in its transcript — unless it was never prompted,
   * and then the reload carries it (see `loadSession`).
   */
  preamble?: string | null;
  spawnTerminal: SpawnTerminal;
  clientVersion?: string;
  onEvent?: (event: SessionEvent, state: SessionState) => void;
  onTerminalOutput?: TerminalOutputListener;
  onFilesChanged?: (paths: string[]) => void;
  onStderr?: (line: string) => void;
  /** Every wire frame, both directions. */
  record?: (frame: RecordedFrame) => void;
  /** For the tests: whose rules the launch is resolved by (`spawnPlan`). */
  platform?: NodeJS.Platform;
};

export type ProcessExit = { code: number | null; signal: NodeJS.Signals | null };

/** When an adapter that exited under a request did so, as the person reads it. */
const EXIT_PHASE: Record<string, string> = {
  initialize: "while starting",
  "session/prompt": "during the turn",
  "session/new": "while starting the session",
  "session/load": "while reopening the session",
};

/** `cmd.exe`'s metacharacters, escaped with `^` in a command line it parses. */
const CMD_META = /([()\][%!^"`<>&|;, *?])/g;

/**
 * One argv entry for `cmd /d /s /c "…"`: quoted for the program, then escaped
 * for cmd twice. A batch file parses its arguments again when it hands them
 * on (`%*`, `%1`): npm's global shims (`npx.cmd`, `%AppData%\npm\gemini.cmd`)
 * as much as the `node_modules\.bin` ones cross-spawn double-escapes for, and
 * an argument's `"` escaped once flips that second parse's quoting and lets
 * a later `&` end the command.
 */
function cmdArg(arg: string): string {
  const quoted = `"${arg.replace(/(\\*)"/g, '$1$1\\"').replace(/(\\*)$/, "$1$1")}"`;
  return quoted.replace(CMD_META, "^$1").replace(CMD_META, "^$1");
}

/**
 * What to spawn for a provider's launch. On Windows `npx`, `gemini` and most
 * agent CLIs are `.cmd` shims, which `spawn` without a shell does not find
 * (ENOENT) and, since Node 20.12, refuses to run directly (EINVAL) — while the
 * detector, which honours PATHEXT, reports them installed. So the command is
 * resolved along PATH the same way, and a `.cmd` or `.bat` — found there, or
 * named by the launch itself — runs under `cmd.exe` with its argv escaped
 * rather than through `shell: true`, whose line nobody escapes. Elsewhere the
 * launch is spawned as it is.
 */
export function spawnPlan(
  launch: Pick<Launch, "command" | "args">,
  env: Record<string, string>,
  platform: NodeJS.Platform = process.platform,
): { command: string; args: string[]; windowsVerbatimArguments?: boolean } {
  const named = path.extname(launch.command);
  const batch = (file: string) => /\.(cmd|bat)$/i.test(file);
  if (platform !== "win32" || (named && !batch(named))) {
    return { command: launch.command, args: launch.args };
  }
  const throughCmd = (file: string) => {
    // cross-spawn's escaping: the program path escaped for cmd once, each
    // argument quoted for the program and then escaped for cmd (`cmdArg`).
    const line = [file.replace(CMD_META, "^$1"), ...launch.args.map(cmdArg)].join(" ");
    return { command: env.ComSpec ?? env.COMSPEC ?? "cmd.exe", args: ["/d", "/s", "/c", `"${line}"`], windowsVerbatimArguments: true };
  };
  const key = Object.keys(env).find((name) => name.toUpperCase() === "PATH");
  const dirs = (key ? env[key] ?? "" : "").split(path.delimiter).filter(Boolean);
  const pathextKey = Object.keys(env).find((name) => name.toUpperCase() === "PATHEXT");
  // A launch that names its extension is looked for as it is.
  const extensions = named ? [""] : ((pathextKey ? env[pathextKey] : undefined) ?? ".COM;.EXE;.BAT;.CMD").split(";").filter(Boolean);
  const isFile = (file: string) => fs.statSync(file, { throwIfNoEntry: false })?.isFile() ?? false;
  for (const dir of path.isAbsolute(launch.command) ? [""] : dirs) {
    for (const ext of extensions) {
      const candidate = dir ? path.join(dir, launch.command + ext) : launch.command + ext;
      if (!isFile(candidate)) {
        continue;
      }
      return batch(candidate) ? throughCmd(candidate) : { command: candidate, args: launch.args };
    }
  }
  // A named `.cmd` not on PATH still cannot be spawned directly; cmd.exe looks
  // for it the way it would at a prompt.
  return named ? throughCmd(launch.command) : { command: launch.command, args: launch.args };
}

/**
 * The options an adapter is spawned with that it cannot change afterwards —
 * the agent, its launch, its environment, the skills root, the client version
 * — as one string two spawns can be compared by. The directory is left out:
 * the warm pool matches on it separately, and keeps an adapter for another
 * directory rather than closing it.
 */
export function adapterOptionsKey(
  options: Pick<SessionConnectionOptions, "agentId" | "launch" | "env" | "skillsRoot" | "clientVersion">,
): string {
  const sorted = (record: Record<string, string> | undefined) =>
    Object.entries(record ?? {}).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return JSON.stringify([
    options.agentId,
    options.launch.command,
    options.launch.args,
    sorted(options.launch.env),
    sorted(options.env),
    options.skillsRoot ?? null,
    options.clientVersion ?? null,
  ]);
}

/**
 * How much of the adapter's stderr is held: one line's last 8 KB (a `\r`
 * spinner with no newline is one line for as long as it spins), and the last
 * 4 KB of the five lines an unexpected exit shows the person.
 */
const STDERR_LINE_MAX = 8 * 1024;
const STDERR_DETAIL_MAX = 4 * 1024;

/** The last `max` characters, marked as cut when anything was. */
function keepTail(text: string, max: number): string {
  return text.length > max ? `…${text.slice(-max)}` : text;
}

/** The last five stderr lines, as an error's detail. */
function stderrDetail(lines: readonly string[]): string {
  return keepTail(lines.slice(-5).join("\n"), STDERR_DETAIL_MAX);
}

export class SessionConnection {
  readonly client: AcpClient;
  readonly agent: ClientSideConnection;
  readonly process: ChildProcessWithoutNullStreams;
  readonly exited: Promise<ProcessExit>;
  readonly terminals: TerminalManager;

  private stateValue: SessionState;
  private initializeResponse: InitializeResponse | null = null;
  /** The preamble, until the first prompt has carried it. */
  private pendingPreamble: string | null = null;
  /**
   * Content `session/update`s heard since the last prompt started: an agent
   * that streamed took the turn. Not the housekeeping an adapter pushes
   * without having read the prompt (`available_commands_update`,
   * `session_info_update`, `usage_update`, a mode or config change).
   */
  private updatesHeard = 0;
  private closing = false;
  private exit: ProcessExit | null = null;
  private readonly stderrTail: string[] = [];
  /** The last stderr line so far, until its newline (or the stream's end) arrives. */
  private stderrPartial = "";

  constructor(private readonly options: SessionConnectionOptions) {
    this.stateValue = initialSessionState(options.sessionId, options.agentId);
    this.optionsKey = adapterOptionsKey(options);

    const env = { ...options.env, ...options.launch.env };
    const plan = spawnPlan(options.launch, env, options.platform);
    this.process = trackChild(
      spawn(plan.command, plan.args, {
        cwd: options.cwd,
        env,
        stdio: ["pipe", "pipe", "pipe"],
        ...(plan.windowsVerbatimArguments ? { windowsVerbatimArguments: true } : {}),
      }),
      "service",
    );

    this.process.stderr.setEncoding("utf8");
    // Chunks are whatever the pipe hands over, not lines: the text after the
    // last newline waits for the next chunk, so a line split across two is
    // still one line in `onStderr` and in the tail an exit shows the person.
    // A line that never ends (a `\r` spinner) is held to its tail, so the
    // buffer does not grow for as long as the adapter runs.
    this.process.stderr.on("data", (chunk: string) => {
      const lines = (this.stderrPartial + chunk).split("\n");
      this.stderrPartial = (lines.pop() ?? "").slice(-STDERR_LINE_MAX);
      for (const line of lines) {
        this.stderrLine(line);
      }
    });
    this.process.stderr.on("end", () => this.flushStderr());

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

    // The four listeners are read at call time rather than captured, because
    // `adopt` re-points them: a warm adapter is spawned before the session it
    // will belong to exists, and the events it produces have to reach that
    // session's manager and not the pool's placeholder.
    this.terminals = new TerminalManager(options.spawnTerminal, (terminalId, data, exit) =>
      this.options.onTerminalOutput?.(terminalId, data, exit),
    );
    this.client = new AcpClient({
      cwd: options.cwd,
      env: { ...options.env, ...options.launch.env },
      terminals: this.terminals,
      dispatch: (event) => this.dispatch(event),
      onFilesChanged: (paths) => this.options.onFilesChanged?.(paths),
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

  /** Where this adapter was spawned. Fixed for its life; the warm pool matches on it. */
  get cwd(): string {
    return this.options.cwd;
  }

  /** What else it was spawned with (`adapterOptionsKey`); the warm pool matches on that too. */
  readonly optionsKey: string;

  /**
   * Point an idle, already-initialized adapter at a real session (the warm
   * pool, `./warm.ts`). Everything a session brings with it arrives here —
   * its id, its MCP servers, its preamble, and the listeners its manager
   * wants the events on — and everything the adapter cannot change is
   * absent: the directory it was spawned in, its environment and its skills
   * root are the same for every session, which is what makes one adapter
   * interchangeable with another.
   *
   * Only before `session/new` or `session/load`: an adapter that already
   * holds a session is that session's, and re-pointing it would give two
   * threads one transcript.
   */
  adopt(
    options: Pick<
      SessionConnectionOptions,
      | "sessionId"
      | "mcpServers"
      | "preamble"
      | "onEvent"
      | "onTerminalOutput"
      | "onFilesChanged"
      | "onStderr"
    >,
  ): void {
    if (this.stateValue.acpSessionId) {
      throw new Error("this adapter already holds a session");
    }
    Object.assign(this.options, options);
    this.stateValue = initialSessionState(options.sessionId, this.options.agentId);
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
    let response: InitializeResponse;
    try {
      response = await this.agent.initialize({
        protocolVersion: PROTOCOL_VERSION,
        clientInfo: { name: "text-to-cad", version: this.options.clientVersion ?? "0.0.0" },
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
            jetbrains: { air: { version: 1, capabilities: ["nativeSubagentSessions"] } },
          },
        },
      });
    } catch (error) {
      // An adapter that dies before it answers (an `npx` that 404s) closes the
      // stream first; its exit and last stderr lines follow a beat later, and
      // they are the message.
      if (!(error instanceof RequestError)) {
        await Promise.race([this.exited, new Promise((resolve) => setTimeout(resolve, 1_000))]);
      }
      throw this.describe(error, "initialize");
    }
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
        ...this.sessionRoots(),
      });
    } catch (error) {
      throw this.describe(error, "session/new");
    }
    // A session this app created: its first prompt carries the preamble, if
    // the agent needs one. `loadSession` never sets it.
    this.pendingPreamble = this.options.preamble ?? null;
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

  /**
   * `title` is the one the app already knew for this session: the replay
   * sends no `session_info_update`, so the reloaded state starts from it.
   *
   * `answered` is the caller's word that the agent has already answered a
   * prompt in this session (the stored transcript has an agent turn with
   * something in it): an adapter that resumes but replays nothing leaves this
   * connection's own transcript without the user turn that carried the
   * preamble, and it must not be sent a second time.
   */
  async loadSession(
    acpSessionId: string,
    title: string | null = null,
    answered = false,
    /** The stored transcript: what it knows of its turns that the replay cannot say again. */
    stored: readonly Turn[] = [],
  ): Promise<LoadSessionResponse> {
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
      title,
      at: Date.now(),
    });
    let response: LoadSessionResponse;
    try {
      response = await this.agent.loadSession({
        sessionId: acpSessionId,
        cwd: this.options.cwd,
        mcpServers: this.options.mcpServers ?? [],
        ...this.sessionRoots(),
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
    const facts = turnFactsFrom(this.stateValue.turns, stored);
    if (facts.length > 0) {
      this.dispatch({ type: "turns/restored", facts, at: Date.now() });
    }
    // A session that was created and never prompted has no transcript to hold
    // the preamble: the replay carried no user turn, and the first prompt on
    // this connection is the first the agent will read.
    this.pendingPreamble = answered || this.stateValue.turns.some((turn) => turn.role === "user")
      ? null
      : (this.options.preamble ?? null);
    return response;
  }

  /**
   * The skills root, in the two spellings the adapters read: the standard
   * `additionalDirectories` (ACP, SDK 1.4.0) and the older
   * `_meta.additionalRoots` extension. Both, always, for every agent — an
   * adapter reads whichever it knows and ignores the other, and which one a
   * given version reads is not something this app can detect.
   */
  private sessionRoots(): { additionalDirectories: string[]; _meta: { additionalRoots: string[] } } | Record<string, never> {
    const root = this.options.skillsRoot;
    if (!root) {
      return {};
    }
    return { additionalDirectories: [root], _meta: { additionalRoots: [root] } };
  }

  /**
   * The sentence refusing the first block the agent's `promptCapabilities`
   * do not cover, or null. Text and a resource link are every agent's
   * baseline (ACP); an image needs `image` and an embedded file's contents
   * need `embeddedContext`. An agent that answered `initialize` without the
   * field takes the baseline only.
   *
   * `SessionManager.prompt` asks before it marks, titles or starts the turn.
   * No `resource_link` stands in for a missing `embeddedContext`: an
   * attachment's uri is `attachment:///…`, which no agent can open.
   */
  refusal(content: PromptBlock[]): string | null {
    const capabilities = this.initializeResponse?.agentCapabilities?.promptCapabilities ?? {};
    // Said to the person beside the draft it kept: the agent by the name they know it by, and
    // what to do about it — not the capability's wire name.
    const agent = agentProvider(this.options.agentId)?.name ?? this.options.agentId;
    if (!capabilities.image && content.some((block) => block.type === "image")) {
      return `${agent} cannot take an image in a prompt. Remove the attachment to send.`;
    }
    if (!capabilities.embeddedContext && content.some((block) => block.type === "resource")) {
      return `${agent} cannot take a file's contents in a prompt. Remove the attachment to send.`;
    }
    return null;
  }

  /** Send a turn. Resolves with the stop reason; rejects (after dispatching `prompt/error`) on failure. */
  async prompt(content: PromptBlock[], turnId = `turn-${Date.now()}`): Promise<PromptResponse> {
    const acpSessionId = this.requireSession();
    // Refused before the preamble is spent and before anything is written —
    // the transcript included: it is not a turn that failed, and a Retry
    // there would only be refused again. The manager refuses first (with the
    // draft kept); this is for any caller that did not ask.
    const unsupported = this.refusal(content);
    if (unsupported) {
      throw new Error(unsupported);
    }
    // The transcript shows what the person wrote; the preamble is a block the
    // AGENT gets, once, in front of it.
    const preamble = this.pendingPreamble;
    this.pendingPreamble = null;
    this.updatesHeard = 0;
    this.dispatch({ type: "prompt/start", turnId, content, at: Date.now() });
    try {
      const response = await this.agent.prompt({
        sessionId: acpSessionId,
        prompt: [
          ...(preamble ? [{ type: "text" as const, text: preamble }] : []),
          ...content.map(toContentBlock),
        ],
      });
      // The reducer cancels every card when a turn ends (`prompt/end`), so main has to answer the
      // same requests: left in the client's map they would wait for a `cancel()` or `dispose()`
      // that may never come, with the UI showing them cancelled.
      this.client.cancelPendingPermissions();
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
      // A turn the agent did not take carried nothing: the retry, or the next
      // message, is the first the agent actually reads, and the only place a
      // preamble-only agent hears where the skills are. One that streamed
      // before it failed did read it.
      if (this.updatesHeard === 0) {
        this.pendingPreamble ??= preamble;
      }
      const described = this.describe(error, "session/prompt");
      // The turn is over, and the reducer cancels every card when `prompt/error`
      // lands (as for `prompt/end`): answer the same requests, or the client's
      // map stays open behind cards that read cancelled.
      this.client.cancelPendingPermissions();
      // After `close` the rejection is the SDK tearing down the turn we
      // killed, not a failure of it: `closed` was the last word.
      if (!this.closing) {
        this.dispatch({ type: "prompt/error", message: described.message, at: Date.now() });
      }
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

  private stderrLine(whole: string) {
    if (!whole.trim()) {
      return;
    }
    const line = keepTail(whole, STDERR_LINE_MAX);
    this.stderrTail.push(line);
    if (this.stderrTail.length > 40) {
      this.stderrTail.shift();
    }
    this.options.onStderr?.(line);
  }

  /** The unterminated last line, as a line of its own. */
  private flushStderr() {
    const line = this.stderrPartial;
    this.stderrPartial = "";
    this.stderrLine(line);
  }

  private onProcessExit(exit: ProcessExit) {
    this.client.dispose();
    // `exit` can come before stderr's `end`: what is buffered is the last
    // thing the adapter said, and belongs in the message below.
    this.flushStderr();
    if (this.closing) {
      return;
    }
    const detail = stderrDetail(this.stderrTail);
    const message =
      `${agentProvider(this.options.agentId)?.name ?? this.options.agentId} exited unexpectedly` +
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
        const tail = stderrDetail(this.stderrTail);
        const code = this.exit?.code;
        // The method and the agent id are for the log; the person reads
        // which agent stopped and when, in words.
        console.warn(`[acp] ${method}: ${this.options.agentId} exited${code != null ? ` (code ${code})` : ""}`);
        const name = agentProvider(this.options.agentId)?.name ?? this.options.agentId;
        return new Error(`${name} exited ${EXIT_PHASE[method] ?? "unexpectedly"}.${tail ? `\n${tail}` : ""}`, { cause: error });
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
            if (TURN_UPDATE_KINDS.has(update.update.sessionUpdate)) this.updatesHeard += 1;
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

/** The updates only an agent that is working on a prompt sends. */
const TURN_UPDATE_KINDS: ReadonlySet<string> = new Set([
  "agent_message_chunk",
  "agent_thought_chunk",
  "tool_call",
  "tool_call_update",
  "plan",
]);

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
    case "resource":
      return {
        type: "resource" as const,
        resource: { uri: block.uri, text: block.text, mimeType: block.mimeType ?? undefined },
      };
  }
}
