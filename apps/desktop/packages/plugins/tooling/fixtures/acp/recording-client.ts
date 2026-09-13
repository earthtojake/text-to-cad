/**
 * ACP Client implementation for fixture recording.
 *
 * Mirrors the wiring of AcpSessionRuntime.buildAgentClient, replacing:
 *   - sessionUpdate   → records raw SessionNotification verbatim
 *   - requestPermission → auto-approves (first allow_once/allow_always option) + records
 *   - readTextFile    → proxies node fs/promises + records
 *   - writeTextFile   → proxies node fs/promises + records
 *   - createTerminal  → delegates to AgentTerminalManager + records lifecycle
 *   - terminalOutput  → delegates to AgentTerminalManager
 *   - waitForTerminalExit → delegates to AgentTerminalManager
 *   - killTerminal    → delegates to AgentTerminalManager
 *   - releaseTerminal → delegates to AgentTerminalManager
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import type {
  Client,
  CreateTerminalRequest,
  CreateTerminalResponse,
  KillTerminalRequest,
  KillTerminalResponse,
  ReadTextFileRequest,
  ReadTextFileResponse,
  ReleaseTerminalRequest,
  ReleaseTerminalResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionNotification,
  TerminalOutputRequest,
  TerminalOutputResponse,
  WaitForTerminalExitRequest,
  WaitForTerminalExitResponse,
  WriteTextFileRequest,
  WriteTextFileResponse,
} from '@agentclientprotocol/sdk';
import type { AcpProcessHost } from '@emdash/core/runtimes/acp/api/transport';
import { AgentTerminalManager } from '@emdash/core/runtimes/acp/node';
import type { Recorder } from './recorder';

/**
 * Build a recording ACP Client.
 *
 * @param recorder   - Recorder instance to append events to.
 * @param host       - AcpProcessHost used to spawn terminals.
 * @param sessionId  - The ACP sessionId for the session this client handles.
 *                     Populated once from the first sessionUpdate notification.
 * @returns          - An ACP Client + a dispose function to release terminals.
 */
export function buildRecordingClient(
  recorder: Recorder,
  host: AcpProcessHost,
  getSessionId: () => string | null
): { client: Client; dispose: () => void } {
  const CONV_ID = 'recording-session';

  const terminals = new AgentTerminalManager(host, {
    onTerminalCreated(e) {
      recorder.record({
        kind: 'terminal_created',
        terminalId: e.terminalId,
        command: e.command,
        args: e.args,
        cwd: e.cwd,
      });
    },
    onTerminalOutput(e) {
      recorder.record({
        kind: 'terminal_output',
        terminalId: e.terminalId,
        chunk: e.chunk,
        truncated: e.truncated,
      });
    },
    onTerminalExit(e) {
      recorder.record({
        kind: 'terminal_exit',
        terminalId: e.terminalId,
        exitCode: e.exitStatus.exitCode,
        signal: e.exitStatus.signal,
      });
    },
    onTerminalReleased(e) {
      recorder.record({ kind: 'terminal_released', terminalId: e.terminalId });
    },
  });

  const client: Client = {
    sessionUpdate: async (params: SessionNotification): Promise<void> => {
      recorder.record({
        kind: 'session_update',
        sessionId: params.sessionId,
        update: params.update,
      });
    },

    requestPermission: async (
      params: RequestPermissionRequest
    ): Promise<RequestPermissionResponse> => {
      // Auto-approve: prefer allow_always, then allow_once, then first option.
      const approved =
        params.options.find((o) => o.optionId === 'allow_always') ??
        params.options.find((o) => o.optionId === 'allow_once') ??
        params.options[0];

      const resolvedOptionId = approved?.optionId ?? null;

      recorder.record({
        kind: 'permission_request',
        sessionId: params.sessionId,
        request: params,
        resolvedOptionId,
      });

      if (!resolvedOptionId) {
        return { outcome: { outcome: 'cancelled' } };
      }

      return { outcome: { outcome: 'selected', optionId: resolvedOptionId } };
    },

    readTextFile: async (params: ReadTextFileRequest): Promise<ReadTextFileResponse> => {
      let ok = false;
      let content = '';
      try {
        content = await readFile(params.path, 'utf8');
        ok = true;
      } catch {
        // file not found or unreadable — return empty content, log the attempt
      }
      recorder.record({ kind: 'fs_read', path: params.path, ok });
      return { content };
    },

    writeTextFile: async (params: WriteTextFileRequest): Promise<WriteTextFileResponse> => {
      await mkdir(dirname(params.path), { recursive: true });
      await writeFile(params.path, params.content ?? '', 'utf8');
      recorder.record({ kind: 'fs_write', path: params.path });
      return {};
    },

    createTerminal: async (params: CreateTerminalRequest): Promise<CreateTerminalResponse> => {
      const envRecord = params.env
        ? Object.fromEntries(params.env.map((e) => [e.name, e.value]))
        : {};
      const cwd = params.cwd ?? process.cwd();
      const terminalId = await terminals.create(CONV_ID, {
        command: params.command,
        args: params.args ?? [],
        env: envRecord,
        cwd,
        outputByteLimit: params.outputByteLimit,
      });
      return { terminalId };
    },

    terminalOutput: async (params: TerminalOutputRequest): Promise<TerminalOutputResponse> => {
      const terminal = terminals.get(params.terminalId);
      if (!terminal) {
        throw new Error(`RecordingClient: terminal not found: ${params.terminalId}`);
      }
      const snap = terminal.outputSnapshot();
      return {
        output: snap.output,
        truncated: snap.truncated,
        exitStatus: snap.exitStatus ?? undefined,
      };
    },

    waitForTerminalExit: async (
      params: WaitForTerminalExitRequest
    ): Promise<WaitForTerminalExitResponse> => {
      const terminal = terminals.get(params.terminalId);
      if (!terminal) {
        throw new Error(`RecordingClient: terminal not found: ${params.terminalId}`);
      }
      const status = await terminal.waitForExit();
      return { exitCode: status.exitCode, signal: status.signal ?? undefined };
    },

    killTerminal: async (params: KillTerminalRequest): Promise<KillTerminalResponse> => {
      const terminal = terminals.get(params.terminalId);
      if (!terminal) {
        throw new Error(`RecordingClient: terminal not found: ${params.terminalId}`);
      }
      terminal.kill();
      return {};
    },

    releaseTerminal: async (params: ReleaseTerminalRequest): Promise<ReleaseTerminalResponse> => {
      terminals.release(params.terminalId);
      return {};
    },
  };

  function dispose() {
    terminals.disposeConversation(CONV_ID);
  }

  return { client, dispose };
}
