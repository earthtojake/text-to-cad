import type {
  Client,
  McpCapabilities,
  SessionUpdate,
  ClientCapabilities,
} from '@agentclientprotocol/sdk';
import type { Result } from '@emdash/shared';
import { ok, toSerializedError } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import type { InitializeFailedError, NormalizedEvent, SpawnFailedError } from '#runtimes/acp/api';
import { acpErr, decodeSessionUpdate } from '#runtimes/acp/api';
import type { AcpProcessHandle, AcpProcessHost } from '#runtimes/acp/api/transport';
import type {
  AcpAgentApi,
  AgentHostAcpSpawn,
  IAcpBehavior,
} from '#services/agent-plugins/api/plugins';

type AcpAgentProcessHost = Pick<AcpProcessHost, 'spawn' | 'spawnTerminal'>;

type ProcessClosed =
  | {
      kind: 'exit';
      exitCode: number | null;
    }
  | {
      kind: 'error';
      error: Error;
      exitCode: number | null;
    };

export type AcpConnectionError = SpawnFailedError | InitializeFailedError;
export type AcpSessionUpdateNormalizer = (raw: SessionUpdate) => NormalizedEvent;

/** Live connection to one spawned agent process. */
export interface AcpAgentConnection {
  agent: AcpAgentApi;
  normalize: AcpSessionUpdateNormalizer;
  supportsLoadSession: boolean;
  mcpCapabilities: Required<Pick<McpCapabilities, 'http' | 'sse'>>;
}

/**
 * Spin up an agent process, initialize it, and return a ready connection.
 * Setup failures are reported as Result errors; `onClosed` is reserved for
 * unexpected exits after the connection is ready.
 */
export async function createAcpAgentConnection(
  deps: {
    host: AcpAgentProcessHost;
    behavior: IAcpBehavior;
    logger?: Logger;
  },
  args: {
    providerId: string;
    clientCapabilities?: ClientCapabilities;
    spawn: AgentHostAcpSpawn;
    scope: Scope;
    /** Factory called once; the runtime passes its buildAgentClient result here. */
    buildClient: (agent: AcpAgentApi, normalize: AcpSessionUpdateNormalizer) => Client;
    /** Called when a ready process exits unexpectedly. */
    onClosed: (exitCode: number | null) => void;
  }
): Promise<Result<AcpAgentConnection, AcpConnectionError>> {
  const { providerId, spawn, scope, buildClient, onClosed } = args;
  const { host, behavior, logger = noopLogger } = deps;
  const connectionScope = scope.child(`acp-connection:${providerId}`);

  let handle: AcpProcessHandle;
  try {
    handle = await host.spawn({
      command: spawn.command,
      args: spawn.args,
      env: spawn.env,
      cwd: spawn.cwd,
    });
  } catch (e) {
    await connectionScope.dispose();
    return acpErr.spawnFailed(toSerializedError(e));
  }

  if (handle.stderr) {
    const onStderr = (data: Buffer): void => {
      logger.debug('createAcpAgentConnection: agent stderr', { text: data.toString().trim() });
    };
    handle.stderr.on('data', onStderr);
    connectionScope.add(() => {
      handle.stderr?.off?.('data', onStderr);
      handle.stderr?.removeListener?.('data', onStderr);
    });
  }

  connectionScope.add(() => {
    try {
      handle.kill('SIGTERM');
    } catch {
      // Ignore teardown errors; process may have already exited.
    }
  });

  const processClosed = onceProcessClosed(handle, logger);

  const normalize = (raw: SessionUpdate): NormalizedEvent => {
    const base = decodeSessionUpdate(raw);
    return behavior.enrich ? behavior.enrich(base, raw) : base;
  };

  let connection: AcpAgentApi;
  try {
    connection = behavior.connect({ stdin: handle.stdin, stdout: handle.stdout }, (agent) =>
      buildClient(agent, normalize)
    );
  } catch (e) {
    await connectionScope.dispose();
    return acpErr.initializeFailed(toSerializedError(e));
  }

  try {
    const initialized = await Promise.race([
      initializeAgent(connection, host, args.clientCapabilities),
      processClosed.then(failClosedBeforeReady),
    ]);
    const supportsLoadSession = initialized.agentCapabilities?.loadSession === true;
    const mcpCapabilities = {
      http: initialized.agentCapabilities?.mcpCapabilities?.http === true,
      sse: initialized.agentCapabilities?.mcpCapabilities?.sse === true,
    };
    logger.debug('createAcpAgentConnection: initialized', { supportsLoadSession, mcpCapabilities });
    void processClosed.then((closed) => {
      if (connectionScope.disposed) return;
      onClosed(exitCodeFromClosed(closed));
    });
    return ok({ agent: connection, normalize, supportsLoadSession, mcpCapabilities });
  } catch (e) {
    logger.error('createAcpAgentConnection: initialize failed', {
      error: e instanceof Error ? e.message : String(e),
    });
    await connectionScope.dispose();
    return acpErr.initializeFailed(toSerializedError(e));
  }
}

function onceProcessClosed(handle: AcpProcessHandle, logger: Logger): Promise<ProcessClosed> {
  return new Promise((resolve) => {
    let settled = false;
    const settle = (closed: ProcessClosed): void => {
      if (settled) return;
      settled = true;
      resolve(closed);
    };

    handle.onExit((exitCode) => {
      settle({ kind: 'exit', exitCode });
    });
    handle.onError((error) => {
      logger.error('createAcpAgentConnection: agent process error', { error: error.message });
      settle({ kind: 'error', error, exitCode: handle.exitCode });
    });
  });
}

function initializeAgent(
  agent: AcpAgentApi,
  host: AcpAgentProcessHost,
  capabilities?: ClientCapabilities
) {
  const clientCapabilities: ClientCapabilities & { _meta?: Record<string, unknown> } = {
    fs: { readTextFile: true, writeTextFile: true },
    terminal: typeof host.spawnTerminal === 'function',
    // Claude re-enables AskUserQuestion and forwards MCP questions only when
    // the client can render a form elicitation (see SessionCell.requestElicitation).
    elicitation: { form: {} },
    // Both adapters run commands themselves and narrate them through _meta
    // (terminal_info / terminal_output / terminal_exit). Codex always does;
    // this flag is what turns the narration on for Claude, whose Bash output
    // otherwise arrives as a plain code block after the command ends.
    _meta: { terminal_output: true },
  };
  return agent.initialize({
    protocolVersion: 1,
    clientInfo: { name: 'emdash', version: '1' },
    clientCapabilities: capabilities ?? clientCapabilities,
  });
}

function failClosedBeforeReady(closed: ProcessClosed): never {
  if (closed.kind === 'error') throw closed.error;
  throw new Error(
    `ACP agent process exited before initialize completed (code ${closed.exitCode ?? 'null'})`
  );
}

function exitCodeFromClosed(closed: ProcessClosed): number | null {
  return closed.exitCode;
}
