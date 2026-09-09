/**
 * Reusable test helpers for ACP unit tests.
 *
 * Not a test file itself (no `.test.` suffix) — Vitest will not collect it.
 * Import from `./acp-test-support` in test files that need it.
 */

import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import type { Client } from '@agentclientprotocol/sdk';
import { createScope } from '@emdash/shared/concurrency';
import { noopLogger } from '@emdash/shared/logger';
import { vi } from 'vitest';
import type { HostDependencyResolver } from '#primitives/host-dependencies/api';
import type {
  AcpFs,
  AcpProcessHandle,
  AcpProcessHost,
  AcpTerminalExit,
  AcpTerminalProcess,
} from '#runtimes/acp/api/transport';
import type { AgentTerminalHooks } from '#runtimes/acp/node/agent-ports/terminal-manager';
import type { AcpRuntimeDeps, AcpStartInput } from '#runtimes/acp/node/runtime/types';
import {
  AgentPluginHost,
  createPluginRegistry,
  type AcpAgentApi,
  type CLIAgentPluginProvider,
  type IAcpBehavior,
  type ResolvedAuthProvider,
} from '#services/agent-plugins/api/plugins';
import type { IExecutionContext } from '#services/exec/api';
import { FakePtySpawner } from '#services/pty/testing';
import { createMemorySessionIntentStore } from '#services/session-intents/api';

/**
 * Creates recording terminal hooks.
 * `emitted(field)` returns all objects emitted via that method.
 */
export function createRecordingListener() {
  const terminalCreated: {
    conversationId: string;
    terminalId: string;
    command: string;
    args: string[];
    cwd: string;
  }[] = [];
  const terminalOutput: {
    conversationId: string;
    terminalId: string;
    chunk: string;
    truncated: boolean;
  }[] = [];
  const terminalExit: {
    conversationId: string;
    terminalId: string;
    exitStatus: AcpTerminalExit;
  }[] = [];
  const terminalReleased: { conversationId: string; terminalId: string }[] = [];

  const listener: AgentTerminalHooks = {
    onTerminalCreated: (e) => terminalCreated.push(e),
    onTerminalOutput: (e) => terminalOutput.push(e),
    onTerminalExit: (e) => terminalExit.push(e),
    onTerminalReleased: (e) => terminalReleased.push(e),
  };

  return {
    listener,
    terminalCreated,
    terminalOutput,
    terminalExit,
    terminalReleased,
    clear() {
      terminalCreated.length = 0;
      terminalOutput.length = 0;
      terminalExit.length = 0;
      terminalReleased.length = 0;
    },
  };
}

/**
 * An injectable fake that implements AcpAgentApi.
 * After the plugin's `connect(io, toClient)` is called, `capturedClient`
 * holds the runtime's inbound Client handler.
 */
export class FakeAcpAgent implements AcpAgentApi {
  initialize = vi.fn().mockResolvedValue({
    protocolVersion: 1,
    agentCapabilities: { loadSession: true },
  });
  newSession = vi.fn().mockResolvedValue({ sessionId: 'session-1' });
  loadSession = vi.fn().mockResolvedValue({});
  closeSession = vi.fn().mockResolvedValue({});
  cancel = vi.fn().mockResolvedValue({});
  prompt = vi.fn().mockResolvedValue({ stopReason: 'end_turn' });
  setSessionConfigOption = vi.fn().mockResolvedValue({});
  setSessionMode = vi.fn().mockResolvedValue({});

  /** The Client handler the runtime registered via toClient(). Available after connect(). */
  capturedClient: Client | null = null;

  readonly behavior: Pick<IAcpBehavior, 'connect'> = {
    connect: (_io, toClient) => {
      this.capturedClient = toClient(this as never);
      return this;
    },
  };

  reset() {
    this.initialize = vi.fn().mockResolvedValue({
      protocolVersion: 1,
      agentCapabilities: { loadSession: true },
    });
    this.newSession = vi.fn().mockResolvedValue({ sessionId: 'session-1' });
    this.loadSession = vi.fn().mockResolvedValue({});
    this.closeSession = vi.fn().mockResolvedValue({});
    this.cancel = vi.fn().mockResolvedValue({});
    this.prompt = vi.fn().mockResolvedValue({ stopReason: 'end_turn' });
    this.setSessionConfigOption = vi.fn().mockResolvedValue({});
    this.setSessionMode = vi.fn().mockResolvedValue({});
    this.capturedClient = null;
  }
}

