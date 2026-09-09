/**
 * Ordered, append-only event log for ACP transcript capture.
 *
 * Every raw `SessionUpdate` notification and client-side action (prompt, permission,
 * fs, terminal, config/mode change) is recorded verbatim in arrival order with a
 * monotonic sequence number and a wall-clock timestamp. The resulting log is the
 * canonical fixture format consumed by AcpSessionParser snapshot tests.
 *
 * The recorder is deliberately dumb: it stores raw data and makes no assertions
 * about shape. Tests that import the fixture may cast/validate as needed.
 */
import { writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';

/** Raw ACP protocol fields from a session/update notification. */
export interface RecordedSessionUpdate {
  kind: 'session_update';
  /** ACP sessionId from the notification envelope. */
  sessionId: string;
  /** The raw SessionUpdate object — serialized verbatim. */
  update: unknown;
}

/** A user prompt sent to the agent. */
export interface RecordedPrompt {
  kind: 'prompt';
  sessionId: string;
  /** Prompt content blocks (text/image). */
  content: unknown;
}

/** The agent's stop reason when a prompt() call resolves. */
export interface RecordedPromptResult {
  kind: 'prompt_result';
  sessionId: string;
  stopReason: string | null | undefined;
}

/** A permission request received from the agent + how it was resolved. */
export interface RecordedPermissionRequest {
  kind: 'permission_request';
  sessionId: string;
  /** The raw RequestPermissionRequest params. */
  request: unknown;
  /** The optionId chosen by auto-approval, or null for cancel. */
  resolvedOptionId: string | null;
}

/** A file read by the agent via fs.readTextFile. */
export interface RecordedFsRead {
  kind: 'fs_read';
  path: string;
  /** True if the read succeeded. */
  ok: boolean;
}

/** A file write from the agent via fs.writeTextFile. */
export interface RecordedFsWrite {
  kind: 'fs_write';
  path: string;
}

/** A terminal spawned by the agent via terminal.create. */
export interface RecordedTerminalCreated {
  kind: 'terminal_created';
  terminalId: string;
  command: string;
  args: string[];
  cwd: string;
}

/** An output chunk received from a running terminal. */
export interface RecordedTerminalOutput {
  kind: 'terminal_output';
  terminalId: string;
  chunk: string;
  truncated: boolean;
}

/** A terminal that has exited. */
export interface RecordedTerminalExit {
  kind: 'terminal_exit';
  terminalId: string;
  exitCode: number | null;
  signal: string | null;
}

/** A terminal that was released by the agent. */
export interface RecordedTerminalReleased {
  kind: 'terminal_released';
  terminalId: string;
}

/** A setSessionConfigOption call + its response. */
export interface RecordedConfigOptionSet {
  kind: 'config_option_set';
  sessionId: string;
  configId: string;
  value: string;
  /** The updated configOptions array returned by the agent. */
  responseConfigOptions: unknown;
}

/** A setSessionMode call + its response. */
export interface RecordedModeSet {
  kind: 'mode_set';
  sessionId: string;
  modeId: string;
}

export type RecordedEvent =
  | RecordedSessionUpdate
  | RecordedPrompt
  | RecordedPromptResult
  | RecordedPermissionRequest
  | RecordedFsRead
  | RecordedFsWrite
  | RecordedTerminalCreated
  | RecordedTerminalOutput
  | RecordedTerminalExit
  | RecordedTerminalReleased
  | RecordedConfigOptionSet
  | RecordedModeSet;

/** A single entry in the log — wraps the event with sequencing metadata. */
export interface RecordedEntry {
  /** Zero-based monotonic sequence number. */
  seq: number;
  /** Wall-clock timestamp (ms since epoch). Parser tests should not assert on this. */
  ts: number;
  event: RecordedEvent;
}

export interface TranscriptMeta {
  providerId: string;
  model: string | null;
  cwd: string;
  sessionId: string;
  generatedAt: string;
  agentCapabilities: unknown;
  initialModes: unknown;
  initialConfigOptions: unknown;
  initialAvailableCommands: unknown;
}

export class Recorder {
  private seq = 0;
  private readonly entries: RecordedEntry[] = [];

  constructor(public meta: Partial<TranscriptMeta> = {}) {}

  record(event: RecordedEvent): void {
    this.entries.push({ seq: this.seq++, ts: Date.now(), event });
  }

  get events(): readonly RecordedEntry[] {
    return this.entries;
  }

  /** Serialize the full transcript to disk. */
  async save(outPath: string): Promise<void> {
    await mkdir(dirname(outPath), { recursive: true });
    const payload = { meta: this.meta, events: this.entries };
    await writeFile(outPath, JSON.stringify(payload, null, 2), 'utf8');
  }
}