// ---------------------------------------------------------------------------
// FakeAcpTerminalProcess
// ---------------------------------------------------------------------------

/**
 * A controllable fake AcpTerminalProcess for use in tests.
 * Push output via `pushOutput(chunk)` and trigger exit via `triggerExit(status)`.
 */
export class FakeAcpTerminalProcess extends EventEmitter implements AcpTerminalProcess {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  exitCode: number | null = null;
  readonly killFn = vi.fn<(signal?: NodeJS.Signals) => void>();

  onExit(cb: (status: AcpTerminalExit) => void): void {
    this.on('exit', cb);
  }

  onError(cb: (err: Error) => void): void {
    this.on('error', cb);
  }

  kill(signal?: NodeJS.Signals): void {
    this.killFn(signal);
  }

  /** Push a chunk of text to stdout so ManagedTerminal buffers it. */
  pushOutput(chunk: string): void {
    this.stdout.push(chunk);
  }

  /** Simulate process exit. */
  triggerExit(status: AcpTerminalExit): void {
    this.exitCode = status.exitCode;
    this.emit('exit', status);
    this.stdout.push(null);
    this.stderr.push(null);
  }
}

export class FakeAcpProcessHandle extends EventEmitter implements AcpProcessHandle {
  readonly stdin = new PassThrough();
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  exitCode: number | null = null;
  readonly kill = vi.fn<(signal?: NodeJS.Signals) => void>();

  onExit(cb: (code: number | null) => void): void {
    this.on('exit', (code: number | null) => cb(code));
  }

  onError(cb: (err: Error) => void): void {
    this.on('error', cb);
  }

  emitExit(code: number | null = null): void {
    this.exitCode = code;
    this.emit('exit', code);
  }

  emitError(err: Error): void {
    this.emit('error', err);
  }
}

// Alias for backward compat.
export { FakeAcpProcessHandle as FakeChildProcess };

export const fakeAcpFs: AcpFs = {
  readFile: vi.fn().mockResolvedValue(''),
  writeFile: vi.fn().mockResolvedValue(undefined),
  mkdir: vi.fn().mockResolvedValue(undefined),
};

export class FakeAcpProcessHost implements AcpProcessHost {
  readonly fs: AcpFs = fakeAcpFs;
  private readonly handles: FakeAcpProcessHandle[] = [];
  private readonly terminalProcs: FakeAcpTerminalProcess[] = [];
  /** When set, the next spawnTerminal call returns this instance. */
  nextTerminal: FakeAcpTerminalProcess | null = null;
  readonly spawnTerminalFn =
    vi.fn<
      (spec: {
        command: string;
        args: string[];
        env: Record<string, string>;
        cwd: string;
      }) => Promise<AcpTerminalProcess>
    >();

  resolveSpawnContext = vi.fn().mockResolvedValue({
    cli: '/usr/local/bin/fake-agent',
    agentEnv: {},
  });

  async spawn(_spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpProcessHandle> {
    const handle = new FakeAcpProcessHandle();
    this.handles.push(handle);
    return handle;
  }

  async spawnTerminal(spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpTerminalProcess> {
    const proc = this.nextTerminal ?? new FakeAcpTerminalProcess();
    this.nextTerminal = null;
    this.terminalProcs.push(proc);
    this.spawnTerminalFn(spec);
    return proc;
  }

  get lastHandle(): FakeAcpProcessHandle {
    const h = this.handles.at(-1);
    if (!h) throw new Error('FakeAcpProcessHost: no handle spawned yet');
    return h;
  }

  get allHandles(): FakeAcpProcessHandle[] {
    return this.handles;
  }

  get lastTerminalProc(): FakeAcpTerminalProcess {
    const p = this.terminalProcs.at(-1);
    if (!p) throw new Error('FakeAcpProcessHost: no terminal spawned yet');
    return p;
  }

  get allTerminalProcs(): FakeAcpTerminalProcess[] {
    return this.terminalProcs;
  }
}

type AcpHarnessOptions = Partial<AcpRuntimeDeps> & {
  acpBehavior?: IAcpBehavior;
  authProvider?: ResolvedAuthProvider;
};

export function testPluginHost(
  options: {
    providerId?: string;
    acpBehavior?: IAcpBehavior;
    authProvider?: ResolvedAuthProvider;
  } = {}
): AgentPluginHost {
  const providerId = options.providerId ?? 'claude';
  const registry = createPluginRegistry<CLIAgentPluginProvider>();

  registry.register({
    metadata: {
      id: providerId,
      name: options.authProvider?.name ?? 'Claude Code',
      description: 'Test provider',
      websiteUrl: 'https://example.com',
    },
    capabilities: {
      acp: options.acpBehavior ? { kind: 'supported' } : { kind: 'none' },
      auth: options.authProvider?.auth ?? { kind: 'none' },
      hostDependency: {
        binaryNames: [providerId],
        installCommands: {},
        updates: { kind: 'none' },
      },
    },
    behavior: {
      acp: options.acpBehavior,
      auth: options.authProvider?.behavior,
    },
  } as unknown as CLIAgentPluginProvider);

  return new AgentPluginHost({
    scope: createScope({ label: 'test-acp' }),
    registry,
    exec: fakeExec(),
    dependencies: fakeDependencies(providerId),
    fs: fakePluginFs(),
    env: async () => ({ PATH: '/bin', HOME: '/home/test' }),
    homeDir: '/home/test',
  });
}

function fakeDependencies(providerId: string): HostDependencyResolver {
  return {
    resolve: async () => ({
      success: true,
      data: {
        id: providerId,
        command: providerId,
        path: providerId,
        realpath: providerId,
        source: { kind: 'auto' },
      },
    }),
  };
}

export function makeAcpHarness(options: AcpHarnessOptions = {}) {
  const { acpBehavior, authProvider, ...depOverrides } = options;
  const agent = new FakeAcpAgent();
  const fakeHost = new FakeAcpProcessHost();
  const ptySpawner = new FakePtySpawner();

  const deps: AcpRuntimeDeps = {
    agentHost:
      depOverrides.agentHost ??
      testPluginHost({
        acpBehavior: acpBehavior ?? {
          buildSpawn: () => ({ command: '/fake/node', args: ['agent.js'], env: {} }),
          connect: agent.behavior.connect,
        },
        authProvider: authProvider ?? {
          name: 'Claude Code',
          auth: { kind: 'none' },
        },
      }),
    host: fakeHost,
    resolveAttachment: vi.fn().mockResolvedValue({ data: '', mimeType: 'image/png' }),
    intents: depOverrides.intents ?? createMemorySessionIntentStore(),
    logger: noopLogger,
    ...depOverrides,
  };

  return {
    deps,
    fakeHost,
    get lastChild(): FakeAcpProcessHandle {
      return fakeHost.lastHandle;
    },
    get children(): FakeAcpProcessHandle[] {
      return fakeHost.allHandles;
    },
    agent,
    ptySpawner,
    client(): Client {
      if (!agent.capturedClient) {
        throw new Error('capturedClient is null — has startSession() been called?');
      }
      return agent.capturedClient;
    },
  };
}

function fakeExec(): IExecutionContext {
  return {
    supportsLocalSpawn: false,
    async exec() {
      throw new Error('missing');
    },
    async execStreaming() {
      return { exitCode: 0 };
    },
    dispose() {},
  };
}

function fakePluginFs() {
  return {
    async read() {
      return null;
    },
    async write() {},
    async delete() {},
    async exists() {
      return false;
    },
    async list() {
      return [];
    },
  };
}

export function makeStartInput(
  overrides: Partial<AcpStartInput> & { conversationId?: string } = {}
): AcpStartInput {
  return {
    conversationId: overrides.conversationId ?? 'conv-1',
    providerId: 'claude',
    cwd: '/tmp/workspace',
    sessionId: null,
    model: null,
    ...overrides,
  };
}
